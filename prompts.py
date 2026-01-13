"""
Prompt Loading Utilities
========================

Functions for loading prompt templates with project-specific support.

Fallback chain:
1. Project-specific: {project_dir}/prompts/{name}.md
2. Base template: .claude/templates/{name}.template.md
"""

import os
import shutil
from pathlib import Path

# Base templates location (generic templates)
TEMPLATES_DIR = Path(__file__).parent / ".claude" / "templates"


def get_project_prompts_dir(project_dir: Path) -> Path:
    """Get the prompts directory for a specific project."""
    return project_dir / "prompts"


def load_prompt(name: str, project_dir: Path | None = None) -> str:
    """
    Load a prompt template with fallback chain.

    Fallback order:
    1. Project-specific: {project_dir}/prompts/{name}.md
    2. Base template: .claude/templates/{name}.template.md

    Args:
        name: The prompt name (without extension), e.g., "initializer_prompt"
        project_dir: Optional project directory for project-specific prompts

    Returns:
        The prompt content as a string

    Raises:
        FileNotFoundError: If prompt not found in any location
    """
    # 1. Try project-specific first
    if project_dir:
        project_prompts = get_project_prompts_dir(project_dir)
        project_path = project_prompts / f"{name}.md"
        if project_path.exists():
            try:
                return project_path.read_text(encoding="utf-8")
            except (OSError, PermissionError) as e:
                print(f"Warning: Could not read {project_path}: {e}")

    # 2. Try base template
    template_path = TEMPLATES_DIR / f"{name}.template.md"
    if template_path.exists():
        try:
            return template_path.read_text(encoding="utf-8")
        except (OSError, PermissionError) as e:
            print(f"Warning: Could not read {template_path}: {e}")

    raise FileNotFoundError(
        f"Prompt '{name}' not found in:\n"
        f"  - Project: {project_dir / 'prompts' if project_dir else 'N/A'}\n"
        f"  - Templates: {TEMPLATES_DIR}"
    )


def get_initializer_prompt(project_dir: Path | None = None) -> str:
    """Load the initializer prompt (project-specific if available)."""
    return load_prompt("initializer_prompt", project_dir)


def get_coding_prompt(project_dir: Path | None = None) -> str:
    """Load the coding agent prompt (project-specific if available)."""
    return load_prompt("coding_prompt", project_dir)


def get_coding_prompt_yolo(project_dir: Path | None = None) -> str:
    """Load the YOLO mode coding agent prompt (project-specific if available)."""
    return load_prompt("coding_prompt_yolo", project_dir)


def get_overseer_prompt(project_dir: Path | None = None) -> str:
    """Load the overseer agent prompt (project-specific if available)."""
    return load_prompt("overseer_prompt", project_dir)


def get_app_spec(project_dir: Path) -> str:
    """
    Load the app spec from the project.

    Checks in order:
    1. Project prompts directory: {project_dir}/prompts/app_spec.txt
    2. Project root (legacy): {project_dir}/app_spec.txt

    Args:
        project_dir: The project directory

    Returns:
        The app spec content

    Raises:
        FileNotFoundError: If no app_spec.txt found
    """
    # Try project prompts directory first
    project_prompts = get_project_prompts_dir(project_dir)
    spec_path = project_prompts / "app_spec.txt"
    if spec_path.exists():
        try:
            return spec_path.read_text(encoding="utf-8")
        except (OSError, PermissionError) as e:
            raise FileNotFoundError(f"Could not read {spec_path}: {e}") from e

    # Fallback to legacy location in project root
    legacy_spec = project_dir / "app_spec.txt"
    if legacy_spec.exists():
        try:
            return legacy_spec.read_text(encoding="utf-8")
        except (OSError, PermissionError) as e:
            raise FileNotFoundError(f"Could not read {legacy_spec}: {e}") from e

    raise FileNotFoundError(f"No app_spec.txt found for project: {project_dir}")


def scaffold_project_prompts(project_dir: Path) -> Path:
    """
    Create the project prompts directory and copy base templates.

    This sets up a new project with template files that can be customized.

    Args:
        project_dir: The absolute path to the project directory

    Returns:
        The path to the project prompts directory
    """
    project_prompts = get_project_prompts_dir(project_dir)
    project_prompts.mkdir(parents=True, exist_ok=True)

    # Define template mappings: (source_template, destination_name)
    templates = [
        ("app_spec.template.txt", "app_spec.txt"),
        ("coding_prompt.template.md", "coding_prompt.md"),
        ("coding_prompt_yolo.template.md", "coding_prompt_yolo.md"),
        ("initializer_prompt.template.md", "initializer_prompt.md"),
        ("overseer_prompt.template.md", "overseer_prompt.md"),
    ]

    copied_files = []
    for template_name, dest_name in templates:
        template_path = TEMPLATES_DIR / template_name
        dest_path = project_prompts / dest_name

        # Only copy if template exists and destination doesn't
        if template_path.exists() and not dest_path.exists():
            try:
                shutil.copy(template_path, dest_path)
                copied_files.append(dest_name)
            except (OSError, PermissionError) as e:
                print(f"  Warning: Could not copy {dest_name}: {e}")

    if copied_files:
        print(f"  Created prompt files: {', '.join(copied_files)}")

    # Copy CLAUDE.md template to project root (for beads workflow instructions)
    claude_template = TEMPLATES_DIR / "project_claude.md.template"
    claude_dest = project_dir / "CLAUDE.md"
    if claude_template.exists() and not claude_dest.exists():
        try:
            # Read template and substitute project name
            content = claude_template.read_text(encoding="utf-8")
            content = content.replace("{project_name}", project_dir.name)
            claude_dest.write_text(content, encoding="utf-8")
            print(f"  Created CLAUDE.md with beads workflow instructions")
        except (OSError, PermissionError) as e:
            print(f"  Warning: Could not create CLAUDE.md: {e}")

    # Ensure .claude/ is gitignored (credentials are sensitive)
    ensure_gitignore_claude(project_dir)

    return project_prompts


def ensure_gitignore_claude(project_dir: Path) -> None:
    """Ensure .claude/ is in project's .gitignore (credentials are sensitive)."""
    gitignore_path = project_dir / ".gitignore"
    claude_pattern = ".claude/"

    existing_lines = []
    if gitignore_path.exists():
        try:
            existing_lines = gitignore_path.read_text(encoding="utf-8").splitlines()
            if claude_pattern in existing_lines or ".claude" in existing_lines:
                return  # Already ignored
        except (OSError, PermissionError):
            pass

    try:
        with open(gitignore_path, "a", encoding="utf-8") as f:
            if existing_lines and existing_lines[-1]:
                f.write("\n")
            f.write(f"\n# Claude credentials\n{claude_pattern}\n")
    except (OSError, PermissionError) as e:
        print(f"  Warning: Could not update .gitignore: {e}")


def has_project_prompts(project_dir: Path) -> bool:
    """
    Check if a project has valid prompts set up.

    A project has valid prompts if:
    1. The prompts directory exists, AND
    2. app_spec.txt exists within it, AND
    3. app_spec.txt contains the <project_specification> tag

    Args:
        project_dir: The project directory to check

    Returns:
        True if valid project prompts exist, False otherwise
    """
    project_prompts = get_project_prompts_dir(project_dir)
    app_spec = project_prompts / "app_spec.txt"

    if not app_spec.exists():
        # Also check legacy location in project root
        legacy_spec = project_dir / "app_spec.txt"
        if legacy_spec.exists():
            try:
                content = legacy_spec.read_text(encoding="utf-8")
                return "<project_specification>" in content
            except (OSError, PermissionError):
                return False
        return False

    # Check for valid spec content
    try:
        content = app_spec.read_text(encoding="utf-8")
        return "<project_specification>" in content
    except (OSError, PermissionError):
        return False


def copy_spec_to_project(project_dir: Path) -> None:
    """
    Copy the app spec file into the project root directory for the agent to read.

    This maintains backwards compatibility - the agent expects app_spec.txt
    in the project root directory.

    The spec is sourced from: {project_dir}/prompts/app_spec.txt

    Args:
        project_dir: The project directory
    """
    spec_dest = project_dir / "app_spec.txt"

    # Don't overwrite if already exists
    if spec_dest.exists():
        return

    # Copy from project prompts directory
    project_prompts = get_project_prompts_dir(project_dir)
    project_spec = project_prompts / "app_spec.txt"
    if project_spec.exists():
        try:
            shutil.copy(project_spec, spec_dest)
            print("Copied app_spec.txt to project directory")
            return
        except (OSError, PermissionError) as e:
            print(f"Warning: Could not copy app_spec.txt: {e}")
            return

    print("Warning: No app_spec.txt found to copy to project directory")


# ============================================================================
# Existing Repo Support
# ============================================================================


def is_existing_repo_project(project_dir: Path) -> bool:
    """
    Check if this is an existing repo project (no valid app_spec).

    Existing repo projects:
    - Do NOT have prompts/app_spec.txt with <project_specification> tag
    - These skip the initializer and go directly to coding

    Returns:
        True if this is an existing repo (no app_spec), False if new project with spec
    """
    app_spec = project_dir / "prompts" / "app_spec.txt"
    if not app_spec.exists():
        return True

    try:
        content = app_spec.read_text(encoding="utf-8")
        return "<project_specification>" not in content
    except (OSError, PermissionError):
        return True


def refresh_project_prompts(project_dir: Path) -> list[str]:
    """
    Refresh agent prompts from base templates (overwrites existing).

    Called on container start to ensure latest templates are used.
    Does NOT touch app_spec.txt or CLAUDE.md (user content).

    For existing repos (no valid app_spec), uses the *_existing.template.md variants.

    Args:
        project_dir: The project directory

    Returns:
        List of updated file names
    """
    project_prompts = get_project_prompts_dir(project_dir)
    project_prompts.mkdir(parents=True, exist_ok=True)

    is_existing = is_existing_repo_project(project_dir)

    # Define template mappings based on project type
    if is_existing:
        # Existing repos use different template variants
        templates = [
            ("coding_prompt_existing.template.md", "coding_prompt.md"),
            ("overseer_prompt_existing.template.md", "overseer_prompt.md"),
        ]
    else:
        # New projects with app_spec
        templates = [
            ("coding_prompt.template.md", "coding_prompt.md"),
            ("coding_prompt_yolo.template.md", "coding_prompt_yolo.md"),
            ("initializer_prompt.template.md", "initializer_prompt.md"),
            ("overseer_prompt.template.md", "overseer_prompt.md"),
        ]

    updated_files = []
    for template_name, dest_name in templates:
        template_path = TEMPLATES_DIR / template_name
        dest_path = project_prompts / dest_name

        if not template_path.exists():
            print(f"  Warning: Template not found: {template_name}")
            continue

        try:
            shutil.copy(template_path, dest_path)
            updated_files.append(dest_name)
        except (OSError, PermissionError) as e:
            print(f"  Warning: Could not update {dest_name}: {e}")

    return updated_files


BEADS_WORKFLOW_MARKER = "## BEADS WORKFLOW"
BEADS_WORKFLOW_SECTION = """
## BEADS WORKFLOW

This project uses **beads** for issue tracking. Issues are stored in `.beads/`.

### Mandatory Commands
```
bd ready                              # Get next issue
bd update <id> --status=in_progress   # BEFORE coding
bd close <id>                         # After verification
bd sync                               # At session end
```

### Quick Reference
| Command | Description |
|---------|-------------|
| `bd ready` | List issues ready to work on |
| `bd show <id>` | View issue details |
| `bd update <id> --status=in_progress` | Claim an issue |
| `bd close <id>` | Mark complete |
| `bd stats` | Show progress |
"""


def scaffold_existing_repo(project_dir: Path) -> None:
    """
    Scaffold minimal files for an existing repository.

    PRESERVES:
    - Existing CLAUDE.md (appends beads section if missing)
    - Existing .claude/ folder (skills, MCP, commands, settings)

    ADDS:
    - prompts/coding_prompt.md (existing repo variant)
    - prompts/overseer_prompt.md (existing repo variant)
    - .gitignore entry for .claude/

    Args:
        project_dir: The project directory
    """
    # 1. Handle CLAUDE.md - preserve existing, append beads workflow if missing
    claude_md = project_dir / "CLAUDE.md"
    if claude_md.exists():
        try:
            content = claude_md.read_text(encoding="utf-8")
            if BEADS_WORKFLOW_MARKER not in content:
                # Append beads workflow section
                with open(claude_md, "a", encoding="utf-8") as f:
                    f.write("\n\n" + BEADS_WORKFLOW_SECTION)
                print("  Appended beads workflow to existing CLAUDE.md")
            else:
                print("  CLAUDE.md already has beads workflow")
        except (OSError, PermissionError) as e:
            print(f"  Warning: Could not update CLAUDE.md: {e}")
    else:
        # Create minimal CLAUDE.md with just beads workflow
        try:
            claude_md.write_text(
                f"# {project_dir.name}\n\n{BEADS_WORKFLOW_SECTION}",
                encoding="utf-8"
            )
            print("  Created CLAUDE.md with beads workflow")
        except (OSError, PermissionError) as e:
            print(f"  Warning: Could not create CLAUDE.md: {e}")

    # 2. Create prompts directory with existing-repo variants
    prompts_dir = get_project_prompts_dir(project_dir)
    prompts_dir.mkdir(parents=True, exist_ok=True)

    # Template mappings for existing repos
    templates = [
        ("coding_prompt_existing.template.md", "coding_prompt.md"),
        ("overseer_prompt_existing.template.md", "overseer_prompt.md"),
    ]

    for template_name, dest_name in templates:
        template_path = TEMPLATES_DIR / template_name
        dest_path = prompts_dir / dest_name

        # Only copy if template exists and destination doesn't
        if template_path.exists() and not dest_path.exists():
            try:
                shutil.copy(template_path, dest_path)
                print(f"  Created {dest_name}")
            except (OSError, PermissionError) as e:
                print(f"  Warning: Could not copy {dest_name}: {e}")

    # 3. Update .gitignore to exclude .claude/
    ensure_gitignore_claude(project_dir)
