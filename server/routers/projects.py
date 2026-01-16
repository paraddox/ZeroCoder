"""
Projects Router
===============

API endpoints for project management.
Uses project registry for path lookups instead of fixed generations/ directory.
"""

import re
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..schemas import (
    AddExistingRepoRequest,
    ContainerCountUpdate,
    ContainerStatus,
    ProjectCreate,
    ProjectDetail,
    ProjectPrompts,
    ProjectPromptsUpdate,
    ProjectSettingsUpdate,
    ProjectStats,
    ProjectSummary,
    TaskCreate,
    TaskUpdate,
    WizardStatus,
)
from ..services.local_project_manager import (
    LocalProjectManager,
    get_local_project_manager,
)

# Default model for coder/overseer agents
DEFAULT_AGENT_MODEL = "glm-4-7"
AGENT_CONFIG_FILENAME = ".agent_config.json"

# Lazy imports to avoid circular dependencies
_imports_initialized = False
_has_project_prompts = None
_scaffold_project_prompts = None
_get_project_prompts_dir = None
_count_passing_tests = None


def _init_imports():
    """Lazy import of project-level modules."""
    global _imports_initialized, _has_project_prompts
    global _scaffold_project_prompts, _get_project_prompts_dir
    global _count_passing_tests

    if _imports_initialized:
        return

    import sys
    root = Path(__file__).parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from progress import count_passing_tests
    from prompts import get_project_prompts_dir, has_project_prompts, scaffold_project_prompts

    _has_project_prompts = has_project_prompts
    _scaffold_project_prompts = scaffold_project_prompts
    _get_project_prompts_dir = get_project_prompts_dir
    _count_passing_tests = count_passing_tests
    _imports_initialized = True


def _get_registry_functions():
    """Get registry functions with lazy import."""
    import sys
    root = Path(__file__).parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from registry import (
        get_project_path,
        get_project_git_url,
        get_project_info,
        get_projects_dir,
        list_registered_projects,
        list_project_containers,
        register_project,
        unregister_project,
        validate_project_path,
        mark_project_initialized,
        update_target_container_count,
    )
    return (
        register_project,
        unregister_project,
        get_project_path,
        get_project_git_url,
        get_project_info,
        get_projects_dir,
        list_registered_projects,
        validate_project_path,
        mark_project_initialized,
        update_target_container_count,
        list_project_containers,
    )


router = APIRouter(prefix="/api/projects", tags=["projects"])


def validate_project_name(name: str) -> str:
    """Validate and sanitize project name to prevent path traversal."""
    if not re.match(r'^[a-zA-Z0-9_-]{1,50}$', name):
        raise HTTPException(
            status_code=400,
            detail="Invalid project name. Use only letters, numbers, hyphens, and underscores (1-50 chars)."
        )
    return name


def validate_task_id(task_id: str) -> str:
    """Validate task ID format (e.g., 'beads-123', 'feat-42')."""
    if not re.match(r'^[a-zA-Z]+-\d+$', task_id):
        raise HTTPException(status_code=400, detail=f"Invalid task ID format: {task_id}")
    return task_id


def get_project_stats(project_dir: Path) -> ProjectStats:
    """Get statistics for a project."""
    _init_imports()
    passing, in_progress, total = _count_passing_tests(project_dir)
    percentage = (passing / total * 100) if total > 0 else 0.0
    return ProjectStats(
        passing=passing,
        in_progress=in_progress,
        total=total,
        percentage=round(percentage, 1)
    )


def get_wizard_status_path(project_dir: Path) -> Path:
    """Get the path to the wizard status file."""
    return project_dir / "prompts" / ".wizard_status.json"


def check_wizard_incomplete(project_dir: Path, has_spec: bool) -> bool:
    """Check if a project has an incomplete wizard (status file exists but no spec)."""
    if has_spec:
        return False
    wizard_file = get_wizard_status_path(project_dir)
    return wizard_file.exists()


def get_agent_config_path(project_dir: Path) -> Path:
    """Get the path to the agent config file."""
    return project_dir / "prompts" / AGENT_CONFIG_FILENAME


def read_agent_model(project_dir: Path) -> str:
    """Read the agent model from project config file."""
    import json
    import logging
    logger = logging.getLogger(__name__)
    config_path = get_agent_config_path(project_dir)
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            return config.get("agent_model", DEFAULT_AGENT_MODEL)
        except Exception as e:
            logger.warning(f"Failed to read agent config for {project_dir.name}, using default: {e}")
    return DEFAULT_AGENT_MODEL


def write_agent_config(project_dir: Path, agent_model: str) -> None:
    """Write the agent model to project config file."""
    import json
    config_path = get_agent_config_path(project_dir)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing config if it exists
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Update the model
    config["agent_model"] = agent_model
    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def clone_repository(git_url: str, destination: Path) -> tuple[bool, str]:
    """
    Clone a git repository to the specified destination.

    Args:
        git_url: Git URL (https:// or git@)
        destination: Local path to clone to

    Returns:
        Tuple of (success, message)
    """
    if not (git_url.startswith('https://') or git_url.startswith('git@')):
        return False, "Invalid git URL. Must start with https:// or git@"

    try:
        result = subprocess.run(
            ['git', 'clone', git_url, str(destination)],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode != 0:
            return False, f"Git clone failed: {result.stderr}"

        return True, "Repository cloned successfully"
    except subprocess.TimeoutExpired:
        return False, "Git clone timed out after 5 minutes"
    except FileNotFoundError:
        return False, "Git is not installed or not in PATH"
    except Exception as e:
        return False, f"Git clone error: {str(e)}"


def init_beads_if_needed(project_dir: Path) -> tuple[bool, str]:
    """
    Initialize beads in the project directory if not already initialized.

    Args:
        project_dir: Project directory path

    Returns:
        Tuple of (success, message)
    """
    beads_config = project_dir / ".beads" / "config.yaml"

    if beads_config.exists():
        return True, "Beads already initialized"

    try:
        result = subprocess.run(
            ['bd', 'init', '--prefix', 'feat'],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return False, f"Beads init failed: {result.stderr}"

        return True, "Beads initialized successfully"
    except FileNotFoundError:
        return False, "beads CLI (bd) not found. Please install beads."
    except subprocess.TimeoutExpired:
        return False, "Beads init timed out"
    except Exception as e:
        return False, f"Beads init error: {str(e)}"


@router.get("", response_model=list[ProjectSummary])
async def list_projects():
    """List all registered projects."""
    _init_imports()
    (
        _, _, _, _, _, _,
        list_registered_projects, validate_project_path, _, _, _
    ) = _get_registry_functions()

    # Import get_project_container for agent status
    from .agent import get_project_container

    projects = list_registered_projects()
    result = []

    for name, info in projects.items():
        local_path = Path(info["local_path"])

        # Skip if local clone doesn't exist
        if not local_path.exists():
            continue

        has_spec = _has_project_prompts(local_path)
        stats = get_project_stats(local_path)
        wizard_incomplete = check_wizard_incomplete(local_path, has_spec)

        # Get agent status for this project
        agent_status = None
        agent_running = None
        try:
            manager = get_project_container(name)
            status_dict = manager.get_status_dict()
            agent_status = status_dict["status"]
            agent_running = status_dict.get("agent_running", False)
        except Exception:
            # If container manager not found or error, leave as None
            pass

        # Get agent model from config
        agent_model = read_agent_model(local_path)

        result.append(ProjectSummary(
            name=name,
            git_url=info["git_url"],
            local_path=info["local_path"],
            is_new=info["is_new"],
            has_spec=has_spec,
            wizard_incomplete=wizard_incomplete,
            stats=stats,
            target_container_count=info["target_container_count"],
            agent_status=agent_status,
            agent_running=agent_running,
            agent_model=agent_model,
        ))

    return result


@router.post("", response_model=ProjectSummary)
async def create_project(project: ProjectCreate):
    """Create a new project by cloning a git repository."""
    _init_imports()
    (
        register_project, _, get_project_path, _, _, get_projects_dir,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(project.name)
    local_path = get_projects_dir() / name

    # Check if project name already registered
    existing = get_project_path(name)
    if existing and existing.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Project '{name}' already exists"
        )

    # Clone the repository
    if not local_path.exists():
        success, msg = clone_repository(project.git_url, local_path)
        if not success:
            raise HTTPException(status_code=500, detail=msg)

    # Scaffold prompts
    _scaffold_project_prompts(local_path)

    # Register in registry
    try:
        register_project(name, project.git_url, is_new=project.is_new)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to register project: {e}"
        )

    return ProjectSummary(
        name=name,
        git_url=project.git_url,
        local_path=local_path.as_posix(),
        is_new=project.is_new,
        has_spec=False,
        stats=ProjectStats(passing=0, total=0, percentage=0.0),
        target_container_count=1,
    )


@router.get("/{name}", response_model=ProjectDetail)
async def get_project(name: str):
    """Get detailed information about a project."""
    _init_imports()
    (
        _, _, get_project_path, _, get_project_info, _,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(name)
    info = get_project_info(name)

    if not info:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found in registry")

    local_path = Path(info["local_path"])
    if not local_path.exists():
        raise HTTPException(status_code=404, detail=f"Project directory no longer exists: {local_path}")

    has_spec = _has_project_prompts(local_path)
    stats = get_project_stats(local_path)
    prompts_dir = _get_project_prompts_dir(local_path)
    agent_model = read_agent_model(local_path)

    return ProjectDetail(
        name=name,
        git_url=info["git_url"],
        local_path=info["local_path"],
        is_new=info["is_new"],
        has_spec=has_spec,
        stats=stats,
        prompts_dir=str(prompts_dir),
        target_container_count=info["target_container_count"],
        agent_model=agent_model,
    )


@router.delete("/{name}")
async def delete_project(name: str, delete_files: bool = False):
    """
    Delete a project from the registry.

    Args:
        name: Project name to delete
        delete_files: If True, also delete the project directory and files
    """
    _init_imports()
    (
        _, unregister_project, get_project_path, _, _, _,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(name)
    project_dir = get_project_path(name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    # Check if agent is running
    lock_file = project_dir / ".agent.lock"
    if lock_file.exists():
        raise HTTPException(
            status_code=409,
            detail="Cannot delete project while agent is running. Stop the agent first."
        )

    # Optionally delete files
    if delete_files and project_dir.exists():
        try:
            shutil.rmtree(project_dir)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete project files: {e}")

    # Clear cached container manager to avoid stale state
    from ..services.container_manager import clear_container_manager
    clear_container_manager(name)

    # Unregister from registry
    unregister_project(name)

    return {
        "success": True,
        "message": f"Project '{name}' deleted" + (" (files removed)" if delete_files else " (files preserved)")
    }


@router.get("/{name}/prompts", response_model=ProjectPrompts)
async def get_project_prompts(name: str):
    """Get the content of project prompt files."""
    _init_imports()
    (
        _, _, get_project_path, _, _, _,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(name)
    project_dir = get_project_path(name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    prompts_dir = _get_project_prompts_dir(project_dir)

    def read_file(filename: str) -> str:
        filepath = prompts_dir / filename
        if filepath.exists():
            try:
                return filepath.read_text(encoding="utf-8")
            except Exception:
                return ""
        return ""

    return ProjectPrompts(
        app_spec=read_file("app_spec.txt"),
        initializer_prompt=read_file("initializer_prompt.md"),
        coding_prompt=read_file("coding_prompt.md"),
    )


@router.put("/{name}/prompts")
async def update_project_prompts(name: str, prompts: ProjectPromptsUpdate):
    """Update project prompt files."""
    _init_imports()
    (
        _, _, get_project_path, _, _, _,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(name)
    project_dir = get_project_path(name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    prompts_dir = _get_project_prompts_dir(project_dir)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    def write_file(filename: str, content: str | None):
        if content is not None:
            filepath = prompts_dir / filename
            filepath.write_text(content, encoding="utf-8")

    write_file("app_spec.txt", prompts.app_spec)
    write_file("initializer_prompt.md", prompts.initializer_prompt)
    write_file("coding_prompt.md", prompts.coding_prompt)

    return {"success": True, "message": "Prompts updated"}


@router.get("/{name}/stats", response_model=ProjectStats)
async def get_project_stats_endpoint(name: str):
    """Get current progress statistics for a project."""
    _init_imports()
    (
        _, _, get_project_path, _, _, _,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(name)
    project_dir = get_project_path(name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    return get_project_stats(project_dir)


@router.get("/{name}/wizard-status", response_model=WizardStatus | None)
async def get_wizard_status(name: str):
    """Get the wizard status for a project, if it exists."""
    import json
    (
        _, _, get_project_path, _, _, _,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(name)
    project_dir = get_project_path(name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    wizard_file = get_wizard_status_path(project_dir)
    if not wizard_file.exists():
        return None

    try:
        data = json.loads(wizard_file.read_text(encoding="utf-8"))
        return WizardStatus(**data)
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=f"Invalid wizard status file: {e}")


@router.put("/{name}/wizard-status", response_model=WizardStatus)
async def update_wizard_status(name: str, status: WizardStatus):
    """Create or update the wizard status for a project."""
    import json
    (
        _, _, get_project_path, _, _, _,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(name)
    project_dir = get_project_path(name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    wizard_file = get_wizard_status_path(project_dir)
    wizard_file.parent.mkdir(parents=True, exist_ok=True)

    wizard_file.write_text(
        json.dumps(status.model_dump(), default=str, indent=2),
        encoding="utf-8"
    )

    return status


@router.delete("/{name}/wizard-status")
async def delete_wizard_status(name: str):
    """Delete the wizard status for a project (called on wizard completion)."""
    (
        _, _, get_project_path, _, _, _,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(name)
    project_dir = get_project_path(name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    wizard_file = get_wizard_status_path(project_dir)
    if wizard_file.exists():
        wizard_file.unlink()

    return {"success": True, "message": "Wizard status cleared"}


# ============================================================================
# Project Settings (Agent Model)
# ============================================================================

@router.patch("/{name}/settings")
async def update_project_settings(name: str, settings: ProjectSettingsUpdate):
    """Update project settings (agent model, etc.)."""
    (
        _, _, get_project_path, _, _, _,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(name)
    project_dir = get_project_path(name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    # Validate the model ID
    valid_models = ["claude-opus-4-5-20251101", "claude-sonnet-4-5-20250514", "glm-4-7"]
    if settings.agent_model not in valid_models:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model. Must be one of: {', '.join(valid_models)}"
        )

    # Write the config
    write_agent_config(project_dir, settings.agent_model)

    return {
        "success": True,
        "message": f"Agent model set to {settings.agent_model}",
        "agent_model": settings.agent_model
    }


@router.get("/{name}/settings")
async def get_project_settings(name: str):
    """Get project settings (agent model, etc.)."""
    (
        _, _, get_project_path, _, _, _,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(name)
    project_dir = get_project_path(name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    agent_model = read_agent_model(project_dir)

    return {
        "agent_model": agent_model
    }


# ============================================================================
# Add Existing Repo
# ============================================================================

@router.post("/add-existing", response_model=ProjectSummary)
async def add_existing_repo(request: AddExistingRepoRequest):
    """
    Add an existing repository to the project registry.

    - Clone the repository to ~/.zerocoder/projects/{name}/
    - Check if .beads/ exists; if not, initialize beads
    - Scaffold minimal prompt files (preserving existing CLAUDE.md and .claude/)
    - Register in the project registry with is_new=False (no wizard)
    """
    _init_imports()
    (
        register_project, _, get_project_path, _, _, get_projects_dir,
        _, _, _, _, _
    ) = _get_registry_functions()

    # Import scaffold function for existing repos
    import sys
    root = Path(__file__).parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from prompts import scaffold_existing_repo

    name = validate_project_name(request.name)
    local_path = get_projects_dir() / name

    # Check if project name already registered
    existing = get_project_path(name)
    if existing and existing.exists():
        raise HTTPException(
            status_code=409,
            detail=f"Project '{name}' already exists"
        )

    # Clone the repository
    if not local_path.exists():
        success, msg = clone_repository(request.git_url, local_path)
        if not success:
            raise HTTPException(status_code=500, detail=msg)

    # Initialize beads if needed
    success, msg = init_beads_if_needed(local_path)
    if not success:
        raise HTTPException(status_code=500, detail=msg)

    # Scaffold minimal prompts (preserving existing files)
    scaffold_existing_repo(local_path)

    # Register with is_new=False (existing project, no wizard)
    try:
        register_project(name, request.git_url, is_new=False)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to register project: {e}"
        )

    # Get stats (beads should be initialized now)
    stats = get_project_stats(local_path)

    return ProjectSummary(
        name=name,
        git_url=request.git_url,
        local_path=local_path.as_posix(),
        is_new=False,
        has_spec=False,  # Existing repos don't have app_spec
        wizard_incomplete=False,
        stats=stats,
        target_container_count=1,
    )


# ============================================================================
# Container Count Management
# ============================================================================

@router.put("/{name}/containers/count")
async def update_container_count(name: str, body: ContainerCountUpdate):
    """Update target container count for a project."""
    (
        _, _, get_project_path, _, _, _,
        _, _, _, update_target_container_count, _
    ) = _get_registry_functions()

    name = validate_project_name(name)

    if not get_project_path(name):
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    success = update_target_container_count(name, body.target_count)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update container count")

    return {"success": True, "target_count": body.target_count}


def _get_docker_container_status(container_name: str) -> str | None:
    """Get live status from Docker for a container."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Status}}", container_name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            docker_status = result.stdout.strip()
            if docker_status == "running":
                return "running"
            else:
                return "stopped"
        return None  # Container doesn't exist
    except Exception:
        return None


@router.get("/{name}/containers", response_model=list[ContainerStatus])
async def list_containers(name: str):
    """List all containers for a project."""
    from ..services.container_manager import get_all_container_managers

    (
        _, _, get_project_path, _, _, _,
        _, _, _, _, list_project_containers
    ) = _get_registry_functions()

    name = validate_project_name(name)

    if not get_project_path(name):
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    containers = list_project_containers(name)

    # Build a map of container managers for agent info
    managers = get_all_container_managers(name)
    manager_map = {cm.container_number: cm for cm in managers}

    result = []
    seen_container_nums = set()

    for c in containers:
        container_number = c["container_number"]
        # Skip invalid container numbers (e.g., -1 for hound - shouldn't be in DB)
        if container_number < 0:
            continue
        seen_container_nums.add(container_number)
        # Construct Docker container name from project and container number
        container_type = c.get("container_type", "coding")
        if container_type == "init" or container_number == 0:
            docker_name = f"zerocoder-{name}-init"
        else:
            docker_name = f"zerocoder-{name}-{container_number}"

        # Get live status from Docker
        live_status = _get_docker_container_status(docker_name)

        # Use live status if available
        db_status = c["status"]
        if live_status is not None:
            final_status = live_status
        elif db_status == "running":
            # Container doesn't exist in Docker but DB says running - it's stopped
            final_status = "stopped"
        else:
            # Keep database status (created, stopping, stopped)
            final_status = db_status

        # Get agent info from container manager
        cm = manager_map.get(container_number)
        agent_type = None
        sdk_type = None
        if cm:
            agent_type = cm._current_agent_type
            sdk_type = "claude" if cm._force_claude_sdk or not cm._is_opencode_model() else "opencode"

        result.append(ContainerStatus(
            id=c["id"],
            container_number=c["container_number"],
            container_type=c["container_type"],
            status=final_status,
            current_feature=c.get("current_feature"),
            docker_container_id=c.get("docker_container_id"),
            agent_type=agent_type,
            sdk_type=sdk_type,
        ))

    # Add any managers not in registry (e.g., hound containers with container_number=-1)
    seen_hound = False
    for cm in managers:
        # Skip if already added from database
        if cm.container_number in seen_container_nums:
            continue

        # Handle hound containers (container_number=-1)
        if cm.container_number < 0:
            # Only show hound containers (skip other invalid container numbers)
            if cm._current_agent_type != "hound":
                continue
            # Prevent duplicate hound entries
            if seen_hound:
                continue
            seen_hound = True
            docker_name = f"zerocoder-{name}-hound"
        else:
            docker_name = f"zerocoder-{name}-{cm.container_number}"

        live_status = _get_docker_container_status(docker_name)
        final_status = live_status if live_status else "stopped"

        result.append(ContainerStatus(
            id=-1,  # Synthetic ID for in-memory only containers
            container_number=cm.container_number,
            container_type=cm.container_type,
            status=final_status,
            current_feature=cm._current_feature,
            docker_container_id=None,
            agent_type=cm._current_agent_type,
            sdk_type="claude" if cm._force_claude_sdk or not cm._is_opencode_model() else "opencode",
        ))

    return result


@router.post("/{name}/stop")
async def stop_all_containers(name: str, graceful: bool = True):
    """
    Stop the container for a project.

    Args:
        name: Project name
        graceful: If True, request graceful shutdown; if False, force stop
    """
    from .agent import get_project_container

    (
        _, _, get_project_path, _, _, _,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(name)

    if not get_project_path(name):
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    try:
        manager = get_project_container(name)
    except HTTPException as e:
        if e.status_code == 404:
            return {"success": True, "message": "No container to stop", "stopped": 0}
        raise

    try:
        if graceful:
            success, message = await manager.graceful_stop()
        else:
            success, message = await manager.stop()

        if success:
            return {
                "success": True,
                "message": f"Stopped container {manager.container_name}",
                "stopped": 1,
            }
        else:
            return {
                "success": False,
                "message": f"Failed to stop container: {message}",
                "stopped": 0,
                "errors": [message],
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Error stopping container: {str(e)}",
            "stopped": 0,
            "errors": [str(e)],
        }


# ============================================================================
# Edit Mode Endpoints
# ============================================================================

# Track projects in edit mode (in-memory for simplicity)
_edit_mode_projects: set[str] = set()


@router.post("/{name}/edit/start")
async def start_edit_mode(name: str):
    """
    Enter edit mode for a project.

    Edit mode allows creating, updating, and deleting tasks without
    running agents. Fails if any agents are currently running.
    """
    from .agent import get_project_container

    (
        _, _, get_project_path, get_project_git_url, _, _,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(name)
    project_dir = get_project_path(name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    # Check if agents are running
    try:
        manager = get_project_container(name)
        status_dict = manager.get_status_dict()
        if status_dict.get("agent_running", False):
            raise HTTPException(
                status_code=409,
                detail="Cannot enter edit mode while agents are running. Stop agents first."
            )
    except HTTPException:
        raise
    except Exception:
        # Container doesn't exist yet, which is fine
        pass

    # Check if already in edit mode
    if name in _edit_mode_projects:
        return {"success": True, "message": "Already in edit mode", "edit_mode": True}

    # Get git URL for LocalProjectManager
    git_url = get_project_git_url(name)
    if not git_url:
        raise HTTPException(status_code=500, detail="Project has no git URL configured")

    # Pull latest and sync beads
    project_manager = get_local_project_manager(name, git_url)
    success, message = await project_manager.pull_latest()
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to pull latest: {message}")

    success, message = await project_manager.sync_beads()
    if not success:
        # Sync failure is not fatal - beads might not be initialized
        pass

    _edit_mode_projects.add(name)

    return {"success": True, "message": "Edit mode started", "edit_mode": True}


@router.post("/{name}/edit/save")
async def save_and_exit_edit_mode(name: str, commit_message: str = "Update tasks"):
    """
    Save changes and exit edit mode.

    Commits all changes and pushes to remote.
    """
    (
        _, _, get_project_path, get_project_git_url, _, _,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(name)

    if not get_project_path(name):
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    if name not in _edit_mode_projects:
        raise HTTPException(status_code=400, detail="Project is not in edit mode")

    git_url = get_project_git_url(name)
    if not git_url:
        raise HTTPException(status_code=500, detail="Project has no git URL configured")

    # Push changes
    project_manager = get_local_project_manager(name, git_url)
    success, message = await project_manager.push_changes(commit_message)

    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to save changes: {message}")

    _edit_mode_projects.discard(name)

    return {"success": True, "message": "Changes saved and edit mode exited", "edit_mode": False}


@router.post("/{name}/tasks")
async def create_task(name: str, task: TaskCreate):
    """
    Create a new task for a project.

    Project must be in edit mode.
    """
    (
        _, _, get_project_path, get_project_git_url, _, _,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(name)

    if not get_project_path(name):
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    if name not in _edit_mode_projects:
        raise HTTPException(
            status_code=400,
            detail="Project must be in edit mode to create tasks. Call POST /{name}/edit/start first."
        )

    git_url = get_project_git_url(name)
    if not git_url:
        raise HTTPException(status_code=500, detail="Project has no git URL configured")

    project_manager = get_local_project_manager(name, git_url)
    success, message, task_id = await project_manager.create_task(
        title=task.title,
        description=task.description,
        priority=task.priority,
        task_type=task.task_type,
    )

    if not success:
        raise HTTPException(status_code=500, detail=message)

    return {"success": True, "message": message, "task_id": task_id}


@router.patch("/{name}/tasks/{task_id}")
async def update_task(name: str, task_id: str, task: TaskUpdate):
    """
    Update an existing task.

    Project must be in edit mode.
    """
    (
        _, _, get_project_path, get_project_git_url, _, _,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(name)
    task_id = validate_task_id(task_id)

    if not get_project_path(name):
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    if name not in _edit_mode_projects:
        raise HTTPException(
            status_code=400,
            detail="Project must be in edit mode to update tasks. Call POST /{name}/edit/start first."
        )

    git_url = get_project_git_url(name)
    if not git_url:
        raise HTTPException(status_code=500, detail="Project has no git URL configured")

    project_manager = get_local_project_manager(name, git_url)
    success, message = await project_manager.update_task(
        task_id=task_id,
        status=task.status,
        priority=task.priority,
        title=task.title,
    )

    if not success:
        raise HTTPException(status_code=500, detail=message)

    return {"success": True, "message": message}


@router.delete("/{name}/tasks/{task_id}")
async def delete_task(name: str, task_id: str):
    """
    Delete a task.

    Project must be in edit mode.
    """
    (
        _, _, get_project_path, get_project_git_url, _, _,
        _, _, _, _, _
    ) = _get_registry_functions()

    name = validate_project_name(name)
    task_id = validate_task_id(task_id)

    if not get_project_path(name):
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    if name not in _edit_mode_projects:
        raise HTTPException(
            status_code=400,
            detail="Project must be in edit mode to delete tasks. Call POST /{name}/edit/start first."
        )

    git_url = get_project_git_url(name)
    if not git_url:
        raise HTTPException(status_code=500, detail="Project has no git URL configured")

    project_manager = get_local_project_manager(name, git_url)
    success, message = await project_manager.delete_task(task_id)

    if not success:
        raise HTTPException(status_code=500, detail=message)

    return {"success": True, "message": message}
