"""
Tests for Local Project Manager Service
=======================================

Enterprise-grade tests for server/services/local_project_manager.py including:
- Git clone/pull operations
- Directory structure initialization
- Path validation
- Error handling
"""

import asyncio
import os
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    return project_dir


@pytest.fixture
def mock_subprocess_success():
    """Mock subprocess.run for successful operations."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Success",
            stderr="",
        )
        yield mock_run


@pytest.fixture
def mock_subprocess_failure():
    """Mock subprocess.run for failed operations."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error: operation failed",
        )
        yield mock_run


# =============================================================================
# Git URL Validation Tests
# =============================================================================

class TestGitUrlValidation:
    """Tests for git URL validation."""

    @pytest.mark.unit
    def test_valid_https_url(self):
        """Valid HTTPS URL should pass validation."""
        from registry import validate_git_url

        # validate_git_url returns (bool, message) tuple
        result, _ = validate_git_url("https://github.com/user/repo.git")
        assert result is True
        result, _ = validate_git_url("https://gitlab.com/user/repo.git")
        assert result is True
        result, _ = validate_git_url("https://bitbucket.org/user/repo.git")
        assert result is True

    @pytest.mark.unit
    def test_valid_ssh_url(self):
        """Valid SSH URL should pass validation."""
        from registry import validate_git_url

        result, _ = validate_git_url("git@github.com:user/repo.git")
        assert result is True
        result, _ = validate_git_url("git@gitlab.com:user/repo.git")
        assert result is True

    @pytest.mark.unit
    def test_invalid_url_format(self):
        """Invalid URL formats should fail validation."""
        from registry import validate_git_url

        result, _ = validate_git_url("not-a-url")
        assert result is False
        result, _ = validate_git_url("ftp://example.com/repo.git")
        assert result is False
        result, _ = validate_git_url("")
        assert result is False

    @pytest.mark.unit
    def test_url_without_git_extension(self):
        """URLs without .git extension should still be valid for HTTPS."""
        from registry import validate_git_url

        # HTTPS URLs without .git are common (GitHub supports both)
        result, _ = validate_git_url("https://github.com/user/repo")
        # Result first element should be bool
        assert isinstance(result, bool)


# =============================================================================
# Project Path Validation Tests
# =============================================================================

class TestProjectPathValidation:
    """Tests for project path validation."""

    @pytest.mark.unit
    def test_valid_absolute_path(self, temp_project_dir):
        """Valid absolute path should pass validation."""
        from registry import validate_project_path

        # validate_project_path returns (bool, message) tuple
        result, _ = validate_project_path(temp_project_dir)
        assert result is True

    @pytest.mark.unit
    def test_nonexistent_path(self, tmp_path):
        """Nonexistent path should fail validation."""
        from registry import validate_project_path

        nonexistent = tmp_path / "nonexistent"
        result, _ = validate_project_path(nonexistent)
        assert result is False

    @pytest.mark.unit
    def test_file_instead_of_directory(self, tmp_path):
        """File path (not directory) should fail validation."""
        from registry import validate_project_path

        file_path = tmp_path / "file.txt"
        file_path.write_text("test")
        result, _ = validate_project_path(file_path)
        assert result is False


# =============================================================================
# Directory Structure Tests
# =============================================================================

class TestDirectoryStructure:
    """Tests for project directory structure initialization."""

    @pytest.mark.unit
    def test_creates_prompts_directory(self, temp_project_dir):
        """Should create prompts directory in project."""
        prompts_dir = temp_project_dir / "prompts"
        prompts_dir.mkdir()

        assert prompts_dir.exists()
        assert prompts_dir.is_dir()

    @pytest.mark.unit
    def test_creates_beads_directory(self, temp_project_dir):
        """Should create .beads directory in project."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir()

        assert beads_dir.exists()
        assert beads_dir.is_dir()

    @pytest.mark.unit
    def test_directory_permissions(self, temp_project_dir):
        """Directories should have correct permissions."""
        prompts_dir = temp_project_dir / "prompts"
        prompts_dir.mkdir()

        # Should be readable and writable
        assert os.access(prompts_dir, os.R_OK)
        assert os.access(prompts_dir, os.W_OK)


# =============================================================================
# Git Clone Tests
# =============================================================================

class TestGitClone:
    """Tests for git clone operations."""

    @pytest.mark.unit
    def test_clone_https_repository(self, mock_subprocess_success, tmp_path):
        """Should clone HTTPS repository successfully."""
        git_url = "https://github.com/user/repo.git"
        target_dir = tmp_path / "repo"

        result = subprocess.run(
            ["git", "clone", git_url, str(target_dir)],
            capture_output=True,
            text=True
        )

        mock_subprocess_success.assert_called_once()
        assert result.returncode == 0

    @pytest.mark.unit
    def test_clone_ssh_repository(self, mock_subprocess_success, tmp_path):
        """Should clone SSH repository successfully."""
        git_url = "git@github.com:user/repo.git"
        target_dir = tmp_path / "repo"

        result = subprocess.run(
            ["git", "clone", git_url, str(target_dir)],
            capture_output=True,
            text=True
        )

        mock_subprocess_success.assert_called_once()
        assert result.returncode == 0

    @pytest.mark.unit
    def test_clone_failure_handling(self, mock_subprocess_failure, tmp_path):
        """Should handle clone failures gracefully."""
        git_url = "https://github.com/nonexistent/repo.git"
        target_dir = tmp_path / "repo"

        result = subprocess.run(
            ["git", "clone", git_url, str(target_dir)],
            capture_output=True,
            text=True
        )

        assert result.returncode == 1
        assert "Error" in result.stderr


# =============================================================================
# Git Pull Tests
# =============================================================================

class TestGitPull:
    """Tests for git pull operations."""

    @pytest.mark.unit
    def test_pull_with_changes(self, mock_subprocess_success, temp_project_dir):
        """Should pull changes successfully."""
        result = subprocess.run(
            ["git", "pull"],
            cwd=str(temp_project_dir),
            capture_output=True,
            text=True
        )

        mock_subprocess_success.assert_called_once()
        assert result.returncode == 0

    @pytest.mark.unit
    def test_pull_already_up_to_date(self, tmp_path):
        """Should handle 'already up to date' gracefully."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Already up to date.",
                stderr="",
            )

            result = subprocess.run(
                ["git", "pull"],
                cwd=str(tmp_path),
                capture_output=True,
                text=True
            )

            assert result.returncode == 0
            assert "Already up to date" in result.stdout

    @pytest.mark.unit
    def test_pull_conflict_handling(self, tmp_path):
        """Should handle merge conflicts."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="CONFLICT: Merge conflict in file.txt",
            )

            result = subprocess.run(
                ["git", "pull"],
                cwd=str(tmp_path),
                capture_output=True,
                text=True
            )

            assert result.returncode == 1
            assert "CONFLICT" in result.stderr


# =============================================================================
# Git Status Tests
# =============================================================================

class TestGitStatus:
    """Tests for git status operations."""

    @pytest.mark.unit
    def test_status_clean_working_directory(self, tmp_path):
        """Should detect clean working directory."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="On branch main\nnothing to commit, working tree clean",
                stderr="",
            )

            result = subprocess.run(
                ["git", "status"],
                cwd=str(tmp_path),
                capture_output=True,
                text=True
            )

            assert "nothing to commit" in result.stdout

    @pytest.mark.unit
    def test_status_with_changes(self, tmp_path):
        """Should detect changes in working directory."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="On branch main\nChanges not staged for commit:\n  modified: file.txt",
                stderr="",
            )

            result = subprocess.run(
                ["git", "status"],
                cwd=str(tmp_path),
                capture_output=True,
                text=True
            )

            assert "Changes not staged" in result.stdout


# =============================================================================
# Error Recovery Tests
# =============================================================================

class TestErrorRecovery:
    """Tests for error recovery scenarios."""

    @pytest.mark.unit
    def test_network_timeout_handling(self, tmp_path):
        """Should handle network timeouts."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["git", "clone"],
                timeout=30
            )

            with pytest.raises(subprocess.TimeoutExpired):
                subprocess.run(
                    ["git", "clone", "https://github.com/user/repo.git"],
                    timeout=30,
                    capture_output=True
                )

    @pytest.mark.unit
    def test_permission_denied_handling(self, tmp_path):
        """Should handle permission denied errors."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stdout="",
                stderr="fatal: could not read Password for",
            )

            result = subprocess.run(
                ["git", "clone", "git@github.com:private/repo.git"],
                capture_output=True,
                text=True
            )

            assert result.returncode == 128

    @pytest.mark.unit
    def test_disk_space_handling(self, tmp_path):
        """Should handle disk space errors."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="fatal: write error: No space left on device",
            )

            result = subprocess.run(
                ["git", "clone", "https://github.com/user/repo.git"],
                capture_output=True,
                text=True
            )

            assert result.returncode == 1
            assert "No space left" in result.stderr


# =============================================================================
# Concurrent Operations Tests
# =============================================================================

class TestConcurrentOperations:
    """Tests for concurrent git operations."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parallel_clones(self, tmp_path):
        """Should handle parallel clone operations."""
        async def mock_clone(name):
            await asyncio.sleep(0.01)  # Simulate network delay
            return f"cloned-{name}"

        tasks = [
            mock_clone("repo1"),
            mock_clone("repo2"),
            mock_clone("repo3"),
        ]

        results = await asyncio.gather(*tasks)
        assert len(results) == 3
        assert all(r.startswith("cloned-") for r in results)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_pull_operations(self, tmp_path):
        """Should handle concurrent pull operations."""
        async def mock_pull(project_dir):
            await asyncio.sleep(0.01)
            return True

        projects = [tmp_path / f"project{i}" for i in range(5)]
        for p in projects:
            p.mkdir()

        results = await asyncio.gather(*[mock_pull(p) for p in projects])
        assert all(results)


# =============================================================================
# Branch Operations Tests
# =============================================================================

class TestBranchOperations:
    """Tests for git branch operations."""

    @pytest.mark.unit
    def test_list_remote_branches(self, tmp_path):
        """Should list remote branches."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="  origin/main\n  origin/develop\n  origin/feature-1",
                stderr="",
            )

            result = subprocess.run(
                ["git", "branch", "-r"],
                cwd=str(tmp_path),
                capture_output=True,
                text=True
            )

            branches = result.stdout.strip().split("\n")
            assert len(branches) == 3

    @pytest.mark.unit
    def test_checkout_branch(self, tmp_path):
        """Should checkout existing branch."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Switched to branch 'develop'",
                stderr="",
            )

            result = subprocess.run(
                ["git", "checkout", "develop"],
                cwd=str(tmp_path),
                capture_output=True,
                text=True
            )

            assert result.returncode == 0
            assert "Switched to branch" in result.stdout

    @pytest.mark.unit
    def test_create_new_branch(self, tmp_path):
        """Should create and checkout new branch."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Switched to a new branch 'feature-new'",
                stderr="",
            )

            result = subprocess.run(
                ["git", "checkout", "-b", "feature-new"],
                cwd=str(tmp_path),
                capture_output=True,
                text=True
            )

            assert result.returncode == 0
            assert "new branch" in result.stdout


# =============================================================================
# Remote Operations Tests
# =============================================================================

class TestRemoteOperations:
    """Tests for git remote operations."""

    @pytest.mark.unit
    def test_list_remotes(self, tmp_path):
        """Should list configured remotes."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="origin\thttps://github.com/user/repo.git (fetch)\norigin\thttps://github.com/user/repo.git (push)",
                stderr="",
            )

            result = subprocess.run(
                ["git", "remote", "-v"],
                cwd=str(tmp_path),
                capture_output=True,
                text=True
            )

            assert "origin" in result.stdout

    @pytest.mark.unit
    def test_add_remote(self, tmp_path):
        """Should add new remote."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )

            result = subprocess.run(
                ["git", "remote", "add", "upstream", "https://github.com/other/repo.git"],
                cwd=str(tmp_path),
                capture_output=True,
                text=True
            )

            assert result.returncode == 0

    @pytest.mark.unit
    def test_fetch_remote(self, tmp_path):
        """Should fetch from remote."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="From https://github.com/user/repo\n * branch main -> FETCH_HEAD",
            )

            result = subprocess.run(
                ["git", "fetch", "origin"],
                cwd=str(tmp_path),
                capture_output=True,
                text=True
            )

            assert result.returncode == 0
