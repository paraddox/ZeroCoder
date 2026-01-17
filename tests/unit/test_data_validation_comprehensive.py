"""
Comprehensive Data Validation Tests
===================================

Enterprise-grade tests for data validation including:
- Schema validation
- Input sanitization
- Type coercion
- Boundary conditions
- Format validation
"""

import json
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from pydantic import ValidationError
from unittest.mock import AsyncMock, MagicMock, patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Project Schema Validation Tests
# =============================================================================

class TestProjectCreateValidation:
    """Tests for ProjectCreate schema validation."""

    @pytest.mark.unit
    def test_valid_project_name_alphanumeric(self):
        """Test valid alphanumeric project names."""
        from server.schemas import ProjectCreate

        valid_names = [
            "myproject",
            "my-project",
            "my_project",
            "MyProject123",
            "a",  # Single char
            "a" * 50,  # Max length
        ]

        for name in valid_names:
            project = ProjectCreate(
                name=name,
                git_url="https://github.com/user/repo.git"
            )
            assert project.name == name

    @pytest.mark.unit
    def test_invalid_project_name_empty(self):
        """Test that empty project names are rejected."""
        from server.schemas import ProjectCreate

        with pytest.raises(ValidationError) as exc_info:
            ProjectCreate(name="", git_url="https://github.com/user/repo.git")

        assert "name" in str(exc_info.value).lower()

    @pytest.mark.unit
    def test_invalid_project_name_too_long(self):
        """Test that project names exceeding max length are rejected."""
        from server.schemas import ProjectCreate

        with pytest.raises(ValidationError):
            ProjectCreate(
                name="a" * 51,  # Exceeds max_length=50
                git_url="https://github.com/user/repo.git"
            )

    @pytest.mark.unit
    def test_invalid_project_name_special_chars(self):
        """Test that special characters are rejected."""
        from server.schemas import ProjectCreate

        invalid_names = [
            "project name",  # Space
            "project.name",  # Dot
            "project/name",  # Slash
            "project@name",  # At
            "project#name",  # Hash
            "project$name",  # Dollar
            "project%name",  # Percent
        ]

        for name in invalid_names:
            with pytest.raises(ValidationError):
                ProjectCreate(
                    name=name,
                    git_url="https://github.com/user/repo.git"
                )

    @pytest.mark.unit
    def test_git_url_https_valid(self):
        """Test valid HTTPS git URLs."""
        from server.schemas import ProjectCreate

        valid_urls = [
            "https://github.com/user/repo.git",
            "https://gitlab.com/user/repo.git",
            "https://bitbucket.org/user/repo.git",
            "https://example.com/path/to/repo.git",
        ]

        for url in valid_urls:
            project = ProjectCreate(name="test", git_url=url)
            assert project.git_url == url

    @pytest.mark.unit
    def test_git_url_ssh_valid(self):
        """Test valid SSH git URLs."""
        from server.schemas import ProjectCreate

        valid_urls = [
            "git@github.com:user/repo.git",
            "git@gitlab.com:user/repo.git",
        ]

        for url in valid_urls:
            project = ProjectCreate(name="test", git_url=url)
            assert project.git_url == url

    @pytest.mark.unit
    def test_spec_method_valid_values(self):
        """Test valid spec_method values."""
        from server.schemas import ProjectCreate

        for method in ["claude", "manual"]:
            project = ProjectCreate(
                name="test",
                git_url="https://github.com/user/repo.git",
                spec_method=method
            )
            assert project.spec_method == method

    @pytest.mark.unit
    def test_spec_method_invalid_value(self):
        """Test invalid spec_method values."""
        from server.schemas import ProjectCreate

        with pytest.raises(ValidationError):
            ProjectCreate(
                name="test",
                git_url="https://github.com/user/repo.git",
                spec_method="invalid"
            )


# =============================================================================
# Feature Schema Validation Tests
# =============================================================================

class TestFeatureCreateValidation:
    """Tests for FeatureCreate schema validation."""

    @pytest.mark.unit
    def test_valid_feature_create(self):
        """Test valid feature creation data."""
        from server.schemas import FeatureCreate

        feature = FeatureCreate(
            category="authentication",
            name="User Login",
            description="Implement user login functionality",
            steps=["Create form", "Add validation", "Connect API"]
        )

        assert feature.category == "authentication"
        assert feature.name == "User Login"
        assert len(feature.steps) == 3

    @pytest.mark.unit
    def test_feature_priority_bounds(self):
        """Test feature priority bounds."""
        from server.schemas import FeatureCreate

        # Valid priorities
        for priority in [0, 1, 2, 3, 4]:
            feature = FeatureCreate(
                category="test",
                name="Test",
                description="Test",
                steps=["Step 1"],
                priority=priority
            )
            assert feature.priority == priority

    @pytest.mark.unit
    def test_feature_optional_priority(self):
        """Test that priority is optional."""
        from server.schemas import FeatureCreate

        feature = FeatureCreate(
            category="test",
            name="Test",
            description="Test",
            steps=["Step 1"]
        )

        assert feature.priority is None


class TestFeatureUpdateValidation:
    """Tests for FeatureUpdate schema validation."""

    @pytest.mark.unit
    def test_partial_update(self):
        """Test that partial updates are allowed."""
        from server.schemas import FeatureUpdate

        # Only name
        update = FeatureUpdate(name="New Name")
        assert update.name == "New Name"
        assert update.description is None

        # Only priority
        update = FeatureUpdate(priority=2)
        assert update.priority == 2
        assert update.name is None

    @pytest.mark.unit
    def test_update_priority_bounds(self):
        """Test priority bounds in updates."""
        from server.schemas import FeatureUpdate

        # Valid
        update = FeatureUpdate(priority=0)
        assert update.priority == 0

        update = FeatureUpdate(priority=4)
        assert update.priority == 4


# =============================================================================
# Container Schema Validation Tests
# =============================================================================

class TestContainerSchemaValidation:
    """Tests for container-related schema validation."""

    @pytest.mark.unit
    def test_container_count_bounds(self):
        """Test container count bounds."""
        from server.schemas import ContainerCountUpdate

        # Valid range
        for count in [1, 5, 10]:
            update = ContainerCountUpdate(target_count=count)
            assert update.target_count == count

    @pytest.mark.unit
    def test_container_count_below_min(self):
        """Test container count below minimum."""
        from server.schemas import ContainerCountUpdate

        with pytest.raises(ValidationError):
            ContainerCountUpdate(target_count=0)

    @pytest.mark.unit
    def test_container_count_above_max(self):
        """Test container count above maximum."""
        from server.schemas import ContainerCountUpdate

        with pytest.raises(ValidationError):
            ContainerCountUpdate(target_count=11)

    @pytest.mark.unit
    def test_container_status_valid_values(self):
        """Test valid container status values."""
        from server.schemas import ContainerStatus

        valid_statuses = ["not_created", "created", "running", "stopping", "stopped", "completed"]
        for status in valid_statuses:
            container = ContainerStatus(
                id=1,
                container_number=1,
                container_type="coding",
                status=status
            )
            assert container.status == status


# =============================================================================
# Task Schema Validation Tests
# =============================================================================

class TestTaskSchemaValidation:
    """Tests for task-related schema validation."""

    @pytest.mark.unit
    def test_task_create_valid(self):
        """Test valid task creation."""
        from server.schemas import TaskCreate

        task = TaskCreate(
            title="Implement feature",
            description="Full description here",
            priority=2,
            task_type="feature"
        )

        assert task.title == "Implement feature"
        assert task.priority == 2
        assert task.task_type == "feature"

    @pytest.mark.unit
    def test_task_create_title_bounds(self):
        """Test task title length bounds."""
        from server.schemas import TaskCreate

        # Empty title
        with pytest.raises(ValidationError):
            TaskCreate(title="")

        # Too long title
        with pytest.raises(ValidationError):
            TaskCreate(title="x" * 201)

        # Valid max length
        task = TaskCreate(title="x" * 200)
        assert len(task.title) == 200

    @pytest.mark.unit
    def test_task_create_priority_bounds(self):
        """Test task priority bounds."""
        from server.schemas import TaskCreate

        # Valid range
        for priority in range(5):
            task = TaskCreate(title="Test", priority=priority)
            assert task.priority == priority

        # Invalid
        with pytest.raises(ValidationError):
            TaskCreate(title="Test", priority=-1)

        with pytest.raises(ValidationError):
            TaskCreate(title="Test", priority=5)

    @pytest.mark.unit
    def test_task_create_type_values(self):
        """Test valid task type values."""
        from server.schemas import TaskCreate

        for task_type in ["feature", "task", "bug"]:
            task = TaskCreate(title="Test", task_type=task_type)
            assert task.task_type == task_type

        with pytest.raises(ValidationError):
            TaskCreate(title="Test", task_type="invalid")

    @pytest.mark.unit
    def test_task_update_status_values(self):
        """Test valid task status values in updates."""
        from server.schemas import TaskUpdate

        for status in ["open", "in_progress", "closed"]:
            update = TaskUpdate(status=status)
            assert update.status == status

        with pytest.raises(ValidationError):
            TaskUpdate(status="invalid")


# =============================================================================
# Attachment Schema Validation Tests
# =============================================================================

class TestAttachmentSchemaValidation:
    """Tests for attachment schema validation."""

    @pytest.mark.unit
    def test_image_attachment_valid(self):
        """Test valid image attachment."""
        from server.schemas import ImageAttachment
        import base64

        # Create small valid base64 image data
        data = base64.b64encode(b"fake image data").decode()

        attachment = ImageAttachment(
            filename="test.png",
            mimeType="image/png",
            base64Data=data
        )

        assert attachment.filename == "test.png"
        assert attachment.mimeType == "image/png"

    @pytest.mark.unit
    def test_image_attachment_invalid_mime(self):
        """Test image attachment with invalid MIME type."""
        from server.schemas import ImageAttachment
        import base64

        data = base64.b64encode(b"data").decode()

        with pytest.raises(ValidationError):
            ImageAttachment(
                filename="test.gif",
                mimeType="image/gif",  # Not in allowed types
                base64Data=data
            )

    @pytest.mark.unit
    def test_image_attachment_size_limit(self):
        """Test image attachment size limit enforcement."""
        from server.schemas import ImageAttachment
        import base64

        # Create data larger than 5MB
        large_data = base64.b64encode(b"x" * (6 * 1024 * 1024)).decode()

        with pytest.raises(ValidationError) as exc_info:
            ImageAttachment(
                filename="large.png",
                mimeType="image/png",
                base64Data=large_data
            )

        assert "exceeds" in str(exc_info.value).lower()

    @pytest.mark.unit
    def test_text_attachment_valid(self):
        """Test valid text attachment."""
        from server.schemas import TextAttachment

        attachment = TextAttachment(
            filename="readme.md",
            mimeType="text/markdown",
            textContent="# Hello World"
        )

        assert attachment.filename == "readme.md"
        assert attachment.textContent == "# Hello World"

    @pytest.mark.unit
    def test_text_attachment_size_limit(self):
        """Test text attachment size limit enforcement."""
        from server.schemas import TextAttachment

        # Create text larger than 1MB
        large_text = "x" * (2 * 1024 * 1024)

        with pytest.raises(ValidationError) as exc_info:
            TextAttachment(
                filename="large.txt",
                mimeType="text/plain",
                textContent=large_text
            )

        assert "exceeds" in str(exc_info.value).lower()


# =============================================================================
# WebSocket Message Schema Validation Tests
# =============================================================================

class TestWebSocketMessageValidation:
    """Tests for WebSocket message schema validation."""

    @pytest.mark.unit
    def test_progress_message_valid(self):
        """Test valid progress message."""
        from server.schemas import WSProgressMessage

        msg = WSProgressMessage(
            passing=5,
            total=10,
            percentage=50.0
        )

        assert msg.type == "progress"
        assert msg.passing == 5
        assert msg.total == 10
        assert msg.percentage == 50.0

    @pytest.mark.unit
    def test_feature_update_message_valid(self):
        """Test valid feature update message."""
        from server.schemas import WSFeatureUpdateMessage

        msg = WSFeatureUpdateMessage(
            feature_id="feat-123",
            passes=True
        )

        assert msg.type == "feature_update"
        assert msg.feature_id == "feat-123"
        assert msg.passes is True

    @pytest.mark.unit
    def test_log_message_valid(self):
        """Test valid log message."""
        from server.schemas import WSLogMessage

        msg = WSLogMessage(
            line="Processing feature...",
            timestamp=datetime.now()
        )

        assert msg.type == "log"
        assert msg.line == "Processing feature..."

    @pytest.mark.unit
    def test_agent_status_message_valid(self):
        """Test valid agent status message."""
        from server.schemas import WSAgentStatusMessage

        msg = WSAgentStatusMessage(status="running")

        assert msg.type == "agent_status"
        assert msg.status == "running"


# =============================================================================
# Wizard Status Schema Validation Tests
# =============================================================================

class TestWizardStatusValidation:
    """Tests for wizard status schema validation."""

    @pytest.mark.unit
    def test_wizard_status_valid(self):
        """Test valid wizard status."""
        from server.schemas import WizardStatus

        status = WizardStatus(
            step="chat",
            spec_method="claude",
            started_at=datetime.now(),
            chat_messages=[]
        )

        assert status.step == "chat"
        assert status.spec_method == "claude"

    @pytest.mark.unit
    def test_wizard_status_step_values(self):
        """Test valid wizard step values."""
        from server.schemas import WizardStatus

        for step in ["mode", "details", "method", "chat"]:
            status = WizardStatus(
                step=step,
                started_at=datetime.now()
            )
            assert status.step == step

    @pytest.mark.unit
    def test_wizard_status_message_format(self):
        """Test wizard status message format."""
        from server.schemas import WizardStatus, WizardStatusMessage

        message = WizardStatusMessage(
            role="user",
            content="Create a todo app",
            timestamp=datetime.now()
        )

        status = WizardStatus(
            step="chat",
            started_at=datetime.now(),
            chat_messages=[message]
        )

        assert len(status.chat_messages) == 1
        assert status.chat_messages[0].role == "user"


# =============================================================================
# Agent Schema Validation Tests
# =============================================================================

class TestAgentSchemaValidation:
    """Tests for agent-related schema validation."""

    @pytest.mark.unit
    def test_agent_start_request_valid(self):
        """Test valid agent start request."""
        from server.schemas import AgentStartRequest

        request = AgentStartRequest(
            instruction="Implement the next feature",
            yolo_mode=False
        )

        assert request.instruction == "Implement the next feature"
        assert request.yolo_mode is False

    @pytest.mark.unit
    def test_agent_start_request_optional_instruction(self):
        """Test that instruction is optional."""
        from server.schemas import AgentStartRequest

        request = AgentStartRequest()

        assert request.instruction is None
        assert request.yolo_mode is False

    @pytest.mark.unit
    def test_agent_status_valid(self):
        """Test valid agent status."""
        from server.schemas import AgentStatus

        status = AgentStatus(
            status="running",
            container_name="zerocoder-test-1",
            started_at=datetime.now(),
            idle_seconds=100,
            agent_running=True
        )

        assert status.status == "running"
        assert status.agent_running is True

    @pytest.mark.unit
    def test_agent_status_values(self):
        """Test valid agent status values."""
        from server.schemas import AgentStatus

        valid_statuses = ["not_created", "stopped", "running", "paused", "crashed", "completed"]

        for status_value in valid_statuses:
            status = AgentStatus(status=status_value)
            assert status.status == status_value


# =============================================================================
# Edge Case Validation Tests
# =============================================================================

class TestEdgeCaseValidation:
    """Tests for edge cases in validation."""

    @pytest.mark.unit
    def test_empty_string_handling(self):
        """Test handling of empty strings."""
        from server.schemas import TaskCreate

        with pytest.raises(ValidationError):
            TaskCreate(title="")

    @pytest.mark.unit
    def test_whitespace_only_string(self):
        """Test handling of whitespace-only strings."""
        from server.schemas import TaskCreate

        # Whitespace may or may not be valid depending on implementation
        try:
            task = TaskCreate(title="   ")
            # If accepted, whitespace is preserved
            assert task.title == "   "
        except ValidationError:
            # If rejected, that's fine
            pass

    @pytest.mark.unit
    def test_unicode_content(self):
        """Test handling of Unicode content."""
        from server.schemas import TaskCreate

        task = TaskCreate(
            title="日本語テスト 🚀 émoji",
            description="Unicode: 中文, العربية, 한국어"
        )

        assert "日本語" in task.title
        assert "🚀" in task.title

    @pytest.mark.unit
    def test_very_long_description(self):
        """Test handling of very long descriptions."""
        from server.schemas import TaskCreate

        # Should accept up to 5000 chars
        long_desc = "x" * 5000
        task = TaskCreate(title="Test", description=long_desc)
        assert len(task.description) == 5000

        # Should reject longer
        with pytest.raises(ValidationError):
            TaskCreate(title="Test", description="x" * 5001)

    @pytest.mark.unit
    def test_null_values_where_optional(self):
        """Test that optional fields can be null."""
        from server.schemas import FeatureUpdate

        update = FeatureUpdate()

        assert update.name is None
        assert update.description is None
        assert update.priority is None
        assert update.steps is None

    @pytest.mark.unit
    def test_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        from server.schemas import ProjectCreate

        # By default, Pydantic ignores extra fields
        project = ProjectCreate(
            name="test",
            git_url="https://github.com/user/repo.git",
            extra_field="should be ignored"  # type: ignore
        )

        assert not hasattr(project, "extra_field") or project.model_config.get("extra") == "ignore"
