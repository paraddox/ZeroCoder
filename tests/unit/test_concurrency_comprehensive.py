"""
Concurrency Tests
=================

Enterprise-grade tests for concurrent access patterns including:
- Thread safety
- Race condition handling
- Lock contention
- Async operation coordination
"""

import asyncio
import threading
import time
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from concurrent.futures import ThreadPoolExecutor

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Registry Concurrency Tests
# =============================================================================

class TestRegistryConcurrency:
    """Tests for registry thread safety."""

    @pytest.fixture
    def isolated_registry(self, tmp_path, monkeypatch):
        """Create isolated registry for concurrency testing."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "concurrent.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        return registry

    @pytest.mark.unit
    @pytest.mark.slow
    def test_concurrent_project_registration(self, isolated_registry):
        """Test concurrent registration of different projects."""
        results = []
        errors = []
        lock = threading.Lock()

        def register_project(index):
            try:
                isolated_registry.register_project(
                    name=f"project-{index}",
                    git_url=f"https://github.com/user/repo{index}.git"
                )
                with lock:
                    results.append(index)
            except Exception as e:
                with lock:
                    errors.append((index, e))

        threads = [
            threading.Thread(target=register_project, args=(i,))
            for i in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Most should succeed (some may fail due to SQLite locking)
        assert len(results) >= 5, f"Only {len(results)} succeeded, errors: {errors}"

    @pytest.mark.unit
    @pytest.mark.slow
    def test_concurrent_read_operations(self, isolated_registry):
        """Test concurrent read operations don't block."""
        # Setup: create some projects
        for i in range(5):
            isolated_registry.register_project(
                name=f"read-test-{i}",
                git_url=f"https://github.com/user/repo{i}.git"
            )

        results = []
        lock = threading.Lock()

        def read_project(index):
            info = isolated_registry.get_project_info(f"read-test-{index % 5}")
            with lock:
                results.append(info is not None)

        threads = [
            threading.Thread(target=read_project, args=(i,))
            for i in range(20)
        ]

        start = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        duration = time.time() - start

        # All reads should succeed
        assert all(results)
        # Should complete quickly
        assert duration < 5.0

    @pytest.mark.unit
    @pytest.mark.slow
    def test_concurrent_read_write(self, isolated_registry):
        """Test concurrent read and write operations."""
        # Setup initial project
        isolated_registry.register_project(
            name="rw-test",
            git_url="https://github.com/user/repo.git"
        )

        read_results = []
        write_results = []
        lock = threading.Lock()

        def read_op():
            for _ in range(10):
                info = isolated_registry.get_project_info("rw-test")
                with lock:
                    read_results.append(info is not None)
                time.sleep(0.01)

        def write_op(index):
            try:
                isolated_registry.register_project(
                    name=f"rw-write-{index}",
                    git_url=f"https://github.com/user/repo{index}.git"
                )
                with lock:
                    write_results.append(True)
            except Exception:
                with lock:
                    write_results.append(False)

        readers = [threading.Thread(target=read_op) for _ in range(3)]
        writers = [threading.Thread(target=write_op, args=(i,)) for i in range(3)]

        for t in readers + writers:
            t.start()
        for t in readers + writers:
            t.join()

        # All reads should succeed
        assert all(read_results)
        # Some writes should succeed
        assert sum(write_results) >= 1


# =============================================================================
# WebSocket Concurrency Tests
# =============================================================================

class TestWebSocketConcurrency:
    """Tests for WebSocket manager thread safety."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_connections(self):
        """Test concurrent WebSocket connections."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        clients = [AsyncMock() for _ in range(20)]

        # Connect all clients concurrently
        await asyncio.gather(*[
            manager.connect(client, "concurrent-connect")
            for client in clients
        ])

        assert manager.get_connection_count("concurrent-connect") == 20

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_broadcasts(self):
        """Test concurrent broadcast operations."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        clients = [AsyncMock() for _ in range(10)]

        for client in clients:
            await manager.connect(client, "broadcast-test")

        # Broadcast concurrently
        async def broadcast(msg_id):
            await manager.broadcast_to_project("broadcast-test", {"id": msg_id})

        await asyncio.gather(*[broadcast(i) for i in range(100)])

        # Each client should receive all messages
        for client in clients:
            assert client.send_json.call_count == 100

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_connect_disconnect(self):
        """Test concurrent connect and disconnect operations."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        clients = [AsyncMock() for _ in range(20)]

        # Connect all
        for client in clients:
            await manager.connect(client, "conn-disco")

        # Disconnect half concurrently while broadcasting
        async def disconnect(client):
            await manager.disconnect(client, "conn-disco")

        async def broadcast():
            for _ in range(10):
                await manager.broadcast_to_project("conn-disco", {"type": "test"})
                await asyncio.sleep(0.001)

        await asyncio.gather(
            *[disconnect(client) for client in clients[:10]],
            broadcast()
        )

        # Should have 10 remaining
        assert manager.get_connection_count("conn-disco") == 10

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_multi_project_broadcast(self):
        """Test broadcasting to multiple projects concurrently."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        projects = ["proj-a", "proj-b", "proj-c"]

        # Connect clients to each project
        for proj in projects:
            for _ in range(5):
                await manager.connect(AsyncMock(), proj)

        # Broadcast to all projects concurrently
        async def broadcast_to_project(proj):
            for i in range(50):
                await manager.broadcast_to_project(proj, {"project": proj, "msg": i})

        await asyncio.gather(*[broadcast_to_project(p) for p in projects])

        # Each project should have 5 connections
        for proj in projects:
            assert manager.get_connection_count(proj) == 5


# =============================================================================
# Container Manager Concurrency Tests
# =============================================================================

class TestContainerManagerConcurrency:
    """Tests for container manager thread safety."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create container manager for concurrency testing."""
        from server.services.container_manager import ContainerManager, _container_managers

        _container_managers.clear()
        project_dir = tmp_path / "concurrent-cm"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="concurrent-cm",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_callback_registration(self, container_manager):
        """Test concurrent callback registration."""
        callbacks = [AsyncMock() for _ in range(100)]

        # Register all callbacks concurrently
        def register(cb):
            container_manager.add_status_callback(cb)

        with ThreadPoolExecutor(max_workers=10) as executor:
            list(executor.map(register, callbacks))

        assert len(container_manager._status_callbacks) == 100

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_notifications(self, container_manager):
        """Test concurrent status notifications."""
        callback = AsyncMock()
        container_manager.add_status_callback(callback)

        # Notify concurrently
        await asyncio.gather(*[
            container_manager._notify_status(f"status-{i}")
            for i in range(50)
        ])

        assert callback.call_count == 50

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_callback_add_remove(self, container_manager):
        """Test concurrent add and remove of callbacks."""
        callbacks = [AsyncMock() for _ in range(20)]

        async def add_and_remove(cb, delay):
            container_manager.add_status_callback(cb)
            await asyncio.sleep(delay)
            container_manager.remove_status_callback(cb)

        await asyncio.gather(*[
            add_and_remove(cb, i * 0.001)
            for i, cb in enumerate(callbacks)
        ])

        # All should be removed
        assert len(container_manager._status_callbacks) == 0


# =============================================================================
# Async Operation Coordination Tests
# =============================================================================

class TestAsyncCoordination:
    """Tests for async operation coordination."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_polling_with_concurrent_updates(self):
        """Test progress polling with concurrent updates."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        client = AsyncMock()
        await manager.connect(client, "poll-test")

        updates = []

        async def simulate_poll():
            for i in range(10):
                await manager.broadcast_to_project("poll-test", {"passing": i})
                updates.append(i)
                await asyncio.sleep(0.01)

        async def simulate_feature_update():
            for i in range(10):
                await manager.broadcast_to_project("poll-test", {"feature": f"feat-{i}"})
                await asyncio.sleep(0.01)

        await asyncio.gather(simulate_poll(), simulate_feature_update())

        # Client should receive interleaved messages
        assert client.send_json.call_count == 20

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_graceful_stop_coordination(self, tmp_path):
        """Test graceful stop flag coordination."""
        from server.services.container_manager import ContainerManager, _container_managers

        _container_managers.clear()
        project_dir = tmp_path / "graceful-stop"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="graceful-stop",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )

        # Test flag visibility across concurrent operations
        manager._graceful_stop_requested = True

        async def check_flag():
            for _ in range(100):
                assert manager._graceful_stop_requested is True
                await asyncio.sleep(0.001)

        await asyncio.gather(*[check_flag() for _ in range(5)])


# =============================================================================
# Thread Pool Executor Tests
# =============================================================================

class TestThreadPoolConcurrency:
    """Tests for operations using thread pools."""

    @pytest.mark.unit
    @pytest.mark.slow
    def test_concurrent_beads_operations(self, tmp_path):
        """Test concurrent beads file operations."""
        import json

        project_dir = tmp_path / "beads-concurrent"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text("")

        lock = threading.Lock()
        results = []

        def read_issues():
            with lock:
                with open(issues_file, "r") as f:
                    lines = f.readlines()
            results.append(len(lines))

        def write_issue(index):
            issue = {"id": f"feat-{index}", "title": f"Feature {index}", "status": "open"}
            with lock:
                with open(issues_file, "a") as f:
                    f.write(json.dumps(issue) + "\n")

        with ThreadPoolExecutor(max_workers=10) as executor:
            # Write some issues
            list(executor.map(write_issue, range(10)))
            # Read concurrently
            list(executor.map(lambda _: read_issues(), range(10)))

        # All reads should return same count
        assert all(r == 10 for r in results)


# =============================================================================
# Lock Contention Tests
# =============================================================================

class TestLockContention:
    """Tests for lock contention scenarios."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_websocket_lock_contention(self):
        """Test WebSocket manager under lock contention."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        # Heavy concurrent operations
        async def heavy_connect_disconnect():
            client = AsyncMock()
            for _ in range(100):
                await manager.connect(client, "contention-test")
                await manager.disconnect(client, "contention-test")

        start = time.time()
        await asyncio.gather(*[heavy_connect_disconnect() for _ in range(5)])
        duration = time.time() - start

        # Should complete in reasonable time despite contention
        assert duration < 10.0

    @pytest.mark.unit
    @pytest.mark.slow
    def test_registry_lock_contention(self, tmp_path, monkeypatch):
        """Test registry under heavy contention."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "contention.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")

        # Create initial project
        registry.register_project("contention-base", "https://github.com/user/repo.git")

        results = []
        lock = threading.Lock()

        def heavy_operations(thread_id):
            for i in range(20):
                try:
                    # Mix of reads and writes
                    registry.get_project_info("contention-base")
                    if i % 5 == 0:
                        try:
                            registry.register_project(
                                f"contention-{thread_id}-{i}",
                                f"https://github.com/user/repo{thread_id}{i}.git"
                            )
                        except:
                            pass  # Expect some failures
                    with lock:
                        results.append(True)
                except Exception as e:
                    with lock:
                        results.append(False)

        threads = [
            threading.Thread(target=heavy_operations, args=(i,))
            for i in range(5)
        ]

        start = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        duration = time.time() - start

        # Most operations should succeed
        success_rate = sum(results) / len(results)
        assert success_rate > 0.5, f"Success rate: {success_rate}"
        assert duration < 30.0


# =============================================================================
# Deadlock Prevention Tests
# =============================================================================

class TestDeadlockPrevention:
    """Tests to verify deadlock prevention."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_deadlock_on_nested_broadcasts(self):
        """Test no deadlock when broadcast triggers another broadcast."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        client = AsyncMock()

        # Simulate nested broadcast (callback triggers another broadcast)
        async def nested_callback(msg):
            await manager.broadcast_to_project("nested-test", {"nested": True})

        client.send_json = nested_callback
        await manager.connect(client, "nested-test")

        # Should not deadlock
        await asyncio.wait_for(
            manager.broadcast_to_project("nested-test", {"trigger": True}),
            timeout=5.0
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_deadlock_on_callback_exception(self, tmp_path):
        """Test no deadlock when callback raises exception."""
        from server.services.container_manager import ContainerManager, _container_managers

        _container_managers.clear()
        project_dir = tmp_path / "deadlock-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="deadlock-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )

        # Add callback that raises
        failing = AsyncMock(side_effect=Exception("Callback error"))
        manager.add_status_callback(failing)

        # Should not deadlock
        await asyncio.wait_for(
            manager._notify_status("test"),
            timeout=5.0
        )


# =============================================================================
# Resource Starvation Tests
# =============================================================================

class TestResourceStarvation:
    """Tests for resource starvation prevention."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fair_broadcast_distribution(self):
        """Test all clients get messages fairly."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        clients = [AsyncMock() for _ in range(100)]

        for client in clients:
            await manager.connect(client, "fair-test")

        # Broadcast many messages
        for i in range(100):
            await manager.broadcast_to_project("fair-test", {"id": i})

        # All clients should receive all messages
        for client in clients:
            assert client.send_json.call_count == 100

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_slow_client_isolation(self):
        """Test slow client doesn't block others."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        fast_client = AsyncMock()
        slow_client = AsyncMock()

        # Slow client has delay
        async def slow_send(msg):
            await asyncio.sleep(0.1)

        slow_client.send_json = slow_send
        fast_client.send_json = AsyncMock()

        await manager.connect(fast_client, "slow-test")
        await manager.connect(slow_client, "slow-test")

        # Broadcast should complete quickly for fast client
        start = time.time()
        await manager.broadcast_to_project("slow-test", {"test": True})
        duration = time.time() - start

        # Fast client should be called
        fast_client.send_json.assert_called()
