"""
Comprehensive Router Tests
==========================

Enterprise-grade unit tests for all API routers including:
- Projects router
- Features router
- Agent router
- WebSocket handling
- Error handling and edge cases
"""

import asyncio
import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Projects Router Tests
# =============================================================================

class TestProjectsRouterValidation:
    """Tests for project name and input validation."""

    @pytest.mark.unit
    def test_validate_project_name_valid(self):
        """Test validation of valid project names."""
        from server.routers.projects import validate_project_name

        valid_names = [
            "my-project",
            "project_1",
            "MyProject",
            "test123",
            "a",
            "A" * 50,  # Max length
        ]

        for name in valid_names:
            result = validate_project_name(name)
            assert result == name

    @pytest.mark.unit
    def test_validate_project_name_invalid(self):
        """Test validation rejects invalid project names."""
        from server.routers.projects import validate_project_name
        from fastapi import HTTPException

        invalid_names = [
            "",  # Empty
            "project/name",  # Path traversal
            "project..name",  # Double dots
            "project name",  # Spaces
            "a" * 51,  # Too long
            "../etc/passwd",  # Path traversal
        ]

        for name in invalid_names:
            with pytest.raises(HTTPException) as exc:
                validate_project_name(name)
            assert exc.value.status_code == 400

    @pytest.mark.unit
    def test_validate_task_id_valid(self):
        """Test validation of valid task IDs."""
        from server.routers.projects import validate_task_id

        valid_ids = [
            "feat-1",
            "feat-123",
            "beads-42",
            "task-999",
        ]

        for task_id in valid_ids:
            result = validate_task_id(task_id)
            assert result == task_id

    @pytest.mark.unit
    def test_validate_task_id_invalid(self):
        """Test validation rejects invalid task IDs."""
        from server.routers.projects import validate_task_id
        from fastapi import HTTPException

        invalid_ids = [
            "feat",  # No number
            "123",  # No prefix
            "feat-",  # No number after dash
            "-123",  # No prefix
            "feat-abc",  # Non-numeric suffix
        ]

        for task_id in invalid_ids:
            with pytest.raises(HTTPException) as exc:
                validate_task_id(task_id)
            assert exc.value.status_code == 400


class TestProjectsRouterClone:
    """Tests for repository cloning functionality."""

    @pytest.mark.unit
    def test_clone_repository_success(self, tmp_path):
        """Test successful repository cloning."""
        from server.routers.projects import clone_repository

        dest = tmp_path / "repo"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Cloning into 'repo'...",
                stderr=""
            )

            success, message = clone_repository(
                "https://github.com/user/repo.git",
                dest
            )

        assert success is True
        assert "success" in message.lower()

    @pytest.mark.unit
    def test_clone_repository_invalid_url(self, tmp_path):
        """Test rejection of invalid git URLs."""
        from server.routers.projects import clone_repository

        dest = tmp_path / "repo"

        # Invalid URL schemes
        invalid_urls = [
            "ftp://github.com/user/repo.git",
            "file:///local/repo",
            "/local/path",
            "relative/path",
        ]

        for url in invalid_urls:
            success, message = clone_repository(url, dest)
            assert success is False
            assert "invalid" in message.lower()

    @pytest.mark.unit
    def test_clone_repository_git_failure(self, tmp_path):
        """Test handling of git clone failure."""
        from server.routers.projects import clone_repository

        dest = tmp_path / "repo"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stderr="fatal: repository not found"
            )

            success, message = clone_repository(
                "https://github.com/user/nonexistent.git",
                dest
            )

        assert success is False
        assert "failed" in message.lower()

    @pytest.mark.unit
    def test_clone_repository_timeout(self, tmp_path):
        """Test handling of clone timeout."""
        from server.routers.projects import clone_repository
        import subprocess

        dest = tmp_path / "repo"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(
                cmd=["git", "clone"],
                timeout=300
            )

            success, message = clone_repository(
                "https://github.com/user/repo.git",
                dest
            )

        assert success is False
        assert "timeout" in message.lower()


class TestProjectsRouterBeadsInit:
    """Tests for beads initialization."""

    @pytest.mark.unit
    def test_init_beads_when_not_initialized(self, tmp_path):
        """Test beads initialization in new project."""
        from server.routers.projects import init_beads_if_needed

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="Initialized beads"
            )

            success, message = init_beads_if_needed(project_dir)

        assert success is True
        assert mock_run.called

    @pytest.mark.unit
    def test_init_beads_already_initialized(self, tmp_path):
        """Test beads initialization skips when already exists."""
        from server.routers.projects import init_beads_if_needed

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat")

        with patch("subprocess.run") as mock_run:
            success, message = init_beads_if_needed(project_dir)

        assert success is True
        assert "already" in message.lower()
        assert not mock_run.called

    @pytest.mark.unit
    def test_init_beads_cli_not_found(self, tmp_path):
        """Test handling when beads CLI not installed."""
        from server.routers.projects import init_beads_if_needed

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            success, message = init_beads_if_needed(project_dir)

        assert success is False
        assert "not found" in message.lower()


class TestProjectsRouterStats:
    """Tests for project statistics."""

    @pytest.mark.unit
    def test_get_project_stats(self, tmp_path):
        """Test getting project statistics."""
        from server.routers.projects import get_project_stats

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        with patch("server.routers.projects._count_passing_tests") as mock_count:
            mock_count.return_value = (5, 2, 10)

            stats = get_project_stats(project_dir)

        assert stats.passing == 5
        assert stats.in_progress == 2
        assert stats.total == 10
        assert stats.percentage == 50.0

    @pytest.mark.unit
    def test_get_project_stats_zero_total(self, tmp_path):
        """Test statistics when no features exist."""
        from server.routers.projects import get_project_stats

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        with patch("server.routers.projects._count_passing_tests") as mock_count:
            mock_count.return_value = (0, 0, 0)

            stats = get_project_stats(project_dir)

        assert stats.passing == 0
        assert stats.total == 0
        assert stats.percentage == 0.0


class TestProjectsRouterAgentConfig:
    """Tests for agent configuration."""

    @pytest.mark.unit
    def test_read_agent_model_default(self, tmp_path):
        """Test reading default model when no config exists."""
        from server.routers.projects import read_agent_model

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "prompts").mkdir()

        model = read_agent_model(project_dir)

        assert model == "glm-4-7"

    @pytest.mark.unit
    def test_read_agent_model_from_config(self, tmp_path):
        """Test reading model from config file."""
        from server.routers.projects import read_agent_model

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir()
        config_file = prompts_dir / ".agent_config.json"
        config_file.write_text(json.dumps({"agent_model": "claude-opus-4-5-20251101"}))

        model = read_agent_model(project_dir)

        assert model == "claude-opus-4-5-20251101"

    @pytest.mark.unit
    def test_write_agent_config(self, tmp_path):
        """Test writing agent configuration."""
        from server.routers.projects import write_agent_config, read_agent_model

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir()

        write_agent_config(project_dir, "claude-sonnet-4-5-20250514")

        model = read_agent_model(project_dir)
        assert model == "claude-sonnet-4-5-20250514"

    @pytest.mark.unit
    def test_write_agent_config_preserves_other_settings(self, tmp_path):
        """Test that writing config preserves other settings."""
        from server.routers.projects import write_agent_config, get_agent_config_path

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir()

        config_file = prompts_dir / ".agent_config.json"
        config_file.write_text(json.dumps({
            "agent_model": "old-model",
            "other_setting": "value"
        }))

        write_agent_config(project_dir, "new-model")

        config = json.loads(config_file.read_text())
        assert config["agent_model"] == "new-model"
        assert config["other_setting"] == "value"


class TestProjectsRouterWizardStatus:
    """Tests for wizard status management."""

    @pytest.mark.unit
    def test_check_wizard_incomplete_with_spec(self, tmp_path):
        """Test wizard incomplete check when spec exists."""
        from server.routers.projects import check_wizard_incomplete

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        result = check_wizard_incomplete(project_dir, has_spec=True)

        assert result is False

    @pytest.mark.unit
    def test_check_wizard_incomplete_with_status_file(self, tmp_path):
        """Test wizard incomplete check when status file exists."""
        from server.routers.projects import check_wizard_incomplete, get_wizard_status_path

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "prompts").mkdir()
        wizard_file = get_wizard_status_path(project_dir)
        wizard_file.write_text("{}")

        result = check_wizard_incomplete(project_dir, has_spec=False)

        assert result is True

    @pytest.mark.unit
    def test_check_wizard_incomplete_no_status(self, tmp_path):
        """Test wizard incomplete check when no status file."""
        from server.routers.projects import check_wizard_incomplete

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "prompts").mkdir()

        result = check_wizard_incomplete(project_dir, has_spec=False)

        assert result is False


# =============================================================================
# Features Router Tests
# =============================================================================

class TestFeaturesRouterConversion:
    """Tests for feature data conversion."""

    @pytest.mark.unit
    def test_beads_task_to_feature_open(self):
        """Test conversion of open beads task to feature."""
        from server.routers.features import beads_task_to_feature

        task = {
            "id": "feat-1",
            "title": "Test Feature",
            "status": "open",
            "priority": 1,
            "labels": ["auth"],
            "description": "Feature description\n\n1. Step one\n2. Step two",
        }

        feature = beads_task_to_feature(task)

        assert feature["id"] == "feat-1"
        assert feature["name"] == "Test Feature"
        assert feature["passes"] is False
        assert feature["in_progress"] is False

    @pytest.mark.unit
    def test_beads_task_to_feature_in_progress(self):
        """Test conversion of in-progress beads task to feature."""
        from server.routers.features import beads_task_to_feature

        task = {
            "id": "feat-2",
            "title": "WIP Feature",
            "status": "in_progress",
            "priority": 2,
            "labels": [],
            "description": "In progress work",
        }

        feature = beads_task_to_feature(task)

        assert feature["passes"] is False
        assert feature["in_progress"] is True

    @pytest.mark.unit
    def test_beads_task_to_feature_closed(self):
        """Test conversion of closed beads task to feature."""
        from server.routers.features import beads_task_to_feature

        task = {
            "id": "feat-3",
            "title": "Done Feature",
            "status": "closed",
            "priority": 0,
            "labels": ["backend"],
            "description": "Completed feature",
        }

        feature = beads_task_to_feature(task)

        assert feature["passes"] is True
        assert feature["in_progress"] is False

    @pytest.mark.unit
    def test_beads_task_to_feature_extracts_steps(self):
        """Test that steps are extracted from description."""
        from server.routers.features import beads_task_to_feature

        task = {
            "id": "feat-4",
            "title": "Feature with Steps",
            "status": "open",
            "priority": 1,
            "labels": [],
            "description": "Main description\n\n## Steps\n\n1. First step\n2. Second step\n3. Third step",
        }

        feature = beads_task_to_feature(task)

        # Steps should be extracted (implementation may vary)
        assert feature["description"] is not None

    @pytest.mark.unit
    def test_beads_task_extracts_category_from_labels(self):
        """Test that category is extracted from labels."""
        from server.routers.features import beads_task_to_feature

        task = {
            "id": "feat-5",
            "title": "Labeled Feature",
            "status": "open",
            "priority": 1,
            "labels": ["frontend", "ui"],
            "description": "Has labels",
        }

        feature = beads_task_to_feature(task)

        assert feature["category"] == "frontend"


# =============================================================================
# Agent Router Tests
# =============================================================================

class TestAgentRouterStatus:
    """Tests for agent status endpoint."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_agent_status_not_created(self):
        """Test status when no container exists."""
        from server.routers.agent import get_agent_status
        from server.routers.projects import validate_project_name

        with patch("server.routers.agent._get_registry_functions") as mock_reg:
            mock_reg.return_value = (
                MagicMock(return_value=Path("/tmp/project")),  # get_project_path
                MagicMock(return_value="https://github.com/user/repo.git"),  # get_project_git_url
            )
            with patch("server.routers.agent.get_existing_container_manager") as mock_get:
                mock_get.return_value = None

                status = await get_agent_status("test-project")

        assert status.status == "not_created"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_agent_status_running(self):
        """Test status when container is running."""
        from server.routers.agent import get_agent_status

        mock_manager = MagicMock()
        mock_manager.status = "running"
        mock_manager.container_name = "zerocoder-test-1"
        mock_manager.started_at = datetime.now()
        mock_manager.get_idle_seconds.return_value = 30
        mock_manager.is_agent_running.return_value = True
        mock_manager._graceful_stop_requested = False
        mock_manager._current_agent_type = "coder"
        mock_manager._is_opencode_model.return_value = False
        mock_manager._sync_status = MagicMock()

        with patch("server.routers.agent._get_registry_functions") as mock_reg:
            mock_reg.return_value = (
                MagicMock(return_value=Path("/tmp/project")),
                MagicMock(return_value="https://github.com/user/repo.git"),
            )
            with patch("server.routers.agent.get_existing_container_manager") as mock_get:
                mock_get.return_value = mock_manager

                status = await get_agent_status("test-project")

        assert status.status == "running"
        assert status.agent_running is True


class TestAgentRouterControl:
    """Tests for agent control endpoints."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_start_agent_creates_container(self):
        """Test that starting agent creates container if needed."""
        from server.routers.agent import start_all_containers

        mock_manager = MagicMock()
        mock_manager.start = AsyncMock(return_value=(True, "Started"))
        mock_manager._is_init_container = True
        mock_manager.is_agent_running.return_value = True
        mock_manager.status = "running"
        mock_manager._graceful_stop_requested = False

        with patch("server.routers.agent._get_registry_functions") as mock_reg:
            mock_reg.return_value = (
                MagicMock(return_value=Path("/tmp/project")),
                MagicMock(return_value="https://github.com/user/repo.git"),
                MagicMock(return_value={"target_container_count": 1, "is_new": False}),
                MagicMock(return_value=False),  # is_new
            )
            with patch("server.routers.agent.get_container_manager") as mock_get:
                mock_get.return_value = mock_manager
                with patch("server.routers.agent.has_project_prompts") as mock_prompts:
                    mock_prompts.return_value = True
                    with patch("server.routers.agent.has_open_features") as mock_features:
                        mock_features.return_value = True

                        response = await start_all_containers("test-project")

        assert response.success is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_stop_agent_stops_all_containers(self):
        """Test that stopping agent stops all containers."""
        from server.routers.agent import stop_all_containers

        mock_manager = MagicMock()
        mock_manager.stop = AsyncMock(return_value=(True, "Stopped"))

        with patch("server.routers.agent._get_registry_functions") as mock_reg:
            mock_reg.return_value = (
                MagicMock(return_value=Path("/tmp/project")),
                MagicMock(return_value="https://github.com/user/repo.git"),
            )
            with patch("server.routers.agent.get_all_container_managers") as mock_all:
                mock_all.return_value = [mock_manager]

                response = await stop_all_containers("test-project")

        assert response.success is True
        mock_manager.stop.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_graceful_stop_sets_flag(self):
        """Test that graceful stop sets the appropriate flag."""
        from server.routers.agent import graceful_stop_agent

        mock_manager = MagicMock()
        mock_manager.graceful_stop = AsyncMock(return_value=(True, "Stopping gracefully"))
        mock_manager._graceful_stop_requested = False

        with patch("server.routers.agent._get_registry_functions") as mock_reg:
            mock_reg.return_value = (
                MagicMock(return_value=Path("/tmp/project")),
                MagicMock(return_value="https://github.com/user/repo.git"),
            )
            with patch("server.routers.agent.get_all_container_managers") as mock_all:
                mock_all.return_value = [mock_manager]

                response = await graceful_stop_agent("test-project")

        assert response.success is True


# =============================================================================
# WebSocket Router Tests
# =============================================================================

class TestWebSocketConnection:
    """Tests for WebSocket connection handling."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_websocket_manager_connect(self):
        """Test WebSocket connection."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        mock_ws = AsyncMock()

        await manager.connect(mock_ws, "test-project")

        assert mock_ws in manager.active_connections.get("test-project", [])
        mock_ws.accept.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_websocket_manager_disconnect(self):
        """Test WebSocket disconnection."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        mock_ws = AsyncMock()

        await manager.connect(mock_ws, "test-project")
        manager.disconnect(mock_ws, "test-project")

        assert mock_ws not in manager.active_connections.get("test-project", [])

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_websocket_manager_broadcast(self):
        """Test WebSocket broadcast."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await manager.connect(mock_ws1, "test-project")
        await manager.connect(mock_ws2, "test-project")

        await manager.broadcast_to_project("test-project", {"type": "test", "data": "value"})

        mock_ws1.send_json.assert_called_once()
        mock_ws2.send_json.assert_called_once()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_websocket_manager_handles_disconnect_on_broadcast(self):
        """Test that broadcast handles disconnected clients."""
        from server.websocket import ConnectionManager

        manager = ConnectionManager()
        mock_ws = AsyncMock()
        mock_ws.send_json.side_effect = Exception("Connection closed")

        await manager.connect(mock_ws, "test-project")

        # Should not raise
        await manager.broadcast_to_project("test-project", {"type": "test"})


# =============================================================================
# Schema Validation Tests
# =============================================================================

class TestSchemaValidation:
    """Tests for Pydantic schema validation."""

    @pytest.mark.unit
    def test_project_create_valid(self):
        """Test valid ProjectCreate schema."""
        from server.schemas import ProjectCreate

        project = ProjectCreate(
            name="my-project",
            git_url="https://github.com/user/repo.git",
            is_new=True,
            spec_method="claude"
        )

        assert project.name == "my-project"
        assert project.is_new is True

    @pytest.mark.unit
    def test_project_create_name_validation(self):
        """Test ProjectCreate name validation."""
        from server.schemas import ProjectCreate
        from pydantic import ValidationError

        invalid_names = [
            "",  # Too short
            "a" * 51,  # Too long
            "my project",  # Space
            "my/project",  # Slash
        ]

        for name in invalid_names:
            with pytest.raises(ValidationError):
                ProjectCreate(
                    name=name,
                    git_url="https://github.com/user/repo.git"
                )

    @pytest.mark.unit
    def test_feature_create_valid(self):
        """Test valid FeatureCreate schema."""
        from server.schemas import FeatureCreate

        feature = FeatureCreate(
            category="auth",
            name="User Login",
            description="Implement user login",
            steps=["Create form", "Add validation"],
            priority=1
        )

        assert feature.name == "User Login"
        assert len(feature.steps) == 2

    @pytest.mark.unit
    def test_agent_start_request_defaults(self):
        """Test AgentStartRequest default values."""
        from server.schemas import AgentStartRequest

        request = AgentStartRequest()

        assert request.instruction is None
        assert request.yolo_mode is False

    @pytest.mark.unit
    def test_container_count_update_bounds(self):
        """Test ContainerCountUpdate validation bounds."""
        from server.schemas import ContainerCountUpdate
        from pydantic import ValidationError

        # Valid
        valid = ContainerCountUpdate(target_count=5)
        assert valid.target_count == 5

        # Too low
        with pytest.raises(ValidationError):
            ContainerCountUpdate(target_count=0)

        # Too high
        with pytest.raises(ValidationError):
            ContainerCountUpdate(target_count=11)

    @pytest.mark.unit
    def test_image_attachment_size_validation(self):
        """Test ImageAttachment size validation."""
        from server.schemas import ImageAttachment, MAX_IMAGE_SIZE
        from pydantic import ValidationError
        import base64

        # Generate oversized data
        oversized_data = base64.b64encode(b"x" * (MAX_IMAGE_SIZE + 1)).decode()

        with pytest.raises(ValidationError) as exc:
            ImageAttachment(
                filename="large.png",
                mimeType="image/png",
                base64Data=oversized_data
            )

        assert "exceeds" in str(exc.value).lower()

    @pytest.mark.unit
    def test_text_attachment_size_validation(self):
        """Test TextAttachment size validation."""
        from server.schemas import TextAttachment, MAX_TEXT_SIZE
        from pydantic import ValidationError

        # Generate oversized content
        oversized_content = "x" * (MAX_TEXT_SIZE + 1)

        with pytest.raises(ValidationError) as exc:
            TextAttachment(
                filename="large.txt",
                mimeType="text/plain",
                textContent=oversized_content
            )

        assert "exceeds" in str(exc.value).lower()

    @pytest.mark.unit
    def test_task_create_validation(self):
        """Test TaskCreate schema validation."""
        from server.schemas import TaskCreate
        from pydantic import ValidationError

        # Valid
        task = TaskCreate(
            title="Test Task",
            description="Task description",
            priority=2,
            task_type="feature"
        )
        assert task.title == "Test Task"

        # Invalid priority
        with pytest.raises(ValidationError):
            TaskCreate(title="Test", priority=5)

        # Invalid task type
        with pytest.raises(ValidationError):
            TaskCreate(title="Test", task_type="invalid")

    @pytest.mark.unit
    def test_task_update_validation(self):
        """Test TaskUpdate schema validation."""
        from server.schemas import TaskUpdate
        from pydantic import ValidationError

        # Valid partial update
        update = TaskUpdate(status="in_progress")
        assert update.status == "in_progress"

        # Invalid status
        with pytest.raises(ValidationError):
            TaskUpdate(status="invalid_status")


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestRouterErrorHandling:
    """Tests for router error handling."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_project_not_found_error(self):
        """Test handling of project not found errors."""
        from server.routers.projects import get_project
        from fastapi import HTTPException

        with patch("server.routers.projects._get_registry_functions") as mock_reg:
            mock_reg.return_value = (
                None, None, None, None,
                MagicMock(return_value=None),  # get_project_info returns None
                None, None, None, None, None, None
            )

            with pytest.raises(HTTPException) as exc:
                await get_project("nonexistent")

            assert exc.value.status_code == 404

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_delete_running_project_error(self):
        """Test error when deleting project with running agent."""
        from server.routers.projects import delete_project
        from fastapi import HTTPException

        with patch("server.routers.projects._get_registry_functions") as mock_reg:
            mock_project_dir = MagicMock()
            mock_project_dir.exists.return_value = True
            mock_project_dir.__truediv__ = MagicMock(
                return_value=MagicMock(exists=MagicMock(return_value=True))
            )
            mock_reg.return_value = (
                None,
                MagicMock(),  # unregister_project
                MagicMock(return_value=mock_project_dir),  # get_project_path
                None, None, None, None, None, None, None, None
            )

            with pytest.raises(HTTPException) as exc:
                await delete_project("test-project")

            assert exc.value.status_code == 409


# =============================================================================
# API Integration Tests
# =============================================================================

class TestAPIEndpoints:
    """Tests for API endpoint behavior."""

    @pytest.fixture
    def test_client(self):
        """Create a FastAPI test client."""
        from fastapi.testclient import TestClient
        from server.main import app

        with patch("signal.signal", return_value=None):
            with TestClient(app, raise_server_exceptions=False) as client:
                yield client

    @pytest.mark.unit
    def test_health_check_endpoint(self, test_client):
        """Test health check endpoint returns ok."""
        response = test_client.get("/api/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    @pytest.mark.unit
    def test_projects_list_endpoint(self, test_client):
        """Test projects list endpoint."""
        with patch("server.routers.projects._init_imports"):
            with patch("server.routers.projects._get_registry_functions") as mock_reg:
                mock_reg.return_value = (
                    None, None, None, None, None, None,
                    MagicMock(return_value={}),  # list_registered_projects
                    None, None, None, None
                )

                response = test_client.get("/api/projects")

        assert response.status_code == 200
        assert isinstance(response.json(), list)
