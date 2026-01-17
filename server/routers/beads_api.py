"""
Beads API Router
================

Host-based API wrapper for beads commands. Agents call these endpoints instead
of running `bd` directly. The host runs `bd` commands on the project directory.

This provides:
- Centralized beads access (no direct bd in containers)
- Concurrency control via per-project locks
- Consistent JSON responses
"""

import asyncio
import json
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Per-project locks for write operations
_beads_locks: dict[str, asyncio.Lock] = {}


def _get_project_path(project_name: str) -> Path:
    """Get project path from registry."""
    _root = Path(__file__).parent.parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    from registry import get_project_path
    return get_project_path(project_name)


def validate_project_name(name: str) -> str:
    """Validate and sanitize project name to prevent path traversal."""
    if not re.match(r'^[a-zA-Z0-9_-]{1,50}$', name):
        raise HTTPException(status_code=400, detail="Invalid project name")
    return name


def validate_issue_id(issue_id: str) -> str:
    """Validate issue ID format."""
    # Allow formats like: beads-1, feat-42, project-abc123
    if not re.match(r'^[a-zA-Z]+-[a-zA-Z0-9]+$', issue_id):
        raise HTTPException(status_code=400, detail="Invalid issue ID format")
    return issue_id


async def run_beads_command(project_name: str, args: list[str]) -> dict[str, Any]:
    """
    Run bd command in project directory on host.

    Args:
        project_name: Name of the project
        args: Command arguments (e.g., ["list", "--json"])

    Returns:
        Parsed JSON output or error dict
    """
    project_path = _get_project_path(project_name)

    if not project_path:
        return {"error": f"Project '{project_name}' not found in registry"}

    if not project_path.exists():
        return {"error": f"Project directory not found: {project_path}"}

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["bd", "--no-daemon", *args],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
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


async def run_beads_write_command(project_name: str, args: list[str]) -> dict[str, Any]:
    """
    Run a write command with project-level locking.

    Write operations (create, update, close, reopen, sync) are serialized
    per-project to avoid race conditions.
    """
    lock = _beads_locks.setdefault(project_name, asyncio.Lock())

    async with lock:
        return await run_beads_command(project_name, args)


# =============================================================================
# Request/Response Models
# =============================================================================

class IssueCreate(BaseModel):
    """Request model for creating an issue."""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    type: str = Field(default="task")  # task, bug, feature, epic
    priority: int = Field(default=2, ge=0, le=4)  # 0=P0 (critical) to 4=P4 (backlog)
    labels: list[str] = Field(default_factory=list)


class IssueUpdate(BaseModel):
    """Request model for updating an issue."""
    title: str | None = None
    description: str | None = None
    status: str | None = None  # open, in_progress, closed
    priority: int | None = Field(default=None, ge=0, le=4)
    assignee: str | None = None


class IssueClose(BaseModel):
    """Request model for closing an issue."""
    reason: str | None = None


# =============================================================================
# Router
# =============================================================================

router = APIRouter(prefix="/api/projects/{project_name}/beads", tags=["beads"])


@router.get("/list")
async def list_issues(project_name: str, status: str | None = None):
    """
    List all issues for a project.

    Query params:
        status: Filter by status (open, in_progress, closed)
    """
    project_name = validate_project_name(project_name)

    args = ["list", "--json"]
    if status:
        args.extend(["--status", status])

    result = await run_beads_command(project_name, args)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result.get("data", [])


@router.get("/ready")
async def ready_issues(project_name: str):
    """
    List issues ready for work (no blockers).

    Returns issues that are open and have no blocking dependencies.
    """
    project_name = validate_project_name(project_name)

    result = await run_beads_command(project_name, ["ready", "--json"])

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result.get("data", [])


@router.get("/show/{issue_id}")
async def show_issue(project_name: str, issue_id: str):
    """
    Get details of a specific issue.
    """
    project_name = validate_project_name(project_name)
    issue_id = validate_issue_id(issue_id)

    result = await run_beads_command(project_name, ["show", issue_id, "--json"])

    if "error" in result:
        if "not found" in result["error"].lower():
            raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")
        raise HTTPException(status_code=500, detail=result["error"])

    data = result.get("data", [])
    if isinstance(data, list) and data:
        return data[0]
    return data


@router.get("/stats")
async def stats(project_name: str):
    """
    Get project statistics (open/closed/blocked counts).
    """
    project_name = validate_project_name(project_name)

    result = await run_beads_command(project_name, ["stats", "--json"])

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result.get("data", result.get("output", {}))


@router.post("/create")
async def create_issue(project_name: str, issue: IssueCreate):
    """
    Create a new issue.
    """
    project_name = validate_project_name(project_name)

    # Build command args
    args = [
        "create",
        "--title", issue.title,
        "--type", issue.type,
        "--priority", f"P{issue.priority}",
        "--json",
    ]

    if issue.description:
        args.extend(["--description", issue.description])

    if issue.labels:
        args.extend(["--labels", ",".join(issue.labels)])

    result = await run_beads_write_command(project_name, args)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result.get("data", {"success": True})


@router.patch("/update/{issue_id}")
async def update_issue(project_name: str, issue_id: str, update: IssueUpdate):
    """
    Update an issue's fields.

    Only provided fields will be updated.
    """
    project_name = validate_project_name(project_name)
    issue_id = validate_issue_id(issue_id)

    # Build command args
    args = ["update", issue_id]

    if update.title is not None:
        args.extend(["--title", update.title])

    if update.description is not None:
        args.extend(["--description", update.description])

    if update.status is not None:
        args.extend(["--status", update.status])

    if update.priority is not None:
        args.extend(["--priority", f"P{update.priority}"])

    if update.assignee is not None:
        args.extend(["--assignee", update.assignee])

    # Must have at least one update
    if len(args) == 2:
        raise HTTPException(status_code=400, detail="No update fields provided")

    result = await run_beads_write_command(project_name, args)

    if "error" in result:
        if "not found" in result["error"].lower():
            raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")
        raise HTTPException(status_code=500, detail=result["error"])

    return {"success": True, "message": f"Issue {issue_id} updated"}


@router.post("/close/{issue_id}")
async def close_issue(project_name: str, issue_id: str, body: IssueClose | None = None):
    """
    Close an issue.
    """
    project_name = validate_project_name(project_name)
    issue_id = validate_issue_id(issue_id)

    args = ["close", issue_id]

    if body and body.reason:
        args.extend(["--reason", body.reason])

    result = await run_beads_write_command(project_name, args)

    if "error" in result:
        if "not found" in result["error"].lower():
            raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")
        raise HTTPException(status_code=500, detail=result["error"])

    return {"success": True, "message": f"Issue {issue_id} closed"}


@router.post("/reopen/{issue_id}")
async def reopen_issue(project_name: str, issue_id: str):
    """
    Reopen a closed issue.
    """
    project_name = validate_project_name(project_name)
    issue_id = validate_issue_id(issue_id)

    result = await run_beads_write_command(project_name, ["reopen", issue_id])

    if "error" in result:
        if "not found" in result["error"].lower():
            raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")
        raise HTTPException(status_code=500, detail=result["error"])

    return {"success": True, "message": f"Issue {issue_id} reopened"}


@router.post("/sync")
async def sync_issues(project_name: str):
    """
    Sync beads with git remote.
    """
    project_name = validate_project_name(project_name)

    result = await run_beads_write_command(project_name, ["sync"])

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return {"success": True, "message": "Beads synced with remote"}


@router.post("/dep/add")
async def add_dependency(project_name: str, issue_id: str, depends_on: str):
    """
    Add a dependency between issues.

    Args:
        issue_id: The issue that depends on another
        depends_on: The issue that must be completed first
    """
    project_name = validate_project_name(project_name)
    issue_id = validate_issue_id(issue_id)
    depends_on = validate_issue_id(depends_on)

    result = await run_beads_write_command(
        project_name, ["dep", "add", issue_id, depends_on]
    )

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return {"success": True, "message": f"Added dependency: {issue_id} depends on {depends_on}"}


class CommentAdd(BaseModel):
    """Request model for adding a comment."""
    comment: str = Field(..., min_length=1)


@router.post("/comments/{issue_id}")
async def add_comment(project_name: str, issue_id: str, body: CommentAdd):
    """
    Add a comment to an issue.
    """
    project_name = validate_project_name(project_name)
    issue_id = validate_issue_id(issue_id)

    result = await run_beads_write_command(
        project_name, ["comments", issue_id, "--add", body.comment]
    )

    if "error" in result:
        if "not found" in result["error"].lower():
            raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")
        raise HTTPException(status_code=500, detail=result["error"])

    return {"success": True, "message": f"Comment added to {issue_id}"}
