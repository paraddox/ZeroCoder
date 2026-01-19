"""
Local Project Manager
=====================

Manages local worktrees for projects used in:
- Spec creation wizard (new projects)
- Task editing (edit mode)

Uses git worktrees stored at ~/.zerocoder/worktrees/{name}/main/
Bare repos are stored at ~/.zerocoder/repos/{name}.git
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
    """Get the projects directory (DEPRECATED - use worktrees instead)."""
    from registry import get_projects_dir as registry_get_projects_dir
    return registry_get_projects_dir()


class LocalProjectManager:
    """Manages local worktree for wizard and edit mode."""

    def __init__(self, project_name: str, git_url: str):
        """
        Initialize the LocalProjectManager.

        Args:
            project_name: Name of the project
            git_url: Git remote URL (https:// or git@)
        """
        self.project_name = project_name
        self.git_url = git_url

        # Use WorktreeManager for worktree operations
        from server.services.worktree_manager import WorktreeManager
        self.worktree_manager = WorktreeManager(project_name, git_url)
        self.local_path = self.worktree_manager.get_worktree_path("main")

    def _get_default_branch(self) -> str:
        """Get the default branch name from remote."""
        try:
            # Try to get from remote HEAD
            result = subprocess.run(
                ["git", "-C", str(self.local_path), "symbolic-ref", "refs/remotes/origin/HEAD"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                ref = result.stdout.strip()
                return ref.split("/")[-1]
            # Try common default branch names
            for branch in ["main", "master", "develop"]:
                result = subprocess.run(
                    ["git", "-C", str(self.local_path), "rev-parse", "--verify", f"origin/{branch}"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    return branch
            # Last resort: get first remote branch
            result = subprocess.run(
                ["git", "-C", str(self.local_path), "branch", "-r", "--list", "origin/*"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                first_branch = result.stdout.strip().split("\n")[0].strip()
                if " -> " in first_branch:
                    first_branch = first_branch.split(" -> ")[1]
                return first_branch.replace("origin/", "")
            return "main"  # Ultimate fallback
        except Exception:
            return "main"  # Default fallback

    async def ensure_cloned(self) -> tuple[bool, str]:
        """
        Ensure the main worktree exists for the project.

        Uses git worktrees instead of full clone:
        1. Ensures bare repo exists (clones if needed)
        2. Creates main worktree if not exists

        Returns:
            Tuple of (success, message)
        """
        # Check if worktree already exists
        if self.local_path.exists() and (self.local_path / ".git").exists():
            return True, "Worktree already exists"

        try:
            # Create main worktree (this will also ensure bare repo exists)
            ok, worktree_path = await self.worktree_manager.create_worktree("main")

            if not ok:
                return False, f"Failed to create main worktree"

            logger.info(f"Created main worktree for {self.project_name} at {worktree_path}")
            return True, "Worktree created successfully"

        except Exception as e:
            logger.exception(f"Failed to create worktree for {self.project_name}")
            return False, f"Worktree creation error: {e}"

    async def pull_latest(self) -> tuple[bool, str]:
        """
        Sync the main worktree with remote.

        Returns:
            Tuple of (success, message)
        """
        if not self.local_path.exists():
            return await self.ensure_cloned()

        try:
            # Use worktree manager to sync the main worktree
            ok, msg = await self.worktree_manager.sync_worktree("main")
            if not ok:
                return False, f"Sync failed: {msg}"
            return True, "Synced successfully"

        except Exception as e:
            logger.warning(f"Failed to sync worktree for {self.project_name}: {e}")
            return False, f"Sync error: {e}"

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
        Read tasks using bd CLI from local project directory.

        Uses bd list --json to query the SQLite database directly,
        providing the authoritative source of truth.

        Returns:
            List of task dictionaries
        """
        if not self.local_path.exists():
            return []

        # Check if .beads directory exists
        beads_dir = self.local_path / ".beads"
        if not beads_dir.exists():
            return []

        try:
            result = subprocess.run(
                ["bd", "--no-daemon", "list", "--json", "--all", "--limit", "0"],
                cwd=self.local_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.debug(f"bd list failed for {self.project_name}: {result.stderr}")
                return []

            stdout = result.stdout.strip()
            if not stdout:
                return []

            return json.loads(stdout)
        except subprocess.TimeoutExpired:
            logger.warning(f"bd list timed out for {self.project_name}")
            return []
        except FileNotFoundError:
            logger.debug("bd CLI not found")
            return []
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse bd list output for {self.project_name}: {e}")
            return []
        except Exception as e:
            logger.warning(f"Failed to get tasks for {self.project_name}: {e}")
            return []

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
