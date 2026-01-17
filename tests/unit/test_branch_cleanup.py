"""
Branch Cleanup Service Unit Tests
=================================

Tests for the branch cleanup service including:
- Remote branch listing and filtering
- Protected branch handling
- Cleanup operations
"""

import json
import pytest
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Protected Branches Tests
# =============================================================================

class TestProtectedBranches:
    """Tests for protected branches configuration."""

    @pytest.mark.unit
    def test_protected_branches_set(self):
        """Test protected branches are correctly defined."""
        from server.services.branch_cleanup import PROTECTED_BRANCHES

        expected = {"main", "master", "beads-sync", "HEAD"}

        assert PROTECTED_BRANCHES == expected

    @pytest.mark.unit
    def test_main_is_protected(self):
        """Test main branch is protected."""
        from server.services.branch_cleanup import PROTECTED_BRANCHES

        assert "main" in PROTECTED_BRANCHES

    @pytest.mark.unit
    def test_master_is_protected(self):
        """Test master branch is protected."""
        from server.services.branch_cleanup import PROTECTED_BRANCHES

        assert "master" in PROTECTED_BRANCHES

    @pytest.mark.unit
    def test_beads_sync_is_protected(self):
        """Test beads-sync branch is protected."""
        from server.services.branch_cleanup import PROTECTED_BRANCHES

        assert "beads-sync" in PROTECTED_BRANCHES


# =============================================================================
# Single Project Cleanup Tests
# =============================================================================

class TestCleanupRemoteBranchesForProject:
    """Tests for cleanup_remote_branches_for_project function."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_zero_when_no_local_clone(self, tmp_path):
        """Test returns 0 when no local clone exists."""
        from server.services.branch_cleanup import cleanup_remote_branches_for_project

        with patch("registry.get_beads_sync_dir") as mock_sync_dir:
            mock_sync_dir.return_value = tmp_path / "nonexistent"

            result = await cleanup_remote_branches_for_project(
                "test-project",
                "https://github.com/user/repo.git",
                tmp_path / "also-nonexistent"
            )

        assert result == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_zero_when_no_branches(self, tmp_path):
        """Test returns 0 when no branches to delete."""
        from server.services.branch_cleanup import cleanup_remote_branches_for_project

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("registry.get_beads_sync_dir") as mock_sync_dir:
            mock_sync_dir.return_value = tmp_path / "nonexistent"

            with patch("subprocess.run") as mock_run:
                # First call: fetch
                mock_fetch = MagicMock(returncode=0)
                # Second call: list branches - return only protected branches
                mock_list = MagicMock(
                    returncode=0,
                    stdout="origin/main\norigin/master\n"
                )
                mock_run.side_effect = [mock_fetch, mock_list]

                result = await cleanup_remote_branches_for_project(
                    "test-project",
                    "https://github.com/user/repo.git",
                    project_dir
                )

        assert result == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_deletes_feature_branches(self, tmp_path):
        """Test deletes non-protected feature branches."""
        from server.services.branch_cleanup import cleanup_remote_branches_for_project

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("registry.get_beads_sync_dir") as mock_sync_dir:
            mock_sync_dir.return_value = tmp_path / "nonexistent"

            with patch("subprocess.run") as mock_run:
                # Calls: fetch, list branches, delete branch1, delete branch2
                mock_run.side_effect = [
                    MagicMock(returncode=0),  # fetch
                    MagicMock(returncode=0, stdout="origin/main\norigin/feature-1\norigin/feature-2\n"),  # list
                    MagicMock(returncode=0),  # delete feature-1
                    MagicMock(returncode=0),  # delete feature-2
                ]

                result = await cleanup_remote_branches_for_project(
                    "test-project",
                    "https://github.com/user/repo.git",
                    project_dir
                )

        assert result == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handles_delete_failure(self, tmp_path):
        """Test handles branch delete failure gracefully."""
        from server.services.branch_cleanup import cleanup_remote_branches_for_project

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("registry.get_beads_sync_dir") as mock_sync_dir:
            mock_sync_dir.return_value = tmp_path / "nonexistent"

            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0),  # fetch
                    MagicMock(returncode=0, stdout="origin/main\norigin/feature-1\n"),  # list
                    MagicMock(returncode=1),  # delete fails
                ]

                result = await cleanup_remote_branches_for_project(
                    "test-project",
                    "https://github.com/user/repo.git",
                    project_dir
                )

        assert result == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_uses_beads_sync_dir_if_available(self, tmp_path):
        """Test uses beads-sync directory when available."""
        from server.services.branch_cleanup import cleanup_remote_branches_for_project

        beads_sync_dir = tmp_path / "beads-sync" / "test-project"
        beads_sync_dir.mkdir(parents=True)

        with patch("registry.get_beads_sync_dir") as mock_sync_dir:
            mock_sync_dir.return_value = tmp_path / "beads-sync"

            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0),  # fetch
                    MagicMock(returncode=0, stdout="origin/main\n"),  # list
                ]

                await cleanup_remote_branches_for_project(
                    "test-project",
                    "https://github.com/user/repo.git",
                    tmp_path / "project-dir"  # This should not be used
                )

        # Verify fetch was called with beads-sync dir
        assert mock_run.called
        call_args = mock_run.call_args_list[0][0][0]
        assert str(beads_sync_dir) in str(call_args)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handles_exception(self, tmp_path):
        """Test handles exceptions gracefully."""
        from server.services.branch_cleanup import cleanup_remote_branches_for_project

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("registry.get_beads_sync_dir") as mock_sync_dir:
            mock_sync_dir.return_value = tmp_path / "nonexistent"

            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = Exception("Network error")

                result = await cleanup_remote_branches_for_project(
                    "test-project",
                    "https://github.com/user/repo.git",
                    project_dir
                )

        assert result == 0


# =============================================================================
# All Projects Cleanup Tests
# =============================================================================

class TestCleanupAllRemoteBranches:
    """Tests for cleanup_all_remote_branches function."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_projects(self):
        """Test returns empty dict when no projects registered."""
        from server.services.branch_cleanup import cleanup_all_remote_branches

        with patch("registry.list_registered_projects") as mock_list:
            mock_list.return_value = {}

            result = await cleanup_all_remote_branches()

        assert result == {}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cleans_multiple_projects(self, tmp_path):
        """Test cleans up branches for multiple projects."""
        from server.services.branch_cleanup import cleanup_all_remote_branches

        project1_dir = tmp_path / "project1"
        project2_dir = tmp_path / "project2"
        project1_dir.mkdir()
        project2_dir.mkdir()

        with patch("registry.list_registered_projects") as mock_list:
            mock_list.return_value = {"project1": {}, "project2": {}}

            with patch("registry.get_project_git_url") as mock_url:
                mock_url.side_effect = lambda n: f"https://github.com/user/{n}.git"

                with patch("registry.get_project_path") as mock_path:
                    mock_path.side_effect = lambda n: tmp_path / n

                    with patch("server.services.branch_cleanup.cleanup_remote_branches_for_project") as mock_cleanup:
                        mock_cleanup.side_effect = [2, 1]  # 2 branches for project1, 1 for project2

                        result = await cleanup_all_remote_branches()

        assert result == {"project1": 2, "project2": 1}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_skips_projects_without_git_url(self, tmp_path):
        """Test skips projects without git URL."""
        from server.services.branch_cleanup import cleanup_all_remote_branches

        with patch("registry.list_registered_projects") as mock_list:
            mock_list.return_value = {"project1": {}}

            with patch("registry.get_project_git_url") as mock_url:
                mock_url.return_value = None  # No git URL

                with patch("registry.get_project_path") as mock_path:
                    mock_path.return_value = tmp_path

                    result = await cleanup_all_remote_branches()

        assert result == {}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_skips_projects_without_path(self, tmp_path):
        """Test skips projects without local path."""
        from server.services.branch_cleanup import cleanup_all_remote_branches

        with patch("registry.list_registered_projects") as mock_list:
            mock_list.return_value = {"project1": {}}

            with patch("registry.get_project_git_url") as mock_url:
                mock_url.return_value = "https://github.com/user/repo.git"

                with patch("registry.get_project_path") as mock_path:
                    mock_path.return_value = None  # No path

                    result = await cleanup_all_remote_branches()

        assert result == {}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_excludes_projects_with_zero_deletions(self, tmp_path):
        """Test excludes projects with zero deleted branches from results."""
        from server.services.branch_cleanup import cleanup_all_remote_branches

        project_dir = tmp_path / "project1"
        project_dir.mkdir()

        with patch("registry.list_registered_projects") as mock_list:
            mock_list.return_value = {"project1": {}}

            with patch("registry.get_project_git_url") as mock_url:
                mock_url.return_value = "https://github.com/user/repo.git"

                with patch("registry.get_project_path") as mock_path:
                    mock_path.return_value = project_dir

                    with patch("server.services.branch_cleanup.cleanup_remote_branches_for_project") as mock_cleanup:
                        mock_cleanup.return_value = 0

                        result = await cleanup_all_remote_branches()

        assert result == {}


# =============================================================================
# Branch Filtering Tests
# =============================================================================

class TestBranchFiltering:
    """Tests for branch filtering logic."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_filters_protected_branches(self, tmp_path):
        """Test protected branches are filtered out."""
        from server.services.branch_cleanup import cleanup_remote_branches_for_project

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("registry.get_beads_sync_dir") as mock_sync_dir:
            mock_sync_dir.return_value = tmp_path / "nonexistent"

            with patch("subprocess.run") as mock_run:
                # Return both protected and unprotected branches
                mock_run.side_effect = [
                    MagicMock(returncode=0),  # fetch
                    MagicMock(
                        returncode=0,
                        stdout="origin/main\norigin/master\norigin/beads-sync\norigin/HEAD\norigin/feature-1\n"
                    ),  # list
                    MagicMock(returncode=0),  # delete feature-1 only
                ]

                result = await cleanup_remote_branches_for_project(
                    "test-project",
                    "https://github.com/user/repo.git",
                    project_dir
                )

        # Only feature-1 should be deleted
        assert result == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handles_empty_branch_list(self, tmp_path):
        """Test handles empty branch list."""
        from server.services.branch_cleanup import cleanup_remote_branches_for_project

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("registry.get_beads_sync_dir") as mock_sync_dir:
            mock_sync_dir.return_value = tmp_path / "nonexistent"

            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0),  # fetch
                    MagicMock(returncode=0, stdout=""),  # empty list
                ]

                result = await cleanup_remote_branches_for_project(
                    "test-project",
                    "https://github.com/user/repo.git",
                    project_dir
                )

        assert result == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handles_branch_list_failure(self, tmp_path):
        """Test handles branch list command failure."""
        from server.services.branch_cleanup import cleanup_remote_branches_for_project

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("registry.get_beads_sync_dir") as mock_sync_dir:
            mock_sync_dir.return_value = tmp_path / "nonexistent"

            with patch("subprocess.run") as mock_run:
                mock_run.side_effect = [
                    MagicMock(returncode=0),  # fetch
                    MagicMock(returncode=1, stdout=""),  # list fails
                ]

                result = await cleanup_remote_branches_for_project(
                    "test-project",
                    "https://github.com/user/repo.git",
                    project_dir
                )

        assert result == 0
