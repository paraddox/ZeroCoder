"""
Schema Validation Unit Tests
============================

Comprehensive tests for Pydantic schema validation including:
- Field validation
- Type coercion
- Default values
- Custom validators
- Edge cases
"""

import pytest
from datetime import datetime
from pathlib import Path
from pydantic import ValidationError

import sys
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
)


class TestProjectCreate:
    """Tests for ProjectCreate schema validation."""

    @pytest.mark.unit
    def test_valid_project_create(self):
        """Test valid project creation."""
        project = ProjectCreate(
            name="my-project",
            git_url="https://github.com/user/repo.git",
            is_new=True,
            spec_method="claude",
        )
        assert project.name == "my-project"
        assert project.is_new is True

    @pytest.mark.unit
    def test_project_name_validation_pattern(self):
        """Test project name pattern validation."""
        # Valid names
        valid_names = ["project", "my-project", "my_project", "Project123"]
        for name in valid_names:
            project = ProjectCreate(
                name=name,
                git_url="https://github.com/user/repo.git"
            )
            assert project.name == name

    @pytest.mark.unit
    def test_project_name_invalid_pattern(self):
        """Test project name rejects invalid patterns."""
        invalid_names = [
            "project with spaces",
            "project/slash",
            "project.dot",
            "project@special",
        ]
        for name in invalid_names:
            with pytest.raises(ValidationError):
                ProjectCreate(
                    name=name,
                    git_url="https://github.com/user/repo.git"
                )

    @pytest.mark.unit
    def test_project_name_length_validation(self):
        """Test project name length constraints."""
        # Empty name
        with pytest.raises(ValidationError):
            ProjectCreate(name="", git_url="https://github.com/user/repo.git")

        # Too long (>50 chars)
        with pytest.raises(ValidationError):
            ProjectCreate(
                name="a" * 51,
                git_url="https://github.com/user/repo.git"
            )

        # Exactly 50 chars should work
        project = ProjectCreate(
            name="a" * 50,
            git_url="https://github.com/user/repo.git"
        )
        assert len(project.name) == 50

    @pytest.mark.unit
    def test_git_url_required(self):
        """Test that git_url is required."""
        with pytest.raises(ValidationError):
            ProjectCreate(name="project")

    @pytest.mark.unit
    def test_spec_method_literal(self):
        """Test spec_method only accepts valid values."""
        # Valid values
        for method in ["claude", "manual"]:
            project = ProjectCreate(
                name="project",
                git_url="https://github.com/user/repo.git",
                spec_method=method,
            )
            assert project.spec_method == method

        # Invalid value
        with pytest.raises(ValidationError):
            ProjectCreate(
                name="project",
                git_url="https://github.com/user/repo.git",
                spec_method="invalid",
            )

    @pytest.mark.unit
    def test_default_values(self):
        """Test default values."""
        project = ProjectCreate(
            name="project",
            git_url="https://github.com/user/repo.git",
        )
        assert project.is_new is True
        assert project.spec_method == "claude"


class TestProjectStats:
    """Tests for ProjectStats schema."""

    @pytest.mark.unit
    def test_default_values(self):
        """Test default values."""
        stats = ProjectStats()
        assert stats.passing == 0
        assert stats.in_progress == 0
        assert stats.total == 0
        assert stats.percentage == 0.0

    @pytest.mark.unit
    def test_valid_stats(self):
        """Test valid stats creation."""
        stats = ProjectStats(
            passing=5,
            in_progress=3,
            total=10,
            percentage=50.0,
        )
        assert stats.passing == 5
        assert stats.percentage == 50.0

    @pytest.mark.unit
    def test_percentage_precision(self):
        """Test percentage can handle float precision."""
        stats = ProjectStats(percentage=33.333333)
        assert abs(stats.percentage - 33.333333) < 0.0001


class TestProjectSummary:
    """Tests for ProjectSummary schema."""

    @pytest.mark.unit
    def test_valid_summary(self):
        """Test valid project summary."""
        summary = ProjectSummary(
            name="test-project",
            git_url="https://github.com/user/repo.git",
            local_path="/path/to/project",
            has_spec=True,
            stats=ProjectStats(),
        )
        assert summary.name == "test-project"
        assert summary.has_spec is True

    @pytest.mark.unit
    def test_optional_fields(self):
        """Test optional fields have defaults."""
        summary = ProjectSummary(
            name="test",
            git_url="https://github.com/user/repo.git",
            local_path="/path",
            has_spec=False,
            stats=ProjectStats(),
        )
        assert summary.is_new is True
        assert summary.wizard_incomplete is False
        assert summary.target_container_count == 1
        assert summary.agent_status is None
        assert summary.agent_running is None


class TestContainerCountUpdate:
    """Tests for ContainerCountUpdate schema."""

    @pytest.mark.unit
    def test_valid_counts(self):
        """Test valid container counts."""
        for count in [1, 5, 10]:
            update = ContainerCountUpdate(target_count=count)
            assert update.target_count == count

    @pytest.mark.unit
    def test_count_too_low(self):
        """Test count below minimum."""
        with pytest.raises(ValidationError):
            ContainerCountUpdate(target_count=0)

    @pytest.mark.unit
    def test_count_too_high(self):
        """Test count above maximum."""
        with pytest.raises(ValidationError):
            ContainerCountUpdate(target_count=11)


class TestContainerStatus:
    """Tests for ContainerStatus schema."""

    @pytest.mark.unit
    def test_valid_status_values(self):
        """Test valid status values."""
        valid_statuses = ["not_created", "created", "running", "stopping", "stopped", "completed"]
        for status in valid_statuses:
            container = ContainerStatus(
                id=1,
                container_number=1,
                container_type="coding",
                status=status,
            )
            assert container.status == status

    @pytest.mark.unit
    def test_container_type_literal(self):
        """Test container_type only accepts valid values."""
        for ctype in ["init", "coding"]:
            container = ContainerStatus(
                id=1,
                container_number=1,
                container_type=ctype,
                status="running",
            )
            assert container.container_type == ctype

        with pytest.raises(ValidationError):
            ContainerStatus(
                id=1,
                container_number=1,
                container_type="invalid",
                status="running",
            )

    @pytest.mark.unit
    def test_agent_type_literal(self):
        """Test agent_type only accepts valid values."""
        valid_types = ["coder", "overseer", "hound", "initializer", None]
        for atype in valid_types:
            container = ContainerStatus(
                id=1,
                container_number=1,
                container_type="coding",
                status="running",
                agent_type=atype,
            )
            assert container.agent_type == atype


class TestFeatureSchemas:
    """Tests for feature-related schemas."""

    @pytest.mark.unit
    def test_feature_base(self):
        """Test FeatureBase schema."""
        feature = FeatureBase(
            category="auth",
            name="Login",
            description="User login feature",
            steps=["Step 1", "Step 2"],
        )
        assert feature.category == "auth"
        assert len(feature.steps) == 2

    @pytest.mark.unit
    def test_feature_create_optional_priority(self):
        """Test FeatureCreate with optional priority."""
        # Without priority
        feature = FeatureCreate(
            category="auth",
            name="Login",
            description="Login",
            steps=[],
        )
        assert feature.priority is None

        # With priority
        feature = FeatureCreate(
            category="auth",
            name="Login",
            description="Login",
            steps=[],
            priority=1,
        )
        assert feature.priority == 1

    @pytest.mark.unit
    def test_feature_update_all_optional(self):
        """Test FeatureUpdate allows all fields to be optional."""
        # Empty update
        update = FeatureUpdate()
        assert update.name is None
        assert update.priority is None

        # Partial update
        update = FeatureUpdate(name="New Name")
        assert update.name == "New Name"
        assert update.description is None

    @pytest.mark.unit
    def test_feature_response(self):
        """Test FeatureResponse schema."""
        response = FeatureResponse(
            id="feat-1",
            priority=1,
            category="auth",
            name="Login",
            description="Login feature",
            steps=["Step 1"],
            passes=True,
            in_progress=False,
        )
        assert response.id == "feat-1"
        assert response.passes is True

    @pytest.mark.unit
    def test_feature_list_response(self):
        """Test FeatureListResponse schema."""
        pending = FeatureResponse(
            id="feat-1", priority=1, category="", name="Test",
            description="", steps=[], passes=False, in_progress=False,
        )
        in_prog = FeatureResponse(
            id="feat-2", priority=2, category="", name="Test2",
            description="", steps=[], passes=False, in_progress=True,
        )
        done = FeatureResponse(
            id="feat-3", priority=3, category="", name="Test3",
            description="", steps=[], passes=True, in_progress=False,
        )

        response = FeatureListResponse(
            pending=[pending],
            in_progress=[in_prog],
            done=[done],
        )
        assert len(response.pending) == 1
        assert len(response.in_progress) == 1
        assert len(response.done) == 1


class TestAgentSchemas:
    """Tests for agent-related schemas."""

    @pytest.mark.unit
    def test_agent_start_request_defaults(self):
        """Test AgentStartRequest default values."""
        request = AgentStartRequest()
        assert request.instruction is None
        assert request.yolo_mode is False

    @pytest.mark.unit
    def test_agent_start_request_with_instruction(self):
        """Test AgentStartRequest with custom instruction."""
        request = AgentStartRequest(
            instruction="Custom instruction",
            yolo_mode=True,
        )
        assert request.instruction == "Custom instruction"
        assert request.yolo_mode is True

    @pytest.mark.unit
    def test_agent_status_valid_values(self):
        """Test AgentStatus with valid status values."""
        valid_statuses = ["not_created", "stopped", "running", "paused", "crashed", "completed"]
        for status in valid_statuses:
            agent = AgentStatus(status=status)
            assert agent.status == status

    @pytest.mark.unit
    def test_agent_status_optional_fields(self):
        """Test AgentStatus optional fields."""
        status = AgentStatus(status="running")
        assert status.container_name is None
        assert status.started_at is None
        assert status.idle_seconds == 0
        assert status.agent_running is False

    @pytest.mark.unit
    def test_agent_status_with_datetime(self):
        """Test AgentStatus with datetime."""
        now = datetime.now()
        status = AgentStatus(
            status="running",
            started_at=now,
        )
        assert status.started_at == now

    @pytest.mark.unit
    def test_agent_action_response(self):
        """Test AgentActionResponse schema."""
        response = AgentActionResponse(
            success=True,
            status="running",
            message="Agent started successfully",
        )
        assert response.success is True
        assert response.message == "Agent started successfully"

    @pytest.mark.unit
    def test_agent_action_response_defaults(self):
        """Test AgentActionResponse default message."""
        response = AgentActionResponse(
            success=False,
            status="error",
        )
        assert response.message == ""


class TestWizardSchemas:
    """Tests for wizard-related schemas."""

    @pytest.mark.unit
    def test_wizard_status_message(self):
        """Test WizardStatusMessage schema."""
        now = datetime.now()
        message = WizardStatusMessage(
            role="user",
            content="Hello",
            timestamp=now,
        )
        assert message.role == "user"
        assert message.timestamp == now

    @pytest.mark.unit
    def test_wizard_status_message_role_literal(self):
        """Test role only accepts user/assistant."""
        for role in ["user", "assistant"]:
            message = WizardStatusMessage(
                role=role,
                content="Test",
                timestamp=datetime.now(),
            )
            assert message.role == role

        with pytest.raises(ValidationError):
            WizardStatusMessage(
                role="system",
                content="Test",
                timestamp=datetime.now(),
            )

    @pytest.mark.unit
    def test_wizard_status(self):
        """Test WizardStatus schema."""
        now = datetime.now()
        status = WizardStatus(
            step="chat",
            spec_method="claude",
            started_at=now,
            chat_messages=[],
        )
        assert status.step == "chat"
        assert status.spec_method == "claude"

    @pytest.mark.unit
    def test_wizard_status_step_literal(self):
        """Test step only accepts valid values."""
        valid_steps = ["mode", "details", "method", "chat"]
        for step in valid_steps:
            status = WizardStatus(
                step=step,
                started_at=datetime.now(),
            )
            assert status.step == step


class TestAddExistingRepoRequest:
    """Tests for AddExistingRepoRequest schema."""

    @pytest.mark.unit
    def test_valid_request(self):
        """Test valid request."""
        request = AddExistingRepoRequest(
            name="existing-repo",
            git_url="https://github.com/user/repo.git",
        )
        assert request.name == "existing-repo"
        assert request.git_url == "https://github.com/user/repo.git"

    @pytest.mark.unit
    def test_name_pattern_validation(self):
        """Test name pattern validation."""
        with pytest.raises(ValidationError):
            AddExistingRepoRequest(
                name="invalid name",
                git_url="https://github.com/user/repo.git",
            )


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.unit
    def test_empty_steps_list(self):
        """Test feature with empty steps list."""
        feature = FeatureCreate(
            category="test",
            name="Test",
            description="Test",
            steps=[],
        )
        assert feature.steps == []

    @pytest.mark.unit
    def test_unicode_in_strings(self):
        """Test unicode characters in string fields."""
        feature = FeatureCreate(
            category="i18n",
            name="Feature with unicode: \u00e9\u00e8\u00ea",
            description="Description with emoji: \ud83d\ude80",
            steps=["Step with CJK: \u4e2d\u6587"],
        )
        assert "\u00e9" in feature.name
        assert "\ud83d\ude80" in feature.description

    @pytest.mark.unit
    def test_long_description(self):
        """Test very long description."""
        long_desc = "A" * 10000
        feature = FeatureCreate(
            category="test",
            name="Test",
            description=long_desc,
            steps=[],
        )
        assert len(feature.description) == 10000

    @pytest.mark.unit
    def test_many_steps(self):
        """Test feature with many steps."""
        steps = [f"Step {i}" for i in range(100)]
        feature = FeatureCreate(
            category="test",
            name="Test",
            description="Test",
            steps=steps,
        )
        assert len(feature.steps) == 100
