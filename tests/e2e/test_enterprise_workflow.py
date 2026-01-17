"""
Enterprise End-to-End Workflow Tests
====================================

Comprehensive E2E tests simulating real-world usage scenarios:
- Complete project lifecycle
- Multi-container orchestration
- WebSocket communication
- Error recovery
- Performance under load
"""

import asyncio
import json
import pytest
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Complete Project Workflow Tests
# =============================================================================

class TestCompleteProjectWorkflow:
    """End-to-end tests for complete project workflows."""

    @pytest.fixture
    def isolated_environment(self, tmp_path, monkeypatch):
        """Set up isolated test environment."""
        import registry

        # Reset registry state
        registry._engine = None
        registry._SessionLocal = None

        # Create directories
        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()
        (temp_config / "beads-sync").mkdir()

        # Patch registry paths
        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "registry.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        yield {
            "registry": registry,
            "config_dir": temp_config,
            "projects_dir": temp_config / "projects",
            "tmp_path": tmp_path,
        }

    @pytest.mark.e2e
    def test_new_project_creation_workflow(self, isolated_environment):
        """Test complete new project creation workflow."""
        env = isolated_environment
        registry = env["registry"]
        projects_dir = env["projects_dir"]

        from registry import register_project, get_project_info, list_registered_projects

        # Step 1: Register project
        register_project("new-workflow-test", "https://github.com/user/repo.git", is_new=True)

        # Step 2: Verify registration
        info = get_project_info("new-workflow-test")
        assert info is not None
        assert info["git_url"] == "https://github.com/user/repo.git"
        assert info["is_new"] is True

        # Step 3: List projects
        projects = list_registered_projects()
        assert "new-workflow-test" in projects

    @pytest.mark.e2e
    def test_existing_repo_workflow(self, isolated_environment):
        """Test workflow for adding existing repository."""
        env = isolated_environment
        registry = env["registry"]

        from registry import register_project, mark_project_initialized, get_project_info

        # Step 1: Register as existing (is_new=False)
        register_project("existing-repo-test", "https://github.com/user/existing.git", is_new=False)

        # Step 2: Verify not marked as new
        info = get_project_info("existing-repo-test")
        assert info["is_new"] is False

        # Step 3: No wizard needed for existing repos
        # (in real scenario, beads would be initialized directly)

    @pytest.mark.e2e
    def test_project_deletion_workflow(self, isolated_environment):
        """Test complete project deletion workflow."""
        env = isolated_environment
        registry = env["registry"]

        from registry import (
            register_project,
            unregister_project,
            get_project_path,
            list_registered_projects,
        )

        # Step 1: Create project
        register_project("delete-test", "https://github.com/user/repo.git")
        assert "delete-test" in list_registered_projects()

        # Step 2: Delete project
        unregister_project("delete-test")

        # Step 3: Verify deletion
        assert "delete-test" not in list_registered_projects()
        assert get_project_path("delete-test") is None


# =============================================================================
# Multi-Container Orchestration Tests
# =============================================================================

class TestMultiContainerOrchestration:
    """End-to-end tests for multi-container orchestration."""

    @pytest.fixture
    def container_env(self, tmp_path):
        """Set up container test environment."""
        project_dir = tmp_path / "multi-container-test"
        project_dir.mkdir()
        (project_dir / "prompts").mkdir()
        (project_dir / ".beads").mkdir()
        (project_dir / ".git").mkdir()

        return project_dir

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_init_then_coding_containers(self, container_env, tmp_path):
        """Test init container followed by coding containers."""
        from server.services.container_manager import (
            ContainerManager,
            get_container_manager,
            _container_managers,
        )

        _container_managers.clear()

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    # Step 1: Create init container
                    init_manager = get_container_manager(
                        project_name="multi-container-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=0,
                        project_dir=container_env,
                    )

                    assert init_manager.container_name == "zerocoder-multi-container-test-init"
                    assert init_manager._is_init_container is True

                    # Step 2: Create coding containers
                    coding_managers = []
                    for i in range(1, 4):
                        manager = get_container_manager(
                            project_name="multi-container-test",
                            git_url="https://github.com/user/repo.git",
                            container_number=i,
                            project_dir=container_env,
                        )
                        coding_managers.append(manager)
                        assert manager.container_name == f"zerocoder-multi-container-test-{i}"
                        assert manager._is_init_container is False

                    # Step 3: Verify all containers created
                    assert len(coding_managers) == 3

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_callback_propagation_across_containers(self, container_env, tmp_path):
        """Test that callbacks work across multiple containers."""
        from server.services.container_manager import (
            ContainerManager,
            get_container_manager,
            _container_managers,
        )

        _container_managers.clear()

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    # Create multiple containers
                    managers = []
                    callbacks = []

                    for i in range(3):
                        manager = get_container_manager(
                            project_name="callback-test",
                            git_url="https://github.com/user/repo.git",
                            container_number=i,
                            project_dir=container_env,
                        )
                        managers.append(manager)

                        callback = AsyncMock()
                        callbacks.append(callback)
                        manager.add_status_callback(callback)

                    # Notify status changes
                    for manager in managers:
                        await manager._notify_status("running")

                    # Verify each callback was called
                    for callback in callbacks:
                        callback.assert_called_once_with("running")


# =============================================================================
# WebSocket Communication Tests
# =============================================================================

class TestWebSocketCommunication:
    """End-to-end tests for WebSocket communication."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_broadcast_progress_updates(self):
        """Test broadcasting progress updates to clients."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        clients = [AsyncMock() for _ in range(5)]

        # Connect clients
        for client in clients:
            await manager.connect(client, "progress-test")

        # Simulate progress updates
        progress_updates = [
            {"type": "progress", "passing": 1, "total": 10, "percentage": 10},
            {"type": "progress", "passing": 5, "total": 10, "percentage": 50},
            {"type": "progress", "passing": 10, "total": 10, "percentage": 100},
        ]

        for update in progress_updates:
            await manager.broadcast_to_project("progress-test", update)

        # Verify all clients received all updates
        for client in clients:
            assert client.send_json.call_count == 3

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_log_streaming_to_clients(self):
        """Test streaming logs to connected clients."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        client = AsyncMock()

        await manager.connect(client, "log-test")

        # Simulate log streaming
        log_lines = [
            {"type": "log", "line": "Starting agent...", "timestamp": datetime.now().isoformat()},
            {"type": "log", "line": "Processing feat-1", "timestamp": datetime.now().isoformat()},
            {"type": "log", "line": "Feature completed", "timestamp": datetime.now().isoformat()},
        ]

        for log in log_lines:
            await manager.broadcast_to_project("log-test", log)

        # Verify log messages received
        assert client.send_json.call_count == 3

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_client_reconnection_scenario(self):
        """Test handling client reconnection."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        client = AsyncMock()

        # Initial connection
        await manager.connect(client, "reconnect-test")
        assert client in manager.active_connections.get("reconnect-test", [])

        # Disconnect
        manager.disconnect(client, "reconnect-test")
        assert client not in manager.active_connections.get("reconnect-test", [])

        # Reconnect
        await manager.connect(client, "reconnect-test")
        assert client in manager.active_connections.get("reconnect-test", [])

        # Verify can receive messages after reconnection
        await manager.broadcast_to_project("reconnect-test", {"type": "test"})
        client.send_json.assert_called()


# =============================================================================
# Feature Management Workflow Tests
# =============================================================================

class TestFeatureManagementWorkflow:
    """End-to-end tests for feature management workflows."""

    @pytest.fixture
    def project_with_beads(self, tmp_path):
        """Create project with beads setup."""
        project_dir = tmp_path / "feature-workflow-test"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat\n")

        return project_dir

    @pytest.mark.e2e
    def test_feature_lifecycle(self, project_with_beads):
        """Test complete feature lifecycle: create -> in_progress -> done."""
        beads_dir = project_with_beads / ".beads"
        issues_file = beads_dir / "issues.jsonl"

        # Step 1: Create features (simulated)
        features = [
            {"id": "feat-1", "title": "Auth", "status": "open", "priority": 0},
            {"id": "feat-2", "title": "Dashboard", "status": "open", "priority": 1},
            {"id": "feat-3", "title": "API", "status": "open", "priority": 2},
        ]

        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        # Step 2: Move feat-1 to in_progress
        features[0]["status"] = "in_progress"
        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        # Step 3: Complete feat-1
        features[0]["status"] = "closed"
        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        # Step 4: Read and verify
        from server.routers.features import read_local_beads_features
        result = read_local_beads_features(project_with_beads)

        assert len(result["pending"]) == 2
        assert len(result["done"]) == 1
        assert result["done"][0]["name"] == "Auth"

    @pytest.mark.e2e
    def test_priority_ordering(self, project_with_beads):
        """Test that features are ordered by priority."""
        beads_dir = project_with_beads / ".beads"
        issues_file = beads_dir / "issues.jsonl"

        # Create features with various priorities
        features = [
            {"id": "feat-1", "title": "Low Priority", "status": "open", "priority": 4},
            {"id": "feat-2", "title": "High Priority", "status": "open", "priority": 0},
            {"id": "feat-3", "title": "Medium Priority", "status": "open", "priority": 2},
        ]

        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        # Read features
        from server.routers.features import read_local_beads_features
        result = read_local_beads_features(project_with_beads)

        # Should be ordered by priority
        priorities = [f["priority"] for f in result["pending"]]
        assert priorities == sorted(priorities)


# =============================================================================
# Error Recovery Tests
# =============================================================================

class TestErrorRecovery:
    """End-to-end tests for error recovery scenarios."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_websocket_error_recovery(self):
        """Test WebSocket manager recovers from client errors."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        # Mix of healthy and failing clients
        healthy_clients = [AsyncMock() for _ in range(3)]
        failing_client = AsyncMock()
        failing_client.send_json.side_effect = Exception("Connection lost")

        # Connect all
        for client in healthy_clients:
            await manager.connect(client, "error-recovery")
        await manager.connect(failing_client, "error-recovery")

        # Broadcast - should not fail
        await manager.broadcast_to_project("error-recovery", {"type": "test"})

        # Healthy clients should have received message
        for client in healthy_clients:
            client.send_json.assert_called_once()

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_container_callback_error_isolation(self, tmp_path):
        """Test that callback errors don't affect other callbacks."""
        from server.services.container_manager import ContainerManager, _container_managers

        _container_managers.clear()

        project_dir = tmp_path / "callback-error"
        project_dir.mkdir()

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="callback-error",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )

        # Add failing and successful callbacks
        failing = AsyncMock(side_effect=Exception("Callback failed"))
        successful = AsyncMock()

        manager.add_status_callback(failing)
        manager.add_status_callback(successful)

        # Should not raise and successful should be called
        await manager._notify_status("running")

        successful.assert_called_once_with("running")


# =============================================================================
# Performance Tests
# =============================================================================

class TestPerformance:
    """End-to-end performance tests."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_websocket_high_volume_messages(self):
        """Test WebSocket handling of high-volume messages."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        clients = [AsyncMock() for _ in range(10)]

        for client in clients:
            await manager.connect(client, "perf-test")

        # Send 100 messages
        start = time.time()
        for i in range(100):
            await manager.broadcast_to_project("perf-test", {
                "type": "progress",
                "passing": i,
                "total": 100,
            })
        duration = time.time() - start

        # Should complete in under 2 seconds
        assert duration < 2.0

        # All clients should have received all messages
        for client in clients:
            assert client.send_json.call_count == 100

    @pytest.mark.e2e
    def test_large_feature_list_performance(self, tmp_path):
        """Test performance with large feature list."""
        project_dir = tmp_path / "large-features"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        # Create 100 features
        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for i in range(100):
                feature = {
                    "id": f"feat-{i}",
                    "title": f"Feature {i}",
                    "status": "open" if i % 3 == 0 else ("in_progress" if i % 3 == 1 else "closed"),
                    "priority": i % 5,
                    "labels": [f"label-{i % 10}"],
                    "description": f"Description for feature {i}" * 10,
                }
                f.write(json.dumps(feature) + "\n")

        # Measure read time
        from server.routers.features import read_local_beads_features

        start = time.time()
        result = read_local_beads_features(project_dir)
        duration = time.time() - start

        # Should complete in under 1 second
        assert duration < 1.0
        assert len(result["pending"]) + len(result["in_progress"]) + len(result["done"]) == 100

    @pytest.mark.e2e
    def test_registry_concurrent_access(self, tmp_path, monkeypatch):
        """Test registry performance under concurrent access."""
        import registry
        import threading

        # Reset registry state
        registry._engine = None
        registry._SessionLocal = None

        # Use temp path
        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "concurrent.db")
        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")

        from registry import register_project, list_registered_projects

        results = []
        errors = []

        def register_projects(prefix: str, count: int):
            try:
                for i in range(count):
                    register_project(
                        f"{prefix}-project-{i}",
                        f"https://github.com/{prefix}/repo{i}.git"
                    )
                results.append(count)
            except Exception as e:
                errors.append(e)

        # Create threads
        threads = [
            threading.Thread(target=register_projects, args=(f"t{i}", 10))
            for i in range(5)
        ]

        # Start all threads
        start = time.time()
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join()
        duration = time.time() - start

        # Verify
        assert len(errors) == 0, f"Errors: {errors}"
        assert sum(results) == 50

        # All projects should be registered
        projects = list_registered_projects()
        assert len(projects) == 50

        # Should complete in reasonable time
        assert duration < 10.0


# =============================================================================
# Integration Scenario Tests
# =============================================================================

class TestIntegrationScenarios:
    """Tests for complex integration scenarios."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_project_setup_to_completion_flow(self, tmp_path, monkeypatch):
        """Test complete flow from project setup to feature completion."""
        import registry

        # Setup isolated registry
        registry._engine = None
        registry._SessionLocal = None
        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "flow.db")
        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")

        from registry import register_project, mark_project_initialized, get_project_info

        # Step 1: Create new project
        register_project("flow-test", "https://github.com/user/repo.git", is_new=True)
        assert get_project_info("flow-test")["is_new"] is True

        # Step 2: Setup project (wizard completion)
        project_dir = temp_config / "projects" / "flow-test"
        project_dir.mkdir(parents=True)
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "app_spec.txt").write_text("<app-spec><name>Flow Test</name></app-spec>")

        # Step 3: Mark initialized
        mark_project_initialized("flow-test")
        assert get_project_info("flow-test")["is_new"] is False

        # Step 4: Create features (via beads)
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text(
            '{"id":"feat-1","title":"Auth","status":"open","priority":0}\n'
            '{"id":"feat-2","title":"Dashboard","status":"open","priority":1}\n'
        )

        # Step 5: Verify features exist
        from progress import has_features
        assert has_features(project_dir) is True

        # Step 6: Complete features
        issues_file.write_text(
            '{"id":"feat-1","title":"Auth","status":"closed","priority":0}\n'
            '{"id":"feat-2","title":"Dashboard","status":"closed","priority":1}\n'
        )

        # Step 7: Verify completion
        from progress import has_open_features
        assert has_open_features(project_dir) is False

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_multi_project_parallel_operations(self, tmp_path, monkeypatch):
        """Test parallel operations across multiple projects."""
        import registry

        # Setup isolated registry
        registry._engine = None
        registry._SessionLocal = None
        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "parallel.db")
        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")

        from registry import register_project, list_registered_projects

        # Create multiple projects
        projects = ["project-a", "project-b", "project-c"]
        for name in projects:
            register_project(name, f"https://github.com/user/{name}.git")

        # Setup WebSocket connections for each
        from server.websocket import ConnectionManager
        ws_manager = ConnectionManager()

        clients = {}
        for name in projects:
            client = AsyncMock()
            clients[name] = client
            await ws_manager.connect(client, name)

        # Broadcast to each project
        for name in projects:
            await ws_manager.broadcast_to_project(name, {"project": name, "type": "test"})

        # Verify isolation
        for name in projects:
            clients[name].send_json.assert_called_once()
            call_args = clients[name].send_json.call_args[0][0]
            assert call_args["project"] == name
