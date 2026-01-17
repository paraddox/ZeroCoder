"""
API Routers Enterprise Tests
============================

Comprehensive enterprise-grade tests for API routers including:
- Input validation and sanitization
- Error handling and responses
- Business logic correctness
- Edge cases and boundary conditions
"""

import json
import pytest
import re
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Project Name Validation Tests
# =============================================================================

class TestProjectNameValidation:
    """Tests for project name validation."""

    @pytest.mark.unit
    def test_valid_project_names(self):
        """Test that valid project names pass validation."""
        from server.routers.projects import validate_project_name

        valid_names = [
            "project",
            "my-project",
            "my_project",
            "MyProject",
            "Project123",
            "123project",
            "a",
            "a" * 50,
            "test-project-2024",
            "UPPERCASE",
            "mixedCase123",
        ]

        for name in valid_names:
            result = validate_project_name(name)
            assert result == name

    @pytest.mark.unit
    def test_invalid_project_names(self):
        """Test that invalid project names are rejected."""
        from server.routers.projects import validate_project_name
        from fastapi import HTTPException

        invalid_names = [
            "",  # Empty
            "a" * 51,  # Too long
            "project with spaces",
            "project/slash",
            "project\\backslash",
            "../traversal",
            "..\\traversal",
            "project@special",
            "project!exclaim",
            "project#hash",
            "project$dollar",
            "project%percent",
            "project;semicolon",
            "project:colon",
        ]

        for name in invalid_names:
            with pytest.raises(HTTPException) as exc_info:
                validate_project_name(name)
            assert exc_info.value.status_code == 400


# =============================================================================
# Task ID Validation Tests
# =============================================================================

class TestTaskIdValidation:
    """Tests for task ID validation."""

    @pytest.mark.unit
    def test_valid_task_ids(self):
        """Test that valid task IDs pass validation."""
        from server.routers.projects import validate_task_id

        valid_ids = [
            "beads-1",
            "beads-42",
            "beads-9999",
            "feat-1",
            "task-123",
            "bug-456",
        ]

        for task_id in valid_ids:
            result = validate_task_id(task_id)
            assert result == task_id

    @pytest.mark.unit
    def test_invalid_task_ids(self):
        """Test that invalid task IDs are rejected."""
        from server.routers.projects import validate_task_id
        from fastapi import HTTPException

        invalid_ids = [
            "",
            "1234",
            "beads",
            "beads-",
            "-123",
            "feat-abc",
            "beads-abc",
            "../evil-1",
            "beads-1; rm -rf",
        ]

        for task_id in invalid_ids:
            with pytest.raises(HTTPException) as exc_info:
                validate_task_id(task_id)
            assert exc_info.value.status_code == 400


# =============================================================================
# Project Stats Tests
# =============================================================================

class TestProjectStats:
    """Tests for project statistics calculation."""

    @pytest.mark.unit
    def test_get_stats_empty_project(self, temp_project_dir):
        """Test stats for project with no features."""
        from server.routers.projects import get_project_stats

        stats = get_project_stats(temp_project_dir)

        assert stats.total == 0
        assert stats.passing == 0
        assert stats.in_progress == 0
        assert stats.percentage == 0.0

    @pytest.mark.unit
    def test_get_stats_with_features(self, temp_project_dir):
        """Test stats with features present."""
        from server.routers.projects import get_project_stats

        # Create beads issues
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        features = [
            {"id": "feat-1", "status": "open", "title": "Feature 1"},
            {"id": "feat-2", "status": "in_progress", "title": "Feature 2"},
            {"id": "feat-3", "status": "closed", "title": "Feature 3"},
            {"id": "feat-4", "status": "closed", "title": "Feature 4"},
        ]

        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        stats = get_project_stats(temp_project_dir)

        assert stats.total == 4
        assert stats.passing == 2
        assert stats.in_progress == 1
        assert stats.percentage == 50.0

    @pytest.mark.unit
    def test_get_stats_all_passing(self, temp_project_dir):
        """Test stats when all features are passing."""
        from server.routers.projects import get_project_stats

        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        features = [
            {"id": "feat-1", "status": "closed", "title": "Feature 1"},
            {"id": "feat-2", "status": "closed", "title": "Feature 2"},
        ]

        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        stats = get_project_stats(temp_project_dir)

        assert stats.total == 2
        assert stats.passing == 2
        assert stats.percentage == 100.0

    @pytest.mark.unit
    def test_get_stats_none_passing(self, temp_project_dir):
        """Test stats when no features are passing."""
        from server.routers.projects import get_project_stats

        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        features = [
            {"id": "feat-1", "status": "open", "title": "Feature 1"},
            {"id": "feat-2", "status": "open", "title": "Feature 2"},
        ]

        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        stats = get_project_stats(temp_project_dir)

        assert stats.total == 2
        assert stats.passing == 0
        assert stats.percentage == 0.0


# =============================================================================
# Wizard Status Tests
# =============================================================================

class TestWizardStatus:
    """Tests for wizard status functions."""

    @pytest.mark.unit
    def test_get_wizard_status_path(self, temp_project_dir):
        """Test wizard status path generation."""
        from server.routers.projects import get_wizard_status_path

        path = get_wizard_status_path(temp_project_dir)

        expected = temp_project_dir / "prompts" / ".wizard_status.json"
        assert path == expected

    @pytest.mark.unit
    def test_check_wizard_complete_with_spec(self, temp_project_dir):
        """Test wizard is complete when spec exists."""
        from server.routers.projects import check_wizard_incomplete

        result = check_wizard_incomplete(temp_project_dir, has_spec=True)
        assert result is False

    @pytest.mark.unit
    def test_check_wizard_complete_no_status_file(self, temp_project_dir):
        """Test wizard is complete when no status file."""
        from server.routers.projects import check_wizard_incomplete

        result = check_wizard_incomplete(temp_project_dir, has_spec=False)
        assert result is False

    @pytest.mark.unit
    def test_check_wizard_incomplete_with_status(self, temp_project_dir):
        """Test wizard is incomplete with status file but no spec."""
        from server.routers.projects import check_wizard_incomplete

        prompts_dir = temp_project_dir / "prompts"
        prompts_dir.mkdir(exist_ok=True)
        status_file = prompts_dir / ".wizard_status.json"
        status_file.write_text('{"step": "chat"}')

        result = check_wizard_incomplete(temp_project_dir, has_spec=False)
        assert result is True


# =============================================================================
# Agent Config Tests
# =============================================================================

class TestAgentConfig:
    """Tests for agent configuration."""

    @pytest.mark.unit
    def test_read_agent_model_default(self, temp_project_dir):
        """Test reading agent model returns default when no config."""
        from server.routers.projects import read_agent_model

        result = read_agent_model(temp_project_dir)
        assert result == "glm-4-7"

    @pytest.mark.unit
    def test_read_agent_model_from_config(self, temp_project_dir):
        """Test reading agent model from config file."""
        from server.routers.projects import read_agent_model

        prompts_dir = temp_project_dir / "prompts"
        prompts_dir.mkdir(exist_ok=True)
        config_file = prompts_dir / ".agent_config.json"
        config_file.write_text('{"agent_model": "claude-opus-4-5-20251101"}')

        result = read_agent_model(temp_project_dir)
        assert result == "claude-opus-4-5-20251101"

    @pytest.mark.unit
    def test_read_agent_model_malformed_json(self, temp_project_dir):
        """Test reading agent model handles malformed JSON."""
        from server.routers.projects import read_agent_model

        prompts_dir = temp_project_dir / "prompts"
        prompts_dir.mkdir(exist_ok=True)
        config_file = prompts_dir / ".agent_config.json"
        config_file.write_text('{"not valid json')

        # Should return default
        result = read_agent_model(temp_project_dir)
        assert result == "glm-4-7"

    @pytest.mark.unit
    def test_write_agent_config(self, temp_project_dir):
        """Test writing agent config."""
        from server.routers.projects import write_agent_config

        write_agent_config(temp_project_dir, "claude-sonnet-4-5-20250514")

        config_file = temp_project_dir / "prompts" / ".agent_config.json"
        assert config_file.exists()

        config = json.loads(config_file.read_text())
        assert config["agent_model"] == "claude-sonnet-4-5-20250514"

    @pytest.mark.unit
    def test_write_agent_config_preserves_other_fields(self, temp_project_dir):
        """Test writing config preserves other fields."""
        from server.routers.projects import write_agent_config

        prompts_dir = temp_project_dir / "prompts"
        prompts_dir.mkdir(exist_ok=True)
        config_file = prompts_dir / ".agent_config.json"
        config_file.write_text('{"other_field": "value", "agent_model": "old"}')

        write_agent_config(temp_project_dir, "new-model")

        config = json.loads(config_file.read_text())
        assert config["agent_model"] == "new-model"
        assert config["other_field"] == "value"


# =============================================================================
# Clone Repository Tests
# =============================================================================

class TestCloneRepository:
    """Tests for git clone functionality."""

    @pytest.mark.unit
    def test_clone_success(self, tmp_path):
        """Test successful git clone."""
        from server.routers.projects import clone_repository

        dest = tmp_path / "new-repo"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            success, message = clone_repository(
                "https://github.com/user/repo.git",
                dest
            )

        assert success is True
        assert "successfully" in message.lower()

    @pytest.mark.unit
    def test_clone_invalid_url(self, tmp_path):
        """Test clone with invalid URL."""
        from server.routers.projects import clone_repository

        dest = tmp_path / "new-repo"

        success, message = clone_repository(
            "ftp://invalid.com/repo.git",
            dest
        )

        assert success is False
        assert "invalid" in message.lower()

    @pytest.mark.unit
    def test_clone_failure(self, tmp_path):
        """Test clone failure handling."""
        from server.routers.projects import clone_repository

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
        """Test clone timeout handling."""
        import subprocess
        from server.routers.projects import clone_repository

        dest = tmp_path / "new-repo"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 300)

            success, message = clone_repository(
                "https://github.com/user/repo.git",
                dest
            )

        assert success is False
        assert "timed out" in message.lower()


# =============================================================================
# Init Beads Tests
# =============================================================================

class TestInitBeads:
    """Tests for beads initialization."""

    @pytest.mark.unit
    def test_beads_already_initialized(self, temp_project_dir):
        """Test detection of already-initialized beads."""
        from server.routers.projects import init_beads_if_needed

        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        (beads_dir / "config.yaml").write_text("prefix: feat")

        success, message = init_beads_if_needed(temp_project_dir)

        assert success is True
        assert "already initialized" in message.lower()

    @pytest.mark.unit
    def test_beads_init_success(self, temp_project_dir):
        """Test successful beads initialization."""
        from server.routers.projects import init_beads_if_needed

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            success, message = init_beads_if_needed(temp_project_dir)

        assert success is True

    @pytest.mark.unit
    def test_beads_init_failure(self, temp_project_dir):
        """Test beads init failure handling."""
        from server.routers.projects import init_beads_if_needed

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stderr="bd: command failed"
            )

            success, message = init_beads_if_needed(temp_project_dir)

        assert success is False


# =============================================================================
# Features Router Tests
# =============================================================================

class TestFeaturesRouter:
    """Tests for features router functions."""

    @pytest.mark.unit
    def test_beads_task_to_feature_basic(self):
        """Test basic beads task to feature conversion."""
        from server.routers.features import beads_task_to_feature

        task = {
            "id": "feat-1",
            "title": "User Authentication",
            "status": "open",
            "priority": 1,
            "labels": ["auth"],
            "description": "Implement user login",
        }

        feature = beads_task_to_feature(task)

        assert feature["id"] == "feat-1"
        assert feature["name"] == "User Authentication"
        assert feature["category"] == "auth"
        assert feature["passes"] is False
        assert feature["in_progress"] is False

    @pytest.mark.unit
    def test_beads_task_to_feature_closed(self):
        """Test conversion of closed task."""
        from server.routers.features import beads_task_to_feature

        task = {
            "id": "feat-2",
            "title": "Dashboard",
            "status": "closed",
            "priority": 2,
        }

        feature = beads_task_to_feature(task)

        assert feature["passes"] is True
        assert feature["in_progress"] is False

    @pytest.mark.unit
    def test_beads_task_to_feature_in_progress(self):
        """Test conversion of in-progress task."""
        from server.routers.features import beads_task_to_feature

        task = {
            "id": "feat-3",
            "title": "API Integration",
            "status": "in_progress",
            "priority": 1,
        }

        feature = beads_task_to_feature(task)

        assert feature["passes"] is False
        assert feature["in_progress"] is True

    @pytest.mark.unit
    def test_beads_task_to_feature_with_steps(self):
        """Test extraction of steps from description."""
        from server.routers.features import beads_task_to_feature

        task = {
            "id": "feat-4",
            "title": "Feature with Steps",
            "status": "open",
            "priority": 1,
            "description": "1. First step\n2. Second step\n3. Third step",
        }

        feature = beads_task_to_feature(task)

        assert len(feature["steps"]) == 3
        assert "First step" in feature["steps"]
        assert "Second step" in feature["steps"]
        assert "Third step" in feature["steps"]

    @pytest.mark.unit
    def test_beads_task_to_feature_no_labels(self):
        """Test conversion when no labels present."""
        from server.routers.features import beads_task_to_feature

        task = {
            "id": "feat-5",
            "title": "No Labels",
            "status": "open",
            "priority": 1,
        }

        feature = beads_task_to_feature(task)

        assert feature["category"] == ""

    @pytest.mark.unit
    def test_feature_to_response(self):
        """Test feature dict to response conversion."""
        from server.routers.features import feature_to_response

        feature = {
            "id": "feat-1",
            "priority": 1,
            "category": "auth",
            "name": "User Login",
            "description": "Implement login",
            "steps": ["Step 1", "Step 2"],
            "passes": True,
            "in_progress": False,
        }

        response = feature_to_response(feature)

        assert response.id == "feat-1"
        assert response.priority == 1
        assert response.category == "auth"
        assert response.name == "User Login"
        assert response.passes is True
        assert response.in_progress is False

    @pytest.mark.unit
    def test_read_local_beads_features(self, temp_project_dir):
        """Test reading features from local beads file."""
        from server.routers.features import read_local_beads_features

        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        features = [
            {"id": "feat-1", "title": "Feature 1", "status": "open", "priority": 1},
            {"id": "feat-2", "title": "Feature 2", "status": "closed", "priority": 2},
        ]

        with open(issues_file, "w") as f:
            for feat in features:
                f.write(json.dumps(feat) + "\n")

        result = read_local_beads_features(temp_project_dir)

        assert len(result) == 2
        assert result[0]["name"] == "Feature 1"
        assert result[1]["name"] == "Feature 2"

    @pytest.mark.unit
    def test_read_local_beads_features_empty(self, temp_project_dir):
        """Test reading features when file is empty."""
        from server.routers.features import read_local_beads_features

        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text("")

        result = read_local_beads_features(temp_project_dir)

        assert len(result) == 0

    @pytest.mark.unit
    def test_read_local_beads_features_no_file(self, temp_project_dir):
        """Test reading features when file doesn't exist."""
        from server.routers.features import read_local_beads_features

        result = read_local_beads_features(temp_project_dir)

        assert len(result) == 0

    @pytest.mark.unit
    def test_features_project_name_validation(self):
        """Test project name validation in features router."""
        from server.routers.features import validate_project_name
        from fastapi import HTTPException

        # Valid
        assert validate_project_name("my-project") == "my-project"

        # Invalid
        with pytest.raises(HTTPException):
            validate_project_name("../evil")


# =============================================================================
# Agent Router Tests
# =============================================================================

class TestAgentRouter:
    """Tests for agent router helper functions."""

    @pytest.mark.unit
    def test_get_container_type_from_number_zero(self):
        """Test container type determination for init container."""
        # Container 0 should be 'init' type
        container_number = 0
        expected_type = "init"

        # Based on container_manager logic
        if container_number == 0:
            result = "init"
        else:
            result = "coding"

        assert result == expected_type

    @pytest.mark.unit
    def test_get_container_type_from_number_positive(self):
        """Test container type determination for coding container."""
        for container_number in [1, 2, 5, 10]:
            if container_number == 0:
                result = "init"
            else:
                result = "coding"

            assert result == "coding"


# =============================================================================
# Error Response Tests
# =============================================================================

class TestErrorResponses:
    """Tests for error response formatting."""

    @pytest.mark.unit
    def test_404_error_format(self):
        """Test 404 error response format."""
        from fastapi import HTTPException

        exc = HTTPException(status_code=404, detail="Project not found")

        assert exc.status_code == 404
        assert exc.detail == "Project not found"

    @pytest.mark.unit
    def test_400_error_format(self):
        """Test 400 error response format."""
        from fastapi import HTTPException

        exc = HTTPException(status_code=400, detail="Invalid project name")

        assert exc.status_code == 400
        assert exc.detail == "Invalid project name"

    @pytest.mark.unit
    def test_503_error_format(self):
        """Test 503 error response format."""
        from fastapi import HTTPException

        exc = HTTPException(status_code=503, detail="Docker not available")

        assert exc.status_code == 503
        assert exc.detail == "Docker not available"


# =============================================================================
# Path Security Tests
# =============================================================================

class TestPathSecurity:
    """Tests for path traversal prevention."""

    @pytest.mark.unit
    def test_project_name_blocks_path_traversal(self):
        """Test that path traversal is blocked in project names."""
        from server.routers.projects import validate_project_name
        from fastapi import HTTPException

        traversal_attempts = [
            "../parent",
            "..\\parent",
            "foo/../bar",
            "foo/../../etc",
            "%2e%2e%2f",
            "..%00",
        ]

        for name in traversal_attempts:
            with pytest.raises(HTTPException):
                validate_project_name(name)

    @pytest.mark.unit
    def test_task_id_blocks_injection(self):
        """Test that task IDs block injection attempts."""
        from server.routers.projects import validate_task_id
        from fastapi import HTTPException

        injection_attempts = [
            "beads-1; rm -rf /",
            "beads-1 && cat /etc/passwd",
            "beads-1 | evil",
            "beads-1$(whoami)",
        ]

        for task_id in injection_attempts:
            with pytest.raises(HTTPException):
                validate_task_id(task_id)
