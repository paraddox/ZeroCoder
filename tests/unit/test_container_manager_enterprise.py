"""
Container Manager Enterprise Tests
==================================

Comprehensive enterprise-grade tests for the container manager including:
- Container lifecycle state machine
- Output sanitization edge cases
- Health monitoring and restart logic
- Resource cleanup
- Async operation handling
- Callback management
"""

import asyncio
import json
import os
import pytest
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call, PropertyMock
from typing import Generator

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Container State Machine Tests
# =============================================================================

class TestContainerStateMachine:
    """Tests for container lifecycle state transitions."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a ContainerManager for state machine tests."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "test-project"
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
        """Test that initial state is 'not_created'."""
        assert container_manager._status == "not_created"
        assert container_manager.status == "not_created"

    @pytest.mark.unit
    def test_status_transitions(self, container_manager):
        """Test valid status transitions."""
        valid_transitions = [
            ("not_created", "running"),
            ("running", "stopped"),
            ("stopped", "running"),
            ("running", "completed"),
        ]

        for from_status, to_status in valid_transitions:
            container_manager._status = from_status
            container_manager._status = to_status
            assert container_manager._status == to_status

    @pytest.mark.unit
    def test_status_property_returns_current_status(self, container_manager):
        """Test that status property returns current status."""
        container_manager._status = "running"
        assert container_manager.status == "running"

        container_manager._status = "stopped"
        assert container_manager.status == "stopped"


# =============================================================================
# Output Sanitization Tests
# =============================================================================

class TestOutputSanitization:
    """Tests for output sanitization."""

    @pytest.mark.unit
    def test_sanitize_anthropic_api_key(self):
        """Test sanitization of Anthropic API keys."""
        from server.services.container_manager import sanitize_output

        # Standard format
        line = "ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxxxxxxxxxx"
        result = sanitize_output(line)
        assert "sk-ant" not in result
        assert "[REDACTED]" in result

    @pytest.mark.unit
    def test_sanitize_generic_sk_key(self):
        """Test sanitization of generic sk- keys."""
        from server.services.container_manager import sanitize_output

        line = "Using key: sk-abcdefghijklmnopqrstuvwxyz123456"
        result = sanitize_output(line)
        assert "sk-abc" not in result
        assert "[REDACTED]" in result

    @pytest.mark.unit
    def test_sanitize_api_key_variations(self):
        """Test sanitization of various API key formats."""
        from server.services.container_manager import sanitize_output

        variations = [
            "api_key=secret123",
            "api-key=secret123",
            "API_KEY=secret123",
            "apikey=secret123",
        ]

        for line in variations:
            result = sanitize_output(line)
            assert "[REDACTED]" in result

    @pytest.mark.unit
    def test_sanitize_token_variations(self):
        """Test sanitization of token formats."""
        from server.services.container_manager import sanitize_output

        variations = [
            "token=abc123secret",
            "TOKEN=abc123secret",
            "token:abc123secret",
        ]

        for line in variations:
            result = sanitize_output(line)
            assert "[REDACTED]" in result

    @pytest.mark.unit
    def test_sanitize_password_variations(self):
        """Test sanitization of password formats."""
        from server.services.container_manager import sanitize_output

        variations = [
            "password=mysecretpass",
            "PASSWORD=mysecretpass",
            "password:mysecretpass",
        ]

        for line in variations:
            result = sanitize_output(line)
            assert "[REDACTED]" in result

    @pytest.mark.unit
    def test_sanitize_secret_variations(self):
        """Test sanitization of secret formats."""
        from server.services.container_manager import sanitize_output

        variations = [
            "secret=topsecret",
            "SECRET=topsecret",
            "secret:topsecret",
        ]

        for line in variations:
            result = sanitize_output(line)
            assert "[REDACTED]" in result

    @pytest.mark.unit
    def test_preserves_normal_output(self):
        """Test that normal output is preserved."""
        from server.services.container_manager import sanitize_output

        normal_lines = [
            "Processing file: /path/to/file.py",
            "Test passed: 42 assertions",
            "Building component: UserAuth",
            "Status: success",
        ]

        for line in normal_lines:
            result = sanitize_output(line)
            assert result == line

    @pytest.mark.unit
    def test_multiple_secrets_in_one_line(self):
        """Test sanitization when multiple secrets in one line."""
        from server.services.container_manager import sanitize_output

        line = "api_key=secret1 token=secret2 password=secret3"
        result = sanitize_output(line)
        assert result.count("[REDACTED]") == 3

    @pytest.mark.unit
    def test_case_insensitive_matching(self):
        """Test that sanitization is case-insensitive."""
        from server.services.container_manager import sanitize_output

        lines = [
            "API_KEY=secret",
            "Api_Key=secret",
            "api_key=secret",
            "aPi_KeY=secret",
        ]

        for line in lines:
            result = sanitize_output(line)
            assert "[REDACTED]" in result


# =============================================================================
# Image Management Tests
# =============================================================================

class TestImageManagement:
    """Tests for Docker image management."""

    @pytest.mark.unit
    def test_image_exists_returns_true(self):
        """Test image_exists returns True when image exists."""
        from server.services.container_manager import image_exists

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = image_exists("test-image")
            assert result is True

    @pytest.mark.unit
    def test_image_exists_returns_false(self):
        """Test image_exists returns False when image doesn't exist."""
        from server.services.container_manager import image_exists

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            result = image_exists("nonexistent")
            assert result is False

    @pytest.mark.unit
    def test_build_image_success(self, tmp_path):
        """Test successful image build."""
        from server.services.container_manager import build_image, DOCKERFILE_PATH

        dockerfile = tmp_path / "Dockerfile.project"
        dockerfile.write_text("FROM ubuntu:latest")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            with patch("server.services.container_manager.DOCKERFILE_PATH", dockerfile):
                success, message = build_image("test-image")

            assert success is True
            assert "successfully" in message.lower()

    @pytest.mark.unit
    def test_build_image_dockerfile_not_found(self, tmp_path):
        """Test build_image when Dockerfile missing."""
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
            mock_run.return_value = MagicMock(returncode=1, stderr="Build error")
            with patch("server.services.container_manager.DOCKERFILE_PATH", dockerfile):
                success, message = build_image("test-image")

        assert success is False
        assert "failed" in message.lower()

    @pytest.mark.unit
    def test_ensure_image_exists_when_present(self):
        """Test ensure_image_exists when image already present."""
        from server.services.container_manager import ensure_image_exists

        with patch("server.services.container_manager.image_exists") as mock_exists:
            mock_exists.return_value = True
            success, message = ensure_image_exists("test-image")

        assert success is True
        assert "exists" in message.lower()

    @pytest.mark.unit
    def test_ensure_image_exists_builds_when_missing(self):
        """Test ensure_image_exists builds when missing."""
        from server.services.container_manager import ensure_image_exists

        with patch("server.services.container_manager.image_exists") as mock_exists:
            mock_exists.return_value = False
            with patch("server.services.container_manager.build_image") as mock_build:
                mock_build.return_value = (True, "Built")
                success, message = ensure_image_exists("test-image")

        assert success is True
        mock_build.assert_called_once()


# =============================================================================
# Container Naming Tests
# =============================================================================

class TestContainerNaming:
    """Tests for container naming conventions."""

    @pytest.fixture
    def manager_factory(self, tmp_path):
        """Factory for creating container managers."""
        from server.services.container_manager import ContainerManager

        def create(project_name, container_number):
            project_dir = tmp_path / project_name
            project_dir.mkdir(parents=True, exist_ok=True)

            with patch("server.services.container_manager.get_projects_dir") as mock_dir:
                mock_dir.return_value = tmp_path

                with patch.object(ContainerManager, "_sync_status"):
                    with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                        return ContainerManager(
                            project_name=project_name,
                            git_url="https://github.com/user/repo.git",
                            container_number=container_number,
                            project_dir=project_dir,
                            skip_db_persist=True,
                        )
        return create

    @pytest.mark.unit
    def test_init_container_naming(self, manager_factory):
        """Test init container (0) naming."""
        manager = manager_factory("my-project", 0)
        assert manager.container_name == "zerocoder-my-project-init"
        assert manager._is_init_container is True

    @pytest.mark.unit
    def test_coding_container_naming(self, manager_factory):
        """Test coding container naming."""
        manager = manager_factory("my-project", 1)
        assert manager.container_name == "zerocoder-my-project-1"
        assert manager._is_init_container is False

        manager5 = manager_factory("my-project", 5)
        assert manager5.container_name == "zerocoder-my-project-5"

    @pytest.mark.unit
    def test_container_name_with_hyphen_project(self, manager_factory):
        """Test container naming with hyphenated project name."""
        manager = manager_factory("my-cool-project", 1)
        assert manager.container_name == "zerocoder-my-cool-project-1"

    @pytest.mark.unit
    def test_container_name_with_underscore_project(self, manager_factory):
        """Test container naming with underscored project name."""
        manager = manager_factory("my_project", 1)
        assert manager.container_name == "zerocoder-my_project-1"


# =============================================================================
# Callback Management Tests
# =============================================================================

class TestCallbackManagement:
    """Tests for callback registration and notification."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a ContainerManager for callback tests."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "callback-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path

            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="callback-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    def test_add_output_callback(self, container_manager):
        """Test adding output callback."""
        callback = AsyncMock()
        container_manager.add_output_callback(callback)
        assert callback in container_manager._output_callbacks

    @pytest.mark.unit
    def test_remove_output_callback(self, container_manager):
        """Test removing output callback."""
        callback = AsyncMock()
        container_manager.add_output_callback(callback)
        container_manager.remove_output_callback(callback)
        assert callback not in container_manager._output_callbacks

    @pytest.mark.unit
    def test_add_status_callback(self, container_manager):
        """Test adding status callback."""
        callback = AsyncMock()
        container_manager.add_status_callback(callback)
        assert callback in container_manager._status_callbacks

    @pytest.mark.unit
    def test_remove_status_callback(self, container_manager):
        """Test removing status callback."""
        callback = AsyncMock()
        container_manager.add_status_callback(callback)
        container_manager.remove_status_callback(callback)
        assert callback not in container_manager._status_callbacks

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_notify_status_change_calls_callbacks(self, container_manager):
        """Test that status change notifies all callbacks."""
        callback1 = AsyncMock()
        callback2 = AsyncMock()

        container_manager.add_status_callback(callback1)
        container_manager.add_status_callback(callback2)

        container_manager._notify_status_change("running")

        await asyncio.sleep(0.1)

        callback1.assert_called_once_with("running")
        callback2.assert_called_once_with("running")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_callback_error_doesnt_break_notifications(self, container_manager):
        """Test that one failing callback doesn't break others."""
        failing_callback = AsyncMock(side_effect=Exception("Callback error"))
        success_callback = AsyncMock()

        container_manager.add_status_callback(failing_callback)
        container_manager.add_status_callback(success_callback)

        # Should not raise
        container_manager._notify_status_change("running")

        await asyncio.sleep(0.1)

        success_callback.assert_called_once()


# =============================================================================
# Status Dict Tests
# =============================================================================

class TestStatusDict:
    """Tests for get_status_dict method."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a ContainerManager for status dict tests."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "status-dict-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path

            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="status-dict-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    def test_status_dict_contains_required_fields(self, container_manager):
        """Test that status dict contains all required fields."""
        status = container_manager.get_status_dict()

        required_fields = [
            "status",
            "container_name",
            "container_number",
            "idle_seconds",
        ]

        for field in required_fields:
            assert field in status, f"Missing field: {field}"

    @pytest.mark.unit
    def test_status_dict_values(self, container_manager):
        """Test status dict values."""
        status = container_manager.get_status_dict()

        assert status["status"] == "not_created"
        assert status["container_name"] == "zerocoder-status-dict-test-1"
        assert status["container_number"] == 1

    @pytest.mark.unit
    def test_idle_seconds_calculation(self, container_manager):
        """Test idle seconds calculation."""
        # No activity yet
        status = container_manager.get_status_dict()
        assert status["idle_seconds"] == 0

        # Set last activity to 5 minutes ago
        container_manager.last_activity = datetime.now() - timedelta(minutes=5)
        status = container_manager.get_status_dict()
        assert 290 <= status["idle_seconds"] <= 310


# =============================================================================
# Agent Running Detection Tests
# =============================================================================

class TestAgentRunningDetection:
    """Tests for is_agent_running method."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a ContainerManager for agent detection tests."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "agent-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path

            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="agent-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    def test_agent_not_running_when_container_not_created(self, container_manager):
        """Test agent not running when container not created."""
        container_manager._status = "not_created"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = container_manager.is_agent_running()

        assert result is False

    @pytest.mark.unit
    def test_agent_running_when_process_exists(self, container_manager):
        """Test agent running when process exists."""
        container_manager._status = "running"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="12345")
            result = container_manager.is_agent_running()

        assert result is True

    @pytest.mark.unit
    def test_agent_not_running_when_no_process(self, container_manager):
        """Test agent not running when no process found."""
        container_manager._status = "running"

        with patch("subprocess.run") as mock_run:
            # Empty stdout means no process
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            result = container_manager.is_agent_running()

        assert result is False


# =============================================================================
# Container Manager Registry Tests
# =============================================================================

class TestContainerManagerRegistry:
    """Tests for container manager registry functions."""

    @pytest.mark.unit
    def test_get_container_manager_creates_new(self, tmp_path):
        """Test that get_container_manager creates new manager."""
        from server.services.container_manager import (
            get_container_manager,
            _container_managers,
            ContainerManager,
        )

        project_dir = tmp_path / "new-project"
        project_dir.mkdir(parents=True)

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

    @pytest.mark.unit
    def test_get_container_manager_returns_existing(self, tmp_path):
        """Test that get_container_manager returns existing manager."""
        from server.services.container_manager import (
            get_container_manager,
            _container_managers,
            ContainerManager,
        )

        project_dir = tmp_path / "existing-project"
        project_dir.mkdir(parents=True)

        _container_managers.clear()

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path

            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager1 = get_container_manager(
                        project_name="existing-project",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                    )
                    manager2 = get_container_manager(
                        project_name="existing-project",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                    )

        assert manager1 is manager2

    @pytest.mark.unit
    def test_get_existing_manager_returns_none(self):
        """Test that get_existing_container_manager returns None when not found."""
        from server.services.container_manager import (
            get_existing_container_manager,
            _container_managers,
        )

        _container_managers.clear()

        manager = get_existing_container_manager("nonexistent", container_number=1)
        assert manager is None


# =============================================================================
# Idle Timeout Tests
# =============================================================================

class TestIdleTimeout:
    """Tests for idle timeout functionality."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a ContainerManager for idle timeout tests."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "idle-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path

            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="idle-test",
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
        result = container_manager.is_idle()
        assert result is False

    @pytest.mark.unit
    def test_is_idle_false_when_recent_activity(self, container_manager):
        """Test is_idle returns False with recent activity."""
        container_manager.last_activity = datetime.now() - timedelta(minutes=5)
        result = container_manager.is_idle()
        assert result is False

    @pytest.mark.unit
    def test_is_idle_true_when_exceeded_timeout(self, container_manager):
        """Test is_idle returns True when timeout exceeded."""
        from server.services.container_manager import IDLE_TIMEOUT_MINUTES

        container_manager.last_activity = datetime.now() - timedelta(minutes=IDLE_TIMEOUT_MINUTES + 1)
        result = container_manager.is_idle()
        assert result is True


# =============================================================================
# Graceful Stop Tests
# =============================================================================

class TestGracefulStop:
    """Tests for graceful stop functionality."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a ContainerManager for graceful stop tests."""
        from server.services.container_manager import ContainerManager

        project_dir = tmp_path / "graceful-test"
        project_dir.mkdir(parents=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path

            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    manager = ContainerManager(
                        project_name="graceful-test",
                        git_url="https://github.com/user/repo.git",
                        container_number=1,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
        return manager

    @pytest.mark.unit
    def test_graceful_stop_requested_initially_false(self, container_manager):
        """Test graceful stop requested is initially False."""
        assert container_manager._graceful_stop_requested is False

    @pytest.mark.unit
    def test_graceful_stop_flag_can_be_set(self, container_manager):
        """Test graceful stop flag can be set directly."""
        container_manager._graceful_stop_requested = True
        assert container_manager._graceful_stop_requested is True


# =============================================================================
# Agent Type Tests
# =============================================================================

class TestAgentTypes:
    """Tests for agent type tracking."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a ContainerManager for agent type tests."""
        from server.services.container_manager import ContainerManager

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
        """Test default agent type is 'coder'."""
        assert container_manager._current_agent_type == "coder"

    @pytest.mark.unit
    def test_agent_type_can_be_set(self, container_manager):
        """Test agent type can be changed."""
        container_manager._current_agent_type = "overseer"
        assert container_manager._current_agent_type == "overseer"

        container_manager._current_agent_type = "hound"
        assert container_manager._current_agent_type == "hound"
