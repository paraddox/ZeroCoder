"""
Container Scripts Unit Tests
============================

Tests for scripts that run inside Docker containers including:
- Feature status parsing
- Beads command handling
- Priority conversion
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "container_scripts"))


class TestBeadsToPriority:
    """Tests for beads_to_priority function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from feature_status import beads_to_priority
        self.beads_to_priority = beads_to_priority

    @pytest.mark.unit
    def test_integer_priority_passthrough(self):
        """Test that integer priorities pass through unchanged."""
        assert self.beads_to_priority(0) == 0
        assert self.beads_to_priority(1) == 1
        assert self.beads_to_priority(4) == 4

    @pytest.mark.unit
    def test_string_numeric_conversion(self):
        """Test conversion of numeric strings."""
        assert self.beads_to_priority("0") == 0
        assert self.beads_to_priority("1") == 1
        assert self.beads_to_priority("4") == 4

    @pytest.mark.unit
    def test_p_notation_conversion(self):
        """Test conversion of P0-P4 notation."""
        assert self.beads_to_priority("P0") == 0
        assert self.beads_to_priority("P1") == 1
        assert self.beads_to_priority("P2") == 2
        assert self.beads_to_priority("P3") == 3
        assert self.beads_to_priority("P4") == 4

    @pytest.mark.unit
    def test_lowercase_p_notation(self):
        """Test conversion of lowercase p notation."""
        assert self.beads_to_priority("p0") == 0
        assert self.beads_to_priority("p1") == 1

    @pytest.mark.unit
    def test_unknown_priority_defaults(self):
        """Test that unknown priorities default to 4."""
        assert self.beads_to_priority("unknown") == 4
        assert self.beads_to_priority("high") == 4
        assert self.beads_to_priority("low") == 4


class TestExtractLabelValue:
    """Tests for extract_label_value function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from feature_status import extract_label_value
        self.extract_label_value = extract_label_value

    @pytest.mark.unit
    def test_extracts_category_label(self):
        """Test extracting category from labels."""
        labels = ["category:auth", "type:feature"]
        result = self.extract_label_value(labels, "category")
        assert result == "auth"

    @pytest.mark.unit
    def test_extracts_priority_label(self):
        """Test extracting priority from labels."""
        labels = ["priority:1", "category:ui"]
        result = self.extract_label_value(labels, "priority")
        assert result == "1"

    @pytest.mark.unit
    def test_returns_none_when_not_found(self):
        """Test returning None when label not found."""
        labels = ["category:auth"]
        result = self.extract_label_value(labels, "priority")
        assert result is None

    @pytest.mark.unit
    def test_returns_none_for_empty_labels(self):
        """Test returning None for empty labels list."""
        result = self.extract_label_value([], "category")
        assert result is None

    @pytest.mark.unit
    def test_handles_colons_in_value(self):
        """Test handling values that contain colons."""
        labels = ["url:https://example.com:8080"]
        result = self.extract_label_value(labels, "url")
        assert result == "https://example.com:8080"


class TestParseStepsFromDescription:
    """Tests for parse_steps_from_description function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from feature_status import parse_steps_from_description
        self.parse_steps_from_description = parse_steps_from_description

    @pytest.mark.unit
    def test_extracts_unchecked_steps(self):
        """Test extracting unchecked steps."""
        description = """Some intro text

## Steps
- [ ] First step
- [ ] Second step
- [ ] Third step
"""
        base, steps = self.parse_steps_from_description(description)

        assert "Some intro text" in base
        assert len(steps) == 3
        assert "First step" in steps
        assert "Second step" in steps
        assert "Third step" in steps

    @pytest.mark.unit
    def test_extracts_checked_steps(self):
        """Test extracting checked steps."""
        description = """## Steps
- [x] Completed step
- [ ] Pending step
"""
        base, steps = self.parse_steps_from_description(description)

        assert len(steps) == 2
        assert "Completed step" in steps
        assert "Pending step" in steps

    @pytest.mark.unit
    def test_no_steps_section(self):
        """Test description without steps section."""
        description = "Just a plain description without any steps."
        base, steps = self.parse_steps_from_description(description)

        assert base == description
        assert steps == []

    @pytest.mark.unit
    def test_empty_steps_section(self):
        """Test empty steps section."""
        description = "Intro\n\n## Steps\n\n"
        base, steps = self.parse_steps_from_description(description)

        assert steps == []


class TestGetStatus:
    """Tests for get_status function."""

    @pytest.mark.unit
    def test_counts_status_correctly(self, tmp_path):
        """Test that status counts are calculated correctly."""
        from feature_status import get_status, ISSUES_FILE

        # Create test issues file
        issues = [
            {"id": "feat-1", "title": "Open", "status": "open"},
            {"id": "feat-2", "title": "WIP", "status": "in_progress"},
            {"id": "feat-3", "title": "Done", "status": "closed"},
            {"id": "feat-4", "title": "Also Open", "status": "open"},
        ]

        issues_content = "\n".join(json.dumps(i) for i in issues)

        # Mock the ISSUES_FILE path
        with patch("feature_status.ISSUES_FILE", tmp_path / "issues.jsonl"):
            (tmp_path / "issues.jsonl").write_text(issues_content)

            with patch("feature_status.read_issues") as mock_read:
                mock_read.return_value = issues
                result = get_status()

        assert result["success"] is True
        assert result["stats"]["pending"] == 2
        assert result["stats"]["in_progress"] == 1
        assert result["stats"]["done"] == 1
        assert result["stats"]["total"] == 4
        assert result["stats"]["percentage"] == 25.0

    @pytest.mark.unit
    def test_extracts_category_from_labels(self, tmp_path):
        """Test that category is extracted from labels."""
        from feature_status import get_status

        issues = [
            {"id": "feat-1", "title": "Test", "status": "open", "labels": ["category:auth"]},
        ]

        with patch("feature_status.read_issues") as mock_read:
            mock_read.return_value = issues
            result = get_status()

        assert len(result["features"]) == 1
        assert result["features"][0]["category"] == "auth"

    @pytest.mark.unit
    def test_handles_missing_labels(self):
        """Test handling issues without labels."""
        from feature_status import get_status

        issues = [
            {"id": "feat-1", "title": "Test", "status": "open"},  # No labels key
        ]

        with patch("feature_status.read_issues") as mock_read:
            mock_read.return_value = issues
            result = get_status()

        assert result["features"][0]["category"] == ""


class TestReadIssues:
    """Tests for read_issues function."""

    @pytest.mark.unit
    def test_reads_jsonl_file(self, tmp_path):
        """Test reading issues from JSONL file."""
        from feature_status import read_issues

        issues_file = tmp_path / "issues.jsonl"
        issues = [
            {"id": "feat-1", "title": "Test 1"},
            {"id": "feat-2", "title": "Test 2"},
        ]
        issues_file.write_text("\n".join(json.dumps(i) for i in issues))

        with patch("feature_status.ISSUES_FILE", issues_file):
            result = read_issues()

        assert len(result) == 2
        assert result[0]["id"] == "feat-1"

    @pytest.mark.unit
    def test_skips_malformed_lines(self, tmp_path):
        """Test skipping malformed JSON lines."""
        from feature_status import read_issues

        issues_file = tmp_path / "issues.jsonl"
        content = '{"id": "feat-1"}\nnot valid json\n{"id": "feat-2"}'
        issues_file.write_text(content)

        with patch("feature_status.ISSUES_FILE", issues_file):
            result = read_issues()

        assert len(result) == 2

    @pytest.mark.unit
    def test_returns_empty_for_missing_file(self, tmp_path):
        """Test returning empty list when file doesn't exist."""
        from feature_status import read_issues

        with patch("feature_status.ISSUES_FILE", tmp_path / "nonexistent.jsonl"):
            result = read_issues()

        assert result == []

    @pytest.mark.unit
    def test_skips_empty_lines(self, tmp_path):
        """Test skipping empty lines."""
        from feature_status import read_issues

        issues_file = tmp_path / "issues.jsonl"
        content = '{"id": "feat-1"}\n\n\n{"id": "feat-2"}\n'
        issues_file.write_text(content)

        with patch("feature_status.ISSUES_FILE", issues_file):
            result = read_issues()

        assert len(result) == 2


class TestPercentageCalculation:
    """Tests for percentage calculation."""

    @pytest.mark.unit
    def test_percentage_with_all_done(self):
        """Test percentage when all tasks are done."""
        from feature_status import get_status

        issues = [
            {"id": "feat-1", "status": "closed"},
            {"id": "feat-2", "status": "closed"},
        ]

        with patch("feature_status.read_issues") as mock_read:
            mock_read.return_value = issues
            result = get_status()

        assert result["stats"]["percentage"] == 100.0

    @pytest.mark.unit
    def test_percentage_with_none_done(self):
        """Test percentage when no tasks are done."""
        from feature_status import get_status

        issues = [
            {"id": "feat-1", "status": "open"},
            {"id": "feat-2", "status": "in_progress"},
        ]

        with patch("feature_status.read_issues") as mock_read:
            mock_read.return_value = issues
            result = get_status()

        assert result["stats"]["percentage"] == 0.0

    @pytest.mark.unit
    def test_percentage_empty_list(self):
        """Test percentage with empty task list."""
        from feature_status import get_status

        with patch("feature_status.read_issues") as mock_read:
            mock_read.return_value = []
            result = get_status()

        assert result["stats"]["percentage"] == 0.0
        assert result["stats"]["total"] == 0


class TestFeatureDataExtraction:
    """Tests for extracting complete feature data."""

    @pytest.mark.unit
    def test_extracts_all_fields(self):
        """Test that all fields are extracted correctly."""
        from feature_status import get_status

        issues = [
            {
                "id": "feat-1",
                "title": "User Authentication",
                "status": "in_progress",
                "priority": 1,
                "labels": ["category:auth", "priority:1"],
                "description": "Implement login\n\n## Steps\n- [ ] Create form\n- [x] Add validation",
            }
        ]

        with patch("feature_status.read_issues") as mock_read:
            mock_read.return_value = issues
            result = get_status()

        feature = result["features"][0]
        assert feature["id"] == "feat-1"
        assert feature["name"] == "User Authentication"
        assert feature["status"] == "in_progress"
        assert feature["priority"] == 1
        assert feature["category"] == "auth"
        assert "Create form" in feature["steps"]
        assert "Add validation" in feature["steps"]

    @pytest.mark.unit
    def test_handles_missing_description(self):
        """Test handling missing description field."""
        from feature_status import get_status

        issues = [
            {"id": "feat-1", "title": "Test", "status": "open"},
        ]

        with patch("feature_status.read_issues") as mock_read:
            mock_read.return_value = issues
            result = get_status()

        assert result["features"][0]["description"] == ""
        assert result["features"][0]["steps"] == []
