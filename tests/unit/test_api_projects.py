"""
Projects Router API Unit Tests
==============================

Tests for /api/projects endpoints including:
- Project CRUD operations
- Prompt management
- Settings management
- Container management
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.routers.projects import (
    validate_project_name,
    validate_task_id,
    get_project_stats,
    get_wizard_status_path,
    check_wizard_incomplete,
    read_agent_model,
    write_agent_config,
    clone_repository,
    init_beads_if_needed,
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
            "test-project-2024",
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
            "a" * 51,
            "project with spaces",
            "project/slash",
            "../traversal",
            "project@special",
        ]
        for name in invalid_names:
            with pytest.raises(HTTPException) as exc_info:
                validate_project_name(name)
            assert exc_info.value.status_code == 400


class TestValidateTaskId:
    """Tests for validate_task_id function."""

    @pytest.mark.unit
    def test_valid_task_ids(self):
        """Test that valid task IDs pass validation."""
        valid_ids = [
            "beads-1",
            "feat-42",
            "task-123",
            "bug-99999",
        ]
        for task_id in valid_ids:
            result = validate_task_id(task_id)
            assert result == task_id

    @pytest.mark.unit
    def test_invalid_task_ids(self):
        """Test that invalid task IDs raise HTTPException."""
        from fastapi import HTTPException

        invalid_ids = [
            "",
            "1234",
            "no-prefix",
            "beads",
            "beads-",
            "-123",
            "feat-abc",
        ]
        for task_id in invalid_ids:
            with pytest.raises(HTTPException) as exc_info:
                validate_task_id(task_id)
            assert exc_info.value.status_code == 400


class TestGetProjectStats:
    """Tests for get_project_stats function."""

    @pytest.mark.unit
    def test_get_stats_with_features(self, temp_project_dir, sample_beads_issues):
        """Test getting stats with features present."""
        # Create beads issues file
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        with open(issues_file, "w") as f:
            for issue in sample_beads_issues:
                f.write(json.dumps(issue) + "\n")

        stats = get_project_stats(temp_project_dir)

        assert stats.total == 3
        assert stats.passing == 1
        assert stats.in_progress == 1
        assert stats.percentage == pytest.approx(33.3, rel=0.1)

    @pytest.mark.unit
    def test_get_stats_empty_project(self, temp_project_dir):
        """Test getting stats with no features."""
        stats = get_project_stats(temp_project_dir)

        assert stats.total == 0
        assert stats.passing == 0
        assert stats.in_progress == 0
        assert stats.percentage == 0.0


class TestWizardStatus:
    """Tests for wizard status functions."""

    @pytest.mark.unit
    def test_get_wizard_status_path(self, temp_project_dir):
        """Test getting wizard status file path."""
        result = get_wizard_status_path(temp_project_dir)

        expected = temp_project_dir / "prompts" / ".wizard_status.json"
        assert result == expected

    @pytest.mark.unit
    def test_check_wizard_incomplete_with_spec(self, temp_project_dir):
        """Test wizard is complete when spec exists."""
        result = check_wizard_incomplete(temp_project_dir, has_spec=True)
        assert result is False

    @pytest.mark.unit
    def test_check_wizard_incomplete_no_status_file(self, temp_project_dir):
        """Test wizard is complete when no status file exists."""
        result = check_wizard_incomplete(temp_project_dir, has_spec=False)
        assert result is False

    @pytest.mark.unit
    def test_check_wizard_incomplete_with_status_file(self, temp_project_dir):
        """Test wizard is incomplete when status file exists but no spec."""
        prompts_dir = temp_project_dir / "prompts"
        prompts_dir.mkdir(exist_ok=True)
        status_file = prompts_dir / ".wizard_status.json"
        status_file.write_text('{"step": "chat"}')

        result = check_wizard_incomplete(temp_project_dir, has_spec=False)
        assert result is True


class TestAgentConfig:
    """Tests for agent configuration functions."""

    @pytest.mark.unit
    def test_read_agent_model_default(self, temp_project_dir):
        """Test reading agent model returns default when no config."""
        result = read_agent_model(temp_project_dir)
        assert result == "glm-4-7"  # DEFAULT_AGENT_MODEL

    @pytest.mark.unit
    def test_read_agent_model_from_config(self, temp_project_dir):
        """Test reading agent model from config file."""
        prompts_dir = temp_project_dir / "prompts"
        prompts_dir.mkdir(exist_ok=True)
        config_file = prompts_dir / ".agent_config.json"
        config_file.write_text('{"agent_model": "claude-opus-4-5-20251101"}')

        result = read_agent_model(temp_project_dir)
        assert result == "claude-opus-4-5-20251101"

    @pytest.mark.unit
    def test_write_agent_config(self, temp_project_dir):
        """Test writing agent config."""
        write_agent_config(temp_project_dir, "claude-sonnet-4-5-20250514")

        config_file = temp_project_dir / "prompts" / ".agent_config.json"
        assert config_file.exists()

        config = json.loads(config_file.read_text())
        assert config["agent_model"] == "claude-sonnet-4-5-20250514"

    @pytest.mark.unit
    def test_write_agent_config_preserves_other_fields(self, temp_project_dir):
        """Test writing config preserves existing fields."""
        prompts_dir = temp_project_dir / "prompts"
        prompts_dir.mkdir(exist_ok=True)
        config_file = prompts_dir / ".agent_config.json"
        config_file.write_text('{"other_field": "value", "agent_model": "old"}')

        write_agent_config(temp_project_dir, "new-model")

        config = json.loads(config_file.read_text())
        assert config["agent_model"] == "new-model"
        assert config["other_field"] == "value"


class TestCloneRepository:
    """Tests for clone_repository function."""

    @pytest.mark.unit
    def test_clone_success(self, tmp_path, mock_git_clone):
        """Test successful git clone."""
        dest = tmp_path / "new-repo"

        success, message = clone_repository(
            "https://github.com/user/repo.git",
            dest
        )

        assert success is True
        assert "successfully" in message.lower()

    @pytest.mark.unit
    def test_clone_invalid_url(self, tmp_path):
        """Test clone with invalid URL."""
        dest = tmp_path / "new-repo"

        success, message = clone_repository(
            "ftp://invalid.com/repo.git",
            dest
        )

        assert success is False
        assert "invalid" in message.lower()

    @pytest.mark.unit
    def test_clone_failure(self, tmp_path):
        """Test handling git clone failure."""
        dest = tmp_path / "new-repo"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="fatal: repository not found"
            )

            success, message = clone_repository(
                "https://github.com/user/repo.git",
                dest
            )

            assert success is False
            assert "failed" in message.lower()

    @pytest.mark.unit
    def test_clone_timeout(self, tmp_path):
        """Test handling git clone timeout."""
        import subprocess
        dest = tmp_path / "new-repo"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 300)

            success, message = clone_repository(
                "https://github.com/user/repo.git",
                dest
            )

            assert success is False
            assert "timed out" in message.lower()


class TestInitBeadsIfNeeded:
    """Tests for init_beads_if_needed function."""

    @pytest.mark.unit
    def test_beads_already_initialized(self, temp_project_dir):
        """Test that already-initialized beads is detected."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        (beads_dir / "config.yaml").write_text("prefix: feat")

        success, message = init_beads_if_needed(temp_project_dir)

        assert success is True
        assert "already initialized" in message.lower()

    @pytest.mark.unit
    def test_beads_init_success(self, temp_project_dir, mock_beads_cli):
        """Test successful beads initialization."""
        success, message = init_beads_if_needed(temp_project_dir)

        assert success is True
        assert "successfully" in message.lower() or mock_beads_cli.called

    @pytest.mark.unit
    def test_beads_init_failure(self, temp_project_dir):
        """Test handling beads init failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="bd: command failed"
            )

            success, message = init_beads_if_needed(temp_project_dir)

            assert success is False


class TestProjectAPIEndpoints:
    """Tests for project API endpoints using test client.

    Note: These tests require complex mocking of the FastAPI application.
    The simpler unit tests above test the helper functions directly.
    """

    @pytest.mark.unit
    @pytest.mark.skip(reason="Requires full application context - covered by integration tests")
    def test_health_check(self, test_client):
        """Test health check endpoint."""
        response = test_client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    @pytest.mark.unit
    @pytest.mark.skip(reason="Requires full application context - covered by integration tests")
    @patch("server.routers.projects._get_registry_functions")
    @patch("server.routers.projects._init_imports")
    def test_list_projects_empty(self, mock_init, mock_registry, test_client):
        """Test listing projects when none exist."""
        mock_registry.return_value = (
            None,  # register_project
            None,  # unregister_project
            None,  # get_project_path
            None,  # get_project_git_url
            None,  # get_project_info
            None,  # get_projects_dir
            lambda: {},  # list_registered_projects
            None,  # validate_project_path
            None,  # mark_project_initialized
            None,  # update_target_container_count
            None,  # list_project_containers
        )

        response = test_client.get("/api/projects")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.unit
    @pytest.mark.skip(reason="Requires full application context - covered by integration tests")
    @patch("server.routers.projects.validate_project_name")
    def test_create_project_invalid_name(self, mock_validate, test_client):
        """Test creating project with invalid name."""
        from fastapi import HTTPException

        mock_validate.side_effect = HTTPException(
            status_code=400,
            detail="Invalid project name"
        )

        response = test_client.post(
            "/api/projects",
            json={
                "name": "invalid name",
                "git_url": "https://github.com/user/repo.git"
            }
        )

        assert response.status_code == 400


class TestProjectContainerManagement:
    """Tests for project container management endpoints."""

    @pytest.mark.unit
    @pytest.mark.skip(reason="Requires full application context - covered by integration tests")
    @patch("server.routers.projects._get_registry_functions")
    @patch("server.routers.projects._get_docker_container_status")
    @patch("server.services.container_manager.get_all_container_managers")
    def test_list_containers(
        self,
        mock_managers,
        mock_docker_status,
        mock_registry,
        test_client
    ):
        """Test listing containers for a project."""
        # Setup mocks
        mock_registry.return_value = (
            None, None,
            lambda name: Path("/tmp/test"),  # get_project_path
            None, None, None, None, None, None, None, None,
        )
        mock_managers.return_value = []
        mock_docker_status.return_value = None

        response = test_client.get("/api/projects/test-project/containers")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestProjectSettingsEndpoints:
    """Tests for project settings endpoints."""

    @pytest.mark.unit
    @pytest.mark.skip(reason="Requires full application context - covered by integration tests")
    @patch("server.routers.projects._get_registry_functions")
    def test_get_settings_not_found(self, mock_registry, test_client):
        """Test getting settings for non-existent project."""
        mock_registry.return_value = (
            None, None,
            lambda name: None,  # get_project_path returns None
            None, None, None, None, None, None, None, None,
        )

        response = test_client.get("/api/projects/nonexistent/settings")

        assert response.status_code == 404

    @pytest.mark.unit
    @pytest.mark.skip(reason="Requires full application context - covered by integration tests")
    @patch("server.routers.projects._get_registry_functions")
    @patch("server.routers.projects.read_agent_model")
    def test_get_settings_success(self, mock_read, mock_registry, test_client, tmp_path):
        """Test getting settings successfully."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        mock_registry.return_value = (
            None, None,
            lambda name: project_dir,  # get_project_path
            None, None, None, None, None, None, None, None,
        )
        mock_read.return_value = "claude-opus-4-5-20251101"

        response = test_client.get("/api/projects/test-project/settings")

        assert response.status_code == 200
        data = response.json()
        assert data["agent_model"] == "claude-opus-4-5-20251101"


class TestProjectPromptsEndpoints:
    """Tests for project prompts endpoints."""

    @pytest.mark.unit
    @pytest.mark.skip(reason="Requires full application context - covered by integration tests")
    @patch("server.routers.projects._get_registry_functions")
    @patch("server.routers.projects._init_imports")
    @patch("server.routers.projects._get_project_prompts_dir")
    def test_get_prompts(
        self,
        mock_prompts_dir,
        mock_init,
        mock_registry,
        test_client,
        project_with_prompts
    ):
        """Test getting project prompts."""
        prompts_dir = project_with_prompts / "prompts"

        mock_registry.return_value = (
            None, None,
            lambda name: project_with_prompts,  # get_project_path
            None, None, None, None, None, None, None, None,
        )
        mock_prompts_dir.return_value = prompts_dir

        response = test_client.get("/api/projects/test-project/prompts")

        assert response.status_code == 200
        data = response.json()
        assert "app_spec" in data
        assert "initializer_prompt" in data
        assert "coding_prompt" in data
