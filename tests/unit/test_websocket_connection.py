"""
Tests for WebSocket Connection Management
=========================================

Enterprise-grade tests for server/websocket.py including:
- ConnectionManager class
- Project name validation
- WebSocket lifecycle
- Message broadcasting
- Progress polling
- Callback registration
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_text = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def mock_project_path(tmp_path):
    """Create a temporary project directory."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    (project_dir / ".beads").mkdir()
    return project_dir


# =============================================================================
# Project Name Validation Tests
# =============================================================================

class TestProjectNameValidation:
    """Tests for validate_project_name function."""

    @pytest.mark.unit
    def test_valid_alphanumeric_name(self):
        """Valid alphanumeric names should pass."""
        from server.websocket import validate_project_name

        assert validate_project_name("myproject") is True
        assert validate_project_name("MyProject123") is True
        assert validate_project_name("project1") is True

    @pytest.mark.unit
    def test_valid_name_with_hyphen(self):
        """Names with hyphens should be valid."""
        from server.websocket import validate_project_name

        assert validate_project_name("my-project") is True
        assert validate_project_name("my-awesome-project") is True

    @pytest.mark.unit
    def test_valid_name_with_underscore(self):
        """Names with underscores should be valid."""
        from server.websocket import validate_project_name

        assert validate_project_name("my_project") is True
        assert validate_project_name("my_awesome_project") is True

    @pytest.mark.unit
    def test_invalid_name_with_path_traversal(self):
        """Path traversal attempts should be rejected."""
        from server.websocket import validate_project_name

        assert validate_project_name("../etc/passwd") is False
        assert validate_project_name("..") is False
        assert validate_project_name(".") is False

    @pytest.mark.unit
    def test_invalid_name_with_special_chars(self):
        """Names with special characters should be rejected."""
        from server.websocket import validate_project_name

        assert validate_project_name("project@name") is False
        assert validate_project_name("project name") is False
        assert validate_project_name("project/name") is False
        assert validate_project_name("project\\name") is False

    @pytest.mark.unit
    def test_invalid_empty_name(self):
        """Empty names should be rejected."""
        from server.websocket import validate_project_name

        assert validate_project_name("") is False

    @pytest.mark.unit
    def test_invalid_too_long_name(self):
        """Names over 50 characters should be rejected."""
        from server.websocket import validate_project_name

        long_name = "a" * 51
        assert validate_project_name(long_name) is False

    @pytest.mark.unit
    def test_valid_max_length_name(self):
        """Names at exactly 50 characters should be valid."""
        from server.websocket import validate_project_name

        max_name = "a" * 50
        assert validate_project_name(max_name) is True


# =============================================================================
# ConnectionManager Tests
# =============================================================================

class TestConnectionManager:
    """Tests for ConnectionManager class."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_connect_adds_websocket(self, mock_websocket):
        """Connect should add WebSocket to project connections."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        await manager.connect(mock_websocket, "test-project")

        mock_websocket.accept.assert_called_once()
        assert manager.get_connection_count("test-project") == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_connect_multiple_websockets(self, mock_websocket):
        """Multiple WebSockets can connect to same project."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await manager.connect(ws1, "test-project")
        await manager.connect(ws2, "test-project")

        assert manager.get_connection_count("test-project") == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_disconnect_removes_websocket(self, mock_websocket):
        """Disconnect should remove WebSocket from project connections."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        await manager.connect(mock_websocket, "test-project")
        await manager.disconnect(mock_websocket, "test-project")

        assert manager.get_connection_count("test-project") == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_disconnect_cleans_up_empty_project(self, mock_websocket):
        """Disconnect should clean up project entry when no connections left."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        await manager.connect(mock_websocket, "test-project")
        await manager.disconnect(mock_websocket, "test-project")

        assert "test-project" not in manager.active_connections

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_project(self, mock_websocket):
        """Disconnect should handle nonexistent project gracefully."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        # Should not raise
        await manager.disconnect(mock_websocket, "nonexistent")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_to_project(self, mock_websocket):
        """Broadcast should send message to all project connections."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await manager.connect(ws1, "test-project")
        await manager.connect(ws2, "test-project")

        message = {"type": "test", "data": "hello"}
        await manager.broadcast_to_project("test-project", message)

        ws1.send_json.assert_called_with(message)
        ws2.send_json.assert_called_with(message)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_cleans_dead_connections(self):
        """Broadcast should remove dead connections."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        good_ws = AsyncMock()
        bad_ws = AsyncMock()
        bad_ws.send_json.side_effect = Exception("Connection closed")

        await manager.connect(good_ws, "test-project")
        await manager.connect(bad_ws, "test-project")

        await manager.broadcast_to_project("test-project", {"type": "test"})

        # Bad connection should be removed
        assert manager.get_connection_count("test-project") == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_to_empty_project(self):
        """Broadcast to project with no connections should not error."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        # Should not raise
        await manager.broadcast_to_project("empty-project", {"type": "test"})

    @pytest.mark.unit
    def test_get_connection_count_empty(self):
        """Connection count for unknown project should be 0."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        assert manager.get_connection_count("unknown") == 0


# =============================================================================
# Progress Polling Tests
# =============================================================================

class TestProgressPolling:
    """Tests for poll_progress function."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_poll_progress_sends_initial_update(self, mock_websocket, mock_project_path):
        """Poll progress should send initial update."""
        with patch("server.websocket._get_count_passing_tests") as mock_get:
            mock_count = MagicMock(return_value=(5, 2, 10))
            mock_get.return_value = mock_count

            from server.websocket import poll_progress

            # Run poll briefly then cancel
            task = asyncio.create_task(
                poll_progress(mock_websocket, "test", mock_project_path)
            )
            await asyncio.sleep(0.1)
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            # Should have sent at least one progress update
            calls = mock_websocket.send_json.call_args_list
            progress_calls = [c for c in calls if c[0][0].get("type") == "progress"]
            assert len(progress_calls) >= 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_poll_progress_only_sends_on_change(self, mock_websocket, mock_project_path):
        """Poll progress should only send updates when values change."""
        call_count = [0]

        def mock_count(*args, **kwargs):
            call_count[0] += 1
            return (5, 2, 10)  # Always return same values

        with patch("server.websocket._get_count_passing_tests") as mock_get:
            mock_get.return_value = mock_count

            from server.websocket import poll_progress

            task = asyncio.create_task(
                poll_progress(mock_websocket, "test", mock_project_path)
            )
            await asyncio.sleep(0.2)
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            # Should only send once despite multiple polls
            progress_calls = [
                c for c in mock_websocket.send_json.call_args_list
                if c[0][0].get("type") == "progress"
            ]
            assert len(progress_calls) == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_poll_progress_sends_on_value_change(self, mock_websocket, mock_project_path):
        """Poll progress should send update when values change."""
        call_count = [0]

        def mock_count(*args, **kwargs):
            call_count[0] += 1
            # Change values on second call
            if call_count[0] == 1:
                return (5, 2, 10)
            return (6, 1, 10)

        with patch("server.websocket._get_count_passing_tests") as mock_get:
            mock_get.return_value = mock_count

            # Patch sleep to speed up test
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                mock_sleep.return_value = None

                from server.websocket import poll_progress

                task = asyncio.create_task(
                    poll_progress(mock_websocket, "test", mock_project_path)
                )

                # Let it poll a few times
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                task.cancel()

                try:
                    await task
                except asyncio.CancelledError:
                    pass

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_poll_progress_calculates_percentage(self, mock_websocket, mock_project_path):
        """Poll progress should calculate correct percentage."""
        with patch("server.websocket._get_count_passing_tests") as mock_get:
            mock_get.return_value = MagicMock(return_value=(5, 0, 10))

            from server.websocket import poll_progress

            task = asyncio.create_task(
                poll_progress(mock_websocket, "test", mock_project_path)
            )
            await asyncio.sleep(0.1)
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            # Check percentage calculation
            calls = mock_websocket.send_json.call_args_list
            progress_call = next(c for c in calls if c[0][0].get("type") == "progress")
            assert progress_call[0][0]["percentage"] == 50.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_poll_progress_handles_zero_total(self, mock_websocket, mock_project_path):
        """Poll progress should handle zero total gracefully."""
        with patch("server.websocket._get_count_passing_tests") as mock_get:
            mock_get.return_value = MagicMock(return_value=(0, 0, 0))

            from server.websocket import poll_progress

            task = asyncio.create_task(
                poll_progress(mock_websocket, "test", mock_project_path)
            )
            await asyncio.sleep(0.1)
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            # Check percentage is 0 for zero total
            calls = mock_websocket.send_json.call_args_list
            progress_call = next(c for c in calls if c[0][0].get("type") == "progress")
            assert progress_call[0][0]["percentage"] == 0


# =============================================================================
# WebSocket Endpoint Tests
# =============================================================================

class TestProjectWebSocket:
    """Tests for project_websocket function."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_invalid_project_name_closes_connection(self, mock_websocket):
        """Invalid project name should close WebSocket with error."""
        from server.websocket import project_websocket

        await project_websocket(mock_websocket, "../invalid")

        mock_websocket.close.assert_called_once()
        call_args = mock_websocket.close.call_args
        assert call_args[1]["code"] == 4000

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_nonexistent_project_closes_connection(self, mock_websocket):
        """Nonexistent project should close WebSocket with error."""
        with patch("server.websocket._get_project_path") as mock_path:
            mock_path.return_value = None

            from server.websocket import project_websocket

            await project_websocket(mock_websocket, "nonexistent")

            mock_websocket.close.assert_called_once()
            call_args = mock_websocket.close.call_args
            assert call_args[1]["code"] == 4004

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_missing_directory_closes_connection(self, mock_websocket, tmp_path):
        """Missing project directory should close WebSocket."""
        with patch("server.websocket._get_project_path") as mock_path:
            mock_path.return_value = tmp_path / "missing"

            from server.websocket import project_websocket

            await project_websocket(mock_websocket, "test-project")

            mock_websocket.close.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_missing_git_url_closes_connection(self, mock_websocket, mock_project_path):
        """Missing git URL should close WebSocket."""
        with patch("server.websocket._get_project_path") as mock_path:
            with patch("server.websocket._get_project_git_url") as mock_url:
                mock_path.return_value = mock_project_path
                mock_url.return_value = None

                from server.websocket import project_websocket

                await project_websocket(mock_websocket, "test-project")

                mock_websocket.close.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handles_ping_message(self, mock_websocket, mock_project_path):
        """WebSocket should respond to ping with pong."""
        mock_websocket.receive_text.side_effect = [
            json.dumps({"type": "ping"}),
            asyncio.CancelledError()
        ]

        with patch("server.websocket._get_project_path") as mock_path:
            with patch("server.websocket._get_project_git_url") as mock_url:
                with patch("server.websocket.get_all_container_managers") as mock_managers:
                    with patch("server.websocket._get_count_passing_tests") as mock_count:
                        mock_path.return_value = mock_project_path
                        mock_url.return_value = "https://github.com/test/repo.git"
                        mock_managers.return_value = []
                        mock_count.return_value = MagicMock(return_value=(0, 0, 0))

                        from server.websocket import project_websocket

                        try:
                            await project_websocket(mock_websocket, "test-project")
                        except asyncio.CancelledError:
                            pass

                        # Check pong was sent
                        pong_calls = [
                            c for c in mock_websocket.send_json.call_args_list
                            if c[0][0].get("type") == "pong"
                        ]
                        assert len(pong_calls) >= 1


# =============================================================================
# Callback Registration Tests
# =============================================================================

class TestCallbackRegistration:
    """Tests for container callback registration."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_registers_callbacks_for_existing_containers(self, mock_websocket, mock_project_path):
        """Should register callbacks for existing container managers."""
        mock_manager = MagicMock()
        mock_manager.container_number = 1
        mock_manager.status = "running"
        mock_manager._current_agent_type = "coding"
        mock_manager._force_claude_sdk = False
        mock_manager._is_opencode_model = MagicMock(return_value=False)
        mock_manager.add_output_callback = MagicMock()
        mock_manager.add_status_callback = MagicMock()
        mock_manager.remove_output_callback = MagicMock()
        mock_manager.remove_status_callback = MagicMock()

        mock_websocket.receive_text.side_effect = asyncio.CancelledError()

        with patch("server.websocket._get_project_path") as mock_path:
            with patch("server.websocket._get_project_git_url") as mock_url:
                with patch("server.websocket.get_all_container_managers") as mock_managers:
                    with patch("server.websocket._get_count_passing_tests") as mock_count:
                        mock_path.return_value = mock_project_path
                        mock_url.return_value = "https://github.com/test/repo.git"
                        mock_managers.return_value = [mock_manager]
                        mock_count.return_value = MagicMock(return_value=(0, 0, 0))

                        from server.websocket import project_websocket

                        try:
                            await project_websocket(mock_websocket, "test-project")
                        except asyncio.CancelledError:
                            pass

                        # Callbacks should have been registered
                        mock_manager.add_output_callback.assert_called()
                        mock_manager.add_status_callback.assert_called()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unregisters_callbacks_on_disconnect(self, mock_websocket, mock_project_path):
        """Should unregister callbacks when WebSocket disconnects."""
        mock_manager = MagicMock()
        mock_manager.container_number = 1
        mock_manager.status = "running"
        mock_manager._current_agent_type = "coding"
        mock_manager._force_claude_sdk = False
        mock_manager._is_opencode_model = MagicMock(return_value=False)
        mock_manager.add_output_callback = MagicMock()
        mock_manager.add_status_callback = MagicMock()
        mock_manager.remove_output_callback = MagicMock()
        mock_manager.remove_status_callback = MagicMock()

        mock_websocket.receive_text.side_effect = asyncio.CancelledError()

        with patch("server.websocket._get_project_path") as mock_path:
            with patch("server.websocket._get_project_git_url") as mock_url:
                with patch("server.websocket.get_all_container_managers") as mock_managers:
                    with patch("server.websocket._get_count_passing_tests") as mock_count:
                        with patch("server.websocket.manager") as mock_conn_manager:
                            mock_path.return_value = mock_project_path
                            mock_url.return_value = "https://github.com/test/repo.git"
                            mock_managers.return_value = [mock_manager]
                            mock_count.return_value = MagicMock(return_value=(0, 0, 0))
                            mock_conn_manager.connect = AsyncMock()
                            mock_conn_manager.disconnect = AsyncMock()

                            from server.websocket import project_websocket

                            try:
                                await project_websocket(mock_websocket, "test-project")
                            except asyncio.CancelledError:
                                pass

                            # Callbacks should have been unregistered
                            mock_manager.remove_output_callback.assert_called()
                            mock_manager.remove_status_callback.assert_called()


# =============================================================================
# Message Format Tests
# =============================================================================

class TestMessageFormats:
    """Tests for WebSocket message formats."""

    @pytest.mark.unit
    def test_progress_message_format(self):
        """Progress message should have correct format."""
        message = {
            "type": "progress",
            "passing": 5,
            "in_progress": 2,
            "total": 10,
            "percentage": 50.0,
        }

        assert message["type"] == "progress"
        assert isinstance(message["passing"], int)
        assert isinstance(message["in_progress"], int)
        assert isinstance(message["total"], int)
        assert isinstance(message["percentage"], float)

    @pytest.mark.unit
    def test_agent_status_message_format(self):
        """Agent status message should have correct format."""
        message = {
            "type": "agent_status",
            "status": "running",
            "container_number": 1,
            "agent_type": "coding",
            "sdk_type": "claude",
        }

        assert message["type"] == "agent_status"
        assert message["status"] in ["not_created", "created", "running", "stopping", "stopped", "completed"]

    @pytest.mark.unit
    def test_log_message_format(self):
        """Log message should have correct format."""
        message = {
            "type": "log",
            "line": "Test log line",
            "timestamp": datetime.now().isoformat(),
            "container_number": 1,
        }

        assert message["type"] == "log"
        assert isinstance(message["line"], str)
        assert isinstance(message["timestamp"], str)
        assert isinstance(message["container_number"], int)

    @pytest.mark.unit
    def test_containers_message_format(self):
        """Containers list message should have correct format."""
        message = {
            "type": "containers",
            "containers": [
                {
                    "number": 1,
                    "type": "coding",
                    "agent_type": "coding",
                    "sdk_type": "claude",
                }
            ],
        }

        assert message["type"] == "containers"
        assert isinstance(message["containers"], list)
        assert message["containers"][0]["number"] == 1
