"""
End-to-End Workflow Enterprise Tests
=====================================

Comprehensive enterprise-grade E2E tests for complete workflows including:
- Project creation to completion flow
- Feature lifecycle management
- Agent execution simulation
- Error recovery scenarios
"""

import asyncio
import json
import pytest
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Project Lifecycle E2E Tests
# =============================================================================

class TestProjectLifecycleE2E:
    """E2E tests for complete project lifecycle."""

    @pytest.fixture
    def e2e_setup(self, tmp_path, monkeypatch):
        """Setup isolated environment for E2E tests."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()
        (temp_config / "beads-sync").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "e2e.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        return registry, temp_config

    @pytest.mark.e2e
    def test_complete_project_creation_flow(self, e2e_setup):
        """Test complete project creation workflow."""
        registry, temp_config = e2e_setup

        # Step 1: Register project
        registry.register_project(
            name="e2e-project",
            git_url="https://github.com/test/repo.git",
            is_new=True
        )

        info = registry.get_project_info("e2e-project")
        assert info is not None
        assert info["is_new"] is True

        # Step 2: Create project directory with prompts
        project_dir = temp_config / "projects" / "e2e-project"
        project_dir.mkdir(parents=True)

        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "app_spec.txt").write_text("<app-spec>E2E Test App</app-spec>")
        (prompts_dir / "coding_prompt.md").write_text("# Coding\nImplement features.")

        # Verify prompts directory exists with required files
        prompts_dir = project_dir / "prompts"
        assert prompts_dir.exists()
        assert (prompts_dir / "app_spec.txt").exists()
        assert (prompts_dir / "coding_prompt.md").exists()

        # Step 3: Initialize beads
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat\n")

        # Step 4: Create features
        features = [
            {"id": "feat-1", "title": "User Auth", "status": "open", "priority": 0},
            {"id": "feat-2", "title": "Dashboard", "status": "open", "priority": 1},
            {"id": "feat-3", "title": "Settings", "status": "open", "priority": 2},
        ]
        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        from progress import count_passing_tests
        passing, in_progress, total = count_passing_tests(project_dir)
        assert total == 3
        assert passing == 0

        # Step 5: Mark project initialized
        registry.mark_project_initialized("e2e-project")
        info = registry.get_project_info("e2e-project")
        assert info["is_new"] is False

    @pytest.mark.e2e
    def test_feature_implementation_flow(self, e2e_setup):
        """Test feature implementation workflow."""
        registry, temp_config = e2e_setup

        # Setup project
        registry.register_project(
            name="feature-flow",
            git_url="https://github.com/test/repo.git"
        )

        project_dir = temp_config / "projects" / "feature-flow"
        project_dir.mkdir(parents=True)

        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat\n")

        # Create features
        features = [
            {"id": "feat-1", "title": "Feature 1", "status": "open", "priority": 0},
            {"id": "feat-2", "title": "Feature 2", "status": "open", "priority": 1},
        ]
        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        # Simulate implementation: update status to in_progress
        features[0]["status"] = "in_progress"
        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        from progress import count_passing_tests
        passing, in_progress, total = count_passing_tests(project_dir)
        assert in_progress == 1

        # Simulate completion: update to closed
        features[0]["status"] = "closed"
        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        passing, in_progress, total = count_passing_tests(project_dir)
        assert passing == 1
        assert in_progress == 0

    @pytest.mark.e2e
    def test_project_deletion_flow(self, e2e_setup):
        """Test project deletion workflow."""
        registry, temp_config = e2e_setup

        # Create project
        registry.register_project(
            name="delete-test",
            git_url="https://github.com/test/repo.git"
        )

        # Create containers
        registry.create_container("delete-test", 1, "coding")
        registry.create_container("delete-test", 2, "coding")

        # Create project directory
        project_dir = temp_config / "projects" / "delete-test"
        project_dir.mkdir(parents=True)

        # Delete project
        registry.delete_all_project_containers("delete-test")
        registry.unregister_project("delete-test")

        # Verify deletion
        info = registry.get_project_info("delete-test")
        assert info is None

        containers = registry.list_project_containers("delete-test")
        assert len(containers) == 0


# =============================================================================
# Container Management E2E Tests
# =============================================================================

class TestContainerManagementE2E:
    """E2E tests for container management."""

    @pytest.fixture
    def container_setup(self, tmp_path, monkeypatch):
        """Setup for container E2E tests."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "container.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        registry.register_project(
            name="container-e2e",
            git_url="https://github.com/test/repo.git"
        )

        return registry, temp_config

    @pytest.mark.e2e
    def test_container_lifecycle(self, container_setup):
        """Test complete container lifecycle."""
        registry, temp_config = container_setup

        # Create container
        container_id = registry.create_container("container-e2e", 1, "coding")
        assert container_id is not None

        # Initial state
        container = registry.get_container("container-e2e", 1, "coding")
        assert container["status"] == "created"

        # Start (running)
        registry.update_container_status(
            "container-e2e", 1, "coding",
            status="running",
            docker_container_id="abc123"
        )

        container = registry.get_container("container-e2e", 1, "coding")
        assert container["status"] == "running"
        assert container["docker_container_id"] == "abc123"

        # Assign feature
        registry.update_container_status(
            "container-e2e", 1, "coding",
            status="running",
            current_feature="feat-1"
        )

        container = registry.get_container("container-e2e", 1, "coding")
        assert container["current_feature"] == "feat-1"

        # Stop
        registry.update_container_status(
            "container-e2e", 1, "coding",
            status="stopped"
        )

        container = registry.get_container("container-e2e", 1, "coding")
        assert container["status"] == "stopped"

        # Delete
        registry.delete_container("container-e2e", 1, "coding")

        container = registry.get_container("container-e2e", 1, "coding")
        assert container is None

    @pytest.mark.e2e
    def test_multiple_containers_flow(self, container_setup):
        """Test multiple containers workflow."""
        registry, temp_config = container_setup

        # Create init container and coding containers
        registry.create_container("container-e2e", 0, "init")
        registry.create_container("container-e2e", 1, "coding")
        registry.create_container("container-e2e", 2, "coding")
        registry.create_container("container-e2e", 3, "coding")

        # Verify all created
        containers = registry.list_project_containers("container-e2e")
        assert len(containers) == 4

        # Filter by type
        init_containers = registry.list_project_containers("container-e2e", container_type="init")
        assert len(init_containers) == 1

        coding_containers = registry.list_project_containers("container-e2e", container_type="coding")
        assert len(coding_containers) == 3

        # Start all coding containers
        for i in range(1, 4):
            registry.update_container_status(
                "container-e2e", i, "coding",
                status="running",
                current_feature=f"feat-{i}"
            )

        # Verify running
        for i in range(1, 4):
            container = registry.get_container("container-e2e", i, "coding")
            assert container["status"] == "running"
            assert container["current_feature"] == f"feat-{i}"


# =============================================================================
# Feature Progress E2E Tests
# =============================================================================

class TestFeatureProgressE2E:
    """E2E tests for feature progress tracking."""

    @pytest.fixture
    def progress_setup(self, tmp_path, monkeypatch):
        """Setup for progress E2E tests."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "progress.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        registry.register_project(
            name="progress-e2e",
            git_url="https://github.com/test/repo.git"
        )

        project_dir = temp_config / "projects" / "progress-e2e"
        project_dir.mkdir(parents=True)

        return registry, project_dir

    @pytest.mark.e2e
    def test_progress_tracking_flow(self, progress_setup):
        """Test complete progress tracking workflow."""
        registry, project_dir = progress_setup
        from progress import count_passing_tests, has_open_features

        # Setup beads
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat\n")

        # Create 5 features
        features = [
            {"id": f"feat-{i}", "title": f"Feature {i}", "status": "open", "priority": i}
            for i in range(1, 6)
        ]

        def update_features():
            with open(beads_dir / "issues.jsonl", "w") as f:
                for feat in features:
                    f.write(json.dumps(feat) + "\n")

        update_features()

        # Initial: 0% complete
        passing, in_progress, total = count_passing_tests(project_dir)
        assert total == 5
        assert passing == 0
        assert has_open_features(project_dir)

        # Implement first feature
        features[0]["status"] = "in_progress"
        update_features()

        passing, in_progress, total = count_passing_tests(project_dir)
        assert in_progress == 1

        features[0]["status"] = "closed"
        update_features()

        passing, in_progress, total = count_passing_tests(project_dir)
        assert passing == 1
        assert in_progress == 0

        # Implement all features
        for i in range(1, 5):
            features[i]["status"] = "closed"
        update_features()

        passing, in_progress, total = count_passing_tests(project_dir)
        assert passing == 5
        assert total == 5
        assert not has_open_features(project_dir)


# =============================================================================
# Simulation E2E Tests
# =============================================================================

class TestAgentSimulationE2E:
    """E2E tests simulating agent behavior."""

    @pytest.fixture
    def simulation_setup(self, tmp_path, monkeypatch):
        """Setup for simulation tests."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "sim.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        registry.register_project(
            name="simulation",
            git_url="https://github.com/test/repo.git"
        )

        project_dir = temp_config / "projects" / "simulation"
        project_dir.mkdir(parents=True)

        # Setup beads
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat\n")

        return registry, project_dir

    @pytest.mark.e2e
    def test_simulated_agent_session(self, simulation_setup):
        """Simulate a complete agent session."""
        registry, project_dir = simulation_setup
        from progress import count_passing_tests

        beads_dir = project_dir / ".beads"

        # Create features
        features = [
            {"id": "feat-1", "title": "Auth", "status": "open", "priority": 0},
            {"id": "feat-2", "title": "Dashboard", "status": "open", "priority": 1},
            {"id": "feat-3", "title": "Profile", "status": "open", "priority": 2},
        ]

        def update_features():
            with open(beads_dir / "issues.jsonl", "w") as f:
                for feat in features:
                    f.write(json.dumps(feat) + "\n")

        update_features()

        # Create container
        registry.create_container("simulation", 1, "coding")

        # Simulate agent session
        # 1. Start container
        registry.update_container_status(
            "simulation", 1, "coding",
            status="running",
            docker_container_id="sim123"
        )

        # 2. Pick feature
        registry.update_container_status(
            "simulation", 1, "coding",
            status="running",
            current_feature="feat-1"
        )

        # 3. Implement feature (simulate)
        features[0]["status"] = "in_progress"
        update_features()

        # 4. Complete feature
        features[0]["status"] = "closed"
        update_features()

        passing, _, total = count_passing_tests(project_dir)
        assert passing == 1

        # 5. Move to next feature
        registry.update_container_status(
            "simulation", 1, "coding",
            status="running",
            current_feature="feat-2"
        )

        features[1]["status"] = "in_progress"
        update_features()

        features[1]["status"] = "closed"
        update_features()

        passing, _, total = count_passing_tests(project_dir)
        assert passing == 2

        # 6. Stop container
        registry.update_container_status(
            "simulation", 1, "coding",
            status="stopped"
        )

        container = registry.get_container("simulation", 1, "coding")
        assert container["status"] == "stopped"


# =============================================================================
# Error Recovery E2E Tests
# =============================================================================

class TestErrorRecoveryE2E:
    """E2E tests for error recovery scenarios."""

    @pytest.fixture
    def recovery_setup(self, tmp_path, monkeypatch):
        """Setup for error recovery tests."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "recovery.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        return registry, temp_config

    @pytest.mark.e2e
    def test_recovery_from_corrupted_issues_file(self, recovery_setup):
        """Test recovery from corrupted issues file."""
        registry, temp_config = recovery_setup
        from progress import count_passing_tests

        registry.register_project(
            name="corrupted",
            git_url="https://github.com/test/repo.git"
        )

        project_dir = temp_config / "projects" / "corrupted"
        project_dir.mkdir(parents=True)

        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat\n")

        # Write corrupted file
        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text('{"id": "feat-1", "title": "Good"}\n{invalid json\n{"id": "feat-2", "title": "Also Good"}\n')

        # Should handle gracefully (skip corrupted line)
        passing, in_progress, total = count_passing_tests(project_dir)
        # Should get at least the valid entries
        assert total >= 1

    @pytest.mark.e2e
    def test_recovery_from_missing_beads_dir(self, recovery_setup):
        """Test recovery when beads directory is missing."""
        registry, temp_config = recovery_setup
        from progress import has_features, count_passing_tests

        registry.register_project(
            name="no-beads",
            git_url="https://github.com/test/repo.git"
        )

        project_dir = temp_config / "projects" / "no-beads"
        project_dir.mkdir(parents=True)

        # No beads directory
        assert has_features(project_dir) is False
        passing, in_progress, total = count_passing_tests(project_dir)
        assert total == 0

    @pytest.mark.e2e
    def test_recovery_from_stale_container_state(self, recovery_setup):
        """Test recovery from stale container state."""
        registry, temp_config = recovery_setup

        registry.register_project(
            name="stale-container",
            git_url="https://github.com/test/repo.git"
        )

        # Create container that should be running but isn't
        registry.create_container("stale-container", 1, "coding")
        registry.update_container_status(
            "stale-container", 1, "coding",
            status="running",
            docker_container_id="stale123"
        )

        # Simulate recovery: update status to stopped
        registry.update_container_status(
            "stale-container", 1, "coding",
            status="stopped"
        )

        container = registry.get_container("stale-container", 1, "coding")
        assert container["status"] == "stopped"


# =============================================================================
# Parallel Container E2E Tests
# =============================================================================

class TestParallelContainersE2E:
    """E2E tests for parallel container execution."""

    @pytest.fixture
    def parallel_setup(self, tmp_path, monkeypatch):
        """Setup for parallel container tests."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "parallel.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        registry.register_project(
            name="parallel-test",
            git_url="https://github.com/test/repo.git"
        )

        project_dir = temp_config / "projects" / "parallel-test"
        project_dir.mkdir(parents=True)

        return registry, project_dir

    @pytest.mark.e2e
    def test_parallel_container_execution(self, parallel_setup):
        """Test parallel container execution simulation."""
        registry, project_dir = parallel_setup
        from progress import count_passing_tests

        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat\n")

        # Create 10 features
        features = [
            {"id": f"feat-{i}", "title": f"Feature {i}", "status": "open", "priority": i}
            for i in range(1, 11)
        ]

        def update_features():
            with open(beads_dir / "issues.jsonl", "w") as f:
                for feat in features:
                    f.write(json.dumps(feat) + "\n")

        update_features()

        # Set target container count
        registry.update_target_container_count("parallel-test", 5)

        # Create 5 parallel containers
        for i in range(1, 6):
            registry.create_container("parallel-test", i, "coding")
            registry.update_container_status(
                "parallel-test", i, "coding",
                status="running",
                docker_container_id=f"container{i}"
            )

        containers = registry.list_project_containers("parallel-test", container_type="coding")
        assert len(containers) == 5

        # Simulate parallel execution: each container works on 2 features
        for i in range(1, 6):
            feat_idx = (i - 1) * 2
            registry.update_container_status(
                "parallel-test", i, "coding",
                status="running",
                current_feature=f"feat-{feat_idx + 1}"
            )

            # Complete first feature
            features[feat_idx]["status"] = "closed"
            update_features()

            # Complete second feature
            if feat_idx + 1 < 10:
                features[feat_idx + 1]["status"] = "closed"
                update_features()

        # All features should be done
        passing, _, total = count_passing_tests(project_dir)
        assert passing == 10


# =============================================================================
# Project Settings E2E Tests
# =============================================================================

class TestProjectSettingsE2E:
    """E2E tests for project settings management."""

    @pytest.fixture
    def settings_setup(self, tmp_path, monkeypatch):
        """Setup for settings tests."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "settings.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        return registry, temp_config

    @pytest.mark.e2e
    def test_project_settings_flow(self, settings_setup):
        """Test project settings management flow."""
        registry, temp_config = settings_setup
        from server.routers.projects import read_agent_model, write_agent_config

        registry.register_project(
            name="settings-test",
            git_url="https://github.com/test/repo.git"
        )

        project_dir = temp_config / "projects" / "settings-test"
        project_dir.mkdir(parents=True)
        (project_dir / "prompts").mkdir()

        # Default model
        model = read_agent_model(project_dir)
        assert model == "glm-4-7"

        # Update model
        write_agent_config(project_dir, "claude-opus-4-5-20251101")

        model = read_agent_model(project_dir)
        assert model == "claude-opus-4-5-20251101"

        # Update again
        write_agent_config(project_dir, "claude-sonnet-4-5-20250514")

        model = read_agent_model(project_dir)
        assert model == "claude-sonnet-4-5-20250514"
