"""
Beads API Router Helper Functions Unit Tests
=============================================

Tests for helper functions in beads_api.py and BeadsManager:
- validate_project_name - Path traversal prevention
- validate_issue_id - Format validation
- BeadsManager._run_bd - Low-level command runner
- BeadsManager._sync_with_remote - Best-effort sync
- run_beads_command - Read operations
- run_beads_write_command - Write operations with lock
"""

import asyncio
import json
import pytest
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import HTTPException


class TestValidateProjectName:
    """Tests for validate_project_name function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from server.routers.beads_api import validate_project_name
        self.validate_project_name = validate_project_name

    @pytest.mark.unit
    def test_valid_simple_name(self):
        """Test simple alphanumeric project name."""
        result = self.validate_project_name("myproject")
        assert result == "myproject"

    @pytest.mark.unit
    def test_valid_name_with_hyphen(self):
        """Test project name with hyphens."""
        result = self.validate_project_name("my-project")
        assert result == "my-project"

    @pytest.mark.unit
    def test_valid_name_with_underscore(self):
        """Test project name with underscores."""
        result = self.validate_project_name("my_project")
        assert result == "my_project"

    @pytest.mark.unit
    def test_valid_name_with_numbers(self):
        """Test project name with numbers."""
        result = self.validate_project_name("project123")
        assert result == "project123"

    @pytest.mark.unit
    def test_valid_mixed_name(self):
        """Test project name with mixed valid characters."""
        result = self.validate_project_name("My_Project-123")
        assert result == "My_Project-123"

    @pytest.mark.unit
    def test_valid_max_length(self):
        """Test project name at max length (50 chars)."""
        name = "a" * 50
        result = self.validate_project_name(name)
        assert result == name

    @pytest.mark.unit
    def test_invalid_path_traversal_dotdot(self):
        """Test path traversal with .. is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            self.validate_project_name("../etc/passwd")

        assert exc_info.value.status_code == 400
        assert "Invalid project name" in exc_info.value.detail

    @pytest.mark.unit
    def test_invalid_path_traversal_slash(self):
        """Test path with slash is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            self.validate_project_name("project/subdir")

        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    def test_invalid_absolute_path(self):
        """Test absolute path is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            self.validate_project_name("/etc/passwd")

        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    def test_invalid_spaces(self):
        """Test project name with spaces is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            self.validate_project_name("my project")

        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    def test_invalid_too_long(self):
        """Test project name over 50 chars is rejected."""
        name = "a" * 51
        with pytest.raises(HTTPException) as exc_info:
            self.validate_project_name(name)

        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    def test_invalid_empty(self):
        """Test empty project name is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            self.validate_project_name("")

        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    def test_invalid_special_chars(self):
        """Test project name with special chars is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            self.validate_project_name("project@name")

        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    def test_invalid_shell_injection(self):
        """Test shell injection attempt is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            self.validate_project_name("project;rm -rf /")

        assert exc_info.value.status_code == 400


class TestValidateIssueId:
    """Tests for validate_issue_id function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from server.routers.beads_api import validate_issue_id
        self.validate_issue_id = validate_issue_id

    @pytest.mark.unit
    def test_valid_beads_format(self):
        """Test standard beads ID format."""
        result = self.validate_issue_id("beads-123")
        assert result == "beads-123"

    @pytest.mark.unit
    def test_valid_feat_format(self):
        """Test feat ID format."""
        result = self.validate_issue_id("feat-1")
        assert result == "feat-1"

    @pytest.mark.unit
    def test_valid_alphanumeric_suffix(self):
        """Test alphanumeric suffix."""
        result = self.validate_issue_id("task-abc123")
        assert result == "task-abc123"

    @pytest.mark.unit
    def test_valid_uppercase(self):
        """Test uppercase letters in ID."""
        result = self.validate_issue_id("BUG-ABC")
        assert result == "BUG-ABC"

    @pytest.mark.unit
    def test_invalid_no_hyphen(self):
        """Test ID without hyphen is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            self.validate_issue_id("feat1")

        assert exc_info.value.status_code == 400
        assert "Invalid issue ID format" in exc_info.value.detail

    @pytest.mark.unit
    def test_invalid_number_prefix(self):
        """Test ID starting with number is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            self.validate_issue_id("123-feat")

        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    def test_invalid_empty_suffix(self):
        """Test ID with empty suffix is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            self.validate_issue_id("feat-")

        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    def test_invalid_empty_prefix(self):
        """Test ID with empty prefix is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            self.validate_issue_id("-123")

        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    def test_invalid_multiple_hyphens(self):
        """Test ID with multiple hyphens is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            self.validate_issue_id("feat-test-123")

        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    def test_invalid_special_chars(self):
        """Test ID with special characters is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            self.validate_issue_id("feat-1!")

        assert exc_info.value.status_code == 400


class TestGetProjectPath:
    """Tests for BeadsManager.local_path property."""

    @pytest.mark.unit
    def test_returns_projects_path(self, tmp_path, monkeypatch):
        """Test that BeadsManager.local_path returns projects directory path."""
        from server.services.beads_manager import BeadsManager

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()

        # Patch get_projects_dir to return our test directory
        with patch("server.services.beads_manager.get_projects_dir") as mock_projects:
            mock_projects.return_value = projects_dir
            manager = BeadsManager("test-project", "https://github.com/test/repo.git")

        assert manager.local_path == projects_dir / "test-project"


class TestRunBd:
    """Tests for BeadsManager._run_bd low-level command runner."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create a BeadsManager with a test path."""
        from server.services.beads_manager import BeadsManager
        mgr = BeadsManager("test-project", "https://github.com/test/repo.git")
        mgr.local_path = tmp_path
        return mgr

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_successful_json_output(self, manager):
        """Test successful command with JSON output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"id": "feat-1", "title": "Test"}'
        mock_result.stderr = ""

        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.return_value = mock_result

            result = await manager._run_bd(["show", "feat-1", "--json"])

        assert result["success"] is True
        assert result["data"]["id"] == "feat-1"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_successful_empty_output(self, manager):
        """Test successful command with empty output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.return_value = mock_result

            result = await manager._run_bd(["list", "--json"])

        assert result["success"] is True
        assert result["data"] == []

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_successful_plain_text_output(self, manager):
        """Test successful command with plain text output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Synced successfully"
        mock_result.stderr = ""

        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.return_value = mock_result

            result = await manager._run_bd(["sync"])

        assert result["success"] is True
        assert result["output"] == "Synced successfully"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_command_failure(self, manager):
        """Test command that returns non-zero exit code."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Issue not found"

        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.return_value = mock_result

            result = await manager._run_bd(["show", "nonexistent"])

        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_command_timeout(self, manager):
        """Test command timeout handling."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = subprocess.TimeoutExpired(cmd="bd", timeout=60)

            result = await manager._run_bd(["sync"])

        assert "error" in result
        assert "timed out" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_bd_not_found(self, manager):
        """Test handling when bd command is not found."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = FileNotFoundError()

            result = await manager._run_bd(["list"])

        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_json_parse_error(self, manager):
        """Test handling of malformed JSON output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json {"
        mock_result.stderr = ""

        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.return_value = mock_result

            result = await manager._run_bd(["list", "--json"])

        # Should treat as plain text when JSON parsing fails
        assert result["success"] is True
        assert result["output"] == "not valid json {"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_generic_exception(self, manager):
        """Test handling of generic exceptions."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = Exception("Unexpected error")

            result = await manager._run_bd(["list"])

        assert "error" in result
        assert "Unexpected error" in result["error"]


class TestSyncBeads:
    """Tests for BeadsManager._sync_with_remote function."""

    @pytest.fixture
    def manager(self, tmp_path):
        """Create a BeadsManager with a test path."""
        from server.services.beads_manager import BeadsManager
        mgr = BeadsManager("test-project", "https://github.com/test/repo.git")
        mgr.local_path = tmp_path
        return mgr

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_sync_success(self, manager):
        """Test successful sync returns True."""
        with patch.object(manager, "_run_bd") as mock_run:
            mock_run.return_value = {"success": True}

            result = await manager._sync_with_remote()

        assert result is True

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_sync_failure(self, manager):
        """Test failed sync returns False."""
        with patch.object(manager, "_run_bd") as mock_run:
            mock_run.return_value = {"error": "Remote not configured"}

            result = await manager._sync_with_remote()

        assert result is False

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_sync_is_best_effort(self, manager):
        """Test sync failure doesn't raise exception."""
        with patch.object(manager, "_run_bd") as mock_run:
            mock_run.return_value = {"error": "Network error"}

            # Should not raise
            result = await manager._sync_with_remote()

        assert result is False


class TestRunBeadsCommand:
    """Tests for run_beads_command function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from server.routers.beads_api import run_beads_command
        self.run_beads_command = run_beads_command

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_does_not_sync_before_read(self, tmp_path):
        """Test that run_beads_command does NOT sync before reading.

        Syncing before every read caused "another sync in progress" warnings.
        Background poller handles sync; reads just query local database.
        """
        from server.services.beads_manager import BeadsManager, _managers

        # Create a mock manager
        manager = BeadsManager("test-project", "https://github.com/test/repo.git")
        manager.local_path = tmp_path
        _managers["test-project"] = manager

        sync_called = False

        async def mock_sync():
            nonlocal sync_called
            sync_called = True
            return True

        manager._sync_with_remote = mock_sync

        with patch.object(manager, "_run_bd") as mock_run:
            mock_run.return_value = {"success": True, "data": []}

            await self.run_beads_command("test-project", ["list", "--json"])

        assert not sync_called, "Sync should NOT be called before read (background poller handles it)"

        # Cleanup
        del _managers["test-project"]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_returns_error_for_missing_project(self):
        """Test error when project git URL not found."""
        from server.services.beads_manager import _managers

        # Ensure project is not in managers
        _managers.pop("nonexistent-project", None)

        with patch("registry.get_project_git_url") as mock_git:
            mock_git.return_value = None

            result = await self.run_beads_command("nonexistent-project", ["list"])

        assert "error" in result


class TestRunBeadsWriteCommand:
    """Tests for run_beads_write_command function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from server.routers.beads_api import run_beads_write_command
        self.run_beads_write_command = run_beads_write_command

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_syncs_after_write(self, tmp_path):
        """Test that run_beads_write_command syncs after writing."""
        from server.services.beads_manager import BeadsManager, _managers

        # Create a mock manager
        manager = BeadsManager("test-project", "https://github.com/test/repo.git")
        manager.local_path = tmp_path
        _managers["test-project"] = manager

        call_order = []

        async def mock_run_bd(args, timeout=60):
            call_order.append(("run_bd", args))
            return {"success": True, "data": {"id": "feat-1"}}

        async def mock_sync():
            call_order.append(("sync",))
            return True

        manager._run_bd = mock_run_bd
        manager._sync_with_remote = mock_sync

        await self.run_beads_write_command("test-project", ["create", "--title", "Test"])

        # Verify sync was called after write
        assert len(call_order) == 2
        assert call_order[0][0] == "run_bd"
        assert call_order[1][0] == "sync"

        # Cleanup
        del _managers["test-project"]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_no_sync_on_error(self, tmp_path):
        """Test that sync is not called if write fails."""
        from server.services.beads_manager import BeadsManager, _managers

        # Create a mock manager
        manager = BeadsManager("test-project", "https://github.com/test/repo.git")
        manager.local_path = tmp_path
        _managers["test-project"] = manager

        sync_called = False

        async def mock_run_bd(args, timeout=60):
            return {"error": "Write failed"}

        async def mock_sync():
            nonlocal sync_called
            sync_called = True
            return True

        manager._run_bd = mock_run_bd
        manager._sync_with_remote = mock_sync

        result = await self.run_beads_write_command("test-project", ["create", "--title", "Test"])

        assert "error" in result
        assert not sync_called, "Sync should not be called on error"

        # Cleanup
        del _managers["test-project"]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_acquires_lock(self, tmp_path):
        """Test that write command acquires lock."""
        from server.services.beads_manager import BeadsManager, _managers

        # Create a mock manager
        manager = BeadsManager("test-project", "https://github.com/test/repo.git")
        manager.local_path = tmp_path
        _managers["test-project"] = manager

        lock_acquired_during_bd = False

        async def mock_run_bd(args, timeout=60):
            nonlocal lock_acquired_during_bd
            # Check if the lock is held when _run_bd is called
            lock_acquired_during_bd = manager._lock.locked()
            return {"success": True, "data": {"id": "feat-1"}}

        manager._run_bd = mock_run_bd

        # Also mock _sync_with_remote to avoid network calls
        async def mock_sync():
            return True

        manager._sync_with_remote = mock_sync

        await self.run_beads_write_command("test-project", ["create", "--title", "Test"])

        assert lock_acquired_during_bd, "Lock should be acquired during _run_bd call"

        # Cleanup
        del _managers["test-project"]
