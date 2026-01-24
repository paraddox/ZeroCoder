"""
Beads API Models Unit Tests
============================

Tests for Pydantic request/response models in beads_api.py:
- IssueCreate model validation
- IssueUpdate model validation
- IssueClose model validation
- CommentAdd model validation
"""

import pytest
from pydantic import ValidationError
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.routers.beads_api import IssueCreate, IssueUpdate, IssueClose, CommentAdd


class TestIssueCreateModel:
    """Tests for IssueCreate Pydantic model."""

    @pytest.mark.unit
    def test_valid_minimal_issue(self):
        """Test creating issue with only required fields."""
        issue = IssueCreate(title="Test Issue")

        assert issue.title == "Test Issue"
        assert issue.description == ""
        assert issue.type == "task"
        assert issue.priority == 2
        assert issue.labels == []

    @pytest.mark.unit
    def test_valid_full_issue(self):
        """Test creating issue with all fields."""
        issue = IssueCreate(
            title="Full Issue",
            description="Detailed description",
            type="feature",
            priority=0,
            labels=["auth", "critical"],
        )

        assert issue.title == "Full Issue"
        assert issue.description == "Detailed description"
        assert issue.type == "feature"
        assert issue.priority == 0
        assert issue.labels == ["auth", "critical"]

    @pytest.mark.unit
    def test_title_required(self):
        """Test that title field is required."""
        with pytest.raises(ValidationError) as exc_info:
            IssueCreate()

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("title",) for e in errors)

    @pytest.mark.unit
    def test_title_min_length(self):
        """Test title minimum length validation."""
        with pytest.raises(ValidationError) as exc_info:
            IssueCreate(title="")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("title",) and "min_length" in str(e) for e in errors)

    @pytest.mark.unit
    def test_title_max_length(self):
        """Test title maximum length validation (200 chars)."""
        long_title = "x" * 201
        with pytest.raises(ValidationError) as exc_info:
            IssueCreate(title=long_title)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("title",) and "max_length" in str(e) for e in errors)

    @pytest.mark.unit
    def test_title_at_max_length(self):
        """Test title at exactly max length is valid."""
        max_title = "x" * 200
        issue = IssueCreate(title=max_title)
        assert len(issue.title) == 200

    @pytest.mark.unit
    def test_priority_range_p0(self):
        """Test priority P0 (0) is valid."""
        issue = IssueCreate(title="P0 Issue", priority=0)
        assert issue.priority == 0

    @pytest.mark.unit
    def test_priority_range_p4(self):
        """Test priority P4 (4) is valid."""
        issue = IssueCreate(title="P4 Issue", priority=4)
        assert issue.priority == 4

    @pytest.mark.unit
    def test_priority_below_range(self):
        """Test priority below 0 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            IssueCreate(title="Invalid", priority=-1)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("priority",) for e in errors)

    @pytest.mark.unit
    def test_priority_above_range(self):
        """Test priority above 4 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            IssueCreate(title="Invalid", priority=5)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("priority",) for e in errors)

    @pytest.mark.unit
    def test_valid_types(self):
        """Test various valid issue types."""
        for issue_type in ["task", "bug", "feature", "epic"]:
            issue = IssueCreate(title="Test", type=issue_type)
            assert issue.type == issue_type

    @pytest.mark.unit
    def test_labels_list(self):
        """Test labels as a list."""
        issue = IssueCreate(title="Test", labels=["label1", "label2", "label3"])
        assert issue.labels == ["label1", "label2", "label3"]

    @pytest.mark.unit
    def test_empty_labels(self):
        """Test empty labels list."""
        issue = IssueCreate(title="Test", labels=[])
        assert issue.labels == []

    @pytest.mark.unit
    def test_description_optional(self):
        """Test description is optional and defaults to empty string."""
        issue = IssueCreate(title="Test")
        assert issue.description == ""

    @pytest.mark.unit
    def test_multiline_description(self):
        """Test multiline description."""
        desc = "Line 1\nLine 2\n\n## Steps\n- [ ] Step 1"
        issue = IssueCreate(title="Test", description=desc)
        assert issue.description == desc


class TestIssueUpdateModel:
    """Tests for IssueUpdate Pydantic model."""

    @pytest.mark.unit
    def test_all_fields_optional(self):
        """Test that all fields are optional."""
        update = IssueUpdate()

        assert update.title is None
        assert update.description is None
        assert update.status is None
        assert update.priority is None
        assert update.assignee is None

    @pytest.mark.unit
    def test_update_single_field_title(self):
        """Test updating only title."""
        update = IssueUpdate(title="New Title")

        assert update.title == "New Title"
        assert update.description is None
        assert update.status is None

    @pytest.mark.unit
    def test_update_single_field_status(self):
        """Test updating only status."""
        update = IssueUpdate(status="in_progress")

        assert update.status == "in_progress"
        assert update.title is None

    @pytest.mark.unit
    def test_update_multiple_fields(self):
        """Test updating multiple fields at once."""
        update = IssueUpdate(
            title="Updated",
            status="closed",
            priority=0,
        )

        assert update.title == "Updated"
        assert update.status == "closed"
        assert update.priority == 0
        assert update.description is None

    @pytest.mark.unit
    def test_priority_range_valid(self):
        """Test priority within valid range."""
        for priority in [0, 1, 2, 3, 4]:
            update = IssueUpdate(priority=priority)
            assert update.priority == priority

    @pytest.mark.unit
    def test_priority_below_range(self):
        """Test priority below 0 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            IssueUpdate(priority=-1)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("priority",) for e in errors)

    @pytest.mark.unit
    def test_priority_above_range(self):
        """Test priority above 4 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            IssueUpdate(priority=5)

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("priority",) for e in errors)

    @pytest.mark.unit
    def test_valid_status_values(self):
        """Test various status values (no validation enforced)."""
        for status in ["open", "in_progress", "closed"]:
            update = IssueUpdate(status=status)
            assert update.status == status

    @pytest.mark.unit
    def test_assignee_field(self):
        """Test assignee field."""
        update = IssueUpdate(assignee="user@example.com")
        assert update.assignee == "user@example.com"

    @pytest.mark.unit
    def test_empty_assignee(self):
        """Test empty assignee to unassign."""
        update = IssueUpdate(assignee="")
        assert update.assignee == ""


class TestIssueCloseModel:
    """Tests for IssueClose Pydantic model."""

    @pytest.mark.unit
    def test_empty_close(self):
        """Test closing without reason."""
        close = IssueClose()
        assert close.reason is None

    @pytest.mark.unit
    def test_close_with_reason(self):
        """Test closing with reason."""
        close = IssueClose(reason="Fixed in commit abc123")
        assert close.reason == "Fixed in commit abc123"

    @pytest.mark.unit
    def test_close_with_empty_reason(self):
        """Test closing with empty reason string."""
        close = IssueClose(reason="")
        assert close.reason == ""

    @pytest.mark.unit
    def test_close_with_multiline_reason(self):
        """Test closing with multiline reason."""
        reason = "Fixed in commit abc123\n\nDetails:\n- Fixed bug A\n- Fixed bug B"
        close = IssueClose(reason=reason)
        assert close.reason == reason


class TestCommentAddModel:
    """Tests for CommentAdd Pydantic model."""

    @pytest.mark.unit
    def test_valid_comment(self):
        """Test valid comment."""
        comment = CommentAdd(comment="This is a comment")
        assert comment.comment == "This is a comment"

    @pytest.mark.unit
    def test_comment_required(self):
        """Test that comment field is required."""
        with pytest.raises(ValidationError) as exc_info:
            CommentAdd()

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("comment",) for e in errors)

    @pytest.mark.unit
    def test_comment_min_length(self):
        """Test comment minimum length (1 char)."""
        with pytest.raises(ValidationError) as exc_info:
            CommentAdd(comment="")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("comment",) and "min_length" in str(e) for e in errors)

    @pytest.mark.unit
    def test_comment_single_char(self):
        """Test single character comment is valid."""
        comment = CommentAdd(comment="x")
        assert comment.comment == "x"

    @pytest.mark.unit
    def test_multiline_comment(self):
        """Test multiline comment."""
        text = "Line 1\nLine 2\nLine 3"
        comment = CommentAdd(comment=text)
        assert comment.comment == text

    @pytest.mark.unit
    def test_comment_with_special_chars(self):
        """Test comment with special characters."""
        text = "Comment with special chars: @mention #tag `code` **bold**"
        comment = CommentAdd(comment=text)
        assert comment.comment == text

    @pytest.mark.unit
    def test_comment_with_unicode(self):
        """Test comment with unicode characters."""
        text = "Comment with unicode: emoji test unicode chars"
        comment = CommentAdd(comment=text)
        assert comment.comment == text


class TestModelSerialization:
    """Tests for model JSON serialization."""

    @pytest.mark.unit
    def test_issue_create_to_dict(self):
        """Test IssueCreate model to dict conversion."""
        issue = IssueCreate(
            title="Test",
            description="Desc",
            type="task",
            priority=1,
            labels=["label1"],
        )

        data = issue.model_dump()

        assert data["title"] == "Test"
        assert data["description"] == "Desc"
        assert data["type"] == "task"
        assert data["priority"] == 1
        assert data["labels"] == ["label1"]

    @pytest.mark.unit
    def test_issue_update_to_dict_excludes_none(self):
        """Test IssueUpdate model excludes None values when serializing."""
        update = IssueUpdate(title="New Title")

        data = update.model_dump(exclude_none=True)

        assert data == {"title": "New Title"}
        assert "description" not in data
        assert "status" not in data

    @pytest.mark.unit
    def test_issue_create_from_dict(self):
        """Test creating IssueCreate from dict."""
        data = {
            "title": "From Dict",
            "priority": 0,
        }

        issue = IssueCreate(**data)

        assert issue.title == "From Dict"
        assert issue.priority == 0
        assert issue.description == ""  # Default

    @pytest.mark.unit
    def test_issue_update_from_dict_partial(self):
        """Test creating IssueUpdate from partial dict."""
        data = {"status": "closed"}

        update = IssueUpdate(**data)

        assert update.status == "closed"
        assert update.title is None
