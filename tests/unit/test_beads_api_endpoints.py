"""
Beads API Endpoints Unit Tests
==============================

Unit tests for each endpoint handler in beads_api.py with mocking:
- list_issues - GET /list (success, empty, status filter, errors)
- ready_issues - GET /ready (unblocked issues)
- show_issue - GET /show/{id} (found, not found 404)
- stats - GET /stats (statistics object)
- create_issue - POST /create (validation, priority conversion)
- update_issue - PATCH /update/{id} (partial update, no fields = 400)
- close_issue - POST /close/{id} (with/without reason)
- reopen_issue - POST /reopen/{id}
- sync_issues - POST /sync
- add_dependency - POST /dep/add
- add_comment - POST /comments/{id}
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import HTTPException


class TestListIssuesEndpoint:
    """Tests for GET /list endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import endpoint after path setup."""
        from server.routers.beads_api import list_issues
        self.list_issues = list_issues

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_list_issues_success(self, mock_beads_locks):
        """Test successful listing of issues."""
        issues = [
            {"id": "feat-1", "title": "Test 1", "status": "open"},
            {"id": "feat-2", "title": "Test 2", "status": "closed"},
        ]

        with patch("server.routers.beads_api.run_beads_command") as mock_cmd:
            mock_cmd.return_value = {"success": True, "data": issues}

            result = await self.list_issues("valid-project")

        assert result == issues

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_list_issues_empty(self, mock_beads_locks):
        """Test listing issues when none exist."""
        with patch("server.routers.beads_api.run_beads_command") as mock_cmd:
            mock_cmd.return_value = {"success": True, "data": []}

            result = await self.list_issues("empty-project")

        assert result == []

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_list_issues_with_status_filter(self, mock_beads_locks):
        """Test listing issues with status filter."""
        with patch("server.routers.beads_api.run_beads_command") as mock_cmd:
            mock_cmd.return_value = {"success": True, "data": []}

            await self.list_issues("project", status="open")

        # Check that status was passed to command
        call_args = mock_cmd.call_args[0]
        assert "--status" in call_args[1]
        assert "open" in call_args[1]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_list_issues_error(self, mock_beads_locks):
        """Test list issues error handling."""
        with patch("server.routers.beads_api.run_beads_command") as mock_cmd:
            mock_cmd.return_value = {"error": "Command failed"}

            with pytest.raises(HTTPException) as exc_info:
                await self.list_issues("project")

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_list_issues_invalid_project_name(self):
        """Test list issues with invalid project name."""
        with pytest.raises(HTTPException) as exc_info:
            await self.list_issues("../invalid")

        assert exc_info.value.status_code == 400


class TestReadyIssuesEndpoint:
    """Tests for GET /ready endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import endpoint after path setup."""
        from server.routers.beads_api import ready_issues
        self.ready_issues = ready_issues

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_ready_issues_success(self, mock_beads_locks):
        """Test getting ready (unblocked) issues."""
        issues = [
            {"id": "feat-1", "title": "Ready Issue", "status": "open"},
        ]

        with patch("server.routers.beads_api.run_beads_command") as mock_cmd:
            mock_cmd.return_value = {"success": True, "data": issues}

            result = await self.ready_issues("project")

        assert len(result) == 1
        assert result[0]["id"] == "feat-1"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_ready_issues_empty(self, mock_beads_locks):
        """Test when no issues are ready."""
        with patch("server.routers.beads_api.run_beads_command") as mock_cmd:
            mock_cmd.return_value = {"success": True, "data": []}

            result = await self.ready_issues("project")

        assert result == []

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_ready_issues_calls_correct_command(self, mock_beads_locks):
        """Test that ready endpoint calls correct bd command."""
        with patch("server.routers.beads_api.run_beads_command") as mock_cmd:
            mock_cmd.return_value = {"success": True, "data": []}

            await self.ready_issues("project")

        call_args = mock_cmd.call_args[0]
        assert "ready" in call_args[1]
        assert "--json" in call_args[1]


class TestShowIssueEndpoint:
    """Tests for GET /show/{id} endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import endpoint after path setup."""
        from server.routers.beads_api import show_issue
        self.show_issue = show_issue

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_show_issue_found(self, mock_beads_locks):
        """Test showing existing issue."""
        issue = {"id": "feat-1", "title": "Test Issue", "status": "open"}

        with patch("server.routers.beads_api.run_beads_command") as mock_cmd:
            mock_cmd.return_value = {"success": True, "data": [issue]}

            result = await self.show_issue("project", "feat-1")

        assert result["id"] == "feat-1"
        assert result["title"] == "Test Issue"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_show_issue_not_found(self, mock_beads_locks):
        """Test showing non-existent issue."""
        with patch("server.routers.beads_api.run_beads_command") as mock_cmd:
            mock_cmd.return_value = {"error": "Issue not found"}

            with pytest.raises(HTTPException) as exc_info:
                await self.show_issue("project", "nonexistent-1")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_show_issue_invalid_id_format(self):
        """Test showing issue with invalid ID format."""
        with pytest.raises(HTTPException) as exc_info:
            await self.show_issue("project", "invalid")

        assert exc_info.value.status_code == 400
        assert "Invalid issue ID" in exc_info.value.detail

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_show_issue_handles_dict_response(self, mock_beads_locks):
        """Test show handles dict response (not list)."""
        issue = {"id": "feat-1", "title": "Test"}

        with patch("server.routers.beads_api.run_beads_command") as mock_cmd:
            mock_cmd.return_value = {"success": True, "data": issue}

            result = await self.show_issue("project", "feat-1")

        assert result["id"] == "feat-1"


class TestStatsEndpoint:
    """Tests for GET /stats endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import endpoint after path setup."""
        from server.routers.beads_api import stats
        self.stats = stats

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_stats_success(self, mock_beads_locks):
        """Test getting project statistics."""
        stats_data = {
            "open": 5,
            "in_progress": 2,
            "closed": 10,
            "blocked": 1,
        }

        with patch("server.routers.beads_api.run_beads_command") as mock_cmd:
            mock_cmd.return_value = {"success": True, "data": stats_data}

            result = await self.stats("project")

        assert result["open"] == 5
        assert result["closed"] == 10

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_stats_handles_output_field(self, mock_beads_locks):
        """Test stats handles 'output' field fallback."""
        with patch("server.routers.beads_api.run_beads_command") as mock_cmd:
            mock_cmd.return_value = {"success": True, "output": "Stats output"}

            result = await self.stats("project")

        assert result == "Stats output"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_stats_error(self, mock_beads_locks):
        """Test stats error handling."""
        with patch("server.routers.beads_api.run_beads_command") as mock_cmd:
            mock_cmd.return_value = {"error": "Failed to get stats"}

            with pytest.raises(HTTPException) as exc_info:
                await self.stats("project")

        assert exc_info.value.status_code == 500


class TestCreateIssueEndpoint:
    """Tests for POST /create endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import endpoint and model after path setup."""
        from server.routers.beads_api import create_issue, IssueCreate
        self.create_issue = create_issue
        self.IssueCreate = IssueCreate

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_create_issue_success(self, mock_beads_locks, issue_create_payload):
        """Test successful issue creation."""
        created_issue = {"id": "feat-1", "title": issue_create_payload["title"]}

        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True, "data": created_issue}

            issue = self.IssueCreate(**issue_create_payload)
            result = await self.create_issue("project", issue)

        assert result["id"] == "feat-1"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_create_issue_priority_conversion(self, mock_beads_locks):
        """Test priority is converted to P-notation."""
        issue = self.IssueCreate(title="Test", priority=0)

        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True, "data": {"id": "feat-1"}}

            await self.create_issue("project", issue)

        # Check priority was converted to P0
        call_args = mock_cmd.call_args[0]
        assert "--priority" in call_args[1]
        assert "P0" in call_args[1]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_create_issue_with_labels(self, mock_beads_locks):
        """Test creating issue with labels."""
        issue = self.IssueCreate(
            title="Test",
            labels=["auth", "critical"],
        )

        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True, "data": {"id": "feat-1"}}

            await self.create_issue("project", issue)

        call_args = mock_cmd.call_args[0]
        assert "--labels" in call_args[1]
        # Labels should be comma-separated
        labels_index = call_args[1].index("--labels") + 1
        assert "auth,critical" in call_args[1][labels_index]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_create_issue_with_description(self, mock_beads_locks):
        """Test creating issue with description."""
        issue = self.IssueCreate(
            title="Test",
            description="Detailed description",
        )

        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True, "data": {"id": "feat-1"}}

            await self.create_issue("project", issue)

        call_args = mock_cmd.call_args[0]
        assert "--description" in call_args[1]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_create_issue_error(self, mock_beads_locks):
        """Test create issue error handling."""
        issue = self.IssueCreate(title="Test")

        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"error": "Creation failed"}

            with pytest.raises(HTTPException) as exc_info:
                await self.create_issue("project", issue)

        assert exc_info.value.status_code == 500


class TestUpdateIssueEndpoint:
    """Tests for PATCH /update/{id} endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import endpoint and model after path setup."""
        from server.routers.beads_api import update_issue, IssueUpdate
        self.update_issue = update_issue
        self.IssueUpdate = IssueUpdate

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_update_issue_success(self, mock_beads_locks):
        """Test successful issue update."""
        update = self.IssueUpdate(title="Updated Title")

        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            result = await self.update_issue("project", "feat-1", update)

        assert result["success"] is True

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_update_issue_no_fields_error(self, mock_beads_locks):
        """Test update with no fields raises error."""
        update = self.IssueUpdate()  # No fields set

        with pytest.raises(HTTPException) as exc_info:
            await self.update_issue("project", "feat-1", update)

        assert exc_info.value.status_code == 400
        assert "No update fields" in exc_info.value.detail

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_update_issue_partial(self, mock_beads_locks):
        """Test partial update (only some fields)."""
        update = self.IssueUpdate(status="in_progress")

        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            await self.update_issue("project", "feat-1", update)

        call_args = mock_cmd.call_args[0]
        args = call_args[1]
        assert "--status" in args
        assert "--title" not in args  # Not provided, not included

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_update_issue_not_found(self, mock_beads_locks):
        """Test update non-existent issue."""
        update = self.IssueUpdate(title="Updated")

        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"error": "Issue not found"}

            with pytest.raises(HTTPException) as exc_info:
                await self.update_issue("project", "nonexistent-1", update)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_update_issue_priority_conversion(self, mock_beads_locks):
        """Test priority is converted to P-notation on update."""
        update = self.IssueUpdate(priority=0)

        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            await self.update_issue("project", "feat-1", update)

        call_args = mock_cmd.call_args[0]
        assert "--priority" in call_args[1]
        assert "P0" in call_args[1]


class TestCloseIssueEndpoint:
    """Tests for POST /close/{id} endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import endpoint and model after path setup."""
        from server.routers.beads_api import close_issue, IssueClose
        self.close_issue = close_issue
        self.IssueClose = IssueClose

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_close_issue_success(self, mock_beads_locks):
        """Test successful issue close."""
        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            result = await self.close_issue("project", "feat-1")

        assert result["success"] is True
        assert "closed" in result["message"].lower()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_close_issue_with_reason(self, mock_beads_locks):
        """Test closing issue with reason."""
        body = self.IssueClose(reason="Fixed in commit abc123")

        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            await self.close_issue("project", "feat-1", body)

        call_args = mock_cmd.call_args[0]
        assert "--reason" in call_args[1]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_close_issue_without_body(self, mock_beads_locks):
        """Test closing issue without body (no reason)."""
        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            await self.close_issue("project", "feat-1", None)

        call_args = mock_cmd.call_args[0]
        assert "--reason" not in call_args[1]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_close_issue_not_found(self, mock_beads_locks):
        """Test closing non-existent issue."""
        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"error": "Issue not found"}

            with pytest.raises(HTTPException) as exc_info:
                await self.close_issue("project", "nonexistent-1")

        assert exc_info.value.status_code == 404


class TestReopenIssueEndpoint:
    """Tests for POST /reopen/{id} endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import endpoint after path setup."""
        from server.routers.beads_api import reopen_issue
        self.reopen_issue = reopen_issue

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_reopen_issue_success(self, mock_beads_locks):
        """Test successful issue reopen."""
        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            result = await self.reopen_issue("project", "feat-1")

        assert result["success"] is True
        assert "reopened" in result["message"].lower()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_reopen_issue_not_found(self, mock_beads_locks):
        """Test reopening non-existent issue."""
        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"error": "Issue not found"}

            with pytest.raises(HTTPException) as exc_info:
                await self.reopen_issue("project", "nonexistent-1")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_reopen_calls_correct_command(self, mock_beads_locks):
        """Test reopen calls correct bd command."""
        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            await self.reopen_issue("project", "feat-1")

        call_args = mock_cmd.call_args[0]
        assert "reopen" in call_args[1]
        assert "feat-1" in call_args[1]


class TestSyncIssuesEndpoint:
    """Tests for POST /sync endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import endpoint after path setup."""
        from server.routers.beads_api import sync_issues
        self.sync_issues = sync_issues

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_sync_success(self, mock_beads_locks):
        """Test successful sync."""
        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            result = await self.sync_issues("project")

        assert result["success"] is True
        assert "synced" in result["message"].lower()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_sync_error(self, mock_beads_locks):
        """Test sync error handling."""
        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"error": "Remote not configured"}

            with pytest.raises(HTTPException) as exc_info:
                await self.sync_issues("project")

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_sync_calls_correct_command(self, mock_beads_locks):
        """Test sync calls correct bd command."""
        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            await self.sync_issues("project")

        call_args = mock_cmd.call_args[0]
        assert "sync" in call_args[1]


class TestAddDependencyEndpoint:
    """Tests for POST /dep/add endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import endpoint after path setup."""
        from server.routers.beads_api import add_dependency
        self.add_dependency = add_dependency

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_add_dependency_success(self, mock_beads_locks):
        """Test successful dependency addition."""
        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            result = await self.add_dependency("project", "feat-2", "feat-1")

        assert result["success"] is True
        assert "depends on" in result["message"].lower()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_add_dependency_validates_ids(self):
        """Test that dependency validates issue IDs."""
        # Invalid issue_id
        with pytest.raises(HTTPException) as exc_info:
            await self.add_dependency("project", "invalid", "feat-1")
        assert exc_info.value.status_code == 400

        # Invalid depends_on
        with pytest.raises(HTTPException) as exc_info:
            await self.add_dependency("project", "feat-1", "invalid")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_add_dependency_calls_correct_command(self, mock_beads_locks):
        """Test add dependency calls correct bd command."""
        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            await self.add_dependency("project", "feat-2", "feat-1")

        call_args = mock_cmd.call_args[0]
        args = call_args[1]
        assert "dep" in args
        assert "add" in args
        assert "feat-2" in args
        assert "feat-1" in args

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_add_dependency_error(self, mock_beads_locks):
        """Test add dependency error handling."""
        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"error": "Circular dependency detected"}

            with pytest.raises(HTTPException) as exc_info:
                await self.add_dependency("project", "feat-2", "feat-1")

        assert exc_info.value.status_code == 500


class TestAddCommentEndpoint:
    """Tests for POST /comments/{id} endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import endpoint and model after path setup."""
        from server.routers.beads_api import add_comment, CommentAdd
        self.add_comment = add_comment
        self.CommentAdd = CommentAdd

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_add_comment_success(self, mock_beads_locks):
        """Test successful comment addition."""
        body = self.CommentAdd(comment="This is a comment")

        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            result = await self.add_comment("project", "feat-1", body)

        assert result["success"] is True
        assert "added" in result["message"].lower()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_add_comment_calls_correct_command(self, mock_beads_locks):
        """Test add comment calls correct bd command."""
        body = self.CommentAdd(comment="Test comment")

        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            await self.add_comment("project", "feat-1", body)

        call_args = mock_cmd.call_args[0]
        args = call_args[1]
        assert "comments" in args
        assert "feat-1" in args
        assert "--add" in args
        assert "Test comment" in args

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_add_comment_not_found(self, mock_beads_locks):
        """Test adding comment to non-existent issue."""
        body = self.CommentAdd(comment="Test")

        with patch("server.routers.beads_api.run_beads_write_command") as mock_cmd:
            mock_cmd.return_value = {"error": "Issue not found"}

            with pytest.raises(HTTPException) as exc_info:
                await self.add_comment("project", "nonexistent-1", body)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_add_comment_validates_issue_id(self):
        """Test that add comment validates issue ID format."""
        body = self.CommentAdd(comment="Test")

        with pytest.raises(HTTPException) as exc_info:
            await self.add_comment("project", "invalid", body)

        assert exc_info.value.status_code == 400


class TestEndpointProjectValidation:
    """Tests for project name validation across all endpoints."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_list_validates_project(self):
        """Test list endpoint validates project name."""
        from server.routers.beads_api import list_issues

        with pytest.raises(HTTPException) as exc_info:
            await list_issues("../traversal")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_ready_validates_project(self):
        """Test ready endpoint validates project name."""
        from server.routers.beads_api import ready_issues

        with pytest.raises(HTTPException) as exc_info:
            await ready_issues("project with spaces")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_stats_validates_project(self):
        """Test stats endpoint validates project name."""
        from server.routers.beads_api import stats

        with pytest.raises(HTTPException) as exc_info:
            await stats("project!")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_sync_validates_project(self):
        """Test sync endpoint validates project name."""
        from server.routers.beads_api import sync_issues

        with pytest.raises(HTTPException) as exc_info:
            await sync_issues("/etc/passwd")
        assert exc_info.value.status_code == 400


class TestEndpointIssueIdValidation:
    """Tests for issue ID validation across relevant endpoints."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_show_validates_issue_id(self):
        """Test show endpoint validates issue ID."""
        from server.routers.beads_api import show_issue

        with pytest.raises(HTTPException) as exc_info:
            await show_issue("project", "notvalid")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_update_validates_issue_id(self):
        """Test update endpoint validates issue ID."""
        from server.routers.beads_api import update_issue, IssueUpdate

        update = IssueUpdate(title="Test")

        with pytest.raises(HTTPException) as exc_info:
            await update_issue("project", "123", update)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_close_validates_issue_id(self):
        """Test close endpoint validates issue ID."""
        from server.routers.beads_api import close_issue

        with pytest.raises(HTTPException) as exc_info:
            await close_issue("project", "no-hyphen-number")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_reopen_validates_issue_id(self):
        """Test reopen endpoint validates issue ID."""
        from server.routers.beads_api import reopen_issue

        with pytest.raises(HTTPException) as exc_info:
            await reopen_issue("project", "@invalid")
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_comment_validates_issue_id(self):
        """Test comment endpoint validates issue ID."""
        from server.routers.beads_api import add_comment, CommentAdd

        body = CommentAdd(comment="test")

        with pytest.raises(HTTPException) as exc_info:
            await add_comment("project", "invalid id", body)
        assert exc_info.value.status_code == 400
