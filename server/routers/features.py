"""
Features Router
===============

API endpoints for feature/test case management using beads.
Routes through container via docker exec. Auto-starts container for edits.
"""

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
from ..services.container_beads import ContainerBeadsClient
from ..services.feature_poller import (
    get_cached_features,
    poll_container_features,
    update_feature_cache,
)

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


router = APIRouter(prefix="/api/projects/{project_name}/features", tags=["features"])


def validate_project_name(name: str) -> str:
    """Validate and sanitize project name to prevent path traversal."""
    if not re.match(r'^[a-zA-Z0-9_-]{1,50}$', name):
        raise HTTPException(
            status_code=400,
            detail="Invalid project name"
        )
    return name


def _is_container_running(project_name: str) -> bool:
    """Check if the container is running for this project."""
    from ..services.container_manager import _managers, _managers_lock

    with _managers_lock:
        manager = _managers.get(project_name)
        return manager is not None and manager.status == "running"


async def _ensure_container_running(project_name: str, project_dir: Path, git_url: str) -> None:
    """
    Ensure the container is running for write operations.

    Auto-starts the container if it's stopped (without starting the agent).
    Raises HTTPException if container can't be started.
    """
    from ..services.container_manager import get_container_manager, check_docker_available, check_image_exists

    if _is_container_running(project_name):
        return  # Already running

    # Check Docker availability
    if not check_docker_available():
        raise HTTPException(
            status_code=503,
            detail="Docker is not available. Please ensure Docker is installed and running."
        )

    if not check_image_exists():
        raise HTTPException(
            status_code=503,
            detail="Container image 'zerocoder-project' not found. Run: docker build -f Dockerfile.project -t zerocoder-project ."
        )

    # Get manager and start container (container_number=1 for default)
    manager = get_container_manager(project_name, git_url, 1, project_dir)
    success, message = await manager.start_container_only()

    if not success:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to start container: {message}"
        )


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


@router.get("", response_model=FeatureListResponse)
async def list_features(project_name: str):
    """
    List all features for a project organized by status.

    Returns features in three lists:
    - pending: passes=False, not currently being worked on
    - in_progress: features currently being worked on
    - done: passes=True

    Uses cached data from polling. Updates every 30 seconds when container running.
    """
    project_name = validate_project_name(project_name)
    project_dir = _get_project_path(project_name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in registry")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    # Always read from cache - populated by feature_poller when container running
    cached_features = get_cached_features(project_name)

    pending = []
    in_progress = []
    done = []

    for f in cached_features:
        feature_response = feature_to_response(f)
        if f.get("passes"):
            done.append(feature_response)
        elif f.get("in_progress"):
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
    """Create a new feature/test case manually. Auto-starts container if needed."""
    project_name = validate_project_name(project_name)
    project_dir = _get_project_path(project_name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in registry")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    # Ensure container is running (auto-start if needed)
    git_url = _get_project_git_url(project_name)
    if not git_url:
        raise HTTPException(status_code=404, detail="Project has no git URL")
    await _ensure_container_running(project_name, project_dir, git_url)

    # Determine priority
    priority = feature.priority if feature.priority is not None else 999

    try:
        container_client = ContainerBeadsClient(project_name)
        feature_id = await container_client.create(
            name=feature.name,
            category=feature.category,
            description=feature.description,
            steps=feature.steps,
            priority=priority,
        )

        if not feature_id:
            raise HTTPException(status_code=500, detail="Failed to create feature")

        # Trigger immediate feature poll to sync to host cache
        container_name = f"zerocoder-{project_name}"
        try:
            data = await poll_container_features(container_name, project_name)
            if data:
                update_feature_cache(project_name, data)
        except Exception as e:
            logger.warning(f"Failed to refresh feature cache: {e}")

        # Get the created feature
        created = await container_client.get_feature(feature_id)
        if not created:
            raise HTTPException(status_code=500, detail="Feature created but could not be retrieved")

        return feature_to_response(created)
    except RuntimeError as e:
        logger.error(f"Container command failed: {e}")
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

    # If container running, get from container for fresh data
    if _is_container_running(project_name):
        try:
            container_client = ContainerBeadsClient(project_name)
            feature = await container_client.get_feature(feature_id)

            if not feature:
                raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

            return feature_to_response(feature)
        except RuntimeError as e:
            logger.error(f"Container command failed: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to get feature: {e}")

    # Fallback to cache
    cached_features = get_cached_features(project_name)
    for f in cached_features:
        if str(f.get("id", "")) == feature_id:
            return feature_to_response(f)

    raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")


@router.delete("/{feature_id}")
async def delete_feature(project_name: str, feature_id: str):
    """Delete a feature. Auto-starts container if needed."""
    project_name = validate_project_name(project_name)
    project_dir = _get_project_path(project_name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in registry")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    # Ensure container is running (auto-start if needed)
    git_url = _get_project_git_url(project_name)
    if not git_url:
        raise HTTPException(status_code=404, detail="Project has no git URL")
    await _ensure_container_running(project_name, project_dir, git_url)

    try:
        container_client = ContainerBeadsClient(project_name)

        # Check if feature exists first
        feature = await container_client.get_feature(feature_id)
        if not feature:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        success = await container_client.delete(feature_id)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to delete feature")

        # Trigger immediate feature poll to sync to host cache
        container_name = f"zerocoder-{project_name}"
        try:
            data = await poll_container_features(container_name, project_name)
            if data:
                update_feature_cache(project_name, data)
        except Exception as e:
            logger.warning(f"Failed to refresh feature cache: {e}")

        return {"success": True, "message": f"Feature {feature_id} deleted"}
    except RuntimeError as e:
        logger.error(f"Container command failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete feature: {e}")
    except HTTPException:
        raise


@router.patch("/{feature_id}/skip")
async def skip_feature(project_name: str, feature_id: str):
    """
    Mark a feature as skipped by moving it to the end of the priority queue.
    Auto-starts container if needed.
    """
    project_name = validate_project_name(project_name)
    project_dir = _get_project_path(project_name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in registry")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    # Ensure container is running (auto-start if needed)
    git_url = _get_project_git_url(project_name)
    if not git_url:
        raise HTTPException(status_code=404, detail="Project has no git URL")
    await _ensure_container_running(project_name, project_dir, git_url)

    try:
        container_client = ContainerBeadsClient(project_name)
        result = await container_client.skip(feature_id)

        if result is None:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        # Trigger immediate feature poll to sync to host cache
        container_name = f"zerocoder-{project_name}"
        try:
            data = await poll_container_features(container_name, project_name)
            if data:
                update_feature_cache(project_name, data)
        except Exception as e:
            logger.warning(f"Failed to refresh feature cache: {e}")

        return {"success": True, "message": f"Feature {feature_id} moved to end of queue"}
    except RuntimeError as e:
        logger.error(f"Container command failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to skip feature: {e}")
    except HTTPException:
        raise


@router.patch("/{feature_id}", response_model=FeatureResponse)
async def update_feature(project_name: str, feature_id: str, update: FeatureUpdate):
    """
    Update a feature's fields. Auto-starts container if needed.

    Only the provided fields will be updated; others remain unchanged.
    """
    project_name = validate_project_name(project_name)
    project_dir = _get_project_path(project_name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in registry")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    # Ensure container is running (auto-start if needed)
    git_url = _get_project_git_url(project_name)
    if not git_url:
        raise HTTPException(status_code=404, detail="Project has no git URL")
    await _ensure_container_running(project_name, project_dir, git_url)

    try:
        container_client = ContainerBeadsClient(project_name)

        # Check if feature exists
        feature = await container_client.get_feature(feature_id)
        if not feature:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        # Update the feature
        updated = await container_client.update(
            feature_id,
            name=update.name,
            description=update.description,
            priority=update.priority,
            category=update.category,
            steps=update.steps,
        )

        if not updated:
            raise HTTPException(status_code=500, detail="Failed to update feature")

        # Trigger immediate feature poll to sync to host cache
        container_name = f"zerocoder-{project_name}"
        try:
            data = await poll_container_features(container_name, project_name)
            if data:
                update_feature_cache(project_name, data)
        except Exception as e:
            logger.warning(f"Failed to refresh feature cache: {e}")

        return feature_to_response(updated)
    except RuntimeError as e:
        logger.error(f"Container command failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update feature: {e}")
    except HTTPException:
        raise


@router.patch("/{feature_id}/reopen")
async def reopen_feature(project_name: str, feature_id: str):
    """
    Reopen a completed feature (move it back to pending).
    Auto-starts container if needed.
    """
    project_name = validate_project_name(project_name)
    project_dir = _get_project_path(project_name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in registry")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    # Ensure container is running (auto-start if needed)
    git_url = _get_project_git_url(project_name)
    if not git_url:
        raise HTTPException(status_code=404, detail="Project has no git URL")
    await _ensure_container_running(project_name, project_dir, git_url)

    try:
        container_client = ContainerBeadsClient(project_name)

        # Check if feature exists and is closed
        feature = await container_client.get_feature(feature_id)
        if not feature:
            raise HTTPException(status_code=404, detail=f"Feature {feature_id} not found")

        if not feature.get("passes"):
            raise HTTPException(status_code=400, detail="Feature is not completed, cannot reopen")

        # Reopen the feature
        reopened = await container_client.reopen(feature_id)

        if not reopened:
            raise HTTPException(status_code=500, detail="Failed to reopen feature")

        # Trigger immediate feature poll to sync to host cache
        container_name = f"zerocoder-{project_name}"
        try:
            data = await poll_container_features(container_name, project_name)
            if data:
                update_feature_cache(project_name, data)
        except Exception as e:
            logger.warning(f"Failed to refresh feature cache: {e}")

        return {"success": True, "message": f"Feature {feature_id} reopened"}
    except RuntimeError as e:
        logger.error(f"Container command failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reopen feature: {e}")
    except HTTPException:
        raise
