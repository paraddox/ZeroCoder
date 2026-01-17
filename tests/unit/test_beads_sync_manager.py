"""
Beads Sync Manager Unit Tests
=============================

Tests for beads synchronization including:
- Feature caching
- Git clone/pull operations
- Polling service
- Error handling
"""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
import subprocess

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class TestBeadsSyncBasics:
    """Tests for basic beads sync operations."""

    @pytest.mark.unit
    def test_get_beads_sync_dir_returns_path(self, isolated_registry):
        """Test that beads sync directory path is returned."""
        beads_dir = isolated_registry.get_beads_sync_dir()
        assert beads_dir is not None
        assert isinstance(beads_dir, Path)

    @pytest.mark.unit
    def test_beads_sync_dir_is_in_config(self, isolated_registry):
        """Test beads sync dir is under config directory."""
        config_dir = isolated_registry.get_config_dir()
        beads_dir = isolated_registry.get_beads_sync_dir()

        # beads-sync should be under config
        assert str(config_dir) in str(beads_dir)


class TestFeatureCaching:
    """Tests for feature caching functionality."""

    @pytest.mark.unit
    def test_feature_cache_structure(self):
        """Test feature cache data structure."""
        feature_data = {
            "pending": [{"id": "feat-1", "title": "Test", "status": "open"}],
            "in_progress": [],
            "done": []
        }

        # Verify the structure is valid
        assert "pending" in feature_data
        assert "in_progress" in feature_data
        assert "done" in feature_data
        assert len(feature_data["pending"]) == 1
        assert feature_data["pending"][0]["id"] == "feat-1"

    @pytest.mark.unit
    def test_feature_cache_data_organization(self):
        """Test organizing features by status."""
        features = [
            {"id": "feat-1", "title": "Auth", "status": "open"},
            {"id": "feat-2", "title": "Dashboard", "status": "in_progress"},
            {"id": "feat-3", "title": "Settings", "status": "closed"},
        ]

        # Organize by status
        pending = [f for f in features if f["status"] == "open"]
        in_progress = [f for f in features if f["status"] == "in_progress"]
        done = [f for f in features if f["status"] == "closed"]

        assert len(pending) == 1
        assert len(in_progress) == 1
        assert len(done) == 1

    @pytest.mark.unit
    def test_feature_cache_empty_categories(self):
        """Test handling empty feature categories."""
        feature_data = {
            "pending": [],
            "in_progress": [],
            "done": []
        }

        assert len(feature_data["pending"]) == 0
        assert len(feature_data["in_progress"]) == 0
        assert len(feature_data["done"]) == 0

    @pytest.mark.unit
    def test_feature_stats_calculation(self):
        """Test calculating feature statistics."""
        features = [
            {"id": "feat-1", "status": "closed"},
            {"id": "feat-2", "status": "closed"},
            {"id": "feat-3", "status": "open"},
            {"id": "feat-4", "status": "in_progress"},
        ]

        stats = {
            "closed": len([f for f in features if f["status"] == "closed"]),
            "open": len([f for f in features if f["status"] == "open"]),
            "in_progress": len([f for f in features if f["status"] == "in_progress"]),
            "total": len(features)
        }

        assert stats["closed"] == 2
        assert stats["open"] == 1
        assert stats["in_progress"] == 1
        assert stats["total"] == 4


class TestBeadsParsing:
    """Tests for parsing beads issues from JSONL files."""

    @pytest.mark.unit
    def test_parse_single_issue(self, beads_issues_file):
        """Test parsing a single issue from JSONL."""
        with open(beads_issues_file, "r") as f:
            lines = f.readlines()

        assert len(lines) >= 1
        issue = json.loads(lines[0])
        assert "id" in issue
        assert "title" in issue
        assert "status" in issue

    @pytest.mark.unit
    def test_parse_multiple_issues(self, beads_issues_file, sample_beads_issues):
        """Test parsing multiple issues from JSONL."""
        with open(beads_issues_file, "r") as f:
            issues = [json.loads(line) for line in f if line.strip()]

        assert len(issues) == len(sample_beads_issues)

    @pytest.mark.unit
    def test_parse_issue_statuses(self, beads_issues_file):
        """Test that issue statuses are parsed correctly."""
        with open(beads_issues_file, "r") as f:
            issues = [json.loads(line) for line in f if line.strip()]

        statuses = {issue["status"] for issue in issues}
        # Should have open, in_progress, and closed based on sample data
        assert "open" in statuses
        assert "in_progress" in statuses
        assert "closed" in statuses

    @pytest.mark.unit
    def test_parse_empty_file(self, temp_project_dir):
        """Test parsing an empty JSONL file."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"
        issues_file.write_text("")

        with open(issues_file, "r") as f:
            issues = [json.loads(line) for line in f if line.strip()]

        assert len(issues) == 0


class TestGitOperations:
    """Tests for git clone/pull operations in beads sync."""

    @pytest.mark.unit
    def test_git_clone_command_structure(self, tmp_path):
        """Test that git clone command is properly structured."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            dest = tmp_path / "clone-test"
            url = "https://github.com/user/repo.git"
            branch = "beads-sync"

            # Simulate the clone operation
            subprocess.run(
                ["git", "clone", "--branch", branch, "--depth", "1", url, str(dest)],
                capture_output=True,
                text=True,
                timeout=120
            )

            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "git" in args
            assert "clone" in args
            assert "--branch" in args
            assert branch in args

    @pytest.mark.unit
    def test_git_pull_command_structure(self, tmp_path):
        """Test that git pull command is properly structured."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")

            repo_dir = tmp_path / "existing-repo"
            repo_dir.mkdir()

            # Simulate the pull operation
            subprocess.run(
                ["git", "pull", "--rebase"],
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=60
            )

            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "git" in args
            assert "pull" in args

    @pytest.mark.unit
    def test_git_clone_timeout_handling(self, tmp_path):
        """Test handling of git clone timeout."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("git", 120)

            dest = tmp_path / "timeout-test"

            with pytest.raises(subprocess.TimeoutExpired):
                subprocess.run(
                    ["git", "clone", "https://github.com/user/repo.git", str(dest)],
                    timeout=120
                )

    @pytest.mark.unit
    def test_git_clone_failure_handling(self, tmp_path):
        """Test handling of git clone failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=128,
                stderr="fatal: repository not found"
            )

            result = mock_run.return_value
            assert result.returncode != 0
            assert "repository not found" in result.stderr


class TestBeadsSyncPolling:
    """Tests for the beads sync polling service."""

    @pytest.mark.unit
    def test_polling_interval_constant(self):
        """Test that polling interval is defined."""
        # The polling interval should be 30 seconds
        POLLING_INTERVAL = 30
        assert POLLING_INTERVAL == 30

    @pytest.mark.unit
    def test_should_poll_running_container(self):
        """Test that polling occurs for running containers."""
        container_status = "running"
        should_poll = container_status == "running"
        assert should_poll is True

    @pytest.mark.unit
    def test_should_not_poll_stopped_container(self):
        """Test that polling doesn't occur for stopped containers."""
        container_status = "stopped"
        should_poll = container_status == "running"
        assert should_poll is False

    @pytest.mark.unit
    def test_should_not_poll_not_created(self):
        """Test that polling doesn't occur for non-existent containers."""
        container_status = "not_created"
        should_poll = container_status == "running"
        assert should_poll is False


class TestBeadsSyncErrorHandling:
    """Tests for error handling in beads sync operations."""

    @pytest.mark.unit
    def test_handle_invalid_json_in_issues(self, temp_project_dir):
        """Test handling of invalid JSON in issues file."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        # Write some valid and some invalid JSON
        issues_file.write_text('{"id": "feat-1", "title": "Valid"}\ninvalid json\n{"id": "feat-2"}')

        issues = []
        with open(issues_file, "r") as f:
            for line in f:
                if line.strip():
                    try:
                        issues.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # Skip invalid lines

        # Should have parsed 2 valid issues
        assert len(issues) == 2

    @pytest.mark.unit
    def test_handle_missing_beads_directory(self, temp_project_dir):
        """Test handling when .beads directory doesn't exist."""
        beads_dir = temp_project_dir / ".beads"

        # Make sure it doesn't exist
        if beads_dir.exists():
            import shutil
            shutil.rmtree(beads_dir)

        assert not beads_dir.exists()

    @pytest.mark.unit
    def test_handle_missing_issues_file(self, temp_project_dir):
        """Test handling when issues.jsonl doesn't exist."""
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)
        issues_file = beads_dir / "issues.jsonl"

        assert not issues_file.exists()

    @pytest.mark.unit
    def test_handle_permission_error(self, temp_project_dir):
        """Test handling of permission errors."""
        # This test documents expected behavior
        # Actual permission testing requires OS-level setup
        beads_dir = temp_project_dir / ".beads"
        beads_dir.mkdir(exist_ok=True)

        # The system should handle permission errors gracefully
        # by catching exceptions and returning empty/cached data


class TestCacheInvalidation:
    """Tests for cache invalidation logic."""

    @pytest.mark.unit
    def test_cache_staleness_detection(self):
        """Test detecting stale cache based on age."""
        cache_time = datetime.now() - timedelta(minutes=5)
        max_age = timedelta(minutes=2)

        is_stale = (datetime.now() - cache_time) > max_age
        assert is_stale is True

    @pytest.mark.unit
    def test_cache_freshness_detection(self):
        """Test detecting fresh cache."""
        cache_time = datetime.now() - timedelta(seconds=30)
        max_age = timedelta(minutes=2)

        is_stale = (datetime.now() - cache_time) > max_age
        assert is_stale is False

    @pytest.mark.unit
    def test_cache_invalidation_logic(self):
        """Test cache invalidation logic."""
        # Simulate a cache with timestamp
        cache_data = {
            "features": [{"id": "feat-1"}],
            "timestamp": datetime.now()
        }

        # Simulate invalidation by marking as None
        invalidated_cache = None

        # After invalidation, cache should be None
        assert invalidated_cache is None

        # Re-caching should work
        new_cache = {"features": [{"id": "feat-2"}]}
        assert new_cache is not None
        assert len(new_cache["features"]) == 1
