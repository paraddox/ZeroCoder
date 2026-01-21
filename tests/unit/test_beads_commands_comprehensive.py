"""
Beads Commands Comprehensive Unit Tests
========================================

Tests for e2b_template/beads_commands.py actions:
- action_list - Stats calculation, empty project, malformed JSONL
- action_get - Single feature, not found, list vs dict response
- action_create - All fields, auto-init, name required, priority conversion
- action_update - Single/multiple fields, steps merge, category/priority labels
- action_delete - Success/failure, --force flag
- action_skip - Sets priority to P4, cannot skip passing feature
- action_reopen - Success, returns updated feature
- action_init - Initialize, already initialized
- handle_action - Dispatcher for all actions, unknown action error
- priority_to_beads - 0->P0, edge cases
- issue_to_feature - Full conversion, status mapping, steps extraction
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "e2b_template"))


class TestPriorityToBeads:
    """Tests for priority_to_beads conversion function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import priority_to_beads
        self.priority_to_beads = priority_to_beads

    @pytest.mark.unit
    def test_p0_conversion(self):
        """Test priority 0 converts to P0."""
        assert self.priority_to_beads(0) == "P0"

    @pytest.mark.unit
    def test_p1_conversion(self):
        """Test priority 1 converts to P1."""
        assert self.priority_to_beads(1) == "P1"

    @pytest.mark.unit
    def test_p2_conversion(self):
        """Test priority 2 converts to P2."""
        assert self.priority_to_beads(2) == "P2"

    @pytest.mark.unit
    def test_p3_conversion(self):
        """Test priority 3 converts to P3."""
        assert self.priority_to_beads(3) == "P3"

    @pytest.mark.unit
    def test_p4_conversion(self):
        """Test priority 4 converts to P4."""
        assert self.priority_to_beads(4) == "P4"

    @pytest.mark.unit
    def test_negative_priority(self):
        """Test negative priority converts to P0."""
        assert self.priority_to_beads(-1) == "P0"
        assert self.priority_to_beads(-100) == "P0"

    @pytest.mark.unit
    def test_high_priority(self):
        """Test priority > 4 converts to P4."""
        assert self.priority_to_beads(5) == "P4"
        assert self.priority_to_beads(100) == "P4"
        assert self.priority_to_beads(999) == "P4"
        assert self.priority_to_beads(9999) == "P4"


class TestBeadsToPriority:
    """Tests for beads_to_priority conversion function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import beads_to_priority
        self.beads_to_priority = beads_to_priority

    @pytest.mark.unit
    def test_integer_passthrough(self):
        """Test integer priorities pass through unchanged."""
        assert self.beads_to_priority(0) == 0
        assert self.beads_to_priority(1) == 1
        assert self.beads_to_priority(4) == 4

    @pytest.mark.unit
    def test_string_numeric(self):
        """Test numeric string conversion."""
        assert self.beads_to_priority("0") == 0
        assert self.beads_to_priority("1") == 1
        assert self.beads_to_priority("4") == 4

    @pytest.mark.unit
    def test_p_notation(self):
        """Test P0-P4 notation."""
        assert self.beads_to_priority("P0") == 0
        assert self.beads_to_priority("P1") == 1
        assert self.beads_to_priority("P2") == 2
        assert self.beads_to_priority("P3") == 3
        assert self.beads_to_priority("P4") == 4

    @pytest.mark.unit
    def test_lowercase_p_notation(self):
        """Test lowercase p notation."""
        assert self.beads_to_priority("p0") == 0
        assert self.beads_to_priority("p1") == 1

    @pytest.mark.unit
    def test_unknown_defaults_to_4(self):
        """Test unknown values default to 4."""
        assert self.beads_to_priority("unknown") == 4
        assert self.beads_to_priority("high") == 4
        assert self.beads_to_priority("") == 4


class TestExtractLabelValue:
    """Tests for extract_label_value function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import extract_label_value
        self.extract_label_value = extract_label_value

    @pytest.mark.unit
    def test_extracts_category(self):
        """Test extracting category from labels."""
        labels = ["category:auth", "type:feature"]
        assert self.extract_label_value(labels, "category") == "auth"

    @pytest.mark.unit
    def test_extracts_priority(self):
        """Test extracting priority from labels."""
        labels = ["priority:1", "category:ui"]
        assert self.extract_label_value(labels, "priority") == "1"

    @pytest.mark.unit
    def test_returns_none_when_not_found(self):
        """Test returning None when label not found."""
        labels = ["category:auth"]
        assert self.extract_label_value(labels, "priority") is None

    @pytest.mark.unit
    def test_handles_empty_labels(self):
        """Test handling empty labels list."""
        assert self.extract_label_value([], "category") is None


class TestParseStepsFromDescription:
    """Tests for parse_steps_from_description function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import parse_steps_from_description
        self.parse_steps_from_description = parse_steps_from_description

    @pytest.mark.unit
    def test_extracts_unchecked_steps(self):
        """Test extracting unchecked steps."""
        description = """Some intro text

## Steps
- [ ] First step
- [ ] Second step
"""
        base, steps = self.parse_steps_from_description(description)

        assert "Some intro text" in base
        assert "First step" in steps
        assert "Second step" in steps

    @pytest.mark.unit
    def test_extracts_checked_steps(self):
        """Test extracting checked steps."""
        description = """## Steps
- [x] Completed
- [ ] Pending
"""
        base, steps = self.parse_steps_from_description(description)

        assert "Completed" in steps
        assert "Pending" in steps

    @pytest.mark.unit
    def test_no_steps_section(self):
        """Test description without steps section."""
        description = "Just a plain description."
        base, steps = self.parse_steps_from_description(description)

        assert base == description
        assert steps == []


class TestStepsToDescription:
    """Tests for steps_to_description function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import steps_to_description
        self.steps_to_description = steps_to_description

    @pytest.mark.unit
    def test_appends_steps_checklist(self):
        """Test appending steps as checklist."""
        description = "Base description"
        steps = ["Step 1", "Step 2"]

        result = self.steps_to_description(description, steps)

        assert "Base description" in result
        assert "## Steps" in result
        assert "- [ ] Step 1" in result
        assert "- [ ] Step 2" in result

    @pytest.mark.unit
    def test_empty_steps(self):
        """Test with empty steps list."""
        description = "Just description"
        result = self.steps_to_description(description, [])

        assert result == description
        assert "## Steps" not in result


class TestIssueToFeature:
    """Tests for issue_to_feature conversion function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import issue_to_feature
        self.issue_to_feature = issue_to_feature

    @pytest.mark.unit
    def test_basic_conversion(self):
        """Test basic issue to feature conversion."""
        issue = {
            "id": "feat-1",
            "title": "User Auth",
            "status": "open",
            "priority": "P1",
            "labels": ["category:auth"],
            "description": "Implement auth",
        }

        result = self.issue_to_feature(issue)

        assert result["id"] == "feat-1"
        assert result["name"] == "User Auth"
        assert result["status"] == "open"
        assert result["category"] == "auth"
        assert result["description"] == "Implement auth"

    @pytest.mark.unit
    def test_status_mapping_open(self):
        """Test open status maps to not passing, not in_progress."""
        issue = {"id": "feat-1", "status": "open"}
        result = self.issue_to_feature(issue)

        assert result["passes"] is False
        assert result["in_progress"] is False

    @pytest.mark.unit
    def test_status_mapping_in_progress(self):
        """Test in_progress status mapping."""
        issue = {"id": "feat-1", "status": "in_progress"}
        result = self.issue_to_feature(issue)

        assert result["passes"] is False
        assert result["in_progress"] is True

    @pytest.mark.unit
    def test_status_mapping_closed(self):
        """Test closed status maps to passes=True."""
        issue = {"id": "feat-1", "status": "closed"}
        result = self.issue_to_feature(issue)

        assert result["passes"] is True
        assert result["in_progress"] is False

    @pytest.mark.unit
    def test_extracts_steps_from_description(self):
        """Test steps extraction from description."""
        issue = {
            "id": "feat-1",
            "description": "Intro\n\n## Steps\n- [ ] Step 1\n- [x] Step 2",
        }
        result = self.issue_to_feature(issue)

        assert "Step 1" in result["steps"]
        assert "Step 2" in result["steps"]

    @pytest.mark.unit
    def test_priority_from_label(self):
        """Test priority extraction from labels."""
        issue = {
            "id": "feat-1",
            "labels": ["priority:2"],
            "priority": "P4",  # Label should override
        }
        result = self.issue_to_feature(issue)

        assert result["priority"] == 2

    @pytest.mark.unit
    def test_priority_from_beads(self):
        """Test priority from beads P-notation when no label."""
        issue = {
            "id": "feat-1",
            "labels": [],
            "priority": "P1",
        }
        result = self.issue_to_feature(issue)

        assert result["priority"] == 1

    @pytest.mark.unit
    def test_handles_missing_fields(self):
        """Test handling issues with missing fields."""
        issue = {"id": "feat-1"}
        result = self.issue_to_feature(issue)

        assert result["id"] == "feat-1"
        assert result["name"] == ""
        assert result["category"] == ""
        assert result["description"] == ""
        assert result["steps"] == []


class TestActionList:
    """Tests for action_list function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import action_list
        self.action_list = action_list

    @pytest.mark.unit
    def test_empty_project(self, tmp_path):
        """Test listing features in empty project."""
        beads_dir = tmp_path / ".beads"
        beads_dir.mkdir()

        with patch("beads_commands.BEADS_DIR", beads_dir):
            result = self.action_list()

        assert result["success"] is True
        assert result["features"] == []
        assert result["stats"]["total"] == 0
        assert result["stats"]["percentage"] == 0.0

    @pytest.mark.unit
    def test_calculates_stats_correctly(self, tmp_path):
        """Test stats calculation."""
        beads_dir = tmp_path / ".beads"
        beads_dir.mkdir()
        issues_file = beads_dir / "issues.jsonl"

        issues = [
            {"id": "feat-1", "title": "Open", "status": "open"},
            {"id": "feat-2", "title": "WIP", "status": "in_progress"},
            {"id": "feat-3", "title": "Done", "status": "closed"},
            {"id": "feat-4", "title": "Also Done", "status": "closed"},
        ]
        issues_file.write_text("\n".join(json.dumps(i) for i in issues))

        with patch("beads_commands.BEADS_DIR", beads_dir):
            result = self.action_list()

        assert result["stats"]["pending"] == 1
        assert result["stats"]["in_progress"] == 1
        assert result["stats"]["done"] == 2
        assert result["stats"]["total"] == 4
        assert result["stats"]["percentage"] == 50.0

    @pytest.mark.unit
    def test_handles_malformed_jsonl(self, tmp_path):
        """Test handling malformed JSONL lines."""
        beads_dir = tmp_path / ".beads"
        beads_dir.mkdir()
        issues_file = beads_dir / "issues.jsonl"

        content = '{"id": "feat-1", "status": "open"}\ninvalid json\n{"id": "feat-2", "status": "closed"}'
        issues_file.write_text(content)

        with patch("beads_commands.BEADS_DIR", beads_dir):
            result = self.action_list()

        # Should skip invalid line
        assert len(result["features"]) == 2

    @pytest.mark.unit
    def test_missing_issues_file(self, tmp_path):
        """Test when issues.jsonl doesn't exist."""
        beads_dir = tmp_path / ".beads"
        beads_dir.mkdir()
        # Don't create issues.jsonl

        with patch("beads_commands.BEADS_DIR", beads_dir):
            result = self.action_list()

        assert result["success"] is True
        assert result["features"] == []


class TestActionGet:
    """Tests for action_get function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import action_get
        self.action_get = action_get

    @pytest.mark.unit
    def test_get_single_feature(self):
        """Test getting a single feature."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([{
            "id": "feat-1",
            "title": "Test Feature",
            "status": "open",
        }])

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.return_value = mock_result
            result = self.action_get("feat-1")

        assert result["success"] is True
        assert result["feature"]["id"] == "feat-1"

    @pytest.mark.unit
    def test_feature_not_found(self):
        """Test getting non-existent feature."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Issue not found"

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.return_value = mock_result
            result = self.action_get("nonexistent")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.unit
    def test_handles_dict_response(self):
        """Test handling dict response instead of list."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({
            "id": "feat-1",
            "title": "Test",
            "status": "closed",
        })

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.return_value = mock_result
            result = self.action_get("feat-1")

        assert result["success"] is True
        assert result["feature"]["id"] == "feat-1"

    @pytest.mark.unit
    def test_empty_response(self):
        """Test handling empty response."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "[]"

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.return_value = mock_result
            result = self.action_get("feat-1")

        assert result["success"] is False
        assert "not found" in result["error"].lower()


class TestActionCreate:
    """Tests for action_create function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import action_create
        self.action_create = action_create

    @pytest.mark.unit
    def test_name_required(self, tmp_path):
        """Test that name is required."""
        # Mock beads as initialized to skip init_beads() call
        beads_dir = tmp_path / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat")

        with patch("beads_commands.BEADS_DIR", beads_dir):
            result = self.action_create({"description": "No name"})

        assert result["success"] is False
        assert "required" in result["error"].lower()

    @pytest.mark.unit
    def test_creates_with_all_fields(self, tmp_path):
        """Test creating feature with all fields."""
        beads_dir = tmp_path / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat")

        mock_create_result = MagicMock()
        mock_create_result.returncode = 0
        mock_create_result.stdout = json.dumps({"id": "feat-1"})

        mock_get_result = MagicMock()
        mock_get_result.returncode = 0
        mock_get_result.stdout = json.dumps([{
            "id": "feat-1",
            "title": "New Feature",
            "status": "open",
        }])

        with patch("beads_commands.BEADS_DIR", beads_dir):
            with patch("beads_commands.run_bd") as mock_run:
                mock_run.side_effect = [mock_create_result, mock_get_result]

                result = self.action_create({
                    "name": "New Feature",
                    "description": "Description",
                    "category": "auth",
                    "steps": ["Step 1", "Step 2"],
                    "priority": 1,
                })

        assert result["success"] is True

    @pytest.mark.unit
    def test_auto_init_if_not_initialized(self, tmp_path):
        """Test auto-initialization if beads not initialized."""
        beads_dir = tmp_path / ".beads"
        # Don't create beads_dir - simulate uninitialized

        mock_init_result = MagicMock()
        mock_init_result.returncode = 0

        mock_create_result = MagicMock()
        mock_create_result.returncode = 0
        mock_create_result.stdout = json.dumps({"id": "feat-1"})

        mock_get_result = MagicMock()
        mock_get_result.returncode = 0
        mock_get_result.stdout = json.dumps([{"id": "feat-1", "title": "Test"}])

        with patch("beads_commands.BEADS_DIR", beads_dir):
            with patch("beads_commands.run_bd") as mock_run:
                mock_run.side_effect = [mock_init_result, mock_create_result, mock_get_result]

                result = self.action_create({"name": "Test"})

        # Should have called init first
        mock_run.assert_any_call(["init", "--prefix", "feat"])

    @pytest.mark.unit
    def test_priority_conversion(self, tmp_path):
        """Test priority is converted to beads P-notation."""
        beads_dir = tmp_path / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat")

        mock_create_result = MagicMock()
        mock_create_result.returncode = 0
        mock_create_result.stdout = json.dumps({"id": "feat-1"})

        mock_get_result = MagicMock()
        mock_get_result.returncode = 0
        mock_get_result.stdout = json.dumps([{"id": "feat-1", "title": "Test"}])

        with patch("beads_commands.BEADS_DIR", beads_dir):
            with patch("beads_commands.run_bd") as mock_run:
                mock_run.side_effect = [mock_create_result, mock_get_result]

                self.action_create({"name": "Test", "priority": 0})

        # Check that P0 was passed
        create_call = mock_run.call_args_list[0]
        assert "--priority" in create_call[0][0]
        assert "P0" in create_call[0][0]


class TestActionUpdate:
    """Tests for action_update function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import action_update
        self.action_update = action_update

    @pytest.mark.unit
    def test_update_single_field(self):
        """Test updating a single field."""
        mock_get_result = MagicMock()
        mock_get_result.returncode = 0
        mock_get_result.stdout = json.dumps([{
            "id": "feat-1",
            "title": "Original",
            "status": "open",
            "labels": [],
        }])

        mock_update_result = MagicMock()
        mock_update_result.returncode = 0

        mock_get_updated = MagicMock()
        mock_get_updated.returncode = 0
        mock_get_updated.stdout = json.dumps([{
            "id": "feat-1",
            "title": "Updated",
            "status": "open",
        }])

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.side_effect = [mock_get_result, mock_update_result, mock_get_updated]

            result = self.action_update("feat-1", {"name": "Updated"})

        assert result["success"] is True

    @pytest.mark.unit
    def test_update_multiple_fields(self):
        """Test updating multiple fields."""
        mock_get_result = MagicMock()
        mock_get_result.returncode = 0
        mock_get_result.stdout = json.dumps([{
            "id": "feat-1",
            "title": "Original",
            "status": "open",
            "labels": ["category:old", "priority:2"],
            "priority": 2,
        }])

        mock_update_result = MagicMock()
        mock_update_result.returncode = 0

        mock_label_remove = MagicMock()
        mock_label_remove.returncode = 0

        mock_label_add = MagicMock()
        mock_label_add.returncode = 0

        mock_get_updated = MagicMock()
        mock_get_updated.returncode = 0
        mock_get_updated.stdout = json.dumps([{"id": "feat-1", "title": "Updated"}])

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.side_effect = [
                mock_get_result,
                mock_update_result,
                mock_label_remove, mock_label_add,  # category label ops
                mock_label_remove, mock_label_add,  # priority label ops
                mock_get_updated,
            ]

            result = self.action_update("feat-1", {
                "name": "Updated",
                "category": "new",
                "priority": 0,
            })

        assert result["success"] is True

    @pytest.mark.unit
    def test_update_nonexistent_feature(self):
        """Test updating non-existent feature."""
        mock_get_result = MagicMock()
        mock_get_result.returncode = 1
        mock_get_result.stderr = "Not found"

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.return_value = mock_get_result

            result = self.action_update("nonexistent", {"name": "Test"})

        assert result["success"] is False


class TestActionDelete:
    """Tests for action_delete function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import action_delete
        self.action_delete = action_delete

    @pytest.mark.unit
    def test_successful_delete(self):
        """Test successful feature deletion."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.return_value = mock_result

            result = self.action_delete("feat-1")

        assert result["success"] is True
        assert "deleted" in result["message"].lower()

    @pytest.mark.unit
    def test_delete_uses_force(self):
        """Test delete uses --force flag."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.return_value = mock_result

            self.action_delete("feat-1")

        mock_run.assert_called_with(["delete", "feat-1", "--force"])

    @pytest.mark.unit
    def test_delete_failure(self):
        """Test delete failure."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Delete failed"

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.return_value = mock_result

            result = self.action_delete("feat-1")

        assert result["success"] is False


class TestActionSkip:
    """Tests for action_skip function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import action_skip
        self.action_skip = action_skip

    @pytest.mark.unit
    def test_skip_sets_priority_to_p4(self):
        """Test skip sets priority to P4."""
        mock_get_result = MagicMock()
        mock_get_result.returncode = 0
        mock_get_result.stdout = json.dumps([{
            "id": "feat-1",
            "title": "Test",
            "status": "open",
            "priority": 1,
            "labels": [],
        }])

        mock_update_result = MagicMock()
        mock_update_result.returncode = 0

        mock_label_ops = MagicMock()
        mock_label_ops.returncode = 0

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.side_effect = [
                mock_get_result,
                mock_update_result,
                mock_label_ops, mock_label_ops,  # label operations
            ]

            result = self.action_skip("feat-1")

        assert result["success"] is True
        assert "moved to end" in result["message"].lower()

    @pytest.mark.unit
    def test_cannot_skip_passing_feature(self):
        """Test cannot skip a feature that is already passing."""
        mock_get_result = MagicMock()
        mock_get_result.returncode = 0
        mock_get_result.stdout = json.dumps([{
            "id": "feat-1",
            "title": "Done",
            "status": "closed",
        }])

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.return_value = mock_get_result

            result = self.action_skip("feat-1")

        assert result["success"] is False
        assert "cannot skip" in result["error"].lower()


class TestActionReopen:
    """Tests for action_reopen function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import action_reopen
        self.action_reopen = action_reopen

    @pytest.mark.unit
    def test_successful_reopen(self):
        """Test successful feature reopen."""
        mock_reopen_result = MagicMock()
        mock_reopen_result.returncode = 0

        mock_get_result = MagicMock()
        mock_get_result.returncode = 0
        mock_get_result.stdout = json.dumps([{
            "id": "feat-1",
            "title": "Reopened",
            "status": "open",
        }])

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.side_effect = [mock_reopen_result, mock_get_result]

            result = self.action_reopen("feat-1")

        assert result["success"] is True
        assert result["feature"]["status"] == "open"

    @pytest.mark.unit
    def test_reopen_failure(self):
        """Test reopen failure."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Cannot reopen"

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.return_value = mock_result

            result = self.action_reopen("feat-1")

        assert result["success"] is False


class TestActionInit:
    """Tests for action_init function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import action_init
        self.action_init = action_init

    @pytest.mark.unit
    def test_init_when_not_initialized(self, tmp_path):
        """Test initialization when not already initialized."""
        beads_dir = tmp_path / ".beads"
        # Don't create beads_dir

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("beads_commands.BEADS_DIR", beads_dir):
            with patch("beads_commands.run_bd") as mock_run:
                mock_run.return_value = mock_result

                result = self.action_init()

        assert result["success"] is True
        assert "initialized" in result["message"].lower()

    @pytest.mark.unit
    def test_already_initialized(self, tmp_path):
        """Test when already initialized."""
        beads_dir = tmp_path / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat")

        with patch("beads_commands.BEADS_DIR", beads_dir):
            result = self.action_init()

        assert result["success"] is True
        assert "already" in result["message"].lower()


class TestHandleAction:
    """Tests for handle_action dispatcher function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import handle_action
        self.handle_action = handle_action

    @pytest.mark.unit
    def test_dispatches_list(self, tmp_path):
        """Test dispatching list action."""
        beads_dir = tmp_path / ".beads"
        beads_dir.mkdir()

        with patch("beads_commands.BEADS_DIR", beads_dir):
            result = self.handle_action({"action": "list"})

        assert result["success"] is True

    @pytest.mark.unit
    def test_dispatches_get(self):
        """Test dispatching get action."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps([{"id": "feat-1", "title": "Test"}])

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.return_value = mock_result

            result = self.handle_action({"action": "get", "feature_id": "feat-1"})

        assert result["success"] is True

    @pytest.mark.unit
    def test_get_requires_feature_id(self):
        """Test get action requires feature_id."""
        result = self.handle_action({"action": "get"})

        assert result["success"] is False
        assert "required" in result["error"].lower()

    @pytest.mark.unit
    def test_dispatches_create(self, tmp_path):
        """Test dispatching create action."""
        beads_dir = tmp_path / ".beads"
        beads_dir.mkdir()
        (beads_dir / "config.yaml").write_text("prefix: feat")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"id": "feat-1"})

        mock_get = MagicMock()
        mock_get.returncode = 0
        mock_get.stdout = json.dumps([{"id": "feat-1", "title": "New"}])

        with patch("beads_commands.BEADS_DIR", beads_dir):
            with patch("beads_commands.run_bd") as mock_run:
                mock_run.side_effect = [mock_result, mock_get]

                result = self.handle_action({
                    "action": "create",
                    "data": {"name": "New Feature"},
                })

        assert result["success"] is True

    @pytest.mark.unit
    def test_dispatches_update(self):
        """Test dispatching update action."""
        mock_get = MagicMock()
        mock_get.returncode = 0
        mock_get.stdout = json.dumps([{"id": "feat-1", "title": "Test", "labels": []}])

        mock_update = MagicMock()
        mock_update.returncode = 0

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.side_effect = [mock_get, mock_update, mock_get]

            result = self.handle_action({
                "action": "update",
                "feature_id": "feat-1",
                "data": {"name": "Updated"},
            })

        assert result["success"] is True

    @pytest.mark.unit
    def test_update_requires_feature_id(self):
        """Test update action requires feature_id."""
        result = self.handle_action({
            "action": "update",
            "data": {"name": "Test"},
        })

        assert result["success"] is False
        assert "required" in result["error"].lower()

    @pytest.mark.unit
    def test_dispatches_delete(self):
        """Test dispatching delete action."""
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.return_value = mock_result

            result = self.handle_action({
                "action": "delete",
                "feature_id": "feat-1",
            })

        assert result["success"] is True

    @pytest.mark.unit
    def test_delete_requires_feature_id(self):
        """Test delete action requires feature_id."""
        result = self.handle_action({"action": "delete"})

        assert result["success"] is False
        assert "required" in result["error"].lower()

    @pytest.mark.unit
    def test_dispatches_skip(self):
        """Test dispatching skip action."""
        mock_get = MagicMock()
        mock_get.returncode = 0
        mock_get.stdout = json.dumps([{
            "id": "feat-1",
            "title": "Test",
            "status": "open",
            "labels": [],
        }])

        mock_update = MagicMock()
        mock_update.returncode = 0

        mock_label = MagicMock()
        mock_label.returncode = 0

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.side_effect = [mock_get, mock_update, mock_label, mock_label]

            result = self.handle_action({
                "action": "skip",
                "feature_id": "feat-1",
            })

        assert result["success"] is True

    @pytest.mark.unit
    def test_skip_requires_feature_id(self):
        """Test skip action requires feature_id."""
        result = self.handle_action({"action": "skip"})

        assert result["success"] is False
        assert "required" in result["error"].lower()

    @pytest.mark.unit
    def test_dispatches_reopen(self):
        """Test dispatching reopen action."""
        mock_reopen = MagicMock()
        mock_reopen.returncode = 0

        mock_get = MagicMock()
        mock_get.returncode = 0
        mock_get.stdout = json.dumps([{"id": "feat-1", "status": "open"}])

        with patch("beads_commands.run_bd") as mock_run:
            mock_run.side_effect = [mock_reopen, mock_get]

            result = self.handle_action({
                "action": "reopen",
                "feature_id": "feat-1",
            })

        assert result["success"] is True

    @pytest.mark.unit
    def test_reopen_requires_feature_id(self):
        """Test reopen action requires feature_id."""
        result = self.handle_action({"action": "reopen"})

        assert result["success"] is False
        assert "required" in result["error"].lower()

    @pytest.mark.unit
    def test_dispatches_init(self, tmp_path):
        """Test dispatching init action."""
        beads_dir = tmp_path / ".beads"

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("beads_commands.BEADS_DIR", beads_dir):
            with patch("beads_commands.run_bd") as mock_run:
                mock_run.return_value = mock_result

                result = self.handle_action({"action": "init"})

        assert result["success"] is True

    @pytest.mark.unit
    def test_unknown_action(self):
        """Test handling unknown action."""
        result = self.handle_action({"action": "unknown"})

        assert result["success"] is False
        assert "unknown" in result["error"].lower()

    @pytest.mark.unit
    def test_empty_action(self):
        """Test handling empty action."""
        result = self.handle_action({})

        assert result["success"] is False
        assert "unknown" in result["error"].lower()


class TestRunBd:
    """Tests for run_bd helper function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import run_bd
        self.run_bd = run_bd

    @pytest.mark.unit
    def test_runs_bd_with_args(self, tmp_path):
        """Test run_bd executes bd with arguments."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            with patch("beads_commands.PROJECT_DIR", tmp_path):
                self.run_bd(["list", "--json"])

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["bd", "list", "--json"]

    @pytest.mark.unit
    def test_runs_in_project_dir(self, tmp_path):
        """Test run_bd runs in project directory."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            with patch("beads_commands.PROJECT_DIR", tmp_path):
                self.run_bd(["status"])

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["cwd"] == tmp_path


class TestParseJsonOutput:
    """Tests for parse_json_output helper function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Import function after path setup."""
        from beads_commands import parse_json_output
        self.parse_json_output = parse_json_output

    @pytest.mark.unit
    def test_parses_valid_json_list(self):
        """Test parsing valid JSON list output."""
        result = MagicMock()
        result.stdout = '[{"id": "feat-1"}, {"id": "feat-2"}]'
        result.stderr = ""

        data, error = self.parse_json_output(result)

        assert error is None
        assert len(data) == 2

    @pytest.mark.unit
    def test_parses_valid_json_dict(self):
        """Test parsing valid JSON dict output."""
        result = MagicMock()
        result.stdout = '{"id": "feat-1", "title": "Test"}'
        result.stderr = ""

        data, error = self.parse_json_output(result)

        assert error is None
        assert data["id"] == "feat-1"

    @pytest.mark.unit
    def test_handles_json_parse_error(self):
        """Test handling JSON parse errors."""
        result = MagicMock()
        result.stdout = "not valid json"
        result.stderr = ""

        data, error = self.parse_json_output(result)

        assert error is not None
        assert "parse error" in error.lower()
        assert data == []
