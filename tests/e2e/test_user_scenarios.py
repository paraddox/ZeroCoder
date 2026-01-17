"""
User Scenario End-to-End Tests
==============================

Enterprise-grade E2E tests simulating real user workflows:
- New project creation workflow
- Existing repository workflow
- Feature development workflow
- Multi-container workflow
- Error recovery workflow
"""

import asyncio
import json
import pytest
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# New Project User Workflow
# =============================================================================

class TestNewProjectUserWorkflow:
    """E2E tests simulating new project creation workflow."""

    @pytest.fixture
    def user_env(self, tmp_path, monkeypatch):
        """Set up user environment."""
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

    @pytest.mark.e2e
    def test_complete_new_project_workflow(self, user_env):
        """Test complete new project creation workflow from user perspective."""
        registry = user_env["registry"]
        projects_dir = user_env["projects_dir"]

        # ===== Step 1: User enters project details =====
        project_name = "my-awesome-app"
        git_url = "https://github.com/user/my-awesome-app.git"

        # ===== Step 2: System registers project =====
        registry.register_project(
            name=project_name,
            git_url=git_url,
            is_new=True
        )

        # Verify registration
        info = registry.get_project_info(project_name)
        assert info is not None
        assert info["is_new"] is True

        # ===== Step 3: System creates project structure =====
        project_dir = projects_dir / project_name
        project_dir.mkdir()
        (project_dir / "prompts").mkdir()
        (project_dir / ".beads").mkdir()

        # ===== Step 4: User defines app spec via wizard =====
        app_spec = """<?xml version="1.0"?>
<app-spec>
    <name>My Awesome App</name>
    <description>A task management application</description>
    <features>
        <feature priority="0">User Authentication</feature>
        <feature priority="1">Task Dashboard</feature>
        <feature priority="2">Task CRUD</feature>
        <feature priority="3">Notifications</feature>
    </features>
</app-spec>
"""
        (project_dir / "prompts" / "app_spec.txt").write_text(app_spec)

        # ===== Step 5: System creates features from spec =====
        features = [
            {"id": "feat-1", "title": "User Authentication", "status": "open", "priority": 0},
            {"id": "feat-2", "title": "Task Dashboard", "status": "open", "priority": 1},
            {"id": "feat-3", "title": "Task CRUD", "status": "open", "priority": 2},
            {"id": "feat-4", "title": "Notifications", "status": "open", "priority": 3},
        ]

        issues_file = project_dir / ".beads" / "issues.jsonl"
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # ===== Step 6: System marks wizard complete =====
        registry.mark_project_initialized(project_name)

        info = registry.get_project_info(project_name)
        assert info["is_new"] is False

        # ===== Step 7: User starts coding agents =====
        registry.create_container(project_name, 0, "init")
        registry.create_container(project_name, 1, "coding")
        registry.create_container(project_name, 2, "coding")

        containers = registry.list_project_containers(project_name)
        assert len(containers) == 3

        # ===== Step 8: User monitors progress =====
        with open(issues_file) as f:
            all_features = [json.loads(line) for line in f if line.strip()]

        progress = {
            "total": len(all_features),
            "open": sum(1 for f in all_features if f["status"] == "open"),
            "completed": sum(1 for f in all_features if f["status"] == "closed"),
        }

        assert progress["total"] == 4
        assert progress["open"] == 4
        assert progress["completed"] == 0

    @pytest.mark.e2e
    def test_project_with_multiple_containers(self, user_env):
        """Test project workflow with multiple coding containers."""
        registry = user_env["registry"]
        projects_dir = user_env["projects_dir"]

        # Setup project
        registry.register_project("multi-container-app", "https://github.com/user/repo.git")
        registry.update_target_container_count("multi-container-app", 5)

        project_dir = projects_dir / "multi-container-app"
        project_dir.mkdir()
        (project_dir / ".beads").mkdir()

        # Create many features
        features = [
            {"id": f"feat-{i}", "title": f"Feature {i}", "status": "open", "priority": i % 5}
            for i in range(1, 21)  # 20 features
        ]

        issues_file = project_dir / ".beads" / "issues.jsonl"
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Start multiple containers
        for i in range(1, 6):
            registry.create_container("multi-container-app", i, "coding")
            registry.update_container_status(
                "multi-container-app", i, "coding",
                status="running"
            )

        # Verify all running
        containers = registry.list_project_containers("multi-container-app", container_type="coding")
        running = sum(1 for c in containers if c["status"] == "running")
        assert running == 5

        # Simulate feature completion by different containers
        for i, feature in enumerate(features[:5]):  # Complete first 5
            features[i]["status"] = "closed"

        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Check progress
        with open(issues_file) as f:
            all_features = [json.loads(line) for line in f if line.strip()]

        completed = sum(1 for f in all_features if f["status"] == "closed")
        assert completed == 5


# =============================================================================
# Existing Repository Workflow
# =============================================================================

class TestExistingRepoWorkflow:
    """E2E tests for adding existing repositories."""

    @pytest.fixture
    def existing_repo_env(self, tmp_path, monkeypatch):
        """Set up existing repo environment."""
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

    @pytest.mark.e2e
    def test_add_existing_repo_workflow(self, existing_repo_env):
        """Test adding an existing repository workflow."""
        registry = existing_repo_env["registry"]
        projects_dir = existing_repo_env["projects_dir"]

        # ===== Step 1: User adds existing repo =====
        registry.register_project(
            name="existing-app",
            git_url="https://github.com/user/existing-app.git",
            is_new=False  # Not new - existing repo
        )

        info = registry.get_project_info("existing-app")
        assert info["is_new"] is False

        # ===== Step 2: Simulate existing project structure =====
        project_dir = projects_dir / "existing-app"
        project_dir.mkdir()
        (project_dir / "prompts").mkdir()
        (project_dir / ".beads").mkdir()

        # Existing features already in beads
        features = [
            {"id": "feat-1", "title": "Login Page", "status": "closed"},
            {"id": "feat-2", "title": "Dashboard", "status": "closed"},
            {"id": "feat-3", "title": "Settings", "status": "in_progress"},
            {"id": "feat-4", "title": "Notifications", "status": "open"},
        ]

        issues_file = project_dir / ".beads" / "issues.jsonl"
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # ===== Step 3: User sees existing progress =====
        with open(issues_file) as f:
            all_features = [json.loads(line) for line in f if line.strip()]

        progress = {
            "completed": sum(1 for f in all_features if f["status"] == "closed"),
            "in_progress": sum(1 for f in all_features if f["status"] == "in_progress"),
            "pending": sum(1 for f in all_features if f["status"] == "open"),
        }

        assert progress["completed"] == 2
        assert progress["in_progress"] == 1
        assert progress["pending"] == 1

        # ===== Step 4: User continues development =====
        registry.create_container("existing-app", 1, "coding")
        registry.update_container_status(
            "existing-app", 1, "coding",
            status="running"
        )

        container = registry.get_container("existing-app", 1, "coding")
        assert container["status"] == "running"


# =============================================================================
# Feature Development Workflow
# =============================================================================

class TestFeatureDevelopmentWorkflow:
    """E2E tests for feature development workflow."""

    @pytest.fixture
    def feature_dev_env(self, tmp_path, monkeypatch):
        """Set up feature development environment."""
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

    @pytest.mark.e2e
    def test_feature_lifecycle_workflow(self, feature_dev_env):
        """Test complete feature lifecycle workflow."""
        registry = feature_dev_env["registry"]
        projects_dir = feature_dev_env["projects_dir"]

        # Setup
        registry.register_project("feature-lifecycle", "https://github.com/user/repo.git")

        project_dir = projects_dir / "feature-lifecycle"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        issues_file = beads_dir / "issues.jsonl"

        # ===== Feature 1: User Authentication =====

        # 1. Feature starts as pending
        features = [
            {"id": "feat-1", "title": "User Authentication", "status": "open", "priority": 0}
        ]
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # 2. Agent picks up feature (in_progress)
        features[0]["status"] = "in_progress"
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Verify in progress
        with open(issues_file) as f:
            current = [json.loads(line) for line in f if line.strip()]
        assert current[0]["status"] == "in_progress"

        # 3. Agent completes feature (closed)
        features[0]["status"] = "closed"
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Verify completed
        with open(issues_file) as f:
            current = [json.loads(line) for line in f if line.strip()]
        assert current[0]["status"] == "closed"

    @pytest.mark.e2e
    def test_parallel_feature_development(self, feature_dev_env):
        """Test parallel feature development by multiple containers."""
        registry = feature_dev_env["registry"]
        projects_dir = feature_dev_env["projects_dir"]

        # Setup
        registry.register_project("parallel-dev", "https://github.com/user/repo.git")

        project_dir = projects_dir / "parallel-dev"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        # Create multiple features
        features = [
            {"id": f"feat-{i}", "title": f"Feature {i}", "status": "open", "priority": i}
            for i in range(1, 6)
        ]

        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Start 3 containers
        for i in range(1, 4):
            registry.create_container("parallel-dev", i, "coding")
            registry.update_container_status(
                "parallel-dev", i, "coding",
                status="running"
            )

        # Each container picks a feature
        features[0]["status"] = "in_progress"  # Container 1
        features[1]["status"] = "in_progress"  # Container 2
        features[2]["status"] = "in_progress"  # Container 3

        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Verify parallel work
        with open(issues_file) as f:
            current = [json.loads(line) for line in f if line.strip()]

        in_progress = sum(1 for f in current if f["status"] == "in_progress")
        assert in_progress == 3


# =============================================================================
# Error Recovery Workflow
# =============================================================================

class TestErrorRecoveryWorkflow:
    """E2E tests for error recovery scenarios."""

    @pytest.fixture
    def error_env(self, tmp_path, monkeypatch):
        """Set up error recovery environment."""
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

    @pytest.mark.e2e
    def test_container_crash_recovery(self, error_env):
        """Test recovery from container crash."""
        registry = error_env["registry"]
        projects_dir = error_env["projects_dir"]

        # Setup
        registry.register_project("crash-recovery", "https://github.com/user/repo.git")

        project_dir = projects_dir / "crash-recovery"
        project_dir.mkdir()
        (project_dir / ".beads").mkdir()

        # Create container
        registry.create_container("crash-recovery", 1, "coding")
        registry.update_container_status(
            "crash-recovery", 1, "coding",
            status="running"
        )

        # Simulate crash
        registry.update_container_status(
            "crash-recovery", 1, "coding",
            status="stopped"
        )

        # Verify stopped
        container = registry.get_container("crash-recovery", 1, "coding")
        assert container["status"] == "stopped"

        # Recovery: Restart container
        registry.update_container_status(
            "crash-recovery", 1, "coding",
            status="running"
        )

        # Verify recovered
        container = registry.get_container("crash-recovery", 1, "coding")
        assert container["status"] == "running"

    @pytest.mark.e2e
    def test_stuck_feature_recovery(self, error_env):
        """Test recovery from stuck feature (in_progress but container stopped)."""
        registry = error_env["registry"]
        projects_dir = error_env["projects_dir"]

        # Setup
        registry.register_project("stuck-feature", "https://github.com/user/repo.git")

        project_dir = projects_dir / "stuck-feature"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        # Feature stuck in progress
        features = [
            {"id": "feat-1", "title": "Stuck Feature", "status": "in_progress"}
        ]

        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # No running containers
        registry.create_container("stuck-feature", 1, "coding")
        registry.update_container_status(
            "stuck-feature", 1, "coding",
            status="stopped"
        )

        # Recovery: Reset feature to open
        features[0]["status"] = "open"
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Restart container
        registry.update_container_status(
            "stuck-feature", 1, "coding",
            status="running"
        )

        # Verify recovery
        with open(issues_file) as f:
            current = [json.loads(line) for line in f if line.strip()]
        assert current[0]["status"] == "open"


# =============================================================================
# Project Completion Workflow
# =============================================================================

class TestProjectCompletionWorkflow:
    """E2E tests for project completion workflow."""

    @pytest.fixture
    def completion_env(self, tmp_path, monkeypatch):
        """Set up completion environment."""
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

    @pytest.mark.e2e
    def test_all_features_complete_workflow(self, completion_env):
        """Test workflow when all features are completed."""
        registry = completion_env["registry"]
        projects_dir = completion_env["projects_dir"]

        # Setup
        registry.register_project("complete-project", "https://github.com/user/repo.git")

        project_dir = projects_dir / "complete-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        # Create features
        features = [
            {"id": f"feat-{i}", "title": f"Feature {i}", "status": "open"}
            for i in range(1, 4)
        ]

        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Start container
        registry.create_container("complete-project", 1, "coding")
        registry.update_container_status(
            "complete-project", 1, "coding",
            status="running"
        )

        # Complete all features
        for feature in features:
            feature["status"] = "closed"

        with open(issues_file, "w") as f:
            for feature in features:
                f.write(json.dumps(feature) + "\n")

        # Check completion
        with open(issues_file) as f:
            all_features = [json.loads(line) for line in f if line.strip()]

        completed = sum(1 for f in all_features if f["status"] == "closed")
        total = len(all_features)

        assert completed == total
        assert completed == 3

        # Mark container as completed
        registry.update_container_status(
            "complete-project", 1, "coding",
            status="completed"
        )

        container = registry.get_container("complete-project", 1, "coding")
        assert container["status"] == "completed"

    @pytest.mark.e2e
    def test_project_deletion_workflow(self, completion_env):
        """Test project deletion workflow."""
        registry = completion_env["registry"]
        projects_dir = completion_env["projects_dir"]

        # Create and setup project
        registry.register_project("to-delete", "https://github.com/user/repo.git")

        project_dir = projects_dir / "to-delete"
        project_dir.mkdir()

        registry.create_container("to-delete", 1, "coding")

        # Verify exists
        assert registry.get_project_info("to-delete") is not None
        assert len(registry.list_project_containers("to-delete")) == 1

        # Delete project
        registry.unregister_project("to-delete")

        # Verify deleted
        assert registry.get_project_info("to-delete") is None
        assert len(registry.list_project_containers("to-delete")) == 0
