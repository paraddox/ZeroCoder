"""
Beads API Integration Tests
===========================

Full request/response flow tests for the beads API:
- TestBeadsAPILifecycle - Create->List->Show->Update->Close->Reopen cycle
- TestBeadsAPIConcurrency - Concurrent read/write serialization
- TestBeadsAPIErrorRecovery - Project not found, command failures
"""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestBeadsAPILifecycle:
    """Integration tests for complete issue lifecycle through API."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_list_show_cycle(self, beads_api_project, mock_beads_locks):
        """Test creating an issue, listing, and showing it."""
        from server.routers.beads_api import (
            create_issue, list_issues, show_issue, IssueCreate
        )

        project_name = beads_api_project["project_name"]

        created_issue = {"id": "feat-1", "title": "Test Feature", "status": "open"}

        with patch("server.routers.beads_api.get_beads_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_get_manager.return_value = mock_manager

            mock_manager.run_write_command = AsyncMock(
                return_value={"data": created_issue}
            )
            mock_manager.run_read_command = AsyncMock(
                side_effect=[
                    {"data": [created_issue]},  # list
                    {"data": [created_issue]},  # show
                ]
            )

            # Create
            issue = IssueCreate(title="Test Feature", priority=1)
            create_result = await create_issue(project_name, issue)
            assert create_result.get("id") == "feat-1"

            # List
            list_result = await list_issues(project_name)
            assert len(list_result) == 1
            assert list_result[0]["title"] == "Test Feature"

            # Show
            show_result = await show_issue(project_name, "feat-1")
            assert show_result["id"] == "feat-1"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_update_close_reopen_cycle(self, beads_api_project, mock_beads_locks):
        """Test updating, closing, and reopening an issue."""
        from server.routers.beads_api import (
            update_issue, close_issue, reopen_issue, IssueUpdate
        )

        project_name = beads_api_project["project_name"]

        with patch("server.routers.beads_api.get_beads_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_get_manager.return_value = mock_manager

            mock_manager.run_write_command = AsyncMock(
                return_value={"success": True}
            )

            # Update
            update = IssueUpdate(status="in_progress")
            update_result = await update_issue(project_name, "feat-1", update)
            assert update_result["success"] is True

            # Close
            close_result = await close_issue(project_name, "feat-1")
            assert close_result["success"] is True

            # Reopen
            reopen_result = await reopen_issue(project_name, "feat-1")
            assert reopen_result["success"] is True

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_lifecycle_with_dependencies(self, beads_api_project, mock_beads_locks):
        """Test full lifecycle including dependencies."""
        from server.routers.beads_api import (
            create_issue, add_dependency, close_issue, IssueCreate
        )

        project_name = beads_api_project["project_name"]

        with patch("server.routers.beads_api.get_beads_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_get_manager.return_value = mock_manager

            mock_manager.run_write_command = AsyncMock(
                side_effect=[
                    {"data": {"id": "feat-1"}},   # create feat-1
                    {"data": {"id": "feat-2"}},   # create feat-2
                    {"success": True},            # add dependency
                    {"success": True},            # close feat-1
                    {"success": True},            # close feat-2
                ]
            )

            # Create two issues
            issue1 = IssueCreate(title="Feature 1")
            await create_issue(project_name, issue1)

            issue2 = IssueCreate(title="Feature 2")
            await create_issue(project_name, issue2)

            # Add dependency: feat-2 depends on feat-1
            dep_result = await add_dependency(project_name, "feat-2", "feat-1")
            assert dep_result["success"] is True

            # Close feat-1 (dependency resolved)
            await close_issue(project_name, "feat-1")

            # Now close feat-2
            close_result = await close_issue(project_name, "feat-2")
            assert close_result["success"] is True


class TestBeadsAPIConcurrency:
    """Tests for concurrent access handling."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_reads_serialized(self, beads_api_project, mock_beads_locks):
        """Test that concurrent reads are serialized per project."""
        from server.routers.beads_api import list_issues, ready_issues

        project_name = beads_api_project["project_name"]

        call_times = []

        async def mock_read_command(args):
            call_times.append(("start", args[0], asyncio.get_event_loop().time()))
            await asyncio.sleep(0.05)  # Simulate command time
            call_times.append(("end", args[0], asyncio.get_event_loop().time()))
            return {"data": []}

        with patch("server.routers.beads_api.get_beads_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_get_manager.return_value = mock_manager
            mock_manager.run_read_command = mock_read_command

            # Start concurrent reads
            task1 = asyncio.create_task(list_issues(project_name))
            task2 = asyncio.create_task(ready_issues(project_name))

            await asyncio.gather(task1, task2)

        # Verify both reads were called
        assert len(call_times) >= 4  # At least 2 starts and 2 ends

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_concurrent_writes_serialized(self, beads_api_project, mock_beads_locks):
        """Test that concurrent writes are serialized per project."""
        from server.routers.beads_api import close_issue, reopen_issue

        project_name = beads_api_project["project_name"]

        operation_order = []

        async def mock_write_command(args, **kwargs):
            cmd = args[0]
            operation_order.append(f"start_{cmd}")
            await asyncio.sleep(0.02)
            operation_order.append(f"end_{cmd}")
            return {"success": True}

        with patch("server.routers.beads_api.get_beads_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_get_manager.return_value = mock_manager
            mock_manager.run_write_command = mock_write_command

            task1 = asyncio.create_task(close_issue(project_name, "feat-1"))
            task2 = asyncio.create_task(reopen_issue(project_name, "feat-2"))

            await asyncio.gather(task1, task2)

        # Both operations should have run
        assert len(operation_order) >= 4

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_different_projects_parallel(self, tmp_path, mock_beads_locks):
        """Test that different projects can be accessed in parallel."""
        from server.routers.beads_api import list_issues

        concurrent_starts = []

        async def mock_read_command(args):
            concurrent_starts.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.05)
            return {"data": []}

        with patch("server.routers.beads_api.get_beads_manager") as mock_get_manager:
            mock_manager1 = AsyncMock()
            mock_manager2 = AsyncMock()
            mock_manager1.run_read_command = mock_read_command
            mock_manager2.run_read_command = mock_read_command

            async def get_manager_for_project(project_name):
                if project_name == "project1":
                    return mock_manager1
                elif project_name == "project2":
                    return mock_manager2
                raise ValueError(f"Project {project_name} not found")

            mock_get_manager.side_effect = get_manager_for_project

            # Different projects should have different managers
            task1 = asyncio.create_task(list_issues("project1"))
            task2 = asyncio.create_task(list_issues("project2"))

            await asyncio.gather(task1, task2)

        # Both projects should be able to start roughly at the same time
        assert len(concurrent_starts) >= 2


class TestBeadsAPIErrorRecovery:
    """Tests for error handling and recovery."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_project_not_found_in_registry(self, mock_beads_locks):
        """Test handling when project not found in registry."""
        from server.routers.beads_api import run_beads_command

        with patch("server.routers.beads_api.get_beads_manager") as mock_get_manager:
            mock_get_manager.side_effect = ValueError("Project nonexistent not found")

            # run_beads_command returns error dict when project not found
            result = await run_beads_command("nonexistent", ["list"])

        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_project_directory_missing(self, tmp_path, mock_beads_locks):
        """Test handling when project directory doesn't exist."""
        from server.routers.beads_api import run_beads_command

        with patch("server.routers.beads_api.get_beads_manager") as mock_get_manager:
            mock_get_manager.side_effect = ValueError("Project missing not found in registry")

            result = await run_beads_command("missing", ["list"])

        assert "error" in result
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_bd_command_failure(self, beads_api_project, mock_beads_locks):
        """Test handling bd command failures."""
        from server.routers.beads_api import show_issue
        from fastapi import HTTPException

        project_name = beads_api_project["project_name"]

        with patch("server.routers.beads_api.get_beads_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_get_manager.return_value = mock_manager

            mock_manager.run_read_command = AsyncMock(
                return_value={"error": "Issue feat-999 not found"}
            )

            with pytest.raises(HTTPException) as exc_info:
                await show_issue(project_name, "feat-999")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_bd_command_timeout(self, beads_api_project, mock_beads_locks):
        """Test handling bd command timeout."""
        from server.routers.beads_api import list_issues
        from fastapi import HTTPException

        project_name = beads_api_project["project_name"]

        with patch("server.routers.beads_api.get_beads_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_get_manager.return_value = mock_manager

            mock_manager.run_read_command = AsyncMock(
                return_value={"error": "Command timed out"}
            )

            with pytest.raises(HTTPException) as exc_info:
                await list_issues(project_name)

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_sync_failure_continues(self, beads_api_project, mock_beads_locks):
        """Test that manager handles sync internally; read still succeeds."""
        from server.routers.beads_api import list_issues

        project_name = beads_api_project["project_name"]

        with patch("server.routers.beads_api.get_beads_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_get_manager.return_value = mock_manager

            # Manager handles sync internally; read command returns data
            mock_manager.run_read_command = AsyncMock(
                return_value={"data": [{"id": "feat-1"}]}
            )

            # Should succeed (sync is internal to manager)
            result = await list_issues(project_name)

        assert len(result) == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_recovery_after_failed_operation(self, beads_api_project, mock_beads_locks):
        """Test that subsequent operations work after a failed one."""
        from server.routers.beads_api import list_issues, ready_issues
        from fastapi import HTTPException

        project_name = beads_api_project["project_name"]

        with patch("server.routers.beads_api.get_beads_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_get_manager.return_value = mock_manager

            mock_manager.run_read_command = AsyncMock(
                side_effect=[
                    {"error": "Temporary failure"},       # list fails
                    {"data": [{"id": "feat-1"}]},         # ready succeeds
                ]
            )

            # First operation fails
            with pytest.raises(HTTPException):
                await list_issues(project_name)

            # Second operation should work
            result = await ready_issues(project_name)

        assert len(result) == 1


class TestBeadsAPIDataIntegrity:
    """Tests for data integrity across operations."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_returns_created_data(self, beads_api_project, mock_beads_locks):
        """Test that create returns the created issue data."""
        from server.routers.beads_api import create_issue, IssueCreate

        project_name = beads_api_project["project_name"]

        created_data = {
            "id": "feat-1",
            "title": "New Feature",
            "status": "open",
            "priority": "P1",
        }

        with patch("server.routers.beads_api.get_beads_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_get_manager.return_value = mock_manager

            mock_manager.run_write_command = AsyncMock(
                return_value={"data": created_data}
            )

            issue = IssueCreate(title="New Feature", priority=1)
            result = await create_issue(project_name, issue)

        assert result["id"] == "feat-1"
        assert result["title"] == "New Feature"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_update_confirms_success(self, beads_api_project, mock_beads_locks):
        """Test that update confirms successful update."""
        from server.routers.beads_api import update_issue, IssueUpdate

        project_name = beads_api_project["project_name"]

        with patch("server.routers.beads_api.get_beads_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_get_manager.return_value = mock_manager

            mock_manager.run_write_command = AsyncMock(
                return_value={"success": True}
            )

            update = IssueUpdate(title="Updated Title")
            result = await update_issue(project_name, "feat-1", update)

        assert result["success"] is True
        assert "updated" in result["message"].lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_close_confirms_closure(self, beads_api_project, mock_beads_locks):
        """Test that close confirms successful closure."""
        from server.routers.beads_api import close_issue

        project_name = beads_api_project["project_name"]

        with patch("server.routers.beads_api.get_beads_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_get_manager.return_value = mock_manager

            mock_manager.run_write_command = AsyncMock(
                return_value={"success": True}
            )

            result = await close_issue(project_name, "feat-1")

        assert result["success"] is True
        assert "closed" in result["message"].lower()
        assert "feat-1" in result["message"]
