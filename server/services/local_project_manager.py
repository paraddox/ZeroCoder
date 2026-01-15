"""
Local Project Manager
=====================

Manages local clones of projects for:
- Spec creation wizard (new projects)
- Task editing (edit mode)

Local clones are stored at ~/.zerocoder/projects/{name}/
"""

import asyncio
import json
import logging
import subprocess
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_projects_dir() -> Path:
    """Get the projects directory for local clones."""
    from registry import get_projects_dir as registry_get_projects_dir
    return registry_get_projects_dir()


class LocalProjectManager:
    """Manages local clone for wizard and edit mode."""

    def __init__(self, project_name: str, git_url: str):
        """
        Initialize the LocalProjectManager.

        Args:
            project_name: Name of the project
            git_url: Git remote URL (https:// or git@)
        """
        self.project_name = project_name
        self.git_url = git_url
        self.local_path = get_projects_dir() / project_name

    async def ensure_cloned(self) -> tuple[bool, str]:
        """
        Clone repo if not already cloned.

        Returns:
            Tuple of (success, message)
        """
        if self.local_path.exists() and (self.local_path / ".git").exists():
            return True, "Already cloned"

        try:
            self.local_path.parent.mkdir(parents=True, exist_ok=True)

            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "clone", self.git_url, str(self.local_path)],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for clone
            )

            if result.returncode != 0:
                return False, f"Clone failed: {result.stderr}"

            logger.info(f"Cloned project {self.project_name} to {self.local_path}")
            return True, "Cloned successfully"

        except subprocess.TimeoutExpired:
            return False, "Clone timed out"
        except Exception as e:
            logger.exception(f"Failed to clone project {self.project_name}")
            return False, f"Clone error: {e}"

    async def pull_latest(self) -> tuple[bool, str]:
        """
        Pull latest from main.

        Returns:
            Tuple of (success, message)
        """
        if not self.local_path.exists():
            return await self.ensure_cloned()

        try:
            # Checkout main first
            checkout_result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", str(self.local_path), "checkout", "main"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if checkout_result.returncode != 0:
                # Try to handle dirty state by stashing
                stash_result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "-C", str(self.local_path), "stash", "push", "-m", "auto-stash before pull"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if stash_result.returncode != 0:
                    return False, f"Checkout failed and could not stash: {checkout_result.stderr}"

                # Retry checkout after stash
                checkout_result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "-C", str(self.local_path), "checkout", "main"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if checkout_result.returncode != 0:
                    return False, f"Checkout failed after stash: {checkout_result.stderr}"

            # Pull from origin
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", str(self.local_path), "pull", "origin", "main"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                return False, f"Pull failed: {result.stderr}"

            return True, "Pulled successfully"

        except subprocess.TimeoutExpired:
            return False, "Pull timed out"
        except Exception as e:
            logger.warning(f"Failed to pull project {self.project_name}: {e}")
            return False, f"Pull error: {e}"

    async def sync_beads(self) -> tuple[bool, str]:
        """
        Sync beads state (run bd sync).

        Returns:
            Tuple of (success, message)
        """
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["bd", "sync"],
                cwd=str(self.local_path),
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                return False, f"Beads sync failed: {result.stderr}"

            return True, "Synced successfully"

        except subprocess.TimeoutExpired:
            return False, "Sync timed out"
        except FileNotFoundError:
            return False, "beads CLI (bd) not found"
        except Exception as e:
            logger.warning(f"Failed to sync beads for {self.project_name}: {e}")
            return False, f"Sync error: {e}"

    async def push_changes(self, message: str = "Update tasks") -> tuple[bool, str]:
        """
        Push local changes to remote.

        Args:
            message: Commit message

        Returns:
            Tuple of (success, message)
        """
        try:
            # Add all changes
            add_result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", str(self.local_path), "add", "."],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if add_result.returncode != 0:
                return False, f"Git add failed: {add_result.stderr}"

            # Check if there's anything to commit
            status_result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", str(self.local_path), "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if status_result.stdout.strip():
                # There are changes to commit
                commit_result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "-C", str(self.local_path), "commit", "-m", message],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if commit_result.returncode != 0:
                    return False, f"Git commit failed: {commit_result.stderr}"

            # Push
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "-C", str(self.local_path), "push", "origin", "main"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                return False, f"Push failed: {result.stderr}"

            # Sync beads
            sync_success, sync_msg = await self.sync_beads()
            if not sync_success:
                logger.warning(f"Beads sync failed after push: {sync_msg}")
                # Don't fail the whole operation if sync fails - changes are pushed

            return True, "Changes pushed successfully"

        except subprocess.TimeoutExpired:
            return False, "Push timed out"
        except Exception as e:
            logger.exception(f"Failed to push changes for {self.project_name}")
            return False, f"Push error: {e}"

    # =========================================================================
    # Task Management (Edit Mode)
    # =========================================================================

    async def create_task(
        self,
        title: str,
        description: str = "",
        priority: int = 2,
        task_type: str = "feature"
    ) -> tuple[bool, str, str | None]:
        """
        Create a new task using bd create.

        Args:
            title: Task title
            description: Task description
            priority: Priority (0-4)
            task_type: Task type (feature, task, bug)

        Returns:
            Tuple of (success, message, task_id)
        """
        try:
            cmd = [
                "bd", "create",
                f"--title={title}",
                f"--type={task_type}",
                f"--priority={priority}",
            ]
            if description:
                cmd.append(f"--description={description}")

            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=str(self.local_path),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return False, f"Create failed: {result.stderr}", None

            # Extract task ID from output (format: "Created beads-123")
            task_id = None
            for line in result.stdout.split("\n"):
                if "Created" in line or "beads-" in line:
                    import re
                    match = re.search(r"(beads-\d+)", line)
                    if match:
                        task_id = match.group(1)
                        break

            return True, "Task created", task_id

        except subprocess.TimeoutExpired:
            return False, "Create timed out", None
        except FileNotFoundError:
            return False, "beads CLI (bd) not found", None
        except Exception as e:
            return False, f"Create error: {e}", None

    async def update_task(
        self,
        task_id: str,
        status: str | None = None,
        priority: int | None = None,
        title: str | None = None,
    ) -> tuple[bool, str]:
        """
        Update an existing task.

        Args:
            task_id: Task ID (e.g., "beads-123")
            status: New status (open, in_progress, closed)
            priority: New priority (0-4)
            title: New title

        Returns:
            Tuple of (success, message)
        """
        try:
            cmd = ["bd", "update", task_id]

            if status:
                cmd.append(f"--status={status}")
            if priority is not None:
                cmd.append(f"--priority={priority}")
            if title:
                cmd.append(f"--title={title}")

            if len(cmd) == 3:  # No updates specified
                return False, "No updates specified"

            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=str(self.local_path),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return False, f"Update failed: {result.stderr}"

            return True, "Task updated"

        except subprocess.TimeoutExpired:
            return False, "Update timed out"
        except FileNotFoundError:
            return False, "beads CLI (bd) not found"
        except Exception as e:
            return False, f"Update error: {e}"

    async def delete_task(self, task_id: str) -> tuple[bool, str]:
        """
        Delete a task.

        Args:
            task_id: Task ID to delete

        Returns:
            Tuple of (success, message)
        """
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["bd", "delete", task_id, "--force"],
                cwd=str(self.local_path),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return False, f"Delete failed: {result.stderr}"

            return True, "Task deleted"

        except subprocess.TimeoutExpired:
            return False, "Delete timed out"
        except FileNotFoundError:
            return False, "beads CLI (bd) not found"
        except Exception as e:
            return False, f"Delete error: {e}"

    async def close_task(self, task_id: str, reason: str | None = None) -> tuple[bool, str]:
        """
        Close a task.

        Args:
            task_id: Task ID to close
            reason: Optional close reason

        Returns:
            Tuple of (success, message)
        """
        try:
            cmd = ["bd", "close", task_id]
            if reason:
                cmd.append(f"--reason={reason}")

            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=str(self.local_path),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return False, f"Close failed: {result.stderr}"

            return True, "Task closed"

        except subprocess.TimeoutExpired:
            return False, "Close timed out"
        except FileNotFoundError:
            return False, "beads CLI (bd) not found"
        except Exception as e:
            return False, f"Close error: {e}"

    async def reopen_task(self, task_id: str) -> tuple[bool, str]:
        """
        Reopen a closed task.

        Args:
            task_id: Task ID to reopen

        Returns:
            Tuple of (success, message)
        """
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                ["bd", "reopen", task_id],
                cwd=str(self.local_path),
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                return False, f"Reopen failed: {result.stderr}"

            return True, "Task reopened"

        except subprocess.TimeoutExpired:
            return False, "Reopen timed out"
        except FileNotFoundError:
            return False, "beads CLI (bd) not found"
        except Exception as e:
            return False, f"Reopen error: {e}"

    def get_tasks(self) -> list[dict]:
        """
        Read tasks from local .beads/issues.jsonl.

        Returns:
            List of task dictionaries
        """
        issues_file = self.local_path / ".beads" / "issues.jsonl"
        if not issues_file.exists():
            return []

        tasks = []
        try:
            with open(issues_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            tasks.append(json.loads(line))
                        except json.JSONDecodeError as e:
                            logger.warning(f"Skipped corrupt JSON in {self.project_name} issues.jsonl: {e}")
                            continue
        except Exception as e:
            logger.warning(f"Failed to read issues file for {self.project_name}: {e}")

        return tasks

    def get_stats(self) -> dict[str, Any]:
        """Get task statistics."""
        tasks = self.get_tasks()
        stats = {
            "open": 0,
            "in_progress": 0,
            "closed": 0,
            "total": len(tasks),
        }

        for task in tasks:
            status = task.get("status", "open")
            if status == "open":
                stats["open"] += 1
            elif status == "in_progress":
                stats["in_progress"] += 1
            elif status == "closed":
                stats["closed"] += 1

        if stats["total"] > 0:
            stats["percentage"] = round((stats["closed"] / stats["total"]) * 100, 1)
        else:
            stats["percentage"] = 0.0

        return stats


# Global registry of LocalProjectManager instances
_project_managers: dict[str, LocalProjectManager] = {}
_project_managers_lock = threading.Lock()


def get_local_project_manager(project_name: str, git_url: str) -> LocalProjectManager:
    """Get or create a LocalProjectManager for a project."""
    with _project_managers_lock:
        if project_name not in _project_managers:
            _project_managers[project_name] = LocalProjectManager(project_name, git_url)
        return _project_managers[project_name]


def clear_local_project_manager(project_name: str) -> None:
    """Clear cached LocalProjectManager for a project."""
    with _project_managers_lock:
        if project_name in _project_managers:
            del _project_managers[project_name]
