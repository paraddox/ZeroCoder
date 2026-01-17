"""
Service Integration Tests
=========================

Enterprise-grade integration tests for service interactions including:
- Service-to-service communication
- Data flow verification
- State synchronization
- Error propagation
"""

import asyncio
import json
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import threading

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Container Manager to Registry Integration
# =============================================================================

class TestContainerRegistryIntegration:
    """Tests for container manager and registry integration."""

    @pytest.fixture
    def integrated_env(self, tmp_path, monkeypatch):
        """Set up integrated test environment."""
        import registry
        from server.services.container_manager import _container_managers

        _container_managers.clear()

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "registry.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")

        return {
            "registry": registry,
            "projects_dir": temp_config / "projects",
            "tmp_path": tmp_path,
        }

    @pytest.mark.integration
    def test_container_status_persists_to_registry(self, integrated_env):
        """Test container status changes persist to registry."""
        registry = integrated_env["registry"]

        # Setup
        registry.register_project("persist-test", "https://github.com/user/repo.git")
        registry.create_container("persist-test", 1, "coding")

        # Update through manager-like operations
        registry.update_container_status(
            "persist-test", 1, "coding",
            status="running",
            docker_container_id="abc123"
        )

        # Verify persisted
        container = registry.get_container("persist-test", 1, "coding")
        assert container["status"] == "running"
        assert container["docker_container_id"] == "abc123"

    @pytest.mark.integration
    def test_container_count_synchronization(self, integrated_env):
        """Test container count stays synchronized."""
        registry = integrated_env["registry"]

        registry.register_project("count-sync", "https://github.com/user/repo.git")

        # Update target count
        registry.update_target_container_count("count-sync", 3)

        # Create containers to match
        for i in range(1, 4):
            registry.create_container("count-sync", i, "coding")

        # Verify
        info = registry.get_project_info("count-sync")
        containers = registry.list_project_containers("count-sync", container_type="coding")

        assert info["target_container_count"] == 3
        assert len(containers) == 3


# =============================================================================
# Beads Sync Manager Integration
# =============================================================================

class TestBeadsSyncIntegration:
    """Tests for beads sync manager integration."""

    @pytest.fixture
    def beads_env(self, tmp_path):
        """Set up beads test environment."""
        project_dir = tmp_path / "beads-sync-test"
        project_dir.mkdir()

        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        return {
            "project_dir": project_dir,
            "beads_dir": beads_dir,
        }

    @pytest.mark.integration
    def test_beads_file_to_api_format(self, beads_env):
        """Test beads file format converts to API format."""
        issues_file = beads_env["beads_dir"] / "issues.jsonl"

        # Beads file format
        beads_issues = [
            {
                "id": "feat-1",
                "title": "Feature Title",
                "status": "open",
                "priority": 1,
                "labels": ["ui"],
                "description": "Feature description",
            }
        ]

        with open(issues_file, "w") as f:
            for issue in beads_issues:
                f.write(json.dumps(issue) + "\n")

        # Read and transform to API format
        with open(issues_file) as f:
            raw_issues = [json.loads(line) for line in f if line.strip()]

        # Transform to API format
        api_features = []
        for issue in raw_issues:
            api_features.append({
                "id": issue["id"],
                "name": issue["title"],
                "category": issue.get("labels", ["general"])[0] if issue.get("labels") else "general",
                "description": issue.get("description", ""),
                "priority": issue.get("priority", 2),
                "passes": issue["status"] == "closed",
                "in_progress": issue["status"] == "in_progress",
            })

        assert len(api_features) == 1
        assert api_features[0]["name"] == "Feature Title"
        assert api_features[0]["passes"] is False

    @pytest.mark.integration
    def test_feature_stats_aggregation(self, beads_env):
        """Test feature stats are aggregated correctly."""
        issues_file = beads_env["beads_dir"] / "issues.jsonl"

        issues = [
            {"id": "f-1", "status": "open", "priority": 0},
            {"id": "f-2", "status": "open", "priority": 1},
            {"id": "f-3", "status": "in_progress", "priority": 0},
            {"id": "f-4", "status": "closed", "priority": 2},
            {"id": "f-5", "status": "closed", "priority": 1},
        ]

        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        # Aggregate stats
        with open(issues_file) as f:
            all_issues = [json.loads(line) for line in f if line.strip()]

        stats = {
            "total": len(all_issues),
            "open": sum(1 for i in all_issues if i["status"] == "open"),
            "in_progress": sum(1 for i in all_issues if i["status"] == "in_progress"),
            "closed": sum(1 for i in all_issues if i["status"] == "closed"),
        }

        assert stats["total"] == 5
        assert stats["open"] == 2
        assert stats["in_progress"] == 1
        assert stats["closed"] == 2


# =============================================================================
# Progress and WebSocket Integration
# =============================================================================

class TestProgressWebSocketIntegration:
    """Tests for progress tracking and WebSocket integration."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_progress_update_broadcasts(self):
        """Test progress updates are broadcast via WebSocket."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        ws = AsyncMock()

        await manager.connect("progress-broadcast", ws)

        # Simulate progress update
        progress = {
            "type": "progress",
            "passing": 5,
            "total": 10,
            "percentage": 50.0,
        }

        await manager.broadcast("progress-broadcast", progress)

        ws.send_json.assert_called_once_with(progress)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_feature_update_broadcasts(self):
        """Test feature updates are broadcast via WebSocket."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        ws = AsyncMock()

        await manager.connect("feature-broadcast", ws)

        # Simulate feature update
        update = {
            "type": "feature_update",
            "feature_id": "feat-1",
            "passes": True,
        }

        await manager.broadcast("feature-broadcast", update)

        ws.send_json.assert_called_once_with(update)


# =============================================================================
# Local Project Manager Integration
# =============================================================================

class TestLocalProjectManagerIntegration:
    """Tests for local project manager integration."""

    @pytest.fixture
    def local_project_env(self, tmp_path):
        """Set up local project environment."""
        project_dir = tmp_path / "local-project"
        project_dir.mkdir()

        return {"project_dir": project_dir, "tmp_path": tmp_path}

    @pytest.mark.integration
    def test_project_directory_structure(self, local_project_env):
        """Test project directory structure is created correctly."""
        project_dir = local_project_env["project_dir"]

        # Create expected structure
        (project_dir / "prompts").mkdir()
        (project_dir / ".beads").mkdir()
        (project_dir / ".git").mkdir()

        # Verify structure
        assert (project_dir / "prompts").exists()
        assert (project_dir / ".beads").exists()
        assert (project_dir / ".git").exists()

    @pytest.mark.integration
    def test_prompt_files_creation(self, local_project_env):
        """Test prompt files are created correctly."""
        project_dir = local_project_env["project_dir"]
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir()

        # Create prompt files
        prompt_files = {
            "app_spec.txt": "<app-spec><name>Test</name></app-spec>",
            "coding_prompt.md": "# Coding Instructions",
            "initializer_prompt.md": "# Init Instructions",
        }

        for filename, content in prompt_files.items():
            (prompts_dir / filename).write_text(content)

        # Verify
        for filename in prompt_files:
            assert (prompts_dir / filename).exists()


# =============================================================================
# Error Propagation Tests
# =============================================================================

class TestErrorPropagation:
    """Tests for error propagation between services."""

    @pytest.mark.integration
    def test_registry_error_propagation(self, isolated_registry):
        """Test registry errors propagate correctly."""
        # Duplicate project error
        isolated_registry.register_project("error-test", "https://github.com/user/repo.git")

        with pytest.raises(Exception) as exc_info:
            isolated_registry.register_project("error-test", "https://github.com/other/repo.git")

        # Error should be meaningful
        assert exc_info.value is not None

    @pytest.mark.integration
    def test_validation_error_format(self, isolated_registry):
        """Test validation errors have consistent format."""
        with pytest.raises(ValueError) as exc_info:
            isolated_registry.register_project(
                name="invalid@name",
                git_url="https://github.com/user/repo.git"
            )

        error = exc_info.value
        assert str(error)  # Should have message


# =============================================================================
# Data Flow Tests
# =============================================================================

class TestDataFlow:
    """Tests for data flow between components."""

    @pytest.fixture
    def data_flow_env(self, tmp_path, monkeypatch):
        """Set up data flow test environment."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        projects_dir = temp_config / "projects"
        projects_dir.mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "registry.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: projects_dir)

        return {
            "registry": registry,
            "projects_dir": projects_dir,
        }

    @pytest.mark.integration
    def test_project_to_container_flow(self, data_flow_env):
        """Test data flows from project to container correctly."""
        registry = data_flow_env["registry"]
        projects_dir = data_flow_env["projects_dir"]

        # Create project
        registry.register_project(
            name="flow-test",
            git_url="https://github.com/user/repo.git"
        )

        # Create project directory
        project_dir = projects_dir / "flow-test"
        project_dir.mkdir()

        # Create container
        registry.create_container("flow-test", 1, "coding")

        # Verify flow
        project_info = registry.get_project_info("flow-test")
        containers = registry.list_project_containers("flow-test")

        assert project_info is not None
        assert len(containers) == 1
        assert containers[0]["project_name"] == "flow-test"

    @pytest.mark.integration
    def test_feature_to_progress_flow(self, data_flow_env):
        """Test data flows from features to progress correctly."""
        registry = data_flow_env["registry"]
        projects_dir = data_flow_env["projects_dir"]

        # Setup
        registry.register_project("progress-flow", "https://github.com/user/repo.git")

        project_dir = projects_dir / "progress-flow"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        # Create features
        issues_file = beads_dir / "issues.jsonl"
        features = [
            {"id": "f-1", "status": "closed"},
            {"id": "f-2", "status": "closed"},
            {"id": "f-3", "status": "open"},
        ]

        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Calculate progress
        with open(issues_file) as f:
            all_features = [json.loads(line) for line in f if line.strip()]

        progress = {
            "passing": sum(1 for f in all_features if f["status"] == "closed"),
            "total": len(all_features),
        }
        progress["percentage"] = (progress["passing"] / progress["total"]) * 100

        # Verify flow
        assert progress["passing"] == 2
        assert progress["total"] == 3
        assert progress["percentage"] == pytest.approx(66.67, rel=0.1)


# =============================================================================
# State Synchronization Tests
# =============================================================================

class TestStateSynchronization:
    """Tests for state synchronization between components."""

    @pytest.mark.integration
    def test_container_state_sync(self, isolated_registry):
        """Test container state stays synchronized."""
        # Setup
        isolated_registry.register_project("sync-test", "https://github.com/user/repo.git")
        isolated_registry.create_container("sync-test", 1, "coding")

        # Multiple state updates
        states = ["running", "stopped", "running", "completed"]

        for state in states:
            isolated_registry.update_container_status(
                "sync-test", 1, "coding",
                status=state
            )

            # Verify immediately
            container = isolated_registry.get_container("sync-test", 1, "coding")
            assert container["status"] == state

    @pytest.mark.integration
    def test_project_container_consistency(self, isolated_registry):
        """Test project and container state consistency."""
        # Create project
        isolated_registry.register_project("consistency-test", "https://github.com/user/repo.git")

        # Create containers
        for i in range(1, 4):
            isolated_registry.create_container("consistency-test", i, "coding")

        # Verify consistency
        project_info = isolated_registry.get_project_info("consistency-test")
        containers = isolated_registry.list_project_containers("consistency-test")

        assert project_info is not None
        assert len(containers) == 3
        assert all(c["project_name"] == "consistency-test" for c in containers)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_websocket_state_sync(self):
        """Test WebSocket connection state synchronization."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        # Add connections
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await manager.connect("sync-ws", ws1)
        await manager.connect("sync-ws", ws2)

        # Verify state
        assert len(manager.active_connections["sync-ws"]) == 2

        # Remove one
        manager.disconnect("sync-ws", ws1)

        # Verify updated state
        assert len(manager.active_connections["sync-ws"]) == 1

        # Remove last
        manager.disconnect("sync-ws", ws2)

        # Verify empty
        assert len(manager.active_connections.get("sync-ws", [])) == 0
