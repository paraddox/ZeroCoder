"""
WebSocket Integration Tests
===========================

Tests for WebSocket functionality including:
- Connection lifecycle
- Message broadcasting
- Multi-client scenarios
- Error recovery
"""

import asyncio
import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from server.websocket import ConnectionManager


# =============================================================================
# Connection Manager Tests
# =============================================================================

class TestConnectionManager:
    """Tests for WebSocket ConnectionManager."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_connect_single_client(self):
        """Test single client connection."""
        manager = ConnectionManager()
        ws = AsyncMock()
        ws.accept = AsyncMock()

        await manager.connect(ws, "test-project")

        assert len(manager.active_connections.get("test-project", set())) == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_connect_multiple_clients_same_project(self):
        """Test multiple clients connecting to same project."""
        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await manager.connect(ws1, "test-project")
        await manager.connect(ws2, "test-project")

        assert len(manager.active_connections.get("test-project", set())) == 2

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_connect_multiple_projects(self):
        """Test clients connecting to different projects."""
        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await manager.connect(ws1, "project-a")
        await manager.connect(ws2, "project-b")

        assert len(manager.active_connections.get("project-a", set())) == 1
        assert len(manager.active_connections.get("project-b", set())) == 1

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_disconnect_client(self):
        """Test client disconnection."""
        manager = ConnectionManager()
        ws = AsyncMock()

        await manager.connect(ws, "test-project")
        await manager.disconnect(ws, "test-project")

        assert len(manager.active_connections.get("test-project", set())) == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_client(self):
        """Test disconnecting non-existent client doesn't error."""
        manager = ConnectionManager()
        ws = AsyncMock()

        # Should not raise
        await manager.disconnect(ws, "test-project")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_disconnect_from_nonexistent_project(self):
        """Test disconnecting from non-existent project."""
        manager = ConnectionManager()
        ws = AsyncMock()

        await manager.connect(ws, "project-a")
        # Disconnect from different project
        await manager.disconnect(ws, "project-b")

        # Original connection should remain
        assert len(manager.active_connections.get("project-a", set())) == 1


# =============================================================================
# Broadcasting Tests
# =============================================================================

class TestBroadcasting:
    """Tests for message broadcasting functionality."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_broadcast_to_single_client(self):
        """Test broadcasting message to single client."""
        manager = ConnectionManager()
        ws = AsyncMock()
        ws.send_json = AsyncMock()

        await manager.connect(ws, "test-project")
        await manager.broadcast_to_project("test-project", {"type": "test", "data": "hello"})

        ws.send_json.assert_called_once_with({"type": "test", "data": "hello"})

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_clients(self):
        """Test broadcasting message to multiple clients."""
        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws1.send_json = AsyncMock()
        ws2.send_json = AsyncMock()

        await manager.connect(ws1, "test-project")
        await manager.connect(ws2, "test-project")
        await manager.broadcast_to_project("test-project", {"type": "test"})

        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_broadcast_only_to_target_project(self):
        """Test broadcast only reaches target project clients."""
        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws1.send_json = AsyncMock()
        ws2.send_json = AsyncMock()

        await manager.connect(ws1, "project-a")
        await manager.connect(ws2, "project-b")
        await manager.broadcast_to_project("project-a", {"type": "test"})

        ws1.send_json.assert_called_once()
        ws2.send_json.assert_not_called()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_broadcast_handles_client_error(self):
        """Test broadcast handles client send error gracefully."""
        manager = ConnectionManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws1.send_json = AsyncMock(side_effect=Exception("Connection lost"))
        ws2.send_json = AsyncMock()

        await manager.connect(ws1, "test-project")
        await manager.connect(ws2, "test-project")

        # Should not raise despite ws1 error
        await manager.broadcast_to_project("test-project", {"type": "test"})

        # ws2 should still receive message
        ws2.send_json.assert_called_once()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_broadcast_to_empty_project(self):
        """Test broadcast to project with no connections."""
        manager = ConnectionManager()

        # Should not raise
        await manager.broadcast_to_project("empty-project", {"type": "test"})


# =============================================================================
# Progress Updates Tests
# =============================================================================

class TestProgressUpdates:
    """Tests for progress update broadcasting."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_broadcast_progress(self):
        """Test broadcasting progress update."""
        manager = ConnectionManager()
        ws = AsyncMock()
        ws.send_json = AsyncMock()

        await manager.connect(ws, "test-project")

        # Broadcast using broadcast_to_project with progress message
        await manager.broadcast_to_project("test-project", {
            "type": "progress",
            "passing": 5,
            "in_progress": 2,
            "total": 10,
            "percentage": 50.0
        })

        call_args = ws.send_json.call_args[0][0]
        assert call_args["type"] == "progress"
        assert call_args["passing"] == 5
        assert call_args["total"] == 10


# =============================================================================
# Feature Updates Tests
# =============================================================================

class TestFeatureUpdates:
    """Tests for feature update broadcasting."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_broadcast_feature_update(self):
        """Test broadcasting feature status update."""
        manager = ConnectionManager()
        ws = AsyncMock()
        ws.send_json = AsyncMock()

        await manager.connect(ws, "test-project")

        # Broadcast using broadcast_to_project with feature_update message
        await manager.broadcast_to_project("test-project", {
            "type": "feature_update",
            "feature_id": "feat-1",
            "passes": True
        })

        call_args = ws.send_json.call_args[0][0]
        assert call_args["type"] == "feature_update"
        assert call_args["feature_id"] == "feat-1"
        assert call_args["passes"] is True


# =============================================================================
# Agent Status Updates Tests
# =============================================================================

class TestAgentStatusUpdates:
    """Tests for agent status update broadcasting."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_broadcast_agent_status(self):
        """Test broadcasting agent status update."""
        manager = ConnectionManager()
        ws = AsyncMock()
        ws.send_json = AsyncMock()

        await manager.connect(ws, "test-project")

        # Broadcast using broadcast_to_project with agent_status message
        await manager.broadcast_to_project("test-project", {
            "type": "agent_status",
            "status": "running"
        })

        call_args = ws.send_json.call_args[0][0]
        assert call_args["type"] == "agent_status"
        assert call_args["status"] == "running"


# =============================================================================
# Log Streaming Tests
# =============================================================================

class TestLogStreaming:
    """Tests for log message streaming."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_broadcast_log_message(self):
        """Test broadcasting log message."""
        manager = ConnectionManager()
        ws = AsyncMock()
        ws.send_json = AsyncMock()

        await manager.connect(ws, "test-project")

        # Broadcast using broadcast_to_project with log message
        await manager.broadcast_to_project("test-project", {
            "type": "log",
            "line": "Agent started"
        })

        call_args = ws.send_json.call_args[0][0]
        assert call_args["type"] == "log"
        assert call_args["line"] == "Agent started"


# =============================================================================
# Connection Cleanup Tests
# =============================================================================

class TestConnectionCleanup:
    """Tests for connection cleanup scenarios."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_failed_send_removes_client(self):
        """Test failed send removes client from connections."""
        manager = ConnectionManager()
        ws = AsyncMock()
        ws.send_json = AsyncMock(side_effect=Exception("Connection lost"))

        await manager.connect(ws, "test-project")

        # First broadcast will fail and should remove the dead connection
        await manager.broadcast_to_project("test-project", {"type": "test"})

        # Client should be removed after failed send
        assert len(manager.active_connections.get("test-project", set())) == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multiple_disconnects_safe(self):
        """Test multiple disconnects don't cause issues."""
        manager = ConnectionManager()
        ws = AsyncMock()

        await manager.connect(ws, "test-project")
        await manager.disconnect(ws, "test-project")
        await manager.disconnect(ws, "test-project")  # Second disconnect

        assert len(manager.active_connections.get("test-project", set())) == 0


# =============================================================================
# Concurrent Access Tests
# =============================================================================

class TestConcurrentAccess:
    """Tests for concurrent access scenarios."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_connections(self):
        """Test concurrent client connections."""
        manager = ConnectionManager()

        async def connect_client(i):
            ws = AsyncMock()
            await manager.connect(ws, "test-project")
            return ws

        clients = await asyncio.gather(*[connect_client(i) for i in range(10)])

        assert len(manager.active_connections.get("test-project", set())) == 10

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_broadcasts(self):
        """Test concurrent message broadcasts."""
        manager = ConnectionManager()
        ws = AsyncMock()
        ws.send_json = AsyncMock()

        await manager.connect(ws, "test-project")

        async def send_message(i):
            await manager.broadcast_to_project("test-project", {"type": "test", "id": i})

        await asyncio.gather(*[send_message(i) for i in range(10)])

        assert ws.send_json.call_count == 10
