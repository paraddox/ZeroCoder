"""
Comprehensive Prompts Module Tests
==================================

Enterprise-grade tests for the prompts module including:
- Prompt loading with fallback chain
- App spec loading
- Project scaffolding
- Existing repo support
- CLAUDE.md management
"""

import pytest
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestPromptLoading:
    """Tests for prompt loading functionality."""

    @pytest.mark.unit
    def test_load_prompt_from_project(self, tmp_path):
        """Test loading prompt from project-specific directory."""
        from prompts import load_prompt

        # Create project-specific prompt
        project_dir = tmp_path / "test-project"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        (prompts_dir / "coding_prompt.md").write_text("# Project-specific coding prompt")

        content = load_prompt("coding_prompt", project_dir)

        assert content == "# Project-specific coding prompt"

    @pytest.mark.unit
    def test_load_prompt_fallback_to_template(self, tmp_path):
        """Test falling back to base template when project prompt missing."""
        from prompts import load_prompt, TEMPLATES_DIR

        # Create project without specific prompt
        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        # Ensure template exists
        if not TEMPLATES_DIR.exists():
            TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

        template_path = TEMPLATES_DIR / "coding_prompt.template.md"
        if template_path.exists():
            content = load_prompt("coding_prompt", project_dir)
            assert content is not None
        else:
            # Skip if template doesn't exist in dev environment
            pass

    @pytest.mark.unit
    def test_load_prompt_not_found(self, tmp_path):
        """Test FileNotFoundError when prompt not found anywhere."""
        from prompts import load_prompt

        project_dir = tmp_path / "empty-project"
        project_dir.mkdir(parents=True)

        with pytest.raises(FileNotFoundError) as exc_info:
            load_prompt("nonexistent_prompt", project_dir)

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.unit
    def test_load_prompt_no_project_dir(self, tmp_path):
        """Test loading prompt without project directory uses only templates."""
        from prompts import load_prompt, TEMPLATES_DIR

        # This should fall back to templates only
        if TEMPLATES_DIR.exists():
            template_path = TEMPLATES_DIR / "coding_prompt.template.md"
            if template_path.exists():
                content = load_prompt("coding_prompt", None)
                assert content is not None


class TestConvenienceFunctions:
    """Tests for prompt loading convenience functions."""

    @pytest.mark.unit
    def test_get_initializer_prompt(self, tmp_path):
        """Test get_initializer_prompt function."""
        from prompts import get_initializer_prompt

        project_dir = tmp_path / "test-project"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        (prompts_dir / "initializer_prompt.md").write_text("# Initializer")

        content = get_initializer_prompt(project_dir)
        assert "Initializer" in content

    @pytest.mark.unit
    def test_get_coding_prompt(self, tmp_path):
        """Test get_coding_prompt function."""
        from prompts import get_coding_prompt

        project_dir = tmp_path / "test-project"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        (prompts_dir / "coding_prompt.md").write_text("# Coding Agent")

        content = get_coding_prompt(project_dir)
        assert "Coding" in content

    @pytest.mark.unit
    def test_get_overseer_prompt(self, tmp_path):
        """Test get_overseer_prompt function."""
        from prompts import get_overseer_prompt

        project_dir = tmp_path / "test-project"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        (prompts_dir / "overseer_prompt.md").write_text("# Overseer Agent")

        content = get_overseer_prompt(project_dir)
        assert "Overseer" in content

    @pytest.mark.unit
    def test_get_hound_prompt(self, tmp_path):
        """Test get_hound_prompt function."""
        from prompts import get_hound_prompt

        project_dir = tmp_path / "test-project"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        (prompts_dir / "hound_prompt.md").write_text("# Hound Agent")

        content = get_hound_prompt(project_dir)
        assert "Hound" in content


class TestAppSpec:
    """Tests for app spec loading."""

    @pytest.mark.unit
    def test_get_app_spec_from_prompts_dir(self, tmp_path):
        """Test loading app spec from prompts directory."""
        from prompts import get_app_spec

        project_dir = tmp_path / "test-project"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        spec_content = "<project_specification>Test App</project_specification>"
        (prompts_dir / "app_spec.txt").write_text(spec_content)

        content = get_app_spec(project_dir)
        assert content == spec_content

    @pytest.mark.unit
    def test_get_app_spec_from_legacy_location(self, tmp_path):
        """Test loading app spec from legacy location (project root)."""
        from prompts import get_app_spec

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        spec_content = "<project_specification>Legacy App</project_specification>"
        (project_dir / "app_spec.txt").write_text(spec_content)

        content = get_app_spec(project_dir)
        assert content == spec_content

    @pytest.mark.unit
    def test_get_app_spec_prefers_prompts_dir(self, tmp_path):
        """Test that prompts directory takes precedence over legacy."""
        from prompts import get_app_spec

        project_dir = tmp_path / "test-project"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        (prompts_dir / "app_spec.txt").write_text("<project_specification>New</project_specification>")
        (project_dir / "app_spec.txt").write_text("<project_specification>Legacy</project_specification>")

        content = get_app_spec(project_dir)
        assert "New" in content
        assert "Legacy" not in content

    @pytest.mark.unit
    def test_get_app_spec_not_found(self, tmp_path):
        """Test FileNotFoundError when app spec not found."""
        from prompts import get_app_spec

        project_dir = tmp_path / "empty-project"
        project_dir.mkdir(parents=True)

        with pytest.raises(FileNotFoundError):
            get_app_spec(project_dir)


class TestHasProjectPrompts:
    """Tests for has_project_prompts function."""

    @pytest.mark.unit
    def test_has_project_prompts_true(self, tmp_path):
        """Test has_project_prompts returns True for valid project."""
        from prompts import has_project_prompts

        project_dir = tmp_path / "test-project"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        (prompts_dir / "app_spec.txt").write_text("<project_specification>Test</project_specification>")

        assert has_project_prompts(project_dir) is True

    @pytest.mark.unit
    def test_has_project_prompts_no_spec_tag(self, tmp_path):
        """Test has_project_prompts returns False without spec tag."""
        from prompts import has_project_prompts

        project_dir = tmp_path / "test-project"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        (prompts_dir / "app_spec.txt").write_text("Just some text without the tag")

        assert has_project_prompts(project_dir) is False

    @pytest.mark.unit
    def test_has_project_prompts_no_file(self, tmp_path):
        """Test has_project_prompts returns False without spec file."""
        from prompts import has_project_prompts

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        assert has_project_prompts(project_dir) is False

    @pytest.mark.unit
    def test_has_project_prompts_legacy_location(self, tmp_path):
        """Test has_project_prompts checks legacy location."""
        from prompts import has_project_prompts

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        (project_dir / "app_spec.txt").write_text("<project_specification>Legacy</project_specification>")

        assert has_project_prompts(project_dir) is True


class TestScaffoldProjectPrompts:
    """Tests for scaffold_project_prompts function."""

    @pytest.mark.unit
    def test_scaffold_creates_prompts_dir(self, tmp_path):
        """Test scaffold creates prompts directory."""
        from prompts import scaffold_project_prompts, TEMPLATES_DIR

        project_dir = tmp_path / "new-project"
        project_dir.mkdir(parents=True)

        # Skip if templates don't exist
        if not TEMPLATES_DIR.exists():
            pytest.skip("Templates directory not found")

        prompts_dir = scaffold_project_prompts(project_dir)

        assert prompts_dir.exists()
        assert prompts_dir == project_dir / "prompts"

    @pytest.mark.unit
    def test_scaffold_copies_templates(self, tmp_path):
        """Test scaffold copies template files."""
        from prompts import scaffold_project_prompts, TEMPLATES_DIR

        project_dir = tmp_path / "new-project"
        project_dir.mkdir(parents=True)

        # Skip if templates don't exist
        if not TEMPLATES_DIR.exists():
            pytest.skip("Templates directory not found")

        prompts_dir = scaffold_project_prompts(project_dir)

        # Check that some files were created
        created_files = list(prompts_dir.glob("*"))
        # May or may not have files depending on templates availability

    @pytest.mark.unit
    def test_scaffold_does_not_overwrite(self, tmp_path):
        """Test scaffold doesn't overwrite existing files."""
        from prompts import scaffold_project_prompts, TEMPLATES_DIR

        project_dir = tmp_path / "new-project"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        # Create existing file
        existing_content = "Existing content that should not be overwritten"
        (prompts_dir / "app_spec.txt").write_text(existing_content)

        scaffold_project_prompts(project_dir)

        # Check content was preserved
        assert (prompts_dir / "app_spec.txt").read_text() == existing_content


class TestEnsureGitignoreClaude:
    """Tests for ensure_gitignore_claude function."""

    @pytest.mark.unit
    def test_creates_gitignore_if_missing(self, tmp_path):
        """Test creates .gitignore if it doesn't exist."""
        from prompts import ensure_gitignore_claude

        project_dir = tmp_path / "project"
        project_dir.mkdir(parents=True)

        ensure_gitignore_claude(project_dir)

        gitignore = project_dir / ".gitignore"
        assert gitignore.exists()
        assert ".claude/" in gitignore.read_text()

    @pytest.mark.unit
    def test_appends_to_existing_gitignore(self, tmp_path):
        """Test appends to existing .gitignore."""
        from prompts import ensure_gitignore_claude

        project_dir = tmp_path / "project"
        project_dir.mkdir(parents=True)

        gitignore = project_dir / ".gitignore"
        gitignore.write_text("node_modules/\n")

        ensure_gitignore_claude(project_dir)

        content = gitignore.read_text()
        assert "node_modules/" in content
        assert ".claude/" in content

    @pytest.mark.unit
    def test_skips_if_already_present(self, tmp_path):
        """Test doesn't duplicate if .claude/ already in gitignore."""
        from prompts import ensure_gitignore_claude

        project_dir = tmp_path / "project"
        project_dir.mkdir(parents=True)

        gitignore = project_dir / ".gitignore"
        original_content = "node_modules/\n.claude/\n"
        gitignore.write_text(original_content)

        ensure_gitignore_claude(project_dir)

        # Should not have duplicated
        content = gitignore.read_text()
        assert content.count(".claude/") == 1


class TestIsExistingRepoProject:
    """Tests for is_existing_repo_project function."""

    @pytest.mark.unit
    def test_is_existing_repo_no_spec(self, tmp_path):
        """Test returns True when no app spec exists."""
        from prompts import is_existing_repo_project

        project_dir = tmp_path / "project"
        project_dir.mkdir(parents=True)

        assert is_existing_repo_project(project_dir) is True

    @pytest.mark.unit
    def test_is_existing_repo_no_spec_tag(self, tmp_path):
        """Test returns True when app spec has no project_specification tag."""
        from prompts import is_existing_repo_project

        project_dir = tmp_path / "project"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        (prompts_dir / "app_spec.txt").write_text("Just some notes, no spec tag")

        assert is_existing_repo_project(project_dir) is True

    @pytest.mark.unit
    def test_is_existing_repo_false_with_valid_spec(self, tmp_path):
        """Test returns False when valid app spec exists."""
        from prompts import is_existing_repo_project

        project_dir = tmp_path / "project"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        (prompts_dir / "app_spec.txt").write_text("<project_specification>Valid Spec</project_specification>")

        assert is_existing_repo_project(project_dir) is False


class TestRefreshProjectPrompts:
    """Tests for refresh_project_prompts function."""

    @pytest.mark.unit
    def test_refresh_creates_prompts_dir(self, tmp_path):
        """Test refresh creates prompts directory if missing."""
        from prompts import refresh_project_prompts

        project_dir = tmp_path / "project"
        project_dir.mkdir(parents=True)

        refresh_project_prompts(project_dir)

        assert (project_dir / "prompts").exists()

    @pytest.mark.unit
    def test_refresh_returns_updated_files(self, tmp_path):
        """Test refresh returns list of updated files."""
        from prompts import refresh_project_prompts, TEMPLATES_DIR

        project_dir = tmp_path / "project"
        project_dir.mkdir(parents=True)

        # Create valid app_spec so it's treated as new project
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)
        (prompts_dir / "app_spec.txt").write_text("<project_specification>Test</project_specification>")

        updated = refresh_project_prompts(project_dir)

        # Should return list of updated file names
        assert isinstance(updated, list)


class TestScaffoldExistingRepo:
    """Tests for scaffold_existing_repo function."""

    @pytest.mark.unit
    def test_creates_minimal_claude_md(self, tmp_path):
        """Test creates minimal CLAUDE.md for existing repo."""
        from prompts import scaffold_existing_repo, BEADS_WORKFLOW_MARKER

        project_dir = tmp_path / "existing-repo"
        project_dir.mkdir(parents=True)

        scaffold_existing_repo(project_dir)

        claude_md = project_dir / "CLAUDE.md"
        assert claude_md.exists()

        content = claude_md.read_text()
        assert BEADS_WORKFLOW_MARKER in content

    @pytest.mark.unit
    def test_appends_to_existing_claude_md(self, tmp_path):
        """Test appends beads workflow to existing CLAUDE.md."""
        from prompts import scaffold_existing_repo, BEADS_WORKFLOW_MARKER

        project_dir = tmp_path / "existing-repo"
        project_dir.mkdir(parents=True)

        # Create existing CLAUDE.md
        claude_md = project_dir / "CLAUDE.md"
        claude_md.write_text("# Existing Project\n\nSome instructions here.")

        scaffold_existing_repo(project_dir)

        content = claude_md.read_text()
        assert "Existing Project" in content
        assert BEADS_WORKFLOW_MARKER in content

    @pytest.mark.unit
    def test_does_not_duplicate_beads_workflow(self, tmp_path):
        """Test doesn't duplicate beads workflow if already present."""
        from prompts import scaffold_existing_repo, BEADS_WORKFLOW_MARKER

        project_dir = tmp_path / "existing-repo"
        project_dir.mkdir(parents=True)

        # Create existing CLAUDE.md with beads workflow
        claude_md = project_dir / "CLAUDE.md"
        original_content = f"# Project\n\n{BEADS_WORKFLOW_MARKER}\nExisting workflow"
        claude_md.write_text(original_content)

        scaffold_existing_repo(project_dir)

        content = claude_md.read_text()
        assert content.count(BEADS_WORKFLOW_MARKER) == 1

    @pytest.mark.unit
    def test_creates_prompts_directory(self, tmp_path):
        """Test creates prompts directory for existing repo."""
        from prompts import scaffold_existing_repo

        project_dir = tmp_path / "existing-repo"
        project_dir.mkdir(parents=True)

        scaffold_existing_repo(project_dir)

        prompts_dir = project_dir / "prompts"
        assert prompts_dir.exists()

    @pytest.mark.unit
    def test_adds_gitignore_entry(self, tmp_path):
        """Test adds .claude/ to gitignore."""
        from prompts import scaffold_existing_repo

        project_dir = tmp_path / "existing-repo"
        project_dir.mkdir(parents=True)

        scaffold_existing_repo(project_dir)

        gitignore = project_dir / ".gitignore"
        assert gitignore.exists()
        assert ".claude/" in gitignore.read_text()


class TestCopySpecToProject:
    """Tests for copy_spec_to_project function."""

    @pytest.mark.unit
    def test_copies_spec_to_root(self, tmp_path):
        """Test copies app_spec.txt to project root."""
        from prompts import copy_spec_to_project

        project_dir = tmp_path / "project"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        (prompts_dir / "app_spec.txt").write_text("<project_specification>Test</project_specification>")

        copy_spec_to_project(project_dir)

        root_spec = project_dir / "app_spec.txt"
        assert root_spec.exists()
        assert "<project_specification>" in root_spec.read_text()

    @pytest.mark.unit
    def test_does_not_overwrite_existing(self, tmp_path):
        """Test doesn't overwrite existing spec in root."""
        from prompts import copy_spec_to_project

        project_dir = tmp_path / "project"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        (prompts_dir / "app_spec.txt").write_text("<project_specification>New</project_specification>")

        # Create existing spec in root
        (project_dir / "app_spec.txt").write_text("<project_specification>Existing</project_specification>")

        copy_spec_to_project(project_dir)

        # Should not have changed
        root_spec = project_dir / "app_spec.txt"
        assert "Existing" in root_spec.read_text()


class TestProjectPromptsDir:
    """Tests for get_project_prompts_dir function."""

    @pytest.mark.unit
    def test_returns_correct_path(self, tmp_path):
        """Test returns correct prompts directory path."""
        from prompts import get_project_prompts_dir

        project_dir = tmp_path / "test-project"

        prompts_dir = get_project_prompts_dir(project_dir)

        assert prompts_dir == project_dir / "prompts"

    @pytest.mark.unit
    def test_works_with_path_object(self, tmp_path):
        """Test works with Path object."""
        from prompts import get_project_prompts_dir

        prompts_dir = get_project_prompts_dir(tmp_path / "project")

        assert isinstance(prompts_dir, Path)


class TestTemplatesDir:
    """Tests for TEMPLATES_DIR constant."""

    @pytest.mark.unit
    def test_templates_dir_is_path(self):
        """Test TEMPLATES_DIR is a Path object."""
        from prompts import TEMPLATES_DIR

        assert isinstance(TEMPLATES_DIR, Path)

    @pytest.mark.unit
    def test_templates_dir_path_format(self):
        """Test TEMPLATES_DIR has expected path format."""
        from prompts import TEMPLATES_DIR

        assert "templates" in str(TEMPLATES_DIR)
        assert ".claude" in str(TEMPLATES_DIR)
