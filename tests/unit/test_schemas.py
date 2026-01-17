"""
Pydantic Schemas Unit Tests
===========================

Tests for request/response schema validation including:
- Field validation
- Type coercion
- Constraint enforcement
- Default values
"""

import base64
import pytest
from datetime import datetime
from pydantic import ValidationError

# Import schemas after path setup
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


class TestProjectSchemas:
    """Tests for project-related schemas."""

    @pytest.mark.unit
    def test_project_create_valid(self):
        """Test valid ProjectCreate schema."""
        data = ProjectCreate(
            name="my-project",
            git_url="https://github.com/user/repo.git",
            is_new=True,
            spec_method="claude"
        )
        assert data.name == "my-project"
        assert data.git_url == "https://github.com/user/repo.git"
        assert data.is_new is True
        assert data.spec_method == "claude"

    @pytest.mark.unit
    def test_project_create_default_values(self):
        """Test ProjectCreate default values."""
        data = ProjectCreate(
            name="test",
            git_url="https://github.com/user/repo.git"
        )
        assert data.is_new is True
        assert data.spec_method == "claude"

    @pytest.mark.unit
    def test_project_create_invalid_name_pattern(self):
        """Test that invalid name patterns are rejected."""
        invalid_names = [
            "name with spaces",
            "name/with/slashes",
            "name@special",
            "",
        ]
        for name in invalid_names:
            with pytest.raises(ValidationError):
                ProjectCreate(name=name, git_url="https://github.com/user/repo.git")

    @pytest.mark.unit
    def test_project_create_name_too_long(self):
        """Test that names over 50 chars are rejected."""
        with pytest.raises(ValidationError):
            ProjectCreate(
                name="a" * 51,
                git_url="https://github.com/user/repo.git"
            )

    @pytest.mark.unit
    def test_project_create_valid_name_patterns(self):
        """Test that valid name patterns are accepted."""
        valid_names = [
            "project",
            "my-project",
            "my_project",
            "Project123",
            "a",
            "a" * 50,
        ]
        for name in valid_names:
            data = ProjectCreate(name=name, git_url="https://github.com/user/repo.git")
            assert data.name == name

    @pytest.mark.unit
    def test_project_stats(self):
        """Test ProjectStats schema."""
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
    def test_project_stats_defaults(self):
        """Test ProjectStats default values."""
        stats = ProjectStats()
        assert stats.passing == 0
        assert stats.in_progress == 0
        assert stats.total == 0
        assert stats.percentage == 0.0

    @pytest.mark.unit
    def test_project_summary(self):
        """Test ProjectSummary schema."""
        summary = ProjectSummary(
            name="test",
            git_url="https://github.com/user/repo.git",
            local_path="/path/to/project",
            is_new=True,
            has_spec=True,
            wizard_incomplete=False,
            stats=ProjectStats(passing=3, total=10, percentage=30.0),
            target_container_count=2
        )
        assert summary.name == "test"
        assert summary.target_container_count == 2

    @pytest.mark.unit
    def test_project_settings_update(self):
        """Test ProjectSettingsUpdate schema."""
        settings = ProjectSettingsUpdate(agent_model="claude-sonnet-4-5-20250514")
        assert settings.agent_model == "claude-sonnet-4-5-20250514"


class TestContainerSchemas:
    """Tests for container-related schemas."""

    @pytest.mark.unit
    def test_container_count_update_valid(self):
        """Test valid ContainerCountUpdate."""
        update = ContainerCountUpdate(target_count=5)
        assert update.target_count == 5

    @pytest.mark.unit
    def test_container_count_update_min_boundary(self):
        """Test ContainerCountUpdate minimum value."""
        update = ContainerCountUpdate(target_count=1)
        assert update.target_count == 1

        with pytest.raises(ValidationError):
            ContainerCountUpdate(target_count=0)

    @pytest.mark.unit
    def test_container_count_update_max_boundary(self):
        """Test ContainerCountUpdate maximum value."""
        update = ContainerCountUpdate(target_count=10)
        assert update.target_count == 10

        with pytest.raises(ValidationError):
            ContainerCountUpdate(target_count=11)

    @pytest.mark.unit
    def test_container_status(self):
        """Test ContainerStatus schema."""
        status = ContainerStatus(
            id=1,
            container_number=1,
            container_type="coding",
            status="running",
            current_feature="feat-1"
        )
        assert status.id == 1
        assert status.container_type == "coding"
        assert status.status == "running"

    @pytest.mark.unit
    def test_container_status_valid_statuses(self):
        """Test ContainerStatus with all valid status values."""
        valid_statuses = ["not_created", "created", "running", "stopping", "stopped", "completed"]
        for status_val in valid_statuses:
            status = ContainerStatus(
                id=1,
                container_number=1,
                container_type="coding",
                status=status_val
            )
            assert status.status == status_val

    @pytest.mark.unit
    def test_container_status_valid_types(self):
        """Test ContainerStatus with valid container types."""
        for container_type in ["init", "coding"]:
            status = ContainerStatus(
                id=1,
                container_number=1,
                container_type=container_type,
                status="running"
            )
            assert status.container_type == container_type


class TestFeatureSchemas:
    """Tests for feature-related schemas."""

    @pytest.mark.unit
    def test_feature_base(self):
        """Test FeatureBase schema."""
        feature = FeatureBase(
            category="auth",
            name="User Login",
            description="Implement login",
            steps=["Create form", "Add validation"]
        )
        assert feature.category == "auth"
        assert feature.name == "User Login"
        assert len(feature.steps) == 2

    @pytest.mark.unit
    def test_feature_create(self):
        """Test FeatureCreate schema."""
        feature = FeatureCreate(
            category="auth",
            name="User Login",
            description="Implement login",
            steps=["Create form"],
            priority=1
        )
        assert feature.priority == 1

    @pytest.mark.unit
    def test_feature_create_optional_priority(self):
        """Test FeatureCreate with optional priority."""
        feature = FeatureCreate(
            category="auth",
            name="User Login",
            description="Implement login",
            steps=[]
        )
        assert feature.priority is None

    @pytest.mark.unit
    def test_feature_update_partial(self):
        """Test FeatureUpdate with partial data."""
        update = FeatureUpdate(name="New Name")
        assert update.name == "New Name"
        assert update.description is None
        assert update.category is None
        assert update.priority is None

    @pytest.mark.unit
    def test_feature_response(self):
        """Test FeatureResponse schema."""
        response = FeatureResponse(
            id="feat-1",
            category="auth",
            name="User Login",
            description="Login feature",
            steps=["Step 1"],
            priority=1,
            passes=True,
            in_progress=False
        )
        assert response.id == "feat-1"
        assert response.passes is True
        assert response.in_progress is False

    @pytest.mark.unit
    def test_feature_list_response(self):
        """Test FeatureListResponse schema."""
        response = FeatureListResponse(
            pending=[],
            in_progress=[],
            done=[]
        )
        assert isinstance(response.pending, list)
        assert isinstance(response.in_progress, list)
        assert isinstance(response.done, list)


class TestAgentSchemas:
    """Tests for agent-related schemas."""

    @pytest.mark.unit
    def test_agent_start_request(self):
        """Test AgentStartRequest schema."""
        request = AgentStartRequest(
            instruction="Start working on features",
            yolo_mode=False
        )
        assert request.instruction == "Start working on features"
        assert request.yolo_mode is False

    @pytest.mark.unit
    def test_agent_start_request_defaults(self):
        """Test AgentStartRequest default values."""
        request = AgentStartRequest()
        assert request.instruction is None
        assert request.yolo_mode is False

    @pytest.mark.unit
    def test_agent_status(self):
        """Test AgentStatus schema."""
        status = AgentStatus(
            status="running",
            container_name="zerocoder-test-1",
            started_at=datetime.now(),
            idle_seconds=0,
            agent_running=True,
            graceful_stop_requested=False
        )
        assert status.status == "running"
        assert status.agent_running is True

    @pytest.mark.unit
    def test_agent_status_valid_statuses(self):
        """Test AgentStatus with all valid status values."""
        valid_statuses = ["not_created", "stopped", "running", "paused", "crashed", "completed"]
        for status_val in valid_statuses:
            status = AgentStatus(status=status_val)
            assert status.status == status_val

    @pytest.mark.unit
    def test_agent_action_response(self):
        """Test AgentActionResponse schema."""
        response = AgentActionResponse(
            success=True,
            status="running",
            message="Agent started successfully"
        )
        assert response.success is True
        assert response.message == "Agent started successfully"


class TestWizardSchemas:
    """Tests for wizard-related schemas."""

    @pytest.mark.unit
    def test_wizard_status_message(self):
        """Test WizardStatusMessage schema."""
        msg = WizardStatusMessage(
            role="user",
            content="Hello",
            timestamp=datetime.now()
        )
        assert msg.role == "user"
        assert msg.content == "Hello"

    @pytest.mark.unit
    def test_wizard_status_message_valid_roles(self):
        """Test WizardStatusMessage with valid roles."""
        for role in ["user", "assistant"]:
            msg = WizardStatusMessage(
                role=role,
                content="Content",
                timestamp=datetime.now()
            )
            assert msg.role == role

    @pytest.mark.unit
    def test_wizard_status(self):
        """Test WizardStatus schema."""
        status = WizardStatus(
            step="chat",
            spec_method="claude",
            started_at=datetime.now(),
            chat_messages=[]
        )
        assert status.step == "chat"
        assert status.spec_method == "claude"

    @pytest.mark.unit
    def test_wizard_status_valid_steps(self):
        """Test WizardStatus with valid steps."""
        for step in ["mode", "details", "method", "chat"]:
            status = WizardStatus(
                step=step,
                started_at=datetime.now()
            )
            assert status.step == step


class TestAttachmentSchemas:
    """Tests for file attachment schemas."""

    @pytest.mark.unit
    def test_image_attachment_valid(self):
        """Test valid ImageAttachment."""
        # Create valid base64 data for a small image
        small_data = b"x" * 100
        b64_data = base64.b64encode(small_data).decode()

        attachment = ImageAttachment(
            filename="test.png",
            mimeType="image/png",
            base64Data=b64_data
        )
        assert attachment.filename == "test.png"
        assert attachment.mimeType == "image/png"

    @pytest.mark.unit
    def test_image_attachment_size_limit(self):
        """Test ImageAttachment size validation."""
        # Create data larger than MAX_IMAGE_SIZE
        large_data = b"x" * (MAX_IMAGE_SIZE + 1)
        b64_data = base64.b64encode(large_data).decode()

        with pytest.raises(ValidationError) as exc_info:
            ImageAttachment(
                filename="large.png",
                mimeType="image/png",
                base64Data=b64_data
            )
        assert "Image size" in str(exc_info.value)

    @pytest.mark.unit
    def test_image_attachment_invalid_base64(self):
        """Test ImageAttachment with invalid base64."""
        with pytest.raises(ValidationError):
            ImageAttachment(
                filename="test.png",
                mimeType="image/png",
                base64Data="not-valid-base64!!!"
            )

    @pytest.mark.unit
    def test_text_attachment_valid(self):
        """Test valid TextAttachment."""
        attachment = TextAttachment(
            filename="test.txt",
            mimeType="text/plain",
            textContent="Hello, World!"
        )
        assert attachment.filename == "test.txt"
        assert attachment.textContent == "Hello, World!"

    @pytest.mark.unit
    def test_text_attachment_size_limit(self):
        """Test TextAttachment size validation."""
        # Create content larger than MAX_TEXT_SIZE
        large_content = "x" * (MAX_TEXT_SIZE + 1)

        with pytest.raises(ValidationError) as exc_info:
            TextAttachment(
                filename="large.txt",
                mimeType="text/plain",
                textContent=large_content
            )
        assert "Text file size" in str(exc_info.value)

    @pytest.mark.unit
    def test_text_attachment_valid_mime_types(self):
        """Test TextAttachment with valid MIME types."""
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
                textContent="content"
            )
            assert attachment.mimeType == mime_type


class TestTaskSchemas:
    """Tests for task (edit mode) schemas."""

    @pytest.mark.unit
    def test_task_create(self):
        """Test TaskCreate schema."""
        task = TaskCreate(
            title="Implement feature",
            description="Detailed description",
            priority=1,
            task_type="feature"
        )
        assert task.title == "Implement feature"
        assert task.priority == 1
        assert task.task_type == "feature"

    @pytest.mark.unit
    def test_task_create_defaults(self):
        """Test TaskCreate default values."""
        task = TaskCreate(title="Test task")
        assert task.description == ""
        assert task.priority == 2
        assert task.task_type == "feature"

    @pytest.mark.unit
    def test_task_create_title_constraints(self):
        """Test TaskCreate title constraints."""
        # Too short
        with pytest.raises(ValidationError):
            TaskCreate(title="")

        # Too long
        with pytest.raises(ValidationError):
            TaskCreate(title="a" * 201)

    @pytest.mark.unit
    def test_task_create_priority_constraints(self):
        """Test TaskCreate priority constraints."""
        # Valid range
        for priority in [0, 1, 2, 3, 4]:
            task = TaskCreate(title="Test", priority=priority)
            assert task.priority == priority

        # Invalid
        with pytest.raises(ValidationError):
            TaskCreate(title="Test", priority=-1)

        with pytest.raises(ValidationError):
            TaskCreate(title="Test", priority=5)

    @pytest.mark.unit
    def test_task_create_valid_types(self):
        """Test TaskCreate with valid task types."""
        for task_type in ["feature", "task", "bug"]:
            task = TaskCreate(title="Test", task_type=task_type)
            assert task.task_type == task_type

    @pytest.mark.unit
    def test_task_update(self):
        """Test TaskUpdate schema."""
        update = TaskUpdate(status="in_progress", priority=0)
        assert update.status == "in_progress"
        assert update.priority == 0

    @pytest.mark.unit
    def test_task_update_valid_statuses(self):
        """Test TaskUpdate with valid status values."""
        for status in ["open", "in_progress", "closed"]:
            update = TaskUpdate(status=status)
            assert update.status == status


class TestWebSocketSchemas:
    """Tests for WebSocket message schemas."""

    @pytest.mark.unit
    def test_ws_progress_message(self):
        """Test WSProgressMessage schema."""
        msg = WSProgressMessage(
            passing=5,
            total=10,
            percentage=50.0
        )
        assert msg.type == "progress"
        assert msg.passing == 5

    @pytest.mark.unit
    def test_ws_feature_update_message(self):
        """Test WSFeatureUpdateMessage schema."""
        msg = WSFeatureUpdateMessage(
            feature_id="feat-1",
            passes=True
        )
        assert msg.type == "feature_update"
        assert msg.passes is True

    @pytest.mark.unit
    def test_ws_log_message(self):
        """Test WSLogMessage schema."""
        msg = WSLogMessage(
            line="Agent started",
            timestamp=datetime.now()
        )
        assert msg.type == "log"
        assert msg.line == "Agent started"

    @pytest.mark.unit
    def test_ws_agent_status_message(self):
        """Test WSAgentStatusMessage schema."""
        msg = WSAgentStatusMessage(status="running")
        assert msg.type == "agent_status"
        assert msg.status == "running"


class TestSetupStatus:
    """Tests for setup status schema."""

    @pytest.mark.unit
    def test_setup_status(self):
        """Test SetupStatus schema."""
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
    def test_setup_status_partial(self):
        """Test SetupStatus with partial setup."""
        status = SetupStatus(
            claude_cli=True,
            credentials=False,
            node=True,
            npm=False
        )
        assert status.credentials is False
        assert status.npm is False
