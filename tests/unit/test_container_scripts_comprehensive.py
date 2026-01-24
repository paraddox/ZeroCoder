"""
Container Scripts Comprehensive Tests
=====================================

Tests for the container scripts including:
- beads_commands.py JSON protocol
- Feature CRUD operations
- Priority conversions
- Error handling
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import subprocess

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Priority Conversion Tests
# =============================================================================

class TestPriorityConversion:
    """Tests for priority conversion functions."""

    @pytest.mark.unit
    def test_priority_to_beads_p0(self):
        """Test converting priority 0 to P0."""
        from container_scripts.beads_commands import priority_to_beads

        result = priority_to_beads(0)
        assert result == "P0"

    @pytest.mark.unit
    def test_priority_to_beads_p4(self):
        """Test converting priority 4 to P4."""
        from container_scripts.beads_commands import priority_to_beads

        result = priority_to_beads(4)
        assert result == "P4"

    @pytest.mark.unit
    def test_priority_to_beads_default(self):
        """Test default priority conversion."""
        from container_scripts.beads_commands import priority_to_beads

        result = priority_to_beads(2)
        assert result == "P2"

    @pytest.mark.unit
    def test_beads_to_priority_p0(self):
        """Test converting P0 to priority 0."""
        from container_scripts.beads_commands import beads_to_priority

        result = beads_to_priority("P0")
        assert result == 0

    @pytest.mark.unit
    def test_beads_to_priority_p4(self):
        """Test converting P4 to priority 4."""
        from container_scripts.beads_commands import beads_to_priority

        result = beads_to_priority("P4")
        assert result == 4

    @pytest.mark.unit
    def test_beads_to_priority_lowercase(self):
        """Test converting lowercase p2 to priority 2."""
        from container_scripts.beads_commands import beads_to_priority

        result = beads_to_priority("p2")
        assert result == 2

    @pytest.mark.unit
    def test_beads_to_priority_default(self):
        """Test default priority for invalid string."""
        from container_scripts.beads_commands import beads_to_priority

        result = beads_to_priority("invalid")
        assert result == 4  # Default priority (P4 = backlog)


# =============================================================================
# Label Extraction Tests
# =============================================================================

class TestLabelExtraction:
    """Tests for label value extraction."""

    @pytest.mark.unit
    def test_extract_label_value_found(self):
        """Test extracting existing label value."""
        from container_scripts.beads_commands import extract_label_value

        labels = ["category:authentication", "type:feature"]
        result = extract_label_value(labels, "category")

        assert result == "authentication"

    @pytest.mark.unit
    def test_extract_label_value_not_found(self):
        """Test extracting non-existent label returns None."""
        from container_scripts.beads_commands import extract_label_value

        labels = ["category:authentication", "type:feature"]
        result = extract_label_value(labels, "priority")

        assert result is None

    @pytest.mark.unit
    def test_extract_label_value_empty_list(self):
        """Test extracting from empty label list."""
        from container_scripts.beads_commands import extract_label_value

        result = extract_label_value([], "category")

        assert result is None

    @pytest.mark.unit
    def test_extract_label_value_no_colon(self):
        """Test labels without colon separator."""
        from container_scripts.beads_commands import extract_label_value

        labels = ["authentication", "feature"]
        result = extract_label_value(labels, "category")

        assert result is None


# =============================================================================
# Run BD Command Tests
# =============================================================================

class TestRunBd:
    """Tests for run_bd function."""

    @pytest.mark.unit
    def test_run_bd_success(self):
        """Test successful bd command execution."""
        from container_scripts.beads_commands import run_bd

        mock_result = MagicMock(
            returncode=0,
            stdout='{"status": "ok"}',
            stderr=""
        )

        with patch("container_scripts.beads_commands.subprocess.run", return_value=mock_result):
            result = run_bd(["list", "--json"])

        # run_bd returns CompletedProcess, not parsed JSON
        assert result.returncode == 0
        assert result.stdout == '{"status": "ok"}'

    @pytest.mark.unit
    def test_run_bd_failure(self):
        """Test bd command failure with check=True."""
        from container_scripts.beads_commands import run_bd

        # When check=True is passed, subprocess.run raises CalledProcessError
        with patch("container_scripts.beads_commands.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(
                returncode=1,
                cmd=["bd", "invalid"],
                stderr="Error: command failed"
            )

            with pytest.raises(subprocess.CalledProcessError) as exc_info:
                run_bd(["invalid"], check=True)

            assert exc_info.value.returncode == 1

    @pytest.mark.unit
    def test_run_bd_empty_output(self):
        """Test bd command with empty output."""
        from container_scripts.beads_commands import run_bd

        mock_result = MagicMock(
            returncode=0,
            stdout="",
            stderr=""
        )

        with patch("container_scripts.beads_commands.subprocess.run", return_value=mock_result):
            result = run_bd(["sync"])

        # run_bd returns CompletedProcess with empty stdout
        assert result.returncode == 0
        assert result.stdout == ""

    @pytest.mark.unit
    def test_run_bd_invalid_json(self):
        """Test bd command with invalid JSON output."""
        from container_scripts.beads_commands import run_bd

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="not valid json",
                stderr=""
            )

            # Should handle invalid JSON gracefully
            try:
                result = run_bd(["list"])
                # If it doesn't raise, result should be the raw string or None
            except json.JSONDecodeError:
                pass  # Expected behavior


# =============================================================================
# List Features Tests
# =============================================================================

class TestListFeatures:
    """Tests for listing features."""

    @pytest.mark.unit
    def test_handle_list_action(self, tmp_path):
        """Test handling list action."""
        from container_scripts.beads_commands import handle_action

        # Create a mock .beads directory with issues.jsonl
        beads_dir = tmp_path / ".beads"
        beads_dir.mkdir()
        jsonl_file = beads_dir / "issues.jsonl"
        jsonl_file.write_text(
            '{"id": "feat-1", "title": "Feature 1", "status": "open", "priority": "P1", "labels": []}\n'
            '{"id": "feat-2", "title": "Feature 2", "status": "closed", "priority": "P2", "labels": []}\n'
        )

        # Patch BEADS_DIR to use our temp directory
        with patch("container_scripts.beads_commands.BEADS_DIR", beads_dir):
            result = handle_action({"action": "list"})

        assert "features" in result
        assert len(result["features"]) == 2


# =============================================================================
# Create Feature Tests
# =============================================================================

class TestCreateFeature:
    """Tests for creating features."""

    @pytest.mark.unit
    def test_handle_create_action(self):
        """Test handling create action."""
        from container_scripts.beads_commands import handle_action

        mock_create_result = MagicMock(
            returncode=0,
            stdout='{"id": "feat-3"}',
            stderr=""
        )
        mock_get_result = MagicMock(
            returncode=0,
            stdout='{"id": "feat-3", "title": "New Feature", "status": "open"}',
            stderr=""
        )

        with patch("container_scripts.beads_commands.is_initialized", return_value=True):
            with patch("container_scripts.beads_commands.run_bd", side_effect=[mock_create_result, mock_get_result]):
                # Note: create expects parameters nested under 'data' key
                result = handle_action({
                    "action": "create",
                    "data": {
                        "name": "New Feature",
                        "description": "Feature description",
                        "priority": 1,
                        "category": "authentication"
                    }
                })

        assert result.get("success") is True or "feature" in result

    @pytest.mark.unit
    def test_handle_create_missing_title(self):
        """Test create action without name."""
        from container_scripts.beads_commands import handle_action

        with patch("container_scripts.beads_commands.is_initialized", return_value=True):
            result = handle_action({
                "action": "create",
                "description": "Feature description"
            })

        assert "error" in result


# =============================================================================
# Update Feature Tests
# =============================================================================

class TestUpdateFeature:
    """Tests for updating features."""

    @pytest.mark.unit
    def test_handle_update_action(self):
        """Test handling update action."""
        from container_scripts.beads_commands import handle_action

        mock_get_result = MagicMock(
            returncode=0,
            stdout='{"id": "feat-1", "title": "Feature 1", "status": "open", "priority": "P2", "labels": []}',
            stderr=""
        )
        mock_update_result = MagicMock(
            returncode=0,
            stdout='{}',
            stderr=""
        )
        mock_get_result2 = MagicMock(
            returncode=0,
            stdout='{"id": "feat-1", "title": "Feature 1", "status": "in_progress"}',
            stderr=""
        )

        with patch("container_scripts.beads_commands.run_bd", side_effect=[mock_get_result, mock_update_result, mock_get_result2]):
            # Note: update expects feature_id and data keys
            result = handle_action({
                "action": "update",
                "feature_id": "feat-1",
                "data": {"status": "in_progress"}
            })

        assert result.get("success") is True or "error" not in result

    @pytest.mark.unit
    def test_handle_update_missing_id(self):
        """Test update action without ID."""
        from container_scripts.beads_commands import handle_action

        result = handle_action({
            "action": "update",
            "status": "in_progress"
        })

        assert "error" in result


# =============================================================================
# Delete Feature Tests
# =============================================================================

class TestDeleteFeature:
    """Tests for deleting features."""

    @pytest.mark.unit
    def test_handle_delete_action(self):
        """Test handling delete action."""
        from container_scripts.beads_commands import handle_action

        mock_result = MagicMock(
            returncode=0,
            stdout='{}',
            stderr=""
        )

        with patch("container_scripts.beads_commands.run_bd", return_value=mock_result):
            # Note: delete expects feature_id key
            result = handle_action({
                "action": "delete",
                "feature_id": "feat-1"
            })

        assert result.get("success") is True or "error" not in result

    @pytest.mark.unit
    def test_handle_delete_missing_id(self):
        """Test delete action without ID."""
        from container_scripts.beads_commands import handle_action

        result = handle_action({
            "action": "delete"
        })

        assert "error" in result


# =============================================================================
# Reopen Feature Tests
# =============================================================================

class TestReopenFeature:
    """Tests for reopening features."""

    @pytest.mark.unit
    def test_handle_reopen_action(self):
        """Test handling reopen action."""
        from container_scripts.beads_commands import handle_action

        mock_reopen_result = MagicMock(
            returncode=0,
            stdout='{}',
            stderr=""
        )
        mock_get_result = MagicMock(
            returncode=0,
            stdout='{"id": "feat-1", "title": "Feature 1", "status": "open"}',
            stderr=""
        )

        with patch("container_scripts.beads_commands.run_bd", side_effect=[mock_reopen_result, mock_get_result]):
            # Note: reopen expects feature_id key
            result = handle_action({
                "action": "reopen",
                "feature_id": "feat-1"
            })

        assert result.get("success") is True or "error" not in result


# =============================================================================
# Unknown Action Tests
# =============================================================================

class TestUnknownAction:
    """Tests for unknown actions."""

    @pytest.mark.unit
    def test_handle_unknown_action(self):
        """Test handling unknown action returns error."""
        from container_scripts.beads_commands import handle_action

        result = handle_action({
            "action": "unknown_action"
        })

        assert "error" in result

    @pytest.mark.unit
    def test_handle_missing_action(self):
        """Test handling missing action field."""
        from container_scripts.beads_commands import handle_action

        result = handle_action({})

        assert "error" in result


# =============================================================================
# Init Action Tests
# =============================================================================

class TestInitAction:
    """Tests for init action."""

    @pytest.mark.unit
    def test_handle_init_action(self):
        """Test handling init action."""
        from container_scripts.beads_commands import handle_action

        mock_init_result = MagicMock(
            returncode=0,
            stdout='',
            stderr=""
        )

        with patch("container_scripts.beads_commands.run_bd", return_value=mock_init_result):
            result = handle_action({
                "action": "init"
            })

        assert result.get("success") is True or "error" not in result
