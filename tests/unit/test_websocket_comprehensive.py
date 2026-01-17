"""
Comprehensive WebSocket Tests
=============================

Enterprise-grade tests for WebSocket functionality including:
- Connection management
- Message broadcasting
- Error handling
- Concurrent connections
- Reconnection scenarios
- Message ordering
"""

import asyncio
import json
import pytest
from datetime import datetime
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Connection Manager Tests
# =============================================================================

class TestConnectionManager:
    """Tests for ConnectionManager class."""

    @pytest.fixture
    def manager(self):
        """Create a fresh ConnectionManager."""
        from server.websocket import ConnectionManager
        return ConnectionManager()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_connect_single_client(self, manager):
        """Test connecting a single client."""
        client = AsyncMock()

        await manager.connect(client, "test-project")

        assert "test-project" in manager.active_connections
        assert client in manager.active_connections["test-project"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_connect_multiple_clients_same_project(self, manager):
        """Test connecting multiple clients to same project."""
        clients = [AsyncMock() for _ in range(5)]

        for client in clients:
            await manager.connect(client, "shared-project")

        assert len(manager.active_connections["shared-project"]) == 5

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_connect_clients_different_projects(self, manager):
        """Test connecting clients to different projects."""
        for i in range(3):
            client = AsyncMock()
            await manager.connect(client, f"project-{i}")

        assert len(manager.active_connections) == 3
        for i in range(3):
            assert f"project-{i}" in manager.active_connections

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_disconnect_client(self, manager):
        """Test disconnecting a client."""
        client = AsyncMock()

        # Connect and disconnect
        await manager.connect(client, "test-project")
        await manager.disconnect(client, "test-project")

        # Client should be removed
        connections = manager.active_connections.get("test-project", set())
        assert client not in connections

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_disconnect_nonexistent_client(self, manager):
        """Test disconnecting a client that doesn't exist."""
        client = AsyncMock()

        # Should not raise
        await manager.disconnect(client, "nonexistent-project")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_disconnect_removes_empty_project(self, manager):
        """Test that empty projects are cleaned up on disconnect."""
        client = AsyncMock()

        await manager.connect(client, "cleanup-project")
        await manager.disconnect(client, "cleanup-project")

        # Empty project entry should be removed or have no connections
        connections = manager.active_connections.get("cleanup-project", set())
        assert len(connections) == 0


# =============================================================================
# Broadcast Tests
# =============================================================================

class TestBroadcasting:
    """Tests for message broadcasting."""

    @pytest.fixture
    def manager(self):
        """Create a fresh ConnectionManager."""
        from server.websocket import ConnectionManager
        return ConnectionManager()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_to_single_client(self, manager):
        """Test broadcasting to a single client."""
        client = AsyncMock()
        await manager.connect(client, "broadcast-test")

        message = {"type": "progress", "value": 50}
        await manager.broadcast_to_project("broadcast-test", message)

        client.send_json.assert_called_once_with(message)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_clients(self, manager):
        """Test broadcasting to multiple clients."""
        clients = [AsyncMock() for _ in range(5)]
        for client in clients:
            await manager.connect(client, "multi-broadcast")

        message = {"type": "log", "line": "Test message"}
        await manager.broadcast_to_project("multi-broadcast", message)

        for client in clients:
            client.send_json.assert_called_once_with(message)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_to_empty_project(self, manager):
        """Test broadcasting when no clients connected."""
        # Should not raise
        await manager.broadcast_to_project("empty-project", {"type": "test"})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_preserves_message_type(self, manager):
        """Test that message types are preserved in broadcast."""
        client = AsyncMock()
        await manager.connect(client, "type-test")

        messages = [
            {"type": "progress", "passing": 5, "total": 10, "percentage": 50},
            {"type": "log", "line": "Log message", "timestamp": datetime.now().isoformat()},
            {"type": "feature_update", "feature_id": "feat-1", "passes": True},
            {"type": "agent_status", "status": "running"},
        ]

        for msg in messages:
            await manager.broadcast_to_project("type-test", msg)
            # Verify the type was preserved
            call_args = client.send_json.call_args[0][0]
            assert call_args["type"] == msg["type"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_isolation_between_projects(self, manager):
        """Test that broadcasts are isolated between projects."""
        client_a = AsyncMock()
        client_b = AsyncMock()

        await manager.connect(client_a, "project-a")
        await manager.connect(client_b, "project-b")

        await manager.broadcast_to_project("project-a", {"project": "a"})

        client_a.send_json.assert_called_once()
        client_b.send_json.assert_not_called()


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestWebSocketErrorHandling:
    """Tests for WebSocket error handling."""

    @pytest.fixture
    def manager(self):
        """Create a fresh ConnectionManager."""
        from server.websocket import ConnectionManager
        return ConnectionManager()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_handles_client_error(self, manager):
        """Test that broadcast handles individual client errors gracefully."""
        healthy_client = AsyncMock()
        failing_client = AsyncMock()
        failing_client.send_json.side_effect = Exception("Connection lost")

        await manager.connect(healthy_client, "error-test")
        await manager.connect(failing_client, "error-test")

        # Should not raise
        await manager.broadcast_to_project("error-test", {"type": "test"})

        # Healthy client should still receive message
        healthy_client.send_json.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_continues_after_client_failure(self, manager):
        """Test that broadcast continues to other clients after one fails."""
        clients = [AsyncMock() for _ in range(5)]
        clients[2].send_json.side_effect = Exception("Failed")

        for client in clients:
            await manager.connect(client, "continue-test")

        await manager.broadcast_to_project("continue-test", {"type": "test"})

        # All clients should have been attempted
        for client in clients:
            assert client.send_json.call_count == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_accept_handles_error(self, manager):
        """Test that connection accept handles errors."""
        failing_client = AsyncMock()
        failing_client.accept.side_effect = Exception("Accept failed")

        # May raise or handle gracefully depending on implementation
        try:
            await manager.connect(failing_client, "accept-error")
        except Exception:
            pass  # Acceptable to raise


# =============================================================================
# Concurrent Operations Tests
# =============================================================================

class TestConcurrentWebSocketOperations:
    """Tests for concurrent WebSocket operations."""

    @pytest.fixture
    def manager(self):
        """Create a fresh ConnectionManager."""
        from server.websocket import ConnectionManager
        return ConnectionManager()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_connects(self, manager):
        """Test handling concurrent connection attempts."""
        clients = [AsyncMock() for _ in range(20)]

        # Connect all concurrently
        tasks = [
            manager.connect(client, "concurrent-connect")
            for client in clients
        ]
        await asyncio.gather(*tasks)

        assert len(manager.active_connections["concurrent-connect"]) == 20

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_broadcasts(self, manager):
        """Test handling concurrent broadcasts."""
        client = AsyncMock()
        await manager.connect(client, "concurrent-broadcast")

        # Broadcast many messages concurrently
        tasks = [
            manager.broadcast_to_project("concurrent-broadcast", {"id": i})
            for i in range(50)
        ]
        await asyncio.gather(*tasks)

        # Should have received all messages
        assert client.send_json.call_count == 50

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_connect_disconnect(self, manager):
        """Test concurrent connect and disconnect operations."""
        async def connect_disconnect():
            client = AsyncMock()
            await manager.connect(client, "churn-test")
            await asyncio.sleep(0.01)
            await manager.disconnect(client, "churn-test")

        tasks = [connect_disconnect() for _ in range(30)]
        await asyncio.gather(*tasks)

        # Should not crash, connections may or may not remain


# =============================================================================
# Message Ordering Tests
# =============================================================================

class TestMessageOrdering:
    """Tests for message ordering guarantees."""

    @pytest.fixture
    def manager(self):
        """Create a fresh ConnectionManager."""
        from server.websocket import ConnectionManager
        return ConnectionManager()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sequential_broadcast_order(self, manager):
        """Test that sequential broadcasts maintain order."""
        client = AsyncMock()
        received_order = []

        async def capture_message(msg):
            received_order.append(msg["seq"])

        client.send_json = capture_message
        await manager.connect(client, "order-test")

        for i in range(10):
            await manager.broadcast_to_project("order-test", {"seq": i})

        # Order should be preserved
        assert received_order == list(range(10))


# =============================================================================
# Reconnection Tests
# =============================================================================

class TestReconnection:
    """Tests for client reconnection scenarios."""

    @pytest.fixture
    def manager(self):
        """Create a fresh ConnectionManager."""
        from server.websocket import ConnectionManager
        return ConnectionManager()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_reconnect_same_client(self, manager):
        """Test reconnecting the same client object."""
        client = AsyncMock()

        # Connect, disconnect, reconnect
        await manager.connect(client, "reconnect-test")
        await manager.disconnect(client, "reconnect-test")
        await manager.connect(client, "reconnect-test")

        assert client in manager.active_connections["reconnect-test"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_reconnect_receives_new_messages(self, manager):
        """Test that reconnected client receives new messages."""
        client = AsyncMock()

        # Connect, disconnect, reconnect
        await manager.connect(client, "receive-test")
        await manager.disconnect(client, "receive-test")
        client.send_json.reset_mock()
        await manager.connect(client, "receive-test")

        # Should receive new messages
        await manager.broadcast_to_project("receive-test", {"type": "new"})
        client.send_json.assert_called_once()


# =============================================================================
# Project-Specific Message Tests
# =============================================================================

class TestProjectSpecificMessages:
    """Tests for project-specific message handling."""

    @pytest.fixture
    def manager(self):
        """Create a fresh ConnectionManager."""
        from server.websocket import ConnectionManager
        return ConnectionManager()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_progress_message_format(self, manager):
        """Test progress message format."""
        client = AsyncMock()
        await manager.connect(client, "progress-format")

        progress = {
            "type": "progress",
            "passing": 5,
            "total": 10,
            "percentage": 50.0
        }
        await manager.broadcast_to_project("progress-format", progress)

        call_args = client.send_json.call_args[0][0]
        assert call_args["type"] == "progress"
        assert call_args["passing"] == 5
        assert call_args["total"] == 10
        assert call_args["percentage"] == 50.0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_log_message_format(self, manager):
        """Test log message format."""
        client = AsyncMock()
        await manager.connect(client, "log-format")

        timestamp = datetime.now().isoformat()
        log = {
            "type": "log",
            "line": "Processing feature feat-1",
            "timestamp": timestamp
        }
        await manager.broadcast_to_project("log-format", log)

        call_args = client.send_json.call_args[0][0]
        assert call_args["type"] == "log"
        assert call_args["line"] == "Processing feature feat-1"
        assert call_args["timestamp"] == timestamp

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_feature_update_message_format(self, manager):
        """Test feature update message format."""
        client = AsyncMock()
        await manager.connect(client, "feature-format")

        update = {
            "type": "feature_update",
            "feature_id": "feat-123",
            "passes": True
        }
        await manager.broadcast_to_project("feature-format", update)

        call_args = client.send_json.call_args[0][0]
        assert call_args["type"] == "feature_update"
        assert call_args["feature_id"] == "feat-123"
        assert call_args["passes"] is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_agent_status_message_format(self, manager):
        """Test agent status message format."""
        client = AsyncMock()
        await manager.connect(client, "status-format")

        status = {
            "type": "agent_status",
            "status": "running"
        }
        await manager.broadcast_to_project("status-format", status)

        call_args = client.send_json.call_args[0][0]
        assert call_args["type"] == "agent_status"
        assert call_args["status"] == "running"


# =============================================================================
# Large Message Tests
# =============================================================================

class TestLargeMessages:
    """Tests for handling large messages."""

    @pytest.fixture
    def manager(self):
        """Create a fresh ConnectionManager."""
        from server.websocket import ConnectionManager
        return ConnectionManager()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_large_log_message(self, manager):
        """Test handling large log messages."""
        client = AsyncMock()
        await manager.connect(client, "large-log")

        # Large log line
        large_line = "X" * 10000
        log = {"type": "log", "line": large_line}

        await manager.broadcast_to_project("large-log", log)

        call_args = client.send_json.call_args[0][0]
        assert len(call_args["line"]) == 10000

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_many_log_lines(self, manager):
        """Test sending many log lines."""
        client = AsyncMock()
        await manager.connect(client, "many-logs")

        for i in range(1000):
            log = {"type": "log", "line": f"Log line {i}"}
            await manager.broadcast_to_project("many-logs", log)

        assert client.send_json.call_count == 1000


# =============================================================================
# Connection State Tests
# =============================================================================

class TestConnectionState:
    """Tests for connection state management."""

    @pytest.fixture
    def manager(self):
        """Create a fresh ConnectionManager."""
        from server.websocket import ConnectionManager
        return ConnectionManager()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_active_connections_count(self, manager):
        """Test getting count of active connections."""
        for i in range(5):
            client = AsyncMock()
            await manager.connect(client, "count-test")

        assert len(manager.active_connections["count-test"]) == 5

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_connected_projects(self, manager):
        """Test getting list of projects with connections."""
        projects = ["proj-a", "proj-b", "proj-c"]
        for proj in projects:
            client = AsyncMock()
            await manager.connect(client, proj)

        connected = set(manager.active_connections.keys())
        assert connected == set(projects)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_client_connected(self, manager):
        """Test checking if a specific client is connected."""
        client = AsyncMock()
        await manager.connect(client, "check-test")

        assert client in manager.active_connections["check-test"]

        await manager.disconnect(client, "check-test")

        connections = manager.active_connections.get("check-test", set())
        assert client not in connections


# =============================================================================
# Edge Cases Tests
# =============================================================================

class TestWebSocketEdgeCases:
    """Tests for edge cases in WebSocket handling."""

    @pytest.fixture
    def manager(self):
        """Create a fresh ConnectionManager."""
        from server.websocket import ConnectionManager
        return ConnectionManager()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_connect_same_client_twice(self, manager):
        """Test connecting the same client twice to same project."""
        client = AsyncMock()

        await manager.connect(client, "double-connect")
        await manager.connect(client, "double-connect")

        # Behavior may vary - document it
        # Could have 2 entries or deduplicate
        assert client in manager.active_connections["double-connect"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_connect_client_to_multiple_projects(self, manager):
        """Test connecting one client to multiple projects."""
        client = AsyncMock()

        await manager.connect(client, "project-1")
        await manager.connect(client, "project-2")

        assert client in manager.active_connections["project-1"]
        assert client in manager.active_connections["project-2"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_disconnect_from_wrong_project(self, manager):
        """Test disconnecting client from wrong project."""
        client = AsyncMock()

        await manager.connect(client, "correct-project")
        await manager.disconnect(client, "wrong-project")

        # Client should still be connected to correct project
        assert client in manager.active_connections["correct-project"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_broadcast_to_nonexistent_project(self, manager):
        """Test broadcasting to a project that doesn't exist."""
        # Should not raise
        await manager.broadcast_to_project("nonexistent", {"type": "test"})

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_unicode_in_messages(self, manager):
        """Test handling Unicode in messages."""
        client = AsyncMock()
        await manager.connect(client, "unicode-test")

        message = {
            "type": "log",
            "line": "Processing 日本語テスト 🚀 émoji àccénts"
        }
        await manager.broadcast_to_project("unicode-test", message)

        call_args = client.send_json.call_args[0][0]
        assert "日本語" in call_args["line"]
        assert "🚀" in call_args["line"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_special_characters_in_project_name(self, manager):
        """Test project names with special characters."""
        client = AsyncMock()

        # Project names should only contain safe characters
        # This tests the WebSocket's handling of names it receives
        await manager.connect(client, "project-with-dash_and_underscore")
        await manager.broadcast_to_project("project-with-dash_and_underscore", {"type": "test"})

        client.send_json.assert_called_once()
