"""
Progress Module Unit Tests
==========================

Tests for progress tracking functionality including:
- Feature detection
- Progress counting
- Webhook notifications
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
    PROGRESS_CACHE_FILE,
)


class TestHasFeatures:
    """Tests for has_features function."""

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_stats")
    def test_has_features_with_project_name(self, mock_cache, temp_project_dir):
        """Test detecting features via beads_manager."""
        mock_cache.return_value = {"total": 5}

        result = has_features(temp_project_dir, project_name="test-project")
        assert result is True
        mock_cache.assert_called_once_with("test-project")

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_stats")
    def test_has_features_no_features(self, mock_cache, temp_project_dir):
        """Test detecting no features when total is 0."""
        mock_cache.return_value = {"total": 0}

        result = has_features(temp_project_dir, project_name="test-project")
        assert result is False

    @pytest.mark.unit
    def test_has_features_no_beads_directory(self, temp_project_dir):
        """Test detecting no features when .beads doesn't exist (fallback)."""
        result = has_features(temp_project_dir)
        assert result is False

    @pytest.mark.unit
    def test_has_features_with_beads_db(self, temp_project_dir):
        """Test detecting features when beads.db exists (fallback)."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        (beads_dir / "beads.db").write_text("")  # Create empty db file

        result = has_features(temp_project_dir)
        assert result is True


class TestHasOpenFeatures:
    """Tests for has_open_features function."""

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_stats")
    def test_has_open_features_with_open_issues(self, mock_cache, temp_project_dir):
        """Test detecting open features."""
        mock_cache.return_value = {"pending": 1, "in_progress": 0}

        result = has_open_features(temp_project_dir, project_name="test-project")
        assert result is True

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_stats")
    def test_has_open_features_with_in_progress(self, mock_cache, temp_project_dir):
        """Test detecting in_progress features."""
        mock_cache.return_value = {"pending": 0, "in_progress": 1}

        result = has_open_features(temp_project_dir, project_name="test-project")
        assert result is True

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_stats")
    def test_has_open_features_all_closed(self, mock_cache, temp_project_dir):
        """Test detecting no open features when all closed."""
        mock_cache.return_value = {"pending": 0, "in_progress": 0}

        result = has_open_features(temp_project_dir, project_name="test-project")
        assert result is False

    @pytest.mark.unit
    def test_has_open_features_fallback_returns_true(self, temp_project_dir):
        """Test fallback returns True (safer assumption)."""
        result = has_open_features(temp_project_dir)
        assert result is True


class TestCountPassingTests:
    """Tests for count_passing_tests function."""

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_stats")
    def test_count_passing_tests_mixed_statuses(self, mock_cache, temp_project_dir):
        """Test counting with mixed status issues."""
        mock_cache.return_value = {"done": 1, "in_progress": 1, "total": 3}

        passing, in_progress, total = count_passing_tests(temp_project_dir, project_name="test-project")

        assert passing == 1
        assert in_progress == 1
        assert total == 3

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_stats")
    def test_count_passing_tests_all_passing(self, mock_cache, temp_project_dir):
        """Test counting when all tests pass."""
        mock_cache.return_value = {"done": 3, "in_progress": 0, "total": 3}

        passing, in_progress, total = count_passing_tests(temp_project_dir, project_name="test-project")

        assert passing == 3
        assert in_progress == 0
        assert total == 3

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_stats")
    def test_count_passing_tests_none_passing(self, mock_cache, temp_project_dir):
        """Test counting when no tests pass."""
        mock_cache.return_value = {"done": 0, "in_progress": 1, "total": 2}

        passing, in_progress, total = count_passing_tests(temp_project_dir, project_name="test-project")

        assert passing == 0
        assert in_progress == 1
        assert total == 2

    @pytest.mark.unit
    def test_count_passing_tests_empty_project(self, temp_project_dir):
        """Test counting with no issues (fallback)."""
        passing, in_progress, total = count_passing_tests(temp_project_dir)

        assert passing == 0
        assert in_progress == 0
        assert total == 0


class TestGetAllPassingFeatures:
    """Tests for get_all_passing_features function."""

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_features")
    def test_get_all_passing_features(self, mock_cache, temp_project_dir):
        """Test getting passing features."""
        mock_cache.return_value = [
            {"id": "feat-1", "category": "auth", "name": "Login", "passes": True},
            {"id": "feat-2", "category": "api", "name": "Endpoint", "passes": False},
            {"id": "feat-3", "category": "ui", "name": "Button", "status": "closed"},
        ]

        result = get_all_passing_features(temp_project_dir, project_name="test-project")

        assert len(result) == 2
        assert result[0]["id"] == "feat-1"
        assert result[1]["id"] == "feat-3"

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_features")
    def test_get_all_passing_features_extracts_category(self, mock_cache, temp_project_dir):
        """Test that category is extracted correctly."""
        mock_cache.return_value = [
            {"id": "feat-1", "category": "authentication", "name": "Login", "passes": True},
        ]

        result = get_all_passing_features(temp_project_dir, project_name="test-project")

        assert len(result) == 1
        assert result[0]["category"] == "authentication"

    @pytest.mark.unit
    def test_get_all_passing_features_empty_fallback(self, temp_project_dir):
        """Test fallback returns empty list."""
        result = get_all_passing_features(temp_project_dir)
        assert result == []


class TestCacheLookup:
    """Tests for cache lookup behavior."""

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_stats")
    def test_count_passing_with_project_name(self, mock_cache, temp_project_dir):
        """Test that project_name triggers beads_manager lookup."""
        mock_cache.return_value = {"done": 3, "in_progress": 0, "total": 3}

        passing, in_progress, total = count_passing_tests(temp_project_dir, project_name="test-project")

        mock_cache.assert_called_once_with("test-project")
        assert total == 3


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.unit
    @patch("server.services.beads_manager.get_cached_features")
    def test_handles_unicode_content(self, mock_cache, temp_project_dir):
        """Test handling of unicode in feature names."""
        mock_cache.return_value = [
            {"id": "feat-1", "category": "测试", "name": "Tëst Fëätürë 日本語", "passes": True},
            {"id": "feat-2", "category": "功能", "name": "功能测试", "passes": True},
        ]

        result = get_all_passing_features(temp_project_dir, project_name="test-project")

        assert len(result) == 2
        assert result[0]["name"] == "Tëst Fëätürë 日本語"
        assert result[1]["category"] == "功能"


class TestWebhookNotification:
    """Tests for webhook notification functions."""

    @pytest.mark.unit
    def test_progress_cache_file_constant(self):
        """Test that PROGRESS_CACHE_FILE is defined."""
        assert PROGRESS_CACHE_FILE == ".progress_cache"
