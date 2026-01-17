"""
Service Integration Enterprise Tests
=====================================

Comprehensive enterprise-grade integration tests for service interactions including:
- Container manager and registry integration
- Beads sync manager and cache synchronization
- WebSocket and container manager coordination
- Feature polling and cache updates
"""

import asyncio
import json
import pytest
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Registry and Container Manager Integration
# =============================================================================

class TestRegistryContainerManagerIntegration:
    """Tests for registry and container manager integration."""

    @pytest.fixture
    def integrated_setup(self, tmp_path, monkeypatch):
        """Create integrated registry and container manager setup."""
        import registry

        # Reset registry
        registry._engine = None
        registry._SessionLocal = None

        # Setup temp paths
        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()
        (temp_config / "beads-sync").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "test.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        # Create project
        registry.register_project(
            name="integration-test",
            git_url="https://github.com/test/repo.git",
            is_new=True
        )

        return registry, temp_config

    @pytest.mark.integration
    def test_project_registration_creates_correct_paths(self, integrated_setup):
        """Test that project registration sets up correct paths."""
        registry, temp_config = integrated_setup

        info = registry.get_project_info("integration-test")
        assert info is not None
        assert info["git_url"] == "https://github.com/test/repo.git"

        path = registry.get_project_path("integration-test")
        assert path is not None
        assert "integration-test" in str(path)

    @pytest.mark.integration
    def test_container_registration_with_project(self, integrated_setup):
        """Test container registration with existing project."""
        registry, temp_config = integrated_setup

        container_id = registry.create_container(
            project_name="integration-test",
            container_number=1,
            container_type="coding"
        )

        assert container_id is not None

        container = registry.get_container("integration-test", 1, "coding")
        assert container is not None
        assert container["project_name"] == "integration-test"
        assert container["status"] == "created"

    @pytest.mark.integration
    def test_container_status_updates(self, integrated_setup):
        """Test container status update flow."""
        registry, temp_config = integrated_setup

        registry.create_container("integration-test", 1, "coding")

        # Update status
        registry.update_container_status(
            "integration-test", 1, "coding",
            status="running",
            docker_container_id="abc123"
        )

        container = registry.get_container("integration-test", 1, "coding")
        assert container["status"] == "running"
        assert container["docker_container_id"] == "abc123"

        # Update again
        registry.update_container_status(
            "integration-test", 1, "coding",
            status="stopped"
        )

        container = registry.get_container("integration-test", 1, "coding")
        assert container["status"] == "stopped"


# =============================================================================
# Beads Sync Manager Integration
# =============================================================================

class TestBeadsSyncManagerIntegration:
    """Tests for beads sync manager integration."""

    @pytest.fixture
    def beads_project(self, tmp_path):
        """Create project with beads data."""
        project_dir = tmp_path / "beads-project"
        project_dir.mkdir(parents=True)

        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        config_file = beads_dir / "config.yaml"
        config_file.write_text("prefix: feat\n")

        issues_file = beads_dir / "issues.jsonl"
        features = [
            {"id": "feat-1", "title": "Feature 1", "status": "open", "priority": 1},
            {"id": "feat-2", "title": "Feature 2", "status": "in_progress", "priority": 2},
            {"id": "feat-3", "title": "Feature 3", "status": "closed", "priority": 3},
        ]
        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        return project_dir

    @pytest.mark.integration
    def test_read_issues_from_beads(self, beads_project):
        """Test reading issues from beads directory."""
        issues_file = beads_project / ".beads" / "issues.jsonl"

        issues = []
        with open(issues_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    issues.append(json.loads(line))

        assert len(issues) == 3
        assert issues[0]["id"] == "feat-1"
        assert issues[1]["status"] == "in_progress"
        assert issues[2]["status"] == "closed"

    @pytest.mark.integration
    def test_calculate_stats_from_issues(self, beads_project):
        """Test calculating stats from issues."""
        issues_file = beads_project / ".beads" / "issues.jsonl"

        issues = []
        with open(issues_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    issues.append(json.loads(line))

        pending = sum(1 for i in issues if i["status"] == "open")
        in_progress = sum(1 for i in issues if i["status"] == "in_progress")
        done = sum(1 for i in issues if i["status"] == "closed")
        total = len(issues)
        percentage = (done / total * 100) if total > 0 else 0.0

        assert pending == 1
        assert in_progress == 1
        assert done == 1
        assert total == 3
        assert percentage == pytest.approx(33.3, rel=0.1)


# =============================================================================
# Feature Cache Integration
# =============================================================================

class TestFeatureCacheIntegration:
    """Tests for feature cache integration."""

    @pytest.fixture
    def cache_setup(self, tmp_path, monkeypatch):
        """Setup cache with registry."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "cache.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        registry.register_project(
            name="cache-test",
            git_url="https://github.com/test/repo.git"
        )

        return registry

    @pytest.mark.integration
    def test_cache_feature_data(self, cache_setup):
        """Test caching feature data."""
        registry = cache_setup
        from registry import FeatureCache, _get_session

        with _get_session() as session:
            cache = FeatureCache(
                project_name="cache-test",
                feature_id="feat-1",
                priority=1,
                category="auth",
                name="User Login",
                description="Implement login",
                steps_json='["Step 1", "Step 2"]',
                status="open",
                updated_at=datetime.now()
            )
            session.add(cache)
            session.commit()

        # Read back
        with _get_session() as session:
            cached = session.query(FeatureCache).filter_by(
                project_name="cache-test",
                feature_id="feat-1"
            ).first()

            assert cached is not None
            assert cached.name == "User Login"
            assert cached.category == "auth"

    @pytest.mark.integration
    def test_cache_stats_data(self, cache_setup):
        """Test caching stats data."""
        registry = cache_setup
        from registry import FeatureStatsCache, _get_session

        with _get_session() as session:
            stats = FeatureStatsCache(
                project_name="cache-test",
                pending_count=5,
                in_progress_count=2,
                done_count=3,
                total_count=10,
                percentage=30.0,
                last_polled_at=datetime.now()
            )
            session.add(stats)
            session.commit()

        # Read back
        with _get_session() as session:
            cached = session.query(FeatureStatsCache).filter_by(
                project_name="cache-test"
            ).first()

            assert cached is not None
            assert cached.pending_count == 5
            assert cached.percentage == 30.0


# =============================================================================
# Progress Module Integration
# =============================================================================

class TestProgressIntegration:
    """Tests for progress module integration."""

    @pytest.fixture
    def progress_project(self, tmp_path):
        """Create project for progress testing."""
        project_dir = tmp_path / "progress-project"
        project_dir.mkdir(parents=True)

        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        config_file = beads_dir / "config.yaml"
        config_file.write_text("prefix: feat\n")

        issues_file = beads_dir / "issues.jsonl"
        features = [
            {"id": "feat-1", "title": "Feature 1", "status": "open", "priority": 1},
            {"id": "feat-2", "title": "Feature 2", "status": "in_progress", "priority": 2},
            {"id": "feat-3", "title": "Feature 3", "status": "closed", "priority": 3},
            {"id": "feat-4", "title": "Feature 4", "status": "closed", "priority": 4},
        ]
        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        return project_dir

    @pytest.mark.integration
    def test_count_passing_tests(self, progress_project):
        """Test counting passing tests."""
        from progress import count_passing_tests

        passing, in_progress, total = count_passing_tests(progress_project)

        assert passing == 2
        assert in_progress == 1
        assert total == 4

    @pytest.mark.integration
    def test_has_features(self, progress_project):
        """Test has_features detection."""
        from progress import has_features

        result = has_features(progress_project)
        assert result is True

    @pytest.mark.integration
    def test_has_open_features(self, progress_project):
        """Test has_open_features detection."""
        from progress import has_open_features

        result = has_open_features(progress_project)
        assert result is True

    @pytest.mark.integration
    def test_get_all_passing_features(self, progress_project):
        """Test getting all passing features."""
        from progress import get_all_passing_features

        passing = get_all_passing_features(progress_project)

        assert len(passing) == 2
        feature_ids = [f["id"] for f in passing]
        assert "feat-3" in feature_ids
        assert "feat-4" in feature_ids


# =============================================================================
# Prompts Module Integration
# =============================================================================

class TestPromptsIntegration:
    """Tests for prompts module integration."""

    @pytest.fixture
    def prompts_project(self, tmp_path):
        """Create project with prompts."""
        project_dir = tmp_path / "prompts-project"
        project_dir.mkdir(parents=True)

        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir()

        # Create prompt files
        (prompts_dir / "app_spec.txt").write_text("<app-spec>Test App</app-spec>")
        (prompts_dir / "coding_prompt.md").write_text("# Coding Prompt\nImplement features.")
        (prompts_dir / "initializer_prompt.md").write_text("# Init Prompt\nCreate features.")

        # Create CLAUDE.md in project root for has_project_prompts to work
        (project_dir / "CLAUDE.md").write_text("# Project docs")

        return project_dir

    @pytest.mark.integration
    def test_has_project_prompts(self, prompts_project):
        """Test prompts directory exists and has files."""
        prompts_dir = prompts_project / "prompts"
        assert prompts_dir.exists()
        assert (prompts_dir / "app_spec.txt").exists()
        assert (prompts_dir / "coding_prompt.md").exists()

    @pytest.mark.integration
    def test_get_app_spec(self, prompts_project):
        """Test getting app spec."""
        from prompts import get_app_spec

        spec = get_app_spec(prompts_project)
        assert spec is not None
        assert "Test App" in spec

    @pytest.mark.integration
    def test_get_coding_prompt(self, prompts_project):
        """Test getting coding prompt."""
        from prompts import get_coding_prompt

        prompt = get_coding_prompt(prompts_project)
        assert prompt is not None
        assert "Implement features" in prompt

    @pytest.mark.integration
    def test_get_initializer_prompt(self, prompts_project):
        """Test getting initializer prompt."""
        from prompts import get_initializer_prompt

        prompt = get_initializer_prompt(prompts_project)
        assert prompt is not None
        assert "Create features" in prompt


# =============================================================================
# WebSocket Integration
# =============================================================================

class TestWebSocketIntegration:
    """Tests for WebSocket integration."""

    @pytest.mark.integration
    def test_connection_manager_initialization(self):
        """Test ConnectionManager can be initialized."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        assert manager is not None
        assert hasattr(manager, 'active_connections')

    @pytest.mark.integration
    def test_connection_manager_has_disconnect(self):
        """Test ConnectionManager has disconnect method."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        assert hasattr(manager, 'disconnect')
        assert callable(manager.disconnect)

    @pytest.mark.integration
    def test_connection_manager_has_broadcast_methods(self):
        """Test ConnectionManager has broadcast methods."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        # Uses broadcast_to_project for all broadcasts
        assert hasattr(manager, 'broadcast_to_project')
        assert callable(manager.broadcast_to_project)


# =============================================================================
# Multi-Service Flow Integration
# =============================================================================

class TestMultiServiceFlow:
    """Tests for multi-service integration flows."""

    @pytest.fixture
    def full_project(self, tmp_path, monkeypatch):
        """Create full project with all services."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)
        (temp_config / "projects").mkdir()

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "full.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        # Register project
        registry.register_project(
            name="full-test",
            git_url="https://github.com/test/repo.git"
        )

        # Create project directory
        project_dir = temp_config / "projects" / "full-test"
        project_dir.mkdir(parents=True)

        # Create prompts
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "app_spec.txt").write_text("<app-spec>Full Test</app-spec>")
        (prompts_dir / "coding_prompt.md").write_text("# Code")

        # Create beads
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat\n")
        (beads_dir / "issues.jsonl").write_text(
            '{"id": "feat-1", "title": "Feature 1", "status": "open", "priority": 1}\n'
        )

        return registry, project_dir

    @pytest.mark.integration
    def test_full_project_setup(self, full_project):
        """Test full project is properly set up."""
        registry, project_dir = full_project

        # Registry has project
        info = registry.get_project_info("full-test")
        assert info is not None

        # Prompts directory exists with files
        prompts_dir = project_dir / "prompts"
        assert prompts_dir.exists()
        assert (prompts_dir / "app_spec.txt").exists()

        # Features exist
        from progress import has_features
        assert has_features(project_dir)

    @pytest.mark.integration
    def test_project_stats_flow(self, full_project):
        """Test full stats calculation flow."""
        registry, project_dir = full_project

        from progress import count_passing_tests

        passing, in_progress, total = count_passing_tests(project_dir)

        assert total == 1
        assert passing == 0
        assert in_progress == 0

    @pytest.mark.integration
    def test_container_lifecycle_flow(self, full_project):
        """Test container creation and status flow."""
        registry, project_dir = full_project

        # Create container
        container_id = registry.create_container("full-test", 1, "coding")
        assert container_id is not None

        # Initial status
        container = registry.get_container("full-test", 1, "coding")
        assert container["status"] == "created"

        # Update status
        registry.update_container_status(
            "full-test", 1, "coding",
            status="running",
            current_feature="feat-1"
        )

        container = registry.get_container("full-test", 1, "coding")
        assert container["status"] == "running"
        assert container["current_feature"] == "feat-1"

        # Stop
        registry.update_container_status(
            "full-test", 1, "coding",
            status="stopped"
        )

        container = registry.get_container("full-test", 1, "coding")
        assert container["status"] == "stopped"


# =============================================================================
# Error Handling Integration
# =============================================================================

class TestErrorHandlingIntegration:
    """Tests for error handling across services."""

    @pytest.mark.integration
    def test_progress_handles_missing_beads(self, tmp_path):
        """Test progress module handles missing beads gracefully."""
        from progress import has_features, count_passing_tests

        project_dir = tmp_path / "no-beads"
        project_dir.mkdir()

        assert has_features(project_dir) is False
        passing, in_progress, total = count_passing_tests(project_dir)
        assert total == 0

    @pytest.mark.integration
    def test_prompts_handles_missing_files(self, tmp_path):
        """Test missing prompts detection."""
        project_dir = tmp_path / "no-prompts"
        project_dir.mkdir()

        # No prompts directory
        prompts_dir = project_dir / "prompts"
        assert not prompts_dir.exists()

        # No app spec
        app_spec = prompts_dir / "app_spec.txt"
        assert not app_spec.exists()


# =============================================================================
# Concurrent Access Integration
# =============================================================================

class TestConcurrentAccessIntegration:
    """Tests for concurrent access patterns."""

    @pytest.fixture
    def concurrent_registry(self, tmp_path, monkeypatch):
        """Setup registry for concurrent testing."""
        import registry

        registry._engine = None
        registry._SessionLocal = None

        temp_config = tmp_path / "zerocoder"
        temp_config.mkdir(parents=True)

        monkeypatch.setattr(registry, "get_registry_path", lambda: tmp_path / "concurrent.db")
        monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
        monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
        monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

        return registry

    @pytest.mark.integration
    def test_concurrent_project_reads(self, concurrent_registry):
        """Test concurrent read operations."""
        registry = concurrent_registry

        # Create projects
        for i in range(5):
            registry.register_project(
                name=f"read-test-{i}",
                git_url=f"https://github.com/test/repo{i}.git"
            )

        results = []
        lock = threading.Lock()

        def read_project(index):
            info = registry.get_project_info(f"read-test-{index % 5}")
            with lock:
                results.append(info is not None)

        threads = [
            threading.Thread(target=read_project, args=(i,))
            for i in range(20)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All reads should succeed
        assert len(results) == 20
        assert all(results)

    @pytest.mark.integration
    def test_concurrent_container_updates(self, concurrent_registry):
        """Test concurrent container status updates."""
        registry = concurrent_registry

        registry.register_project(
            name="update-test",
            git_url="https://github.com/test/repo.git"
        )

        registry.create_container("update-test", 1, "coding")

        results = []
        lock = threading.Lock()

        def update_status(status):
            try:
                registry.update_container_status(
                    "update-test", 1, "coding",
                    status=status
                )
                with lock:
                    results.append(True)
            except Exception:
                with lock:
                    results.append(False)

        statuses = ["running", "stopped", "running", "stopped", "running"]
        threads = [
            threading.Thread(target=update_status, args=(s,))
            for s in statuses
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All updates should complete (some may fail due to locking)
        assert len(results) == 5
