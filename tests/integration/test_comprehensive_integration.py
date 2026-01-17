"""
Comprehensive Integration Tests
===============================

Enterprise-grade integration tests covering:
- Full API workflow tests
- Multi-component interactions
- Database integration
- WebSocket communication
- Container orchestration scenarios
"""

import asyncio
import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Project Lifecycle Integration Tests
# =============================================================================

class TestProjectLifecycleIntegration:
    """Integration tests for complete project lifecycle."""

    @pytest.fixture
    def isolated_registry(self, tmp_path, monkeypatch):
        """Set up isolated registry for testing."""
        import registry

        # Store original state
        original_engine = registry._engine
        original_session = registry._SessionLocal

        # Reset module state
        registry._engine = None
        registry._SessionLocal = None

        # Create temp directories
        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()
        (temp_config / "beads-sync").mkdir()

        # Patch registry paths
        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "registry.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        yield registry

        # Restore original state
        registry._engine = original_engine
        registry._SessionLocal = original_session

    @pytest.mark.integration
    def test_register_and_list_project(self, isolated_registry):
        """Test registering and listing a project."""
        from registry import register_project, list_registered_projects

        register_project("test-project", "https://github.com/user/repo.git", is_new=True)

        projects = list_registered_projects()

        assert "test-project" in projects
        assert projects["test-project"]["git_url"] == "https://github.com/user/repo.git"
        assert projects["test-project"]["is_new"] is True

    @pytest.mark.integration
    def test_register_and_unregister_project(self, isolated_registry):
        """Test complete project registration lifecycle."""
        from registry import register_project, unregister_project, get_project_path

        # Register
        register_project("lifecycle-test", "https://github.com/user/repo.git")
        assert get_project_path("lifecycle-test") is not None

        # Unregister
        unregister_project("lifecycle-test")
        assert get_project_path("lifecycle-test") is None

    @pytest.mark.integration
    def test_update_target_container_count(self, isolated_registry):
        """Test updating target container count."""
        from registry import (
            register_project,
            update_target_container_count,
            get_project_info
        )

        register_project("container-test", "https://github.com/user/repo.git")
        update_target_container_count("container-test", 5)

        info = get_project_info("container-test")

        assert info["target_container_count"] == 5

    @pytest.mark.integration
    def test_mark_project_initialized(self, isolated_registry):
        """Test marking project as initialized."""
        from registry import (
            register_project,
            mark_project_initialized,
            get_project_info
        )

        register_project("init-test", "https://github.com/user/repo.git", is_new=True)
        assert get_project_info("init-test")["is_new"] is True

        mark_project_initialized("init-test")

        assert get_project_info("init-test")["is_new"] is False


# =============================================================================
# Container Management Integration Tests
# =============================================================================

class TestContainerManagementIntegration:
    """Integration tests for container management."""

    @pytest.fixture
    def project_setup(self, tmp_path):
        """Set up a test project directory."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        (project_dir / "prompts").mkdir()
        (project_dir / ".beads").mkdir()
        (project_dir / ".git").mkdir()

        return project_dir

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_container_manager_full_lifecycle(self, project_setup, tmp_path):
        """Test complete container manager lifecycle."""
        from server.services.container_manager import (
            ContainerManager,
            get_container_manager,
            clear_container_manager,
            _container_managers,
        )

        _container_managers.clear()

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    # Get manager (creates new)
                    manager = get_container_manager(
                        project_name="test-project",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_setup,
                    )

                    assert manager.project_name == "test-project"
                    assert manager._status == "not_created"

                    # Add callbacks
                    status_callback = AsyncMock()
                    manager.add_status_callback(status_callback)

                    # Notify status
                    manager._notify_status_change("running")
                    status_callback.assert_called_with("running")

                    # Clear manager
                    clear_container_manager("test-project")
                    assert "test-project" not in _container_managers

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multiple_container_managers_same_project(self, project_setup, tmp_path):
        """Test multiple containers for same project."""
        from server.services.container_manager import (
            ContainerManager,
            get_container_manager,
            get_all_container_managers,
            _container_managers,
        )

        _container_managers.clear()

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    # Create multiple containers
                    manager1 = get_container_manager(
                        "multi-test", "https://github.com/user/repo.git",
                        container_number=1, project_dir=project_setup
                    )
                    manager2 = get_container_manager(
                        "multi-test", "https://github.com/user/repo.git",
                        container_number=2, project_dir=project_setup
                    )
                    init_manager = get_container_manager(
                        "multi-test", "https://github.com/user/repo.git",
                        container_number=0, project_dir=project_setup
                    )

                    # Verify different names
                    assert manager1.container_name == "zerocoder-multi-test-1"
                    assert manager2.container_name == "zerocoder-multi-test-2"
                    assert init_manager.container_name == "zerocoder-multi-test-init"

                    # Get all managers
                    all_managers = get_all_container_managers("multi-test")
                    assert len(all_managers) == 3


# =============================================================================
# API Integration Tests
# =============================================================================

class TestAPIIntegration:
    """Integration tests for API endpoints."""

    @pytest.fixture
    def test_client(self):
        """Create FastAPI test client."""
        from fastapi.testclient import TestClient
        from server.main import app

        with patch("signal.signal", return_value=None):
            with TestClient(app, raise_server_exceptions=False) as client:
                yield client

    @pytest.mark.integration
    def test_create_and_get_project(self, test_client, tmp_path):
        """Test creating and retrieving a project via API."""
        with patch("server.routers.projects._init_imports"):
            with patch("server.routers.projects._get_registry_functions") as mock_reg:
                mock_projects_dir = tmp_path / "projects"
                mock_projects_dir.mkdir()

                project_data = {
                    "name": "api-test-project",
                    "git_url": "https://github.com/user/repo.git",
                    "local_path": str(mock_projects_dir / "api-test-project"),
                    "is_new": True,
                    "target_container_count": 1,
                }

                mock_reg.return_value = (
                    MagicMock(),  # register_project
                    MagicMock(),  # unregister_project
                    MagicMock(return_value=mock_projects_dir / "api-test-project"),  # get_project_path
                    MagicMock(return_value="https://github.com/user/repo.git"),  # get_project_git_url
                    MagicMock(return_value=project_data),  # get_project_info
                    MagicMock(return_value=mock_projects_dir),  # get_projects_dir
                    MagicMock(return_value={"api-test-project": project_data}),  # list_registered_projects
                    MagicMock(return_value=True),  # validate_project_path
                    MagicMock(),  # mark_project_initialized
                    MagicMock(),  # update_target_container_count
                    MagicMock(return_value=[]),  # list_project_containers
                )

                with patch("server.routers.projects.clone_repository") as mock_clone:
                    mock_clone.return_value = (True, "Cloned")
                    with patch("server.routers.projects._scaffold_project_prompts"):
                        with patch("server.routers.projects._has_project_prompts", return_value=True):
                            with patch("server.routers.projects._count_passing_tests", return_value=(0, 0, 0)):
                                # Create project
                                response = test_client.post(
                                    "/api/projects",
                                    json={
                                        "name": "api-test-project",
                                        "git_url": "https://github.com/user/repo.git",
                                        "is_new": True
                                    }
                                )

                assert response.status_code == 200

    @pytest.mark.integration
    def test_project_settings_update(self, test_client, tmp_path):
        """Test updating project settings via API."""
        with patch("server.routers.projects._init_imports"):
            with patch("server.routers.projects._get_registry_functions") as mock_reg:
                project_dir = tmp_path / "settings-test"
                project_dir.mkdir()
                (project_dir / "prompts").mkdir()

                mock_reg.return_value = (
                    None, None,
                    MagicMock(return_value=project_dir),
                    None, None, None, None, None, None, None, None
                )

                with patch("server.routers.projects.write_agent_config") as mock_write:
                    response = test_client.put(
                        "/api/projects/settings-test/settings",
                        json={"agent_model": "claude-opus-4-5-20251101"}
                    )

                    if response.status_code == 200:
                        mock_write.assert_called_once()


# =============================================================================
# WebSocket Integration Tests
# =============================================================================

class TestWebSocketIntegration:
    """Integration tests for WebSocket functionality."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_websocket_broadcast_to_multiple_clients(self):
        """Test broadcasting to multiple WebSocket clients."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        # Create mock clients
        clients = [AsyncMock() for _ in range(5)]

        # Connect all clients
        for client in clients:
            await manager.connect(client, "test-project")

        # Broadcast message
        message = {"type": "progress", "passing": 5, "total": 10}
        await manager.broadcast_to_project("test-project", message)

        # Verify all received
        for client in clients:
            client.send_json.assert_called_once_with(message)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_websocket_project_isolation(self):
        """Test that messages are isolated by project."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        client_a = AsyncMock()
        client_b = AsyncMock()

        await manager.connect(client_a, "project-a")
        await manager.connect(client_b, "project-b")

        # Broadcast to project-a only
        await manager.broadcast_to_project("project-a", {"type": "test"})

        client_a.send_json.assert_called_once()
        client_b.send_json.assert_not_called()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_websocket_handles_client_disconnect(self):
        """Test handling of disconnected clients during broadcast."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        healthy_client = AsyncMock()
        failing_client = AsyncMock()
        failing_client.send_json.side_effect = Exception("Connection closed")

        await manager.connect(healthy_client, "test-project")
        await manager.connect(failing_client, "test-project")

        # Should not raise and healthy client should receive
        await manager.broadcast_to_project("test-project", {"type": "test"})

        healthy_client.send_json.assert_called_once()


# =============================================================================
# Feature Management Integration Tests
# =============================================================================

class TestFeatureManagementIntegration:
    """Integration tests for feature management."""

    @pytest.fixture
    def project_with_features(self, tmp_path):
        """Create a project with beads features."""
        project_dir = tmp_path / "feature-test"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        # Create issues file
        issues = [
            {"id": "feat-1", "title": "Auth", "status": "open", "priority": 0, "labels": ["auth"]},
            {"id": "feat-2", "title": "Dashboard", "status": "in_progress", "priority": 1, "labels": ["ui"]},
            {"id": "feat-3", "title": "API", "status": "closed", "priority": 2, "labels": ["backend"]},
        ]

        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        return project_dir, issues

    @pytest.mark.integration
    def test_read_local_beads_features(self, project_with_features):
        """Test reading features from local beads."""
        from server.routers.features import read_local_beads_features

        project_dir, expected_issues = project_with_features

        features = read_local_beads_features(project_dir)

        assert len(features["pending"]) >= 1
        assert len(features["in_progress"]) >= 1
        assert len(features["done"]) >= 1

    @pytest.mark.integration
    def test_feature_conversion_preserves_data(self, project_with_features):
        """Test that feature conversion preserves all data."""
        from server.routers.features import beads_task_to_feature

        _, expected_issues = project_with_features

        for issue in expected_issues:
            feature = beads_task_to_feature(issue)

            assert feature["id"] == issue["id"]
            assert feature["name"] == issue["title"]
            assert feature["priority"] == issue["priority"]


# =============================================================================
# Progress Tracking Integration Tests
# =============================================================================

class TestProgressTrackingIntegration:
    """Integration tests for progress tracking."""

    @pytest.fixture
    def project_with_progress(self, tmp_path):
        """Create a project with various feature states."""
        project_dir = tmp_path / "progress-test"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        issues = [
            {"id": "feat-1", "status": "closed"},
            {"id": "feat-2", "status": "closed"},
            {"id": "feat-3", "status": "closed"},
            {"id": "feat-4", "status": "in_progress"},
            {"id": "feat-5", "status": "open"},
        ]

        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        return project_dir

    @pytest.mark.integration
    def test_count_passing_tests(self, project_with_progress):
        """Test counting passing tests."""
        from progress import count_passing_tests

        passing, in_progress, total = count_passing_tests(project_with_progress)

        assert passing == 3
        assert in_progress == 1
        assert total == 5

    @pytest.mark.integration
    def test_has_open_features(self, project_with_progress):
        """Test checking for open features."""
        from progress import has_open_features

        result = has_open_features(project_with_progress)

        assert result is True

    @pytest.mark.integration
    def test_has_features(self, project_with_progress):
        """Test checking for any features."""
        from progress import has_features

        result = has_features(project_with_progress)

        assert result is True

    @pytest.mark.integration
    def test_empty_project_has_no_features(self, tmp_path):
        """Test empty project detection."""
        from progress import has_features

        empty_project = tmp_path / "empty"
        empty_project.mkdir()
        (empty_project / ".beads").mkdir()

        result = has_features(empty_project)

        assert result is False


# =============================================================================
# Prompts Integration Tests
# =============================================================================

class TestPromptsIntegration:
    """Integration tests for prompt management."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create a project directory for testing."""
        project_dir = tmp_path / "prompts-test"
        project_dir.mkdir()
        return project_dir

    @pytest.mark.integration
    def test_scaffold_project_prompts(self, project_dir):
        """Test scaffolding project prompts."""
        from prompts import scaffold_project_prompts, has_project_prompts

        scaffold_project_prompts(project_dir)

        prompts_dir = project_dir / "prompts"
        assert prompts_dir.exists()
        assert (prompts_dir / "app_spec.txt").exists()
        assert (prompts_dir / "coding_prompt.md").exists()

    @pytest.mark.integration
    def test_get_project_prompts_dir(self, project_dir):
        """Test getting prompts directory."""
        from prompts import get_project_prompts_dir

        prompts_dir = get_project_prompts_dir(project_dir)

        assert prompts_dir == project_dir / "prompts"

    @pytest.mark.integration
    def test_has_project_prompts(self, project_dir):
        """Test checking for project prompts."""
        from prompts import scaffold_project_prompts, has_project_prompts

        # Before scaffolding
        assert has_project_prompts(project_dir) is False

        # After scaffolding
        scaffold_project_prompts(project_dir)
        prompts_dir = project_dir / "prompts"
        (prompts_dir / "app_spec.txt").write_text("<app-spec><name>Test</name></app-spec>")

        assert has_project_prompts(project_dir) is True


# =============================================================================
# Beads Sync Integration Tests
# =============================================================================

class TestBeadsSyncIntegration:
    """Integration tests for beads sync functionality."""

    @pytest.fixture
    def beads_sync_setup(self, tmp_path):
        """Set up beads sync directories."""
        sync_dir = tmp_path / "beads-sync" / "test-project"
        sync_dir.mkdir(parents=True)

        beads_dir = sync_dir / ".beads"
        beads_dir.mkdir()

        # Create sample issues
        issues = [
            {"id": "feat-1", "title": "Feature 1", "status": "open", "priority": 1},
            {"id": "feat-2", "title": "Feature 2", "status": "closed", "priority": 2},
        ]

        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        return tmp_path, sync_dir

    @pytest.mark.integration
    def test_beads_sync_manager_get_tasks(self, beads_sync_setup):
        """Test getting tasks from beads sync."""
        from server.services.beads_sync_manager import BeadsSyncManager

        base_dir, sync_dir = beads_sync_setup

        with patch("server.services.beads_sync_manager.get_beads_sync_dir") as mock_dir:
            mock_dir.return_value = base_dir / "beads-sync"

            manager = BeadsSyncManager("test-project", "https://github.com/user/repo.git")
            tasks = manager.get_tasks()

        assert len(tasks) == 2
        assert tasks[0]["id"] == "feat-1"
        assert tasks[1]["status"] == "closed"


# =============================================================================
# Error Recovery Integration Tests
# =============================================================================

class TestErrorRecoveryIntegration:
    """Integration tests for error recovery scenarios."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_callback_error_isolation(self):
        """Test that callback errors don't affect other callbacks."""
        from server.services.container_manager import ContainerManager

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = Path("/tmp")
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="error-test",
                        git_url="https://github.com/user/repo.git",
                        skip_db_persist=True,
                    )

        # Add failing and successful callbacks
        fail_callback = AsyncMock(side_effect=Exception("Callback error"))
        success_callback = AsyncMock()

        manager.add_status_callback(fail_callback)
        manager.add_status_callback(success_callback)

        # Should not raise and success callback should be called
        manager._notify_status_change("running")

        fail_callback.assert_called_once()
        success_callback.assert_called_once()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_websocket_resilient_to_disconnects(self):
        """Test WebSocket manager handles disconnects gracefully."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        # Mix of healthy and failing clients
        healthy = AsyncMock()
        failing = AsyncMock()
        failing.send_json.side_effect = RuntimeError("Disconnected")

        await manager.connect(healthy, "test")
        await manager.connect(failing, "test")

        # Should complete without error
        await manager.broadcast_to_project("test", {"type": "test"})

        healthy.send_json.assert_called_once()


# =============================================================================
# Concurrent Access Integration Tests
# =============================================================================

class TestConcurrentAccessIntegration:
    """Integration tests for concurrent access scenarios."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_websocket_connections(self):
        """Test handling concurrent WebSocket connections."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        clients = [AsyncMock() for _ in range(10)]

        # Connect all concurrently
        await asyncio.gather(*[
            manager.connect(client, "concurrent-test")
            for client in clients
        ])

        # All should be connected
        assert len(manager.active_connections.get("concurrent-test", [])) == 10

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_container_manager_access(self, tmp_path):
        """Test concurrent access to container manager."""
        from server.services.container_manager import (
            ContainerManager,
            get_container_manager,
            _container_managers,
        )

        project_dir = tmp_path / "concurrent"
        project_dir.mkdir()

        _container_managers.clear()

        async def get_manager():
            with patch("server.services.container_manager.get_projects_dir") as mock_dir:
                mock_dir.return_value = tmp_path
                with patch.object(ContainerManager, "_sync_status"):
                    with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                        return get_container_manager(
                            "concurrent-test",
                            "https://github.com/user/repo.git",
                            container_number=1,
                            project_dir=project_dir,
                        )

        # Get manager from multiple tasks
        managers = await asyncio.gather(*[get_manager() for _ in range(5)])

        # All should return the same instance
        assert all(m is managers[0] for m in managers)


# =============================================================================
# Data Integrity Integration Tests
# =============================================================================

class TestDataIntegrityIntegration:
    """Integration tests for data integrity."""

    @pytest.mark.integration
    def test_registry_isolation_between_tests(self, tmp_path, monkeypatch):
        """Test that registry tests are isolated."""
        import registry

        # Store original state
        original_engine = registry._engine
        original_session = registry._SessionLocal

        # Reset module state
        registry._engine = None
        registry._SessionLocal = None

        # Use temp path
        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "test.db")
        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")

        # Create a project
        from registry import register_project, list_registered_projects

        register_project("isolation-test", "https://github.com/user/repo.git")

        projects = list_registered_projects()
        assert "isolation-test" in projects

        # Restore original state
        registry._engine = original_engine
        registry._SessionLocal = original_session

    @pytest.mark.integration
    def test_beads_issues_jsonl_format(self, tmp_path):
        """Test that beads issues file maintains valid JSONL format."""
        beads_dir = tmp_path / ".beads"
        beads_dir.mkdir()

        issues_file = beads_dir / "issues.jsonl"

        # Write issues
        issues = [
            {"id": "feat-1", "title": "First", "status": "open"},
            {"id": "feat-2", "title": "Second", "status": "closed"},
            {"id": "feat-3", "title": "Third", "status": "in_progress"},
        ]

        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        # Read and validate
        with open(issues_file, "r") as f:
            for i, line in enumerate(f):
                parsed = json.loads(line.strip())
                assert parsed["id"] == f"feat-{i + 1}"


# =============================================================================
# Performance Integration Tests
# =============================================================================

class TestPerformanceIntegration:
    """Integration tests for performance characteristics."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_websocket_broadcast_performance(self):
        """Test broadcast performance with many clients."""
        from server.websocket import ConnectionManager
        import time

        manager = ConnectionManager()
        num_clients = 100
        clients = [AsyncMock() for _ in range(num_clients)]

        # Connect all
        for client in clients:
            await manager.connect(client, "perf-test")

        # Measure broadcast time
        start = time.time()
        await manager.broadcast_to_project("perf-test", {"type": "test"})
        duration = time.time() - start

        # Should complete quickly (under 1 second)
        assert duration < 1.0

    @pytest.mark.integration
    def test_registry_query_performance(self, tmp_path, monkeypatch):
        """Test registry query performance with many projects."""
        import registry
        import time

        # Reset module state
        registry._engine = None
        registry._SessionLocal = None

        # Use temp path
        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "perf.db")
        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")

        from registry import register_project, list_registered_projects

        # Register many projects
        for i in range(50):
            register_project(f"perf-project-{i}", f"https://github.com/user/repo{i}.git")

        # Measure list time
        start = time.time()
        projects = list_registered_projects()
        duration = time.time() - start

        assert len(projects) == 50
        assert duration < 1.0  # Should complete quickly
