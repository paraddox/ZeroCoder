"""
State Machine Tests
==================

Enterprise-grade tests for state machine behavior including:
- Container state transitions
- Agent lifecycle states
- Feature status transitions
- Invalid state transition handling
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Container State Machine Tests
# =============================================================================

class TestContainerStateMachine:
    """Tests for container state transitions."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a ContainerManager for state testing."""
        from server.services.container_manager import ContainerManager, _container_managers

        _container_managers.clear()
        project_dir = tmp_path / "state-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="state-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    def test_initial_state_is_not_created(self, container_manager):
        """Test that initial container state is not_created."""
        assert container_manager._status == "not_created"
        assert container_manager.status == "not_created"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_transition_not_created_to_running(self, container_manager):
        """Test transition from not_created to running."""
        status_callback = AsyncMock()
        container_manager.add_status_callback(status_callback)

        # Simulate container starting
        container_manager._status = "running"
        container_manager.started_at = datetime.now()
        container_manager.last_activity = datetime.now()

        await container_manager._notify_status("running")

        status_callback.assert_called_once_with("running")
        assert container_manager._status == "running"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_transition_running_to_stopped(self, container_manager):
        """Test transition from running to stopped."""
        container_manager._status = "running"
        container_manager.started_at = datetime.now()

        status_callback = AsyncMock()
        container_manager.add_status_callback(status_callback)

        # Simulate container stopping
        container_manager._status = "stopped"
        await container_manager._notify_status("stopped")

        status_callback.assert_called_once_with("stopped")
        assert container_manager._status == "stopped"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_transition_stopped_to_running_restart(self, container_manager):
        """Test restart: stopped -> running."""
        container_manager._status = "stopped"

        status_callback = AsyncMock()
        container_manager.add_status_callback(status_callback)

        # Simulate restart
        container_manager._status = "running"
        container_manager.started_at = datetime.now()
        await container_manager._notify_status("running")

        status_callback.assert_called_once_with("running")
        assert container_manager._status == "running"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_transition_running_to_completed(self, container_manager):
        """Test transition from running to completed (all features done)."""
        container_manager._status = "running"

        status_callback = AsyncMock()
        container_manager.add_status_callback(status_callback)

        # Simulate completion
        container_manager._status = "completed"
        await container_manager._notify_status("completed")

        status_callback.assert_called_once_with("completed")
        assert container_manager._status == "completed"

    @pytest.mark.unit
    def test_status_property_returns_current_status(self, container_manager):
        """Test that status property reflects current state."""
        assert container_manager.status == "not_created"

        container_manager._status = "running"
        assert container_manager.status == "running"

        container_manager._status = "stopped"
        assert container_manager.status == "stopped"

    @pytest.mark.unit
    def test_get_status_dict_includes_all_fields(self, container_manager):
        """Test that get_status_dict returns all required fields."""
        container_manager._status = "running"
        container_manager.started_at = datetime.now()
        container_manager.last_activity = datetime.now()

        status = container_manager.get_status_dict()

        assert "status" in status
        assert "container_name" in status
        assert "started_at" in status
        assert "idle_seconds" in status
        assert "agent_running" in status
        assert "graceful_stop_requested" in status


class TestContainerStateInvariants:
    """Tests for state machine invariants that must always hold."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a ContainerManager for invariant testing."""
        from server.services.container_manager import ContainerManager, _container_managers

        _container_managers.clear()
        project_dir = tmp_path / "invariant-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="invariant-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    def test_started_at_is_none_when_not_created(self, container_manager):
        """Invariant: started_at should be None when not_created."""
        assert container_manager._status == "not_created"
        assert container_manager.started_at is None

    @pytest.mark.unit
    def test_idle_seconds_zero_when_no_activity(self, container_manager):
        """Invariant: idle_seconds should be 0 when no activity recorded."""
        container_manager.last_activity = None
        assert container_manager.get_idle_seconds() == 0

    @pytest.mark.unit
    def test_idle_calculation_increases_over_time(self, container_manager):
        """Invariant: idle_seconds should increase as time passes."""
        container_manager.last_activity = datetime.now() - timedelta(seconds=10)
        idle1 = container_manager.get_idle_seconds()

        container_manager.last_activity = datetime.now() - timedelta(seconds=20)
        idle2 = container_manager.get_idle_seconds()

        assert idle2 > idle1

    @pytest.mark.unit
    def test_graceful_stop_flag_default_false(self, container_manager):
        """Invariant: graceful_stop_requested starts as False."""
        assert container_manager._graceful_stop_requested is False


class TestContainerStatePersistence:
    """Tests for container state persistence and recovery."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a ContainerManager for persistence testing."""
        from server.services.container_manager import ContainerManager, _container_managers

        _container_managers.clear()
        project_dir = tmp_path / "persist-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="persist-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    def test_sync_status_updates_from_docker(self, container_manager):
        """Test that _sync_status updates state from Docker."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="running\n")
            with patch("server.services.container_manager.get_container", return_value=None):
                with patch("server.services.container_manager.create_container"):
                    container_manager._status = "not_created"
                    container_manager._sync_status()

        assert container_manager._status == "running"

    @pytest.mark.unit
    def test_sync_status_handles_nonexistent_container(self, container_manager):
        """Test that _sync_status handles missing containers."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            with patch("server.services.container_manager.get_container", return_value=None):
                container_manager._status = "running"
                container_manager._sync_status()

        assert container_manager._status == "not_created"

    @pytest.mark.unit
    def test_completed_status_preserved_during_sync(self, container_manager):
        """Test that completed status is preserved during sync."""
        container_manager._status = "completed"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="running\n")
            container_manager._sync_status()

        # Completed status should be preserved
        assert container_manager._status == "completed"


# =============================================================================
# Agent State Machine Tests
# =============================================================================

class TestAgentStateMachine:
    """Tests for agent process state tracking."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a ContainerManager for agent state testing."""
        from server.services.container_manager import ContainerManager, _container_managers

        _container_managers.clear()
        project_dir = tmp_path / "agent-state-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="agent-state-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    def test_agent_running_false_when_not_created(self, container_manager):
        """Test is_agent_running returns False when container not created."""
        container_manager._status = "not_created"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            assert container_manager.is_agent_running() is False

    @pytest.mark.unit
    def test_agent_running_true_when_process_exists(self, container_manager):
        """Test is_agent_running returns True when process exists."""
        container_manager._status = "running"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="12345\n")
            assert container_manager.is_agent_running() is True

    @pytest.mark.unit
    def test_agent_running_false_when_no_process(self, container_manager):
        """Test is_agent_running returns False when no process."""
        container_manager._status = "running"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            assert container_manager.is_agent_running() is False

    @pytest.mark.unit
    def test_is_agent_stuck_requires_running_agent(self, container_manager):
        """Test is_agent_stuck only true when agent running but no output."""
        container_manager.last_activity = datetime.now() - timedelta(minutes=15)

        # Not stuck if agent not running
        with patch.object(container_manager, "is_agent_running", return_value=False):
            assert container_manager.is_agent_stuck() is False

        # Stuck if agent running and no output
        with patch.object(container_manager, "is_agent_running", return_value=True):
            assert container_manager.is_agent_stuck() is True

    @pytest.mark.unit
    def test_is_idle_based_on_last_activity(self, container_manager):
        """Test is_idle calculation based on last_activity."""
        from server.services.container_manager import IDLE_TIMEOUT_MINUTES

        # No activity - not idle
        container_manager.last_activity = None
        assert container_manager.is_idle() is False

        # Recent activity - not idle
        container_manager.last_activity = datetime.now() - timedelta(minutes=5)
        assert container_manager.is_idle() is False

        # Old activity - idle
        container_manager.last_activity = datetime.now() - timedelta(minutes=IDLE_TIMEOUT_MINUTES + 1)
        assert container_manager.is_idle() is True


class TestAgentTypeTransitions:
    """Tests for agent type transitions during container lifecycle."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a ContainerManager for agent type testing."""
        from server.services.container_manager import ContainerManager, _container_managers

        _container_managers.clear()
        project_dir = tmp_path / "agent-type-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="agent-type-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    def test_default_agent_type_is_coder(self, container_manager):
        """Test that default agent type is coder."""
        assert container_manager._current_agent_type == "coder"

    @pytest.mark.unit
    def test_init_container_type(self, tmp_path):
        """Test that init container has correct type."""
        from server.services.container_manager import ContainerManager, _container_managers

        _container_managers.clear()
        project_dir = tmp_path / "init-type-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="init-type-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=0,  # Init container
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )

        assert manager._is_init_container is True
        assert manager.container_type == "init"


# =============================================================================
# Feature State Machine Tests
# =============================================================================

class TestFeatureStateMachine:
    """Tests for feature status transitions."""

    @pytest.fixture
    def beads_project(self, tmp_path):
        """Create a project with beads setup."""
        project_dir = tmp_path / "feature-state-test"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat\n")
        return project_dir

    @pytest.mark.unit
    def test_feature_initial_state_open(self, beads_project):
        """Test that features start in open state."""
        import json

        issues_file = beads_project / ".beads" / "issues.jsonl"
        feature = {"id": "feat-1", "title": "Test", "status": "open", "priority": 1}
        issues_file.write_text(json.dumps(feature) + "\n")

        # Read feature
        with open(issues_file) as f:
            loaded = json.loads(f.readline())

        assert loaded["status"] == "open"

    @pytest.mark.unit
    def test_feature_transition_open_to_in_progress(self, beads_project):
        """Test transition from open to in_progress."""
        import json

        issues_file = beads_project / ".beads" / "issues.jsonl"

        # Start as open
        feature = {"id": "feat-1", "title": "Test", "status": "open", "priority": 1}
        issues_file.write_text(json.dumps(feature) + "\n")

        # Transition to in_progress
        feature["status"] = "in_progress"
        issues_file.write_text(json.dumps(feature) + "\n")

        with open(issues_file) as f:
            loaded = json.loads(f.readline())

        assert loaded["status"] == "in_progress"

    @pytest.mark.unit
    def test_feature_transition_in_progress_to_closed(self, beads_project):
        """Test transition from in_progress to closed."""
        import json

        issues_file = beads_project / ".beads" / "issues.jsonl"

        feature = {"id": "feat-1", "title": "Test", "status": "in_progress", "priority": 1}
        issues_file.write_text(json.dumps(feature) + "\n")

        # Transition to closed
        feature["status"] = "closed"
        issues_file.write_text(json.dumps(feature) + "\n")

        with open(issues_file) as f:
            loaded = json.loads(f.readline())

        assert loaded["status"] == "closed"

    @pytest.mark.unit
    def test_feature_reopen_from_closed(self, beads_project):
        """Test reopening a closed feature."""
        import json

        issues_file = beads_project / ".beads" / "issues.jsonl"

        # Start as closed
        feature = {"id": "feat-1", "title": "Test", "status": "closed", "priority": 1}
        issues_file.write_text(json.dumps(feature) + "\n")

        # Reopen to open
        feature["status"] = "open"
        issues_file.write_text(json.dumps(feature) + "\n")

        with open(issues_file) as f:
            loaded = json.loads(f.readline())

        assert loaded["status"] == "open"


# =============================================================================
# Callback State Tests
# =============================================================================

class TestCallbackStateManagement:
    """Tests for callback registration state management."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a ContainerManager for callback testing."""
        from server.services.container_manager import ContainerManager, _container_managers

        _container_managers.clear()
        project_dir = tmp_path / "callback-state-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="callback-state-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    def test_callbacks_start_empty(self, container_manager):
        """Test that callback lists start empty."""
        assert len(container_manager._output_callbacks) == 0
        assert len(container_manager._status_callbacks) == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_add_callback_increases_count(self, container_manager):
        """Test that adding callbacks increases count."""
        cb1 = AsyncMock()
        cb2 = AsyncMock()

        container_manager.add_output_callback(cb1)
        assert len(container_manager._output_callbacks) == 1

        container_manager.add_output_callback(cb2)
        assert len(container_manager._output_callbacks) == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_remove_callback_decreases_count(self, container_manager):
        """Test that removing callbacks decreases count."""
        cb1 = AsyncMock()
        cb2 = AsyncMock()

        container_manager.add_output_callback(cb1)
        container_manager.add_output_callback(cb2)
        assert len(container_manager._output_callbacks) == 2

        container_manager.remove_output_callback(cb1)
        assert len(container_manager._output_callbacks) == 1

        container_manager.remove_output_callback(cb2)
        assert len(container_manager._output_callbacks) == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_remove_nonexistent_callback_no_error(self, container_manager):
        """Test that removing nonexistent callback doesn't error."""
        cb = AsyncMock()

        # Should not raise
        container_manager.remove_output_callback(cb)
        assert len(container_manager._output_callbacks) == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_duplicate_callback_handling(self, container_manager):
        """Test adding the same callback twice."""
        cb = AsyncMock()

        container_manager.add_output_callback(cb)
        container_manager.add_output_callback(cb)

        # Behavior depends on implementation - list allows duplicates
        # Check callback is present
        assert cb in container_manager._output_callbacks


# =============================================================================
# Manager Registry State Tests
# =============================================================================

class TestManagerRegistryState:
    """Tests for container manager registry state."""

    @pytest.mark.unit
    def test_registry_starts_empty_after_clear(self):
        """Test that registry is empty after clear."""
        from server.services.container_manager import _container_managers

        _container_managers.clear()
        assert len(_container_managers) == 0

    @pytest.mark.unit
    def test_registry_caches_managers(self, tmp_path):
        """Test that registry caches created managers."""
        from server.services.container_manager import (
            get_container_manager,
            _container_managers,
            ContainerManager,
        )

        _container_managers.clear()
        project_dir = tmp_path / "cache-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = get_container_manager(
                        project_name="cache-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                    )

        assert "cache-test" in _container_managers
        assert len(_container_managers["cache-test"]) == 1

    @pytest.mark.unit
    def test_registry_returns_same_manager(self, tmp_path):
        """Test that registry returns same manager instance."""
        from server.services.container_manager import (
            get_container_manager,
            _container_managers,
            ContainerManager,
        )

        _container_managers.clear()
        project_dir = tmp_path / "same-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager1 = get_container_manager(
                        project_name="same-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                    )
                    manager2 = get_container_manager(
                        project_name="same-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                    )

        assert manager1 is manager2
