"""
Task Cleanup Service Unit Tests
===============================

Tests for the task cleanup service including:
- In-progress task reversion
- Beads CLI integration
- Multi-project cleanup
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
# Run BD Command Tests
# =============================================================================

class TestRunBd:
    """Tests for _run_bd helper function."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_error_on_nonzero_exit(self, tmp_path):
        """Test returns error dict when command fails."""
        from server.services.task_cleanup import _run_bd

        with patch("asyncio.to_thread") as mock_thread:
            mock_result = MagicMock(
                returncode=1,
                stderr="Command failed"
            )
            mock_thread.return_value = mock_result

            result = await _run_bd(tmp_path, ["list"])

        assert "error" in result
        assert "Command failed" in result["error"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_success_on_empty_output(self, tmp_path):
        """Test returns success when output is empty."""
        from server.services.task_cleanup import _run_bd

        with patch("asyncio.to_thread") as mock_thread:
            mock_result = MagicMock(
                returncode=0,
                stdout=""
            )
            mock_thread.return_value = mock_result

            result = await _run_bd(tmp_path, ["sync"])

        assert result == {"success": True}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parses_json_output(self, tmp_path):
        """Test parses JSON output when available."""
        from server.services.task_cleanup import _run_bd

        json_data = [{"id": "feat-1", "status": "open"}]

        with patch("asyncio.to_thread") as mock_thread:
            mock_result = MagicMock(
                returncode=0,
                stdout=json.dumps(json_data)
            )
            mock_thread.return_value = mock_result

            result = await _run_bd(tmp_path, ["list", "--json"])

        assert result["success"] is True
        assert result["data"] == json_data

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_raw_output_on_json_parse_failure(self, tmp_path):
        """Test returns raw output when JSON parsing fails."""
        from server.services.task_cleanup import _run_bd

        with patch("asyncio.to_thread") as mock_thread:
            mock_result = MagicMock(
                returncode=0,
                stdout="Not JSON output"
            )
            mock_thread.return_value = mock_result

            result = await _run_bd(tmp_path, ["list"])

        assert result["success"] is True
        assert result["output"] == "Not JSON output"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handles_exception(self, tmp_path):
        """Test handles exceptions gracefully."""
        from server.services.task_cleanup import _run_bd

        with patch("asyncio.to_thread") as mock_thread:
            mock_thread.side_effect = Exception("Network timeout")

            result = await _run_bd(tmp_path, ["list"])

        assert "error" in result
        assert "Network timeout" in result["error"]


# =============================================================================
# Single Project Reversion Tests
# =============================================================================

class TestRevertInProgressTasksForProject:
    """Tests for revert_in_progress_tasks_for_project function."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_zero_when_list_fails(self, tmp_path):
        """Test returns 0 when list command fails."""
        from server.services.task_cleanup import revert_in_progress_tasks_for_project

        with patch("server.services.task_cleanup._run_bd") as mock_bd:
            mock_bd.return_value = {"error": "Command failed"}

            result = await revert_in_progress_tasks_for_project(
                "test-project", tmp_path
            )

        assert result == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_zero_when_no_in_progress_tasks(self, tmp_path):
        """Test returns 0 when no in_progress tasks found."""
        from server.services.task_cleanup import revert_in_progress_tasks_for_project

        with patch("server.services.task_cleanup._run_bd") as mock_bd:
            mock_bd.return_value = {"success": True, "data": []}

            result = await revert_in_progress_tasks_for_project(
                "test-project", tmp_path
            )

        assert result == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_reverts_in_progress_tasks(self, tmp_path):
        """Test reverts in_progress tasks to open."""
        from server.services.task_cleanup import revert_in_progress_tasks_for_project

        tasks = [
            {"id": "feat-1", "status": "in_progress"},
            {"id": "feat-2", "status": "in_progress"},
        ]

        call_count = 0

        async def mock_run_bd(path, args):
            nonlocal call_count
            call_count += 1
            if args == ["list", "--json", "--status", "in_progress"]:
                return {"success": True, "data": tasks}
            elif args[0] == "update":
                return {"success": True}
            elif args == ["sync"]:
                return {"success": True}
            return {"error": "Unknown command"}

        with patch("server.services.task_cleanup._run_bd", side_effect=mock_run_bd):
            result = await revert_in_progress_tasks_for_project(
                "test-project", tmp_path
            )

        assert result == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handles_update_failure(self, tmp_path):
        """Test handles individual task update failure."""
        from server.services.task_cleanup import revert_in_progress_tasks_for_project

        tasks = [
            {"id": "feat-1", "status": "in_progress"},
            {"id": "feat-2", "status": "in_progress"},
        ]

        async def mock_run_bd(path, args):
            if args == ["list", "--json", "--status", "in_progress"]:
                return {"success": True, "data": tasks}
            elif args == ["update", "feat-1", "--status=open"]:
                return {"error": "Update failed"}
            elif args == ["update", "feat-2", "--status=open"]:
                return {"success": True}
            elif args == ["sync"]:
                return {"success": True}
            return {"error": "Unknown command"}

        with patch("server.services.task_cleanup._run_bd", side_effect=mock_run_bd):
            result = await revert_in_progress_tasks_for_project(
                "test-project", tmp_path
            )

        # Only feat-2 should succeed
        assert result == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_skips_tasks_without_id(self, tmp_path):
        """Test skips tasks without ID field."""
        from server.services.task_cleanup import revert_in_progress_tasks_for_project

        tasks = [
            {"id": "feat-1", "status": "in_progress"},
            {"status": "in_progress"},  # No ID
        ]

        async def mock_run_bd(path, args):
            if args == ["list", "--json", "--status", "in_progress"]:
                return {"success": True, "data": tasks}
            elif args[0] == "update":
                return {"success": True}
            elif args == ["sync"]:
                return {"success": True}
            return {"error": "Unknown command"}

        with patch("server.services.task_cleanup._run_bd", side_effect=mock_run_bd):
            result = await revert_in_progress_tasks_for_project(
                "test-project", tmp_path
            )

        # Only feat-1 should be processed
        assert result == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_calls_sync_after_changes(self, tmp_path):
        """Test calls sync after successful changes."""
        from server.services.task_cleanup import revert_in_progress_tasks_for_project

        tasks = [{"id": "feat-1", "status": "in_progress"}]
        sync_called = False

        async def mock_run_bd(path, args):
            nonlocal sync_called
            if args == ["list", "--json", "--status", "in_progress"]:
                return {"success": True, "data": tasks}
            elif args[0] == "update":
                return {"success": True}
            elif args == ["sync"]:
                sync_called = True
                return {"success": True}
            return {"error": "Unknown command"}

        with patch("server.services.task_cleanup._run_bd", side_effect=mock_run_bd):
            await revert_in_progress_tasks_for_project("test-project", tmp_path)

        assert sync_called is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_sync_when_no_changes(self, tmp_path):
        """Test does not call sync when no changes made."""
        from server.services.task_cleanup import revert_in_progress_tasks_for_project

        sync_called = False

        async def mock_run_bd(path, args):
            nonlocal sync_called
            if args == ["list", "--json", "--status", "in_progress"]:
                return {"success": True, "data": []}
            elif args == ["sync"]:
                sync_called = True
                return {"success": True}
            return {"error": "Unknown command"}

        with patch("server.services.task_cleanup._run_bd", side_effect=mock_run_bd):
            await revert_in_progress_tasks_for_project("test-project", tmp_path)

        assert sync_called is False


# =============================================================================
# All Projects Reversion Tests
# =============================================================================

class TestRevertAllInProgressTasks:
    """Tests for revert_all_in_progress_tasks function."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_projects(self):
        """Test returns empty dict when no projects registered."""
        from server.services.task_cleanup import revert_all_in_progress_tasks

        with patch("registry.list_valid_projects") as mock_list:
            mock_list.return_value = []

            result = await revert_all_in_progress_tasks()

        assert result == {}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_processes_multiple_projects(self, tmp_path):
        """Test processes multiple projects."""
        from server.services.task_cleanup import revert_all_in_progress_tasks

        project1_dir = tmp_path / "project1"
        project2_dir = tmp_path / "project2"
        project1_dir.mkdir()
        project2_dir.mkdir()
        (project1_dir / ".beads").mkdir()
        (project2_dir / ".beads").mkdir()

        projects = [
            {"name": "project1"},
            {"name": "project2"},
        ]

        with patch("registry.list_valid_projects") as mock_list:
            mock_list.return_value = projects

            with patch("registry.get_project_path") as mock_path:
                mock_path.side_effect = lambda n: tmp_path / n

                with patch("server.services.task_cleanup.revert_in_progress_tasks_for_project") as mock_revert:
                    mock_revert.side_effect = [2, 1]

                    result = await revert_all_in_progress_tasks()

        assert result == {"project1": 2, "project2": 1}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_skips_projects_without_path(self, tmp_path):
        """Test skips projects without valid path."""
        from server.services.task_cleanup import revert_all_in_progress_tasks

        projects = [{"name": "project1"}]

        with patch("registry.list_valid_projects") as mock_list:
            mock_list.return_value = projects

            with patch("registry.get_project_path") as mock_path:
                mock_path.return_value = None

                result = await revert_all_in_progress_tasks()

        assert result == {}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_skips_projects_without_beads_dir(self, tmp_path):
        """Test skips projects without .beads directory."""
        from server.services.task_cleanup import revert_all_in_progress_tasks

        project_dir = tmp_path / "project1"
        project_dir.mkdir()
        # No .beads directory

        projects = [{"name": "project1"}]

        with patch("registry.list_valid_projects") as mock_list:
            mock_list.return_value = projects

            with patch("registry.get_project_path") as mock_path:
                mock_path.return_value = project_dir

                result = await revert_all_in_progress_tasks()

        assert result == {}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_excludes_projects_with_zero_reverts(self, tmp_path):
        """Test excludes projects with zero reverted tasks."""
        from server.services.task_cleanup import revert_all_in_progress_tasks

        project_dir = tmp_path / "project1"
        project_dir.mkdir()
        (project_dir / ".beads").mkdir()

        projects = [{"name": "project1"}]

        with patch("registry.list_valid_projects") as mock_list:
            mock_list.return_value = projects

            with patch("registry.get_project_path") as mock_path:
                mock_path.return_value = project_dir

                with patch("server.services.task_cleanup.revert_in_progress_tasks_for_project") as mock_revert:
                    mock_revert.return_value = 0

                    result = await revert_all_in_progress_tasks()

        assert result == {}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_skips_nonexistent_paths(self, tmp_path):
        """Test skips paths that don't exist."""
        from server.services.task_cleanup import revert_all_in_progress_tasks

        projects = [{"name": "project1"}]

        with patch("registry.list_valid_projects") as mock_list:
            mock_list.return_value = projects

            with patch("registry.get_project_path") as mock_path:
                mock_path.return_value = tmp_path / "nonexistent"

                result = await revert_all_in_progress_tasks()

        assert result == {}
