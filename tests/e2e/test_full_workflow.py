"""
End-to-End Workflow Tests
=========================

Comprehensive tests for complete application workflows including:
- Project lifecycle (create, configure, run, complete)
- Feature management workflows
- Container lifecycle
- Error recovery scenarios
"""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestProjectLifecycle:
    """End-to-end tests for project lifecycle."""

    @pytest.mark.e2e
    def test_new_project_creation_flow(
        self, isolated_registry, tmp_path, mock_git_clone
    ):
        """Test complete flow for creating a new project."""
        # Step 1: Register project
        isolated_registry.register_project(
            name="e2e-project",
            git_url="https://github.com/user/repo.git",
            is_new=True
        )

        # Verify registration
        info = isolated_registry.get_project_info("e2e-project")
        assert info is not None
        assert info["is_new"] is True

        # Step 2: Verify project path
        path = isolated_registry.get_project_path("e2e-project")
        assert path is not None

        # Step 3: Mark as initialized (wizard complete)
        isolated_registry.mark_project_initialized("e2e-project")

        info = isolated_registry.get_project_info("e2e-project")
        assert info["is_new"] is False

    @pytest.mark.e2e
    def test_existing_project_import_flow(
        self, isolated_registry, tmp_path, mock_git_clone
    ):
        """Test flow for importing an existing project."""
        # Step 1: Register as existing (not new)
        isolated_registry.register_project(
            name="existing-project",
            git_url="https://github.com/user/existing.git",
            is_new=False
        )

        # Verify registration
        info = isolated_registry.get_project_info("existing-project")
        assert info is not None
        assert info["is_new"] is False

    @pytest.mark.e2e
    def test_project_deletion_flow(self, isolated_registry, tmp_path):
        """Test complete flow for deleting a project."""
        # Create project
        isolated_registry.register_project(
            name="to-delete-project",
            git_url="https://github.com/user/repo.git"
        )

        # Create containers
        isolated_registry.create_container("to-delete-project", 1, "coding")
        isolated_registry.create_container("to-delete-project", 2, "coding")

        # Delete containers first
        deleted = isolated_registry.delete_all_project_containers("to-delete-project")
        assert deleted == 2

        # Delete project
        result = isolated_registry.unregister_project("to-delete-project")
        assert result is True

        # Verify deletion
        info = isolated_registry.get_project_info("to-delete-project")
        assert info is None


class TestFeatureManagementWorkflow:
    """End-to-end tests for feature management."""

    @pytest.mark.e2e
    def test_feature_creation_to_completion_flow(
        self, isolated_registry, temp_project_dir
    ):
        """Test feature lifecycle from creation to completion."""
        # Setup project with beads
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        # Step 1: Create feature (simulated)
        feature = {
            "id": "feat-1",
            "title": "User Authentication",
            "status": "open",
            "priority": 1,
            "description": "Implement user login",
        }

        with open(issues_file, "w") as f:
            f.write(json.dumps(feature) + "\n")

        # Verify creation
        with open(issues_file, "r") as f:
            issues = [json.loads(line) for line in f if line.strip()]

        assert len(issues) == 1
        assert issues[0]["status"] == "open"

        # Step 2: Update to in_progress
        feature["status"] = "in_progress"
        with open(issues_file, "w") as f:
            f.write(json.dumps(feature) + "\n")

        # Verify update
        with open(issues_file, "r") as f:
            issues = [json.loads(line) for line in f if line.strip()]
        assert issues[0]["status"] == "in_progress"

        # Step 3: Mark as complete
        feature["status"] = "closed"
        with open(issues_file, "w") as f:
            f.write(json.dumps(feature) + "\n")

        # Verify completion
        with open(issues_file, "r") as f:
            issues = [json.loads(line) for line in f if line.strip()]
        assert issues[0]["status"] == "closed"

    @pytest.mark.e2e
    def test_multiple_feature_workflow(self, temp_project_dir):
        """Test managing multiple features simultaneously."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        # Create multiple features
        features = [
            {"id": "feat-1", "title": "Auth", "status": "open", "priority": 0},
            {"id": "feat-2", "title": "Dashboard", "status": "open", "priority": 1},
            {"id": "feat-3", "title": "Settings", "status": "open", "priority": 2},
        ]

        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Verify all created
        with open(issues_file, "r") as f:
            issues = [json.loads(line) for line in f if line.strip()]

        assert len(issues) == 3

        # Complete features one by one
        for i, feature in enumerate(features):
            feature["status"] = "closed"
            with open(issues_file, "w") as f:
                for feat in features:
                    f.write(json.dumps(feat) + "\n")

        # Verify all completed
        with open(issues_file, "r") as f:
            issues = [json.loads(line) for line in f if line.strip()]

        all_closed = all(issue["status"] == "closed" for issue in issues)
        assert all_closed


class TestContainerLifecycleWorkflow:
    """End-to-end tests for container lifecycle."""

    @pytest.mark.e2e
    def test_container_full_lifecycle(self, isolated_registry):
        """Test container from creation through completion."""
        # Create project
        isolated_registry.register_project(
            name="container-lifecycle",
            git_url="https://github.com/user/repo.git"
        )

        # Step 1: Create container
        container_id = isolated_registry.create_container(
            "container-lifecycle", 1, "coding"
        )
        assert container_id is not None

        # Step 2: Start container (update status)
        isolated_registry.update_container_status(
            "container-lifecycle", 1, "coding",
            status="running",
            docker_container_id="docker-abc123"
        )

        container = isolated_registry.get_container(
            "container-lifecycle", 1, "coding"
        )
        assert container["status"] == "running"

        # Step 3: Set current feature
        isolated_registry.update_container_status(
            "container-lifecycle", 1, "coding",
            status="running",
            current_feature="feat-1"
        )

        container = isolated_registry.get_container(
            "container-lifecycle", 1, "coding"
        )
        assert container["current_feature"] == "feat-1"

        # Step 4: Stop container
        isolated_registry.update_container_status(
            "container-lifecycle", 1, "coding",
            status="stopped"
        )

        container = isolated_registry.get_container(
            "container-lifecycle", 1, "coding"
        )
        assert container["status"] == "stopped"

        # Step 5: Complete container
        isolated_registry.update_container_status(
            "container-lifecycle", 1, "coding",
            status="completed"
        )

        container = isolated_registry.get_container(
            "container-lifecycle", 1, "coding"
        )
        assert container["status"] == "completed"

    @pytest.mark.e2e
    def test_multiple_containers_workflow(self, isolated_registry):
        """Test managing multiple containers for a project."""
        # Create project
        isolated_registry.register_project(
            name="multi-container",
            git_url="https://github.com/user/repo.git"
        )

        # Update target container count
        isolated_registry.update_target_container_count("multi-container", 3)

        info = isolated_registry.get_project_info("multi-container")
        assert info["target_container_count"] == 3

        # Create multiple containers
        for i in range(1, 4):
            isolated_registry.create_container("multi-container", i, "coding")

        containers = isolated_registry.list_project_containers("multi-container")
        assert len(containers) == 3

        # Start all containers
        for container in containers:
            isolated_registry.update_container_status(
                "multi-container",
                container["container_number"],
                container["container_type"],
                status="running"
            )

        containers = isolated_registry.list_project_containers("multi-container")
        all_running = all(c["status"] == "running" for c in containers)
        assert all_running


class TestWizardWorkflow:
    """End-to-end tests for project setup wizard."""

    @pytest.mark.e2e
    def test_wizard_complete_flow(self, temp_project_dir, sample_app_spec):
        """Test complete wizard flow from start to finish."""
        prompts_dir = temp_project_dir / "prompts"
        prompts_dir.mkdir(exist_ok=True)

        # Step 1: Create wizard status (in progress)
        status_file = prompts_dir / ".wizard_status.json"
        wizard_status = {
            "step": "chat",
            "spec_method": "claude",
            "started_at": datetime.now().isoformat(),
            "chat_messages": []
        }
        status_file.write_text(json.dumps(wizard_status))

        # Verify wizard is incomplete
        assert status_file.exists()

        # Step 2: Save app spec
        spec_file = prompts_dir / "app_spec.txt"
        spec_file.write_text(sample_app_spec)

        # Verify spec exists
        assert spec_file.exists()

        # Step 3: Clean up wizard status (wizard complete)
        status_file.unlink()

        # Verify wizard is complete
        assert not status_file.exists()
        assert spec_file.exists()

    @pytest.mark.e2e
    def test_wizard_resume_flow(self, temp_project_dir):
        """Test resuming an interrupted wizard."""
        prompts_dir = temp_project_dir / "prompts"
        prompts_dir.mkdir(exist_ok=True)

        # Create interrupted wizard state
        status_file = prompts_dir / ".wizard_status.json"
        wizard_status = {
            "step": "chat",
            "spec_method": "claude",
            "started_at": datetime.now().isoformat(),
            "chat_messages": [
                {"role": "user", "content": "Build a todo app"},
                {"role": "assistant", "content": "I'll help you build a todo app."}
            ]
        }
        status_file.write_text(json.dumps(wizard_status))

        # Load wizard state
        loaded = json.loads(status_file.read_text())

        # Verify state is preserved
        assert loaded["step"] == "chat"
        assert len(loaded["chat_messages"]) == 2
        assert loaded["chat_messages"][0]["content"] == "Build a todo app"


class TestErrorRecoveryWorkflow:
    """End-to-end tests for error recovery scenarios."""

    @pytest.mark.e2e
    def test_container_crash_recovery(self, isolated_registry):
        """Test recovery from container crash."""
        # Setup
        isolated_registry.register_project(
            name="crash-recovery",
            git_url="https://github.com/user/repo.git"
        )
        isolated_registry.create_container("crash-recovery", 1, "coding")

        # Simulate crash
        isolated_registry.update_container_status(
            "crash-recovery", 1, "coding",
            status="running"
        )

        # Simulate crash detection and status update
        isolated_registry.update_container_status(
            "crash-recovery", 1, "coding",
            status="stopped"
        )

        container = isolated_registry.get_container("crash-recovery", 1, "coding")
        assert container["status"] == "stopped"

        # Simulate restart
        isolated_registry.update_container_status(
            "crash-recovery", 1, "coding",
            status="running"
        )

        container = isolated_registry.get_container("crash-recovery", 1, "coding")
        assert container["status"] == "running"

    @pytest.mark.e2e
    def test_stale_project_cleanup(self, isolated_registry, tmp_path):
        """Test cleanup of stale projects."""
        # Create projects
        isolated_registry.register_project(
            name="active-project",
            git_url="https://github.com/user/active.git"
        )
        isolated_registry.register_project(
            name="stale-project",
            git_url="https://github.com/user/stale.git"
        )

        # List projects
        projects = isolated_registry.list_registered_projects()
        assert "active-project" in projects
        assert "stale-project" in projects

        # Manually clean up stale project
        isolated_registry.unregister_project("stale-project")

        # Verify cleanup
        projects = isolated_registry.list_registered_projects()
        assert "active-project" in projects
        assert "stale-project" not in projects


class TestProgressTrackingWorkflow:
    """End-to-end tests for progress tracking."""

    @pytest.mark.e2e
    def test_progress_tracking_full_cycle(
        self, isolated_registry, temp_project_dir
    ):
        """Test progress tracking from 0% to 100%."""
        # Setup project
        isolated_registry.register_project(
            name="progress-tracking",
            git_url="https://github.com/user/repo.git"
        )

        # Create features
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        features = [
            {"id": f"feat-{i}", "title": f"Feature {i}", "status": "open"}
            for i in range(1, 6)
        ]

        # Initial state: 0% complete
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        with open(issues_file, "r") as f:
            issues = [json.loads(line) for line in f if line.strip()]

        closed = sum(1 for i in issues if i["status"] == "closed")
        total = len(issues)
        assert closed == 0
        assert total == 5

        # Complete features one by one
        for i, feature in enumerate(features):
            feature["status"] = "closed"

            with open(issues_file, "w") as f:
                for feat in features:
                    f.write(json.dumps(feat) + "\n")

            with open(issues_file, "r") as f:
                issues = [json.loads(line) for line in f if line.strip()]

            closed = sum(1 for iss in issues if iss["status"] == "closed")
            percentage = (closed / len(issues)) * 100

            # Verify progress increases
            assert closed == i + 1
            assert percentage == (i + 1) * 20

        # Final state: 100% complete
        with open(issues_file, "r") as f:
            issues = [json.loads(line) for line in f if line.strip()]

        all_closed = all(i["status"] == "closed" for i in issues)
        assert all_closed


class TestCachingWorkflow:
    """End-to-end tests for caching functionality."""

    @pytest.mark.e2e
    def test_feature_cache_workflow(self, isolated_registry):
        """Test feature cache creation and retrieval workflow."""
        # Setup
        isolated_registry.register_project(
            name="cache-workflow",
            git_url="https://github.com/user/repo.git"
        )

        # Initial state: no cache
        cached = isolated_registry.get_feature_cache("cache-workflow")
        assert cached is None

        # Create cache
        feature_data = {
            "pending": [{"id": "feat-1", "title": "Feature 1"}],
            "in_progress": [],
            "done": []
        }
        isolated_registry.update_feature_cache("cache-workflow", feature_data)

        # Verify cache exists
        cached = isolated_registry.get_feature_cache("cache-workflow")
        assert cached is not None
        assert len(cached["pending"]) == 1

        # Update cache
        feature_data["pending"] = []
        feature_data["done"] = [{"id": "feat-1", "title": "Feature 1"}]
        isolated_registry.update_feature_cache("cache-workflow", feature_data)

        # Verify update
        cached = isolated_registry.get_feature_cache("cache-workflow")
        assert len(cached["pending"]) == 0
        assert len(cached["done"]) == 1

        # Delete cache
        isolated_registry.delete_feature_cache("cache-workflow")

        # Verify deletion
        cached = isolated_registry.get_feature_cache("cache-workflow")
        assert cached is None
