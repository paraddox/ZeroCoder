"""
Complete Workflow End-to-End Tests
==================================

Enterprise-grade E2E tests for complete application workflows including:
- Full project lifecycle
- Feature tracking through completion
- Error recovery scenarios
- Data persistence verification
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


class TestFullProjectLifecycle:
    """E2E tests for complete project lifecycle."""

    @pytest.mark.e2e
    def test_project_creation_to_deletion(self, isolated_registry, tmp_path):
        """Test complete project lifecycle from creation to deletion."""
        project_name = f"e2e-lifecycle-{int(time.time())}"

        # Step 1: Create project via registry
        isolated_registry.register_project(
            name=project_name,
            git_url="https://github.com/e2e/test-repo.git",
            is_new=True
        )

        # Step 2: Verify project exists
        info = isolated_registry.get_project_info(project_name)
        assert info is not None
        assert info["is_new"] is True

        # Step 3: Create containers
        for i in range(1, 4):
            isolated_registry.create_container(
                project_name=project_name,
                container_number=i,
                container_type="coding"
            )

        # Step 4: Verify containers
        containers = isolated_registry.list_project_containers(project_name)
        assert len(containers) == 3

        # Step 5: Delete containers
        deleted = isolated_registry.delete_all_project_containers(project_name)
        assert deleted == 3

        # Step 6: Delete project
        result = isolated_registry.unregister_project(project_name)
        assert result is True

        # Step 7: Verify deletion
        info = isolated_registry.get_project_info(project_name)
        assert info is None

    @pytest.mark.e2e
    def test_feature_file_lifecycle(self, tmp_path):
        """Test complete feature lifecycle using file operations."""
        # Create project directory structure
        project_dir = tmp_path / "e2e-feature-project"
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir(parents=True)

        issues_file = beads_dir / "issues.jsonl"

        # Step 1: Create initial features
        features = [
            {"id": "feat-1", "title": "Feature 1", "status": "open", "priority": 0},
            {"id": "feat-2", "title": "Feature 2", "status": "open", "priority": 1},
        ]
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Step 2: Read and verify
        with open(issues_file, "r") as f:
            lines = f.readlines()
        assert len(lines) == 2

        # Step 3: Update a feature status (simulate progress)
        features[0]["status"] = "in_progress"
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Step 4: Complete a feature
        features[0]["status"] = "closed"
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Step 5: Verify final state
        with open(issues_file, "r") as f:
            final_features = [json.loads(line) for line in f]

        assert final_features[0]["status"] == "closed"
        assert final_features[1]["status"] == "open"


class TestDataPersistence:
    """E2E tests for data persistence across operations."""

    @pytest.mark.e2e
    def test_registry_persistence(self, isolated_registry, tmp_path):
        """Test that registry data persists correctly."""
        # Register project
        isolated_registry.register_project(
            name="persistence-test",
            git_url="https://github.com/test/repo.git",
            is_new=True
        )

        # Retrieve and verify
        info = isolated_registry.get_project_info("persistence-test")
        assert info is not None
        assert info["git_url"] == "https://github.com/test/repo.git"
        assert info["is_new"] is True

        # Update and verify
        isolated_registry.mark_project_initialized("persistence-test")
        info = isolated_registry.get_project_info("persistence-test")
        assert info["is_new"] is False

        # Update container count and verify
        isolated_registry.update_target_container_count("persistence-test", 3)
        info = isolated_registry.get_project_info("persistence-test")
        assert info["target_container_count"] == 3

    @pytest.mark.e2e
    def test_container_record_persistence(self, isolated_registry):
        """Test that container records persist correctly."""
        # Register project first
        isolated_registry.register_project(
            name="container-persist-test",
            git_url="https://github.com/test/repo.git"
        )

        # Create container
        container_id = isolated_registry.create_container(
            project_name="container-persist-test",
            container_number=1,
            container_type="coding"
        )
        assert container_id is not None

        # Retrieve and verify
        container = isolated_registry.get_container(
            project_name="container-persist-test",
            container_number=1,
            container_type="coding"
        )
        assert container is not None
        assert container["status"] == "created"

        # Update status and verify
        isolated_registry.update_container_status(
            project_name="container-persist-test",
            container_number=1,
            container_type="coding",
            status="running",
            docker_container_id="test-container-123"
        )

        container = isolated_registry.get_container(
            project_name="container-persist-test",
            container_number=1,
            container_type="coding"
        )
        assert container["status"] == "running"
        assert container["docker_container_id"] == "test-container-123"


class TestErrorRecovery:
    """E2E tests for error recovery scenarios."""

    @pytest.mark.e2e
    def test_invalid_project_recovery(self, isolated_registry):
        """Test recovery from invalid project operations."""
        # Try to get non-existent project
        info = isolated_registry.get_project_info("nonexistent-project-xyz")
        assert info is None

        # Try to delete non-existent project
        result = isolated_registry.unregister_project("nonexistent-project-xyz")
        assert result is False

        # Try to get non-existent container
        container = isolated_registry.get_container(
            "nonexistent", 1, "coding"
        )
        assert container is None

    @pytest.mark.e2e
    def test_concurrent_operations_recovery(self, isolated_registry):
        """Test recovery from concurrent operations."""
        import concurrent.futures
        import threading

        project_name = f"concurrent-test-{int(time.time())}"

        isolated_registry.register_project(
            name=project_name,
            git_url="https://github.com/test/repo.git"
        )

        isolated_registry.create_container(
            project_name=project_name,
            container_number=1,
            container_type="coding"
        )

        results = []
        lock = threading.Lock()

        def update_status(status):
            try:
                isolated_registry.update_container_status(
                    project_name=project_name,
                    container_number=1,
                    container_type="coding",
                    status=status
                )
                with lock:
                    results.append(True)
            except Exception:
                with lock:
                    results.append(False)

        # Make many concurrent updates
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(update_status, "running" if i % 2 == 0 else "stopped")
                for i in range(20)
            ]
            concurrent.futures.wait(futures)

        # At least some should succeed
        success_count = sum(1 for r in results if r)
        assert success_count >= 1


class TestBeadsSyncWorkflow:
    """E2E tests for beads sync workflow."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_beads_sync_lifecycle(self, tmp_path, monkeypatch):
        """Test complete beads sync lifecycle."""
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
            "e2e-beads-test",
            "https://github.com/test/repo.git"
        )

        # Create local beads data
        beads_dir = tmp_path / "beads-sync" / "e2e-beads-test" / ".beads"
        beads_dir.mkdir(parents=True)

        # Create issues
        issues = [
            {"id": "feat-1", "title": "Feature 1", "status": "open", "priority": 0},
            {"id": "feat-2", "title": "Feature 2", "status": "in_progress", "priority": 1},
            {"id": "feat-3", "title": "Feature 3", "status": "closed", "priority": 2},
        ]

        with open(beads_dir / "issues.jsonl", "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        # Test task reading
        tasks = manager.get_tasks()
        assert len(tasks) == 3

        # Test stats
        stats = manager.get_stats()
        assert stats["open"] == 1
        assert stats["in_progress"] == 1
        assert stats["closed"] == 1
        assert stats["total"] == 3

        # Test filtering
        open_tasks = manager.get_tasks_by_status("open")
        assert len(open_tasks) == 1


class TestProjectPromptManagement:
    """E2E tests for project prompt management."""

    @pytest.mark.e2e
    def test_prompt_scaffold_and_refresh(self, tmp_path):
        """Test complete prompt scaffolding and refresh workflow."""
        from prompts import (
            scaffold_project_prompts,
            has_project_prompts,
            refresh_project_prompts,
            TEMPLATES_DIR
        )

        project_dir = tmp_path / "e2e-prompt-project"
        project_dir.mkdir(parents=True)

        # Skip if templates don't exist
        if not TEMPLATES_DIR.exists():
            pytest.skip("Templates directory not found")

        # Step 1: Initial scaffold
        prompts_dir = scaffold_project_prompts(project_dir)
        assert prompts_dir.exists()

        # Step 2: Add valid app spec
        (prompts_dir / "app_spec.txt").write_text(
            "<project_specification>E2E Test App</project_specification>"
        )

        # Step 3: Verify prompts detected
        assert has_project_prompts(project_dir) is True

        # Step 4: Refresh prompts
        updated = refresh_project_prompts(project_dir)
        assert isinstance(updated, list)


class TestMultiContainerWorkflow:
    """E2E tests for multi-container scenarios."""

    @pytest.mark.e2e
    def test_multiple_container_records(self, isolated_registry):
        """Test managing multiple containers for a project."""
        project_name = "multi-container-e2e"

        # Register project
        isolated_registry.register_project(
            name=project_name,
            git_url="https://github.com/test/repo.git"
        )

        # Update to support 3 containers
        isolated_registry.update_target_container_count(project_name, 3)

        # Create multiple containers
        for i in range(1, 4):
            container_id = isolated_registry.create_container(
                project_name=project_name,
                container_number=i,
                container_type="coding"
            )
            assert container_id is not None

        # Verify all containers exist
        containers = isolated_registry.list_project_containers(project_name)
        assert len(containers) == 3

        # Update each container's status
        for i in range(1, 4):
            isolated_registry.update_container_status(
                project_name=project_name,
                container_number=i,
                container_type="coding",
                status="running",
                current_feature=f"feat-{i}"
            )

        # Verify all running
        containers = isolated_registry.list_project_containers(project_name)
        running_count = sum(1 for c in containers if c["status"] == "running")
        assert running_count == 3

        # Cleanup - delete all containers
        deleted = isolated_registry.delete_all_project_containers(project_name)
        assert deleted == 3

        # Verify cleanup
        containers = isolated_registry.list_project_containers(project_name)
        assert len(containers) == 0


class TestExistingRepoWorkflow:
    """E2E tests for existing repository workflow."""

    @pytest.mark.e2e
    def test_existing_repo_scaffold(self, tmp_path):
        """Test scaffolding for existing repository."""
        from prompts import (
            scaffold_existing_repo,
            is_existing_repo_project,
            BEADS_WORKFLOW_MARKER
        )

        project_dir = tmp_path / "existing-repo-e2e"
        project_dir.mkdir(parents=True)

        # Create existing CLAUDE.md (simulating pre-existing repo)
        (project_dir / "CLAUDE.md").write_text("# My Existing Project\n\nExisting instructions.")

        # Scaffold for existing repo
        scaffold_existing_repo(project_dir)

        # Verify CLAUDE.md updated
        claude_content = (project_dir / "CLAUDE.md").read_text()
        assert "My Existing Project" in claude_content  # Preserved
        assert BEADS_WORKFLOW_MARKER in claude_content  # Added

        # Verify prompts directory created
        assert (project_dir / "prompts").exists()

        # Verify .gitignore updated
        gitignore = project_dir / ".gitignore"
        assert gitignore.exists()
        assert ".claude/" in gitignore.read_text()

        # Verify it's detected as existing repo (no valid spec)
        assert is_existing_repo_project(project_dir) is True


class TestSchemaValidation:
    """E2E tests for schema validation."""

    @pytest.mark.e2e
    def test_project_create_validation(self):
        """Test ProjectCreate schema validation end-to-end."""
        from server.schemas import ProjectCreate
        from pydantic import ValidationError

        # Valid project
        project = ProjectCreate(
            name="valid-project",
            git_url="https://github.com/user/repo.git",
            is_new=True
        )
        assert project.name == "valid-project"

        # Invalid name
        with pytest.raises(ValidationError):
            ProjectCreate(
                name="invalid name",
                git_url="https://github.com/user/repo.git"
            )

    @pytest.mark.e2e
    def test_feature_schema_workflow(self):
        """Test feature schema workflow end-to-end."""
        from server.schemas import FeatureCreate, FeatureUpdate, FeatureResponse

        # Create feature
        feature = FeatureCreate(
            category="auth",
            name="User Login",
            description="Implement login",
            steps=["Create form", "Add validation"]
        )
        assert feature.category == "auth"

        # Update feature
        update = FeatureUpdate(
            status="in_progress",
            priority=0
        )
        assert update.priority == 0

        # Response
        response = FeatureResponse(
            id="feat-1",
            category="auth",
            name="User Login",
            description="Implement login",
            steps=["Create form"],
            priority=0,
            passes=False,
            in_progress=True
        )
        assert response.in_progress is True

    @pytest.mark.e2e
    def test_container_count_limits(self):
        """Test container count validation."""
        from server.schemas import ContainerCountUpdate
        from pydantic import ValidationError

        # Valid counts
        for count in [1, 5, 10]:
            update = ContainerCountUpdate(target_count=count)
            assert update.target_count == count

        # Invalid counts
        for count in [0, 11, 100, -1]:
            with pytest.raises(ValidationError):
                ContainerCountUpdate(target_count=count)
