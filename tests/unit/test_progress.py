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
    def test_has_features_with_issues_file(self, temp_project_dir, sample_beads_issues):
        """Test detecting features from issues.jsonl file."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        with open(issues_file, "w") as f:
            for issue in sample_beads_issues:
                f.write(json.dumps(issue) + "\n")

        result = has_features(temp_project_dir)
        assert result is True

    @pytest.mark.unit
    def test_has_features_empty_issues_file(self, temp_project_dir):
        """Test detecting no features from empty issues.jsonl."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text("")

        result = has_features(temp_project_dir)
        assert result is False

    @pytest.mark.unit
    def test_has_features_no_beads_directory(self, temp_project_dir):
        """Test detecting no features when .beads doesn't exist."""
        result = has_features(temp_project_dir)
        assert result is False

    @pytest.mark.unit
    def test_has_features_whitespace_only_file(self, temp_project_dir):
        """Test detecting no features from whitespace-only file."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text("   \n  \n  ")

        result = has_features(temp_project_dir)
        assert result is False

    @pytest.mark.unit
    def test_has_features_with_project_name_cache(self, temp_project_dir):
        """Test has_features with project_name triggers cache lookup."""
        with patch("server.services.beads_sync_manager.get_cached_stats") as mock_cache:
            mock_cache.return_value = {"total": 5}

            result = has_features(temp_project_dir, project_name="test-project")
            assert result is True
            mock_cache.assert_called_once_with("test-project")


class TestHasOpenFeatures:
    """Tests for has_open_features function."""

    @pytest.mark.unit
    def test_has_open_features_with_open_issues(self, temp_project_dir):
        """Test detecting open features."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        issues = [
            {"id": "feat-1", "title": "Open", "status": "open"},
            {"id": "feat-2", "title": "Closed", "status": "closed"},
        ]
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        result = has_open_features(temp_project_dir)
        assert result is True

    @pytest.mark.unit
    def test_has_open_features_with_in_progress(self, temp_project_dir):
        """Test detecting in_progress features."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        issues = [
            {"id": "feat-1", "title": "In Progress", "status": "in_progress"},
        ]
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        result = has_open_features(temp_project_dir)
        assert result is True

    @pytest.mark.unit
    def test_has_open_features_all_closed(self, temp_project_dir):
        """Test detecting no open features when all closed."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        issues = [
            {"id": "feat-1", "title": "Closed 1", "status": "closed"},
            {"id": "feat-2", "title": "Closed 2", "status": "closed"},
        ]
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        result = has_open_features(temp_project_dir)
        assert result is False

    @pytest.mark.unit
    def test_has_open_features_empty(self, temp_project_dir):
        """Test detecting no open features when file is empty."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text("")

        result = has_open_features(temp_project_dir)
        assert result is False


class TestCountPassingTests:
    """Tests for count_passing_tests function."""

    @pytest.mark.unit
    def test_count_passing_tests_mixed_statuses(self, temp_project_dir, sample_beads_issues):
        """Test counting with mixed status issues."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        with open(issues_file, "w") as f:
            for issue in sample_beads_issues:
                f.write(json.dumps(issue) + "\n")

        passing, in_progress, total = count_passing_tests(temp_project_dir)

        # From sample_beads_issues: 1 open, 1 in_progress, 1 closed
        assert passing == 1
        assert in_progress == 1
        assert total == 3

    @pytest.mark.unit
    def test_count_passing_tests_all_passing(self, temp_project_dir):
        """Test counting when all tests pass."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        issues = [
            {"id": "feat-1", "title": "Test 1", "status": "closed"},
            {"id": "feat-2", "title": "Test 2", "status": "closed"},
            {"id": "feat-3", "title": "Test 3", "status": "closed"},
        ]
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        passing, in_progress, total = count_passing_tests(temp_project_dir)

        assert passing == 3
        assert in_progress == 0
        assert total == 3

    @pytest.mark.unit
    def test_count_passing_tests_none_passing(self, temp_project_dir):
        """Test counting when no tests pass."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        issues = [
            {"id": "feat-1", "title": "Test 1", "status": "open"},
            {"id": "feat-2", "title": "Test 2", "status": "in_progress"},
        ]
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        passing, in_progress, total = count_passing_tests(temp_project_dir)

        assert passing == 0
        assert in_progress == 1
        assert total == 2

    @pytest.mark.unit
    def test_count_passing_tests_empty_project(self, temp_project_dir):
        """Test counting with no issues."""
        passing, in_progress, total = count_passing_tests(temp_project_dir)

        assert passing == 0
        assert in_progress == 0
        assert total == 0

    @pytest.mark.unit
    def test_count_passing_tests_malformed_json(self, temp_project_dir):
        """Test counting handles malformed JSON gracefully."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        content = '{"id": "feat-1", "status": "closed"}\n'
        content += 'not valid json\n'
        content += '{"id": "feat-2", "status": "open"}\n'
        issues_file.write_text(content)

        passing, in_progress, total = count_passing_tests(temp_project_dir)

        # Should skip malformed line and count valid ones
        assert total == 2
        assert passing == 1


class TestGetAllPassingFeatures:
    """Tests for get_all_passing_features function."""

    @pytest.mark.unit
    def test_get_all_passing_features(self, temp_project_dir):
        """Test getting list of passing features."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        issues = [
            {"id": "feat-1", "title": "Auth Login", "status": "closed", "labels": ["category:auth"]},
            {"id": "feat-2", "title": "Dashboard", "status": "open", "labels": ["category:ui"]},
            {"id": "feat-3", "title": "API Client", "status": "closed", "labels": ["category:backend"]},
        ]
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        passing = get_all_passing_features(temp_project_dir)

        assert len(passing) == 2
        assert any(f["id"] == "feat-1" for f in passing)
        assert any(f["id"] == "feat-3" for f in passing)
        assert not any(f["id"] == "feat-2" for f in passing)

    @pytest.mark.unit
    def test_get_all_passing_features_extracts_category(self, temp_project_dir):
        """Test that category is extracted from labels."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        issues = [
            {"id": "feat-1", "title": "Test", "status": "closed", "labels": ["category:authentication"]},
        ]
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        passing = get_all_passing_features(temp_project_dir)

        assert len(passing) == 1
        assert passing[0]["category"] == "authentication"

    @pytest.mark.unit
    def test_get_all_passing_features_no_category(self, temp_project_dir):
        """Test handling features without category label."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        issues = [
            {"id": "feat-1", "title": "Test", "status": "closed", "labels": ["other-label"]},
        ]
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        passing = get_all_passing_features(temp_project_dir)

        assert len(passing) == 1
        assert passing[0]["category"] == ""

    @pytest.mark.unit
    def test_get_all_passing_features_empty(self, temp_project_dir):
        """Test getting passing features from empty project."""
        passing = get_all_passing_features(temp_project_dir)
        assert len(passing) == 0


class TestProgressCache:
    """Tests for progress caching functionality."""

    @pytest.mark.unit
    def test_cache_file_location(self):
        """Test that cache file name is correct."""
        assert PROGRESS_CACHE_FILE == ".progress_cache"

    @pytest.mark.unit
    def test_progress_cache_used_by_webhook(self, temp_project_dir):
        """Test that webhook uses cache to track previous progress."""
        from progress import send_progress_webhook

        cache_file = temp_project_dir / PROGRESS_CACHE_FILE

        # Initially no cache
        assert not cache_file.exists()

        # Setup issues
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        issues = [
            {"id": "feat-1", "title": "Test", "status": "closed"},
        ]
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        # Call webhook with mocked URL and urllib.request.urlopen
        with patch("progress.WEBHOOK_URL", "http://test-webhook.com"):
            with patch("urllib.request.urlopen") as mock_urlopen:
                mock_urlopen.return_value = MagicMock()
                send_progress_webhook(1, 1, temp_project_dir)

        # Cache should exist now (only written when WEBHOOK_URL is configured)
        assert cache_file.exists()

        cache_data = json.loads(cache_file.read_text())
        assert cache_data["count"] == 1


class TestCacheLookup:
    """Tests for cache lookup functionality in progress functions."""

    @pytest.mark.unit
    def test_count_passing_uses_cache(self, temp_project_dir):
        """Test that count_passing_tests uses cache when available."""
        with patch("server.services.beads_sync_manager.get_cached_stats") as mock_cache:
            mock_cache.return_value = {
                "done": 5,
                "in_progress": 2,
                "total": 10,
            }

            passing, in_progress, total = count_passing_tests(
                temp_project_dir,
                project_name="test-project"
            )

            assert passing == 5
            assert in_progress == 2
            assert total == 10
            mock_cache.assert_called_once_with("test-project")

    @pytest.mark.unit
    def test_count_passing_fallback_to_file(self, temp_project_dir, sample_beads_issues):
        """Test that count_passing_tests falls back to file when cache empty."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        with open(issues_file, "w") as f:
            for issue in sample_beads_issues:
                f.write(json.dumps(issue) + "\n")

        with patch("server.services.beads_sync_manager.get_cached_stats") as mock_cache:
            mock_cache.return_value = {"total": 0}  # Empty cache

            passing, in_progress, total = count_passing_tests(
                temp_project_dir,
                project_name="test-project"
            )

            # Should fallback to file reading
            assert total == 3  # From sample_beads_issues


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.unit
    def test_handles_permission_error(self, temp_project_dir):
        """Test handling of permission errors."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text('{"id": "1", "status": "open"}')

        with patch("builtins.open", side_effect=PermissionError("No access")):
            # Should not raise, just return defaults
            result = has_features(temp_project_dir)
            # Will try DB fallback next, which also fails, so False
            assert result is False

    @pytest.mark.unit
    def test_handles_missing_status_field(self, temp_project_dir):
        """Test handling issues without status field."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        # Issue without status field (defaults to "open")
        issues = [
            {"id": "feat-1", "title": "Test"},  # No status
        ]
        with open(issues_file, "w") as f:
            for issue in issues:
                f.write(json.dumps(issue) + "\n")

        result = has_open_features(temp_project_dir)
        assert result is True  # Defaults to open

    @pytest.mark.unit
    def test_handles_unicode_content(self, temp_project_dir):
        """Test handling unicode in issue content."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        issues = [
            {"id": "feat-1", "title": "日本語テスト", "status": "closed"},
            {"id": "feat-2", "title": "Émoji 🚀", "status": "open"},
        ]
        with open(issues_file, "w", encoding="utf-8") as f:
            for issue in issues:
                f.write(json.dumps(issue, ensure_ascii=False) + "\n")

        passing, in_progress, total = count_passing_tests(temp_project_dir)

        assert total == 2
        assert passing == 1
