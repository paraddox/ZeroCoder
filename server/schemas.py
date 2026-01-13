"""
Pydantic Schemas
================

Request/Response models for the API endpoints.
"""

import base64
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ============================================================================
# Project Schemas
# ============================================================================

class ProjectCreate(BaseModel):
    """Request schema for creating a new project."""
    name: str = Field(..., min_length=1, max_length=50, pattern=r'^[a-zA-Z0-9_-]+$')
    path: str = Field(..., min_length=1, description="Absolute path to project directory")
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
    path: str
    has_spec: bool
    wizard_incomplete: bool = False
    stats: ProjectStats
    agent_status: str | None = None
    agent_running: bool | None = None


class ProjectDetail(BaseModel):
    """Detailed project information."""
    name: str
    path: str
    has_spec: bool
    stats: ProjectStats
    prompts_dir: str


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
    source_type: Literal["git_url", "local_folder"]
    git_url: str | None = None
    path: str = Field(..., min_length=1, description="Destination for clone, or existing folder path")

    @model_validator(mode='after')
    def validate_git_url(self):
        """Ensure git_url is provided when source_type is git_url."""
        if self.source_type == "git_url" and not self.git_url:
            raise ValueError("git_url is required when source_type is git_url")
        return self


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
# Filesystem Schemas
# ============================================================================

class DriveInfo(BaseModel):
    """Information about a drive (Windows only)."""
    letter: str
    label: str
    available: bool = True


class DirectoryEntry(BaseModel):
    """An entry in a directory listing."""
    name: str
    path: str  # POSIX format
    is_directory: bool
    is_hidden: bool = False
    size: int | None = None  # Bytes, for files
    has_children: bool = False  # True if directory has subdirectories


class DirectoryListResponse(BaseModel):
    """Response for directory listing."""
    current_path: str  # POSIX format
    parent_path: str | None
    entries: list[DirectoryEntry]
    drives: list[DriveInfo] | None = None  # Windows only


class PathValidationResponse(BaseModel):
    """Response for path validation."""
    valid: bool
    exists: bool
    is_directory: bool
    can_read: bool
    can_write: bool
    message: str = ""


class CreateDirectoryRequest(BaseModel):
    """Request to create a new directory."""
    parent_path: str
    name: str = Field(..., min_length=1, max_length=255)
