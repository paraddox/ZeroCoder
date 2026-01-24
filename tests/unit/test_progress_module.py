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
    count_passing_tests,
    get_all_passing_features,
)


def get_progress_stats(project_dir: Path, project_name: str = None) -> dict:
    """Helper function to get progress stats in the expected format."""
    passing, in_progress, total = count_passing_tests(project_dir, project_name)
    percentage = (passing / total * 100) if total > 0 else 0.0
    return {
        "passing": passing,
        "in_progress": in_progress,
        "total": total,
        "percentage": percentage,
    }


class TestHasFeatures:
    """Tests for has_features function."""

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_stats")
    def test_has_features_with_issues(self, mock_cache, tmp_path):
        """Test has_features returns True when issues exist."""
        mock_cache.return_value = {"total": 5}

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        result = has_features(project_dir, project_name="test-project")

        assert result is True
        mock_cache.assert_called_once_with("test-project")

    @pytest.mark.unit
    def test_has_features_no_beads_dir(self, tmp_path):
        """Test has_features returns False when no .beads directory (fallback)."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        result = has_features(project_dir)

        assert result is False

    @pytest.mark.unit
    def test_has_features_with_beads_db(self, tmp_path):
        """Test has_features returns True when beads.db exists (fallback)."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()
        beads_dir = project_dir / ".beads"
        beads_dir.mkdir()
        (beads_dir / "beads.db").write_text("")

        result = has_features(project_dir)

        assert result is True

    @pytest.mark.unit
    def test_has_features_nonexistent_project(self, tmp_path):
        """Test has_features returns False for nonexistent project."""
        nonexistent = tmp_path / "nonexistent"

        result = has_features(nonexistent)

        assert result is False


class TestHasOpenFeatures:
    """Tests for has_open_features function."""

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_stats")
    def test_has_open_features_with_open(self, mock_cache, tmp_path):
        """Test has_open_features returns True when open issues exist."""
        mock_cache.return_value = {"pending": 1, "in_progress": 0}

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        result = has_open_features(project_dir, project_name="test-project")

        assert result is True

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_stats")
    def test_has_open_features_all_closed(self, mock_cache, tmp_path):
        """Test has_open_features returns False when all issues closed."""
        mock_cache.return_value = {"pending": 0, "in_progress": 0}

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        result = has_open_features(project_dir, project_name="test-project")

        assert result is False

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_stats")
    def test_has_open_features_in_progress(self, mock_cache, tmp_path):
        """Test has_open_features returns True for in_progress issues."""
        mock_cache.return_value = {"pending": 0, "in_progress": 1}

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        result = has_open_features(project_dir, project_name="test-project")

        assert result is True

    @pytest.mark.unit
    def test_has_open_features_fallback_returns_true(self, tmp_path):
        """Test fallback returns True (safer assumption)."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        result = has_open_features(project_dir)

        assert result is True


class TestGetProgressStats:
    """Tests for get_progress_stats function."""

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_stats")
    def test_get_progress_stats(self, mock_cache, tmp_path):
        """Test get_progress_stats calculates correctly."""
        mock_cache.return_value = {"done": 2, "in_progress": 1, "total": 4}

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        stats = get_progress_stats(project_dir, project_name="test-project")

        assert stats["total"] == 4
        assert stats["passing"] == 2
        assert stats["in_progress"] == 1
        assert stats["percentage"] == 50.0

    @pytest.mark.unit
    def test_get_progress_stats_empty(self, tmp_path):
        """Test get_progress_stats with no project_name (fallback)."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        stats = get_progress_stats(project_dir)

        assert stats["total"] == 0
        assert stats["passing"] == 0
        assert stats["percentage"] == 0.0

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_stats")
    def test_get_progress_stats_all_done(self, mock_cache, tmp_path):
        """Test get_progress_stats when all issues closed."""
        mock_cache.return_value = {"done": 2, "in_progress": 0, "total": 2}

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        stats = get_progress_stats(project_dir, project_name="test-project")

        assert stats["total"] == 2
        assert stats["passing"] == 2
        assert stats["percentage"] == 100.0


class TestProgressCalculations:
    """Tests for progress percentage calculations."""

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_stats")
    def test_percentage_precision(self, mock_cache, tmp_path):
        """Test percentage calculation precision."""
        mock_cache.return_value = {"done": 1, "in_progress": 0, "total": 3}

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        stats = get_progress_stats(project_dir, project_name="test-project")

        # Should be approximately 33.33
        assert 33.0 <= stats["percentage"] <= 34.0

    @pytest.mark.unit
    def test_percentage_zero_total(self, tmp_path):
        """Test percentage when no issues (fallback)."""
        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        stats = get_progress_stats(project_dir)

        # Should not divide by zero
        assert stats["percentage"] == 0.0
