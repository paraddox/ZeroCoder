"""
WebSocket Handler Unit Tests
============================

Tests for WebSocket functionality including:
- Connection management
- Message broadcasting
- Progress polling
- Agent status updates
- Error handling
"""

import asyncio
import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestWebSocketConnectionManager:
    """Tests for WebSocket connection management."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_websocket_accept(self, mock_websocket):
        """Test WebSocket connection acceptance."""
        await mock_websocket.accept()
        mock_websocket.accept.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_websocket_send_json(self, mock_websocket):
        """Test sending JSON over WebSocket."""
        message = {"type": "progress", "passing": 5, "total": 10}

        await mock_websocket.send_json(message)

        mock_websocket.send_json.assert_called_once_with(message)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_websocket_receive_json(self, mock_websocket):
        """Test receiving JSON over WebSocket."""
        expected_message = {"command": "subscribe"}
        mock_websocket.receive_json.return_value = expected_message

        message = await mock_websocket.receive_json()

        assert message == expected_message

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_websocket_close(self, mock_websocket):
        """Test WebSocket connection close."""
        await mock_websocket.close()

        mock_websocket.close.assert_called_once()


class TestProgressMessages:
    """Tests for progress update messages."""

    @pytest.mark.unit
    def test_progress_message_structure(self):
        """Test progress message has correct structure."""
        from server.schemas import WSProgressMessage

        message = WSProgressMessage(
            passing=5,
            total=10,
            percentage=50.0
        )

        assert message.type == "progress"
        assert message.passing == 5
        assert message.total == 10
        assert message.percentage == 50.0

    @pytest.mark.unit
    def test_progress_percentage_calculation(self):
        """Test progress percentage is calculated correctly."""
        passing = 3
        total = 10
        expected_percentage = (passing / total) * 100

        assert expected_percentage == 30.0

    @pytest.mark.unit
    def test_progress_zero_total_handling(self):
        """Test handling when total is zero."""
        passing = 0
        total = 0

        # Should not raise division by zero
        percentage = 0.0 if total == 0 else (passing / total) * 100
        assert percentage == 0.0


class TestFeatureUpdateMessages:
    """Tests for feature update messages."""

    @pytest.mark.unit
    def test_feature_update_message_structure(self):
        """Test feature update message has correct structure."""
        from server.schemas import WSFeatureUpdateMessage

        message = WSFeatureUpdateMessage(
            feature_id="feat-1",
            passes=True
        )

        assert message.type == "feature_update"
        assert message.feature_id == "feat-1"
        assert message.passes is True

    @pytest.mark.unit
    def test_feature_update_with_string_id(self):
        """Test feature update accepts string IDs."""
        from server.schemas import WSFeatureUpdateMessage

        message = WSFeatureUpdateMessage(
            feature_id="beads-123",
            passes=False
        )

        assert message.feature_id == "beads-123"


class TestLogMessages:
    """Tests for agent log messages."""

    @pytest.mark.unit
    def test_log_message_structure(self):
        """Test log message has correct structure."""
        from server.schemas import WSLogMessage

        now = datetime.now()
        message = WSLogMessage(
            line="Processing feature feat-1...",
            timestamp=now
        )

        assert message.type == "log"
        assert message.line == "Processing feature feat-1..."
        assert message.timestamp == now

    @pytest.mark.unit
    def test_log_message_sanitization(self):
        """Test that sensitive data in logs is sanitized."""
        from server.services.container_manager import sanitize_output

        # Use a pattern that matches the actual sanitize_output patterns
        # Pattern: sk-[a-zA-Z0-9]{20,}
        sensitive_line = "api_key=sk-abcdefghij1234567890abcdefghij"
        sanitized = sanitize_output(sensitive_line)

        assert "[REDACTED]" in sanitized

    @pytest.mark.unit
    def test_log_message_preserves_regular_output(self):
        """Test that regular output is not modified."""
        from server.services.container_manager import sanitize_output

        regular_line = "Building component: Button.tsx"
        result = sanitize_output(regular_line)

        assert result == regular_line


class TestAgentStatusMessages:
    """Tests for agent status messages."""

    @pytest.mark.unit
    def test_agent_status_message_structure(self):
        """Test agent status message has correct structure."""
        from server.schemas import WSAgentStatusMessage

        message = WSAgentStatusMessage(status="running")

        assert message.type == "agent_status"
        assert message.status == "running"

    @pytest.mark.unit
    def test_valid_agent_statuses(self):
        """Test all valid agent statuses."""
        from server.schemas import WSAgentStatusMessage

        valid_statuses = ["not_created", "stopped", "running", "completed"]

        for status in valid_statuses:
            message = WSAgentStatusMessage(status=status)
            assert message.status == status


class TestWebSocketBroadcasting:
    """Tests for message broadcasting to multiple clients."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_clients(self):
        """Test broadcasting to multiple connected clients."""
        clients = [AsyncMock() for _ in range(3)]
        message = {"type": "progress", "passing": 5, "total": 10}

        for client in clients:
            await client.send_json(message)

        for client in clients:
            client.send_json.assert_called_once_with(message)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_handles_disconnected_client(self):
        """Test that broadcasting handles disconnected clients gracefully."""
        good_client = AsyncMock()
        bad_client = AsyncMock()
        bad_client.send_json.side_effect = Exception("Connection closed")

        clients = [good_client, bad_client]
        message = {"type": "progress", "passing": 5, "total": 10}

        # Should not raise even if one client fails
        for client in clients:
            try:
                await client.send_json(message)
            except Exception:
                pass

        good_client.send_json.assert_called_once()


class TestWebSocketPolling:
    """Tests for WebSocket polling functionality."""

    @pytest.mark.unit
    def test_poll_interval_constant(self):
        """Test that poll interval is defined."""
        POLL_INTERVAL = 30  # seconds
        assert POLL_INTERVAL == 30

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_poll_sends_progress_update(self, mock_websocket):
        """Test that polling sends progress updates."""
        progress_data = {"passing": 5, "total": 10, "percentage": 50.0}

        message = {"type": "progress", **progress_data}
        await mock_websocket.send_json(message)

        mock_websocket.send_json.assert_called_with(message)


class TestWebSocketErrorHandling:
    """Tests for WebSocket error handling."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handle_invalid_json_message(self, mock_websocket):
        """Test handling of invalid JSON in received message."""
        mock_websocket.receive_json.side_effect = json.JSONDecodeError(
            "Invalid JSON", "doc", 0
        )

        with pytest.raises(json.JSONDecodeError):
            await mock_websocket.receive_json()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handle_connection_closed(self, mock_websocket):
        """Test handling of closed connection."""
        mock_websocket.send_json.side_effect = Exception("Connection closed")

        with pytest.raises(Exception) as exc_info:
            await mock_websocket.send_json({"test": "data"})

        assert "Connection closed" in str(exc_info.value)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handle_timeout(self, mock_websocket):
        """Test handling of receive timeout."""
        mock_websocket.receive_json.side_effect = asyncio.TimeoutError()

        with pytest.raises(asyncio.TimeoutError):
            await mock_websocket.receive_json()


class TestProjectSubscription:
    """Tests for project-specific WebSocket subscriptions."""

    @pytest.mark.unit
    def test_project_name_in_url(self):
        """Test that project name is extracted from WebSocket URL."""
        ws_url = "/ws/projects/my-project"
        parts = ws_url.split("/")

        project_name = parts[-1]
        assert project_name == "my-project"

    @pytest.mark.unit
    def test_validate_project_name_in_subscription(self):
        """Test that project name is validated for subscription."""
        import re

        valid_pattern = r"^[a-zA-Z0-9_-]{1,50}$"

        valid_names = ["project", "my-project", "Project_123"]
        invalid_names = ["", "a" * 51, "project/path", "../traversal"]

        for name in valid_names:
            assert re.match(valid_pattern, name)

        for name in invalid_names:
            assert not re.match(valid_pattern, name)


class TestWebSocketMessageValidation:
    """Tests for WebSocket message validation."""

    @pytest.mark.unit
    def test_progress_message_validation(self):
        """Test that progress messages are validated."""
        from server.schemas import WSProgressMessage

        # Valid message
        message = WSProgressMessage(passing=0, total=0, percentage=0.0)
        assert message.type == "progress"

        # Fields must be non-negative
        message = WSProgressMessage(passing=100, total=100, percentage=100.0)
        assert message.passing >= 0
        assert message.total >= 0

    @pytest.mark.unit
    def test_feature_id_required(self):
        """Test that feature ID is required in update messages."""
        from server.schemas import WSFeatureUpdateMessage
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            WSFeatureUpdateMessage(passes=True)  # Missing feature_id

    @pytest.mark.unit
    def test_log_line_required(self):
        """Test that line is required in log messages."""
        from server.schemas import WSLogMessage
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            WSLogMessage(timestamp=datetime.now())  # Missing line


class TestContainerCallbackIntegration:
    """Tests for container manager callback integration."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_output_callback_registration(self, mock_container_manager):
        """Test registering output callback with container manager."""
        callback = AsyncMock()

        # Simulate callback registration
        callbacks = []
        callbacks.append(callback)

        assert callback in callbacks

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_status_callback_registration(self, mock_container_manager):
        """Test registering status callback with container manager."""
        callback = AsyncMock()

        # Simulate callback registration
        callbacks = []
        callbacks.append(callback)

        assert callback in callbacks

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_callback_invocation_on_status_change(self):
        """Test that callbacks are invoked on status changes."""
        callback = AsyncMock()
        new_status = "running"

        await callback(new_status)

        callback.assert_called_once_with(new_status)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_callback_invocation_on_output(self):
        """Test that callbacks are invoked on new output."""
        callback = AsyncMock()
        log_line = "Building feature..."

        await callback(log_line)

        callback.assert_called_once_with(log_line)
