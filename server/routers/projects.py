"""
Projects Router
===============

API endpoints for project management.
Uses project registry for path lookups instead of fixed generations/ directory.
"""

import re
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..schemas import (
    AddExistingRepoRequest,
    ProjectCreate,
    ProjectDetail,
    ProjectPrompts,
    ProjectPromptsUpdate,
    ProjectSettingsUpdate,
    ProjectStats,
    ProjectSummary,
    WizardStatus,
)

# Default model for coder/overseer agents
DEFAULT_AGENT_MODEL = "claude-sonnet-4-5-20250514"
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
        list_registered_projects,
        register_project,
        unregister_project,
        validate_project_path,
    )
    return register_project, unregister_project, get_project_path, list_registered_projects, validate_project_path


router = APIRouter(prefix="/api/projects", tags=["projects"])


def validate_project_name(name: str) -> str:
    """Validate and sanitize project name to prevent path traversal."""
    if not re.match(r'^[a-zA-Z0-9_-]{1,50}$', name):
        raise HTTPException(
            status_code=400,
            detail="Invalid project name. Use only letters, numbers, hyphens, and underscores (1-50 chars)."
        )
    return name


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
    config_path = get_agent_config_path(project_dir)
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            return config.get("agent_model", DEFAULT_AGENT_MODEL)
        except Exception:
            pass
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


@router.get("", response_model=list[ProjectSummary])
async def list_projects():
    """List all registered projects."""
    _init_imports()
    _, _, _, list_registered_projects, validate_project_path = _get_registry_functions()

    # Import get_project_container for agent status
    from .agent import get_project_container

    projects = list_registered_projects()
    result = []

    for name, info in projects.items():
        project_dir = Path(info["path"])

        # Skip if path no longer exists
        is_valid, _ = validate_project_path(project_dir)
        if not is_valid:
            continue

        has_spec = _has_project_prompts(project_dir)
        stats = get_project_stats(project_dir)
        wizard_incomplete = check_wizard_incomplete(project_dir, has_spec)

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
        agent_model = read_agent_model(project_dir)

        result.append(ProjectSummary(
            name=name,
            path=info["path"],
            has_spec=has_spec,
            wizard_incomplete=wizard_incomplete,
            stats=stats,
            agent_status=agent_status,
            agent_running=agent_running,
            agent_model=agent_model,
        ))

    return result


@router.post("", response_model=ProjectSummary)
async def create_project(project: ProjectCreate):
    """Create a new project at the specified path."""
    _init_imports()
    register_project, _, get_project_path, _, _ = _get_registry_functions()

    name = validate_project_name(project.name)
    project_path = Path(project.path).resolve()

    # Check if project name already registered
    existing = get_project_path(name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Project '{name}' already exists at {existing}"
        )

    # Security: Check if path is in a blocked location
    from .filesystem import is_path_blocked
    if is_path_blocked(project_path):
        raise HTTPException(
            status_code=403,
            detail="Cannot create project in system or sensitive directory"
        )

    # Validate the path is usable
    if project_path.exists():
        if not project_path.is_dir():
            raise HTTPException(
                status_code=400,
                detail="Path exists but is not a directory"
            )
    else:
        # Create the directory
        try:
            project_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create directory: {e}"
            )

    # Scaffold prompts
    _scaffold_project_prompts(project_path)

    # Register in registry
    try:
        register_project(name, project_path)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to register project: {e}"
        )

    return ProjectSummary(
        name=name,
        path=project_path.as_posix(),
        has_spec=False,  # Just created, no spec yet
        stats=ProjectStats(passing=0, total=0, percentage=0.0),
    )


@router.get("/{name}", response_model=ProjectDetail)
async def get_project(name: str):
    """Get detailed information about a project."""
    _init_imports()
    _, _, get_project_path, _, _ = _get_registry_functions()

    name = validate_project_name(name)
    project_dir = get_project_path(name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found in registry")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail=f"Project directory no longer exists: {project_dir}")

    has_spec = _has_project_prompts(project_dir)
    stats = get_project_stats(project_dir)
    prompts_dir = _get_project_prompts_dir(project_dir)
    agent_model = read_agent_model(project_dir)

    return ProjectDetail(
        name=name,
        path=project_dir.as_posix(),
        has_spec=has_spec,
        stats=stats,
        prompts_dir=str(prompts_dir),
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
    _, unregister_project, get_project_path, _, _ = _get_registry_functions()

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
    _, _, get_project_path, _, _ = _get_registry_functions()

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
    _, _, get_project_path, _, _ = _get_registry_functions()

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
    _, _, get_project_path, _, _ = _get_registry_functions()

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
    _, _, get_project_path, _, _ = _get_registry_functions()

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
    _, _, get_project_path, _, _ = _get_registry_functions()

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
    _, _, get_project_path, _, _ = _get_registry_functions()

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
    _, _, get_project_path, _, _ = _get_registry_functions()

    name = validate_project_name(name)
    project_dir = get_project_path(name)

    if not project_dir:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project directory not found")

    # Validate the model ID
    valid_models = ["claude-opus-4-5-20251101", "claude-sonnet-4-5-20250514"]
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
    _, _, get_project_path, _, _ = _get_registry_functions()

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

import subprocess


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


@router.post("/add-existing", response_model=ProjectSummary)
async def add_existing_repo(request: AddExistingRepoRequest):
    """
    Add an existing repository to the project registry.

    - If source_type is git_url: Clone the repository to the specified path
    - If source_type is local_folder: Use the existing folder directly
    - Check if .beads/ exists; if not, initialize beads
    - Scaffold minimal prompt files (preserving existing CLAUDE.md and .claude/)
    - Register in the project registry
    """
    _init_imports()
    register_project, _, get_project_path, _, _ = _get_registry_functions()

    # Import scaffold function for existing repos
    import sys
    root = Path(__file__).parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from prompts import scaffold_existing_repo

    name = validate_project_name(request.name)
    project_path = Path(request.path).resolve()

    # Check if project name already registered
    existing = get_project_path(name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Project '{name}' already exists at {existing}"
        )

    # Security: Check if path is in a blocked location
    from .filesystem import is_path_blocked
    if is_path_blocked(project_path):
        raise HTTPException(
            status_code=403,
            detail="Cannot add project in system or sensitive directory"
        )

    # Handle based on source type
    if request.source_type == "git_url":
        # Clone repository
        if project_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Destination already exists: {project_path}"
            )

        success, msg = clone_repository(request.git_url, project_path)
        if not success:
            raise HTTPException(status_code=500, detail=msg)
    else:
        # Local folder - must exist
        if not project_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"Folder does not exist: {project_path}"
            )
        if not project_path.is_dir():
            raise HTTPException(
                status_code=400,
                detail=f"Path is not a directory: {project_path}"
            )

    # Initialize beads if needed
    success, msg = init_beads_if_needed(project_path)
    if not success:
        raise HTTPException(status_code=500, detail=msg)

    # Scaffold minimal prompts (preserving existing files)
    scaffold_existing_repo(project_path)

    # Register in registry
    try:
        register_project(name, project_path)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to register project: {e}"
        )

    # Get stats (beads should be initialized now)
    stats = get_project_stats(project_path)

    return ProjectSummary(
        name=name,
        path=project_path.as_posix(),
        has_spec=False,  # Existing repos don't have app_spec
        wizard_incomplete=False,
        stats=stats,
    )
