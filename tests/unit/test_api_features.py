"""
Features Router API Unit Tests
==============================

Tests for /api/projects/{project_name}/features endpoints including:
- Feature listing
- Feature CRUD operations
- Status transformations
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.routers.features import (
    validate_project_name,
    feature_to_response,
    beads_task_to_feature,
    read_local_beads_features,
)


class TestValidateProjectName:
    """Tests for validate_project_name function."""

    @pytest.mark.unit
    def test_valid_names(self):
        """Test that valid names pass validation."""
        valid_names = ["project", "my-project", "test_123"]
        for name in valid_names:
            result = validate_project_name(name)
            assert result == name

    @pytest.mark.unit
    def test_invalid_names(self):
        """Test that invalid names raise HTTPException."""
        from fastapi import HTTPException

        invalid_names = ["", "project with spaces", "../path"]
        for name in invalid_names:
            with pytest.raises(HTTPException) as exc_info:
                validate_project_name(name)
            assert exc_info.value.status_code == 400


class TestBeadsTaskToFeature:
    """Tests for beads_task_to_feature transformation."""

    @pytest.mark.unit
    def test_basic_conversion(self):
        """Test basic task to feature conversion."""
        task = {
            "id": "feat-1",
            "title": "User Login",
            "status": "open",
            "priority": 1,
            "labels": ["auth"],
            "description": "Implement login form",
        }

        result = beads_task_to_feature(task)

        assert result["id"] == "feat-1"
        assert result["name"] == "User Login"
        assert result["priority"] == 1
        assert result["category"] == "auth"
        assert result["description"] == "Implement login form"
        assert result["passes"] is False
        assert result["in_progress"] is False

    @pytest.mark.unit
    def test_closed_status_means_passes(self):
        """Test that closed status maps to passes=True."""
        task = {
            "id": "feat-1",
            "title": "Completed Feature",
            "status": "closed",
            "priority": 1,
            "labels": [],
        }

        result = beads_task_to_feature(task)

        assert result["passes"] is True
        assert result["in_progress"] is False

    @pytest.mark.unit
    def test_in_progress_status(self):
        """Test that in_progress status is mapped correctly."""
        task = {
            "id": "feat-1",
            "title": "WIP Feature",
            "status": "in_progress",
            "priority": 1,
            "labels": [],
        }

        result = beads_task_to_feature(task)

        assert result["passes"] is False
        assert result["in_progress"] is True

    @pytest.mark.unit
    def test_extracts_first_label_as_category(self):
        """Test that first label becomes category."""
        task = {
            "id": "feat-1",
            "title": "Test",
            "status": "open",
            "priority": 1,
            "labels": ["frontend", "ui", "react"],
            "description": "",
        }

        result = beads_task_to_feature(task)

        assert result["category"] == "frontend"

    @pytest.mark.unit
    def test_empty_labels_gives_empty_category(self):
        """Test that empty labels gives empty category."""
        task = {
            "id": "feat-1",
            "title": "Test",
            "status": "open",
            "priority": 1,
            "labels": [],
            "description": "",
        }

        result = beads_task_to_feature(task)

        assert result["category"] == ""

    @pytest.mark.unit
    def test_extracts_steps_from_description(self):
        """Test extracting numbered steps from description."""
        task = {
            "id": "feat-1",
            "title": "Test",
            "status": "open",
            "priority": 1,
            "labels": [],
            "description": "1. First step\n2. Second step\n3. Third step",
        }

        result = beads_task_to_feature(task)

        assert result["steps"] == ["First step", "Second step", "Third step"]

    @pytest.mark.unit
    def test_no_steps_from_non_numbered_description(self):
        """Test that non-numbered descriptions don't extract steps."""
        task = {
            "id": "feat-1",
            "title": "Test",
            "status": "open",
            "priority": 1,
            "labels": [],
            "description": "Just a plain description without numbered items.",
        }

        result = beads_task_to_feature(task)

        assert result["steps"] == []

    @pytest.mark.unit
    def test_handles_missing_fields(self):
        """Test handling tasks with missing fields."""
        task = {
            "id": "feat-1",
        }

        result = beads_task_to_feature(task)

        assert result["id"] == "feat-1"
        assert result["name"] == ""
        assert result["priority"] == 999
        assert result["category"] == ""
        assert result["description"] == ""
        assert result["steps"] == []

    @pytest.mark.unit
    def test_uses_body_field_fallback(self):
        """Test that 'body' field is used if 'description' is missing."""
        task = {
            "id": "feat-1",
            "title": "Test",
            "status": "open",
            "priority": 1,
            "labels": [],
            "body": "Content from body field",
        }

        result = beads_task_to_feature(task)

        assert result["description"] == "Content from body field"


class TestFeatureToResponse:
    """Tests for feature_to_response conversion."""

    @pytest.mark.unit
    def test_converts_to_response_schema(self):
        """Test conversion to FeatureResponse schema."""
        feature = {
            "id": "feat-1",
            "priority": 1,
            "category": "auth",
            "name": "Login Feature",
            "description": "Implement login",
            "steps": ["Step 1", "Step 2"],
            "passes": True,
            "in_progress": False,
        }

        result = feature_to_response(feature)

        assert result.id == "feat-1"
        assert result.priority == 1
        assert result.category == "auth"
        assert result.name == "Login Feature"
        assert result.passes is True
        assert result.in_progress is False

    @pytest.mark.unit
    def test_handles_missing_fields_with_defaults(self):
        """Test that missing fields get defaults."""
        feature = {}

        result = feature_to_response(feature)

        assert result.id == ""
        assert result.priority == 999
        assert result.category == ""
        assert result.name == ""
        assert result.passes is False
        assert result.in_progress is False


class TestReadLocalBeadsFeatures:
    """Tests for read_local_beads_features function."""

    @pytest.mark.unit
    def test_reads_features_from_jsonl(self, temp_project_dir, sample_beads_issues):
        """Test reading features from issues.jsonl file."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        with open(issues_file, "w") as f:
            for issue in sample_beads_issues:
                f.write(json.dumps(issue) + "\n")

        result = read_local_beads_features(temp_project_dir)

        assert len(result) == 3

    @pytest.mark.unit
    def test_returns_empty_for_missing_file(self, temp_project_dir):
        """Test returns empty list when file doesn't exist."""
        result = read_local_beads_features(temp_project_dir)
        assert result == []

    @pytest.mark.unit
    def test_handles_malformed_json_lines(self, temp_project_dir):
        """Test handling of malformed JSON lines."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        content = '{"id": "feat-1", "title": "Valid", "status": "open"}\n'
        content += 'invalid json line\n'
        content += '{"id": "feat-2", "title": "Also Valid", "status": "closed"}\n'
        issues_file.write_text(content)

        result = read_local_beads_features(temp_project_dir)

        # Should skip invalid line
        assert len(result) == 2

    @pytest.mark.unit
    def test_skips_empty_lines(self, temp_project_dir):
        """Test that empty lines are skipped."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        content = '{"id": "feat-1", "title": "Test", "status": "open"}\n\n\n'
        issues_file.write_text(content)

        result = read_local_beads_features(temp_project_dir)

        assert len(result) == 1


class TestFeatureListResponse:
    """Tests for feature list response organization."""

    @pytest.mark.unit
    def test_organizes_by_status(self, temp_project_dir):
        """Test that features are organized into pending/in_progress/done."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        issues = [
            {"id": "feat-1", "title": "Open", "status": "open", "priority": 1, "labels": []},
            {"id": "feat-2", "title": "WIP", "status": "in_progress", "priority": 2, "labels": []},
            {"id": "feat-3", "title": "Done", "status": "closed", "priority": 3, "labels": []},
        ]
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        features = read_local_beads_features(temp_project_dir)

        # Organize by status
        pending = [f for f in features if not f.get("passes") and not f.get("in_progress")]
        in_progress = [f for f in features if f.get("in_progress")]
        done = [f for f in features if f.get("passes")]

        assert len(pending) == 1
        assert len(in_progress) == 1
        assert len(done) == 1

        assert pending[0]["id"] == "feat-1"
        assert in_progress[0]["id"] == "feat-2"
        assert done[0]["id"] == "feat-3"


class TestFeatureAPIEndpoints:
    """Tests for feature API endpoints.

    Note: These tests require complex mocking of the FastAPI application.
    The simpler unit tests above test the helper functions directly.
    """

    @pytest.mark.unit
    @pytest.mark.skip(reason="Requires full application context - covered by integration tests")
    @patch("server.routers.features._get_project_path")
    @patch("server.routers.features._get_project_git_url")
    @patch("server.routers.features.get_cached_features")
    def test_list_features_not_found(
        self,
        mock_cache,
        mock_git_url,
        mock_path,
        test_client
    ):
        """Test listing features for non-existent project."""
        mock_path.return_value = None

        response = test_client.get("/api/projects/nonexistent/features")

        assert response.status_code == 404

    @pytest.mark.unit
    @pytest.mark.skip(reason="Requires full application context - covered by integration tests")
    @patch("server.routers.features._get_project_path")
    @patch("server.routers.features._get_project_git_url")
    @patch("server.routers.features.get_cached_features")
    @patch("server.routers.features.read_local_beads_features")
    def test_list_features_success(
        self,
        mock_read_local,
        mock_cache,
        mock_git_url,
        mock_path,
        test_client,
        tmp_path
    ):
        """Test listing features successfully."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        mock_path.return_value = project_dir
        mock_git_url.return_value = "https://github.com/user/repo.git"
        mock_cache.return_value = []
        mock_read_local.return_value = []

        response = test_client.get("/api/projects/test-project/features")

        assert response.status_code == 200
        data = response.json()
        assert "pending" in data
        assert "in_progress" in data
        assert "done" in data


class TestFeaturePriority:
    """Tests for feature priority handling."""

    @pytest.mark.unit
    def test_priority_preserved(self):
        """Test that priority is preserved in conversion."""
        for priority in [0, 1, 2, 3, 4, 999]:
            task = {
                "id": "feat-1",
                "title": "Test",
                "status": "open",
                "priority": priority,
                "labels": [],
            }

            result = beads_task_to_feature(task)

            assert result["priority"] == priority

    @pytest.mark.unit
    def test_default_priority(self):
        """Test default priority when not specified."""
        task = {
            "id": "feat-1",
            "title": "Test",
            "status": "open",
            "labels": [],
        }

        result = beads_task_to_feature(task)

        assert result["priority"] == 999


class TestStepsParsing:
    """Tests for parsing steps from description."""

    @pytest.mark.unit
    def test_parses_numbered_steps(self):
        """Test parsing numbered steps."""
        task = {
            "id": "feat-1",
            "title": "Test",
            "status": "open",
            "priority": 1,
            "labels": [],
            "description": "1. Create component\n2. Add styling\n3. Write tests",
        }

        result = beads_task_to_feature(task)

        assert result["steps"] == ["Create component", "Add styling", "Write tests"]

    @pytest.mark.unit
    def test_handles_varied_numbering(self):
        """Test handling various number formats."""
        task = {
            "id": "feat-1",
            "title": "Test",
            "status": "open",
            "priority": 1,
            "labels": [],
            "description": "1. First\n10. Tenth\n100. Hundredth",
        }

        result = beads_task_to_feature(task)

        assert len(result["steps"]) == 3

    @pytest.mark.unit
    def test_ignores_non_numbered_lines(self):
        """Test that non-numbered lines don't become steps."""
        task = {
            "id": "feat-1",
            "title": "Test",
            "status": "open",
            "priority": 1,
            "labels": [],
            "description": "Introduction text\n1. Actual step\n- Not a step\n2. Another step",
        }

        result = beads_task_to_feature(task)

        # Should only have the numbered steps
        assert len(result["steps"]) == 2
        assert "Actual step" in result["steps"]
        assert "Another step" in result["steps"]
