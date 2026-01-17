"""
Comprehensive Schema Validation Tests
=====================================

Enterprise-grade tests for all Pydantic schemas including:
- Field validation
- Pattern matching
- Size limits
- Type coercion
- Edge cases
"""

import base64
import pytest
from datetime import datetime
from pydantic import ValidationError

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from server.schemas import (
    ProjectCreate,
    ProjectStats,
    ProjectSummary,
    ProjectDetail,
    ProjectSettingsUpdate,
    ProjectPrompts,
    ProjectPromptsUpdate,
    WizardStatusMessage,
    WizardStatus,
    AddExistingRepoRequest,
    ContainerCountUpdate,
    ContainerStatus,
    FeatureBase,
    FeatureCreate,
    FeatureUpdate,
    FeatureResponse,
    FeatureListResponse,
    AgentStartRequest,
    AgentStatus,
    AgentActionResponse,
    SetupStatus,
    WSProgressMessage,
    WSFeatureUpdateMessage,
    WSLogMessage,
    WSAgentStatusMessage,
    ImageAttachment,
    TextAttachment,
    TaskCreate,
    TaskUpdate,
    MAX_IMAGE_SIZE,
    MAX_TEXT_SIZE,
)


class TestProjectCreate:
    """Tests for ProjectCreate schema validation."""

    @pytest.mark.unit
    def test_valid_project_create(self):
        """Test valid project creation data."""
        project = ProjectCreate(
            name="my-project",
            git_url="https://github.com/user/repo.git",
            is_new=True,
            spec_method="claude"
        )
        assert project.name == "my-project"
        assert project.git_url == "https://github.com/user/repo.git"
        assert project.is_new is True
        assert project.spec_method == "claude"

    @pytest.mark.unit
    def test_project_name_with_underscore(self):
        """Test project name with underscore."""
        project = ProjectCreate(
            name="my_project_name",
            git_url="https://github.com/user/repo.git"
        )
        assert project.name == "my_project_name"

    @pytest.mark.unit
    def test_project_name_with_dash(self):
        """Test project name with dash."""
        project = ProjectCreate(
            name="my-project-name",
            git_url="https://github.com/user/repo.git"
        )
        assert project.name == "my-project-name"

    @pytest.mark.unit
    def test_project_name_numeric(self):
        """Test project name with numbers."""
        project = ProjectCreate(
            name="project123",
            git_url="https://github.com/user/repo.git"
        )
        assert project.name == "project123"

    @pytest.mark.unit
    def test_project_name_too_short(self):
        """Test that empty project name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ProjectCreate(
                name="",
                git_url="https://github.com/user/repo.git"
            )
        assert "String should have at least 1 character" in str(exc_info.value)

    @pytest.mark.unit
    def test_project_name_too_long(self):
        """Test that overly long project name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ProjectCreate(
                name="a" * 51,
                git_url="https://github.com/user/repo.git"
            )
        assert "String should have at most 50 character" in str(exc_info.value)

    @pytest.mark.unit
    def test_project_name_invalid_characters(self):
        """Test that invalid characters in project name are rejected."""
        invalid_names = [
            "project with space",
            "project/slash",
            "project.dot",
            "project@at",
            "project#hash",
            "project$dollar",
            "project%percent",
        ]
        for name in invalid_names:
            with pytest.raises(ValidationError):
                ProjectCreate(
                    name=name,
                    git_url="https://github.com/user/repo.git"
                )

    @pytest.mark.unit
    def test_git_url_https(self):
        """Test HTTPS git URL validation."""
        project = ProjectCreate(
            name="test",
            git_url="https://github.com/user/repo.git"
        )
        assert project.git_url == "https://github.com/user/repo.git"

    @pytest.mark.unit
    def test_git_url_ssh(self):
        """Test SSH git URL validation."""
        project = ProjectCreate(
            name="test",
            git_url="git@github.com:user/repo.git"
        )
        assert project.git_url == "git@github.com:user/repo.git"

    @pytest.mark.unit
    def test_git_url_empty(self):
        """Test that empty git URL is rejected."""
        with pytest.raises(ValidationError):
            ProjectCreate(
                name="test",
                git_url=""
            )

    @pytest.mark.unit
    def test_default_is_new(self):
        """Test default value for is_new."""
        project = ProjectCreate(
            name="test",
            git_url="https://github.com/user/repo.git"
        )
        assert project.is_new is True

    @pytest.mark.unit
    def test_default_spec_method(self):
        """Test default value for spec_method."""
        project = ProjectCreate(
            name="test",
            git_url="https://github.com/user/repo.git"
        )
        assert project.spec_method == "claude"

    @pytest.mark.unit
    def test_spec_method_manual(self):
        """Test manual spec_method."""
        project = ProjectCreate(
            name="test",
            git_url="https://github.com/user/repo.git",
            spec_method="manual"
        )
        assert project.spec_method == "manual"

    @pytest.mark.unit
    def test_spec_method_invalid(self):
        """Test that invalid spec_method is rejected."""
        with pytest.raises(ValidationError):
            ProjectCreate(
                name="test",
                git_url="https://github.com/user/repo.git",
                spec_method="invalid"
            )


class TestProjectStats:
    """Tests for ProjectStats schema."""

    @pytest.mark.unit
    def test_default_values(self):
        """Test default values for ProjectStats."""
        stats = ProjectStats()
        assert stats.passing == 0
        assert stats.in_progress == 0
        assert stats.total == 0
        assert stats.percentage == 0.0

    @pytest.mark.unit
    def test_custom_values(self):
        """Test custom values for ProjectStats."""
        stats = ProjectStats(
            passing=5,
            in_progress=2,
            total=10,
            percentage=50.0
        )
        assert stats.passing == 5
        assert stats.in_progress == 2
        assert stats.total == 10
        assert stats.percentage == 50.0

    @pytest.mark.unit
    def test_percentage_precision(self):
        """Test percentage with decimal precision."""
        stats = ProjectStats(percentage=33.33)
        assert stats.percentage == 33.33


class TestContainerCountUpdate:
    """Tests for ContainerCountUpdate schema."""

    @pytest.mark.unit
    def test_valid_count(self):
        """Test valid container count."""
        update = ContainerCountUpdate(target_count=5)
        assert update.target_count == 5

    @pytest.mark.unit
    def test_minimum_count(self):
        """Test minimum container count."""
        update = ContainerCountUpdate(target_count=1)
        assert update.target_count == 1

    @pytest.mark.unit
    def test_maximum_count(self):
        """Test maximum container count."""
        update = ContainerCountUpdate(target_count=10)
        assert update.target_count == 10

    @pytest.mark.unit
    def test_count_too_low(self):
        """Test that count below minimum is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ContainerCountUpdate(target_count=0)
        assert "greater than or equal to 1" in str(exc_info.value)

    @pytest.mark.unit
    def test_count_too_high(self):
        """Test that count above maximum is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ContainerCountUpdate(target_count=11)
        assert "less than or equal to 10" in str(exc_info.value)


class TestContainerStatus:
    """Tests for ContainerStatus schema."""

    @pytest.mark.unit
    def test_valid_container_status(self):
        """Test valid container status."""
        status = ContainerStatus(
            id=1,
            container_number=1,
            container_type="coding",
            status="running",
            current_feature="feat-1"
        )
        assert status.id == 1
        assert status.container_number == 1
        assert status.container_type == "coding"
        assert status.status == "running"
        assert status.current_feature == "feat-1"

    @pytest.mark.unit
    def test_init_container_type(self):
        """Test init container type."""
        status = ContainerStatus(
            id=1,
            container_number=0,
            container_type="init",
            status="created"
        )
        assert status.container_type == "init"

    @pytest.mark.unit
    def test_all_status_values(self):
        """Test all valid status values."""
        valid_statuses = ["not_created", "created", "running", "stopping", "stopped", "completed"]
        for status_value in valid_statuses:
            status = ContainerStatus(
                id=1,
                container_number=1,
                container_type="coding",
                status=status_value
            )
            assert status.status == status_value

    @pytest.mark.unit
    def test_invalid_status_value(self):
        """Test that invalid status value is rejected."""
        with pytest.raises(ValidationError):
            ContainerStatus(
                id=1,
                container_number=1,
                container_type="coding",
                status="invalid_status"
            )

    @pytest.mark.unit
    def test_agent_types(self):
        """Test all valid agent types."""
        agent_types = ["coder", "overseer", "hound", "initializer"]
        for agent_type in agent_types:
            status = ContainerStatus(
                id=1,
                container_number=1,
                container_type="coding",
                status="running",
                agent_type=agent_type
            )
            assert status.agent_type == agent_type


class TestFeatureSchemas:
    """Tests for Feature-related schemas."""

    @pytest.mark.unit
    def test_feature_create_valid(self):
        """Test valid feature creation."""
        feature = FeatureCreate(
            category="auth",
            name="User Login",
            description="Implement user authentication",
            steps=["Create form", "Add validation", "Connect API"],
            priority=1
        )
        assert feature.category == "auth"
        assert feature.name == "User Login"
        assert len(feature.steps) == 3
        assert feature.priority == 1

    @pytest.mark.unit
    def test_feature_create_no_priority(self):
        """Test feature creation without priority."""
        feature = FeatureCreate(
            category="ui",
            name="Dashboard",
            description="Create dashboard",
            steps=["Design", "Implement"]
        )
        assert feature.priority is None

    @pytest.mark.unit
    def test_feature_update_partial(self):
        """Test partial feature update."""
        update = FeatureUpdate(name="Updated Name")
        assert update.name == "Updated Name"
        assert update.description is None
        assert update.category is None

    @pytest.mark.unit
    def test_feature_update_full(self):
        """Test full feature update."""
        update = FeatureUpdate(
            name="Updated",
            description="New description",
            category="backend",
            priority=2,
            steps=["Step 1", "Step 2"]
        )
        assert update.name == "Updated"
        assert update.description == "New description"
        assert update.category == "backend"
        assert update.priority == 2
        assert len(update.steps) == 2

    @pytest.mark.unit
    def test_feature_response(self):
        """Test feature response schema."""
        response = FeatureResponse(
            id="feat-1",
            category="auth",
            name="Login",
            description="User login",
            steps=["Form", "Validation"],
            priority=0,
            passes=False,
            in_progress=True
        )
        assert response.id == "feat-1"
        assert response.passes is False
        assert response.in_progress is True

    @pytest.mark.unit
    def test_feature_list_response(self):
        """Test feature list response schema."""
        response = FeatureListResponse(
            pending=[],
            in_progress=[],
            done=[]
        )
        assert len(response.pending) == 0
        assert len(response.in_progress) == 0
        assert len(response.done) == 0


class TestAgentSchemas:
    """Tests for Agent-related schemas."""

    @pytest.mark.unit
    def test_agent_start_request_default(self):
        """Test agent start request with defaults."""
        request = AgentStartRequest()
        assert request.instruction is None
        assert request.yolo_mode is False

    @pytest.mark.unit
    def test_agent_start_request_with_instruction(self):
        """Test agent start request with instruction."""
        request = AgentStartRequest(
            instruction="Implement feature X",
            yolo_mode=False
        )
        assert request.instruction == "Implement feature X"

    @pytest.mark.unit
    def test_agent_status_all_fields(self):
        """Test agent status with all fields."""
        status = AgentStatus(
            status="running",
            container_name="zerocoder-test-1",
            started_at=datetime.now(),
            idle_seconds=100,
            agent_running=True,
            graceful_stop_requested=False,
            agent_type="coder",
            sdk_type="claude"
        )
        assert status.status == "running"
        assert status.container_name == "zerocoder-test-1"
        assert status.agent_running is True
        assert status.agent_type == "coder"
        assert status.sdk_type == "claude"

    @pytest.mark.unit
    def test_agent_status_values(self):
        """Test all valid agent status values."""
        valid_statuses = ["not_created", "stopped", "running", "paused", "crashed", "completed"]
        for status_value in valid_statuses:
            status = AgentStatus(status=status_value)
            assert status.status == status_value

    @pytest.mark.unit
    def test_agent_action_response(self):
        """Test agent action response."""
        response = AgentActionResponse(
            success=True,
            status="running",
            message="Agent started successfully"
        )
        assert response.success is True
        assert response.status == "running"
        assert response.message == "Agent started successfully"


class TestImageAttachment:
    """Tests for ImageAttachment schema validation."""

    @pytest.mark.unit
    def test_valid_jpeg_image(self):
        """Test valid JPEG image attachment."""
        # Create small valid base64 image data
        image_data = base64.b64encode(b"fake image data").decode()
        attachment = ImageAttachment(
            filename="test.jpg",
            mimeType="image/jpeg",
            base64Data=image_data,
            isText=False
        )
        assert attachment.filename == "test.jpg"
        assert attachment.mimeType == "image/jpeg"

    @pytest.mark.unit
    def test_valid_png_image(self):
        """Test valid PNG image attachment."""
        image_data = base64.b64encode(b"fake png data").decode()
        attachment = ImageAttachment(
            filename="test.png",
            mimeType="image/png",
            base64Data=image_data,
            isText=False
        )
        assert attachment.mimeType == "image/png"

    @pytest.mark.unit
    def test_filename_too_long(self):
        """Test that overly long filename is rejected."""
        image_data = base64.b64encode(b"data").decode()
        with pytest.raises(ValidationError):
            ImageAttachment(
                filename="a" * 256,
                mimeType="image/jpeg",
                base64Data=image_data,
                isText=False
            )

    @pytest.mark.unit
    def test_empty_filename(self):
        """Test that empty filename is rejected."""
        image_data = base64.b64encode(b"data").decode()
        with pytest.raises(ValidationError):
            ImageAttachment(
                filename="",
                mimeType="image/jpeg",
                base64Data=image_data,
                isText=False
            )

    @pytest.mark.unit
    def test_invalid_base64(self):
        """Test that invalid base64 data is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ImageAttachment(
                filename="test.jpg",
                mimeType="image/jpeg",
                base64Data="not valid base64!!!",
                isText=False
            )
        assert "Invalid base64" in str(exc_info.value)

    @pytest.mark.unit
    def test_image_too_large(self):
        """Test that oversized image is rejected."""
        # Create data larger than MAX_IMAGE_SIZE
        large_data = b"x" * (MAX_IMAGE_SIZE + 1)
        large_base64 = base64.b64encode(large_data).decode()
        with pytest.raises(ValidationError) as exc_info:
            ImageAttachment(
                filename="large.jpg",
                mimeType="image/jpeg",
                base64Data=large_base64,
                isText=False
            )
        assert "exceeds maximum" in str(exc_info.value)

    @pytest.mark.unit
    def test_invalid_mime_type(self):
        """Test that invalid MIME type is rejected."""
        image_data = base64.b64encode(b"data").decode()
        with pytest.raises(ValidationError):
            ImageAttachment(
                filename="test.gif",
                mimeType="image/gif",  # Not in allowed types
                base64Data=image_data,
                isText=False
            )


class TestTextAttachment:
    """Tests for TextAttachment schema validation."""

    @pytest.mark.unit
    def test_valid_text_attachment(self):
        """Test valid text file attachment."""
        attachment = TextAttachment(
            filename="readme.md",
            mimeType="text/markdown",
            textContent="# Hello World",
            isText=True
        )
        assert attachment.filename == "readme.md"
        assert attachment.mimeType == "text/markdown"
        assert attachment.textContent == "# Hello World"

    @pytest.mark.unit
    def test_valid_json_attachment(self):
        """Test valid JSON file attachment."""
        attachment = TextAttachment(
            filename="config.json",
            mimeType="application/json",
            textContent='{"key": "value"}',
            isText=True
        )
        assert attachment.mimeType == "application/json"

    @pytest.mark.unit
    def test_text_too_large(self):
        """Test that oversized text is rejected."""
        large_text = "x" * (MAX_TEXT_SIZE + 1)
        with pytest.raises(ValidationError) as exc_info:
            TextAttachment(
                filename="large.txt",
                mimeType="text/plain",
                textContent=large_text,
                isText=True
            )
        assert "exceeds maximum" in str(exc_info.value)

    @pytest.mark.unit
    def test_all_text_mime_types(self):
        """Test all valid text MIME types."""
        valid_types = [
            "text/plain",
            "text/markdown",
            "text/csv",
            "application/json",
            "text/html",
            "text/css",
            "text/javascript",
            "application/xml"
        ]
        for mime_type in valid_types:
            attachment = TextAttachment(
                filename="test.txt",
                mimeType=mime_type,
                textContent="content",
                isText=True
            )
            assert attachment.mimeType == mime_type


class TestTaskSchemas:
    """Tests for Task-related schemas (Edit Mode)."""

    @pytest.mark.unit
    def test_task_create_valid(self):
        """Test valid task creation."""
        task = TaskCreate(
            title="Fix login bug",
            description="Users cannot login with valid credentials",
            priority=1,
            task_type="bug"
        )
        assert task.title == "Fix login bug"
        assert task.priority == 1
        assert task.task_type == "bug"

    @pytest.mark.unit
    def test_task_create_defaults(self):
        """Test task creation with defaults."""
        task = TaskCreate(title="New feature")
        assert task.description == ""
        assert task.priority == 2
        assert task.task_type == "feature"

    @pytest.mark.unit
    def test_task_create_title_too_short(self):
        """Test that empty title is rejected."""
        with pytest.raises(ValidationError):
            TaskCreate(title="")

    @pytest.mark.unit
    def test_task_create_title_too_long(self):
        """Test that overly long title is rejected."""
        with pytest.raises(ValidationError):
            TaskCreate(title="a" * 201)

    @pytest.mark.unit
    def test_task_create_priority_range(self):
        """Test valid priority range."""
        for priority in range(5):
            task = TaskCreate(title="Test", priority=priority)
            assert task.priority == priority

    @pytest.mark.unit
    def test_task_create_priority_too_low(self):
        """Test that negative priority is rejected."""
        with pytest.raises(ValidationError):
            TaskCreate(title="Test", priority=-1)

    @pytest.mark.unit
    def test_task_create_priority_too_high(self):
        """Test that priority above 4 is rejected."""
        with pytest.raises(ValidationError):
            TaskCreate(title="Test", priority=5)

    @pytest.mark.unit
    def test_task_create_invalid_type(self):
        """Test that invalid task type is rejected."""
        with pytest.raises(ValidationError):
            TaskCreate(title="Test", task_type="invalid")

    @pytest.mark.unit
    def test_task_update_status_values(self):
        """Test valid task update status values."""
        valid_statuses = ["open", "in_progress", "closed"]
        for status in valid_statuses:
            update = TaskUpdate(status=status)
            assert update.status == status

    @pytest.mark.unit
    def test_task_update_invalid_status(self):
        """Test that invalid status is rejected."""
        with pytest.raises(ValidationError):
            TaskUpdate(status="invalid")


class TestWebSocketMessages:
    """Tests for WebSocket message schemas."""

    @pytest.mark.unit
    def test_ws_progress_message(self):
        """Test WebSocket progress message."""
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
    def test_ws_feature_update_message(self):
        """Test WebSocket feature update message."""
        msg = WSFeatureUpdateMessage(
            feature_id="feat-1",
            passes=True
        )
        assert msg.type == "feature_update"
        assert msg.feature_id == "feat-1"
        assert msg.passes is True

    @pytest.mark.unit
    def test_ws_log_message(self):
        """Test WebSocket log message."""
        msg = WSLogMessage(
            line="Processing feature...",
            timestamp=datetime.now()
        )
        assert msg.type == "log"
        assert msg.line == "Processing feature..."

    @pytest.mark.unit
    def test_ws_agent_status_message(self):
        """Test WebSocket agent status message."""
        msg = WSAgentStatusMessage(status="running")
        assert msg.type == "agent_status"
        assert msg.status == "running"


class TestWizardSchemas:
    """Tests for Wizard-related schemas."""

    @pytest.mark.unit
    def test_wizard_status_message(self):
        """Test wizard status message."""
        msg = WizardStatusMessage(
            role="user",
            content="Create a todo app",
            timestamp=datetime.now()
        )
        assert msg.role == "user"
        assert msg.content == "Create a todo app"

    @pytest.mark.unit
    def test_wizard_status_message_roles(self):
        """Test both valid roles."""
        for role in ["user", "assistant"]:
            msg = WizardStatusMessage(
                role=role,
                content="Message",
                timestamp=datetime.now()
            )
            assert msg.role == role

    @pytest.mark.unit
    def test_wizard_status(self):
        """Test wizard status."""
        status = WizardStatus(
            step="chat",
            spec_method="claude",
            started_at=datetime.now(),
            chat_messages=[]
        )
        assert status.step == "chat"
        assert status.spec_method == "claude"

    @pytest.mark.unit
    def test_wizard_status_steps(self):
        """Test all valid wizard steps."""
        valid_steps = ["mode", "details", "method", "chat"]
        for step in valid_steps:
            status = WizardStatus(
                step=step,
                started_at=datetime.now()
            )
            assert status.step == step


class TestSetupStatus:
    """Tests for SetupStatus schema."""

    @pytest.mark.unit
    def test_setup_status_all_true(self):
        """Test setup status with all checks passing."""
        status = SetupStatus(
            claude_cli=True,
            credentials=True,
            node=True,
            npm=True
        )
        assert status.claude_cli is True
        assert status.credentials is True
        assert status.node is True
        assert status.npm is True

    @pytest.mark.unit
    def test_setup_status_mixed(self):
        """Test setup status with mixed results."""
        status = SetupStatus(
            claude_cli=True,
            credentials=False,
            node=True,
            npm=False
        )
        assert status.claude_cli is True
        assert status.credentials is False
