"""
Features Router
===============

API endpoints for feature/test case management using beads.
All beads operations run on the host via BeadsManager with file-based locking.
"""

import json
import logging
import re
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..schemas import (
    FeatureCreate,
    FeatureListResponse,
    FeatureResponse,
    FeatureUpdate,
)
from ..services.beads_manager import get_cached_features, get_beads_manager

logger = logging.getLogger(__name__)


def _get_project_path(project_name: str) -> Path:
    """Get project path from registry."""
    # Add parent to path for imports
    _root = Path(__file__).parent.parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    from registry import get_project_path
    return get_project_path(project_name)


def _get_project_git_url(project_name: str) -> str | None:
    """Get project git URL from registry."""
    # Add parent to path for imports
    _root = Path(__file__).parent.parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    from registry import get_project_git_url
    return get_project_git_url(project_name)


def _get_in_progress_features_from_containers(project_name: str) -> set[str]:
    """Get feature IDs currently being worked on by containers."""
    _root = Path(__file__).parent.parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    from registry import list_project_containers
    try:
        containers = list_project_containers(project_name)
        return {c["current_feature"] for c in containers if c.get("current_feature")}
    except Exception:
        return set()


def read_local_beads_features(project_dir: Path) -> list[dict]:
    """Read features directly from local project's .beads/issues.jsonl."""
    issues_file = project_dir / ".beads" / "issues.jsonl"
    if not issues_file.exists():
        return []

    features = []
    try:
        with open(issues_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        task = json.loads(line)
                        features.append(beads_task_to_feature(task))
                    except json.JSONDecodeError:
                        continue
    except (PermissionError, OSError) as e:
        logger.warning(f"Failed to read local beads: {e}")
    return features


router = APIRouter(prefix="/api/projects/{project_name}/features", tags=["features"])


def validate_project_name(name: str) -> str:
    """Validate and sanitize project name to prevent path traversal."""
    if not re.match(r'^[a-zA-Z0-9_-]{1,50}$', name):
        raise HTTPException(
            status_code=400,
            detail="Invalid project name"
        )
    return name


def feature_to_response(feature: dict) -> FeatureResponse:
    """Convert a feature dict to a FeatureResponse."""
    return FeatureResponse(
        id=str(feature.get("id", "")),
        priority=feature.get("priority", 999),
        category=feature.get("category", ""),
        name=feature.get("name", ""),
        description=feature.get("description", ""),
        steps=feature.get("steps", []),
        passes=feature.get("passes", False),
        in_progress=feature.get("in_progress", False),
    )


def beads_task_to_feature(task: dict) -> dict:
    """
    Convert a beads task to feature format.

    Beads tasks have: id, title, status, priority, labels, body
    Features need: id, priority, category, name, description, steps, passes, in_progress
    """
    # Extract category from labels (first label)
    labels = task.get("labels", [])
    category = labels[0] if labels else ""

    # Parse steps from description if available (beads uses 'description' not 'body')
    description = task.get("description", "") or task.get("body", "")
    steps = []
    if description:
        # Try to extract numbered steps from description
        import re
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


@router.get("", response_model=FeatureListResponse)
async def list_features(project_name: str):
    """
    List all features for a project organized by status.

    Returns features in three lists:
    - pending: passes=False, not currently being worked on
    - in_progress: features currently being worked on
    - done: passes=True

    Reads from local beads database. Background poller handles remote sync.
    """
    project_name = validate_project_name(project_name)
    project_dir = _get_project_path(project_name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in registry")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    # Read from local beads database (no sync needed - background poller handles it)
    features = []
    git_url = _get_project_git_url(project_name)
    if git_url:
        try:
            from ..services.beads_manager import get_beads_manager
            manager = await get_beads_manager(project_name, git_url)
            tasks = manager.get_tasks()
            if tasks:
                features = [beads_task_to_feature(t) for t in tasks]
        except Exception as e:
            logger.warning(f"Failed to get features from beads for {project_name}: {e}")

    # Fall back to cache lookup if beads didn't return data
    if not features:
        features = get_cached_features(project_name)

    # Final fallback: read directly from local project beads
    if not features:
        features = read_local_beads_features(project_dir)

    # Get features currently being worked on from containers
    # This is more reliable than beads status since it's managed by our own code
    in_progress_ids = _get_in_progress_features_from_containers(project_name)

    pending = []
    in_progress = []
    done = []

    for f in features:
        feature_response = feature_to_response(f)
        feature_id = str(f.get("id", ""))

        if f.get("passes"):
            done.append(feature_response)
        elif feature_id in in_progress_ids or f.get("in_progress"):
            # Use container's current_feature as primary indicator,
            # fall back to beads in_progress status as secondary
            in_progress.append(feature_response)
        else:
            pending.append(feature_response)

    return FeatureListResponse(
        pending=pending,
        in_progress=in_progress,
        done=done,
    )


@router.post("", response_model=FeatureResponse)
async def create_feature(project_name: str, feature: FeatureCreate):
    """Create a new feature/test case manually."""
    project_name = validate_project_name(project_name)
    project_dir = _get_project_path(project_name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in registry")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    git_url = _get_project_git_url(project_name)
    if not git_url:
        raise HTTPException(status_code=404, detail="Project has no git URL")

    # Determine priority
    priority = feature.priority if feature.priority is not None else 999

    try:
        manager = await get_beads_manager(project_name, git_url)
        created = await manager.create_feature(
            name=feature.name,
            category=feature.category,
            description=feature.description,
            steps=feature.steps,
            priority=priority,
        )

        if not created:
            raise HTTPException(status_code=500, detail="Failed to create feature")

        return feature_to_response(created)
    except Exception as e:
        logger.error(f"Failed to create feature: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create feature: {e}")


@router.get("/{feature_id}", response_model=FeatureResponse)
async def get_feature(project_name: str, feature_id: str):
    """Get details of a specific feature."""
    project_name = validate_project_name(project_name)
    project_dir = _get_project_path(project_name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in registry")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    git_url = _get_project_git_url(project_name)
    if git_url:
        try:
            manager = await get_beads_manager(project_name, git_url)
            feature = manager.get_feature(feature_id)

            if feature:
                return feature_to_response(feature)
        except Exception as e:
            logger.warning(f"Failed to get feature from beads: {e}")

    # Fallback to cache
    cached_features = get_cached_features(project_name)
    for f in cached_features:
        if str(f.get("id", "")) == feature_id:
            return feature_to_response(f)

    raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")


@router.delete("/{feature_id}")
async def delete_feature(project_name: str, feature_id: str):
    """Delete a feature."""
    project_name = validate_project_name(project_name)
    project_dir = _get_project_path(project_name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in registry")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    git_url = _get_project_git_url(project_name)
    if not git_url:
        raise HTTPException(status_code=404, detail="Project has no git URL")

    try:
        manager = await get_beads_manager(project_name, git_url)

        # Check if feature exists first
        feature = manager.get_feature(feature_id)
        if not feature:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        success = await manager.delete_feature(feature_id)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete feature")

        return {"success": True, "message": f"Feature {feature_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete feature: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete feature: {e}")


@router.patch("/{feature_id}/skip")
async def skip_feature(project_name: str, feature_id: str):
    """Mark a feature as skipped by moving it to the end of the priority queue."""
    project_name = validate_project_name(project_name)
    project_dir = _get_project_path(project_name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in registry")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    git_url = _get_project_git_url(project_name)
    if not git_url:
        raise HTTPException(status_code=404, detail="Project has no git URL")

    try:
        manager = await get_beads_manager(project_name, git_url)
        result = await manager.skip_feature(feature_id)

        if result is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return {"success": True, "message": f"Feature {feature_id} moved to end of queue"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to skip feature: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to skip feature: {e}")


@router.patch("/{feature_id}", response_model=FeatureResponse)
async def update_feature(project_name: str, feature_id: str, update: FeatureUpdate):
    """
    Update a feature's fields.

    Only the provided fields will be updated; others remain unchanged.
    """
    project_name = validate_project_name(project_name)
    project_dir = _get_project_path(project_name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in registry")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    git_url = _get_project_git_url(project_name)
    if not git_url:
        raise HTTPException(status_code=404, detail="Project has no git URL")

    try:
        manager = await get_beads_manager(project_name, git_url)

        # Check if feature exists
        feature = manager.get_feature(feature_id)
        if not feature:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        # Update the feature
        updated = await manager.update_feature(
            feature_id,
            name=update.name,
            description=update.description,
            priority=update.priority,
            category=update.category,
            steps=update.steps,
        )

        if not updated:
            raise HTTPException(status_code=500, detail="Failed to update feature")

        return feature_to_response(updated)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update feature: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update feature: {e}")


@router.patch("/{feature_id}/reopen")
async def reopen_feature(project_name: str, feature_id: str):
    """Reopen a completed feature (move it back to pending)."""
    project_name = validate_project_name(project_name)
    project_dir = _get_project_path(project_name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in registry")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    git_url = _get_project_git_url(project_name)
    if not git_url:
        raise HTTPException(status_code=404, detail="Project has no git URL")

    try:
        manager = await get_beads_manager(project_name, git_url)

        # Check if feature exists and is closed
        feature = manager.get_feature(feature_id)
        if not feature:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        if not feature.get("passes"):
            raise HTTPException(status_code=400, detail="Feature is not completed, cannot reopen")

        # Reopen the feature
        reopened = await manager.reopen_feature(feature_id)

        if not reopened:
            raise HTTPException(status_code=500, detail="Failed to reopen feature")

        return {"success": True, "message": f"Feature {feature_id} reopened"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reopen feature: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reopen feature: {e}")
