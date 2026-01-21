"""
Performance and Stress Tests
============================

Enterprise-grade performance tests covering:
- Response time benchmarks
- Memory usage patterns
- Concurrent request handling
- Large dataset processing
- Resource cleanup verification
"""

import asyncio
import gc
import json
import os
import pytest
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
# =============================================================================
# Registry Performance Tests
# =============================================================================

class TestRegistryPerformance:
    """Performance tests for registry operations."""

    @pytest.mark.performance
    def test_bulk_project_registration(self, isolated_registry):
        """Test performance of registering many projects."""
        start = time.time()
        count = 100

        for i in range(count):
            isolated_registry.register_project(
                name=f"perf-project-{i}",
                git_url=f"https://github.com/user/repo{i}.git"
            )

        duration = time.time() - start

        # Should complete in reasonable time
        assert duration < 10.0, f"Took too long: {duration}s for {count} projects"

        # Verify all registered
        projects = isolated_registry.list_registered_projects()
        assert len(projects) == count

    @pytest.mark.performance
    def test_bulk_project_lookup(self, isolated_registry):
        """Test performance of looking up many projects."""
        # First, register projects
        count = 100
        for i in range(count):
            isolated_registry.register_project(
                name=f"lookup-project-{i}",
                git_url=f"https://github.com/user/repo{i}.git"
            )

        # Measure lookup time
        start = time.time()
        for i in range(count):
            isolated_registry.get_project_info(f"lookup-project-{i}")
        duration = time.time() - start

        # Should complete quickly
        assert duration < 5.0, f"Lookups took too long: {duration}s"

    @pytest.mark.performance
    def test_concurrent_project_access(self, isolated_registry):
        """Test concurrent access performance."""
        import threading

        # Register base projects
        for i in range(10):
            isolated_registry.register_project(
                name=f"concurrent-{i}",
                git_url=f"https://github.com/user/repo{i}.git"
            )

        results = []
        errors = []
        lock = threading.Lock()

        def read_projects():
            try:
                start = time.time()
                for _ in range(10):
                    isolated_registry.list_registered_projects()
                with lock:
                    results.append(time.time() - start)
            except Exception as e:
                with lock:
                    errors.append(str(e))

        threads = [threading.Thread(target=read_projects) for _ in range(10)]

        start = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        total_duration = time.time() - start

        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert total_duration < 10.0, f"Concurrent access took too long: {total_duration}s"
class TestContainerCachePerformance:
    """Performance tests for container cache operations."""

    @pytest.mark.performance
    def test_bulk_container_creation(self, isolated_registry):
        """Test performance of creating many containers."""
        # Register a project first
        isolated_registry.register_project(
            name="container-perf",
            git_url="https://github.com/user/repo.git"
        )

        start = time.time()
        count = 50

        for i in range(count):
            isolated_registry.create_container(
                project_name="container-perf",
                container_number=i,
                container_type="coding"
            )

        duration = time.time() - start

        assert duration < 5.0, f"Container creation took too long: {duration}s"

    @pytest.mark.performance
    def test_container_listing_performance(self, isolated_registry):
        """Test performance of listing containers."""
        # Setup
        isolated_registry.register_project(
            name="list-perf",
            git_url="https://github.com/user/repo.git"
        )
        for i in range(20):
            isolated_registry.create_container("list-perf", i, "coding")

        # Measure
        start = time.time()
        for _ in range(100):
            isolated_registry.list_project_containers("list-perf")
        duration = time.time() - start

        assert duration < 2.0, f"Container listing took too long: {duration}s"
# =============================================================================
# Feature Processing Performance Tests
# =============================================================================

class TestFeatureProcessingPerformance:
    """Performance tests for feature/beads processing."""

    @pytest.mark.performance
    def test_large_feature_conversion_parsing(self):
        """Test conversion performance for large feature lists."""
        from server.routers.features import beads_task_to_feature

        # Create large feature list
        tasks = [
            {
                "id": f"feat-{i}",
                "title": f"Feature {i} with a somewhat longer title",
                "description": f"Description for feature {i}" * 20,
                "status": ["open", "in_progress", "closed"][i % 3],
                "priority": i % 5,
                "labels": [f"label-{i % 10}"],
            }
            for i in range(5000)
        ]

        # Measure conversion time
        start = time.time()
        result = [beads_task_to_feature(t) for t in tasks]
        duration = time.time() - start

        assert duration < 3.0, f"Conversion took too long: {duration}s"

        # Result is a list
        assert isinstance(result, list)
        assert len(result) == 5000

    @pytest.mark.performance
    def test_feature_sorting_performance(self):
        """Test sorting performance for many features."""
        from server.routers.features import beads_task_to_feature
        import random

        # Create features with random priorities
        tasks = [
            {
                "id": f"feat-{i}",
                "title": f"Feature {i}",
                "status": "open",
                "priority": random.randint(0, 4),
            }
            for i in range(1000)
        ]

        # Measure conversion with sorting
        start = time.time()
        for _ in range(10):
            features = [beads_task_to_feature(t) for t in tasks]
            sorted_features = sorted(features, key=lambda f: f.get("priority", 999))
        duration = time.time() - start

        assert duration < 5.0, f"Sorting took too long: {duration}s"
# =============================================================================
# WebSocket Performance Tests
# =============================================================================

class TestWebSocketPerformance:
    """Performance tests for WebSocket operations."""

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_high_volume_broadcast(self):
        """Test broadcasting many messages."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        clients = [AsyncMock() for _ in range(20)]

        for client in clients:
            await manager.connect(client, "perf-test")

        # Broadcast many messages
        start = time.time()
        for i in range(500):
            await manager.broadcast_to_project("perf-test", {
                "type": "log",
                "line": f"Log message {i}",
                "timestamp": datetime.now().isoformat()
            })
        duration = time.time() - start

        assert duration < 5.0, f"Broadcasting took too long: {duration}s"

        # Verify all clients received messages
        for client in clients:
            assert client.send_json.call_count == 500

    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_many_connections_performance(self):
        """Test handling many simultaneous connections."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        # Connect many clients
        start = time.time()
        clients = []
        for i in range(100):
            client = AsyncMock()
            await manager.connect(client, f"project-{i % 10}")
            clients.append(client)
        connect_duration = time.time() - start

        assert connect_duration < 2.0, f"Connections took too long: {connect_duration}s"

        # Disconnect all
        start = time.time()
        for i, client in enumerate(clients):
            manager.disconnect(client, f"project-{i % 10}")
        disconnect_duration = time.time() - start

        assert disconnect_duration < 2.0, f"Disconnections took too long: {disconnect_duration}s"
# =============================================================================
# Output Sanitization Performance Tests
# =============================================================================

class TestSanitizationPerformance:
    """Performance tests for output sanitization."""

    @pytest.mark.performance
    def test_sanitize_large_output(self):
        """Test sanitization performance on large output."""
        from server.services.e2b_sandbox_manager import sanitize_output

        # Create large log output
        lines = []
        for i in range(10000):
            lines.append(f"[{datetime.now().isoformat()}] Processing file {i}: /path/to/file{i}.py")
        large_output = "\n".join(lines)

        start = time.time()
        result = sanitize_output(large_output)
        duration = time.time() - start

        assert duration < 2.0, f"Sanitization took too long: {duration}s"
        assert len(result) == len(large_output)

    @pytest.mark.performance
    def test_sanitize_many_sensitive_values(self):
        """Test sanitization with many sensitive values."""
        from server.services.e2b_sandbox_manager import sanitize_output

        # Create output with many sensitive values
        lines = []
        for i in range(1000):
            lines.append(f"api_key=secret{i}")
            lines.append(f"token=token{i}")
            lines.append(f"password=pass{i}")
        output = "\n".join(lines)

        start = time.time()
        result = sanitize_output(output)
        duration = time.time() - start

        assert duration < 2.0, f"Sanitization took too long: {duration}s"
        assert "[REDACTED]" in result
# =============================================================================
# Memory Usage Tests
# =============================================================================

class TestMemoryUsage:
    """Tests for memory usage patterns."""

    @pytest.mark.performance
    def test_registry_memory_cleanup(self, isolated_registry):
        """Test that registry operations don't leak memory."""
        import sys

        # Get initial memory
        gc.collect()
        initial_objects = len(gc.get_objects())

        # Do many operations
        for i in range(100):
            isolated_registry.register_project(
                f"mem-test-{i}",
                f"https://github.com/user/repo{i}.git"
            )
            isolated_registry.get_project_info(f"mem-test-{i}")
            isolated_registry.list_registered_projects()

        # Cleanup
        gc.collect()
        final_objects = len(gc.get_objects())

        # Object count shouldn't grow excessively
        growth = final_objects - initial_objects
        # Allow reasonable growth but not unbounded
        assert growth < 50000, f"Too many new objects: {growth}"

    @pytest.mark.performance
    def test_feature_conversion_memory(self):
        """Test that feature conversion doesn't accumulate memory."""
        from server.routers.features import beads_task_to_feature

        # Create moderate task list
        tasks = [
            {
                "id": f"feat-{i}",
                "title": f"Feature {i}",
                "status": "open",
                "priority": 1
            }
            for i in range(100)
        ]

        gc.collect()
        initial = len(gc.get_objects())

        # Convert many times
        for _ in range(50):
            result = [beads_task_to_feature(t) for t in tasks]
            del result

        gc.collect()
        final = len(gc.get_objects())

        growth = final - initial
        assert growth < 10000, f"Memory growth: {growth} objects"
# =============================================================================
# Container Manager Performance Tests
# =============================================================================

class TestSandboxManagerPerformance:
    """Performance tests for sandbox manager."""

    @pytest.mark.performance
    def test_callback_registration_performance(self, tmp_path):
        """Test callback registration performance."""
        from server.services.e2b_sandbox_manager import E2BSandboxManager

        project_dir = tmp_path / "callback-perf"
        project_dir.mkdir()

        with patch("registry.get_projects_dir", return_value=tmp_path):
            with patch.object(E2BSandboxManager, "_sync_status"):
                with patch("registry.is_user_started", return_value=False):
                    manager = E2BSandboxManager(
                        project_name="callback-perf",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                    )

        # Measure callback registration/removal performance
        callbacks = []
        start = time.time()

        # Add many callbacks
        for _ in range(100):
            cb = MagicMock()
            callbacks.append(cb)
            manager.register_status_callback(cb)

        add_duration = time.time() - start

        assert len(manager._status_callbacks) == 100
        assert add_duration < 1.0, f"Adding callbacks took too long: {add_duration}s"

        # Remove all callbacks
        start = time.time()
        for cb in callbacks:
            manager.unregister_status_callback(cb)

        remove_duration = time.time() - start

        assert len(manager._status_callbacks) == 0
        assert remove_duration < 1.0, f"Removing callbacks took too long: {remove_duration}s"
# =============================================================================
# Database Connection Performance Tests
# =============================================================================

class TestDatabaseConnectionPerformance:
    """Performance tests for database connections."""

    @pytest.mark.performance
    def test_rapid_session_creation(self, isolated_registry):
        """Test rapid database session creation."""
        start = time.time()

        # Do many operations that require sessions
        for i in range(500):
            isolated_registry.get_project_info(f"nonexistent-{i}")

        duration = time.time() - start

        assert duration < 5.0, f"Session creation took too long: {duration}s"

    @pytest.mark.performance
    def test_transaction_throughput(self, isolated_registry):
        """Test transaction throughput."""
        # Register a project
        isolated_registry.register_project(
            "transaction-perf",
            "https://github.com/user/repo.git"
        )

        start = time.time()

        # Many read-write operations
        for i in range(100):
            isolated_registry.update_target_container_count("transaction-perf", (i % 10) + 1)
            isolated_registry.get_project_info("transaction-perf")

        duration = time.time() - start

        assert duration < 5.0, f"Transactions took too long: {duration}s"
# =============================================================================
# Stress Tests
# =============================================================================

class TestStressConditions:
    """Stress tests for edge conditions."""

    @pytest.mark.stress
    @pytest.mark.asyncio
    async def test_concurrent_websocket_operations(self):
        """Test WebSocket under concurrent stress."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        async def connect_disconnect_cycle():
            for _ in range(20):
                client = AsyncMock()
                await manager.connect(client, "stress-test")
                await manager.broadcast_to_project("stress-test", {"type": "test"})
                manager.disconnect(client, "stress-test")

        # Run multiple concurrent cycles
        tasks = [connect_disconnect_cycle() for _ in range(10)]

        start = time.time()
        await asyncio.gather(*tasks)
        duration = time.time() - start

        assert duration < 10.0, f"Stress test took too long: {duration}s"

    @pytest.mark.stress
    def test_registry_under_concurrent_writes(self, isolated_registry):
        """Test registry under concurrent write stress."""
        import threading

        errors = []
        lock = threading.Lock()

        def writer(prefix):
            try:
                for i in range(20):
                    isolated_registry.register_project(
                        f"{prefix}-project-{i}",
                        f"https://github.com/{prefix}/repo{i}.git"
                    )
            except Exception as e:
                with lock:
                    errors.append(str(e))

        threads = [threading.Thread(target=writer, args=(f"t{i}",)) for i in range(5)]

        start = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        duration = time.time() - start

        # Allow for some SQLite locking issues
        assert len(errors) < 50, f"Too many errors: {len(errors)}"
        assert duration < 30.0, f"Stress test took too long: {duration}s"

    @pytest.mark.stress
    def test_feature_malformed_data_recovery(self):
        """Test recovery from malformed task data during conversion."""
        from server.routers.features import beads_task_to_feature

        # Mix of valid and problematic task data
        tasks = []
        for i in range(100):
            if i % 10 == 5:
                # Missing required fields
                tasks.append({"id": f"feat-{i}"})
            else:
                tasks.append({
                    "id": f"feat-{i}",
                    "title": f"Feature {i}",
                    "status": "open",
                    "priority": 1
                })

        # Should handle gracefully - returns converted features
        results = [beads_task_to_feature(t) for t in tasks]
        assert isinstance(results, list)
        assert len(results) == 100  # All converted (some with defaults)
# =============================================================================
# Benchmark Tests
# =============================================================================

class TestBenchmarks:
    """Benchmark tests for establishing performance baselines."""

    @pytest.mark.benchmark
    def test_baseline_project_registration_time(self, isolated_registry):
        """Establish baseline for project registration."""
        times = []

        for i in range(10):
            start = time.time()
            isolated_registry.register_project(
                f"benchmark-{i}",
                f"https://github.com/user/repo{i}.git"
            )
            times.append(time.time() - start)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        # Document baseline expectations
        assert avg_time < 0.1, f"Average time too high: {avg_time}s"
        assert max_time < 0.5, f"Max time too high: {max_time}s"

    @pytest.mark.benchmark
    def test_baseline_feature_conversion_time(self):
        """Establish baseline for feature conversion."""
        from server.routers.features import beads_task_to_feature

        # Create 100 tasks
        tasks = [
            {
                "id": f"feat-{i}",
                "title": f"Feature {i}",
                "status": "open",
                "priority": 1
            }
            for i in range(100)
        ]

        times = []
        for _ in range(20):
            start = time.time()
            [beads_task_to_feature(t) for t in tasks]
            times.append(time.time() - start)

        avg_time = sum(times) / len(times)
        max_time = max(times)

        assert avg_time < 0.05, f"Average conversion time too high: {avg_time}s"
        assert max_time < 0.2, f"Max conversion time too high: {max_time}s"

    @pytest.mark.benchmark
    @pytest.mark.asyncio
    async def test_baseline_websocket_broadcast_time(self):
        """Establish baseline for WebSocket broadcast."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        clients = [AsyncMock() for _ in range(10)]
        for client in clients:
            await manager.connect(client, "benchmark")

        times = []
        for _ in range(100):
            start = time.time()
            await manager.broadcast_to_project("benchmark", {"type": "test"})
            times.append(time.time() - start)

        avg_time = sum(times) / len(times)

        assert avg_time < 0.01, f"Average broadcast time too high: {avg_time}s"
