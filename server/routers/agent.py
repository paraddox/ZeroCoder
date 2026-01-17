"""
Agent Router
============

API endpoints for agent/container control (start/stop/send instruction).
Uses ContainerManager for per-project Docker containers.
"""

import asyncio
import logging
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import APIRouter, HTTPException

from ..schemas import AgentActionResponse, AgentStartRequest, AgentStatus
from ..services.container_manager import (
    get_container_manager,
    get_existing_container_manager,
    check_docker_available,
    check_image_exists,
)
from ..websocket import manager as websocket_manager

# Add root to path for imports
_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from registry import get_project_path, get_project_git_url, get_project_info
from progress import has_features, has_open_features
from prompts import (
    get_initializer_prompt,
    get_coding_prompt,
    get_coding_prompt_yolo,
    get_overseer_prompt,
    is_existing_repo_project,
)
import asyncio


def _get_project_path(project_name: str) -> Path | None:
    """Get project path from registry."""
    return get_project_path(project_name)


def _get_project_git_url(project_name: str) -> str | None:
    """Get project git URL from registry."""
    return get_project_git_url(project_name)


def _get_registry_functions():
    """Get registry functions for testing purposes."""
    return (
        get_project_path,
        get_project_git_url,
        get_project_info,
    )


router = APIRouter(prefix="/api/projects/{project_name}/agent", tags=["agent"])


def validate_project_name(name: str) -> str:
    """Validate and sanitize project name to prevent path traversal."""
    if not re.match(r'^[a-zA-Z0-9_-]{1,50}$', name):
        raise HTTPException(
            status_code=400,
            detail="Invalid project name"
        )
    return name


def get_project_container(project_name: str, container_number: int = 1):
    """Get the container manager for a project and container number."""
    project_name = validate_project_name(project_name)
    project_dir = _get_project_path(project_name)
    git_url = _get_project_git_url(project_name)

    if not project_dir:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_name}' not found in registry"
        )

    if not git_url:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{project_name}' has no git URL"
        )

    if not project_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Project directory not found: {project_dir}"
        )

    return get_container_manager(project_name, git_url, container_number, project_dir)


@router.get("/status", response_model=AgentStatus)
async def get_agent_status(project_name: str):
    """Get the current status of the container for a project."""
    project_name = validate_project_name(project_name)

    # Check if a manager exists without creating one
    manager = get_existing_container_manager(project_name, container_number=1)

    if manager is None:
        # No container has been created yet - return default status
        return AgentStatus(
            status="not_created",
            container_name=f"zerocoder-{project_name}-1",
            started_at=None,
            idle_seconds=0,
            agent_running=False,
            graceful_stop_requested=False,
        )

    status_dict = manager.get_status_dict()

    return AgentStatus(
        status=status_dict["status"],
        container_name=status_dict["container_name"],
        started_at=manager.started_at,
        idle_seconds=status_dict["idle_seconds"],
        agent_running=status_dict.get("agent_running", False),
        graceful_stop_requested=status_dict.get("graceful_stop_requested", False),
    )


def _get_agent_prompt(project_dir: Path, project_name: str, yolo_mode: bool = False) -> str:
    """
    Determine the appropriate prompt based on project state.

    For NEW projects (with app_spec):
    - If no features exist: use initializer prompt
    - If open features exist: use coding prompt (or yolo variant)
    - If all features closed: use overseer prompt (verification)

    For EXISTING repos (no app_spec):
    - Skip initializer entirely - go straight to coding
    - Use existing-repo variants of coding and overseer prompts
    """
    is_existing = is_existing_repo_project(project_dir)

    if not has_features(project_dir, project_name):
        if is_existing:
            # Existing repo with no features - go straight to coding
            # (no initializer needed since there's no spec to parse)
            return get_coding_prompt(project_dir)
        else:
            # New project with no features - run initializer
            return get_initializer_prompt(project_dir)
    elif has_open_features(project_dir, project_name):
        # Open features exist - run coding agent
        if yolo_mode:
            return get_coding_prompt_yolo(project_dir)
        return get_coding_prompt(project_dir)
    else:
        # Features exist but all closed - run overseer for verification
        return get_overseer_prompt(project_dir)


@router.post("/start", response_model=AgentActionResponse)
async def start_agent(
    project_name: str,
    request: AgentStartRequest = AgentStartRequest(),
):
    """
    Start the container for a project and send the appropriate instruction.

    - Creates container if not exists
    - Starts container if stopped
    - Automatically determines if this is initialization or continuation
    - Sends the appropriate prompt (initializer or coding)
    """
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

    manager = get_project_container(project_name)
    project_dir = manager.project_dir  # Use manager's validated project_dir

    # Determine the instruction to send
    instruction = request.instruction
    agent_type = "coder"  # Default agent type
    use_initializer = False  # Track if we need the initializer
    if not instruction:
        # Auto-determine based on project state
        try:
            instruction = _get_agent_prompt(project_dir, project_name, request.yolo_mode)
            # Determine which prompt was selected for logging
            is_existing = is_existing_repo_project(project_dir)
            if not has_features(project_dir, project_name):
                prompt_type = "coding (existing repo)" if is_existing else "initializer"
                agent_type = "coder"  # Initializer uses coder agent type
                # Only set use_initializer for new projects (not existing repos)
                use_initializer = not is_existing
            elif has_open_features(project_dir, project_name):
                prompt_type = "coding"
                agent_type = "coder"
            else:
                prompt_type = "overseer"
                agent_type = "overseer"
            print(f"[Agent] Auto-selected {prompt_type} prompt for {project_name}")
        except FileNotFoundError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Could not load prompt: {e}"
            )

    # Set agent type for OpenCode SDK routing
    manager._current_agent_type = agent_type

    # For initializer, always use Claude SDK with Opus 4.5 (regardless of project model)
    if use_initializer:
        manager._force_claude_sdk = True
        manager._forced_model = "claude-opus-4-5-20251101"
        print(f"[Agent] Initializer will use Claude SDK with Opus 4.5")
    else:
        manager._force_claude_sdk = False

    success, message = await manager.start(instruction=instruction)

    return AgentActionResponse(
        success=success,
        status=manager.status,
        message=message,
    )


@router.post("/start-all", response_model=AgentActionResponse)
async def start_all_containers(project_name: str):
    """
    Start project with init container first, then spawn coding containers.

    This orchestrates parallel container startup according to a two-phase plan:

    Phase 1: Run init container (zerocoder-{project}-0)
    - New project: full initializer prompt to create features from app_spec
    - Existing project: recovery (in_progress -> open) and sync
    - Waits for init to complete before proceeding

    Phase 2: Spawn N coding containers (zerocoder-{project}-1..N)
    - N is determined by target_container_count in project registry
    - All coding containers start in parallel with the coding prompt
    """
    # Check Docker availability first
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

    # Validate project name
    project_name = validate_project_name(project_name)

    # Get project info from registry
    project_info = get_project_info(project_name)
    if not project_info:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found in registry")

    git_url = project_info.get("git_url")
    if not git_url:
        raise HTTPException(status_code=404, detail=f"Project '{project_name}' has no git URL")

    target_count = project_info.get("target_container_count", 1)
    is_new = project_info.get("is_new", False)

    # Register with BeadsSyncManager to ensure we can pull beads-sync data
    try:
        from ..services.beads_sync_manager import get_beads_sync_manager
        beads_manager = get_beads_sync_manager(project_name, git_url)
        await beads_manager.ensure_cloned()
    except Exception as e:
        # Non-fatal - beads sync might not be set up yet for new projects
        print(f"[StartAll] Beads sync init warning (continuing): {e}")

    # Get project directory
    project_dir = _get_project_path(project_name)
    if not project_dir or not project_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Project directory not found for '{project_name}'"
        )

    # Pull latest changes to local clone before checking state
    # This ensures we have up-to-date .beads/ data for has_features check
    if (project_dir / ".git").exists():
        try:
            # Sync beads first to commit any pending task state changes
            # Use beads API to avoid lock conflicts with container beads operations
            if (project_dir / ".beads").exists():
                print(f"[StartAll] Syncing beads state...")
                from .beads_api import run_beads_write_command
                sync_result = await run_beads_write_command(project_name, ["sync"])
                if "error" not in sync_result:
                    print(f"[StartAll] Beads synced successfully")
                else:
                    print(f"[StartAll] Beads sync warning: {sync_result.get('error', 'Unknown error')}")

            print(f"[StartAll] Pulling latest changes to local clone...")

            # Stash any unstaged changes first to avoid pull conflicts
            stash_result = subprocess.run(
                ["git", "-C", str(project_dir), "stash", "--include-untracked"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            stashed = "No local changes to save" not in stash_result.stdout
            if stashed:
                print(f"[StartAll] Stashed local changes")

            # Now pull
            pull_result = subprocess.run(
                ["git", "-C", str(project_dir), "pull", "--rebase", "origin", "main"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if pull_result.returncode == 0:
                print(f"[StartAll] Local clone updated successfully")
            else:
                print(f"[StartAll] Git pull warning: {pull_result.stderr}")

            # Restore stashed changes
            if stashed:
                pop_result = subprocess.run(
                    ["git", "-C", str(project_dir), "stash", "pop"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if pop_result.returncode == 0:
                    print(f"[StartAll] Restored stashed changes")
                else:
                    print(f"[StartAll] Stash pop warning: {pop_result.stderr}")
        except Exception as e:
            print(f"[StartAll] Git pull error (continuing anyway): {e}")

    # ==========================================================================
    # PHASE 1: Run init container (container_number=0)
    # ==========================================================================
    init_manager = get_container_manager(project_name, git_url, container_number=0, project_dir=project_dir)

    # Determine init instruction based on project state
    try:
        if is_new or not has_features(project_dir, project_name):
            # New project - run full initializer with Opus 4.5
            instruction = get_initializer_prompt(project_dir)
            init_manager._force_claude_sdk = True
            init_manager._forced_model = "claude-opus-4-5-20251101"
            print(f"[StartAll] Phase 1: Running full initializer for new project {project_name}")
        else:
            # Existing project - just run recovery (pre_agent_sync + recover_stuck_features)
            # The init container will sync and recover any stuck features
            instruction = None  # Will trigger sync and recovery without full agent run
            print(f"[StartAll] Phase 1: Running recovery for existing project {project_name}")
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not load initializer prompt: {e}"
        )

    # Start init container and wait for it to complete
    if instruction:
        # Full initializer run
        success, message = await init_manager.start(instruction=instruction)
        if not success:
            return AgentActionResponse(
                success=False,
                status=init_manager.status,
                message=f"Phase 1 (init) failed: {message}",
            )

        # Wait for init container to finish
        # The init container runs the initializer which creates features, then exits
        print(f"[StartAll] Waiting for init container to complete...")
        while init_manager.is_agent_running():
            await asyncio.sleep(2)

        print(f"[StartAll] Phase 1 complete. Init container finished.")
    else:
        # Recovery only - start container, run sync and recovery, then stop
        success, message = await init_manager.start_container_only()
        if not success:
            return AgentActionResponse(
                success=False,
                status=init_manager.status,
                message=f"Phase 1 (init container start) failed: {message}",
            )

        # Wait for container to clone the repo (entrypoint clones from GIT_REMOTE_URL)
        for attempt in range(30):  # 60 seconds total
            await asyncio.sleep(2)
            check = subprocess.run(
                ["docker", "exec", "-u", "coder", init_manager.container_name,
                 "test", "-d", "/project/.git"],
                capture_output=True,
                text=True,
            )
            if check.returncode == 0:
                print(f"[StartAll] Init container repo cloned successfully")
                break
            print(f"[StartAll] Waiting for repo clone (attempt {attempt + 1}/30)")
        else:
            await init_manager.stop()
            return AgentActionResponse(
                success=False,
                status="error",
                message="Init container failed to clone repo after 60 seconds",
            )

        # Run pre_agent_sync and recover_stuck_features
        sync_ok, sync_msg = await init_manager.pre_agent_sync()
        if not sync_ok:
            print(f"[StartAll] Pre-agent sync warning: {sync_msg}")

        recovery_ok, recovery_msg = await init_manager.recover_stuck_features()
        if not recovery_ok:
            print(f"[StartAll] Recovery warning: {recovery_msg}")

        # Stop init container after recovery
        await init_manager.stop()
        print(f"[StartAll] Phase 1 complete. Recovery finished.")

    # ==========================================================================
    # PHASE 2: Spawn N coding containers in parallel
    # ==========================================================================
    print(f"[StartAll] Phase 2: Spawning {target_count} coding container(s)...")

    coding_managers = []
    for i in range(1, target_count + 1):
        manager = get_container_manager(project_name, git_url, container_number=i, project_dir=project_dir)
        coding_managers.append(manager)

    # Get coding prompt for all containers
    try:
        coding_prompt = get_coding_prompt(project_dir)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not load coding prompt: {e}"
        )

    # Start coding containers with staggered delays to prevent race conditions
    # Each container needs time to claim a feature and sync before next starts
    STAGGER_DELAY_SECONDS = 10

    async def start_coding_container(manager):
        """Start a single coding container with the coding prompt."""
        manager._current_agent_type = "coder"
        manager._force_claude_sdk = False
        return await manager.start(instruction=coding_prompt)

    results = []
    for i, manager in enumerate(coding_managers):
        if i > 0:
            # Wait between container starts to allow beads-sync coordination
            logger.info(f"[StartAll] Waiting {STAGGER_DELAY_SECONDS}s before starting container {i+1}...")
            await asyncio.sleep(STAGGER_DELAY_SECONDS)
        try:
            logger.info(f"[StartAll] Starting coding container {i+1}...")
            result = await start_coding_container(manager)
            results.append(result)
        except Exception as e:
            results.append(e)

    # Analyze results
    successes = 0
    failures = []
    for i, result in enumerate(results, start=1):
        if isinstance(result, Exception):
            failures.append(f"Container {i}: {str(result)}")
        elif isinstance(result, tuple):
            success, msg = result
            if success:
                successes += 1
            else:
                failures.append(f"Container {i}: {msg}")
        else:
            failures.append(f"Container {i}: unexpected result")

    # Determine overall status
    all_success = successes == target_count
    status = "running" if all_success else ("error" if successes == 0 else "partial")

    if failures:
        message = f"Started {successes}/{target_count} coding containers. Failures: {'; '.join(failures)}"
    else:
        message = f"Successfully started init + {target_count} coding container(s)"

    return AgentActionResponse(
        success=all_success,
        status=status,
        message=message,
    )


@router.post("/stop", response_model=AgentActionResponse)
async def stop_agent(project_name: str):
    """Stop ALL containers for a project (does not remove them)."""
    from ..services.container_manager import _managers

    project_name = validate_project_name(project_name)

    # Get all managers for this project
    project_managers = _managers.get(project_name, {})
    if not project_managers:
        # Try to stop container 1 as fallback (single container mode)
        manager = get_project_container(project_name)
        success, message = await manager.stop()
        return AgentActionResponse(
            success=success,
            status=manager.status,
            message=message,
        )

    # Stop all containers in parallel
    async def stop_container(manager):
        return await manager.stop()

    results = await asyncio.gather(
        *[stop_container(m) for m in project_managers.values()],
        return_exceptions=True
    )

    # Count successes
    successes = sum(1 for r in results if isinstance(r, tuple) and r[0])
    total = len(project_managers)

    return AgentActionResponse(
        success=successes == total,
        status="stopped" if successes == total else "partial",
        message=f"Stopped {successes}/{total} containers",
    )


@router.post("/graceful-stop", response_model=AgentActionResponse)
async def graceful_stop_agent(project_name: str):
    """
    Request graceful shutdown of ALL agents for a project.

    Each agent will complete its current work before stopping.
    Falls back to force stop after 10 minutes.
    """
    from ..services.container_manager import _managers

    project_name = validate_project_name(project_name)

    # Get all managers for this project
    project_managers = _managers.get(project_name, {})
    if not project_managers:
        # Try single container mode fallback
        manager = get_project_container(project_name)
        success, message = await manager.graceful_stop()
        if success:
            await websocket_manager.broadcast_to_project(project_name, {
                "type": "graceful_stop_requested",
                "graceful_stop_requested": True,
            })
        return AgentActionResponse(
            success=success,
            status=manager.status,
            message=message,
        )

    # Request graceful stop for all containers
    async def graceful_stop_container(manager):
        return await manager.graceful_stop()

    results = await asyncio.gather(
        *[graceful_stop_container(m) for m in project_managers.values()],
        return_exceptions=True
    )

    # Count successes
    successes = sum(1 for r in results if isinstance(r, tuple) and r[0])
    total = len(project_managers)

    # Broadcast to WebSocket
    if successes > 0:
        await websocket_manager.broadcast_to_project(project_name, {
            "type": "graceful_stop_requested",
            "graceful_stop_requested": True,
        })

    return AgentActionResponse(
        success=successes == total,
        status="stopping" if successes > 0 else "error",
        message=f"Graceful stop requested for {successes}/{total} containers",
    )


@router.post("/instruction", response_model=AgentActionResponse)
async def send_instruction(project_name: str, request: AgentStartRequest):
    """
    Send an instruction to the running container.

    Container must already be running.
    """
    if not request.instruction:
        raise HTTPException(
            status_code=400,
            detail="instruction is required"
        )

    manager = get_project_container(project_name)

    if manager.status != "running":
        raise HTTPException(
            status_code=400,
            detail=f"Container is not running (status: {manager.status})"
        )

    success, message = await manager.send_instruction(request.instruction)

    return AgentActionResponse(
        success=success,
        status=manager.status,
        message=message,
    )


@router.delete("/container", response_model=AgentActionResponse)
async def remove_container(project_name: str):
    """Remove the container completely (for cleanup)."""
    manager = get_project_container(project_name)
    success, message = await manager.remove()

    return AgentActionResponse(
        success=success,
        status=manager.status,
        message=message,
    )


@router.post("/container/start", response_model=AgentActionResponse)
async def start_container_only(project_name: str):
    """
    Start the container without starting the agent.

    This is useful for editing tasks when you don't want to start
    the agent consuming API credits. The container will stay running
    until idle timeout (60 min).
    """
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

    manager = get_project_container(project_name)
    success, message = await manager.start_container_only()

    return AgentActionResponse(
        success=success,
        status=manager.status,
        message=message,
    )


# Legacy endpoints for backwards compatibility
@router.post("/pause", response_model=AgentActionResponse)
async def pause_agent(_project_name: str):
    """
    Pause endpoint (deprecated).

    Containers don't support pause - use stop instead.
    """
    raise HTTPException(
        status_code=400,
        detail="Pause is not supported for containers. Use stop instead."
    )


@router.post("/resume", response_model=AgentActionResponse)
async def resume_agent(_project_name: str):
    """
    Resume endpoint (deprecated).

    Use start to restart a stopped container.
    """
    raise HTTPException(
        status_code=400,
        detail="Resume is not supported for containers. Use start instead."
    )
