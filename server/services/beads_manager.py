"""
Beads Manager
=============

Unified manager for all beads operations, combining:
- BeadsSyncManager: Git operations and local JSONL parsing
- BeadsAPI: bd CLI commands for write operations

Key design decisions:
- Single asyncio.Lock per project for all operations (read/write/sync)
- Reads from local JSONL are fast and don't require lock (atomic file reads)
- Writes go through bd CLI, acquire lock, and sync after
- Pull operations acquire lock to prevent conflicts with writes

This replaces both beads_sync_manager.py and the core logic in beads_api.py.
"""

import asyncio
import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_beads_sync_dir() -> Path:
    """Get the beads-sync directory for beads-sync branch clones."""
    _root = Path(__file__).parent.parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    from registry import get_beads_sync_dir as registry_get_beads_sync_dir
    return registry_get_beads_sync_dir()


class BeadsManager:
    """
    Unified manager for all beads operations on a single project.

    Handles:
    - Git operations (clone beads-sync branch, pull latest)
    - Read operations (fast local JSONL parsing)
    - Write operations (bd CLI commands with locking)
    - Sync operations (push changes to remote)
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
        self.local_path = get_beads_sync_dir() / project_name
        self._lock = asyncio.Lock()  # Single lock for all operations
        self._last_pull: datetime | None = None

    # =========================================================================
    # Git Operations (from BeadsSyncManager)
    # =========================================================================

    async def ensure_cloned(self) -> tuple[bool, str]:
        """
        Clone beads-sync branch if not already cloned.

        Returns:
            Tuple of (success, message)
        """
        if self.local_path.exists() and (self.local_path / ".git").exists():
            return True, "Already cloned"

        async with self._lock:
            # Double-check after acquiring lock
            if self.local_path.exists() and (self.local_path / ".git").exists():
                return True, "Already cloned"

            try:
                self.local_path.parent.mkdir(parents=True, exist_ok=True)

                # Clone only beads-sync branch (sparse)
                result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "git", "clone",
                        "--single-branch", "--branch", "beads-sync",
                        "--depth", "1",
                        self.git_remote_url,
                        str(self.local_path)
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,  # 2 minute timeout for clone
                )

                if result.returncode != 0:
                    # beads-sync branch may not exist yet
                    if "not found" in result.stderr.lower() or "does not exist" in result.stderr.lower():
                        logger.info(f"beads-sync branch not found for {self.project_name}, will create on first sync")
                        return False, "beads-sync branch does not exist yet"
                    return False, f"Clone failed: {result.stderr}"

                logger.info(f"Cloned beads-sync branch for {self.project_name}")
                return True, "Cloned successfully"

            except subprocess.TimeoutExpired:
                return False, "Clone timed out"
            except Exception as e:
                logger.exception(f"Failed to clone beads-sync for {self.project_name}")
                return False, f"Clone error: {e}"

    async def pull_latest(self) -> tuple[bool, str]:
        """
        Pull latest beads state from remote.

        Acquires lock to prevent conflicts with write operations.

        Returns:
            Tuple of (success, message)
        """
        if not self.local_path.exists():
            return await self.ensure_cloned()

        async with self._lock:
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "-C", str(self.local_path), "pull", "--ff-only", "origin", "beads-sync"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    self._last_pull = datetime.now()
                    return True, "Pulled successfully"

                # Pull failed - try fetch + reset as fallback
                logger.warning(f"Git pull failed for {self.project_name}: {result.stderr}, trying fetch+reset")

                fetch_result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "-C", str(self.local_path), "fetch", "origin", "beads-sync"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if fetch_result.returncode != 0:
                    logger.error(f"Git fetch failed for {self.project_name}: {fetch_result.stderr}")
                    return False, f"Fetch failed: {fetch_result.stderr}"

                reset_result = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "-C", str(self.local_path), "reset", "--hard", "origin/beads-sync"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if reset_result.returncode != 0:
                    logger.error(f"Git reset failed for {self.project_name}: {reset_result.stderr}")
                    return False, f"Reset failed: {reset_result.stderr}"

                # Fallback succeeded
                self._last_pull = datetime.now()
                return True, "Pulled via fetch+reset"

            except subprocess.TimeoutExpired:
                return False, "Pull timed out"
            except Exception as e:
                logger.warning(f"Failed to pull beads-sync for {self.project_name}: {e}")
                return False, f"Pull error: {e}"

    # =========================================================================
    # Read Operations - Fast Local Access (from BeadsSyncManager)
    # No lock needed - atomic file reads
    # =========================================================================

    def get_tasks(self) -> list[dict]:
        """
        Read tasks directly from local .beads/issues.jsonl.

        This is a fast local read that doesn't require locking.

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

    async def _run_bd(self, args: list[str], timeout: int = 60) -> dict[str, Any]:
        """
        Low-level bd command runner.

        Args:
            args: Command arguments (e.g., ["list", "--json"])
            timeout: Command timeout in seconds

        Returns:
            Parsed JSON output or error dict
        """
        try:
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

    async def _sync_with_remote(self) -> bool:
        """
        Run bd sync to synchronize with git remote.

        This is best-effort - failures are logged but don't cause errors.
        Called internally after write operations.

        Returns:
            True if sync succeeded, False otherwise
        """
        result = await self._run_bd(["sync"], timeout=30)
        if "error" in result:
            logger.warning(f"bd sync failed (best-effort): {result['error']}")
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
        Run a read command with sync before.

        Syncs with remote BEFORE running the command to get latest state.

        Args:
            args: Command arguments (e.g., ["list", "--json"])

        Returns:
            Parsed JSON output or error dict
        """
        if not self.local_path.exists():
            return {"error": f"Beads sync directory not found: {self.local_path}"}

        async with self._lock:
            # Sync before read to get latest state from remote
            await self._sync_with_remote()
            # Run the actual command
            return await self._run_bd(args)

    async def run_write_command(self, args: list[str]) -> dict[str, Any]:
        """
        Run a write command with project-level locking.

        Write operations (create, update, close, reopen) are serialized
        per-project to avoid race conditions. Syncs AFTER the write to push changes.

        Args:
            args: Command arguments (e.g., ["create", "--title", "...", "--json"])

        Returns:
            Parsed JSON output or error dict
        """
        if not self.local_path.exists():
            return {"error": f"Beads sync directory not found: {self.local_path}"}

        async with self._lock:
            # Run the write command
            result = await self._run_bd(args)

            # Sync after write to push changes to remote
            if "error" not in result:
                await self._sync_with_remote()

            return result

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
    Get cached stats for a project from beads-sync.

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
    Get cached features for a project from beads-sync.

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
    Clone beads-sync branches for all registered projects on server startup.

    This ensures we have local copies of beads data for all projects
    before the polling loop starts.

    Returns:
        Dict mapping project name to success status
    """
    _root = Path(__file__).parent.parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    from registry import list_valid_projects, get_project_git_url

    results = {}
    projects = list_valid_projects()
    logger.info(f"Initializing beads-sync for {len(projects)} registered projects")

    for project in projects:
        project_name = project["name"]
        git_url = get_project_git_url(project_name)
        if git_url:
            manager = await get_beads_manager(project_name, git_url)
            success, message = await manager.ensure_cloned()
            results[project_name] = success
            if success:
                logger.debug(f"Beads-sync initialized for {project_name}: {message}")
            else:
                logger.info(f"Beads-sync init for {project_name}: {message}")
        else:
            logger.debug(f"Skipping {project_name}: no git URL")

    successes = sum(1 for v in results.values() if v)
    logger.info(f"Beads-sync initialization complete: {successes}/{len(results)} successful")
    return results


async def pull_all_beads_sync() -> dict[str, bool]:
    """
    Pull latest for projects with active containers only.

    Returns:
        Dict mapping project name to success status
    """
    from .container_manager import get_projects_with_active_containers

    active_projects = get_projects_with_active_containers()
    if not active_projects:
        return {}

    results = {}
    for project_name in active_projects:
        manager = get_beads_manager_sync(project_name)
        if manager:
            success, _ = await manager.pull_latest()
            results[project_name] = success

    return results


# Background polling task
POLL_INTERVAL_IDLE = 15  # seconds when no containers running
POLL_INTERVAL_ACTIVE = 5  # seconds when containers are running


def _has_running_containers() -> bool:
    """Check if any containers are running."""
    try:
        from server.services.container_manager import get_all_managers
        managers = get_all_managers()
        return any(m.status == "running" for m in managers.values())
    except Exception:
        return False


async def start_beads_sync_poller() -> None:
    """
    Start a background task that polls beads-sync for all projects.

    Uses dynamic polling interval:
    - 5 seconds when containers are running (for faster UI updates)
    - 15 seconds when idle (to reduce resource usage)

    This should be called when the server starts.
    """
    logger.info(f"Starting beads-sync poller (idle: {POLL_INTERVAL_IDLE}s, active: {POLL_INTERVAL_ACTIVE}s)")

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
