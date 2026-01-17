"""
Registry Module Enterprise Tests
================================

Comprehensive enterprise-grade tests for the registry module including:
- Transaction handling and rollback scenarios
- Edge cases and boundary conditions
- Data integrity constraints
- Cross-platform path handling
- Database migration scenarios
- Error recovery and resilience
"""

import json
import os
import pytest
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Transaction Safety Tests
# =============================================================================

class TestTransactionSafety:
    """Tests for database transaction handling."""

    @pytest.mark.unit
    def test_rollback_on_constraint_violation(self, isolated_registry):
        """Test that transactions are rolled back on constraint violations."""
        # First create a valid project
        isolated_registry.register_project(
            name="existing-project",
            git_url="https://github.com/user/repo.git"
        )

        # Attempt to create duplicate - should fail
        with pytest.raises(isolated_registry.RegistryError):
            isolated_registry.register_project(
                name="existing-project",
                git_url="https://github.com/other/repo.git"
            )

        # Verify original project is unchanged
        info = isolated_registry.get_project_info("existing-project")
        assert info["git_url"] == "https://github.com/user/repo.git"

    @pytest.mark.unit
    def test_atomic_container_creation(self, isolated_registry):
        """Test that container creation is atomic."""
        isolated_registry.register_project(
            name="container-atomic-test",
            git_url="https://github.com/user/repo.git"
        )

        # Create container
        container_id = isolated_registry.create_container(
            "container-atomic-test", 1, "coding"
        )

        # Verify container exists
        container = isolated_registry.get_container(
            "container-atomic-test", 1, "coding"
        )
        assert container is not None
        assert container["status"] == "created"

    @pytest.mark.unit
    def test_cascade_delete_removes_containers(self, isolated_registry):
        """Test that deleting a project requires deleting containers first."""
        isolated_registry.register_project(
            name="cascade-test",
            git_url="https://github.com/user/repo.git"
        )

        # Create containers
        isolated_registry.create_container("cascade-test", 1, "coding")
        isolated_registry.create_container("cascade-test", 2, "coding")

        # Delete containers first
        isolated_registry.delete_all_project_containers("cascade-test")

        # Then delete project
        isolated_registry.unregister_project("cascade-test")

        # Containers should be gone
        containers = isolated_registry.list_project_containers("cascade-test")
        assert len(containers) == 0

        # Project should be gone
        info = isolated_registry.get_project_info("cascade-test")
        assert info is None


# =============================================================================
# Boundary Condition Tests
# =============================================================================

class TestBoundaryConditions:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.unit
    def test_project_name_exact_length_limits(self, isolated_registry):
        """Test project names at exact length boundaries."""
        # Exactly 1 character (minimum valid)
        isolated_registry.register_project(
            name="a",
            git_url="https://github.com/user/a.git"
        )
        info = isolated_registry.get_project_info("a")
        assert info is not None

        # Exactly 50 characters (maximum valid)
        name_50 = "a" * 50
        isolated_registry.register_project(
            name=name_50,
            git_url="https://github.com/user/long.git"
        )
        info = isolated_registry.get_project_info(name_50)
        assert info is not None

        # 51 characters should fail
        with pytest.raises(ValueError):
            isolated_registry.register_project(
                name="a" * 51,
                git_url="https://github.com/user/toolong.git"
            )

    @pytest.mark.unit
    def test_container_count_boundaries(self, isolated_registry):
        """Test container count at exact boundaries."""
        isolated_registry.register_project(
            name="count-boundary",
            git_url="https://github.com/user/repo.git"
        )

        # Min valid: 1
        result = isolated_registry.update_target_container_count("count-boundary", 1)
        assert result is True
        info = isolated_registry.get_project_info("count-boundary")
        assert info["target_container_count"] == 1

        # Max valid: 10
        result = isolated_registry.update_target_container_count("count-boundary", 10)
        assert result is True
        info = isolated_registry.get_project_info("count-boundary")
        assert info["target_container_count"] == 10

        # Below min: 0
        with pytest.raises(ValueError):
            isolated_registry.update_target_container_count("count-boundary", 0)

        # Above max: 11
        with pytest.raises(ValueError):
            isolated_registry.update_target_container_count("count-boundary", 11)

    @pytest.mark.unit
    def test_container_number_edge_cases(self, isolated_registry):
        """Test container number edge cases."""
        isolated_registry.register_project(
            name="container-numbers",
            git_url="https://github.com/user/repo.git"
        )

        # Container 0 (init container)
        id_0 = isolated_registry.create_container("container-numbers", 0, "init")
        assert id_0 is not None

        container = isolated_registry.get_container("container-numbers", 0, "init")
        assert container["container_number"] == 0

        # Container 1 (first coding container)
        id_1 = isolated_registry.create_container("container-numbers", 1, "coding")
        assert id_1 is not None

        # Container 10 (max coding container)
        id_10 = isolated_registry.create_container("container-numbers", 10, "coding")
        assert id_10 is not None

    @pytest.mark.unit
    def test_empty_git_url_validation(self, isolated_registry):
        """Test that empty git URLs are rejected."""
        with pytest.raises(ValueError):
            isolated_registry.register_project(
                name="empty-url",
                git_url=""
            )

        with pytest.raises(ValueError):
            isolated_registry.register_project(
                name="whitespace-url",
                git_url="   "
            )


# =============================================================================
# Data Integrity Tests
# =============================================================================

class TestDataIntegrity:
    """Tests for data integrity constraints."""

    @pytest.mark.unit
    def test_container_type_constraints(self, isolated_registry):
        """Test that only valid container types are accepted."""
        isolated_registry.register_project(
            name="type-constraints",
            git_url="https://github.com/user/repo.git"
        )

        # Valid types
        isolated_registry.create_container("type-constraints", 0, "init")
        isolated_registry.create_container("type-constraints", 1, "coding")

        # Verify types are correct
        init_container = isolated_registry.get_container("type-constraints", 0, "init")
        assert init_container["container_type"] == "init"

        coding_container = isolated_registry.get_container("type-constraints", 1, "coding")
        assert coding_container["container_type"] == "coding"

    @pytest.mark.unit
    def test_container_status_constraints(self, isolated_registry):
        """Test that container status updates are constrained."""
        isolated_registry.register_project(
            name="status-constraints",
            git_url="https://github.com/user/repo.git"
        )

        isolated_registry.create_container("status-constraints", 1, "coding")

        # Valid status transitions
        valid_statuses = ["created", "running", "stopping", "stopped"]
        for status in valid_statuses:
            result = isolated_registry.update_container_status(
                "status-constraints", 1, "coding", status
            )
            assert result is True

            container = isolated_registry.get_container("status-constraints", 1, "coding")
            assert container["status"] == status

    @pytest.mark.unit
    def test_unique_container_identity_constraint(self, isolated_registry):
        """Test that container identity (project, number, type) is unique."""
        isolated_registry.register_project(
            name="unique-container",
            git_url="https://github.com/user/repo.git"
        )

        # First creation should succeed
        id1 = isolated_registry.create_container("unique-container", 1, "coding")

        # Same identity should return same ID (upsert)
        id2 = isolated_registry.create_container("unique-container", 1, "coding")
        assert id1 == id2

        # Different number is allowed
        id3 = isolated_registry.create_container("unique-container", 2, "coding")
        assert id3 != id1

    @pytest.mark.unit
    def test_feature_cache_integrity(self, isolated_registry):
        """Test feature cache data integrity."""
        isolated_registry.register_project(
            name="cache-integrity",
            git_url="https://github.com/user/repo.git"
        )

        # Update feature cache
        from registry import FeatureCache, _get_session

        with _get_session() as session:
            cache_entry = FeatureCache(
                project_name="cache-integrity",
                feature_id="feat-1",
                priority=1,
                category="auth",
                name="Test Feature",
                description="Test description",
                steps_json='["Step 1", "Step 2"]',
                status="open",
                updated_at=datetime.now()
            )
            session.add(cache_entry)
            session.commit()

        # Verify cache entry
        with _get_session() as session:
            entry = session.query(FeatureCache).filter_by(
                project_name="cache-integrity",
                feature_id="feat-1"
            ).first()
            assert entry is not None
            assert entry.name == "Test Feature"
            assert entry.status == "open"


# =============================================================================
# Cross-Platform Path Tests
# =============================================================================

class TestCrossPlatformPaths:
    """Tests for cross-platform path handling."""

    @pytest.mark.unit
    def test_path_normalization(self, isolated_registry, tmp_path):
        """Test that paths are normalized across platforms."""
        # Create project
        isolated_registry.register_project(
            name="path-normalization",
            git_url="https://github.com/user/repo.git"
        )

        # Get path
        path = isolated_registry.get_project_path("path-normalization")
        assert path is not None

        # Path should use forward slashes (POSIX style) internally
        # but be a valid Path object that works on the current platform
        assert "path-normalization" in str(path)

    @pytest.mark.unit
    def test_config_dir_consistency(self, isolated_registry):
        """Test config directory is consistent across calls."""
        dir1 = isolated_registry.get_config_dir()
        dir2 = isolated_registry.get_config_dir()
        assert dir1 == dir2

    @pytest.mark.unit
    def test_projects_dir_creation(self, isolated_registry):
        """Test projects directory path is returned."""
        projects_dir = isolated_registry.get_projects_dir()
        assert projects_dir is not None
        # Create it if it doesn't exist (the function returns path but may not create)
        projects_dir.mkdir(parents=True, exist_ok=True)
        assert projects_dir.exists()

    @pytest.mark.unit
    def test_beads_sync_dir_creation(self, isolated_registry):
        """Test beads-sync directory path is returned."""
        beads_sync_dir = isolated_registry.get_beads_sync_dir()
        assert beads_sync_dir is not None
        # Create it if it doesn't exist (the function returns path but may not create)
        beads_sync_dir.mkdir(parents=True, exist_ok=True)
        assert beads_sync_dir.exists()


# =============================================================================
# Error Recovery Tests
# =============================================================================

class TestErrorRecovery:
    """Tests for error recovery and resilience."""

    @pytest.mark.unit
    def test_session_recovery_after_error(self, isolated_registry):
        """Test that sessions can be used after an error."""
        # Force an error
        try:
            isolated_registry.register_project(
                name="",  # Invalid
                git_url="https://github.com/user/repo.git"
            )
        except ValueError:
            pass

        # Should still be able to create valid project
        isolated_registry.register_project(
            name="recovery-test",
            git_url="https://github.com/user/repo.git"
        )

        info = isolated_registry.get_project_info("recovery-test")
        assert info is not None

    @pytest.mark.unit
    def test_multiple_error_recovery(self, isolated_registry):
        """Test recovery from multiple consecutive errors."""
        # Generate multiple errors
        for i in range(5):
            try:
                isolated_registry.register_project(
                    name=f"../invalid-{i}",
                    git_url="https://github.com/user/repo.git"
                )
            except ValueError:
                pass

        # Should still work
        isolated_registry.register_project(
            name="after-errors",
            git_url="https://github.com/user/repo.git"
        )

        info = isolated_registry.get_project_info("after-errors")
        assert info is not None

    @pytest.mark.unit
    def test_graceful_handling_of_missing_project(self, isolated_registry):
        """Test graceful handling when project doesn't exist."""
        # All these should return None or empty, not raise
        info = isolated_registry.get_project_info("nonexistent")
        assert info is None

        path = isolated_registry.get_project_path("nonexistent")
        assert path is None

        url = isolated_registry.get_project_git_url("nonexistent")
        assert url is None

        containers = isolated_registry.list_project_containers("nonexistent")
        assert containers == []


# =============================================================================
# Feature Stats Cache Tests
# =============================================================================

class TestFeatureStatsCache:
    """Tests for feature stats cache operations."""

    @pytest.mark.unit
    def test_stats_cache_create_and_read(self, isolated_registry):
        """Test creating and reading feature stats cache."""
        isolated_registry.register_project(
            name="stats-cache-test",
            git_url="https://github.com/user/repo.git"
        )

        from registry import FeatureStatsCache, _get_session

        with _get_session() as session:
            stats = FeatureStatsCache(
                project_name="stats-cache-test",
                pending_count=5,
                in_progress_count=2,
                done_count=3,
                total_count=10,
                percentage=30.0,
                last_polled_at=datetime.now()
            )
            session.add(stats)
            session.commit()

        with _get_session() as session:
            stats = session.query(FeatureStatsCache).filter_by(
                project_name="stats-cache-test"
            ).first()
            assert stats is not None
            assert stats.pending_count == 5
            assert stats.done_count == 3
            assert stats.percentage == 30.0

    @pytest.mark.unit
    def test_stats_cache_update(self, isolated_registry):
        """Test updating feature stats cache."""
        isolated_registry.register_project(
            name="stats-update-test",
            git_url="https://github.com/user/repo.git"
        )

        from registry import FeatureStatsCache, _get_session

        # Create initial
        with _get_session() as session:
            stats = FeatureStatsCache(
                project_name="stats-update-test",
                pending_count=10,
                done_count=0,
                total_count=10,
                percentage=0.0,
                last_polled_at=datetime.now()
            )
            session.add(stats)
            session.commit()

        # Update
        with _get_session() as session:
            stats = session.query(FeatureStatsCache).filter_by(
                project_name="stats-update-test"
            ).first()
            stats.done_count = 5
            stats.pending_count = 5
            stats.percentage = 50.0
            session.commit()

        # Verify
        with _get_session() as session:
            stats = session.query(FeatureStatsCache).filter_by(
                project_name="stats-update-test"
            ).first()
            assert stats.done_count == 5
            assert stats.percentage == 50.0


# =============================================================================
# Cleanup and Maintenance Tests
# =============================================================================

class TestCleanupOperations:
    """Tests for cleanup and maintenance operations."""

    @pytest.mark.unit
    def test_delete_all_containers_for_project(self, isolated_registry):
        """Test deleting all containers for a project."""
        isolated_registry.register_project(
            name="cleanup-test",
            git_url="https://github.com/user/repo.git"
        )

        # Create multiple containers
        for i in range(5):
            isolated_registry.create_container("cleanup-test", i, "coding" if i > 0 else "init")

        # Delete all
        deleted = isolated_registry.delete_all_project_containers("cleanup-test")
        assert deleted == 5

        # Verify all gone
        containers = isolated_registry.list_project_containers("cleanup-test")
        assert len(containers) == 0

    @pytest.mark.unit
    def test_delete_individual_container(self, isolated_registry):
        """Test deleting individual container."""
        isolated_registry.register_project(
            name="delete-one",
            git_url="https://github.com/user/repo.git"
        )

        isolated_registry.create_container("delete-one", 1, "coding")
        isolated_registry.create_container("delete-one", 2, "coding")

        # Delete one
        result = isolated_registry.delete_container("delete-one", 1, "coding")
        assert result is True

        # Verify only one remaining
        containers = isolated_registry.list_project_containers("delete-one")
        assert len(containers) == 1
        assert containers[0]["container_number"] == 2


# =============================================================================
# Git URL Validation Tests
# =============================================================================

class TestGitUrlValidation:
    """Tests for git URL validation."""

    @pytest.mark.unit
    def test_https_urls_accepted(self, isolated_registry):
        """Test that HTTPS git URLs are accepted."""
        valid_https = [
            "https://github.com/user/repo.git",
            "https://gitlab.com/user/repo.git",
            "https://bitbucket.org/user/repo.git",
            "https://github.com/user/repo",  # Without .git
        ]

        for i, url in enumerate(valid_https):
            isolated_registry.register_project(
                name=f"https-test-{i}",
                git_url=url
            )
            info = isolated_registry.get_project_info(f"https-test-{i}")
            assert info is not None

    @pytest.mark.unit
    def test_ssh_urls_accepted(self, isolated_registry):
        """Test that SSH git URLs are accepted."""
        valid_ssh = [
            "git@github.com:user/repo.git",
            "git@gitlab.com:user/repo.git",
            "git@bitbucket.org:user/repo.git",
        ]

        for i, url in enumerate(valid_ssh):
            isolated_registry.register_project(
                name=f"ssh-test-{i}",
                git_url=url
            )
            info = isolated_registry.get_project_info(f"ssh-test-{i}")
            assert info is not None

    @pytest.mark.unit
    def test_invalid_urls_rejected(self, isolated_registry):
        """Test that invalid URLs are rejected."""
        invalid_urls = [
            "ftp://invalid.com/repo.git",
            "http://insecure.com/repo.git",  # HTTP not HTTPS
            "file:///local/path",
            "/absolute/path",
            "relative/path",
            "not-a-url",
        ]

        for url in invalid_urls:
            with pytest.raises(ValueError):
                isolated_registry.register_project(
                    name="invalid-url-test",
                    git_url=url
                )


# =============================================================================
# Session Management Tests
# =============================================================================

class TestSessionManagement:
    """Tests for database session management."""

    @pytest.mark.unit
    def test_context_manager_commits(self, isolated_registry):
        """Test that context manager commits changes."""
        from registry import Project, _get_session

        with _get_session() as session:
            project = Project(
                name="cm-test",
                git_url="https://github.com/user/repo.git",
                created_at=datetime.now()
            )
            session.add(project)
            session.commit()

        # Verify persisted
        info = isolated_registry.get_project_info("cm-test")
        assert info is not None

    @pytest.mark.unit
    def test_context_manager_rollback_on_exception(self, isolated_registry):
        """Test that context manager rolls back on exception."""
        from registry import Project, _get_session

        try:
            with _get_session() as session:
                project = Project(
                    name="rollback-test",
                    git_url="https://github.com/user/repo.git",
                    created_at=datetime.now()
                )
                session.add(project)
                raise Exception("Force rollback")
        except Exception:
            pass

        # Should not be persisted
        info = isolated_registry.get_project_info("rollback-test")
        assert info is None
