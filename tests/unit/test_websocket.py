"""
WebSocket Manager Unit Tests
============================

Tests for WebSocket connection management including:
- Client connection handling
- Message broadcasting
- Connection cleanup
- Error handling
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import json

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.websocket import WebSocketManager


class TestWebSocketManager:
    """Tests for WebSocketManager class."""

    @pytest.fixture
    def ws_manager(self):
        """Create a WebSocketManager instance."""
        return WebSocketManager()

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket connection."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.send_text = AsyncMock()
        ws.close = AsyncMock()
        return ws

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_connect_client(self, ws_manager, mock_websocket):
        """Test connecting a client."""
        project_name = "test-project"

        await ws_manager.connect(mock_websocket, project_name)

        mock_websocket.accept.assert_called_once()
        assert project_name in ws_manager.active_connections
        assert mock_websocket in ws_manager.active_connections[project_name]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_disconnect_client(self, ws_manager, mock_websocket):
        """Test disconnecting a client."""
        project_name = "test-project"

        await ws_manager.connect(mock_websocket, project_name)
        ws_manager.disconnect(mock_websocket, project_name)

        assert mock_websocket not in ws_manager.active_connections.get(project_name, [])

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_disconnect_removes_empty_project(self, ws_manager, mock_websocket):
        """Test that project is removed when last client disconnects."""
        project_name = "test-project"

        await ws_manager.connect(mock_websocket, project_name)
        ws_manager.disconnect(mock_websocket, project_name)

        # Empty project list should be removed
        assert project_name not in ws_manager.active_connections or \
               len(ws_manager.active_connections[project_name]) == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_to_project(self, ws_manager, mock_websocket):
        """Test broadcasting message to project."""
        project_name = "test-project"
        message = {"type": "test", "data": {"value": 123}}

        await ws_manager.connect(mock_websocket, project_name)
        await ws_manager.broadcast(project_name, message)

        mock_websocket.send_json.assert_called_once_with(message)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_clients(self, ws_manager):
        """Test broadcasting to multiple clients."""
        project_name = "test-project"
        message = {"type": "test"}

        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2.accept = AsyncMock()

        await ws_manager.connect(ws1, project_name)
        await ws_manager.connect(ws2, project_name)
        await ws_manager.broadcast(project_name, message)

        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_to_nonexistent_project(self, ws_manager):
        """Test broadcasting to project with no clients."""
        # Should not raise error
        await ws_manager.broadcast("nonexistent", {"type": "test"})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_handles_client_error(self, ws_manager):
        """Test broadcast handles client send errors."""
        project_name = "test-project"

        ws_good = AsyncMock()
        ws_bad = AsyncMock()
        ws_good.accept = AsyncMock()
        ws_bad.accept = AsyncMock()
        ws_bad.send_json = AsyncMock(side_effect=Exception("Connection closed"))

        await ws_manager.connect(ws_good, project_name)
        await ws_manager.connect(ws_bad, project_name)

        # Should not raise, should handle error gracefully
        await ws_manager.broadcast(project_name, {"type": "test"})

        ws_good.send_json.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_multiple_projects(self, ws_manager):
        """Test managing multiple projects."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws1.accept = AsyncMock()
        ws2.accept = AsyncMock()

        await ws_manager.connect(ws1, "project-a")
        await ws_manager.connect(ws2, "project-b")

        assert "project-a" in ws_manager.active_connections
        assert "project-b" in ws_manager.active_connections

        # Broadcast to project-a should only reach ws1
        await ws_manager.broadcast("project-a", {"type": "test"})

        ws1.send_json.assert_called_once()
        ws2.send_json.assert_not_called()


class TestWebSocketMessageTypes:
    """Tests for different WebSocket message types."""

    @pytest.fixture
    def ws_manager(self):
        """Create a WebSocketManager instance."""
        return WebSocketManager()

    @pytest.fixture
    def mock_websocket(self):
        """Create a mock WebSocket connection."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        return ws

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_progress_message(self, ws_manager, mock_websocket):
        """Test progress message format."""
        await ws_manager.connect(mock_websocket, "test")

        message = {
            "type": "progress",
            "data": {
                "passing": 5,
                "in_progress": 2,
                "total": 10,
                "percentage": 50.0,
            }
        }

        await ws_manager.broadcast("test", message)

        mock_websocket.send_json.assert_called_with(message)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_agent_status_message(self, ws_manager, mock_websocket):
        """Test agent status message format."""
        await ws_manager.connect(mock_websocket, "test")

        message = {
            "type": "agent_status",
            "data": {
                "status": "running",
                "agent_running": True,
                "idle_seconds": 100,
            }
        }

        await ws_manager.broadcast("test", message)

        mock_websocket.send_json.assert_called_with(message)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_message(self, ws_manager, mock_websocket):
        """Test log message format."""
        await ws_manager.connect(mock_websocket, "test")

        message = {
            "type": "log",
            "data": {
                "line": "Agent output: Processing feature feat-1",
            }
        }

        await ws_manager.broadcast("test", message)

        mock_websocket.send_json.assert_called_with(message)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_feature_update_message(self, ws_manager, mock_websocket):
        """Test feature update message format."""
        await ws_manager.connect(mock_websocket, "test")

        message = {
            "type": "feature_update",
            "data": {
                "feature_id": "feat-1",
                "status": "closed",
            }
        }

        await ws_manager.broadcast("test", message)

        mock_websocket.send_json.assert_called_with(message)


class TestWebSocketConcurrency:
    """Tests for concurrent WebSocket operations."""

    @pytest.fixture
    def ws_manager(self):
        """Create a WebSocketManager instance."""
        return WebSocketManager()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_connections(self, ws_manager):
        """Test handling concurrent connection attempts."""
        async def connect_client(i):
            ws = AsyncMock()
            ws.accept = AsyncMock()
            await ws_manager.connect(ws, "test-project")
            return ws

        # Connect 10 clients concurrently
        clients = await asyncio.gather(*[connect_client(i) for i in range(10)])

        assert len(ws_manager.active_connections.get("test-project", [])) == 10

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_broadcasts(self, ws_manager):
        """Test handling concurrent broadcasts."""
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()

        await ws_manager.connect(ws, "test")

        # Broadcast 10 messages concurrently
        messages = [{"type": "test", "data": {"i": i}} for i in range(10)]
        await asyncio.gather(*[ws_manager.broadcast("test", m) for m in messages])

        assert ws.send_json.call_count == 10

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_connect_and_disconnect_concurrent(self, ws_manager):
        """Test concurrent connect and disconnect operations."""
        clients = []

        async def add_client(i):
            ws = AsyncMock()
            ws.accept = AsyncMock()
            await ws_manager.connect(ws, "test")
            clients.append((ws, i))

        async def remove_client(ws):
            ws_manager.disconnect(ws, "test")

        # Add clients
        await asyncio.gather(*[add_client(i) for i in range(5)])

        # Remove some while adding more
        tasks = [
            remove_client(clients[0][0]),
            add_client(5),
            remove_client(clients[1][0]),
            add_client(6),
        ]
        await asyncio.gather(*tasks)

        # Should handle without errors
