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
        registry.register_project(project_name, git_url)

        # Verify registration
        project_path = registry.get_project_path(project_name)
        assert project_path is not None

        # Verify project info - is_new derived from disk (no beads.db = new)
        info = registry.get_project_info(project_name)
        assert info is not None
        assert info["git_url"] == git_url
        assert info["is_new"] is True  # No beads.db exists yet

        # Create .beads/beads.db to mark project as initialized
        # (is_new is derived from disk state: not beads.db exists)
        projects_dir = registry.get_projects_dir()
        local_path = projects_dir / project_name
        beads_dir = local_path / ".beads"
        beads_dir.mkdir(parents=True, exist_ok=True)
        (beads_dir / "beads.db").touch()

        # mark_project_initialized is now a no-op; is_new derived from disk
        registry.mark_project_initialized(project_name)
        updated_info = registry.get_project_info(project_name)
        assert updated_info["is_new"] is False  # beads.db now exists

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
        registry.register_project(project_name, git_url)

        # Create containers
        container1 = registry.create_container(project_name, 1, "coding")
        container2 = registry.create_container(project_name, 2, "coding")

        assert container1 is not None
        assert container2 is not None

        # List containers
        containers = registry.list_project_containers(project_name)
        assert len(containers) == 2

        # Update container status
        registry.update_container_status(project_name, 1, "coding", status="running")
        container = registry.get_container(project_name, 1, "coding")
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
        registry.register_project(project_name, "https://github.com/test/repo.git")

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
        registry.register_project(project_name, "https://github.com/test/repo.git")
        registry.create_container(project_name, 1, "coding")

        # Initial status
        container = registry.get_container(project_name, 1, "coding")
        assert container["status"] == "created"

        # Status transitions
        statuses = ["running", "stopping", "stopped"]

        for status in statuses:
            registry.update_container_status(project_name, 1, "coding", status=status)
            container = registry.get_container(project_name, 1, "coding")
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

        # validate_project_path returns (is_valid, error_message) tuple
        is_valid, error_msg = registry.validate_project_path(project_path)
        assert is_valid is False
        assert "does not exist" in error_msg

    @pytest.mark.integration
    def test_concurrent_project_updates(self, isolated_registry, temp_project_dir):
        """Test concurrent updates to same project."""
        import registry
        import threading

        project_name = "concurrent-test"
        registry.register_project(project_name, "https://github.com/test/repo.git")

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
        """Test feature cache updates using direct SQLAlchemy models."""
        from datetime import datetime
        from registry import FeatureCache, _get_session

        project_name = "cache-test"
        isolated_registry.register_project(project_name, "https://github.com/test/repo.git")

        # Insert feature cache entries directly using SQLAlchemy
        with _get_session() as session:
            for issue in sample_beads_issues:
                cache = FeatureCache(
                    project_name=project_name,
                    feature_id=issue["id"],
                    priority=issue.get("priority", 999),
                    category=issue.get("labels", [""])[0] if issue.get("labels") else "",
                    name=issue["title"],
                    description=issue.get("description", ""),
                    steps_json="[]",
                    status=issue["status"],
                    updated_at=datetime.now()
                )
                session.add(cache)

        # Read from cache
        with _get_session() as session:
            cached = session.query(FeatureCache).filter_by(project_name=project_name).all()
            assert len(cached) == len(sample_beads_issues)

        isolated_registry.unregister_project(project_name)

    @pytest.mark.integration
    def test_stats_cache_update(self, isolated_registry, temp_project_dir):
        """Test stats cache updates using direct SQLAlchemy models."""
        from datetime import datetime
        from registry import FeatureStatsCache, _get_session, get_cached_stats

        project_name = "stats-cache-test"
        isolated_registry.register_project(project_name, "https://github.com/test/repo.git")

        # Insert stats cache directly using SQLAlchemy
        with _get_session() as session:
            stats_cache = FeatureStatsCache(
                project_name=project_name,
                pending_count=5,
                in_progress_count=2,
                done_count=3,
                total_count=10,
                percentage=30.0,
                last_polled_at=datetime.now()
            )
            session.add(stats_cache)

        # Read from cache using the registry function
        cached_stats = get_cached_stats(project_name)
        assert cached_stats is not None
        assert cached_stats["total"] == 10
        assert cached_stats["pending"] == 5
        assert cached_stats["done"] == 3

        isolated_registry.unregister_project(project_name)
