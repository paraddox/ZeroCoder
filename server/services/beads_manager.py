"""
Beads Manager
=============

Unified manager for all beads operations. Reads directly from the project
directory's SQLite database via the `bd` CLI.

Key design decisions:
- Single asyncio.Lock per project for all operations (read/write/sync)
- Reads use `bd list --json` for authoritative SQLite database access
- Writes go through bd CLI, acquire lock, and sync after
- Uses project directory directly (~/.zerocoder/projects/{name}/)
"""

import asyncio
import fcntl
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_projects_dir() -> Path:
    """Get the projects directory for local clones."""
    _root = Path(__file__).parent.parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    from registry import get_projects_dir as registry_get_projects_dir
    return registry_get_projects_dir()


class BeadsManager:
    """
    Unified manager for all beads operations on a single project.

    Handles:
    - Read operations (via bd CLI from project directory)
    - Write operations (bd CLI commands with locking)
    - Sync operations (push changes to remote)

    Uses the project directory directly (~/.zerocoder/projects/{name}/).
    """

    def __init__(self, project_name: str, git_remote_url: str):
        """
        Initialize the BeadsManager.

        Args:
            project_name: Name of the project
            git_remote_url: Git remote URL (https:// or git@)
        """
        self.project_name = project_name
        self.git_remote_url = git_remote_url
        # Use project directory directly
        self.local_path = get_projects_dir() / project_name
        self._lock = asyncio.Lock()  # Single lock for all operations
        self._last_pull: datetime | None = None
        self._file_lock_fd: int | None = None

    # =========================================================================
    # File-Based Locking for Cross-Process Coordination
    # =========================================================================

    def _get_lock_path(self) -> Path:
        """Get the path to the file lock."""
        return self.local_path / ".beads" / ".sync.lock"

    def _acquire_file_lock(self) -> int:
        """
        Acquire file lock for cross-process coordination.

        Uses fcntl.flock for POSIX-compliant file locking.
        This prevents both host and container from running bd commands simultaneously.

        Returns:
            File descriptor for the lock file
        """
        lock_path = self._get_lock_path()
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def _release_file_lock(self, fd: int) -> None:
        """
        Release file lock.

        Args:
            fd: File descriptor returned by _acquire_file_lock
        """
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        except Exception as e:
            logger.warning(f"Error releasing file lock: {e}")

    # =========================================================================
    # Project Directory Operations
    # =========================================================================

    async def ensure_project_exists(self) -> tuple[bool, str]:
        """
        Check if the project directory exists.

        LocalProjectManager handles cloning, so we just verify the path exists.

        Returns:
            Tuple of (success, message)
        """
        if self.local_path.exists() and (self.local_path / ".git").exists():
            return True, "Project exists"

        return False, f"Project directory not found: {self.local_path}"

    # Backwards compatibility alias
    async def ensure_cloned(self) -> tuple[bool, str]:
        """Deprecated: Use ensure_project_exists() instead."""
        return await self.ensure_project_exists()

    async def pull_latest(self) -> tuple[bool, str]:
        """
        Pull latest from remote main branch.

        Returns:
            Tuple of (success, message)
        """
        if not self.local_path.exists():
            return False, "Project directory does not exist"

        async with self._lock:
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "-C", str(self.local_path), "pull", "--ff-only"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    self._last_pull = datetime.now()
                    return True, "Pulled successfully"

                # Pull failed - log but don't error (project may have local changes)
                logger.debug(f"Git pull skipped for {self.project_name}: {result.stderr}")
                return True, "Pull skipped (local changes or up-to-date)"

            except subprocess.TimeoutExpired:
                return False, "Pull timed out"
            except Exception as e:
                logger.warning(f"Failed to pull for {self.project_name}: {e}")
                return False, f"Pull error: {e}"

    # =========================================================================
    # Read Operations - Via bd CLI (queries SQLite database)
    # =========================================================================

    def get_tasks(self) -> list[dict]:
        """
        Read tasks using bd CLI from local project directory.

        This queries the SQLite database directly via bd list --json,
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
        """
        Calculate stats from local tasks.

        Returns:
            Dict with open, in_progress, closed, total counts
        """
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

    def get_features(self) -> list[dict]:
        """
        Get features in UI-compatible format.

        Returns:
            List of feature dicts with id, priority, category, name, description, steps, passes, in_progress
        """
        return _tasks_to_features(self.get_tasks())

    def get_tasks_by_status(self, status: str) -> list[dict]:
        """Get tasks filtered by status."""
        return [t for t in self.get_tasks() if t.get("status") == status]

    # =========================================================================
    # Write Operations - via bd CLI (from BeadsAPI)
    # Acquires lock and syncs after
    # =========================================================================

    async def _run_bd(self, args: list[str], timeout: int = 60, use_file_lock: bool = True) -> dict[str, Any]:
        """
        Low-level bd command runner with cross-process file locking.

        Args:
            args: Command arguments (e.g., ["list", "--json"])
            timeout: Command timeout in seconds
            use_file_lock: Whether to acquire file lock (default True)

        Returns:
            Parsed JSON output or error dict
        """
        fd = None
        try:
            # Acquire file lock for cross-process coordination
            if use_file_lock:
                fd = await asyncio.to_thread(self._acquire_file_lock)

            result = await asyncio.to_thread(
                subprocess.run,
                ["bd", "--no-daemon", *args],
                cwd=self.local_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else f"Command failed with exit code {result.returncode}"
                # Don't log warning for "another sync in progress" - it's expected behavior
                if "another sync is in progress" not in error_msg.lower():
                    logger.warning(f"bd command failed: bd {' '.join(args)} - {error_msg}")
                return {"error": error_msg}

            # Try to parse JSON output
            stdout = result.stdout.strip()
            if not stdout:
                return {"success": True, "data": []}

            try:
                return {"success": True, "data": json.loads(stdout)}
            except json.JSONDecodeError:
                # Some commands return plain text
                return {"success": True, "output": stdout}

        except subprocess.TimeoutExpired:
            return {"error": "Command timed out"}
        except FileNotFoundError:
            return {"error": "bd command not found. Is beads installed?"}
        except Exception as e:
            logger.exception(f"Error running beads command: {e}")
            return {"error": str(e)}
        finally:
            # Always release the file lock
            if fd is not None:
                await asyncio.to_thread(self._release_file_lock, fd)

    async def _sync_with_remote(self) -> bool:
        """
        Run bd sync to synchronize with git remote.

        This is best-effort - failures are logged but don't cause errors.
        Called internally after write operations.

        Returns:
            True if sync succeeded or already in progress, False on real errors
        """
        result = await self._run_bd(["sync"], timeout=30)
        if "error" in result:
            error_msg = result["error"]
            # "another sync is in progress" is not an error - just means we're already syncing
            if "another sync is in progress" in error_msg.lower():
                logger.debug(f"bd sync skipped for {self.project_name}: already in progress")
                return True  # Consider this success - sync is happening
            logger.warning(f"bd sync failed (best-effort): {error_msg}")
            return False
        logger.debug(f"bd sync completed for {self.project_name}")
        return True

    async def sync(self) -> tuple[bool, str]:
        """
        Sync beads with git remote.

        Acquires lock to prevent conflicts.

        Returns:
            Tuple of (success, message)
        """
        async with self._lock:
            success = await self._sync_with_remote()
            if success:
                return True, "Synced successfully"
            return False, "Sync failed"

    async def run_read_command(self, args: list[str]) -> dict[str, Any]:
        """
        Run a read command (no sync).

        Reads from local beads database. Background poller handles remote sync.

        Args:
            args: Command arguments (e.g., ["list", "--json"])

        Returns:
            Parsed JSON output or error dict
        """
        if not self.local_path.exists():
            return {"error": f"Project directory not found: {self.local_path}"}

        async with self._lock:
            # Read from local database (background poller handles sync)
            return await self._run_bd(args)

    async def run_write_command(self, args: list[str], skip_lock: bool = False) -> dict[str, Any]:
        """
        Run a write command with project-level locking.

        Write operations (create, update, close, reopen) are serialized
        per-project to avoid race conditions. Syncs AFTER the write to push changes.

        Args:
            args: Command arguments (e.g., ["create", "--title", "...", "--json"])
            skip_lock: If True, skip acquiring the lock (caller already holds it)

        Returns:
            Parsed JSON output or error dict
        """
        if not self.local_path.exists():
            return {"error": f"Project directory not found: {self.local_path}"}

        async def _do_write():
            # Run the write command
            result = await self._run_bd(args)

            # Sync after write to push changes to remote
            if "error" not in result:
                await self._sync_with_remote()

            return result

        if skip_lock:
            return await _do_write()
        else:
            async with self._lock:
                return await _do_write()

    # =========================================================================
    # High-level Write Operations
    # =========================================================================

    async def create_issue(
        self,
        title: str,
        type: str = "task",
        priority: int = 2,
        description: str = "",
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Create a new issue.

        Args:
            title: Issue title
            type: Issue type (task, bug, feature, epic)
            priority: Priority 0-4 (0=critical, 4=backlog)
            description: Optional description
            labels: Optional list of labels

        Returns:
            Result dict with success or error
        """
        args = [
            "create",
            "--title", title,
            "--type", type,
            "--priority", f"P{priority}",
            "--json",
        ]

        if description:
            args.extend(["--description", description])

        if labels:
            args.extend(["--labels", ",".join(labels)])

        return await self.run_write_command(args)

    async def update_issue(
        self,
        issue_id: str,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: int | None = None,
        assignee: str | None = None,
    ) -> dict[str, Any]:
        """
        Update an issue's fields.

        Args:
            issue_id: Issue ID to update
            title: New title (optional)
            description: New description (optional)
            status: New status - open, in_progress, closed (optional)
            priority: New priority 0-4 (optional)
            assignee: New assignee (optional)

        Returns:
            Result dict with success or error
        """
        args = ["update", issue_id]

        if title is not None:
            args.extend(["--title", title])
        if description is not None:
            args.extend(["--description", description])
        if status is not None:
            args.extend(["--status", status])
        if priority is not None:
            args.extend(["--priority", f"P{priority}"])
        if assignee is not None:
            args.extend(["--assignee", assignee])

        # Must have at least one update
        if len(args) == 2:
            return {"error": "No update fields provided"}

        return await self.run_write_command(args)

    async def close_issue(self, issue_id: str, reason: str | None = None) -> dict[str, Any]:
        """
        Close an issue.

        Args:
            issue_id: Issue ID to close
            reason: Optional close reason

        Returns:
            Result dict with success or error
        """
        args = ["close", issue_id]
        if reason:
            args.extend(["--reason", reason])

        return await self.run_write_command(args)

    async def reopen_issue(self, issue_id: str) -> dict[str, Any]:
        """
        Reopen a closed issue.

        Args:
            issue_id: Issue ID to reopen

        Returns:
            Result dict with success or error
        """
        return await self.run_write_command(["reopen", issue_id])

    async def add_dependency(self, issue_id: str, depends_on: str) -> dict[str, Any]:
        """
        Add a dependency between issues.

        Args:
            issue_id: The issue that depends on another
            depends_on: The issue that must be completed first

        Returns:
            Result dict with success or error
        """
        return await self.run_write_command(["dep", "add", issue_id, depends_on])

    async def add_comment(self, issue_id: str, comment: str) -> dict[str, Any]:
        """
        Add a comment to an issue.

        Args:
            issue_id: Issue ID
            comment: Comment text

        Returns:
            Result dict with success or error
        """
        return await self.run_write_command(["comments", issue_id, "--add", comment])

    async def delete_issue(self, issue_id: str) -> dict[str, Any]:
        """
        Delete an issue.

        Args:
            issue_id: Issue ID to delete

        Returns:
            Result dict with success or error
        """
        return await self.run_write_command(["delete", issue_id, "--force"])

    # =========================================================================
    # Feature-Level Operations (for UI compatibility)
    # =========================================================================

    def get_feature(self, feature_id: str) -> dict | None:
        """
        Get a single feature by ID.

        Args:
            feature_id: Feature/issue ID

        Returns:
            Feature dict in UI format, or None if not found
        """
        tasks = self.get_tasks()
        for task in tasks:
            if str(task.get("id")) == str(feature_id):
                return _task_to_feature(task)
        return None

    async def create_feature(
        self,
        name: str,
        category: str = "",
        description: str = "",
        steps: list[str] | None = None,
        priority: int = 999,
    ) -> dict | None:
        """
        Create a new feature.

        Args:
            name: Feature name/title
            category: Category label
            description: Feature description
            steps: Implementation steps
            priority: Priority (0-4)

        Returns:
            Created feature dict in UI format, or None on failure
        """
        # Build full description with steps if provided
        full_description = description
        if steps:
            step_text = "\n".join(f"{i+1}. {step}" for i, step in enumerate(steps))
            if description:
                full_description = f"{description}\n\n{step_text}"
            else:
                full_description = step_text

        labels = [category] if category else None

        result = await self.create_issue(
            title=name,
            type="feature",
            priority=priority,
            description=full_description,
            labels=labels,
        )

        if "error" in result:
            logger.warning(f"Failed to create feature: {result['error']}")
            return None

        # Extract created issue ID from result
        data = result.get("data", {})
        if isinstance(data, dict):
            issue_id = data.get("id")
            if issue_id:
                return self.get_feature(issue_id)

        # Fallback: get the most recently created feature with this name
        tasks = self.get_tasks()
        for task in tasks:
            if task.get("title") == name:
                return _task_to_feature(task)

        return None

    async def update_feature(
        self,
        feature_id: str,
        name: str | None = None,
        description: str | None = None,
        priority: int | None = None,
        category: str | None = None,
        steps: list[str] | None = None,
    ) -> dict | None:
        """
        Update a feature's fields.

        Args:
            feature_id: Feature/issue ID
            name: New name/title
            description: New description
            priority: New priority (0-4)
            category: New category label
            steps: New implementation steps

        Returns:
            Updated feature dict in UI format, or None on failure
        """
        # Get current feature to merge with updates
        current = self.get_feature(feature_id)
        if not current:
            return None

        # Build full description with steps if provided
        final_description = description
        if steps is not None:
            step_text = "\n".join(f"{i+1}. {step}" for i, step in enumerate(steps))
            base_desc = description if description is not None else ""
            if base_desc:
                final_description = f"{base_desc}\n\n{step_text}"
            else:
                final_description = step_text

        # Update via beads CLI
        result = await self.update_issue(
            issue_id=feature_id,
            title=name,
            description=final_description,
            priority=priority,
        )

        if "error" in result:
            logger.warning(f"Failed to update feature: {result['error']}")
            return None

        # Handle category/label update separately if needed
        if category is not None:
            # Use bd label command to update labels
            await self.run_write_command(["label", feature_id, "--set", category])

        return self.get_feature(feature_id)

    async def delete_feature(self, feature_id: str) -> bool:
        """
        Delete a feature.

        Args:
            feature_id: Feature/issue ID

        Returns:
            True if deleted successfully
        """
        result = await self.delete_issue(feature_id)
        return "error" not in result

    async def skip_feature(self, feature_id: str) -> dict | None:
        """
        Skip a feature by setting its priority to P4 (backlog).

        Args:
            feature_id: Feature/issue ID

        Returns:
            Dict with success info, or None on failure
        """
        # Verify feature exists
        feature = self.get_feature(feature_id)
        if not feature:
            return None

        result = await self.update_issue(issue_id=feature_id, priority=4)
        if "error" in result:
            return {"error": result["error"]}

        return {"success": True, "message": f"Feature {feature_id} moved to backlog"}

    async def reopen_feature(self, feature_id: str) -> dict | None:
        """
        Reopen a closed feature.

        Args:
            feature_id: Feature/issue ID

        Returns:
            Reopened feature dict in UI format, or None on failure
        """
        result = await self.reopen_issue(feature_id)
        if "error" in result:
            return None

        return self.get_feature(feature_id)


def _task_to_feature(task: dict) -> dict:
    """Convert a single beads task to feature format for UI compatibility."""
    # Extract category from labels (first label)
    labels = task.get("labels", [])
    category = labels[0] if labels else ""

    # Parse steps from description if available (beads uses 'description' not 'body')
    description = task.get("description", "") or task.get("body", "")
    steps = []
    if description:
        step_matches = re.findall(r'^\d+\.\s*(.+)$', description, re.MULTILINE)
        if step_matches:
            steps = step_matches

    status = task.get("status", "open")

    return {
        "id": task.get("id", ""),
        "priority": task.get("priority", 999),
        "category": category,
        "name": task.get("title", ""),
        "description": description,
        "steps": steps,
        "passes": status == "closed",
        "in_progress": status == "in_progress",
    }


# =============================================================================
# Global Manager Registry
# =============================================================================

_managers: dict[str, BeadsManager] = {}
_managers_lock = asyncio.Lock()


async def get_beads_manager(project_name: str, git_url: str | None = None) -> BeadsManager:
    """
    Get or create a BeadsManager for a project.

    Args:
        project_name: Name of the project
        git_url: Git remote URL (required for first access)

    Returns:
        BeadsManager instance

    Raises:
        ValueError: If git_url not provided and manager doesn't exist
    """
    async with _managers_lock:
        if project_name not in _managers:
            if not git_url:
                # Try to get git_url from registry
                _root = Path(__file__).parent.parent.parent
                if str(_root) not in sys.path:
                    sys.path.insert(0, str(_root))
                from registry import get_project_git_url
                git_url = get_project_git_url(project_name)

            if not git_url:
                raise ValueError(f"No git URL available for project {project_name}")

            _managers[project_name] = BeadsManager(project_name, git_url)
        return _managers[project_name]


def get_beads_manager_sync(project_name: str) -> BeadsManager | None:
    """
    Get an existing BeadsManager for a project (synchronous, no creation).

    This is for use in synchronous contexts that need to read cached data.
    Returns None if the manager doesn't exist yet.

    Args:
        project_name: Name of the project

    Returns:
        BeadsManager instance or None
    """
    return _managers.get(project_name)


def clear_beads_manager(project_name: str) -> None:
    """
    Clear cached BeadsManager for a project.

    Args:
        project_name: Name of the project to clear
    """
    if project_name in _managers:
        del _managers[project_name]


# =============================================================================
# Convenience Functions (API-compatible with BeadsSyncManager)
# =============================================================================

def get_cached_stats(project_name: str) -> dict:
    """
    Get stats for a project from the local project directory.

    This is a convenience function for use by progress.py and other modules
    that don't have the git_url handy.

    Returns:
        Dict with pending, in_progress, done, total, percentage
    """
    manager = get_beads_manager_sync(project_name)
    if manager:
        stats = manager.get_stats()
        # Map to feature_poller-compatible format
        return {
            "pending": stats.get("open", 0),
            "in_progress": stats.get("in_progress", 0),
            "done": stats.get("closed", 0),
            "total": stats.get("total", 0),
            "percentage": stats.get("percentage", 0.0),
        }

    # Manager not found - try to create one from registry
    try:
        _root = Path(__file__).parent.parent.parent
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))

        from registry import get_project_git_url
        git_url = get_project_git_url(project_name)
        if git_url:
            # Create manager synchronously (can't await in sync context)
            if project_name not in _managers:
                _managers[project_name] = BeadsManager(project_name, git_url)
            manager = _managers[project_name]
            stats = manager.get_stats()
            return {
                "pending": stats.get("open", 0),
                "in_progress": stats.get("in_progress", 0),
                "done": stats.get("closed", 0),
                "total": stats.get("total", 0),
                "percentage": stats.get("percentage", 0.0),
            }
    except Exception as e:
        logger.debug(f"Failed to get stats for {project_name}: {e}")

    return {"pending": 0, "in_progress": 0, "done": 0, "total": 0, "percentage": 0.0}


def get_cached_features(project_name: str) -> list[dict]:
    """
    Get features for a project from the local project directory.

    This is a convenience function for use by progress.py and other modules.
    Returns features in the format expected by the UI (compatible with feature_poller).

    Returns:
        List of feature dicts with id, priority, category, name, description, steps, passes, in_progress
    """
    manager = get_beads_manager_sync(project_name)
    if manager:
        return manager.get_features()

    # Manager not found - try to create one from registry
    try:
        _root = Path(__file__).parent.parent.parent
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))

        from registry import get_project_git_url
        git_url = get_project_git_url(project_name)
        if git_url:
            # Create manager synchronously
            if project_name not in _managers:
                _managers[project_name] = BeadsManager(project_name, git_url)
            return _managers[project_name].get_features()
    except Exception as e:
        logger.debug(f"Failed to get features for {project_name}: {e}")

    return []


def _tasks_to_features(tasks: list[dict]) -> list[dict]:
    """Convert beads tasks to feature format for UI compatibility."""
    features = []
    for task in tasks:
        # Extract category from labels (first label)
        labels = task.get("labels", [])
        category = labels[0] if labels else ""

        # Parse steps from description if available (beads uses 'description' not 'body')
        description = task.get("description", "") or task.get("body", "")
        steps = []
        if description:
            step_matches = re.findall(r'^\d+\.\s*(.+)$', description, re.MULTILINE)
            if step_matches:
                steps = step_matches

        status = task.get("status", "open")

        features.append({
            "id": task.get("id", ""),
            "priority": task.get("priority", 999),
            "category": category,
            "name": task.get("title", ""),
            "description": description,
            "steps": steps,
            "passes": status == "closed",
            "in_progress": status == "in_progress",
        })

    return features


# =============================================================================
# Initialization and Background Polling
# =============================================================================

async def initialize_all_projects() -> dict[str, bool]:
    """
    Initialize BeadsManagers for all registered projects on server startup.

    This creates manager instances for all projects that have local clones.
    LocalProjectManager handles actual cloning - we just verify paths exist.

    Returns:
        Dict mapping project name to success status
    """
    _root = Path(__file__).parent.parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    from registry import list_valid_projects, get_project_git_url

    results = {}
    projects = list_valid_projects()
    logger.info(f"Initializing beads managers for {len(projects)} registered projects")

    for project in projects:
        project_name = project["name"]
        git_url = get_project_git_url(project_name)
        if git_url:
            manager = await get_beads_manager(project_name, git_url)
            success, message = await manager.ensure_project_exists()
            results[project_name] = success
            if success:
                logger.debug(f"Beads manager initialized for {project_name}: {message}")
            else:
                logger.info(f"Beads manager init for {project_name}: {message}")
        else:
            logger.debug(f"Skipping {project_name}: no git URL")

    successes = sum(1 for v in results.values() if v)
    logger.info(f"Beads manager initialization complete: {successes}/{len(results)} successful")
    return results


async def pull_all_beads_sync() -> dict[str, bool]:
    """
    Sync beads for projects with active containers.

    This is now a lightweight operation since we read directly from
    the project directory's SQLite database.

    Returns:
        Dict mapping project name to success status
    """
    from .e2b_sandbox_manager import get_projects_with_active_containers

    active_projects = get_projects_with_active_containers()
    if not active_projects:
        return {}

    results = {}
    for project_name in active_projects:
        manager = get_beads_manager_sync(project_name)
        if manager:
            # Just run bd sync to push any local changes
            success = await manager._sync_with_remote()
            results[project_name] = success

    return results


# Background polling task
POLL_INTERVAL_IDLE = 30  # seconds when no containers running (increased since no git pull needed)
POLL_INTERVAL_ACTIVE = 10  # seconds when containers are running


def _has_running_containers() -> bool:
    """Check if any containers are running."""
    try:
        from server.services.e2b_sandbox_manager import get_projects_with_active_containers
        active_projects = get_projects_with_active_containers()
        return len(active_projects) > 0
    except Exception:
        return False


async def start_beads_sync_poller() -> None:
    """
    Start a background task that syncs beads for active projects.

    Since we now read directly from the project directory, this is mainly
    for pushing local changes to remote (bd sync).

    Uses dynamic polling interval:
    - 10 seconds when containers are running (for faster sync)
    - 30 seconds when idle (to reduce resource usage)

    This should be called when the server starts.
    """
    logger.info(f"Starting beads sync poller (idle: {POLL_INTERVAL_IDLE}s, active: {POLL_INTERVAL_ACTIVE}s)")

    while True:
        try:
            # Use faster polling when containers are running
            interval = POLL_INTERVAL_ACTIVE if _has_running_containers() else POLL_INTERVAL_IDLE
            await asyncio.sleep(interval)
            results = await pull_all_beads_sync()
            if results:
                successes = sum(1 for v in results.values() if v)
                logger.debug(f"Beads sync poll: {successes}/{len(results)} successful (interval: {interval}s)")
        except asyncio.CancelledError:
            logger.info("Beads sync poller stopped")
            break
        except Exception as e:
            logger.exception(f"Error in beads sync poller: {e}")


# =============================================================================
# Backwards Compatibility Aliases
# =============================================================================

# These maintain compatibility with code that imports from beads_sync_manager
def get_beads_sync_manager(project_name: str, git_remote_url: str) -> BeadsManager:
    """
    Backwards compatibility: Get a BeadsManager.

    This is a synchronous wrapper that creates the manager if needed.
    Use get_beads_manager() for async contexts.
    """
    if project_name not in _managers:
        _managers[project_name] = BeadsManager(project_name, git_remote_url)
    return _managers[project_name]
