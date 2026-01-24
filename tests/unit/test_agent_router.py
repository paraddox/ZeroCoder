"""
Agent Router Unit Tests
=======================

Tests for /api/projects/{project_name}/agent endpoints including:
- Agent status retrieval
- Agent start/stop operations
- Prompt selection logic
- Container management integration
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.routers.agent import (
    validate_project_name,
    get_project_container,
    _get_agent_prompt,
)


class TestValidateProjectName:
    """Tests for validate_project_name function."""

    @pytest.mark.unit
    def test_valid_names(self):
        """Test that valid names pass validation."""
        valid_names = [
            "project",
            "my-project",
            "my_project",
            "Project123",
            "a",
            "a" * 50,
        ]
        for name in valid_names:
            result = validate_project_name(name)
            assert result == name

    @pytest.mark.unit
    def test_invalid_names_raise_exception(self):
        """Test that invalid names raise HTTPException."""
        from fastapi import HTTPException

        invalid_names = [
            "",
            "a" * 51,  # Too long
            "project with spaces",
            "project/slash",
            "../traversal",
            "project@special",
            "project.dot",
        ]
        for name in invalid_names:
            with pytest.raises(HTTPException) as exc_info:
                validate_project_name(name)
            assert exc_info.value.status_code == 400


class TestGetProjectContainer:
    """Tests for get_project_container function."""

    @pytest.mark.unit
    def test_project_not_found(self):
        """Test HTTPException when project not found."""
        from fastapi import HTTPException

        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                get_project_container("nonexistent")

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.unit
    def test_no_git_url(self, tmp_path):
        """Test HTTPException when project has no git URL."""
        from fastapi import HTTPException

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = project_dir

            with patch("server.routers.agent._get_project_git_url") as mock_url:
                mock_url.return_value = None

                with pytest.raises(HTTPException) as exc_info:
                    get_project_container("test-project")

                assert exc_info.value.status_code == 404
                assert "no git url" in exc_info.value.detail.lower()

    @pytest.mark.unit
    def test_directory_not_exists(self, tmp_path):
        """Test HTTPException when project directory doesn't exist."""
        from fastapi import HTTPException

        nonexistent_dir = tmp_path / "nonexistent"

        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = nonexistent_dir

            with patch("server.routers.agent._get_project_git_url") as mock_url:
                mock_url.return_value = "https://github.com/user/repo.git"

                with pytest.raises(HTTPException) as exc_info:
                    get_project_container("test-project")

                assert exc_info.value.status_code == 404
                assert "not found" in exc_info.value.detail.lower()

    @pytest.mark.unit
    def test_returns_container_manager(self, tmp_path):
        """Test successful container manager retrieval."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        mock_manager = MagicMock()

        with patch("server.routers.agent._get_project_path") as mock_path:
            mock_path.return_value = project_dir

            with patch("server.routers.agent._get_project_git_url") as mock_url:
                mock_url.return_value = "https://github.com/user/repo.git"

                with patch("server.routers.agent.get_container_manager") as mock_get:
                    mock_get.return_value = mock_manager

                    result = get_project_container("test-project")

                    assert result == mock_manager
                    mock_get.assert_called_once()


class TestGetAgentPrompt:
    """Tests for _get_agent_prompt function."""

    @pytest.mark.unit
    def test_new_project_no_features_returns_initializer(self, tmp_path):
        """Test new project without features gets initializer prompt."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("server.routers.agent.is_existing_repo_project") as mock_existing:
            mock_existing.return_value = False

            with patch("server.routers.agent.has_features") as mock_has:
                mock_has.return_value = False

                with patch("server.routers.agent.get_initializer_prompt") as mock_init:
                    mock_init.return_value = "Initializer prompt"

                    result = _get_agent_prompt(project_dir, "test-project")

                    assert result == "Initializer prompt"
                    mock_init.assert_called_once_with(project_dir)

    @pytest.mark.unit
    def test_existing_repo_no_features_returns_coding(self, tmp_path):
        """Test existing repo without features gets coding prompt."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("server.routers.agent.is_existing_repo_project") as mock_existing:
            mock_existing.return_value = True

            with patch("server.routers.agent.has_features") as mock_has:
                mock_has.return_value = False

                with patch("server.routers.agent.get_coding_prompt") as mock_coding:
                    mock_coding.return_value = "Coding prompt"

                    result = _get_agent_prompt(project_dir, "test-project")

                    assert result == "Coding prompt"

    @pytest.mark.unit
    def test_open_features_returns_coding_prompt(self, tmp_path):
        """Test project with open features gets coding prompt."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("server.routers.agent.is_existing_repo_project") as mock_existing:
            mock_existing.return_value = False

            with patch("server.routers.agent.has_features") as mock_has:
                mock_has.return_value = True

                with patch("server.routers.agent.has_open_features") as mock_open:
                    mock_open.return_value = True

                    with patch("server.routers.agent.get_coding_prompt") as mock_coding:
                        mock_coding.return_value = "Coding prompt"

                        result = _get_agent_prompt(project_dir, "test-project")

                        assert result == "Coding prompt"

    @pytest.mark.unit
    def test_open_features_yolo_mode_returns_yolo_prompt(self, tmp_path):
        """Test project with open features in yolo mode gets yolo prompt."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("server.routers.agent.is_existing_repo_project") as mock_existing:
            mock_existing.return_value = False

            with patch("server.routers.agent.has_features") as mock_has:
                mock_has.return_value = True

                with patch("server.routers.agent.has_open_features") as mock_open:
                    mock_open.return_value = True

                    with patch("server.routers.agent.get_coding_prompt_yolo") as mock_yolo:
                        mock_yolo.return_value = "Yolo prompt"

                        result = _get_agent_prompt(project_dir, "test-project", yolo_mode=True)

                        assert result == "Yolo prompt"

    @pytest.mark.unit
    def test_all_features_closed_returns_overseer_prompt(self, tmp_path):
        """Test project with all features closed gets overseer prompt."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch("server.routers.agent.is_existing_repo_project") as mock_existing:
            mock_existing.return_value = False

            with patch("server.routers.agent.has_features") as mock_has:
                mock_has.return_value = True

                with patch("server.routers.agent.has_open_features") as mock_open:
                    mock_open.return_value = False

                    with patch("server.routers.agent.get_overseer_prompt") as mock_overseer:
                        mock_overseer.return_value = "Overseer prompt"

                        result = _get_agent_prompt(project_dir, "test-project")

                        assert result == "Overseer prompt"


class TestAgentStatusEndpoint:
    """Tests for GET /agent/status endpoint."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_status_no_container_returns_default(self):
        """Test status returns default when no container exists."""
        from server.routers.agent import get_agent_status

        with patch("server.routers.agent.validate_project_name") as mock_validate:
            mock_validate.return_value = "test-project"

            with patch("server.routers.agent.get_existing_container_manager") as mock_get:
                mock_get.return_value = None

                result = await get_agent_status("test-project")

                assert result.status == "not_created"
                assert result.container_name == "zerocoder-test-project-1"
                assert result.agent_running is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_status_returns_container_status(self):
        """Test status returns actual container status."""
        from server.routers.agent import get_agent_status

        mock_manager = MagicMock()
        mock_manager.started_at = datetime.now()
        mock_manager.get_status_dict.return_value = {
            "status": "running",
            "container_name": "zerocoder-test-1",
            "idle_seconds": 100,
            "agent_running": True,
            "graceful_stop_requested": False,
        }

        with patch("server.routers.agent.validate_project_name") as mock_validate:
            mock_validate.return_value = "test-project"

            with patch("server.routers.agent.get_existing_container_manager") as mock_get:
                mock_get.return_value = mock_manager

                result = await get_agent_status("test-project")

                assert result.status == "running"
                assert result.agent_running is True


class TestAgentStartEndpoint:
    """Tests for POST /agent/start endpoint."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_start_docker_not_available(self):
        """Test start fails when Docker not available."""
        from fastapi import HTTPException
        from server.routers.agent import start_agent
        from server.schemas import AgentStartRequest

        with patch("server.routers.agent.check_docker_available") as mock_docker:
            mock_docker.return_value = False

            with pytest.raises(HTTPException) as exc_info:
                await start_agent("test-project", AgentStartRequest())

            assert exc_info.value.status_code == 503
            assert "docker" in exc_info.value.detail.lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_start_image_not_found(self):
        """Test start fails when container image not found."""
        from fastapi import HTTPException
        from server.routers.agent import start_agent
        from server.schemas import AgentStartRequest

        with patch("server.routers.agent.check_docker_available") as mock_docker:
            mock_docker.return_value = True

            with patch("server.routers.agent.check_image_exists") as mock_image:
                mock_image.return_value = False

                with pytest.raises(HTTPException) as exc_info:
                    await start_agent("test-project", AgentStartRequest())

                assert exc_info.value.status_code == 503
                assert "image" in exc_info.value.detail.lower()


class TestAgentStopEndpoint:
    """Tests for POST /agent/stop endpoint."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_stop_no_container(self):
        """Test stop when no container exists."""
        from server.routers.agent import stop_agent

        mock_manager = MagicMock()
        mock_manager.status = "stopped"
        mock_manager.stop = AsyncMock(return_value=(True, "Container stopped"))

        with patch("server.routers.agent.validate_project_name") as mock_validate:
            mock_validate.return_value = "test-project"

            # Mock _managers to be empty, triggering the fallback path
            with patch("server.services.container_manager._managers", {}):
                with patch("server.routers.agent.get_project_container") as mock_get_container:
                    mock_get_container.return_value = mock_manager

                    result = await stop_agent("test-project")

                    assert result.success is True
                    mock_manager.stop.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_stop_container_success(self):
        """Test successful container stop."""
        from server.routers.agent import stop_agent

        mock_manager = MagicMock()
        mock_manager.status = "stopped"
        mock_manager.stop = AsyncMock(return_value=(True, "Container stopped"))

        with patch("server.routers.agent.validate_project_name") as mock_validate:
            mock_validate.return_value = "test-project"

            # Mock _managers with an existing manager
            with patch("server.services.container_manager._managers", {"test-project": {1: mock_manager}}):
                result = await stop_agent("test-project")

                assert result.success is True
                mock_manager.stop.assert_called_once()


class TestGracefulStopEndpoint:
    """Tests for POST /agent/graceful-stop endpoint."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_graceful_stop_no_container(self):
        """Test graceful stop when no container exists (fallback path)."""
        from server.routers.agent import graceful_stop_agent

        mock_manager = MagicMock()
        mock_manager.status = "stopped"
        mock_manager.graceful_stop = AsyncMock(return_value=(True, "Graceful stop requested"))

        with patch("server.routers.agent.validate_project_name") as mock_validate:
            mock_validate.return_value = "test-project"

            # Mock _managers to be empty, triggering the fallback path
            with patch("server.services.container_manager._managers", {}):
                with patch("server.routers.agent.get_project_container") as mock_get_container:
                    mock_get_container.return_value = mock_manager

                    with patch("server.routers.agent.websocket_manager") as mock_ws:
                        mock_ws.broadcast_to_project = AsyncMock()

                        result = await graceful_stop_agent("test-project")

                        assert result.success is True
                        mock_manager.graceful_stop.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_graceful_stop_success(self):
        """Test successful graceful stop."""
        from server.routers.agent import graceful_stop_agent

        mock_manager = MagicMock()
        mock_manager.status = "running"
        mock_manager.graceful_stop = AsyncMock(return_value=(True, "Graceful stop requested"))

        with patch("server.routers.agent.validate_project_name") as mock_validate:
            mock_validate.return_value = "test-project"

            # Mock _managers with an existing manager
            with patch("server.services.container_manager._managers", {"test-project": {1: mock_manager}}):
                with patch("server.routers.agent.websocket_manager") as mock_ws:
                    mock_ws.broadcast_to_project = AsyncMock()

                    result = await graceful_stop_agent("test-project")

                    assert result.success is True
                    mock_manager.graceful_stop.assert_called_once()


class TestContainerNumberValidation:
    """Tests for container number validation."""

    @pytest.mark.unit
    def test_valid_container_numbers(self, tmp_path):
        """Test valid container numbers."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        for container_num in [0, 1, 2, 5, 10]:
            with patch("server.routers.agent._get_project_path") as mock_path:
                mock_path.return_value = project_dir

                with patch("server.routers.agent._get_project_git_url") as mock_url:
                    mock_url.return_value = "https://github.com/user/repo.git"

                    with patch("server.routers.agent.get_container_manager") as mock_get:
                        mock_get.return_value = MagicMock()

                        result = get_project_container("test-project", container_num)

                        assert result is not None
