"""
API Contract Tests
==================

Enterprise-grade tests for API request/response validation including:
- Schema validation edge cases
- Request/response contract compliance
- Error response formats
- Input sanitization and validation
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from server.schemas import (
    ProjectCreate,
    ProjectSummary,
    ProjectDetail,
    ProjectSettingsUpdate,
    ProjectPrompts,
    FeatureCreate,
    FeatureUpdate,
    FeatureResponse,
    AgentStartRequest,
    AgentStatus,
    ContainerCountUpdate,
    WizardStatus,
    WizardStatusMessage,
    ImageAttachment,
    TextAttachment,
    TaskCreate,
    TaskUpdate,
)


# =============================================================================
# Project Schema Contract Tests
# =============================================================================

class TestProjectCreateContract:
    """Tests for ProjectCreate schema validation."""

    @pytest.mark.unit
    def test_valid_project_create_minimal(self):
        """Test minimal valid project creation."""
        data = ProjectCreate(
            name="my-project",
            git_url="https://github.com/user/repo.git"
        )
        assert data.name == "my-project"
        assert data.is_new is True  # default
        assert data.spec_method == "claude"  # default

    @pytest.mark.unit
    def test_valid_project_create_full(self):
        """Test full valid project creation with all fields."""
        data = ProjectCreate(
            name="test-app-123",
            git_url="git@github.com:org/repo.git",
            is_new=False,
            spec_method="manual"
        )
        assert data.name == "test-app-123"
        assert data.git_url == "git@github.com:org/repo.git"
        assert data.is_new is False
        assert data.spec_method == "manual"

    @pytest.mark.unit
    def test_project_name_validation_too_short(self):
        """Test that empty project names are rejected."""
        with pytest.raises(ValueError):
            ProjectCreate(name="", git_url="https://github.com/user/repo.git")

    @pytest.mark.unit
    def test_project_name_validation_too_long(self):
        """Test that project names over 50 chars are rejected."""
        with pytest.raises(ValueError):
            ProjectCreate(
                name="a" * 51,
                git_url="https://github.com/user/repo.git"
            )

    @pytest.mark.unit
    def test_project_name_validation_invalid_chars(self):
        """Test that invalid characters in names are rejected."""
        invalid_names = [
            "project with spaces",
            "project/slash",
            "project.dot",
            "project@at",
            "../path-traversal",
            "project!bang",
            "project#hash",
        ]
        for name in invalid_names:
            with pytest.raises(ValueError, match="pattern"):
                ProjectCreate(name=name, git_url="https://github.com/user/repo.git")

    @pytest.mark.unit
    def test_project_name_valid_chars(self):
        """Test that valid character combinations are accepted."""
        valid_names = [
            "simple",
            "with-dashes",
            "with_underscores",
            "MixedCase123",
            "a",  # single char
            "a" * 50,  # max length
            "123-numeric-start",
        ]
        for name in valid_names:
            data = ProjectCreate(name=name, git_url="https://github.com/user/repo.git")
            assert data.name == name

    @pytest.mark.unit
    def test_git_url_validation_empty(self):
        """Test that empty git URLs are rejected."""
        with pytest.raises(ValueError):
            ProjectCreate(name="project", git_url="")

    @pytest.mark.unit
    def test_spec_method_validation(self):
        """Test that only valid spec methods are accepted."""
        # Valid values
        for method in ["claude", "manual"]:
            data = ProjectCreate(
                name="test",
                git_url="https://github.com/user/repo.git",
                spec_method=method
            )
            assert data.spec_method == method


class TestContainerCountUpdateContract:
    """Tests for ContainerCountUpdate schema validation."""

    @pytest.mark.unit
    def test_valid_container_counts(self):
        """Test valid container count values."""
        for count in [1, 5, 10]:
            data = ContainerCountUpdate(target_count=count)
            assert data.target_count == count

    @pytest.mark.unit
    def test_invalid_container_count_zero(self):
        """Test that zero is rejected."""
        with pytest.raises(ValueError):
            ContainerCountUpdate(target_count=0)

    @pytest.mark.unit
    def test_invalid_container_count_negative(self):
        """Test that negative values are rejected."""
        with pytest.raises(ValueError):
            ContainerCountUpdate(target_count=-1)

    @pytest.mark.unit
    def test_invalid_container_count_exceeds_max(self):
        """Test that values over 10 are rejected."""
        with pytest.raises(ValueError):
            ContainerCountUpdate(target_count=11)


# =============================================================================
# Feature Schema Contract Tests
# =============================================================================

class TestFeatureCreateContract:
    """Tests for FeatureCreate schema validation."""

    @pytest.mark.unit
    def test_valid_feature_create_minimal(self):
        """Test minimal valid feature creation."""
        data = FeatureCreate(
            category="auth",
            name="User Login",
            description="Login functionality",
            steps=["Create form", "Add validation"]
        )
        assert data.category == "auth"
        assert data.priority is None  # optional

    @pytest.mark.unit
    def test_valid_feature_create_with_priority(self):
        """Test feature creation with priority."""
        data = FeatureCreate(
            category="ui",
            name="Dashboard",
            description="Main dashboard",
            steps=["Layout", "Components"],
            priority=1
        )
        assert data.priority == 1

    @pytest.mark.unit
    def test_feature_empty_steps(self):
        """Test feature with empty steps list."""
        data = FeatureCreate(
            category="test",
            name="Test Feature",
            description="Description",
            steps=[]
        )
        assert data.steps == []


class TestFeatureUpdateContract:
    """Tests for FeatureUpdate schema validation."""

    @pytest.mark.unit
    def test_partial_update_name_only(self):
        """Test updating only the name."""
        data = FeatureUpdate(name="New Name")
        assert data.name == "New Name"
        assert data.description is None
        assert data.priority is None

    @pytest.mark.unit
    def test_partial_update_priority_only(self):
        """Test updating only the priority."""
        data = FeatureUpdate(priority=2)
        assert data.priority == 2
        assert data.name is None

    @pytest.mark.unit
    def test_full_update(self):
        """Test updating all fields."""
        data = FeatureUpdate(
            name="Updated",
            description="New desc",
            category="new-cat",
            priority=3,
            steps=["Step 1", "Step 2"]
        )
        assert data.name == "Updated"
        assert data.description == "New desc"
        assert data.category == "new-cat"
        assert data.priority == 3
        assert data.steps == ["Step 1", "Step 2"]


class TestFeatureResponseContract:
    """Tests for FeatureResponse schema."""

    @pytest.mark.unit
    def test_feature_response_creation(self):
        """Test creating a feature response."""
        data = FeatureResponse(
            id="feat-1",
            category="auth",
            name="Login",
            description="User login",
            steps=["Step 1"],
            priority=1,
            passes=False,
            in_progress=True
        )
        assert data.id == "feat-1"
        assert data.passes is False
        assert data.in_progress is True


# =============================================================================
# Agent Schema Contract Tests
# =============================================================================

class TestAgentStartRequestContract:
    """Tests for AgentStartRequest schema validation."""

    @pytest.mark.unit
    def test_minimal_start_request(self):
        """Test minimal agent start request."""
        data = AgentStartRequest()
        assert data.instruction is None
        assert data.yolo_mode is False

    @pytest.mark.unit
    def test_start_with_instruction(self):
        """Test start request with instruction."""
        data = AgentStartRequest(instruction="Implement feature X")
        assert data.instruction == "Implement feature X"

    @pytest.mark.unit
    def test_start_with_yolo_mode(self):
        """Test start request with yolo mode enabled."""
        data = AgentStartRequest(yolo_mode=True)
        assert data.yolo_mode is True


class TestAgentStatusContract:
    """Tests for AgentStatus schema."""

    @pytest.mark.unit
    def test_agent_status_not_created(self):
        """Test agent status when not created."""
        data = AgentStatus(status="not_created")
        assert data.status == "not_created"
        assert data.container_name is None
        assert data.started_at is None
        assert data.agent_running is False

    @pytest.mark.unit
    def test_agent_status_running(self):
        """Test agent status when running."""
        started = datetime.now()
        data = AgentStatus(
            status="running",
            container_name="zerocoder-test-1",
            started_at=started,
            idle_seconds=60,
            agent_running=True,
            agent_type="coder",
            sdk_type="claude"
        )
        assert data.status == "running"
        assert data.container_name == "zerocoder-test-1"
        assert data.started_at == started
        assert data.agent_type == "coder"
        assert data.sdk_type == "claude"


# =============================================================================
# Wizard Schema Contract Tests
# =============================================================================

class TestWizardStatusContract:
    """Tests for WizardStatus schema validation."""

    @pytest.mark.unit
    def test_wizard_status_initial(self):
        """Test initial wizard status."""
        data = WizardStatus(
            step="mode",
            started_at=datetime.now()
        )
        assert data.step == "mode"
        assert data.spec_method is None
        assert data.chat_messages == []

    @pytest.mark.unit
    def test_wizard_status_with_messages(self):
        """Test wizard status with chat messages."""
        msg = WizardStatusMessage(
            role="user",
            content="I want a todo app",
            timestamp=datetime.now()
        )
        data = WizardStatus(
            step="chat",
            spec_method="claude",
            started_at=datetime.now(),
            chat_messages=[msg]
        )
        assert len(data.chat_messages) == 1
        assert data.chat_messages[0].role == "user"

    @pytest.mark.unit
    def test_wizard_step_validation(self):
        """Test that only valid wizard steps are accepted."""
        valid_steps = ["mode", "details", "method", "chat"]
        for step in valid_steps:
            data = WizardStatus(step=step, started_at=datetime.now())
            assert data.step == step


# =============================================================================
# Attachment Schema Contract Tests
# =============================================================================

class TestImageAttachmentContract:
    """Tests for ImageAttachment schema validation."""

    @pytest.mark.unit
    def test_valid_image_attachment(self):
        """Test valid image attachment."""
        import base64
        # Small valid PNG bytes (1x1 transparent pixel)
        png_bytes = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
            0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,
            0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
            0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
            0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
            0x42, 0x60, 0x82
        ])
        b64_data = base64.b64encode(png_bytes).decode()

        data = ImageAttachment(
            filename="test.png",
            mimeType="image/png",
            base64Data=b64_data,
            isText=False
        )
        assert data.filename == "test.png"
        assert data.mimeType == "image/png"
        assert data.isText is False

    @pytest.mark.unit
    def test_image_attachment_invalid_base64(self):
        """Test that invalid base64 data is rejected."""
        with pytest.raises(ValueError, match="Invalid base64"):
            ImageAttachment(
                filename="test.png",
                mimeType="image/png",
                base64Data="not-valid-base64!!!",
                isText=False
            )

    @pytest.mark.unit
    def test_image_attachment_size_limit(self):
        """Test that images over 5MB are rejected."""
        import base64
        large_data = base64.b64encode(b"x" * (6 * 1024 * 1024)).decode()  # 6MB

        with pytest.raises(ValueError, match="exceeds maximum"):
            ImageAttachment(
                filename="large.png",
                mimeType="image/png",
                base64Data=large_data,
                isText=False
            )


class TestTextAttachmentContract:
    """Tests for TextAttachment schema validation."""

    @pytest.mark.unit
    def test_valid_text_attachment(self):
        """Test valid text attachment."""
        data = TextAttachment(
            filename="readme.md",
            mimeType="text/markdown",
            textContent="# Hello World",
            isText=True
        )
        assert data.filename == "readme.md"
        assert data.mimeType == "text/markdown"
        assert data.isText is True

    @pytest.mark.unit
    def test_text_attachment_size_limit(self):
        """Test that text over 1MB is rejected."""
        large_content = "x" * (2 * 1024 * 1024)  # 2MB

        with pytest.raises(ValueError, match="exceeds maximum"):
            TextAttachment(
                filename="large.txt",
                mimeType="text/plain",
                textContent=large_content,
                isText=True
            )


# =============================================================================
# Task Schema Contract Tests
# =============================================================================

class TestTaskCreateContract:
    """Tests for TaskCreate schema validation."""

    @pytest.mark.unit
    def test_valid_task_create_minimal(self):
        """Test minimal valid task creation."""
        data = TaskCreate(title="Fix bug")
        assert data.title == "Fix bug"
        assert data.description == ""  # default
        assert data.priority == 2  # default
        assert data.task_type == "feature"  # default

    @pytest.mark.unit
    def test_valid_task_create_full(self):
        """Test full task creation."""
        data = TaskCreate(
            title="Implement auth",
            description="Add OAuth support",
            priority=0,
            task_type="task"
        )
        assert data.title == "Implement auth"
        assert data.priority == 0
        assert data.task_type == "task"

    @pytest.mark.unit
    def test_task_title_too_short(self):
        """Test that empty titles are rejected."""
        with pytest.raises(ValueError):
            TaskCreate(title="")

    @pytest.mark.unit
    def test_task_title_too_long(self):
        """Test that titles over 200 chars are rejected."""
        with pytest.raises(ValueError):
            TaskCreate(title="x" * 201)

    @pytest.mark.unit
    def test_task_priority_validation(self):
        """Test priority must be 0-4."""
        # Valid priorities
        for p in [0, 1, 2, 3, 4]:
            data = TaskCreate(title="Test", priority=p)
            assert data.priority == p

        # Invalid priorities
        with pytest.raises(ValueError):
            TaskCreate(title="Test", priority=-1)
        with pytest.raises(ValueError):
            TaskCreate(title="Test", priority=5)

    @pytest.mark.unit
    def test_task_type_validation(self):
        """Test that only valid task types are accepted."""
        valid_types = ["feature", "task", "bug"]
        for t in valid_types:
            data = TaskCreate(title="Test", task_type=t)
            assert data.task_type == t


class TestTaskUpdateContract:
    """Tests for TaskUpdate schema validation."""

    @pytest.mark.unit
    def test_task_update_status(self):
        """Test updating task status."""
        valid_statuses = ["open", "in_progress", "closed"]
        for status in valid_statuses:
            data = TaskUpdate(status=status)
            assert data.status == status

    @pytest.mark.unit
    def test_task_update_priority(self):
        """Test updating task priority."""
        for p in [0, 1, 2, 3, 4]:
            data = TaskUpdate(priority=p)
            assert data.priority == p

    @pytest.mark.unit
    def test_task_update_title(self):
        """Test updating task title."""
        data = TaskUpdate(title="New title")
        assert data.title == "New title"


# =============================================================================
# Edge Case Tests
# =============================================================================

class TestSchemaEdgeCases:
    """Tests for schema edge cases and boundary conditions."""

    @pytest.mark.unit
    def test_unicode_in_project_name(self):
        """Test that unicode in project names is handled."""
        # Pattern only allows ASCII alphanumeric, dash, underscore
        with pytest.raises(ValueError):
            ProjectCreate(name="项目", git_url="https://github.com/user/repo.git")

    @pytest.mark.unit
    def test_unicode_in_feature_description(self):
        """Test that unicode in descriptions is allowed."""
        data = FeatureCreate(
            category="i18n",
            name="多语言支持",
            description="Implement 国际化 support with emoji 🎉",
            steps=["Step 一"]
        )
        assert "国际化" in data.description
        assert "🎉" in data.description

    @pytest.mark.unit
    def test_special_chars_in_description(self):
        """Test that special characters in descriptions work."""
        special_desc = "Use `code` and **bold** with <html> and 'quotes' and \"double\""
        data = FeatureCreate(
            category="test",
            name="Special",
            description=special_desc,
            steps=[]
        )
        assert data.description == special_desc

    @pytest.mark.unit
    def test_very_long_description(self):
        """Test handling of long descriptions."""
        long_desc = "x" * 10000
        data = FeatureCreate(
            category="test",
            name="Long Desc",
            description=long_desc,
            steps=[]
        )
        assert len(data.description) == 10000

    @pytest.mark.unit
    def test_empty_optional_fields(self):
        """Test that empty optional fields are handled."""
        data = FeatureUpdate()
        assert data.name is None
        assert data.description is None
        assert data.category is None
        assert data.priority is None
        assert data.steps is None

    @pytest.mark.unit
    def test_whitespace_handling(self):
        """Test whitespace in various fields."""
        # Leading/trailing whitespace should be preserved in Pydantic by default
        data = FeatureCreate(
            category="  auth  ",
            name="  Login  ",
            description="  Description  ",
            steps=["  Step 1  "]
        )
        assert data.category == "  auth  "
        assert data.name == "  Login  "


# =============================================================================
# Serialization Tests
# =============================================================================

class TestSchemaSerialization:
    """Tests for schema serialization and deserialization."""

    @pytest.mark.unit
    def test_project_summary_to_dict(self):
        """Test ProjectSummary serialization."""
        from server.schemas import ProjectStats

        stats = ProjectStats(passing=5, in_progress=2, total=10, percentage=50.0)
        summary = ProjectSummary(
            name="test",
            git_url="https://github.com/user/repo.git",
            local_path="/path/to/project",
            is_new=False,
            has_spec=True,
            stats=stats
        )

        data = summary.model_dump()
        assert data["name"] == "test"
        assert data["stats"]["passing"] == 5
        assert data["stats"]["percentage"] == 50.0

    @pytest.mark.unit
    def test_agent_status_json_serialization(self):
        """Test AgentStatus JSON serialization with datetime."""
        started = datetime(2024, 1, 15, 12, 0, 0)
        status = AgentStatus(
            status="running",
            started_at=started
        )

        json_data = status.model_dump_json()
        assert "2024-01-15" in json_data

    @pytest.mark.unit
    def test_wizard_status_roundtrip(self):
        """Test WizardStatus serialization roundtrip."""
        original = WizardStatus(
            step="chat",
            spec_method="claude",
            started_at=datetime(2024, 1, 15, 12, 0, 0),
            chat_messages=[
                WizardStatusMessage(
                    role="user",
                    content="Hello",
                    timestamp=datetime(2024, 1, 15, 12, 0, 1)
                )
            ]
        )

        # Serialize to dict and back
        data = original.model_dump()
        restored = WizardStatus(**data)

        assert restored.step == original.step
        assert restored.spec_method == original.spec_method
        assert len(restored.chat_messages) == 1
        assert restored.chat_messages[0].content == "Hello"
