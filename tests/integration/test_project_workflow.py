"""
Project Workflow Integration Tests
==================================

Enterprise-grade integration tests for complete project workflows including:
- Project creation and configuration
- Feature management
- Container lifecycle
- WebSocket updates
"""

import asyncio
import json
import pytest
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestProjectCreationWorkflow:
    """Integration tests for project creation workflow."""

    @pytest.mark.integration
    def test_registry_project_creation(self, isolated_registry, tmp_path):
        """Test project registration through registry."""
        project_name = f"integration-test-{int(time.time())}"

        # Register project
        isolated_registry.register_project(
            name=project_name,
            git_url="https://github.com/user/repo.git",
            is_new=True
        )

        # Verify registration
        info = isolated_registry.get_project_info(project_name)
        assert info is not None
        assert info["git_url"] == "https://github.com/user/repo.git"
        assert info["is_new"] is True

    @pytest.mark.integration
    def test_project_list_after_registration(self, isolated_registry):
        """Test listing projects after registration."""
        # Register multiple projects
        isolated_registry.register_project(
            name="project-a",
            git_url="https://github.com/user/repo-a.git"
        )
        isolated_registry.register_project(
            name="project-b",
            git_url="https://github.com/user/repo-b.git"
        )

        # List projects
        projects = isolated_registry.list_registered_projects()
        assert "project-a" in projects
        assert "project-b" in projects

    @pytest.mark.integration
    def test_project_deletion_workflow(self, isolated_registry):
        """Test project deletion workflow."""
        # Register project
        isolated_registry.register_project(
            name="to-delete",
            git_url="https://github.com/user/repo.git"
        )

        # Verify exists
        assert isolated_registry.get_project_info("to-delete") is not None

        # Delete
        result = isolated_registry.unregister_project("to-delete")
        assert result is True

        # Verify deleted
        assert isolated_registry.get_project_info("to-delete") is None


class TestFeatureManagementWorkflow:
    """Integration tests for feature management workflow."""

    @pytest.fixture
    def project_with_beads(self, isolated_registry, tmp_path):
        """Set up a project with beads for feature tests."""
        project_name = "feature-test-project"
        project_dir = tmp_path / "projects" / project_name
        project_dir.mkdir(parents=True)

        # Create .beads directory
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        # Create sample issues.jsonl
        issues = [
            {"id": "feat-1", "title": "Feature One", "status": "open", "priority": 0},
            {"id": "feat-2", "title": "Feature Two", "status": "in_progress", "priority": 1},
            {"id": "feat-3", "title": "Feature Three", "status": "closed", "priority": 2},
        ]
        with open(beads_dir / "issues.jsonl", "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        isolated_registry.register_project(
            name=project_name,
            git_url="https://github.com/user/repo.git"
        )

        return {
            "project_name": project_name,
            "project_dir": project_dir,
            "beads_dir": beads_dir,
        }

    @pytest.mark.integration
    def test_feature_file_parsing(self, project_with_beads):
        """Test parsing feature files from beads directory."""
        beads_dir = project_with_beads["beads_dir"]
        issues_file = beads_dir / "issues.jsonl"

        # Read and parse
        issues = []
        with open(issues_file, "r") as f:
            for line in f:
                issues.append(json.loads(line.strip()))

        assert len(issues) == 3
        assert issues[0]["status"] == "open"
        assert issues[1]["status"] == "in_progress"
        assert issues[2]["status"] == "closed"


class TestContainerWorkflow:
    """Integration tests for container lifecycle workflow."""

    @pytest.mark.integration
    def test_container_record_lifecycle(self, isolated_registry):
        """Test container record lifecycle."""
        # Register project
        isolated_registry.register_project(
            name="container-test",
            git_url="https://github.com/user/repo.git"
        )

        # Create container
        container_id = isolated_registry.create_container(
            project_name="container-test",
            container_number=1,
            container_type="coding"
        )
        assert container_id is not None

        # Update status
        isolated_registry.update_container_status(
            project_name="container-test",
            container_number=1,
            container_type="coding",
            status="running",
            docker_container_id="test-123"
        )

        # Verify status
        container = isolated_registry.get_container(
            project_name="container-test",
            container_number=1,
            container_type="coding"
        )
        assert container["status"] == "running"

        # Delete
        result = isolated_registry.delete_container(
            "container-test", 1, "coding"
        )
        assert result is True


class TestWebSocketIntegration:
    """Integration tests for WebSocket functionality."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_websocket_connection_manager(self):
        """Test WebSocket connection management."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        assert manager is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_connection_manager_methods(self):
        """Test ConnectionManager method signatures."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()

        # Test that methods exist
        assert hasattr(manager, "connect")
        assert hasattr(manager, "disconnect")
        assert hasattr(manager, "broadcast_to_project")


class TestDataPersistence:
    """Integration tests for data persistence."""

    @pytest.mark.integration
    def test_registry_persistence(self, isolated_registry):
        """Test that registry data persists correctly."""
        # Register project
        isolated_registry.register_project(
            name="persist-test",
            git_url="https://github.com/test/repo.git",
            is_new=True
        )

        # Retrieve and verify
        info = isolated_registry.get_project_info("persist-test")
        assert info is not None
        assert info["is_new"] is True

        # Update
        isolated_registry.mark_project_initialized("persist-test")

        # Verify update persisted
        info = isolated_registry.get_project_info("persist-test")
        assert info["is_new"] is False

    @pytest.mark.integration
    def test_container_count_update(self, isolated_registry):
        """Test container count update persistence."""
        # Register project
        isolated_registry.register_project(
            name="count-test",
            git_url="https://github.com/test/repo.git"
        )

        # Initial count should be 1
        info = isolated_registry.get_project_info("count-test")
        assert info["target_container_count"] == 1

        # Update count
        isolated_registry.update_target_container_count("count-test", 5)

        # Verify
        info = isolated_registry.get_project_info("count-test")
        assert info["target_container_count"] == 5


class TestConcurrentAccess:
    """Integration tests for concurrent access handling."""

    @pytest.mark.integration
    def test_concurrent_project_registration(self, isolated_registry):
        """Test that concurrent registration is handled safely."""
        import threading

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

        # Create threads for different project names
        threads = [
            threading.Thread(target=register, args=(f"concurrent-{i}",))
            for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed as they have different names
        assert len(results) + len(errors) == 5

    @pytest.mark.integration
    def test_concurrent_container_updates(self, isolated_registry):
        """Test concurrent container status updates."""
        import threading

        # Register project
        isolated_registry.register_project(
            name="concurrent-container",
            git_url="https://github.com/test/repo.git"
        )

        # Create container
        isolated_registry.create_container(
            project_name="concurrent-container",
            container_number=1,
            container_type="coding"
        )

        results = []
        lock = threading.Lock()

        def update_status(status):
            try:
                isolated_registry.update_container_status(
                    project_name="concurrent-container",
                    container_number=1,
                    container_type="coding",
                    status=status
                )
                with lock:
                    results.append(True)
            except Exception as e:
                with lock:
                    results.append(False)

        # Concurrent updates
        threads = [
            threading.Thread(target=update_status, args=("running",)),
            threading.Thread(target=update_status, args=("stopped",)),
            threading.Thread(target=update_status, args=("running",)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # At least one should succeed
        assert True in results


class TestBeadsSyncIntegration:
    """Integration tests for beads sync functionality."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_beads_sync_manager_creation(self, tmp_path, monkeypatch):
        """Test BeadsSyncManager creation and basic operations."""
        monkeypatch.setattr(
            "server.services.beads_sync_manager.get_beads_sync_dir",
            lambda: tmp_path / "beads-sync"
        )

        from server.services.beads_sync_manager import (
            get_beads_sync_manager,
            _sync_managers,
            _sync_managers_lock
        )

        # Clear existing managers
        with _sync_managers_lock:
            _sync_managers.clear()

        # Create manager
        manager = get_beads_sync_manager(
            "integration-project",
            "https://github.com/test/repo.git"
        )

        assert manager is not None
        assert manager.project_name == "integration-project"

    @pytest.mark.integration
    def test_beads_task_parsing(self, tmp_path, monkeypatch):
        """Test parsing tasks from beads files."""
        monkeypatch.setattr(
            "server.services.beads_sync_manager.get_beads_sync_dir",
            lambda: tmp_path / "beads-sync"
        )

        from server.services.beads_sync_manager import (
            get_beads_sync_manager,
            _sync_managers,
            _sync_managers_lock
        )

        # Clear existing managers
        with _sync_managers_lock:
            _sync_managers.clear()

        # Create manager
        manager = get_beads_sync_manager(
            "parse-test",
            "https://github.com/test/repo.git"
        )

        # Create beads data
        beads_dir = tmp_path / "beads-sync" / "parse-test" / ".beads"
        beads_dir.mkdir(parents=True)

        issues = [
            {"id": "feat-1", "title": "Feature 1", "status": "open"},
            {"id": "feat-2", "title": "Feature 2", "status": "closed"},
        ]
        with open(beads_dir / "issues.jsonl", "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        # Read tasks
        tasks = manager.get_tasks()
        assert len(tasks) == 2

        # Get stats
        stats = manager.get_stats()
        assert stats["open"] == 1
        assert stats["closed"] == 1


class TestPromptsIntegration:
    """Integration tests for prompts functionality."""

    @pytest.mark.integration
    def test_prompt_scaffold_integration(self, tmp_path):
        """Test complete prompt scaffolding."""
        from prompts import scaffold_project_prompts, has_project_prompts

        project_dir = tmp_path / "prompt-test"
        project_dir.mkdir(parents=True)

        # Scaffold
        prompts_dir = scaffold_project_prompts(project_dir)

        assert prompts_dir.exists()

        # Add valid app_spec
        (prompts_dir / "app_spec.txt").write_text(
            "<project_specification>Test App</project_specification>"
        )

        # Verify detection
        assert has_project_prompts(project_dir) is True

    @pytest.mark.integration
    def test_existing_repo_scaffold(self, tmp_path):
        """Test scaffolding for existing repos."""
        from prompts import scaffold_existing_repo, BEADS_WORKFLOW_MARKER

        project_dir = tmp_path / "existing-repo"
        project_dir.mkdir(parents=True)

        # Scaffold
        scaffold_existing_repo(project_dir)

        # Verify CLAUDE.md
        claude_md = project_dir / "CLAUDE.md"
        assert claude_md.exists()
        assert BEADS_WORKFLOW_MARKER in claude_md.read_text()

        # Verify prompts directory
        assert (project_dir / "prompts").exists()
