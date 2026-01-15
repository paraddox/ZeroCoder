"""
Beads Sync Manager
==================

Manages local clones of beads-sync branches for all projects.
Reads task state directly from the local .beads/issues.jsonl file.

This replaces the feature_poller.py approach of querying containers via docker exec.
"""

import asyncio
import json
import logging
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def get_beads_sync_dir() -> Path:
    """Get the beads-sync directory for beads-sync branch clones."""
    from registry import get_beads_sync_dir as registry_get_beads_sync_dir
    return registry_get_beads_sync_dir()


class BeadsSyncManager:
    """Manages local clone of beads-sync branch for a single project."""

    def __init__(self, project_name: str, git_remote_url: str):
        """
        Initialize the BeadsSyncManager.

        Args:
            project_name: Name of the project
            git_remote_url: Git remote URL (https:// or git@)
        """
        self.project_name = project_name
        self.git_remote_url = git_remote_url
        self.local_path = get_beads_sync_dir() / project_name
        self._last_pull: datetime | None = None

    async def ensure_cloned(self) -> tuple[bool, str]:
        """
        Clone beads-sync branch if not already cloned.

        Returns:
            Tuple of (success, message)
        """
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

        Returns:
            Tuple of (success, message)
        """
        if not self.local_path.exists():
            return await self.ensure_cloned()

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

    def get_tasks(self) -> list[dict]:
        """
        Read tasks directly from local .beads/issues.jsonl.

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

    def get_tasks_by_status(self, status: str) -> list[dict]:
        """Get tasks filtered by status."""
        return [t for t in self.get_tasks() if t.get("status") == status]


# Global registry of BeadsSyncManager instances
_sync_managers: dict[str, BeadsSyncManager] = {}
_sync_managers_lock = threading.Lock()


def get_beads_sync_manager(project_name: str, git_remote_url: str) -> BeadsSyncManager:
    """Get or create a BeadsSyncManager for a project."""
    with _sync_managers_lock:
        if project_name not in _sync_managers:
            _sync_managers[project_name] = BeadsSyncManager(project_name, git_remote_url)
        return _sync_managers[project_name]


def clear_beads_sync_manager(project_name: str) -> None:
    """Clear cached BeadsSyncManager for a project."""
    with _sync_managers_lock:
        if project_name in _sync_managers:
            del _sync_managers[project_name]


def get_cached_stats(project_name: str) -> dict:
    """
    Get cached stats for a project from beads-sync.

    This is a convenience function for use by progress.py and other modules
    that don't have the git_url handy.

    Returns:
        Dict with open, in_progress, closed (done), total, percentage
    """
    with _sync_managers_lock:
        if project_name in _sync_managers:
            stats = _sync_managers[project_name].get_stats()
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
        import sys
        from pathlib import Path
        root = Path(__file__).parent.parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))

        from registry import get_project_git_url
        git_url = get_project_git_url(project_name)
        if git_url:
            manager = get_beads_sync_manager(project_name, git_url)
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
    with _sync_managers_lock:
        if project_name in _sync_managers:
            return _tasks_to_features(_sync_managers[project_name].get_tasks())

    # Manager not found - try to create one from registry
    try:
        import sys
        from pathlib import Path
        root = Path(__file__).parent.parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))

        from registry import get_project_git_url
        git_url = get_project_git_url(project_name)
        if git_url:
            manager = get_beads_sync_manager(project_name, git_url)
            return _tasks_to_features(manager.get_tasks())
    except Exception as e:
        logger.debug(f"Failed to get features for {project_name}: {e}")

    return []


def _tasks_to_features(tasks: list[dict]) -> list[dict]:
    """Convert beads tasks to feature format for UI compatibility."""
    import re

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


async def initialize_all_projects() -> dict[str, bool]:
    """
    Clone beads-sync branches for all registered projects on server startup.

    This ensures we have local copies of beads data for all projects
    before the polling loop starts.

    Returns:
        Dict mapping project name to success status
    """
    import sys
    from pathlib import Path
    root = Path(__file__).parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from registry import list_valid_projects, get_project_git_url

    results = {}
    projects = list_valid_projects()
    logger.info(f"Initializing beads-sync for {len(projects)} registered projects")

    for project in projects:
        project_name = project["name"]
        git_url = get_project_git_url(project_name)
        if git_url:
            manager = get_beads_sync_manager(project_name, git_url)
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
        if project_name in _sync_managers:
            success, _ = await _sync_managers[project_name].pull_latest()
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
