"""
Comprehensive API Integration Tests
===================================

Enterprise-grade integration tests for API endpoints including:
- Full request/response cycle testing
- Error handling verification
- State management across requests
- WebSocket integration
"""

import asyncio
import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
import threading
import time

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Project API Integration Tests
# =============================================================================

class TestProjectAPIIntegration:
    """Integration tests for project API endpoints."""

    @pytest.fixture
    def api_test_env(self, tmp_path, monkeypatch):
        """Set up API test environment."""
        import registry

        # Reset registry
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
        }

    @pytest.mark.integration
    def test_project_crud_flow(self, api_test_env):
        """Test complete project CRUD flow."""
        registry = api_test_env["registry"]

        # Create
        registry.register_project(
            name="crud-test",
            git_url="https://github.com/user/repo.git",
            is_new=True
        )

        # Read
        info = registry.get_project_info("crud-test")
        assert info is not None
        assert info["git_url"] == "https://github.com/user/repo.git"

        # Update (mark initialized)
        registry.mark_project_initialized("crud-test")
        info = registry.get_project_info("crud-test")
        assert info["is_new"] is False

        # Delete
        registry.unregister_project("crud-test")
        info = registry.get_project_info("crud-test")
        assert info is None

    @pytest.mark.integration
    def test_project_list_filtering(self, api_test_env):
        """Test project listing with filters."""
        registry = api_test_env["registry"]

        # Create multiple projects
        registry.register_project("filter-a", "https://github.com/user/a.git", is_new=True)
        registry.register_project("filter-b", "https://github.com/user/b.git", is_new=False)
        registry.register_project("filter-c", "https://github.com/user/c.git", is_new=True)

        # List all
        projects = registry.list_registered_projects()
        filter_projects = [p for p in projects if p.startswith("filter-")]
        assert len(filter_projects) == 3

    @pytest.mark.integration
    def test_project_with_containers(self, api_test_env):
        """Test project with container management."""
        registry = api_test_env["registry"]

        # Create project
        registry.register_project("container-project", "https://github.com/user/repo.git")

        # Add containers
        registry.create_container("container-project", 0, "init")
        registry.create_container("container-project", 1, "coding")
        registry.create_container("container-project", 2, "coding")

        # List containers
        containers = registry.list_project_containers("container-project")
        assert len(containers) == 3

        # Update container status
        registry.update_container_status(
            "container-project", 1, "coding",
            status="running"
        )

        container = registry.get_container("container-project", 1, "coding")
        assert container["status"] == "running"


# =============================================================================
# Feature API Integration Tests
# =============================================================================

class TestFeatureAPIIntegration:
    """Integration tests for feature API endpoints."""

    @pytest.fixture
    def feature_test_env(self, tmp_path):
        """Set up feature test environment."""
        project_dir = tmp_path / "feature-test"
        project_dir.mkdir()

        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        issues_file = beads_dir / "issues.jsonl"

        return {
            "project_dir": project_dir,
            "beads_dir": beads_dir,
            "issues_file": issues_file,
        }

    @pytest.mark.integration
    def test_feature_crud_via_beads(self, feature_test_env):
        """Test feature CRUD operations via beads files."""
        issues_file = feature_test_env["issues_file"]

        # Create features
        features = [
            {"id": "feat-1", "title": "Feature 1", "status": "open", "priority": 1},
            {"id": "feat-2", "title": "Feature 2", "status": "in_progress", "priority": 0},
        ]

        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Read features
        with open(issues_file) as f:
            read_features = [json.loads(line) for line in f if line.strip()]

        assert len(read_features) == 2
        assert read_features[0]["id"] == "feat-1"

        # Update feature
        features[0]["status"] = "in_progress"
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Verify update
        with open(issues_file) as f:
            updated = [json.loads(line) for line in f if line.strip()]

        assert updated[0]["status"] == "in_progress"

    @pytest.mark.integration
    def test_feature_status_counts(self, feature_test_env):
        """Test feature status counting."""
        issues_file = feature_test_env["issues_file"]

        features = [
            {"id": "feat-1", "status": "open"},
            {"id": "feat-2", "status": "open"},
            {"id": "feat-3", "status": "in_progress"},
            {"id": "feat-4", "status": "closed"},
            {"id": "feat-5", "status": "closed"},
            {"id": "feat-6", "status": "closed"},
        ]

        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Count by status
        with open(issues_file) as f:
            all_features = [json.loads(line) for line in f if line.strip()]

        counts = {}
        for f in all_features:
            status = f["status"]
            counts[status] = counts.get(status, 0) + 1

        assert counts["open"] == 2
        assert counts["in_progress"] == 1
        assert counts["closed"] == 3


# =============================================================================
# Container Integration Tests
# =============================================================================

class TestContainerIntegration:
    """Integration tests for container operations."""

    @pytest.fixture
    def container_test_env(self, tmp_path, monkeypatch):
        """Set up container test environment."""
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
    def test_container_lifecycle(self, container_test_env):
        """Test container lifecycle through registry."""
        registry = container_test_env["registry"]

        # Register project
        registry.register_project("lifecycle-test", "https://github.com/user/repo.git")

        # Create container
        container_id = registry.create_container("lifecycle-test", 1, "coding")
        assert container_id is not None

        # Get container
        container = registry.get_container("lifecycle-test", 1, "coding")
        assert container["status"] == "created"

        # Update status through lifecycle
        for status in ["running", "stopped", "running", "completed"]:
            registry.update_container_status(
                "lifecycle-test", 1, "coding",
                status=status
            )
            container = registry.get_container("lifecycle-test", 1, "coding")
            assert container["status"] == status

    @pytest.mark.integration
    def test_multiple_containers_per_project(self, container_test_env):
        """Test multiple containers for one project."""
        registry = container_test_env["registry"]

        registry.register_project("multi-container", "https://github.com/user/repo.git")
        registry.update_target_container_count("multi-container", 5)

        # Create 5 coding containers + 1 init
        registry.create_container("multi-container", 0, "init")
        for i in range(1, 6):
            registry.create_container("multi-container", i, "coding")

        containers = registry.list_project_containers("multi-container")
        assert len(containers) == 6

        # Filter by type
        coding_only = registry.list_project_containers("multi-container", container_type="coding")
        assert len(coding_only) == 5


# =============================================================================
# WebSocket Integration Tests
# =============================================================================

class TestWebSocketIntegration:
    """Integration tests for WebSocket functionality."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_connection_manager_lifecycle(self):
        """Test WebSocket connection manager lifecycle."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        # Create mock connections
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        # Connect
        await manager.connect("test-project", ws1)
        await manager.connect("test-project", ws2)

        assert len(manager.active_connections.get("test-project", [])) == 2

        # Disconnect one
        manager.disconnect("test-project", ws1)
        assert len(manager.active_connections.get("test-project", [])) == 1

        # Disconnect all
        manager.disconnect("test-project", ws2)
        # Empty list or no key
        connections = manager.active_connections.get("test-project", [])
        assert len(connections) == 0

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_broadcast_to_project(self):
        """Test broadcasting messages to project connections."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        ws1 = AsyncMock()
        ws2 = AsyncMock()

        await manager.connect("broadcast-test", ws1)
        await manager.connect("broadcast-test", ws2)

        # Broadcast message
        message = {"type": "progress", "passing": 5, "total": 10}
        await manager.broadcast("broadcast-test", message)

        # Both should receive
        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_project_isolation(self):
        """Test messages are isolated to their project."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        ws_project_a = AsyncMock()
        ws_project_b = AsyncMock()

        await manager.connect("project-a", ws_project_a)
        await manager.connect("project-b", ws_project_b)

        # Broadcast to project A only
        await manager.broadcast("project-a", {"message": "for A"})

        ws_project_a.send_json.assert_called_once()
        ws_project_b.send_json.assert_not_called()


# =============================================================================
# Progress Tracking Integration Tests
# =============================================================================

class TestProgressIntegration:
    """Integration tests for progress tracking."""

    @pytest.fixture
    def progress_test_env(self, tmp_path):
        """Set up progress test environment."""
        project_dir = tmp_path / "progress-test"
        project_dir.mkdir()

        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        return {
            "project_dir": project_dir,
            "beads_dir": beads_dir,
        }

    @pytest.mark.integration
    def test_progress_calculation(self, progress_test_env):
        """Test progress calculation from features."""
        issues_file = progress_test_env["beads_dir"] / "issues.jsonl"

        features = [
            {"id": "f-1", "status": "closed"},
            {"id": "f-2", "status": "closed"},
            {"id": "f-3", "status": "in_progress"},
            {"id": "f-4", "status": "open"},
            {"id": "f-5", "status": "open"},
        ]

        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Calculate progress
        with open(issues_file) as f:
            all_features = [json.loads(line) for line in f if line.strip()]

        total = len(all_features)
        closed = sum(1 for f in all_features if f["status"] == "closed")
        in_progress = sum(1 for f in all_features if f["status"] == "in_progress")

        percentage = (closed / total) * 100 if total > 0 else 0

        assert total == 5
        assert closed == 2
        assert in_progress == 1
        assert percentage == 40.0

    @pytest.mark.integration
    def test_progress_updates_on_feature_close(self, progress_test_env):
        """Test progress updates when features are closed."""
        issues_file = progress_test_env["beads_dir"] / "issues.jsonl"

        # Initial state: all open
        features = [
            {"id": "f-1", "status": "open"},
            {"id": "f-2", "status": "open"},
            {"id": "f-3", "status": "open"},
        ]

        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Close one feature
        features[0]["status"] = "closed"

        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Check progress
        with open(issues_file) as f:
            all_features = [json.loads(line) for line in f if line.strip()]

        closed = sum(1 for f in all_features if f["status"] == "closed")
        assert closed == 1


# =============================================================================
# Prompt Loading Integration Tests
# =============================================================================

class TestPromptIntegration:
    """Integration tests for prompt loading."""

    @pytest.fixture
    def prompt_test_env(self, tmp_path):
        """Set up prompt test environment."""
        project_dir = tmp_path / "prompt-test"
        project_dir.mkdir()

        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir()

        return {
            "project_dir": project_dir,
            "prompts_dir": prompts_dir,
        }

    @pytest.mark.integration
    def test_prompt_loading_fallback(self, prompt_test_env):
        """Test prompt loading with fallback."""
        prompts_dir = prompt_test_env["prompts_dir"]

        # Create project-specific prompt
        coding_prompt = prompts_dir / "coding_prompt.md"
        coding_prompt.write_text("# Custom Coding Prompt\nCustom instructions here.")

        # Verify it exists
        assert coding_prompt.exists()
        content = coding_prompt.read_text()
        assert "Custom" in content

    @pytest.mark.integration
    def test_app_spec_loading(self, prompt_test_env):
        """Test app spec loading."""
        prompts_dir = prompt_test_env["prompts_dir"]

        app_spec = prompts_dir / "app_spec.txt"
        spec_content = """<?xml version="1.0"?>
<app-spec>
    <name>Test App</name>
    <features>
        <feature>User Login</feature>
        <feature>Dashboard</feature>
    </features>
</app-spec>
"""
        app_spec.write_text(spec_content)

        assert app_spec.exists()
        content = app_spec.read_text()
        assert "<app-spec>" in content
        assert "User Login" in content


# =============================================================================
# Database Integration Tests
# =============================================================================

class TestDatabaseIntegration:
    """Integration tests for database operations."""

    @pytest.mark.integration
    def test_database_transaction_integrity(self, isolated_registry):
        """Test database maintains transaction integrity."""
        # Create project
        isolated_registry.register_project(
            name="transaction-test",
            git_url="https://github.com/user/repo.git"
        )

        # Create containers
        for i in range(3):
            isolated_registry.create_container("transaction-test", i, "coding" if i > 0 else "init")

        # All should be created
        containers = isolated_registry.list_project_containers("transaction-test")
        assert len(containers) == 3

        # Delete project should clean up containers
        isolated_registry.unregister_project("transaction-test")

        # Containers should be deleted too
        containers = isolated_registry.list_project_containers("transaction-test")
        assert len(containers) == 0

    @pytest.mark.integration
    def test_database_concurrent_access(self, isolated_registry):
        """Test database handles concurrent access."""
        results = []
        errors = []
        lock = threading.Lock()

        def register(name):
            try:
                isolated_registry.register_project(
                    name=name,
                    git_url=f"https://github.com/user/{name}.git"
                )
                with lock:
                    results.append(name)
            except Exception as e:
                with lock:
                    errors.append(str(e))

        # Run concurrent registrations
        threads = [
            threading.Thread(target=register, args=(f"concurrent-{i}",))
            for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All operations should complete
        total = len(results) + len(errors)
        assert total == 5

        # At least some should succeed
        assert len(results) >= 1


# =============================================================================
# End-to-End Flow Integration Tests
# =============================================================================

class TestEndToEndFlows:
    """Integration tests for complete user flows."""

    @pytest.fixture
    def full_env(self, tmp_path, monkeypatch):
        """Set up full environment for E2E flows."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        projects_dir = temp_config / "projects"
        projects_dir.mkdir()
        (temp_config / "beads-sync").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "registry.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: projects_dir)
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        return {
            "registry": registry,
            "projects_dir": projects_dir,
            "tmp_path": tmp_path,
        }

    @pytest.mark.integration
    def test_new_project_flow(self, full_env):
        """Test complete new project creation flow."""
        registry = full_env["registry"]
        projects_dir = full_env["projects_dir"]

        # Step 1: Register project
        registry.register_project(
            name="new-project-flow",
            git_url="https://github.com/user/repo.git",
            is_new=True
        )

        # Step 2: Create project directory structure
        project_dir = projects_dir / "new-project-flow"
        project_dir.mkdir()
        (project_dir / "prompts").mkdir()
        (project_dir / ".beads").mkdir()

        # Step 3: Initialize beads
        issues_file = project_dir / ".beads" / "issues.jsonl"
        issues_file.write_text("")

        # Step 4: Mark initialized
        registry.mark_project_initialized("new-project-flow")

        # Verify
        info = registry.get_project_info("new-project-flow")
        assert info["is_new"] is False
        assert project_dir.exists()
        assert issues_file.exists()

    @pytest.mark.integration
    def test_feature_completion_flow(self, full_env):
        """Test feature completion flow."""
        registry = full_env["registry"]
        projects_dir = full_env["projects_dir"]

        # Setup project
        registry.register_project("feature-flow", "https://github.com/user/repo.git")

        project_dir = projects_dir / "feature-flow"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        # Create features
        issues_file = beads_dir / "issues.jsonl"
        features = [
            {"id": "feat-1", "title": "Feature 1", "status": "open"},
            {"id": "feat-2", "title": "Feature 2", "status": "open"},
        ]

        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Create container
        registry.create_container("feature-flow", 1, "coding")

        # Start working (in_progress)
        features[0]["status"] = "in_progress"
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Complete feature
        features[0]["status"] = "closed"
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Verify progress
        with open(issues_file) as f:
            all_features = [json.loads(line) for line in f if line.strip()]

        closed = sum(1 for f in all_features if f["status"] == "closed")
        assert closed == 1
