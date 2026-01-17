"""
Task Cleanup Service
====================
Handles cleanup of stale task states on server startup.
"""

import asyncio
import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


async def _run_bd(project_path: Path, args: list[str], timeout: int = 60) -> dict:
    """Run bd command in project directory."""
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["bd", "--no-daemon", *args],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return {"error": result.stderr.strip() or f"Exit code {result.returncode}"}

        stdout = result.stdout.strip()
        if not stdout:
            return {"success": True}
        try:
            return {"success": True, "data": json.loads(stdout)}
        except json.JSONDecodeError:
            return {"success": True, "output": stdout}
    except Exception as e:
        return {"error": str(e)}


async def revert_in_progress_tasks_for_project(project_name: str, project_path: Path) -> int:
    """
    Revert all in_progress tasks to open for a single project.
    Returns number of tasks reverted.
    """
    # Get all in_progress tasks
    result = await _run_bd(project_path, ["list", "--json", "--status", "in_progress"])
    if "error" in result:
        logger.warning(f"Failed to list in_progress tasks for {project_name}: {result['error']}")
        return 0

    tasks = result.get("data", [])
    if not tasks:
        return 0

    reverted = 0
    for task in tasks:
        task_id = task.get("id")
        if not task_id:
            continue

        # Revert to open status
        update_result = await _run_bd(project_path, ["update", task_id, "--status=open"])
        if "error" not in update_result:
            reverted += 1
            logger.debug(f"Reverted {task_id} to open in {project_name}")
        else:
            logger.warning(f"Failed to revert {task_id}: {update_result['error']}")

    # Sync after changes
    if reverted > 0:
        await _run_bd(project_path, ["sync"])

    return reverted


async def revert_all_in_progress_tasks() -> dict[str, int]:
    """
    Revert all in_progress tasks to open for all registered projects.
    Called on server startup.
    Returns dict of project_name -> tasks_reverted.
    """
    from registry import list_valid_projects, get_project_path

    results = {}
    projects = list_valid_projects()

    if not projects:
        return results

    logger.info(f"Checking {len(projects)} projects for stale in_progress tasks...")

    for project in projects:
        project_name = project["name"]
        project_path = get_project_path(project_name)

        if not project_path or not project_path.exists():
            continue

        # Check if .beads directory exists
        beads_dir = project_path / ".beads"
        if not beads_dir.exists():
            continue

        reverted = await revert_in_progress_tasks_for_project(project_name, project_path)
        if reverted > 0:
            results[project_name] = reverted

    if results:
        total = sum(results.values())
        logger.info(f"Reverted {total} in_progress tasks to open across {len(results)} projects")

    return results
