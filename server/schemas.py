"""
Pydantic Schemas
================

Request/Response models for the API endpoints.
"""

import base64
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ============================================================================
# Project Schemas
# ============================================================================

class ProjectCreate(BaseModel):
    """Request schema for creating a new project."""
    name: str = Field(..., min_length=1, max_length=50, pattern=r'^[a-zA-Z0-9_-]+$')
    git_url: str = Field(..., min_length=1, description="Git repository URL (https:// or git@)")
    is_new: bool = Field(default=True, description="True if this is a new project needing wizard setup")
    spec_method: Literal["claude", "manual"] = "claude"


class ProjectStats(BaseModel):
    """Project statistics."""
    passing: int = 0
    in_progress: int = 0
    total: int = 0
    percentage: float = 0.0


class ProjectSummary(BaseModel):
    """Summary of a project for list view."""
    name: str
    git_url: str
    local_path: str
    is_new: bool = True
    has_spec: bool
    wizard_incomplete: bool = False
    stats: ProjectStats
    target_container_count: int = 1
    agent_status: str | None = None
    agent_running: bool | None = None
    agent_model: str | None = None  # Model for coder/overseer agents


class ProjectDetail(BaseModel):
    """Detailed project information."""
    name: str
    git_url: str
    local_path: str
    is_new: bool = True
    has_spec: bool
    stats: ProjectStats
    prompts_dir: str
    target_container_count: int = 1
    agent_model: str | None = None  # Model for coder/overseer agents


class ProjectSettingsUpdate(BaseModel):
    """Request schema for updating project settings."""
    agent_model: str = Field(..., description="Model ID for coder/overseer agents")


class ProjectPrompts(BaseModel):
    """Project prompt files content."""
    app_spec: str = ""
    initializer_prompt: str = ""
    coding_prompt: str = ""


class ProjectPromptsUpdate(BaseModel):
    """Request schema for updating project prompts."""
    app_spec: str | None = None
    initializer_prompt: str | None = None
    coding_prompt: str | None = None


class WizardStatusMessage(BaseModel):
    """A chat message stored in wizard status."""
    role: Literal["user", "assistant"]
    content: str
    timestamp: datetime


class WizardStatus(BaseModel):
    """Wizard state for resuming interrupted project setup."""
    step: Literal["name", "folder", "method", "chat"]
    spec_method: Literal["claude", "manual"] | None = None
    started_at: datetime
    chat_messages: list[WizardStatusMessage] = []


class AddExistingRepoRequest(BaseModel):
    """Request schema for adding an existing repository."""
    name: str = Field(..., min_length=1, max_length=50, pattern=r'^[a-zA-Z0-9_-]+$')
    git_url: str = Field(..., min_length=1, description="Git repository URL (https:// or git@)")


class ContainerCountUpdate(BaseModel):
    """Request to update target container count."""
    target_count: int = Field(..., ge=1, le=10)


# ============================================================================
# Container Schemas
# ============================================================================

class ContainerStatus(BaseModel):
    """Container instance status."""
    id: int
    container_number: int
    container_type: Literal["init", "coding"]
    status: Literal["created", "running", "stopping", "stopped"]
    current_feature: str | None = None
    docker_container_id: str | None = None


# ============================================================================
# Feature Schemas
# ============================================================================

class FeatureBase(BaseModel):
    """Base feature attributes."""
    category: str
    name: str
    description: str
    steps: list[str]


class FeatureCreate(FeatureBase):
    """Request schema for creating a new feature."""
    priority: int | None = None


class FeatureUpdate(BaseModel):
    """Request schema for updating a feature."""
    name: str | None = None
    description: str | None = None
    category: str | None = None
    priority: int | None = None
    steps: list[str] | None = None


class FeatureResponse(FeatureBase):
    """Response schema for a feature."""
    id: str  # beads uses string IDs like "feat-1"
    priority: int
    passes: bool
    in_progress: bool

    class Config:
        from_attributes = True


class FeatureListResponse(BaseModel):
    """Response containing list of features organized by status."""
    pending: list[FeatureResponse]
    in_progress: list[FeatureResponse]
    done: list[FeatureResponse]


# ============================================================================
# Agent Schemas
# ============================================================================

class AgentStartRequest(BaseModel):
    """Request schema for starting the agent."""
    instruction: str | None = None  # Instruction to send to Claude Code
    yolo_mode: bool = False  # Kept for backwards compatibility


class AgentStatus(BaseModel):
    """Current agent/container status."""
    status: Literal["not_created", "stopped", "running", "paused", "crashed", "completed"]
    container_name: str | None = None
    started_at: datetime | None = None
    idle_seconds: int = 0
    agent_running: bool = False  # True if agent process is running inside container
    graceful_stop_requested: bool = False  # True if graceful stop has been requested
    # Legacy fields for backwards compatibility
    pid: int | None = None
    yolo_mode: bool = False


class AgentActionResponse(BaseModel):
    """Response for agent control actions."""
    success: bool
    status: str
    message: str = ""


# ============================================================================
# Setup Schemas
# ============================================================================

class SetupStatus(BaseModel):
    """System setup status."""
    claude_cli: bool
    credentials: bool
    node: bool
    npm: bool


# ============================================================================
# WebSocket Message Schemas
# ============================================================================

class WSProgressMessage(BaseModel):
    """WebSocket message for progress updates."""
    type: Literal["progress"] = "progress"
    passing: int
    total: int
    percentage: float


class WSFeatureUpdateMessage(BaseModel):
    """WebSocket message for feature status updates."""
    type: Literal["feature_update"] = "feature_update"
    feature_id: str  # beads uses string IDs
    passes: bool


class WSLogMessage(BaseModel):
    """WebSocket message for agent log output."""
    type: Literal["log"] = "log"
    line: str
    timestamp: datetime


class WSAgentStatusMessage(BaseModel):
    """WebSocket message for agent status changes."""
    type: Literal["agent_status"] = "agent_status"
    status: str


# ============================================================================
# Spec Chat Schemas
# ============================================================================

# Maximum file sizes
MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5 MB for images
MAX_TEXT_SIZE = 1 * 1024 * 1024   # 1 MB for text files

# Supported MIME types
IMAGE_MIME_TYPES = Literal['image/jpeg', 'image/png']
TEXT_MIME_TYPES = Literal[
    'text/plain', 'text/markdown', 'text/csv', 'application/json',
    'text/html', 'text/css', 'text/javascript', 'application/xml'
]


class ImageAttachment(BaseModel):
    """Image attachment from client for spec creation chat."""
    filename: str = Field(..., min_length=1, max_length=255)
    mimeType: IMAGE_MIME_TYPES
    base64Data: str
    isText: Literal[False] = False

    @field_validator('base64Data')
    @classmethod
    def validate_base64_and_size(cls, v: str) -> str:
        """Validate that base64 data is valid and within size limit."""
        try:
            decoded = base64.b64decode(v)
            if len(decoded) > MAX_IMAGE_SIZE:
                raise ValueError(
                    f'Image size ({len(decoded) / (1024 * 1024):.1f} MB) exceeds '
                    f'maximum of {MAX_IMAGE_SIZE // (1024 * 1024)} MB'
                )
            return v
        except Exception as e:
            if 'Image size' in str(e):
                raise
            raise ValueError(f'Invalid base64 data: {e}')


class TextAttachment(BaseModel):
    """Text file attachment from client for spec creation chat."""
    filename: str = Field(..., min_length=1, max_length=255)
    mimeType: TEXT_MIME_TYPES
    textContent: str
    isText: Literal[True] = True

    @field_validator('textContent')
    @classmethod
    def validate_text_size(cls, v: str) -> str:
        """Validate that text content is within size limit."""
        size = len(v.encode('utf-8'))
        if size > MAX_TEXT_SIZE:
            raise ValueError(
                f'Text file size ({size / (1024 * 1024):.1f} MB) exceeds '
                f'maximum of {MAX_TEXT_SIZE // (1024 * 1024)} MB'
            )
        return v


# Union type for any attachment
FileAttachment = ImageAttachment | TextAttachment


# ============================================================================
# Task Schemas (Edit Mode)
# ============================================================================

class TaskCreate(BaseModel):
    """Request schema for creating a task in edit mode."""
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    priority: int = Field(default=2, ge=0, le=4)
    task_type: str = Field(default="feature", pattern=r'^(feature|task|bug)$')


class TaskUpdate(BaseModel):
    """Request schema for updating a task in edit mode."""
    status: str | None = Field(default=None, pattern=r'^(open|in_progress|closed)$')
    priority: int | None = Field(default=None, ge=0, le=4)
    title: str | None = Field(default=None, min_length=1, max_length=200)
