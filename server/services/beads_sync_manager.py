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
            result = subprocess.run(
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
            result = subprocess.run(
                ["git", "-C", str(self.local_path), "pull", "--ff-only", "origin", "beads-sync"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                # Try a fetch + reset if pull fails
                subprocess.run(
                    ["git", "-C", str(self.local_path), "fetch", "origin", "beads-sync"],
                    capture_output=True,
                    timeout=30,
                )
                subprocess.run(
                    ["git", "-C", str(self.local_path), "reset", "--hard", "origin/beads-sync"],
                    capture_output=True,
                    timeout=10,
                )

            self._last_pull = datetime.now()
            return True, "Pulled successfully"

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
                        except json.JSONDecodeError:
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


def get_beads_sync_manager(project_name: str, git_remote_url: str) -> BeadsSyncManager:
    """Get or create a BeadsSyncManager for a project."""
    if project_name not in _sync_managers:
        _sync_managers[project_name] = BeadsSyncManager(project_name, git_remote_url)
    return _sync_managers[project_name]


def clear_beads_sync_manager(project_name: str) -> None:
    """Clear cached BeadsSyncManager for a project."""
    if project_name in _sync_managers:
        del _sync_managers[project_name]


async def pull_all_beads_sync() -> dict[str, bool]:
    """
    Pull latest for all registered projects.

    Returns:
        Dict mapping project name to success status
    """
    results = {}
    for project_name, manager in _sync_managers.items():
        success, _ = await manager.pull_latest()
        results[project_name] = success
    return results


# Background polling task
POLL_INTERVAL_SECONDS = 15


async def start_beads_sync_poller() -> None:
    """
    Start a background task that polls beads-sync for all projects.

    This should be called when the server starts.
    """
    logger.info(f"Starting beads-sync poller (interval: {POLL_INTERVAL_SECONDS}s)")

    while True:
        try:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            results = await pull_all_beads_sync()
            if results:
                successes = sum(1 for v in results.values() if v)
                logger.debug(f"Beads sync poll: {successes}/{len(results)} successful")
        except asyncio.CancelledError:
            logger.info("Beads sync poller stopped")
            break
        except Exception as e:
            logger.exception(f"Error in beads sync poller: {e}")
