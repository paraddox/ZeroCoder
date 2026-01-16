"""
Branch Cleanup Service
======================
Cleans up remote feature branches on server startup.
"""

import asyncio
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

PROTECTED_BRANCHES = {"main", "master", "beads-sync", "HEAD"}


async def cleanup_remote_branches_for_project(project_name: str, git_url: str, local_path: Path) -> int:
    """
    Delete all remote feature branches for a project.
    Uses the local clone at ~/.zerocoder/beads-sync/{project} or project path.

    Returns number of branches deleted.
    """
    from registry import get_beads_sync_dir

    # Use beads-sync clone path if available, otherwise project path
    work_dir = get_beads_sync_dir() / project_name
    if not work_dir.exists():
        work_dir = local_path
    if not work_dir.exists():
        logger.warning(f"No local clone found for {project_name}")
        return 0

    try:
        # Fetch to get current remote state
        subprocess.run(
            ["git", "-C", str(work_dir), "fetch", "--prune", "origin"],
            capture_output=True, timeout=60
        )

        # List remote branches
        result = subprocess.run(
            ["git", "-C", str(work_dir), "branch", "-r", "--format=%(refname:short)"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return 0

        # Find branches to delete
        branches_to_delete = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            branch = line.replace("origin/", "").strip()
            if branch and branch not in PROTECTED_BRANCHES:
                branches_to_delete.append(branch)

        if not branches_to_delete:
            return 0

        # Delete from remote
        deleted = 0
        for branch in branches_to_delete:
            result = subprocess.run(
                ["git", "-C", str(work_dir), "push", "origin", "--delete", branch],
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                deleted += 1
                logger.info(f"Deleted remote branch {branch} from {project_name}")

        return deleted

    except Exception as e:
        logger.warning(f"Error cleaning branches for {project_name}: {e}")
        return 0


async def cleanup_all_remote_branches() -> dict[str, int]:
    """
    Clean up remote feature branches for all registered projects.
    Called on server startup.

    Returns dict of project_name -> branches_deleted.
    """
    from registry import list_registered_projects, get_project_path, get_project_git_url

    results = {}
    projects = list_registered_projects()

    if not projects:
        return results

    logger.info(f"Cleaning up remote feature branches for {len(projects)} projects...")

    for name in projects:
        git_url = get_project_git_url(name)
        local_path = get_project_path(name)

        if not git_url or not local_path:
            continue

        deleted = await cleanup_remote_branches_for_project(name, git_url, local_path)
        if deleted > 0:
            results[name] = deleted

    if results:
        total = sum(results.values())
        logger.info(f"Cleaned up {total} remote feature branches across {len(results)} projects")

    return results
