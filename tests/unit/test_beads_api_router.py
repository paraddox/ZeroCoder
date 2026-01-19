"""
Beads API Router Helper Functions Unit Tests
=============================================

Tests for helper functions in beads_api.py:
- validate_project_name - Path traversal prevention
- validate_issue_id - Format validation
- _get_project_path - Path resolution
- _run_bd - Low-level command runner
- _sync_beads - Best-effort sync
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
    def test_invalid_special_chars(self):
        """Test project name with special characters is rejected."""
        invalid_names = ["project!", "project@test", "proj#123", "proj$", "proj%"]
        for name in invalid_names:
            with pytest.raises(HTTPException) as exc_info:
                self.validate_project_name(name)
            assert exc_info.value.status_code == 400

    @pytest.mark.unit
    def test_invalid_empty_name(self):
        """Test empty project name is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            self.validate_project_name("")

        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    def test_invalid_too_long(self):
        """Test project name over 50 chars is rejected."""
        name = "a" * 51
        with pytest.raises(HTTPException) as exc_info:
            self.validate_project_name(name)

        assert exc_info.value.status_code == 400

    @pytest.mark.unit
    def test_invalid_dots_only(self):
        """Test name with only dots is rejected."""
        with pytest.raises(HTTPException) as exc_info:
            self.validate_project_name("...")

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
        result = self.validate_issue_id("beads-1")
        assert result == "beads-1"

    @pytest.mark.unit
    def test_valid_feat_format(self):
        """Test feat ID format."""
        result = self.validate_issue_id("feat-42")
        assert result == "feat-42"

    @pytest.mark.unit
    def test_valid_long_number(self):
        """Test ID with long number."""
        result = self.validate_issue_id("feat-12345")
        assert result == "feat-12345"

    @pytest.mark.unit
    def test_valid_alphanumeric_suffix(self):
        """Test ID with alphanumeric suffix."""
        result = self.validate_issue_id("project-abc123")
        assert result == "project-abc123"

    @pytest.mark.unit
    def test_valid_uppercase_prefix(self):
        """Test ID with uppercase prefix."""
        result = self.validate_issue_id("FEAT-1")
        assert result == "FEAT-1"

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
    """Tests for _get_project_path function."""

    @pytest.mark.unit
    def test_returns_beads_sync_path(self, tmp_path, monkeypatch):
        """Test that _get_project_path returns beads-sync directory path."""
        from server.routers.beads_api import _get_project_path

        beads_sync_dir = tmp_path / "beads-sync"
        beads_sync_dir.mkdir()
        project_dir = beads_sync_dir / "test-project"
        project_dir.mkdir()

        # The function imports get_beads_sync_dir from registry module
        # We need to patch it in the registry module before it's imported
        with patch("registry.get_beads_sync_dir") as mock_sync:
            mock_sync.return_value = beads_sync_dir
            result = _get_project_path("test-project")

        assert result == project_dir


class TestRunBd:
    """Tests for _run_bd low-level command runner."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from server.routers.beads_api import _run_bd
        self._run_bd = _run_bd

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_successful_json_output(self, tmp_path):
        """Test successful command with JSON output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"id": "feat-1", "title": "Test"}'
        mock_result.stderr = ""

        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.return_value = mock_result

            result = await self._run_bd(tmp_path, ["show", "feat-1", "--json"])

        assert result["success"] is True
        assert result["data"]["id"] == "feat-1"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_successful_empty_output(self, tmp_path):
        """Test successful command with empty output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.return_value = mock_result

            result = await self._run_bd(tmp_path, ["list", "--json"])

        assert result["success"] is True
        assert result["data"] == []

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_successful_plain_text_output(self, tmp_path):
        """Test successful command with plain text output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Synced successfully"
        mock_result.stderr = ""

        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.return_value = mock_result

            result = await self._run_bd(tmp_path, ["sync"])

        assert result["success"] is True
        assert result["output"] == "Synced successfully"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_command_failure(self, tmp_path):
        """Test command that returns non-zero exit code."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Issue not found"

        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.return_value = mock_result

            result = await self._run_bd(tmp_path, ["show", "nonexistent"])

        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_command_timeout(self, tmp_path):
        """Test command timeout handling."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = subprocess.TimeoutExpired(cmd="bd", timeout=60)

            result = await self._run_bd(tmp_path, ["sync"])

        assert "error" in result
        assert "timed out" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_bd_not_found(self, tmp_path):
        """Test handling when bd command is not found."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = FileNotFoundError()

            result = await self._run_bd(tmp_path, ["list"])

        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_json_parse_error(self, tmp_path):
        """Test handling of malformed JSON output."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json {"
        mock_result.stderr = ""

        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.return_value = mock_result

            result = await self._run_bd(tmp_path, ["list", "--json"])

        # Should treat as plain text when JSON parsing fails
        assert result["success"] is True
        assert result["output"] == "not valid json {"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_generic_exception(self, tmp_path):
        """Test handling of generic exceptions."""
        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = Exception("Unexpected error")

            result = await self._run_bd(tmp_path, ["list"])

        assert "error" in result
        assert "Unexpected error" in result["error"]


class TestSyncBeads:
    """Tests for _sync_beads function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from server.routers.beads_api import _sync_beads
        self._sync_beads = _sync_beads

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_sync_success(self, tmp_path):
        """Test successful sync returns True."""
        with patch("server.routers.beads_api._run_bd") as mock_run:
            mock_run.return_value = {"success": True}

            result = await self._sync_beads(tmp_path)

        assert result is True

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_sync_failure(self, tmp_path):
        """Test failed sync returns False."""
        with patch("server.routers.beads_api._run_bd") as mock_run:
            mock_run.return_value = {"error": "Remote not configured"}

            result = await self._sync_beads(tmp_path)

        assert result is False

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_sync_is_best_effort(self, tmp_path):
        """Test sync failure doesn't raise exception."""
        with patch("server.routers.beads_api._run_bd") as mock_run:
            mock_run.return_value = {"error": "Network error"}

            # Should not raise
            result = await self._sync_beads(tmp_path)

        assert result is False


class TestRunBeadsCommand:
    """Tests for run_beads_command (read operations)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from server.routers.beads_api import run_beads_command
        self.run_beads_command = run_beads_command

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_syncs_before_read(self, beads_api_project, mock_beads_locks):
        """Test that sync is called before read command."""
        project_name = beads_api_project["project_name"]
        project_dir = beads_api_project["project_dir"]

        sync_called = False

        async def mock_sync(path):
            nonlocal sync_called
            sync_called = True
            return True

        with patch("server.routers.beads_api._get_project_path") as mock_path:
            mock_path.return_value = project_dir

            with patch("server.routers.beads_api._sync_beads", mock_sync):
                with patch("server.routers.beads_api._run_bd") as mock_run:
                    mock_run.return_value = {"success": True, "data": []}

                    await self.run_beads_command(project_name, ["list", "--json"])

        assert sync_called is True

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_project_not_found(self, mock_beads_locks):
        """Test error when project not found."""
        with patch("server.routers.beads_api._get_project_path") as mock_path:
            mock_path.return_value = None

            result = await self.run_beads_command("nonexistent", ["list"])

        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_project_dir_not_exists(self, tmp_path, mock_beads_locks):
        """Test error when project directory doesn't exist."""
        non_existent = tmp_path / "nonexistent"

        with patch("server.routers.beads_api._get_project_path") as mock_path:
            mock_path.return_value = non_existent

            result = await self.run_beads_command("test", ["list"])

        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_uses_per_project_lock(self, beads_api_project, mock_beads_locks):
        """Test that operations use per-project locking."""
        project_name = beads_api_project["project_name"]
        project_dir = beads_api_project["project_dir"]

        with patch("server.routers.beads_api._get_project_path") as mock_path:
            mock_path.return_value = project_dir

            with patch("server.routers.beads_api._sync_beads") as mock_sync:
                mock_sync.return_value = True

                with patch("server.routers.beads_api._run_bd") as mock_run:
                    mock_run.return_value = {"success": True, "data": []}

                    await self.run_beads_command(project_name, ["list"])

        # Lock should have been created for project
        assert project_name in mock_beads_locks


class TestRunBeadsWriteCommand:
    """Tests for run_beads_write_command (write operations)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from server.routers.beads_api import run_beads_write_command
        self.run_beads_write_command = run_beads_write_command

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_syncs_after_successful_write(self, beads_api_project, mock_beads_locks):
        """Test that sync is called after successful write."""
        project_name = beads_api_project["project_name"]
        project_dir = beads_api_project["project_dir"]

        sync_call_count = 0

        async def mock_sync(path):
            nonlocal sync_call_count
            sync_call_count += 1
            return True

        with patch("server.routers.beads_api._get_project_path") as mock_path:
            mock_path.return_value = project_dir

            with patch("server.routers.beads_api._sync_beads", mock_sync):
                with patch("server.routers.beads_api._run_bd") as mock_run:
                    mock_run.return_value = {"success": True}

                    await self.run_beads_write_command(project_name, ["close", "feat-1"])

        assert sync_call_count == 1

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_no_sync_after_failed_write(self, beads_api_project, mock_beads_locks):
        """Test that sync is NOT called after failed write."""
        project_name = beads_api_project["project_name"]
        project_dir = beads_api_project["project_dir"]

        sync_called = False

        async def mock_sync(path):
            nonlocal sync_called
            sync_called = True
            return True

        with patch("server.routers.beads_api._get_project_path") as mock_path:
            mock_path.return_value = project_dir

            with patch("server.routers.beads_api._sync_beads", mock_sync):
                with patch("server.routers.beads_api._run_bd") as mock_run:
                    mock_run.return_value = {"error": "Write failed"}

                    await self.run_beads_write_command(project_name, ["close", "nonexistent"])

        assert sync_called is False

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_write_uses_lock(self, beads_api_project, mock_beads_locks):
        """Test that write operations use per-project locking."""
        project_name = beads_api_project["project_name"]
        project_dir = beads_api_project["project_dir"]

        with patch("server.routers.beads_api._get_project_path") as mock_path:
            mock_path.return_value = project_dir

            with patch("server.routers.beads_api._sync_beads") as mock_sync:
                mock_sync.return_value = True

                with patch("server.routers.beads_api._run_bd") as mock_run:
                    mock_run.return_value = {"success": True}

                    await self.run_beads_write_command(project_name, ["create", "--title", "Test"])

        assert project_name in mock_beads_locks

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_project_not_found(self, mock_beads_locks):
        """Test error when project not found for write."""
        with patch("server.routers.beads_api._get_project_path") as mock_path:
            mock_path.return_value = None

            result = await self.run_beads_write_command("nonexistent", ["close", "feat-1"])

        assert "error" in result
        assert "not found" in result["error"]


class TestConcurrencyControl:
    """Tests for concurrent operation handling."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_operations_serialize_per_project(self, beads_api_project, mock_beads_locks):
        """Test that operations on same project are serialized."""
        from server.routers.beads_api import run_beads_command

        project_name = beads_api_project["project_name"]
        project_dir = beads_api_project["project_dir"]

        call_order = []

        async def slow_run(path, args, timeout=60):
            call_order.append(("start", args[0]))
            await asyncio.sleep(0.1)
            call_order.append(("end", args[0]))
            return {"success": True, "data": []}

        with patch("server.routers.beads_api._get_project_path") as mock_path:
            mock_path.return_value = project_dir

            with patch("server.routers.beads_api._sync_beads") as mock_sync:
                mock_sync.return_value = True

                with patch("server.routers.beads_api._run_bd", slow_run):
                    # Start two concurrent operations
                    task1 = asyncio.create_task(
                        run_beads_command(project_name, ["list"])
                    )
                    task2 = asyncio.create_task(
                        run_beads_command(project_name, ["ready"])
                    )

                    await asyncio.gather(task1, task2)

        # Operations should be serialized - first should complete before second starts
        # Due to lock, we expect: start list, end list, start ready, end ready
        starts = [c for c in call_order if c[0] == "start"]
        ends = [c for c in call_order if c[0] == "end"]

        # First start should be before first end
        assert call_order.index(starts[0]) < call_order.index(ends[0])
