"""
Container Manager Unit Tests
============================

Tests for container lifecycle management including:
- Container creation and destruction
- Agent process management
- Health monitoring
- Idle timeout handling
- Output sanitization
"""

import asyncio
import json
import pytest
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Generator

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.services.container_manager import (
    ContainerManager,
    image_exists,
    build_image,
    ensure_image_exists,
    sanitize_output,
    SENSITIVE_PATTERNS,
    IDLE_TIMEOUT_MINUTES,
    CONTAINER_IMAGE,
)


class TestSanitizeOutput:
    """Tests for output sanitization function."""

    @pytest.mark.unit
    def test_redacts_anthropic_api_key(self):
        """Test that Anthropic API keys are redacted."""
        line = "Using API key: sk-ant-api03-abcdefghij1234567890abcdefghij"
        result = sanitize_output(line)
        assert "sk-ant" not in result
        assert "[REDACTED]" in result

    @pytest.mark.unit
    def test_redacts_generic_api_key(self):
        """Test that generic API keys are redacted."""
        lines = [
            "api_key=secret123abc",
            "api-key:supersecret",
            "API_KEY=mysecretkey",
        ]
        for line in lines:
            result = sanitize_output(line)
            assert "[REDACTED]" in result

    @pytest.mark.unit
    def test_redacts_tokens(self):
        """Test that tokens are redacted."""
        lines = [
            "token=abc123secret",
            "TOKEN:mytoken123",
        ]
        for line in lines:
            result = sanitize_output(line)
            assert "[REDACTED]" in result

    @pytest.mark.unit
    def test_redacts_passwords(self):
        """Test that passwords are redacted."""
        lines = [
            "password=mypassword123",
            "PASSWORD:secret",
        ]
        for line in lines:
            result = sanitize_output(line)
            assert "[REDACTED]" in result

    @pytest.mark.unit
    def test_redacts_secrets(self):
        """Test that secrets are redacted."""
        lines = [
            "secret=mysecret123",
            "SECRET:topsecret",
        ]
        for line in lines:
            result = sanitize_output(line)
            assert "[REDACTED]" in result

    @pytest.mark.unit
    def test_preserves_non_sensitive_content(self):
        """Test that non-sensitive content is preserved."""
        line = "Processing file: /path/to/file.py - status: success"
        result = sanitize_output(line)
        assert result == line

    @pytest.mark.unit
    def test_case_insensitive_matching(self):
        """Test that pattern matching is case-insensitive."""
        lines = [
            "API_KEY=secret",
            "api_key=secret",
            "Api_Key=secret",
        ]
        for line in lines:
            result = sanitize_output(line)
            assert "[REDACTED]" in result


class TestImageManagement:
    """Tests for Docker image management functions."""

    @pytest.mark.unit
    def test_image_exists_true(self):
        """Test image_exists returns True when image exists."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = image_exists("test-image")

            assert result is True
            mock_run.assert_called_once()

    @pytest.mark.unit
    def test_image_exists_false(self):
        """Test image_exists returns False when image doesn't exist."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            result = image_exists("nonexistent-image")

            assert result is False

    @pytest.mark.unit
    def test_build_image_success(self, tmp_path):
        """Test successful image build."""
        # Create a mock Dockerfile
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
        """Test build_image when Dockerfile doesn't exist."""
        nonexistent = tmp_path / "nonexistent" / "Dockerfile.project"

        with patch("server.services.container_manager.DOCKERFILE_PATH", nonexistent):
            success, message = build_image("test-image")

        assert success is False
        assert "not found" in message.lower()

    @pytest.mark.unit
    def test_build_image_failure(self, tmp_path):
        """Test build_image when build fails."""
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
        with patch("server.services.container_manager.image_exists") as mock_exists:
            mock_exists.return_value = True

            success, message = ensure_image_exists("test-image")

            assert success is True
            assert "exists" in message.lower()

    @pytest.mark.unit
    def test_ensure_image_exists_builds_when_missing(self, tmp_path):
        """Test ensure_image_exists builds image when missing."""
        dockerfile = tmp_path / "Dockerfile.project"
        dockerfile.write_text("FROM ubuntu:latest")

        with patch("server.services.container_manager.image_exists") as mock_exists:
            mock_exists.return_value = False

            with patch("server.services.container_manager.build_image") as mock_build:
                mock_build.return_value = (True, "Built successfully")

                success, message = ensure_image_exists("test-image")

                assert success is True
                mock_build.assert_called_once()


class TestContainerManager:
    """Tests for ContainerManager class."""

    @pytest.fixture
    def mock_registry(self):
        """Mock registry functions."""
        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = Path("/tmp/projects")
            yield mock_dir

    @pytest.fixture
    def container_manager(self, mock_registry, tmp_path):
        """Create a ContainerManager instance for testing."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

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
    def test_container_naming_coding_container(self, mock_registry, tmp_path):
        """Test container naming for coding containers."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        with patch.object(ContainerManager, "_sync_status"):
            with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                manager = ContainerManager(
                    project_name="my-project",
                    git_url="https://github.com/user/repo.git",
                    container_number=1,
                    project_dir=project_dir,
                    skip_db_persist=True,
                )

        assert manager.container_name == "zerocoder-my-project-1"
        assert not manager._is_init_container

    @pytest.mark.unit
    def test_container_naming_init_container(self, mock_registry, tmp_path):
        """Test container naming for init containers."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir(parents=True)

        with patch.object(ContainerManager, "_sync_status"):
            with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                manager = ContainerManager(
                    project_name="my-project",
                    git_url="https://github.com/user/repo.git",
                    container_number=0,
                    project_dir=project_dir,
                    skip_db_persist=True,
                )

        assert manager.container_name == "zerocoder-my-project-init"
        assert manager._is_init_container

    @pytest.mark.unit
    def test_initial_status(self, container_manager):
        """Test initial container status."""
        assert container_manager._status == "not_created"
        assert container_manager.started_at is None
        assert container_manager.last_activity is None

    @pytest.mark.unit
    def test_get_status_dict(self, container_manager):
        """Test get_status_dict method."""
        status = container_manager.get_status_dict()

        assert "status" in status
        assert "container_name" in status
        assert status["container_name"] == "zerocoder-test-project-1"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_add_output_callback(self, container_manager):
        """Test adding output callback."""
        callback = AsyncMock()

        container_manager.add_output_callback(callback)

        assert callback in container_manager._output_callbacks

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_remove_output_callback(self, container_manager):
        """Test removing output callback."""
        callback = AsyncMock()

        container_manager.add_output_callback(callback)
        container_manager.remove_output_callback(callback)

        assert callback not in container_manager._output_callbacks

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_add_status_callback(self, container_manager):
        """Test adding status callback."""
        callback = AsyncMock()

        container_manager.add_status_callback(callback)

        assert callback in container_manager._status_callbacks

    @pytest.mark.unit
    def test_project_dir_default(self, mock_registry):
        """Test default project directory."""
        with patch.object(ContainerManager, "_sync_status"):
            with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                manager = ContainerManager(
                    project_name="test",
                    git_url="https://github.com/user/repo.git",
                    skip_db_persist=True,
                )

        assert "test" in str(manager.project_dir)


class TestContainerLifecycle:
    """Tests for container lifecycle operations."""

    @pytest.fixture
    def mock_subprocess(self):
        """Mock subprocess calls."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )
            yield mock_run

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a ContainerManager for lifecycle tests."""
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
    def test_is_agent_running_false_when_not_created(self, container_manager):
        """Test is_agent_running returns False when container not created."""
        container_manager._status = "not_created"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")

            result = container_manager.is_agent_running()

            assert result is False

    @pytest.mark.unit
    def test_is_agent_running_true_when_process_exists(self, container_manager):
        """Test is_agent_running returns True when agent process exists."""
        container_manager._status = "running"

        with patch("subprocess.run") as mock_run:
            # First call: docker exec to check process
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="12345",
            )

            result = container_manager.is_agent_running()

            assert result is True


class TestIdleTimeout:
    """Tests for idle timeout functionality."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a ContainerManager for idle timeout tests."""
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
    def test_idle_seconds_calculation(self, container_manager):
        """Test idle seconds calculation."""
        container_manager.last_activity = datetime.now() - timedelta(minutes=5)

        status = container_manager.get_status_dict()

        # Should be approximately 300 seconds (5 minutes)
        assert 290 <= status["idle_seconds"] <= 310

    @pytest.mark.unit
    def test_idle_seconds_zero_when_no_activity(self, container_manager):
        """Test idle seconds is 0 when no activity recorded."""
        container_manager.last_activity = None

        status = container_manager.get_status_dict()

        assert status["idle_seconds"] == 0


class TestCallbackManagement:
    """Tests for callback registration and notification."""

    @pytest.fixture
    def container_manager(self, tmp_path):
        """Create a ContainerManager for callback tests."""
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
    async def test_notify_status_change(self, container_manager):
        """Test status change notification."""
        callback = AsyncMock()
        container_manager.add_status_callback(callback)

        await container_manager._notify_status("running")

        callback.assert_called_once_with("running")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_notify_multiple_callbacks(self, container_manager):
        """Test notification to multiple callbacks."""
        callback1 = AsyncMock()
        callback2 = AsyncMock()

        container_manager.add_status_callback(callback1)
        container_manager.add_status_callback(callback2)

        await container_manager._notify_status("stopped")

        callback1.assert_called_once_with("stopped")
        callback2.assert_called_once_with("stopped")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_callback_error_handling(self, container_manager):
        """Test that callback errors don't break notification."""
        failing_callback = AsyncMock(side_effect=Exception("Callback failed"))
        success_callback = AsyncMock()

        container_manager.add_status_callback(failing_callback)
        container_manager.add_status_callback(success_callback)

        # Should not raise despite failing callback
        await container_manager._notify_status("running")

        # Success callback should still be called
        success_callback.assert_called_once()


class TestContainerManagerRegistry:
    """Tests for container manager registry functions."""

    @pytest.mark.unit
    def test_get_container_manager_creates_new(self, tmp_path):
        """Test get_container_manager creates new manager."""
        from server.services.container_manager import (
            get_container_manager,
            _container_managers,
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
