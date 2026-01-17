"""
Comprehensive API Router Tests
==============================

Enterprise-grade tests for API endpoint validation, error handling,
and response format verification via schema testing.
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Schema Validation Tests for API Requests
# =============================================================================

class TestProjectCreateRequestValidation:
    """Tests for project creation request validation."""

    @pytest.mark.unit
    def test_valid_project_create_request(self):
        """Test valid project creation request."""
        from server.schemas import ProjectCreate

        request = ProjectCreate(
            name="test-project",
            git_url="https://github.com/user/repo.git",
            is_new=True,
            spec_method="claude"
        )

        assert request.name == "test-project"
        assert request.git_url == "https://github.com/user/repo.git"

    @pytest.mark.unit
    def test_invalid_project_name_validation(self):
        """Test that invalid project names are rejected."""
        from server.schemas import ProjectCreate

        invalid_names = [
            "",  # Empty
            "a" * 51,  # Too long
            "project name",  # Contains space
            "project/name",  # Contains slash
            "project@name",  # Contains @
        ]

        for name in invalid_names:
            with pytest.raises(ValidationError):
                ProjectCreate(
                    name=name,
                    git_url="https://github.com/user/repo.git"
                )

    @pytest.mark.unit
    def test_valid_project_names(self):
        """Test that valid project names are accepted."""
        from server.schemas import ProjectCreate

        valid_names = [
            "project",
            "my-project",
            "my_project",
            "MyProject123",
            "a",
            "a" * 50,
        ]

        for name in valid_names:
            request = ProjectCreate(
                name=name,
                git_url="https://github.com/user/repo.git"
            )
            assert request.name == name


class TestFeatureCreateRequestValidation:
    """Tests for feature creation request validation."""

    @pytest.mark.unit
    def test_valid_feature_create(self):
        """Test valid feature creation request."""
        from server.schemas import FeatureCreate

        request = FeatureCreate(
            category="authentication",
            name="User Login",
            description="Implement user login",
            steps=["Create form", "Add validation"],
            priority=1
        )

        assert request.category == "authentication"
        assert request.name == "User Login"
        assert len(request.steps) == 2

    @pytest.mark.unit
    def test_feature_create_optional_priority(self):
        """Test that priority is optional."""
        from server.schemas import FeatureCreate

        request = FeatureCreate(
            category="test",
            name="Test",
            description="Test",
            steps=["Step 1"]
        )

        assert request.priority is None


class TestFeatureUpdateRequestValidation:
    """Tests for feature update request validation."""

    @pytest.mark.unit
    def test_partial_update_allowed(self):
        """Test that partial updates are allowed."""
        from server.schemas import FeatureUpdate

        # Only name
        request = FeatureUpdate(name="New Name")
        assert request.name == "New Name"
        assert request.description is None

    @pytest.mark.unit
    def test_all_fields_optional(self):
        """Test that all fields are optional."""
        from server.schemas import FeatureUpdate

        request = FeatureUpdate()
        assert request.name is None
        assert request.description is None
        assert request.priority is None


# =============================================================================
# Agent Request Validation Tests
# =============================================================================

class TestAgentRequestValidation:
    """Tests for agent-related request validation."""

    @pytest.mark.unit
    def test_agent_start_request_valid(self):
        """Test valid agent start request."""
        from server.schemas import AgentStartRequest

        request = AgentStartRequest(
            instruction="Implement the feature",
            yolo_mode=False
        )

        assert request.instruction == "Implement the feature"
        assert request.yolo_mode is False

    @pytest.mark.unit
    def test_agent_start_request_defaults(self):
        """Test agent start request with defaults."""
        from server.schemas import AgentStartRequest

        request = AgentStartRequest()

        assert request.instruction is None
        assert request.yolo_mode is False


# =============================================================================
# Container Request Validation Tests
# =============================================================================

class TestContainerRequestValidation:
    """Tests for container-related request validation."""

    @pytest.mark.unit
    def test_container_count_valid_range(self):
        """Test valid container count range."""
        from server.schemas import ContainerCountUpdate

        for count in [1, 5, 10]:
            request = ContainerCountUpdate(target_count=count)
            assert request.target_count == count

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


# =============================================================================
# Task Schema Validation Tests
# =============================================================================

class TestTaskRequestValidation:
    """Tests for task-related request validation."""

    @pytest.mark.unit
    def test_task_create_valid(self):
        """Test valid task creation."""
        from server.schemas import TaskCreate

        request = TaskCreate(
            title="Implement feature",
            description="Full description",
            priority=2,
            task_type="feature"
        )

        assert request.title == "Implement feature"
        assert request.priority == 2

    @pytest.mark.unit
    def test_task_create_title_validation(self):
        """Test task title validation."""
        from server.schemas import TaskCreate

        # Empty title
        with pytest.raises(ValidationError):
            TaskCreate(title="")

        # Too long
        with pytest.raises(ValidationError):
            TaskCreate(title="x" * 201)

    @pytest.mark.unit
    def test_task_create_priority_validation(self):
        """Test task priority validation."""
        from server.schemas import TaskCreate

        # Invalid priority
        with pytest.raises(ValidationError):
            TaskCreate(title="Test", priority=-1)

        with pytest.raises(ValidationError):
            TaskCreate(title="Test", priority=5)

    @pytest.mark.unit
    def test_task_create_type_validation(self):
        """Test task type validation."""
        from server.schemas import TaskCreate

        valid_types = ["feature", "task", "bug"]
        for task_type in valid_types:
            request = TaskCreate(title="Test", task_type=task_type)
            assert request.task_type == task_type

        with pytest.raises(ValidationError):
            TaskCreate(title="Test", task_type="invalid")

    @pytest.mark.unit
    def test_task_update_status_validation(self):
        """Test task status validation in updates."""
        from server.schemas import TaskUpdate

        valid_statuses = ["open", "in_progress", "closed"]
        for status in valid_statuses:
            request = TaskUpdate(status=status)
            assert request.status == status

        with pytest.raises(ValidationError):
            TaskUpdate(status="invalid")


# =============================================================================
# Response Schema Tests
# =============================================================================

class TestResponseSchemas:
    """Tests for response schemas."""

    @pytest.mark.unit
    def test_project_stats_defaults(self):
        """Test project stats with defaults."""
        from server.schemas import ProjectStats

        stats = ProjectStats()

        assert stats.passing == 0
        assert stats.in_progress == 0
        assert stats.total == 0
        assert stats.percentage == 0.0

    @pytest.mark.unit
    def test_project_stats_calculated(self):
        """Test project stats with values."""
        from server.schemas import ProjectStats

        stats = ProjectStats(
            passing=5,
            in_progress=2,
            total=10,
            percentage=50.0
        )

        assert stats.passing == 5
        assert stats.total == 10

    @pytest.mark.unit
    def test_agent_status_response(self):
        """Test agent status response schema."""
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
    def test_agent_action_response(self):
        """Test agent action response schema."""
        from server.schemas import AgentActionResponse

        response = AgentActionResponse(
            success=True,
            status="running",
            message="Container started"
        )

        assert response.success is True
        assert response.status == "running"


# =============================================================================
# WebSocket Message Schema Tests
# =============================================================================

class TestWebSocketMessageSchemas:
    """Tests for WebSocket message schemas."""

    @pytest.mark.unit
    def test_progress_message(self):
        """Test progress message schema."""
        from server.schemas import WSProgressMessage

        msg = WSProgressMessage(
            passing=5,
            total=10,
            percentage=50.0
        )

        assert msg.type == "progress"
        assert msg.passing == 5

    @pytest.mark.unit
    def test_log_message(self):
        """Test log message schema."""
        from server.schemas import WSLogMessage

        msg = WSLogMessage(
            line="Processing feature...",
            timestamp=datetime.now()
        )

        assert msg.type == "log"
        assert "Processing" in msg.line

    @pytest.mark.unit
    def test_feature_update_message(self):
        """Test feature update message schema."""
        from server.schemas import WSFeatureUpdateMessage

        msg = WSFeatureUpdateMessage(
            feature_id="feat-123",
            passes=True
        )

        assert msg.type == "feature_update"
        assert msg.feature_id == "feat-123"

    @pytest.mark.unit
    def test_agent_status_message(self):
        """Test agent status message schema."""
        from server.schemas import WSAgentStatusMessage

        msg = WSAgentStatusMessage(status="running")

        assert msg.type == "agent_status"
        assert msg.status == "running"


# =============================================================================
# Attachment Schema Tests
# =============================================================================

class TestAttachmentSchemas:
    """Tests for attachment schemas."""

    @pytest.mark.unit
    def test_image_attachment_valid(self):
        """Test valid image attachment."""
        from server.schemas import ImageAttachment
        import base64

        data = base64.b64encode(b"fake image data").decode()

        attachment = ImageAttachment(
            filename="test.png",
            mimeType="image/png",
            base64Data=data
        )

        assert attachment.filename == "test.png"
        assert attachment.isText is False

    @pytest.mark.unit
    def test_image_attachment_valid_mimetypes(self):
        """Test valid image MIME types."""
        from server.schemas import ImageAttachment
        import base64

        data = base64.b64encode(b"data").decode()

        for mime in ["image/jpeg", "image/png"]:
            attachment = ImageAttachment(
                filename="test.img",
                mimeType=mime,
                base64Data=data
            )
            assert attachment.mimeType == mime

    @pytest.mark.unit
    def test_text_attachment_valid(self):
        """Test valid text attachment."""
        from server.schemas import TextAttachment

        attachment = TextAttachment(
            filename="readme.md",
            mimeType="text/markdown",
            textContent="# Hello"
        )

        assert attachment.filename == "readme.md"
        assert attachment.isText is True

    @pytest.mark.unit
    def test_text_attachment_valid_mimetypes(self):
        """Test valid text MIME types."""
        from server.schemas import TextAttachment

        valid_mimes = [
            "text/plain",
            "text/markdown",
            "text/csv",
            "application/json",
            "text/html",
            "text/css",
            "text/javascript",
            "application/xml"
        ]

        for mime in valid_mimes:
            attachment = TextAttachment(
                filename="test.txt",
                mimeType=mime,
                textContent="content"
            )
            assert attachment.mimeType == mime


# =============================================================================
# Wizard Status Schema Tests
# =============================================================================

class TestWizardStatusSchemas:
    """Tests for wizard status schemas."""

    @pytest.mark.unit
    def test_wizard_status_valid(self):
        """Test valid wizard status."""
        from server.schemas import WizardStatus

        status = WizardStatus(
            step="chat",
            spec_method="claude",
            started_at=datetime.now()
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
    def test_wizard_status_message(self):
        """Test wizard status message."""
        from server.schemas import WizardStatusMessage

        msg = WizardStatusMessage(
            role="user",
            content="Create a todo app",
            timestamp=datetime.now()
        )

        assert msg.role == "user"
        assert msg.content == "Create a todo app"


# =============================================================================
# Container Status Schema Tests
# =============================================================================

class TestContainerStatusSchemas:
    """Tests for container status schemas."""

    @pytest.mark.unit
    def test_container_status_valid(self):
        """Test valid container status."""
        from server.schemas import ContainerStatus

        status = ContainerStatus(
            id=1,
            container_number=1,
            container_type="coding",
            status="running"
        )

        assert status.id == 1
        assert status.container_type == "coding"

    @pytest.mark.unit
    def test_container_status_values(self):
        """Test valid container status values."""
        from server.schemas import ContainerStatus

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
    def test_container_type_values(self):
        """Test valid container type values."""
        from server.schemas import ContainerStatus

        for container_type in ["init", "coding"]:
            status = ContainerStatus(
                id=1,
                container_number=1,
                container_type=container_type,
                status="running"
            )
            assert status.container_type == container_type


# =============================================================================
# Setup Status Schema Tests
# =============================================================================

class TestSetupStatusSchema:
    """Tests for setup status schema."""

    @pytest.mark.unit
    def test_setup_status_valid(self):
        """Test valid setup status."""
        from server.schemas import SetupStatus

        status = SetupStatus(
            claude_cli=True,
            credentials=True,
            node=True,
            npm=True
        )

        assert status.claude_cli is True
        assert status.npm is True

    @pytest.mark.unit
    def test_setup_status_partial(self):
        """Test setup status with some missing."""
        from server.schemas import SetupStatus

        status = SetupStatus(
            claude_cli=True,
            credentials=False,
            node=True,
            npm=False
        )

        assert status.credentials is False
        assert status.npm is False
