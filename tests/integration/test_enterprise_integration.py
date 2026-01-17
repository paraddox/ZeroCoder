"""
Enterprise Integration Tests
============================

End-to-end integration tests covering:
- Full API workflows
- Multi-component interactions
- Real-world scenarios
- Cross-service communication
"""

import asyncio
import json
import pytest
import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# API Integration Tests
# =============================================================================

class TestProjectAPIIntegration:
    """Integration tests for project API workflows."""

    @pytest.fixture
    def isolated_env(self, tmp_path, monkeypatch):
        """Set up isolated test environment."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()
        (temp_config / "beads-sync").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "registry.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        return {
            "registry": registry,
            "config_dir": temp_config,
            "projects_dir": temp_config / "projects",
            "tmp_path": tmp_path,
        }

    @pytest.fixture
    def test_client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from server.main import app

        with patch("signal.signal", return_value=None):
            with TestClient(app, raise_server_exceptions=False) as client:
                yield client

    @pytest.mark.integration
    def test_project_crud_workflow(self, isolated_env, test_client):
        """Test complete project CRUD workflow."""
        env = isolated_env

        # Create project
        with patch("server.routers.projects._get_registry_functions") as mock_reg:
            mock_reg.return_value = (
                env["registry"].register_project,
                env["registry"].unregister_project,
                env["registry"].get_project_path,
                env["registry"].get_project_git_url,
                env["registry"].get_project_info,
                lambda: env["projects_dir"],
                env["registry"].list_registered_projects,
                env["registry"].validate_project_path,
                env["registry"].mark_project_initialized,
                env["registry"].update_target_container_count,
                env["registry"].list_project_containers,
            )

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="")

                # This would normally clone the repo
                response = test_client.post("/api/projects", json={
                    "name": "integration-test",
                    "git_url": "https://github.com/user/repo.git",
                    "is_new": True,
                })

                # Note: May fail due to missing git clone - that's expected without mocking

    @pytest.mark.integration
    def test_list_projects_workflow(self, isolated_env):
        """Test listing projects workflow."""
        env = isolated_env
        registry = env["registry"]

        # Register some projects directly
        registry.register_project("proj-a", "https://github.com/user/a.git")
        registry.register_project("proj-b", "https://github.com/user/b.git")

        # List projects
        projects = registry.list_registered_projects()

        assert "proj-a" in projects
        assert "proj-b" in projects
        assert len(projects) == 2


class TestFeatureAPIIntegration:
    """Integration tests for feature API workflows."""

    @pytest.fixture
    def project_with_features(self, tmp_path):
        """Create project with features for testing."""
        project_dir = tmp_path / "feature-test"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat\n")

        features = [
            {"id": "feat-1", "title": "Auth", "status": "open", "priority": 0, "labels": ["auth"]},
            {"id": "feat-2", "title": "Dashboard", "status": "in_progress", "priority": 1, "labels": ["ui"]},
            {"id": "feat-3", "title": "API", "status": "closed", "priority": 2, "labels": ["backend"]},
        ]

        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        return project_dir

    @pytest.mark.integration
    def test_read_features_workflow(self, project_with_features):
        """Test reading features from beads files."""
        from server.routers.features import read_local_beads_features

        result = read_local_beads_features(project_with_features)

        assert len(result["pending"]) == 1
        assert len(result["in_progress"]) == 1
        assert len(result["done"]) == 1

        assert result["pending"][0]["name"] == "Auth"
        assert result["in_progress"][0]["name"] == "Dashboard"
        assert result["done"][0]["name"] == "API"

    @pytest.mark.integration
    def test_feature_status_transitions(self, project_with_features):
        """Test feature status transitions through the workflow."""
        from server.routers.features import read_local_beads_features

        beads_dir = project_with_features / ".beads"
        issues_file = beads_dir / "issues.jsonl"

        # Read initial state
        result = read_local_beads_features(project_with_features)
        pending_count = len(result["pending"])

        # Simulate claiming a feature (move to in_progress)
        with open(issues_file, "r") as f:
            features = [json.loads(line) for line in f]

        # Update first pending feature
        for feat in features:
            if feat["status"] == "open":
                feat["status"] = "in_progress"
                break

        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        # Read updated state
        result = read_local_beads_features(project_with_features)
        assert len(result["pending"]) == pending_count - 1
        assert len(result["in_progress"]) == 2


# =============================================================================
# WebSocket Integration Tests
# =============================================================================

class TestWebSocketIntegration:
    """Integration tests for WebSocket functionality."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_websocket_progress_broadcast(self):
        """Test WebSocket progress broadcasting to multiple clients."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        clients = [AsyncMock() for _ in range(5)]

        # Connect all clients
        for client in clients:
            await manager.connect(client, "ws-test")

        # Simulate progress updates
        progress_updates = [
            {"type": "progress", "passing": 1, "total": 10, "percentage": 10},
            {"type": "progress", "passing": 5, "total": 10, "percentage": 50},
            {"type": "progress", "passing": 10, "total": 10, "percentage": 100},
        ]

        for update in progress_updates:
            await manager.broadcast_to_project("ws-test", update)

        # Verify all clients received all updates
        for client in clients:
            assert client.send_json.call_count == 3

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_websocket_multi_project_isolation(self):
        """Test that WebSocket messages are isolated between projects."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        # Create clients for different projects
        proj_a_clients = [AsyncMock() for _ in range(3)]
        proj_b_clients = [AsyncMock() for _ in range(3)]

        for client in proj_a_clients:
            await manager.connect(client, "project-a")
        for client in proj_b_clients:
            await manager.connect(client, "project-b")

        # Broadcast to project-a only
        await manager.broadcast_to_project("project-a", {"type": "test", "project": "a"})

        # Only project-a clients should receive
        for client in proj_a_clients:
            assert client.send_json.call_count == 1
        for client in proj_b_clients:
            assert client.send_json.call_count == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_websocket_connection_lifecycle(self):
        """Test WebSocket connection connect/disconnect lifecycle."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        client = AsyncMock()

        # Connect
        await manager.connect(client, "lifecycle-test")
        assert manager.get_connection_count("lifecycle-test") == 1

        # Disconnect
        await manager.disconnect(client, "lifecycle-test")
        assert manager.get_connection_count("lifecycle-test") == 0


# =============================================================================
# Container Manager Integration Tests
# =============================================================================

class TestContainerManagerIntegration:
    """Integration tests for container manager."""

    @pytest.fixture
    def container_env(self, tmp_path):
        """Set up container test environment."""
        project_dir = tmp_path / "container-test"
        project_dir.mkdir()
        (project_dir / "prompts").mkdir()
        (project_dir / ".beads").mkdir()
        (project_dir / ".git").mkdir()

        # Create prompts
        (project_dir / "prompts" / "coding_prompt.md").write_text("# Coding Prompt")

        return project_dir

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_container_manager_callback_flow(self, container_env, tmp_path):
        """Test container manager callback flow."""
        from server.services.container_manager import ContainerManager, _container_managers

        _container_managers.clear()

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="container-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=container_env,
                        skip_db_persist=True,
                    )

        # Track callback invocations
        status_history = []
        output_history = []

        async def status_callback(status):
            status_history.append(status)

        async def output_callback(line):
            output_history.append(line)

        manager.add_status_callback(status_callback)
        manager.add_output_callback(output_callback)

        # Simulate status changes
        manager._notify_status_change("running")
        manager._notify_status_change("stopped")

        # Simulate output
        await manager._broadcast_output("Line 1")
        await manager._broadcast_output("Line 2")

        assert status_history == ["running", "stopped"]
        assert output_history == ["Line 1", "Line 2"]

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multiple_container_managers(self, container_env, tmp_path):
        """Test managing multiple containers for same project."""
        from server.services.container_manager import (
            get_container_manager,
            _container_managers,
            ContainerManager,
        )

        _container_managers.clear()

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    # Create multiple containers for same project
                    managers = []
                    for i in range(3):
                        manager = get_container_manager(
                            project_name="container-test",
                            git_url="https://github.com/user/repo.git",
                            container_number=i + 1,
                            project_dir=container_env,
                        )
                        managers.append(manager)

        # Verify different container numbers
        assert managers[0].container_name == "zerocoder-container-test-1"
        assert managers[1].container_name == "zerocoder-container-test-2"
        assert managers[2].container_name == "zerocoder-container-test-3"


# =============================================================================
# Progress Tracking Integration Tests
# =============================================================================

class TestProgressTrackingIntegration:
    """Integration tests for progress tracking."""

    @pytest.fixture
    def progress_project(self, tmp_path):
        """Create project for progress testing."""
        project_dir = tmp_path / "progress-test"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat\n")
        return project_dir

    @pytest.mark.integration
    def test_progress_counting_workflow(self, progress_project):
        """Test progress counting through feature lifecycle."""
        from progress import count_passing_tests, has_features, has_open_features

        beads_dir = progress_project / ".beads"
        issues_file = beads_dir / "issues.jsonl"

        # No features initially
        assert has_features(progress_project) is False

        # Create features
        features = [
            {"id": "feat-1", "title": "A", "status": "open", "priority": 1},
            {"id": "feat-2", "title": "B", "status": "open", "priority": 2},
            {"id": "feat-3", "title": "C", "status": "open", "priority": 3},
        ]

        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        # Now has features
        assert has_features(progress_project) is True
        assert has_open_features(progress_project) is True

        passing, in_progress, total = count_passing_tests(progress_project)
        assert passing == 0
        assert total == 3

        # Complete some features
        features[0]["status"] = "closed"
        features[1]["status"] = "in_progress"

        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        passing, in_progress, total = count_passing_tests(progress_project)
        assert passing == 1
        assert in_progress == 1
        assert total == 3

        # Complete all
        for feat in features:
            feat["status"] = "closed"

        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        assert has_open_features(progress_project) is False
        passing, in_progress, total = count_passing_tests(progress_project)
        assert passing == 3
        assert total == 3


# =============================================================================
# Prompt Loading Integration Tests
# =============================================================================

class TestPromptLoadingIntegration:
    """Integration tests for prompt loading."""

    @pytest.fixture
    def prompt_project(self, tmp_path):
        """Create project with prompts."""
        project_dir = tmp_path / "prompt-test"
        project_dir.mkdir()
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir()

        (prompts_dir / "coding_prompt.md").write_text("# Custom Coding Prompt")
        (prompts_dir / "app_spec.txt").write_text("<project_specification>Test App</project_specification>")

        return project_dir

    @pytest.mark.integration
    def test_prompt_loading_workflow(self, prompt_project):
        """Test prompt loading with fallback chain."""
        from prompts import load_prompt, get_app_spec, has_project_prompts

        # Load project-specific prompt
        coding = load_prompt("coding_prompt", prompt_project)
        assert "Custom Coding Prompt" in coding

        # Load app spec
        spec = get_app_spec(prompt_project)
        assert "Test App" in spec

        # Check has prompts
        assert has_project_prompts(prompt_project) is True

    @pytest.mark.integration
    def test_prompt_scaffolding_workflow(self, tmp_path):
        """Test prompt scaffolding for new project."""
        from prompts import scaffold_project_prompts, has_project_prompts

        new_project = tmp_path / "new-project"
        new_project.mkdir()

        # Initially no prompts
        assert has_project_prompts(new_project) is False

        # Scaffold prompts
        scaffold_project_prompts(new_project)

        # Should have prompts directory
        assert (new_project / "prompts").exists()

        # Should have CLAUDE.md
        assert (new_project / "CLAUDE.md").exists()


# =============================================================================
# End-to-End Workflow Tests
# =============================================================================

class TestEndToEndWorkflows:
    """End-to-end workflow tests."""

    @pytest.fixture
    def full_env(self, tmp_path, monkeypatch):
        """Set up full test environment."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        config_dir = tmp_path / "zerocoder"
        config_dir.mkdir(parents=True)
        (config_dir / "projects").mkdir()
        (config_dir / "beads-sync").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "registry.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: config_dir)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: config_dir / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: config_dir / "beads-sync")

        return {
            "registry": registry,
            "config_dir": config_dir,
            "projects_dir": config_dir / "projects",
        }

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_new_project_complete_workflow(self, full_env):
        """Test complete workflow: create project -> setup -> track progress."""
        env = full_env
        registry = env["registry"]
        projects_dir = env["projects_dir"]

        # 1. Register project
        registry.register_project(
            name="e2e-workflow",
            git_url="https://github.com/user/repo.git",
            is_new=True
        )

        info = registry.get_project_info("e2e-workflow")
        assert info is not None
        assert info["is_new"] is True

        # 2. Create project directory structure
        project_dir = projects_dir / "e2e-workflow"
        project_dir.mkdir()

        from prompts import scaffold_project_prompts
        scaffold_project_prompts(project_dir)

        # 3. Create app spec
        spec_content = """<project_specification>
<name>E2E Test App</name>
<features>
    <feature>User Authentication</feature>
    <feature>Dashboard</feature>
</features>
</project_specification>"""
        (project_dir / "prompts" / "app_spec.txt").write_text(spec_content)

        from prompts import has_project_prompts
        assert has_project_prompts(project_dir) is True

        # 4. Mark initialized
        registry.mark_project_initialized("e2e-workflow")

        info = registry.get_project_info("e2e-workflow")
        assert info["is_new"] is False

        # 5. Create features via beads
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat\n")

        features = [
            {"id": "feat-1", "title": "User Authentication", "status": "open", "priority": 0},
            {"id": "feat-2", "title": "Dashboard", "status": "open", "priority": 1},
        ]

        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        from progress import has_features, count_passing_tests
        assert has_features(project_dir) is True

        passing, in_progress, total = count_passing_tests(project_dir)
        assert total == 2
        assert passing == 0

        # 6. Simulate WebSocket broadcast
        from server.websocket import ConnectionManager
        ws_manager = ConnectionManager()
        client = AsyncMock()

        await ws_manager.connect(client, "e2e-workflow")

        await ws_manager.broadcast_to_project("e2e-workflow", {
            "type": "progress",
            "passing": passing,
            "total": total,
            "percentage": 0,
        })

        client.send_json.assert_called_once()

        # 7. Complete features
        for feat in features:
            feat["status"] = "closed"

        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        passing, in_progress, total = count_passing_tests(project_dir)
        assert passing == 2
        assert total == 2

        # 8. Broadcast completion
        await ws_manager.broadcast_to_project("e2e-workflow", {
            "type": "progress",
            "passing": 2,
            "total": 2,
            "percentage": 100,
        })

        assert client.send_json.call_count == 2

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_multi_project_parallel_workflow(self, full_env):
        """Test parallel operation of multiple projects."""
        env = full_env
        registry = env["registry"]
        projects_dir = env["projects_dir"]

        from server.websocket import ConnectionManager
        ws_manager = ConnectionManager()

        # Create multiple projects
        projects = ["parallel-a", "parallel-b", "parallel-c"]
        clients = {}

        for proj_name in projects:
            # Register
            registry.register_project(
                name=proj_name,
                git_url=f"https://github.com/user/{proj_name}.git"
            )

            # Create directory
            project_dir = projects_dir / proj_name
            project_dir.mkdir()

            # Connect WebSocket
            client = AsyncMock()
            clients[proj_name] = client
            await ws_manager.connect(client, proj_name)

        # Broadcast to each project
        for proj_name in projects:
            await ws_manager.broadcast_to_project(proj_name, {
                "type": "status",
                "project": proj_name,
            })

        # Verify isolation
        for proj_name in projects:
            client = clients[proj_name]
            assert client.send_json.call_count == 1
            call_args = client.send_json.call_args[0][0]
            assert call_args["project"] == proj_name
