"""
Performance and Stress Enterprise Tests
=======================================

Comprehensive enterprise-grade performance and stress tests including:
- Load testing
- Memory usage patterns
- Concurrent access stress
- Large dataset handling
- Response time benchmarks
"""

import asyncio
import gc
import json
import pytest
import random
import sys
import threading
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Registry Performance Tests
# =============================================================================

class TestRegistryPerformance:
    """Performance tests for registry operations."""

    @pytest.fixture
    def perf_registry(self, tmp_path, monkeypatch):
        """Setup registry for performance tests."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "perf.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        return registry

    @pytest.mark.unit
    @pytest.mark.slow
    def test_bulk_project_registration(self, perf_registry):
        """Test performance of bulk project registration."""
        start = time.time()

        for i in range(100):
            perf_registry.register_project(
                name=f"bulk-project-{i}",
                git_url=f"https://github.com/user/repo{i}.git"
            )

        elapsed = time.time() - start

        # Should complete 100 registrations in under 5 seconds
        assert elapsed < 5.0, f"Bulk registration took {elapsed:.2f}s"

        # Verify all registered
        projects = perf_registry.list_registered_projects()
        assert len(projects) == 100

    @pytest.mark.unit
    @pytest.mark.slow
    def test_bulk_project_lookup(self, perf_registry):
        """Test performance of bulk project lookups."""
        # Setup: register projects
        for i in range(100):
            perf_registry.register_project(
                name=f"lookup-project-{i}",
                git_url=f"https://github.com/user/repo{i}.git"
            )

        # Benchmark lookups
        start = time.time()

        for i in range(1000):
            idx = i % 100
            perf_registry.get_project_info(f"lookup-project-{idx}")

        elapsed = time.time() - start

        # Should complete 1000 lookups in under 2 seconds
        assert elapsed < 2.0, f"Bulk lookup took {elapsed:.2f}s"

    @pytest.mark.unit
    @pytest.mark.slow
    def test_container_creation_performance(self, perf_registry):
        """Test performance of container creation."""
        # Setup: register projects
        for i in range(10):
            perf_registry.register_project(
                name=f"container-perf-{i}",
                git_url=f"https://github.com/user/repo{i}.git"
            )

        # Benchmark container creation
        start = time.time()

        for i in range(10):
            for j in range(1, 11):
                perf_registry.create_container(f"container-perf-{i}", j, "coding")

        elapsed = time.time() - start

        # Should create 100 containers in under 3 seconds
        assert elapsed < 3.0, f"Container creation took {elapsed:.2f}s"


# =============================================================================
# Memory Usage Tests
# =============================================================================

class TestMemoryUsage:
    """Tests for memory usage patterns."""

    @pytest.mark.unit
    @pytest.mark.slow
    def test_large_issues_file_memory(self, tmp_path):
        """Test memory usage with large issues file."""
        from progress import count_passing_tests

        project_dir = tmp_path / "large-issues"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat\n")

        # Create large issues file
        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for i in range(10000):
                issue = {
                    "id": f"feat-{i}",
                    "title": f"Feature {i} with a longer description to increase memory",
                    "status": "open" if i % 3 == 0 else ("in_progress" if i % 3 == 1 else "closed"),
                    "priority": i % 5,
                    "description": "Lorem ipsum " * 50,
                }
                f.write(json.dumps(issue) + "\n")

        # Start memory tracking
        tracemalloc.start()

        passing, in_progress, total = count_passing_tests(project_dir)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Verify correctness
        assert total == 10000

        # Peak memory should be under 100MB for 10k issues
        assert peak < 100 * 1024 * 1024, f"Peak memory: {peak / 1024 / 1024:.2f}MB"

    @pytest.mark.unit
    @pytest.mark.slow
    def test_session_memory_leak(self, tmp_path, monkeypatch):
        """Test for memory leaks in repeated session creation."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "leak.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        # Register a project
        registry.register_project(
            name="leak-test",
            git_url="https://github.com/test/repo.git"
        )

        # Force garbage collection
        gc.collect()

        tracemalloc.start()
        baseline = tracemalloc.get_traced_memory()[0]

        # Perform many operations
        for i in range(1000):
            registry.get_project_info("leak-test")

        gc.collect()
        current = tracemalloc.get_traced_memory()[0]
        tracemalloc.stop()

        # Memory growth should be minimal
        growth = (current - baseline) / 1024  # KB
        assert growth < 1024, f"Memory grew by {growth:.2f}KB"


# =============================================================================
# Concurrent Access Stress Tests
# =============================================================================

class TestConcurrentStress:
    """Stress tests for concurrent access."""

    @pytest.fixture
    def stress_registry(self, tmp_path, monkeypatch):
        """Setup registry for stress tests."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "stress.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        return registry

    @pytest.mark.unit
    @pytest.mark.slow
    def test_concurrent_reads(self, stress_registry):
        """Stress test concurrent read operations."""
        # Setup
        for i in range(10):
            stress_registry.register_project(
                name=f"stress-read-{i}",
                git_url=f"https://github.com/user/repo{i}.git"
            )

        results = []
        errors = []
        lock = threading.Lock()

        def read_operation():
            try:
                for _ in range(100):
                    idx = random.randint(0, 9)
                    stress_registry.get_project_info(f"stress-read-{idx}")
                with lock:
                    results.append(True)
            except Exception as e:
                with lock:
                    errors.append(str(e))

        # Run 20 concurrent readers
        threads = [threading.Thread(target=read_operation) for _ in range(20)]

        start = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.time() - start

        # All should succeed
        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 20

        # Should complete in reasonable time
        assert elapsed < 10.0, f"Stress test took {elapsed:.2f}s"

    @pytest.mark.unit
    @pytest.mark.slow
    def test_concurrent_mixed_operations(self, stress_registry):
        """Stress test mixed read/write operations."""
        # Setup initial projects
        for i in range(10):
            stress_registry.register_project(
                name=f"stress-mixed-{i}",
                git_url=f"https://github.com/user/repo{i}.git"
            )

        results = {"reads": 0, "writes": 0}
        errors = []
        lock = threading.Lock()

        def mixed_operation(thread_id):
            try:
                for i in range(50):
                    if random.random() < 0.8:  # 80% reads
                        idx = random.randint(0, 9)
                        stress_registry.get_project_info(f"stress-mixed-{idx}")
                        with lock:
                            results["reads"] += 1
                    else:  # 20% writes
                        stress_registry.create_container(
                            f"stress-mixed-{thread_id % 10}",
                            i % 10 + 1,
                            "coding"
                        )
                        with lock:
                            results["writes"] += 1
            except Exception as e:
                with lock:
                    errors.append(str(e))

        threads = [
            threading.Thread(target=mixed_operation, args=(i,))
            for i in range(10)
        ]

        start = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.time() - start

        # Most operations should succeed (some write conflicts expected)
        total_ops = results["reads"] + results["writes"]
        assert total_ops > 400, f"Only {total_ops} operations completed"

        # Should complete in reasonable time
        assert elapsed < 15.0, f"Mixed stress test took {elapsed:.2f}s"


# =============================================================================
# Large Dataset Handling Tests
# =============================================================================

class TestLargeDatasets:
    """Tests for handling large datasets."""

    @pytest.mark.unit
    @pytest.mark.slow
    def test_large_feature_list_parsing(self, tmp_path):
        """Test parsing large feature lists."""
        from server.routers.features import read_local_beads_features

        project_dir = tmp_path / "large-features"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for i in range(5000):
                issue = {
                    "id": f"feat-{i}",
                    "title": f"Feature {i}",
                    "status": "open",
                    "priority": i % 5,
                    "labels": [f"label-{i % 10}"],
                    "description": "1. Step one\n2. Step two\n3. Step three",
                }
                f.write(json.dumps(issue) + "\n")

        start = time.time()
        features = read_local_beads_features(project_dir)
        elapsed = time.time() - start

        assert len(features) == 5000
        assert elapsed < 5.0, f"Parsing took {elapsed:.2f}s"

    @pytest.mark.unit
    @pytest.mark.slow
    def test_large_project_list(self, tmp_path, monkeypatch):
        """Test handling large number of projects."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "large.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        # Register many projects
        for i in range(500):
            registry.register_project(
                name=f"large-project-{i}",
                git_url=f"https://github.com/user/repo{i}.git"
            )

        # Time listing
        start = time.time()
        projects = registry.list_registered_projects()
        elapsed = time.time() - start

        assert len(projects) == 500
        assert elapsed < 1.0, f"Listing took {elapsed:.2f}s"


# =============================================================================
# Response Time Benchmarks
# =============================================================================

class TestResponseTimeBenchmarks:
    """Benchmark tests for response times."""

    @pytest.fixture
    def benchmark_setup(self, tmp_path, monkeypatch):
        """Setup for benchmark tests."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "bench.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        # Setup test data
        registry.register_project(
            name="bench-project",
            git_url="https://github.com/test/repo.git"
        )

        for i in range(1, 11):
            registry.create_container("bench-project", i, "coding")

        return registry, temp_config

    @pytest.mark.unit
    def test_project_lookup_latency(self, benchmark_setup):
        """Benchmark single project lookup latency."""
        registry, _ = benchmark_setup

        latencies = []
        for _ in range(100):
            start = time.perf_counter()
            registry.get_project_info("bench-project")
            latency = (time.perf_counter() - start) * 1000  # ms
            latencies.append(latency)

        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        p95_latency = sorted(latencies)[94]

        # Average should be under 5ms
        assert avg_latency < 5.0, f"Avg latency: {avg_latency:.2f}ms"
        # P95 should be under 10ms
        assert p95_latency < 10.0, f"P95 latency: {p95_latency:.2f}ms"

    @pytest.mark.unit
    def test_container_list_latency(self, benchmark_setup):
        """Benchmark container list latency."""
        registry, _ = benchmark_setup

        latencies = []
        for _ in range(100):
            start = time.perf_counter()
            registry.list_project_containers("bench-project")
            latency = (time.perf_counter() - start) * 1000  # ms
            latencies.append(latency)

        avg_latency = sum(latencies) / len(latencies)
        p95_latency = sorted(latencies)[94]

        # Average should be under 5ms
        assert avg_latency < 5.0, f"Avg latency: {avg_latency:.2f}ms"
        # P95 should be under 10ms
        assert p95_latency < 10.0, f"P95 latency: {p95_latency:.2f}ms"

    @pytest.mark.unit
    def test_progress_calculation_latency(self, benchmark_setup, tmp_path):
        """Benchmark progress calculation latency."""
        from progress import count_passing_tests

        _, temp_config = benchmark_setup

        project_dir = temp_config / "projects" / "bench-project"
        project_dir.mkdir(parents=True)
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat\n")

        # Create 100 features
        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for i in range(100):
                f.write(json.dumps({
                    "id": f"feat-{i}",
                    "title": f"Feature {i}",
                    "status": "closed" if i < 50 else "open"
                }) + "\n")

        latencies = []
        for _ in range(50):
            start = time.perf_counter()
            count_passing_tests(project_dir)
            latency = (time.perf_counter() - start) * 1000  # ms
            latencies.append(latency)

        avg_latency = sum(latencies) / len(latencies)
        p95_latency = sorted(latencies)[47]

        # Average should be under 20ms for 100 features
        assert avg_latency < 20.0, f"Avg latency: {avg_latency:.2f}ms"


# =============================================================================
# Sanitization Performance Tests
# =============================================================================

class TestSanitizationPerformance:
    """Performance tests for output sanitization."""

    @pytest.mark.unit
    def test_sanitize_output_performance(self):
        """Benchmark output sanitization."""
        from server.services.container_manager import sanitize_output

        # Generate test lines
        test_lines = [
            "Normal log line without secrets",
            "api_key=secret123 some data",
            "Processing file with token=abc123",
            "Error: password=hidden in message",
            "sk-ant-api03-xxxxxxxxxxxxxxxxxxxx leaked",
        ] * 200  # 1000 lines

        start = time.time()
        for line in test_lines:
            sanitize_output(line)
        elapsed = time.time() - start

        # Should process 1000 lines in under 100ms
        assert elapsed < 0.1, f"Sanitization took {elapsed * 1000:.2f}ms"

    @pytest.mark.unit
    def test_sanitize_long_line_performance(self):
        """Test sanitization performance with long lines."""
        from server.services.container_manager import sanitize_output

        # Generate long line with multiple secrets
        long_line = " ".join([
            f"data_{i} api_key=secret{i} token=tok{i}"
            for i in range(100)
        ])

        start = time.time()
        for _ in range(100):
            sanitize_output(long_line)
        elapsed = time.time() - start

        # Should process 100 long lines in under 500ms
        assert elapsed < 0.5, f"Long line sanitization took {elapsed * 1000:.2f}ms"


# =============================================================================
# WebSocket Performance Tests
# =============================================================================

class TestWebSocketPerformance:
    """Performance tests for WebSocket operations."""

    @pytest.mark.unit
    def test_connection_manager_creation_performance(self):
        """Test ConnectionManager creation performance."""
        from server.websocket import ConnectionManager

        start = time.time()

        managers = []
        for _ in range(100):
            manager = ConnectionManager()
            managers.append(manager)

        elapsed = time.time() - start

        # Should create 100 managers in under 100ms
        assert elapsed < 0.1, f"Manager creation took {elapsed * 1000:.2f}ms"

    @pytest.mark.unit
    def test_dict_operations_performance(self):
        """Test performance of dict operations similar to connection tracking."""
        start = time.time()

        connections = {}
        for i in range(1000):
            project = f"project-{i % 10}"
            if project not in connections:
                connections[project] = set()
            connections[project].add(f"ws-{i}")

        # Simulate disconnects
        for i in range(500):
            project = f"project-{i % 10}"
            ws = f"ws-{i}"
            if ws in connections.get(project, set()):
                connections[project].discard(ws)

        elapsed = time.time() - start

        # Should complete in under 50ms
        assert elapsed < 0.05, f"Dict operations took {elapsed * 1000:.2f}ms"
