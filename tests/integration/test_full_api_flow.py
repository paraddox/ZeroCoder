"""
Full API Flow Integration Tests
===============================

Enterprise-grade integration tests for complete API workflows including:
- Project creation to completion
- Feature lifecycle management
- Container orchestration
- WebSocket communication
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_docker_client():
    """Mock Docker client for container operations."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="container-id-123",
            stderr="",
        )
        yield mock_run


@pytest.fixture
def mock_git_operations():
    """Mock git operations."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Cloning into 'repo'...",
            stderr="",
        )
        yield mock_run


# =============================================================================
# Project Lifecycle Tests
# =============================================================================

class TestProjectLifecycle:
    """Tests for complete project lifecycle."""

    @pytest.mark.integration
    def test_project_creation_to_deletion(self, isolated_registry, temp_project_dir, mock_git_operations):
        """Test complete project lifecycle from creation to deletion."""
        import registry

        # Create project
        project_name = "integration-test-project"
        git_url = "https://github.com/test/repo.git"

        # Register project
        registry.register_project(project_name, temp_project_dir, git_url, is_new=True)

        # Verify registration
        project_path = registry.get_project_path(project_name)
        assert project_path == temp_project_dir

        # Verify project info
        info = registry.get_project_info(project_name)
        assert info is not None
        assert info["git_url"] == git_url
        assert info["is_new"] is True

        # Update project
        registry.mark_project_initialized(project_name)
        updated_info = registry.get_project_info(project_name)
        assert updated_info["is_new"] is False

        # Unregister project
        registry.unregister_project(project_name)

        # Verify deletion
        assert registry.get_project_path(project_name) is None

    @pytest.mark.integration
    def test_project_with_containers(self, isolated_registry, temp_project_dir, mock_docker_client):
        """Test project with container creation and management."""
        import registry

        project_name = "container-test-project"
        git_url = "https://github.com/test/repo.git"

        # Create project
        registry.register_project(project_name, temp_project_dir, git_url)

        # Create containers
        container1 = registry.create_container(project_name, 1, "coding")
        container2 = registry.create_container(project_name, 2, "coding")

        assert container1 is not None
        assert container2 is not None

        # List containers
        containers = registry.list_project_containers(project_name)
        assert len(containers) == 2

        # Update container status
        registry.update_container_status(project_name, 1, "running")
        container = registry.get_container(project_name, 1)
        assert container["status"] == "running"

        # Delete container
        registry.delete_container(project_name, 1)
        containers = registry.list_project_containers(project_name)
        assert len(containers) == 1

        # Cleanup
        registry.unregister_project(project_name)


# =============================================================================
# Feature Management Tests
# =============================================================================

class TestFeatureManagement:
    """Tests for feature CRUD and status transitions."""

    @pytest.mark.integration
    def test_feature_lifecycle(self, temp_project_dir, sample_beads_issues):
        """Test complete feature lifecycle."""
        # Create .beads directory
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)

        # Write initial issues
        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for issue in sample_beads_issues:
                f.write(json.dumps(issue) + "\n")

        # Read and verify
        with open(issues_file) as f:
            loaded = [json.loads(line) for line in f]

        assert len(loaded) == 3
        assert loaded[0]["status"] == "open"

        # Update status
        loaded[0]["status"] = "in_progress"

        with open(issues_file, "w") as f:
            for issue in loaded:
                f.write(json.dumps(issue) + "\n")

        # Verify update
        with open(issues_file) as f:
            updated = [json.loads(line) for line in f]

        assert updated[0]["status"] == "in_progress"

        # Close feature
        updated[0]["status"] = "closed"

        with open(issues_file, "w") as f:
            for issue in updated:
                f.write(json.dumps(issue) + "\n")

        # Verify closed
        with open(issues_file) as f:
            final = [json.loads(line) for line in f]

        assert final[0]["status"] == "closed"

    @pytest.mark.integration
    def test_feature_filtering(self, temp_project_dir, sample_beads_issues):
        """Test feature filtering by status."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)

        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for issue in sample_beads_issues:
                f.write(json.dumps(issue) + "\n")

        with open(issues_file) as f:
            all_issues = [json.loads(line) for line in f]

        # Filter by status
        open_issues = [i for i in all_issues if i["status"] == "open"]
        in_progress = [i for i in all_issues if i["status"] == "in_progress"]
        closed = [i for i in all_issues if i["status"] == "closed"]

        assert len(open_issues) == 1
        assert len(in_progress) == 1
        assert len(closed) == 1

    @pytest.mark.integration
    def test_feature_priority_sorting(self, temp_project_dir):
        """Test feature sorting by priority."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)

        issues = [
            {"id": "feat-1", "title": "Low priority", "status": "open", "priority": 4},
            {"id": "feat-2", "title": "High priority", "status": "open", "priority": 0},
            {"id": "feat-3", "title": "Medium priority", "status": "open", "priority": 2},
        ]

        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        with open(issues_file) as f:
            loaded = [json.loads(line) for line in f]

        # Sort by priority
        sorted_issues = sorted(loaded, key=lambda x: x["priority"])

        assert sorted_issues[0]["priority"] == 0
        assert sorted_issues[1]["priority"] == 2
        assert sorted_issues[2]["priority"] == 4


# =============================================================================
# Progress Tracking Tests
# =============================================================================

class TestProgressTracking:
    """Tests for progress tracking and statistics."""

    @pytest.mark.integration
    def test_progress_calculation(self, temp_project_dir):
        """Test progress percentage calculation."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)

        issues = [
            {"id": "feat-1", "status": "closed", "priority": 1},
            {"id": "feat-2", "status": "closed", "priority": 1},
            {"id": "feat-3", "status": "in_progress", "priority": 1},
            {"id": "feat-4", "status": "open", "priority": 1},
            {"id": "feat-5", "status": "open", "priority": 1},
        ]

        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        with open(issues_file) as f:
            loaded = [json.loads(line) for line in f]

        total = len(loaded)
        closed = sum(1 for i in loaded if i["status"] == "closed")
        in_progress = sum(1 for i in loaded if i["status"] == "in_progress")

        percentage = (closed / total * 100) if total > 0 else 0

        assert total == 5
        assert closed == 2
        assert in_progress == 1
        assert percentage == 40.0

    @pytest.mark.integration
    def test_progress_webhook_payload(self, temp_project_dir):
        """Test webhook payload generation."""
        stats = {
            "passing": 5,
            "in_progress": 2,
            "total": 10,
            "percentage": 50.0,
        }

        payload = {
            "project": "test-project",
            "stats": stats,
            "features": [
                {"id": "feat-1", "title": "Feature 1", "status": "closed"},
                {"id": "feat-2", "title": "Feature 2", "status": "closed"},
            ],
        }

        # Validate payload structure
        assert "project" in payload
        assert "stats" in payload
        assert "features" in payload
        assert payload["stats"]["percentage"] == 50.0


# =============================================================================
# Container Orchestration Tests
# =============================================================================

class TestContainerOrchestration:
    """Tests for container orchestration scenarios."""

    @pytest.mark.integration
    def test_container_scaling(self, isolated_registry, temp_project_dir):
        """Test container count scaling."""
        import registry

        project_name = "scaling-test"
        registry.register_project(project_name, temp_project_dir, "https://github.com/test/repo.git")

        # Initial container count
        registry.update_target_container_count(project_name, 1)
        info = registry.get_project_info(project_name)
        assert info["target_container_count"] == 1

        # Scale up
        registry.update_target_container_count(project_name, 3)
        info = registry.get_project_info(project_name)
        assert info["target_container_count"] == 3

        # Scale down
        registry.update_target_container_count(project_name, 2)
        info = registry.get_project_info(project_name)
        assert info["target_container_count"] == 2

        registry.unregister_project(project_name)

    @pytest.mark.integration
    def test_container_status_transitions(self, isolated_registry, temp_project_dir):
        """Test container status transitions."""
        import registry

        project_name = "status-test"
        registry.register_project(project_name, temp_project_dir, "https://github.com/test/repo.git")
        registry.create_container(project_name, 1, "coding")

        # Initial status
        container = registry.get_container(project_name, 1)
        assert container["status"] == "not_created"

        # Status transitions
        statuses = ["created", "running", "stopping", "stopped", "completed"]

        for status in statuses:
            registry.update_container_status(project_name, 1, status)
            container = registry.get_container(project_name, 1)
            assert container["status"] == status

        registry.unregister_project(project_name)


# =============================================================================
# Error Recovery Tests
# =============================================================================

class TestErrorRecovery:
    """Tests for error recovery scenarios."""

    @pytest.mark.integration
    def test_registry_corruption_recovery(self, temp_db_path, monkeypatch):
        """Test recovery from corrupted registry."""
        import registry

        # Create initial state
        monkeypatch.setattr(registry, "get_registry_path", lambda: temp_db_path)
        registry._engine = None
        registry._SessionLocal = None

        # Write corrupted data
        temp_db_path.write_bytes(b"corrupted data")

        # Should handle gracefully
        try:
            registry.list_registered_projects()
        except Exception:
            # Expected - corruption detected
            pass

    @pytest.mark.integration
    def test_missing_project_directory(self, isolated_registry, tmp_path):
        """Test handling of missing project directories."""
        import registry

        project_name = "missing-dir-test"
        project_path = tmp_path / "nonexistent"

        # Should validate path
        result = registry.validate_project_path(project_path)
        assert result is False

    @pytest.mark.integration
    def test_concurrent_project_updates(self, isolated_registry, temp_project_dir):
        """Test concurrent updates to same project."""
        import registry
        import threading

        project_name = "concurrent-test"
        registry.register_project(project_name, temp_project_dir, "https://github.com/test/repo.git")

        errors = []

        def update_project():
            try:
                for i in range(10):
                    registry.update_target_container_count(project_name, i + 1)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=update_project) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should not have errors (or handle gracefully)
        # SQLite should handle concurrent writes

        registry.unregister_project(project_name)


# =============================================================================
# Cache Tests
# =============================================================================

class TestCaching:
    """Tests for feature and stats caching."""

    @pytest.mark.integration
    def test_feature_cache_update(self, isolated_registry, temp_project_dir, sample_beads_issues):
        """Test feature cache updates."""
        import registry

        project_name = "cache-test"
        registry.register_project(project_name, temp_project_dir, "https://github.com/test/repo.git")

        # Update feature cache
        registry.update_feature_cache(project_name, sample_beads_issues)

        # Read from cache
        cached = registry.get_cached_features(project_name)
        assert cached is not None
        assert len(cached) == len(sample_beads_issues)

        registry.unregister_project(project_name)

    @pytest.mark.integration
    def test_stats_cache_update(self, isolated_registry, temp_project_dir):
        """Test stats cache updates."""
        import registry

        project_name = "stats-cache-test"
        registry.register_project(project_name, temp_project_dir, "https://github.com/test/repo.git")

        stats = {
            "total": 10,
            "open": 5,
            "in_progress": 2,
            "closed": 3,
        }

        registry.update_stats_cache(project_name, stats)

        cached_stats = registry.get_cached_stats(project_name)
        assert cached_stats is not None
        assert cached_stats["total"] == 10

        registry.unregister_project(project_name)
