"""
Comprehensive BeadsSyncManager Tests
====================================

Enterprise-grade tests for the BeadsSyncManager service including:
- Clone operations
- Pull operations
- Task parsing and transformation
- Stats calculation
- Global manager registry
- Error handling
"""

import asyncio
import json
import pytest
import subprocess
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestBeadsSyncManagerInit:
    """Tests for BeadsSyncManager initialization."""

    @pytest.mark.unit
    def test_init_creates_manager(self, tmp_path, monkeypatch):
        """Test that BeadsSyncManager initializes correctly."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        manager = BeadsSyncManager(
            project_name="test-project",
            git_remote_url="https://github.com/user/repo.git"
        )

        assert manager.project_name == "test-project"
        assert manager.git_remote_url == "https://github.com/user/repo.git"
        assert manager.local_path == tmp_path / "projects" / "test-project"
        assert manager._last_pull is None

    @pytest.mark.unit
    def test_init_with_ssh_url(self, tmp_path, monkeypatch):
        """Test initialization with SSH git URL."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        manager = BeadsSyncManager(
            project_name="ssh-project",
            git_remote_url="git@github.com:user/repo.git"
        )

        assert manager.git_remote_url == "git@github.com:user/repo.git"


class TestBeadsSyncManagerClone:
    """Tests for project existence checks (formerly clone operations)."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ensure_cloned_already_exists(self, tmp_path, monkeypatch):
        """Test ensure_cloned when project directory already exists."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        # Create existing project directory
        project_path = tmp_path / "projects" / "test-project"
        project_path.mkdir(parents=True)
        (project_path / ".git").mkdir()

        manager = BeadsSyncManager(
            project_name="test-project",
            git_remote_url="https://github.com/user/repo.git"
        )

        success, message = await manager.ensure_cloned()

        assert success is True
        assert "exists" in message.lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ensure_cloned_not_exists(self, tmp_path, monkeypatch):
        """Test ensure_cloned when project directory doesn't exist."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        manager = BeadsSyncManager(
            project_name="test-project",
            git_remote_url="https://github.com/user/repo.git"
        )

        # Project directory doesn't exist
        success, message = await manager.ensure_cloned()

        assert success is False
        assert "not found" in message.lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ensure_cloned_exists_but_no_git(self, tmp_path, monkeypatch):
        """Test ensure_cloned when directory exists but is not a git repo."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        # Create directory without .git
        project_path = tmp_path / "projects" / "test-project"
        project_path.mkdir(parents=True)

        manager = BeadsSyncManager(
            project_name="test-project",
            git_remote_url="https://github.com/user/repo.git"
        )

        success, message = await manager.ensure_cloned()

        assert success is False
        assert "not found" in message.lower()


class TestBeadsSyncManagerPull:
    """Tests for pull operations."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_pull_latest_not_exists(self, tmp_path, monkeypatch):
        """Test pull when project directory doesn't exist returns error."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        manager = BeadsSyncManager(
            project_name="test-project",
            git_remote_url="https://github.com/user/repo.git"
        )

        # Directory doesn't exist
        success, message = await manager.pull_latest()

        assert success is False
        assert "does not exist" in message.lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_pull_latest_success(self, tmp_path, monkeypatch):
        """Test successful pull operation."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        # Create existing project directory
        project_path = tmp_path / "projects" / "test-project"
        project_path.mkdir(parents=True)

        manager = BeadsSyncManager(
            project_name="test-project",
            git_remote_url="https://github.com/user/repo.git"
        )

        mock_result = MagicMock(returncode=0, stdout="Already up to date.", stderr="")

        with patch("asyncio.to_thread", return_value=mock_result):
            success, message = await manager.pull_latest()

        assert success is True
        assert "Pulled successfully" in message
        assert manager._last_pull is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_pull_latest_fails_gracefully(self, tmp_path, monkeypatch):
        """Test pull fails gracefully when git pull fails (local changes or up-to-date)."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        # Create existing project directory
        project_path = tmp_path / "projects" / "test-project"
        project_path.mkdir(parents=True)

        manager = BeadsSyncManager(
            project_name="test-project",
            git_remote_url="https://github.com/user/repo.git"
        )

        # Pull fails - but we return success since local changes or up-to-date is OK
        mock_result = MagicMock(returncode=1, stdout="", stderr="Cannot fast-forward")

        with patch("asyncio.to_thread", return_value=mock_result):
            success, message = await manager.pull_latest()

        # New behavior: pull failures are treated gracefully
        assert success is True
        assert "skipped" in message.lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_pull_latest_timeout(self, tmp_path, monkeypatch):
        """Test pull timeout handling."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        # Create existing project directory
        project_path = tmp_path / "projects" / "test-project"
        project_path.mkdir(parents=True)

        manager = BeadsSyncManager(
            project_name="test-project",
            git_remote_url="https://github.com/user/repo.git"
        )

        with patch("asyncio.to_thread", side_effect=subprocess.TimeoutExpired("git", 30)):
            success, message = await manager.pull_latest()

        assert success is False
        assert "timed out" in message.lower()


class TestBeadsSyncManagerTasks:
    """Tests for task reading via bd CLI."""

    @pytest.mark.unit
    def test_get_tasks_no_beads_dir(self, tmp_path, monkeypatch):
        """Test get_tasks when .beads directory doesn't exist."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        # Create project directory without .beads
        project_path = tmp_path / "projects" / "test-project"
        project_path.mkdir(parents=True)

        manager = BeadsSyncManager(
            project_name="test-project",
            git_remote_url="https://github.com/user/repo.git"
        )

        tasks = manager.get_tasks()

        assert tasks == []

    @pytest.mark.unit
    def test_get_tasks_bd_cli_success(self, tmp_path, monkeypatch):
        """Test get_tasks with successful bd CLI output."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        # Create project with .beads directory
        project_path = tmp_path / "projects" / "test-project"
        beads_dir = project_path / ".beads"
        beads_dir.mkdir(parents=True)

        issues_data = [
            {"id": "feat-1", "title": "Feature 1", "status": "open", "priority": 0},
            {"id": "feat-2", "title": "Feature 2", "status": "closed", "priority": 1},
        ]

        manager = BeadsSyncManager(
            project_name="test-project",
            git_remote_url="https://github.com/user/repo.git"
        )

        mock_result = MagicMock(
            returncode=0,
            stdout=json.dumps(issues_data),
            stderr=""
        )

        with patch("subprocess.run", return_value=mock_result):
            tasks = manager.get_tasks()

        assert len(tasks) == 2
        assert tasks[0]["id"] == "feat-1"
        assert tasks[1]["status"] == "closed"

    @pytest.mark.unit
    def test_get_tasks_bd_cli_failure(self, tmp_path, monkeypatch):
        """Test get_tasks handles bd CLI failure gracefully."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        # Create project with .beads directory
        project_path = tmp_path / "projects" / "test-project"
        beads_dir = project_path / ".beads"
        beads_dir.mkdir(parents=True)

        manager = BeadsSyncManager(
            project_name="test-project",
            git_remote_url="https://github.com/user/repo.git"
        )

        mock_result = MagicMock(
            returncode=1,
            stdout="",
            stderr="bd: command failed"
        )

        with patch("subprocess.run", return_value=mock_result):
            tasks = manager.get_tasks()

        # bd CLI failure returns empty list
        assert tasks == []

    @pytest.mark.unit
    def test_get_tasks_bd_cli_timeout(self, tmp_path, monkeypatch):
        """Test get_tasks handles bd CLI timeout gracefully."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        # Create project with .beads directory
        project_path = tmp_path / "projects" / "test-project"
        beads_dir = project_path / ".beads"
        beads_dir.mkdir(parents=True)

        manager = BeadsSyncManager(
            project_name="test-project",
            git_remote_url="https://github.com/user/repo.git"
        )

        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("bd", 30)):
            tasks = manager.get_tasks()

        assert tasks == []

    @pytest.mark.unit
    def test_get_tasks_bd_cli_not_found(self, tmp_path, monkeypatch):
        """Test get_tasks handles bd CLI not found gracefully."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        # Create project with .beads directory
        project_path = tmp_path / "projects" / "test-project"
        beads_dir = project_path / ".beads"
        beads_dir.mkdir(parents=True)

        manager = BeadsSyncManager(
            project_name="test-project",
            git_remote_url="https://github.com/user/repo.git"
        )

        with patch("subprocess.run", side_effect=FileNotFoundError):
            tasks = manager.get_tasks()

        assert tasks == []


class TestBeadsSyncManagerStats:
    """Tests for stats calculation."""

    @pytest.mark.unit
    def test_get_stats_empty(self, tmp_path, monkeypatch):
        """Test get_stats with no tasks."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        manager = BeadsSyncManager(
            project_name="test-project",
            git_remote_url="https://github.com/user/repo.git"
        )

        # Mock empty result from bd CLI
        mock_result = MagicMock(returncode=0, stdout="[]", stderr="")

        with patch("subprocess.run", return_value=mock_result):
            stats = manager.get_stats()

        assert stats["open"] == 0
        assert stats["in_progress"] == 0
        assert stats["closed"] == 0
        assert stats["total"] == 0
        assert stats["percentage"] == 0.0

    @pytest.mark.unit
    def test_get_stats_mixed(self, tmp_path, monkeypatch):
        """Test get_stats with mixed task statuses."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        # Create project with .beads directory
        project_path = tmp_path / "projects" / "test-project"
        beads_dir = project_path / ".beads"
        beads_dir.mkdir(parents=True)

        issues_data = [
            {"id": "feat-1", "status": "open"},
            {"id": "feat-2", "status": "open"},
            {"id": "feat-3", "status": "in_progress"},
            {"id": "feat-4", "status": "closed"},
            {"id": "feat-5", "status": "closed"},
            {"id": "feat-6", "status": "closed"},
        ]

        manager = BeadsSyncManager(
            project_name="test-project",
            git_remote_url="https://github.com/user/repo.git"
        )

        mock_result = MagicMock(returncode=0, stdout=json.dumps(issues_data), stderr="")

        with patch("subprocess.run", return_value=mock_result):
            stats = manager.get_stats()

        assert stats["open"] == 2
        assert stats["in_progress"] == 1
        assert stats["closed"] == 3
        assert stats["total"] == 6
        assert stats["percentage"] == 50.0

    @pytest.mark.unit
    def test_get_tasks_by_status(self, tmp_path, monkeypatch):
        """Test get_tasks_by_status filtering."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import BeadsSyncManager

        # Create project with .beads directory
        project_path = tmp_path / "projects" / "test-project"
        beads_dir = project_path / ".beads"
        beads_dir.mkdir(parents=True)

        issues_data = [
            {"id": "feat-1", "status": "open"},
            {"id": "feat-2", "status": "open"},
            {"id": "feat-3", "status": "closed"},
        ]

        manager = BeadsSyncManager(
            project_name="test-project",
            git_remote_url="https://github.com/user/repo.git"
        )

        mock_result = MagicMock(returncode=0, stdout=json.dumps(issues_data), stderr="")

        with patch("subprocess.run", return_value=mock_result):
            open_tasks = manager.get_tasks_by_status("open")
            closed_tasks = manager.get_tasks_by_status("closed")
            in_progress_tasks = manager.get_tasks_by_status("in_progress")

        assert len(open_tasks) == 2
        assert len(closed_tasks) == 1
        assert len(in_progress_tasks) == 0


class TestGlobalManagerRegistry:
    """Tests for the global manager registry functions."""

    @pytest.mark.unit
    def test_get_beads_sync_manager_creates_new(self, tmp_path, monkeypatch):
        """Test get_beads_sync_manager creates new manager."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import (
            get_beads_sync_manager,
            _sync_managers,
        )

        # Clear existing managers
        _sync_managers.clear()

        manager = get_beads_sync_manager(
            "new-project",
            "https://github.com/user/repo.git"
        )

        assert manager is not None
        assert manager.project_name == "new-project"
        assert "new-project" in _sync_managers

    @pytest.mark.unit
    def test_get_beads_sync_manager_reuses_existing(self, tmp_path, monkeypatch):
        """Test get_beads_sync_manager reuses existing manager."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import (
            get_beads_sync_manager,
            _sync_managers,
        )

        # Clear existing managers
        _sync_managers.clear()

        manager1 = get_beads_sync_manager(
            "test-project",
            "https://github.com/user/repo.git"
        )

        manager2 = get_beads_sync_manager(
            "test-project",
            "https://github.com/user/repo.git"
        )

        assert manager1 is manager2

    @pytest.mark.unit
    def test_clear_beads_sync_manager(self, tmp_path, monkeypatch):
        """Test clear_beads_sync_manager removes manager."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import (
            get_beads_sync_manager,
            clear_beads_sync_manager,
            _sync_managers,
        )

        # Clear existing managers
        _sync_managers.clear()

        manager = get_beads_sync_manager(
            "test-project",
            "https://github.com/user/repo.git"
        )

        assert "test-project" in _sync_managers

        clear_beads_sync_manager("test-project")

        assert "test-project" not in _sync_managers

    @pytest.mark.unit
    def test_clear_nonexistent_manager(self, tmp_path, monkeypatch):
        """Test clear_beads_sync_manager handles nonexistent manager."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import (
            clear_beads_sync_manager,
            _sync_managers,
        )

        # Clear existing managers
        _sync_managers.clear()

        # Should not raise
        clear_beads_sync_manager("nonexistent")


class TestTasksToFeatures:
    """Tests for _tasks_to_features transformation."""

    @pytest.mark.unit
    def test_tasks_to_features_basic(self, tmp_path, monkeypatch):
        """Test basic task to feature transformation."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import _tasks_to_features

        tasks = [
            {
                "id": "feat-1",
                "title": "User Login",
                "status": "open",
                "priority": 0,
                "labels": ["auth"],
                "description": "1. Create form\n2. Add validation"
            }
        ]

        features = _tasks_to_features(tasks)

        assert len(features) == 1
        assert features[0]["id"] == "feat-1"
        assert features[0]["name"] == "User Login"
        assert features[0]["category"] == "auth"
        assert features[0]["passes"] is False
        assert features[0]["in_progress"] is False
        assert len(features[0]["steps"]) == 2

    @pytest.mark.unit
    def test_tasks_to_features_closed_status(self, tmp_path, monkeypatch):
        """Test closed task maps to passes=True."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import _tasks_to_features

        tasks = [
            {"id": "feat-1", "title": "Done", "status": "closed", "labels": []}
        ]

        features = _tasks_to_features(tasks)

        assert features[0]["passes"] is True
        assert features[0]["in_progress"] is False

    @pytest.mark.unit
    def test_tasks_to_features_in_progress_status(self, tmp_path, monkeypatch):
        """Test in_progress task maps to in_progress=True."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import _tasks_to_features

        tasks = [
            {"id": "feat-1", "title": "WIP", "status": "in_progress", "labels": []}
        ]

        features = _tasks_to_features(tasks)

        assert features[0]["passes"] is False
        assert features[0]["in_progress"] is True

    @pytest.mark.unit
    def test_tasks_to_features_no_labels(self, tmp_path, monkeypatch):
        """Test task without labels gets empty category."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import _tasks_to_features

        tasks = [
            {"id": "feat-1", "title": "No Labels", "status": "open", "labels": []}
        ]

        features = _tasks_to_features(tasks)

        assert features[0]["category"] == ""

    @pytest.mark.unit
    def test_tasks_to_features_body_field(self, tmp_path, monkeypatch):
        """Test task with 'body' field instead of 'description'."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import _tasks_to_features

        tasks = [
            {
                "id": "feat-1",
                "title": "Test",
                "status": "open",
                "labels": [],
                "body": "1. Step one\n2. Step two"
            }
        ]

        features = _tasks_to_features(tasks)

        assert features[0]["description"] == "1. Step one\n2. Step two"
        assert len(features[0]["steps"]) == 2


class TestCachedStats:
    """Tests for get_cached_stats function."""

    @pytest.mark.unit
    def test_get_cached_stats_no_manager(self, tmp_path, monkeypatch):
        """Test get_cached_stats when no manager exists."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import (
            get_cached_stats,
            _sync_managers,
        )

        # Clear existing managers
        _sync_managers.clear()

        # Mock registry to return None (registry.get_project_git_url is imported inside the function)
        with patch("registry.get_project_git_url", return_value=None):
            stats = get_cached_stats("nonexistent")

        assert stats["pending"] == 0
        assert stats["in_progress"] == 0
        assert stats["done"] == 0
        assert stats["total"] == 0

    @pytest.mark.unit
    def test_get_cached_stats_with_manager(self, tmp_path, monkeypatch):
        """Test get_cached_stats with existing manager."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import (
            get_beads_sync_manager,
            get_cached_stats,
            _sync_managers,
        )

        # Clear existing managers
        _sync_managers.clear()

        # Create manager and .beads directory
        beads_dir = tmp_path / "projects" / "test-project" / ".beads"
        beads_dir.mkdir(parents=True)

        issues_data = [
            {"id": "feat-1", "status": "open"},
            {"id": "feat-2", "status": "closed"},
        ]

        get_beads_sync_manager(
            "test-project",
            "https://github.com/user/repo.git"
        )

        mock_result = MagicMock(returncode=0, stdout=json.dumps(issues_data), stderr="")

        with patch("subprocess.run", return_value=mock_result):
            stats = get_cached_stats("test-project")

        assert stats["pending"] == 1
        assert stats["done"] == 1
        assert stats["total"] == 2


class TestCachedFeatures:
    """Tests for get_cached_features function."""

    @pytest.mark.unit
    def test_get_cached_features_no_manager(self, tmp_path, monkeypatch):
        """Test get_cached_features when no manager exists."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import (
            get_cached_features,
            _sync_managers,
        )

        # Clear existing managers
        _sync_managers.clear()

        # Mock registry to return None (registry.get_project_git_url is imported inside the function)
        with patch("registry.get_project_git_url", return_value=None):
            features = get_cached_features("nonexistent")

        assert features == []

    @pytest.mark.unit
    def test_get_cached_features_with_manager(self, tmp_path, monkeypatch):
        """Test get_cached_features with existing manager."""
        monkeypatch.setattr(
            "server.services.beads_manager.get_projects_dir",
            lambda: tmp_path / "projects"
        )

        from server.services.beads_sync_manager import (
            get_beads_sync_manager,
            get_cached_features,
            _sync_managers,
        )

        # Clear existing managers
        _sync_managers.clear()

        # Create manager and issues
        beads_dir = tmp_path / "projects" / "test-project" / ".beads"
        beads_dir.mkdir(parents=True)

        issues_data = [
            {"id": "feat-1", "title": "Feature One", "status": "open", "labels": ["ui"]},
        ]

        with open(beads_dir / "issues.jsonl", "w") as f:
            for issue in issues_data:
                f.write(json.dumps(issue) + "\n")

        get_beads_sync_manager(
            "test-project",
            "https://github.com/user/repo.git"
        )

        features = get_cached_features("test-project")

        assert len(features) == 1
        assert features[0]["id"] == "feat-1"
        assert features[0]["name"] == "Feature One"
        assert features[0]["category"] == "ui"
