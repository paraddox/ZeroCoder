"""
Comprehensive Service Layer Tests
=================================

Enterprise-grade unit tests for all service modules including:
- Container lifecycle management
- Beads synchronization
- Local project management
- Error handling and edge cases
- Concurrency and thread safety
"""

import asyncio
import json
import pytest
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call, PropertyMock

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Container Manager Service Tests
# =============================================================================

class TestContainerManagerInitialization:
    """Tests for ContainerManager initialization and configuration."""

    @pytest.fixture
    def mock_registry(self, tmp_path):
        """Mock registry functions."""
        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            yield mock_dir

    @pytest.mark.unit
    def test_init_creates_correct_container_name_for_coding(self, mock_registry, tmp_path):
        """Test that coding containers get numeric suffix."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        with patch.object(ContainerManager, "_sync_status"):
            with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                manager = ContainerManager(
                    project_name="my-app",
                    git_url="https://github.com/user/repo.git",
                    container_number=3,
                    project_dir=project_dir,
                    skip_db_persist=True,
                )

        assert manager.container_name == "zerocoder-my-app-3"
        assert not manager._is_init_container

    @pytest.mark.unit
    def test_init_creates_correct_container_name_for_init(self, mock_registry, tmp_path):
        """Test that init container gets -init suffix."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        with patch.object(ContainerManager, "_sync_status"):
            with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                manager = ContainerManager(
                    project_name="my-app",
                    git_url="https://github.com/user/repo.git",
                    container_number=0,
                    project_dir=project_dir,
                    skip_db_persist=True,
                )

        assert manager.container_name == "zerocoder-my-app-init"
        assert manager._is_init_container

    @pytest.mark.unit
    def test_init_sets_default_values(self, mock_registry, tmp_path):
        """Test that initialization sets correct default values."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        with patch.object(ContainerManager, "_sync_status"):
            with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                manager = ContainerManager(
                    project_name="test",
                    git_url="https://github.com/user/repo.git",
                    container_number=1,
                    project_dir=project_dir,
                    skip_db_persist=True,
                )

        assert manager._status == "not_created"
        assert manager.started_at is None
        assert manager.last_activity is None
        assert manager._graceful_stop_requested is False
        assert manager._current_agent_type == "coder"

    @pytest.mark.unit
    def test_container_type_property(self, mock_registry, tmp_path):
        """Test container_type property returns correct values."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        with patch.object(ContainerManager, "_sync_status"):
            with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                init_manager = ContainerManager(
                    project_name="test",
                    git_url="https://github.com/user/repo.git",
                    container_number=0,
                    project_dir=project_dir,
                    skip_db_persist=True,
                )
                coding_manager = ContainerManager(
                    project_name="test",
                    git_url="https://github.com/user/repo.git",
                    container_number=1,
                    project_dir=project_dir,
                    skip_db_persist=True,
                )

        assert init_manager.container_type == "init"
        assert coding_manager.container_type == "coding"


class TestContainerManagerStatusSync:
    """Tests for container status synchronization with Docker."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a container manager for testing."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="test-project",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    def test_sync_status_with_running_container(self, container_manager):
        """Test status sync when container is running in Docker."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="running\n"
            )
            with patch("server.services.container_manager.get_container", return_value=None):
                with patch("server.services.container_manager.create_container"):
                    container_manager._status = "not_created"
                    container_manager._sync_status()

        assert container_manager._status == "running"

    @pytest.mark.unit
    def test_sync_status_with_stopped_container(self, container_manager):
        """Test status sync when container is stopped in Docker."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="exited\n"
            )
            with patch("server.services.container_manager.get_container", return_value=None):
                with patch("server.services.container_manager.create_container"):
                    container_manager._status = "running"
                    container_manager._sync_status()

        assert container_manager._status == "stopped"

    @pytest.mark.unit
    def test_sync_status_with_nonexistent_container(self, container_manager):
        """Test status sync when container doesn't exist in Docker."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout=""
            )
            with patch("server.services.container_manager.get_container", return_value=None):
                container_manager._status = "running"
                container_manager._sync_status()

        assert container_manager._status == "not_created"

    @pytest.mark.unit
    def test_sync_preserves_completed_status(self, container_manager):
        """Test that completed status is preserved during sync."""
        container_manager._status = "completed"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="running\n")
            container_manager._sync_status()

        assert container_manager._status == "completed"


class TestContainerManagerAgentModel:
    """Tests for agent model configuration."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a container manager for testing."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)
        (project_dir / "prompts").mkdir()

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="test-project",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    def test_get_agent_model_returns_default_when_no_config(self, container_manager):
        """Test default model is returned when config doesn't exist."""
        model = container_manager._get_agent_model()
        assert model == "claude-sonnet-4-5-20250514"

    @pytest.mark.unit
    def test_get_agent_model_reads_from_config(self, container_manager):
        """Test model is read from config file."""
        config_path = container_manager.project_dir / "prompts" / ".agent_config.json"
        config_path.write_text(json.dumps({"agent_model": "glm-4-7"}))

        model = container_manager._get_agent_model()
        assert model == "glm-4-7"

    @pytest.mark.unit
    def test_is_opencode_model_true_for_glm(self, container_manager):
        """Test OpenCode detection for GLM model."""
        config_path = container_manager.project_dir / "prompts" / ".agent_config.json"
        config_path.write_text(json.dumps({"agent_model": "glm-4-7"}))

        assert container_manager._is_opencode_model() is True

    @pytest.mark.unit
    def test_is_opencode_model_false_for_claude(self, container_manager):
        """Test OpenCode detection for Claude model."""
        config_path = container_manager.project_dir / "prompts" / ".agent_config.json"
        config_path.write_text(json.dumps({"agent_model": "claude-sonnet-4-5-20250514"}))

        assert container_manager._is_opencode_model() is False


class TestContainerManagerIdleTimeout:
    """Tests for idle timeout functionality."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a container manager for testing."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="test-project",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    def test_is_idle_false_when_no_activity(self, container_manager):
        """Test is_idle returns False when no activity recorded."""
        container_manager.last_activity = None
        assert container_manager.is_idle() is False

    @pytest.mark.unit
    def test_is_idle_false_when_recent_activity(self, container_manager):
        """Test is_idle returns False when activity is recent."""
        container_manager.last_activity = datetime.now() - timedelta(minutes=5)
        assert container_manager.is_idle() is False

    @pytest.mark.unit
    def test_is_idle_true_when_old_activity(self, container_manager):
        """Test is_idle returns True when activity is old."""
        container_manager.last_activity = datetime.now() - timedelta(minutes=20)
        assert container_manager.is_idle() is True

    @pytest.mark.unit
    def test_get_idle_seconds_zero_when_no_activity(self, container_manager):
        """Test get_idle_seconds returns 0 when no activity."""
        container_manager.last_activity = None
        assert container_manager.get_idle_seconds() == 0

    @pytest.mark.unit
    def test_get_idle_seconds_accurate(self, container_manager):
        """Test get_idle_seconds returns accurate count."""
        container_manager.last_activity = datetime.now() - timedelta(seconds=60)
        idle = container_manager.get_idle_seconds()
        assert 55 <= idle <= 65  # Allow some tolerance


class TestContainerManagerAgentStuck:
    """Tests for stuck agent detection."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a container manager for testing."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="test-project",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    def test_is_agent_stuck_false_when_no_activity(self, container_manager):
        """Test is_agent_stuck returns False when no activity recorded."""
        container_manager.last_activity = None
        assert container_manager.is_agent_stuck() is False

    @pytest.mark.unit
    def test_is_agent_stuck_false_when_agent_not_running(self, container_manager):
        """Test is_agent_stuck returns False when agent not running."""
        container_manager.last_activity = datetime.now() - timedelta(minutes=15)
        with patch.object(container_manager, "is_agent_running", return_value=False):
            assert container_manager.is_agent_stuck() is False

    @pytest.mark.unit
    def test_is_agent_stuck_true_when_no_output(self, container_manager):
        """Test is_agent_stuck returns True when agent running but no output."""
        container_manager.last_activity = datetime.now() - timedelta(minutes=15)
        with patch.object(container_manager, "is_agent_running", return_value=True):
            assert container_manager.is_agent_stuck() is True


class TestContainerManagerCallbacks:
    """Tests for callback management."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a container manager for testing."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="test-project",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_add_and_remove_output_callback(self, container_manager):
        """Test adding and removing output callbacks."""
        callback = AsyncMock()

        container_manager.add_output_callback(callback)
        assert callback in container_manager._output_callbacks

        container_manager.remove_output_callback(callback)
        assert callback not in container_manager._output_callbacks

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_add_and_remove_status_callback(self, container_manager):
        """Test adding and removing status callbacks."""
        callback = AsyncMock()

        container_manager.add_status_callback(callback)
        assert callback in container_manager._status_callbacks

        container_manager.remove_status_callback(callback)
        assert callback not in container_manager._status_callbacks

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_safe_callback_handles_errors(self, container_manager):
        """Test that _safe_callback handles errors gracefully."""
        error_callback = AsyncMock(side_effect=Exception("Test error"))

        # Should not raise
        await container_manager._safe_callback(error_callback, "test")

        error_callback.assert_called_once_with("test")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_notify_status_calls_callbacks(self, container_manager):
        """Test that _notify_status calls all registered callbacks."""
        callback1 = AsyncMock()
        callback2 = AsyncMock()

        container_manager.add_status_callback(callback1)
        container_manager.add_status_callback(callback2)

        await container_manager._notify_status("running")

        callback1.assert_called_once_with("running")
        callback2.assert_called_once_with("running")


class TestContainerManagerMarkerFiles:
    """Tests for user-started marker file management."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a container manager for testing."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="test-project",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    def test_marker_file_path_includes_container_number(self, container_manager):
        """Test marker file path is container-specific."""
        path = container_manager._get_marker_file_path()
        assert ".agent_started.1" in str(path)

    @pytest.mark.unit
    def test_set_user_started_marker_creates_file(self, container_manager):
        """Test that setting marker creates the file."""
        marker_path = container_manager._get_marker_file_path()
        assert not marker_path.exists()

        container_manager._set_user_started_marker()

        assert marker_path.exists()

    @pytest.mark.unit
    def test_remove_user_started_marker_deletes_file(self, container_manager):
        """Test that removing marker deletes the file."""
        marker_path = container_manager._get_marker_file_path()
        marker_path.touch()
        assert marker_path.exists()

        container_manager._remove_user_started_marker()

        assert not marker_path.exists()

    @pytest.mark.unit
    def test_check_user_started_marker(self, container_manager):
        """Test checking marker file existence."""
        marker_path = container_manager._get_marker_file_path()

        assert container_manager._check_user_started_marker() is False

        marker_path.touch()

        assert container_manager._check_user_started_marker() is True


# =============================================================================
# Container Beads Service Tests
# =============================================================================

class TestContainerBeadsClient:
    """Tests for ContainerBeadsClient service."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_feature_success(self):
        """Test successful feature creation."""
        from server.services.container_beads import ContainerBeadsClient

        client = ContainerBeadsClient("test-project")

        with patch("server.services.container_beads.send_beads_command") as mock_cmd:
            mock_cmd.return_value = {"success": True, "id": "feat-1"}

            result = await client.create(
                name="Test Feature",
                category="auth",
                description="Test description",
                steps=["Step 1", "Step 2"],
                priority=1
            )

        assert result == {"success": True, "id": "feat-1"}
        mock_cmd.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_feature_success(self):
        """Test successful feature update."""
        from server.services.container_beads import ContainerBeadsClient

        client = ContainerBeadsClient("test-project")

        with patch("server.services.container_beads.send_beads_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            result = await client.update("feat-1", title="Updated Title", priority=2)

        assert result == {"success": True}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_delete_feature_success(self):
        """Test successful feature deletion."""
        from server.services.container_beads import ContainerBeadsClient

        client = ContainerBeadsClient("test-project")

        with patch("server.services.container_beads.send_beads_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            result = await client.delete("feat-1")

        assert result == {"success": True}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_skip_feature_success(self):
        """Test successful feature skip."""
        from server.services.container_beads import ContainerBeadsClient

        client = ContainerBeadsClient("test-project")

        with patch("server.services.container_beads.send_beads_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            result = await client.skip("feat-1")

        assert result == {"success": True}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_reopen_feature_success(self):
        """Test successful feature reopen."""
        from server.services.container_beads import ContainerBeadsClient

        client = ContainerBeadsClient("test-project")

        with patch("server.services.container_beads.send_beads_command") as mock_cmd:
            mock_cmd.return_value = {"success": True}

            result = await client.reopen("feat-1")

        assert result == {"success": True}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_list_all_features(self):
        """Test listing all features."""
        from server.services.container_beads import ContainerBeadsClient

        client = ContainerBeadsClient("test-project")

        mock_features = [
            {"id": "feat-1", "title": "Feature 1", "status": "open"},
            {"id": "feat-2", "title": "Feature 2", "status": "closed"},
        ]

        with patch("server.services.container_beads.send_beads_command") as mock_cmd:
            mock_cmd.return_value = {"success": True, "tasks": mock_features}

            result = await client.list_all()

        assert result["tasks"] == mock_features


class TestSendBeadsCommand:
    """Tests for send_beads_command function."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_command_success(self):
        """Test successful beads command execution."""
        from server.services.container_beads import send_beads_command

        with patch("asyncio.to_thread") as mock_thread:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = '{"success": true}'
            mock_thread.return_value = mock_result

            result = await send_beads_command("test-project", "list")

        assert result == {"success": True}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_command_failure(self):
        """Test beads command failure handling."""
        from server.services.container_beads import send_beads_command

        with patch("asyncio.to_thread") as mock_thread:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "Command failed"
            mock_thread.return_value = mock_result

            with pytest.raises(Exception):
                await send_beads_command("test-project", "invalid-command")


# =============================================================================
# Beads Sync Manager Tests
# =============================================================================

class TestBeadsSyncManager:
    """Tests for BeadsSyncManager service."""

    @pytest.fixture
    def mock_sync_dir(self, tmp_path):
        """Create mock beads-sync directory."""
        sync_dir = tmp_path / "beads-sync" / "test-project"
        sync_dir.mkdir(parents=True)
        return sync_dir

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ensure_cloned_new_repo(self, tmp_path):
        """Test cloning when repo doesn't exist."""
        from server.services.beads_sync_manager import BeadsSyncManager

        with patch("server.services.beads_sync_manager.get_beads_sync_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch("asyncio.to_thread") as mock_thread:
                mock_thread.return_value = MagicMock(returncode=0)

                manager = BeadsSyncManager("test-project", "https://github.com/user/repo.git")
                await manager.ensure_cloned()

                # Git clone should have been called
                assert mock_thread.called

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_pull_latest(self, mock_sync_dir, tmp_path):
        """Test pulling latest changes."""
        from server.services.beads_sync_manager import BeadsSyncManager

        # Create .git directory to simulate existing clone
        (mock_sync_dir / ".git").mkdir()

        with patch("server.services.beads_sync_manager.get_beads_sync_dir") as mock_dir:
            mock_dir.return_value = tmp_path / "beads-sync"
            with patch("asyncio.to_thread") as mock_thread:
                mock_thread.return_value = MagicMock(returncode=0)

                manager = BeadsSyncManager("test-project", "https://github.com/user/repo.git")
                manager._cloned = True
                await manager.pull_latest()

                assert mock_thread.called

    @pytest.mark.unit
    def test_get_tasks_from_jsonl(self, mock_sync_dir, tmp_path):
        """Test parsing tasks from JSONL file."""
        from server.services.beads_sync_manager import BeadsSyncManager

        # Create beads issues file
        beads_dir = mock_sync_dir / ".beads"
        beads_dir.mkdir()
        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text(
            '{"id": "feat-1", "title": "Test 1", "status": "open", "priority": 1}\n'
            '{"id": "feat-2", "title": "Test 2", "status": "closed", "priority": 2}\n'
        )

        with patch("server.services.beads_sync_manager.get_beads_sync_dir") as mock_dir:
            mock_dir.return_value = tmp_path / "beads-sync"

            manager = BeadsSyncManager("test-project", "https://github.com/user/repo.git")
            tasks = manager.get_tasks()

        assert len(tasks) == 2
        assert tasks[0]["id"] == "feat-1"
        assert tasks[1]["status"] == "closed"


# =============================================================================
# Local Project Manager Tests
# =============================================================================

class TestLocalProjectManager:
    """Tests for LocalProjectManager service."""

    @pytest.fixture
    def project_dir(self, tmp_path):
        """Create a test project directory."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        (project_dir / ".git").mkdir()
        (project_dir / ".beads").mkdir()
        return project_dir

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ensure_cloned_existing(self, project_dir, tmp_path):
        """Test ensure_cloned with existing clone."""
        from server.services.local_project_manager import LocalProjectManager

        with patch("server.services.local_project_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path

            manager = LocalProjectManager(
                "test-project",
                "https://github.com/user/repo.git"
            )
            manager._cloned = True

            await manager.ensure_cloned()
            # Should not attempt to clone again
            assert manager._cloned

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_pull_latest(self, project_dir, tmp_path):
        """Test pulling latest changes."""
        from server.services.local_project_manager import LocalProjectManager

        with patch("server.services.local_project_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch("asyncio.to_thread") as mock_thread:
                mock_thread.return_value = MagicMock(returncode=0)

                manager = LocalProjectManager(
                    "test-project",
                    "https://github.com/user/repo.git"
                )
                manager._cloned = True
                await manager.pull_latest()

                assert mock_thread.called

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_push_changes(self, project_dir, tmp_path):
        """Test pushing changes to remote."""
        from server.services.local_project_manager import LocalProjectManager

        with patch("server.services.local_project_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch("asyncio.to_thread") as mock_thread:
                mock_thread.return_value = MagicMock(returncode=0)

                manager = LocalProjectManager(
                    "test-project",
                    "https://github.com/user/repo.git"
                )
                manager._cloned = True
                await manager.push_changes("Test commit message")

                # Should call git add, commit, push
                assert mock_thread.call_count >= 3

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_task(self, project_dir, tmp_path):
        """Test creating a task via beads CLI."""
        from server.services.local_project_manager import LocalProjectManager

        with patch("server.services.local_project_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch("asyncio.to_thread") as mock_thread:
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = "Created feat-1"
                mock_thread.return_value = mock_result

                manager = LocalProjectManager(
                    "test-project",
                    "https://github.com/user/repo.git"
                )
                manager._cloned = True

                result = await manager.create_task(
                    title="New Feature",
                    description="Feature description",
                    priority=1,
                    task_type="feature"
                )

                assert mock_thread.called


# =============================================================================
# Output Sanitization Tests
# =============================================================================

class TestOutputSanitization:
    """Tests for output sanitization function."""

    @pytest.mark.unit
    def test_redacts_anthropic_api_keys(self):
        """Test redaction of Anthropic API keys."""
        from server.services.container_manager import sanitize_output

        line = "Using API key: sk-ant-api03-abcdefghij1234567890abcdefghij"
        result = sanitize_output(line)

        assert "sk-ant" not in result
        assert "[REDACTED]" in result

    @pytest.mark.unit
    def test_redacts_generic_api_keys(self):
        """Test redaction of generic API keys."""
        from server.services.container_manager import sanitize_output

        test_cases = [
            "api_key=secret123abc",
            "api-key:supersecret",
            "API_KEY=mysecretkey",
        ]

        for line in test_cases:
            result = sanitize_output(line)
            assert "[REDACTED]" in result, f"Failed for: {line}"

    @pytest.mark.unit
    def test_redacts_tokens(self):
        """Test redaction of tokens."""
        from server.services.container_manager import sanitize_output

        test_cases = [
            "token=abc123secret",
            "TOKEN:mytoken123",
        ]

        for line in test_cases:
            result = sanitize_output(line)
            assert "[REDACTED]" in result, f"Failed for: {line}"

    @pytest.mark.unit
    def test_redacts_passwords(self):
        """Test redaction of passwords."""
        from server.services.container_manager import sanitize_output

        test_cases = [
            "password=mypassword123",
            "PASSWORD:secret",
        ]

        for line in test_cases:
            result = sanitize_output(line)
            assert "[REDACTED]" in result, f"Failed for: {line}"

    @pytest.mark.unit
    def test_preserves_safe_content(self):
        """Test that safe content is preserved."""
        from server.services.container_manager import sanitize_output

        safe_lines = [
            "Processing file: /path/to/file.py",
            "Status: success",
            "Installing package: requests",
            "Error: File not found",
        ]

        for line in safe_lines:
            result = sanitize_output(line)
            assert result == line, f"Modified safe line: {line}"

    @pytest.mark.unit
    def test_case_insensitive_matching(self):
        """Test that pattern matching is case-insensitive."""
        from server.services.container_manager import sanitize_output

        test_cases = [
            "API_KEY=secret",
            "api_key=secret",
            "Api_Key=secret",
        ]

        for line in test_cases:
            result = sanitize_output(line)
            assert "[REDACTED]" in result, f"Failed for: {line}"


# =============================================================================
# Docker Image Management Tests
# =============================================================================

class TestDockerImageManagement:
    """Tests for Docker image management functions."""

    @pytest.mark.unit
    def test_image_exists_true(self):
        """Test image_exists returns True when image exists."""
        from server.services.container_manager import image_exists

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = image_exists("test-image")

            assert result is True
            mock_run.assert_called_once()

    @pytest.mark.unit
    def test_image_exists_false(self):
        """Test image_exists returns False when image doesn't exist."""
        from server.services.container_manager import image_exists

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            result = image_exists("nonexistent-image")

            assert result is False

    @pytest.mark.unit
    def test_build_image_success(self, tmp_path):
        """Test successful image build."""
        from server.services.container_manager import build_image

        dockerfile = tmp_path / "Dockerfile.project"
        dockerfile.write_text("FROM ubuntu:latest")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            with patch("server.services.container_manager.DOCKERFILE_PATH", dockerfile):
                success, message = build_image("test-image")

            assert success is True
            assert "success" in message.lower()

    @pytest.mark.unit
    def test_build_image_dockerfile_not_found(self, tmp_path):
        """Test build_image when Dockerfile doesn't exist."""
        from server.services.container_manager import build_image

        nonexistent = tmp_path / "nonexistent" / "Dockerfile.project"

        with patch("server.services.container_manager.DOCKERFILE_PATH", nonexistent):
            success, message = build_image("test-image")

        assert success is False
        assert "not found" in message.lower()

    @pytest.mark.unit
    def test_build_image_failure(self, tmp_path):
        """Test build_image when build fails."""
        from server.services.container_manager import build_image

        dockerfile = tmp_path / "Dockerfile.project"
        dockerfile.write_text("FROM ubuntu:latest")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="Error building image"
            )

            with patch("server.services.container_manager.DOCKERFILE_PATH", dockerfile):
                success, message = build_image("test-image")

        assert success is False
        assert "failed" in message.lower()

    @pytest.mark.unit
    def test_ensure_image_exists_already_exists(self):
        """Test ensure_image_exists when image already exists."""
        from server.services.container_manager import ensure_image_exists

        with patch("server.services.container_manager.image_exists") as mock_exists:
            mock_exists.return_value = True

            success, message = ensure_image_exists("test-image")

            assert success is True
            assert "exists" in message.lower()

    @pytest.mark.unit
    def test_ensure_image_exists_builds_when_missing(self, tmp_path):
        """Test ensure_image_exists builds image when missing."""
        from server.services.container_manager import ensure_image_exists

        with patch("server.services.container_manager.image_exists") as mock_exists:
            mock_exists.return_value = False

            with patch("server.services.container_manager.build_image") as mock_build:
                mock_build.return_value = (True, "Built successfully")

                success, message = ensure_image_exists("test-image")

                assert success is True
                mock_build.assert_called_once()


# =============================================================================
# Container Manager Registry Tests
# =============================================================================

class TestContainerManagerRegistry:
    """Tests for container manager registry functions."""

    @pytest.mark.unit
    def test_get_container_manager_creates_new(self, tmp_path):
        """Test get_container_manager creates new manager when not cached."""
        from server.services.container_manager import (
            get_container_manager,
            _container_managers,
            ContainerManager,
        )

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        # Clear existing managers
        _container_managers.clear()

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = get_container_manager(
                        project_name="new-project",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                    )

        assert manager is not None
        assert manager.project_name == "new-project"
        assert "new-project" in _container_managers

    @pytest.mark.unit
    def test_get_container_manager_returns_cached(self, tmp_path):
        """Test get_container_manager returns cached manager."""
        from server.services.container_manager import (
            get_container_manager,
            _container_managers,
            ContainerManager,
        )

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        # Clear existing managers
        _container_managers.clear()

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager1 = get_container_manager(
                        project_name="cached-project",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                    )
                    manager2 = get_container_manager(
                        project_name="cached-project",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                    )

        assert manager1 is manager2

    @pytest.mark.unit
    def test_get_existing_container_manager_returns_none(self):
        """Test get_existing_container_manager returns None when not found."""
        from server.services.container_manager import (
            get_existing_container_manager,
            _container_managers,
        )

        # Clear existing managers
        _container_managers.clear()

        manager = get_existing_container_manager("nonexistent", container_number=1)

        assert manager is None

    @pytest.mark.unit
    def test_clear_container_manager(self, tmp_path):
        """Test clear_container_manager removes cached managers."""
        from server.services.container_manager import (
            get_container_manager,
            clear_container_manager,
            _container_managers,
            ContainerManager,
        )

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        # Clear existing managers
        _container_managers.clear()

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    get_container_manager(
                        project_name="to-clear",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                    )

        assert "to-clear" in _container_managers

        clear_container_manager("to-clear")

        assert "to-clear" not in _container_managers


# =============================================================================
# Performance Tests
# =============================================================================

class TestServicePerformance:
    """Performance-related tests for services."""

    @pytest.mark.unit
    def test_sanitize_output_performance(self):
        """Test that sanitize_output handles large inputs efficiently."""
        from server.services.container_manager import sanitize_output
        import time

        # Generate large input
        large_input = "Processing file: /path/to/file.py - status: ok\n" * 10000

        start = time.time()
        result = sanitize_output(large_input)
        duration = time.time() - start

        # Should complete in under 1 second
        assert duration < 1.0, f"Sanitization took too long: {duration}s"
        assert result == large_input

    @pytest.mark.unit
    def test_container_manager_callback_performance(self, tmp_path):
        """Test callback management with many callbacks."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="perf-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )

        # Add many callbacks
        callbacks = [AsyncMock() for _ in range(100)]
        for cb in callbacks:
            manager.add_status_callback(cb)

        assert len(manager._status_callbacks) == 100

        # Remove all callbacks
        for cb in callbacks:
            manager.remove_status_callback(cb)

        assert len(manager._status_callbacks) == 0
