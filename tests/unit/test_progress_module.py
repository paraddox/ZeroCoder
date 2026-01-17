"""
Progress Module Unit Tests
==========================

Tests for progress tracking functionality including:
- Feature detection
- Progress calculation
- Beads integration
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from progress import (
    has_features,
    has_open_features,
    get_progress_stats,
    read_beads_issues,
)


class TestHasFeatures:
    """Tests for has_features function."""

    @pytest.mark.unit
    def test_has_features_with_issues(self, tmp_path):
        """Test has_features returns True when issues exist."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text('{"id": "feat-1", "status": "open"}\n')

        result = has_features(project_dir, "test-project")

        assert result is True

    @pytest.mark.unit
    def test_has_features_empty_file(self, tmp_path):
        """Test has_features returns False for empty issues file."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text("")

        result = has_features(project_dir, "test-project")

        assert result is False

    @pytest.mark.unit
    def test_has_features_no_beads_dir(self, tmp_path):
        """Test has_features returns False when no .beads directory."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        result = has_features(project_dir, "test-project")

        assert result is False

    @pytest.mark.unit
    def test_has_features_nonexistent_project(self, tmp_path):
        """Test has_features returns False for nonexistent project."""
        nonexistent = tmp_path / "nonexistent"

        result = has_features(nonexistent, "nonexistent")

        assert result is False


class TestHasOpenFeatures:
    """Tests for has_open_features function."""

    @pytest.mark.unit
    def test_has_open_features_with_open(self, tmp_path):
        """Test has_open_features returns True when open issues exist."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        issues = [
            {"id": "feat-1", "status": "open"},
            {"id": "feat-2", "status": "closed"},
        ]
        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        result = has_open_features(project_dir, "test-project")

        assert result is True

    @pytest.mark.unit
    def test_has_open_features_all_closed(self, tmp_path):
        """Test has_open_features returns False when all issues closed."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        issues = [
            {"id": "feat-1", "status": "closed"},
            {"id": "feat-2", "status": "closed"},
        ]
        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        result = has_open_features(project_dir, "test-project")

        assert result is False

    @pytest.mark.unit
    def test_has_open_features_in_progress(self, tmp_path):
        """Test has_open_features returns True for in_progress issues."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        issues = [
            {"id": "feat-1", "status": "in_progress"},
            {"id": "feat-2", "status": "closed"},
        ]
        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        result = has_open_features(project_dir, "test-project")

        assert result is True


class TestGetProgressStats:
    """Tests for get_progress_stats function."""

    @pytest.mark.unit
    def test_get_progress_stats(self, tmp_path):
        """Test get_progress_stats calculates correctly."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        issues = [
            {"id": "feat-1", "status": "open"},
            {"id": "feat-2", "status": "in_progress"},
            {"id": "feat-3", "status": "closed"},
            {"id": "feat-4", "status": "closed"},
        ]
        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        stats = get_progress_stats(project_dir, "test-project")

        assert stats["total"] == 4
        assert stats["passing"] == 2
        assert stats["in_progress"] == 1
        assert stats["percentage"] == 50.0

    @pytest.mark.unit
    def test_get_progress_stats_empty(self, tmp_path):
        """Test get_progress_stats with no issues."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text("")

        stats = get_progress_stats(project_dir, "test-project")

        assert stats["total"] == 0
        assert stats["passing"] == 0
        assert stats["percentage"] == 0.0

    @pytest.mark.unit
    def test_get_progress_stats_all_done(self, tmp_path):
        """Test get_progress_stats when all issues closed."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        issues = [
            {"id": "feat-1", "status": "closed"},
            {"id": "feat-2", "status": "closed"},
        ]
        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        stats = get_progress_stats(project_dir, "test-project")

        assert stats["total"] == 2
        assert stats["passing"] == 2
        assert stats["percentage"] == 100.0


class TestReadBeadsIssues:
    """Tests for read_beads_issues function."""

    @pytest.mark.unit
    def test_read_beads_issues(self, tmp_path):
        """Test reading issues from JSONL file."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        issues = [
            {"id": "feat-1", "title": "Feature 1", "status": "open"},
            {"id": "feat-2", "title": "Feature 2", "status": "closed"},
        ]
        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        result = read_beads_issues(project_dir)

        assert len(result) == 2
        assert result[0]["id"] == "feat-1"
        assert result[1]["id"] == "feat-2"

    @pytest.mark.unit
    def test_read_beads_issues_handles_malformed(self, tmp_path):
        """Test reading issues handles malformed JSON."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        content = '{"id": "feat-1"}\ninvalid json\n{"id": "feat-2"}\n'
        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text(content)

        result = read_beads_issues(project_dir)

        # Should skip malformed line
        assert len(result) == 2

    @pytest.mark.unit
    def test_read_beads_issues_empty_lines(self, tmp_path):
        """Test reading issues skips empty lines."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        content = '{"id": "feat-1"}\n\n\n{"id": "feat-2"}\n'
        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text(content)

        result = read_beads_issues(project_dir)

        assert len(result) == 2

    @pytest.mark.unit
    def test_read_beads_issues_no_file(self, tmp_path):
        """Test reading issues when file doesn't exist."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        result = read_beads_issues(project_dir)

        assert result == []


class TestProgressCalculations:
    """Tests for progress percentage calculations."""

    @pytest.mark.unit
    def test_percentage_precision(self, tmp_path):
        """Test percentage calculation precision."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()

        # 1 closed out of 3 = 33.33...%
        issues = [
            {"id": "feat-1", "status": "closed"},
            {"id": "feat-2", "status": "open"},
            {"id": "feat-3", "status": "open"},
        ]
        issues_file = beads_dir / "issues.jsonl"
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        stats = get_progress_stats(project_dir, "test-project")

        # Should be approximately 33.33
        assert 33.0 <= stats["percentage"] <= 34.0

    @pytest.mark.unit
    def test_percentage_zero_total(self, tmp_path):
        """Test percentage when no issues."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        stats = get_progress_stats(project_dir, "test-project")

        # Should not divide by zero
        assert stats["percentage"] == 0.0
