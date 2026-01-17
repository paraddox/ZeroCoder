"""
Pytest Configuration and Fixtures
=================================

Enterprise-grade test fixtures for ZeroCoder test suite.
Provides isolated database, mock services, and test utilities.
"""

import asyncio
import json
import os
import tempfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add project root to path for imports
import sys
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Environment Setup
# =============================================================================

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment variables."""
    original_env = os.environ.copy()

    # Use temp directory for test data
    test_data_dir = tempfile.mkdtemp(prefix="zerocoder_test_")
    os.environ["ZEROCODER_DATA_DIR"] = test_data_dir
    os.environ["ALLOW_EXTERNAL_ACCESS"] = "false"

    yield test_data_dir

    # Cleanup
    os.environ.clear()
    os.environ.update(original_env)
    if Path(test_data_dir).exists():
        shutil.rmtree(test_data_dir, ignore_errors=True)


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / "test_registry.db"


@pytest.fixture
def isolated_registry(temp_db_path: Path, monkeypatch):
    """
    Provide an isolated registry database for testing.

    Patches the registry module to use a fresh database for each test.
    """
    # Reset registry module state
    import registry

    # Store original values
    original_engine = registry._engine
    original_session = registry._SessionLocal

    # Reset module state
    registry._engine = None
    registry._SessionLocal = None

    # Patch get_registry_path to return our temp path
    monkeypatch.setattr(registry, "get_registry_path", lambda: temp_db_path)

    # Also patch the config dir to use a temp directory
    temp_config = temp_db_path.parent / "zerocoder"
    temp_config.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(registry, "get_config_dir", lambda: temp_config)
    monkeypatch.setattr(registry, "get_projects_dir", lambda: temp_config / "projects")
    monkeypatch.setattr(registry, "get_beads_sync_dir", lambda: temp_config / "beads-sync")

    yield registry

    # Restore original state
    registry._engine = original_engine
    registry._SessionLocal = original_session


# =============================================================================
# Project Fixtures
# =============================================================================

@pytest.fixture
def sample_project_data() -> dict:
    """Sample project data for testing."""
    return {
        "name": "test-project",
        "git_url": "https://github.com/example/test-repo.git",
        "is_new": True,
    }


@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory structure."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir(parents=True)

    # Create prompts directory
    prompts_dir = project_dir / "prompts"
    prompts_dir.mkdir()

    # Create .beads directory
    beads_dir = project_dir / ".beads"
    beads_dir.mkdir()

    return project_dir


@pytest.fixture
def sample_app_spec() -> str:
    """Sample app spec content."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<app-spec>
    <name>Test Application</name>
    <description>A test application for unit testing</description>
    <features>
        <feature priority="1">
            <name>User Authentication</name>
            <description>Implement user login and registration</description>
        </feature>
        <feature priority="2">
            <name>Dashboard</name>
            <description>Create main dashboard view</description>
        </feature>
    </features>
</app-spec>
"""


@pytest.fixture
def project_with_prompts(temp_project_dir: Path, sample_app_spec: str) -> Path:
    """Create a project directory with sample prompt files."""
    prompts_dir = temp_project_dir / "prompts"

    (prompts_dir / "app_spec.txt").write_text(sample_app_spec)
    (prompts_dir / "initializer_prompt.md").write_text("# Initializer Prompt\nCreate features from spec.")
    (prompts_dir / "coding_prompt.md").write_text("# Coding Prompt\nImplement features one by one.")

    return temp_project_dir


# =============================================================================
# Beads/Feature Fixtures
# =============================================================================

@pytest.fixture
def sample_beads_issues() -> list[dict]:
    """Sample beads issues/tasks data."""
    return [
        {
            "id": "feat-1",
            "title": "User Authentication",
            "status": "open",
            "priority": 0,
            "labels": ["auth"],
            "description": "1. Create login form\n2. Add validation\n3. Implement API",
            "created_at": "2024-01-01T00:00:00Z",
        },
        {
            "id": "feat-2",
            "title": "Dashboard View",
            "status": "in_progress",
            "priority": 1,
            "labels": ["ui"],
            "description": "Create the main dashboard component",
            "created_at": "2024-01-02T00:00:00Z",
        },
        {
            "id": "feat-3",
            "title": "API Integration",
            "status": "closed",
            "priority": 2,
            "labels": ["backend"],
            "description": "Connect frontend to REST API",
            "created_at": "2024-01-03T00:00:00Z",
        },
    ]


@pytest.fixture
def beads_issues_file(temp_project_dir: Path, sample_beads_issues: list[dict]) -> Path:
    """Create a .beads/issues.jsonl file with sample data."""
    beads_dir = temp_project_dir / ".beads"
    beads_dir.mkdir(exist_ok=True)
    issues_file = beads_dir / "issues.jsonl"

    with open(issues_file, "w") as f:
        for issue in sample_beads_issues:
            f.write(json.dumps(issue) + "\n")

    return issues_file


# =============================================================================
# FastAPI Test Client Fixtures
# =============================================================================

@pytest.fixture
def test_client():
    """Create a FastAPI test client.

    Note: Uses raise_server_exceptions=False to avoid signal handler issues
    in pytest's test runner thread.
    """
    from fastapi.testclient import TestClient
    from server.main import app

    # Disable signal handlers for test environment
    with patch("signal.signal", return_value=None):
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client


@pytest.fixture
async def async_test_client():
    """Create an async FastAPI test client."""
    from httpx import AsyncClient, ASGITransport
    from server.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


# =============================================================================
# Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_docker():
    """Mock Docker operations."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )
        yield mock_run


@pytest.fixture
def mock_git_clone():
    """Mock git clone operations."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Cloning into 'repo'...",
            stderr="",
        )
        yield mock_run


@pytest.fixture
def mock_beads_cli():
    """Mock beads CLI (bd) operations."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"status": "ok"}),
            stderr="",
        )
        yield mock_run


@pytest.fixture
def mock_container_manager():
    """Mock ContainerManager for testing without Docker."""
    mock_manager = MagicMock()
    mock_manager.status = "running"
    mock_manager.container_name = "zerocoder-test-1"
    mock_manager.is_agent_running.return_value = False
    mock_manager.get_status_dict.return_value = {
        "status": "running",
        "agent_running": False,
        "container_name": "zerocoder-test-1",
    }
    mock_manager.start_container_only = AsyncMock(return_value=(True, "Started"))
    mock_manager.stop = AsyncMock(return_value=(True, "Stopped"))
    mock_manager.graceful_stop = AsyncMock(return_value=(True, "Stopped gracefully"))

    return mock_manager


# =============================================================================
# WebSocket Fixtures
# =============================================================================

@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket for testing."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.close = AsyncMock()
    return ws


# =============================================================================
# Async Utilities
# =============================================================================

@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# Schema Test Data Fixtures
# =============================================================================

@pytest.fixture
def valid_project_create_data() -> dict:
    """Valid data for ProjectCreate schema."""
    return {
        "name": "my-project",
        "git_url": "https://github.com/user/repo.git",
        "is_new": True,
        "spec_method": "claude",
    }


@pytest.fixture
def valid_feature_create_data() -> dict:
    """Valid data for FeatureCreate schema."""
    return {
        "category": "authentication",
        "name": "User Login",
        "description": "Implement user login functionality",
        "steps": ["Create form", "Add validation", "Connect API"],
        "priority": 1,
    }


@pytest.fixture
def valid_agent_start_data() -> dict:
    """Valid data for AgentStartRequest schema."""
    return {
        "instruction": "Implement the next pending feature",
        "yolo_mode": False,
    }


# =============================================================================
# File System Utilities
# =============================================================================

@pytest.fixture
def create_temp_file(tmp_path: Path):
    """Factory fixture to create temporary files."""
    def _create(name: str, content: str) -> Path:
        file_path = tmp_path / name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        return file_path
    return _create


@pytest.fixture
def create_temp_project(tmp_path: Path):
    """Factory fixture to create complete test projects."""
    def _create(name: str, with_beads: bool = True, with_prompts: bool = True) -> Path:
        project_dir = tmp_path / name
        project_dir.mkdir(parents=True)

        if with_prompts:
            prompts_dir = project_dir / "prompts"
            prompts_dir.mkdir()
            (prompts_dir / "app_spec.txt").write_text("<app-spec><name>Test</name></app-spec>")
            (prompts_dir / "coding_prompt.md").write_text("# Coding")

        if with_beads:
            beads_dir = project_dir / ".beads"
            beads_dir.mkdir()
            config_file = beads_dir / "config.yaml"
            config_file.write_text("prefix: feat\n")
            issues_file = beads_dir / "issues.jsonl"
            issues_file.write_text('{"id":"feat-1","title":"Test","status":"open","priority":1}\n')

        return project_dir

    return _create


# =============================================================================
# Cleanup Utilities
# =============================================================================

@pytest.fixture(autouse=True)
def cleanup_test_artifacts(tmp_path: Path):
    """Automatically clean up test artifacts after each test."""
    yield
    # Cleanup is handled by tmp_path fixture


# =============================================================================
# Performance Test Utilities
# =============================================================================

@pytest.fixture
def large_issues_dataset():
    """Generate a large dataset for performance testing."""
    def _generate(count: int = 1000) -> list[dict]:
        return [
            {
                "id": f"feat-{i}",
                "title": f"Feature {i}",
                "status": "open" if i % 3 == 0 else ("in_progress" if i % 3 == 1 else "closed"),
                "priority": i % 5,
                "labels": [f"label-{i % 10}"],
                "description": f"Description for feature {i}",
            }
            for i in range(count)
        ]
    return _generate


# =============================================================================
# WebSocket Test Fixtures
# =============================================================================

@pytest.fixture
def websocket_manager():
    """Create a ConnectionManager instance for testing."""
    from server.websocket import ConnectionManager
    return ConnectionManager()


@pytest.fixture
def mock_websocket_client():
    """Create a mock WebSocket client."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.receive_json = AsyncMock()
    ws.close = AsyncMock()
    ws.send_text = AsyncMock()
    ws.receive_text = AsyncMock()
    return ws


# =============================================================================
# Container Manager Test Fixtures
# =============================================================================

@pytest.fixture
def container_manager_factory(tmp_path):
    """Factory fixture to create ContainerManager instances."""
    from server.services.container_manager import ContainerManager, _container_managers

    _container_managers.clear()

    def _create(project_name: str, container_number: int = 1):
        project_dir = tmp_path / project_name
        project_dir.mkdir(parents=True, exist_ok=True)

        with patch("server.services.container_manager.get_projects_dir") as mock_dir:
            mock_dir.return_value = tmp_path
            with patch.object(ContainerManager, "_sync_status"):
                with patch.object(ContainerManager, "_check_user_started_marker", return_value=False):
                    return ContainerManager(
                        project_name=project_name,
                        git_url=f"https://github.com/user/{project_name}.git",
                        container_number=container_number,
                        project_dir=project_dir,
                        skip_db_persist=True,
                    )
    return _create


# =============================================================================
# API Test Fixtures
# =============================================================================

@pytest.fixture
def mock_registry_functions():
    """Mock common registry functions."""
    with patch("server.routers.projects._get_registry_functions") as mock:
        mock.return_value = (
            MagicMock(),  # register_project
            MagicMock(),  # unregister_project
            MagicMock(return_value=None),  # get_project_path
            MagicMock(return_value=None),  # get_project_git_url
            MagicMock(return_value=None),  # get_project_info
            MagicMock(return_value=Path("/tmp")),  # get_projects_dir
            MagicMock(return_value={}),  # list_registered_projects
            MagicMock(return_value=True),  # validate_project_path
            MagicMock(),  # mark_project_initialized
            MagicMock(),  # update_target_container_count
            MagicMock(return_value=[]),  # list_project_containers
        )
        yield mock


# =============================================================================
# Beads Test Fixtures
# =============================================================================

@pytest.fixture
def beads_project(tmp_path):
    """Create a project with initialized beads."""
    project_dir = tmp_path / "beads-test"
    project_dir.mkdir()

    beads_dir = project_dir / ".beads"
    beads_dir.mkdir()

    config_file = beads_dir / "config.yaml"
    config_file.write_text("prefix: feat\n")

    issues_file = beads_dir / "issues.jsonl"
    issues_file.write_text("")

    return project_dir


@pytest.fixture
def populated_beads_project(beads_project):
    """Create a project with beads and sample features."""
    issues_file = beads_project / ".beads" / "issues.jsonl"

    features = [
        {"id": "feat-1", "title": "Auth", "status": "open", "priority": 0, "labels": ["auth"]},
        {"id": "feat-2", "title": "Dashboard", "status": "in_progress", "priority": 1, "labels": ["ui"]},
        {"id": "feat-3", "title": "API", "status": "closed", "priority": 2, "labels": ["backend"]},
    ]

    with open(issues_file, "w") as f:
        for feat in features:
            f.write(json.dumps(feat) + "\n")

    return beads_project, features


# =============================================================================
# Async Test Utilities
# =============================================================================

@pytest.fixture
def run_async():
    """Helper to run async functions in sync tests."""
    import asyncio

    def _run(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    return _run


# =============================================================================
# Time-based Test Fixtures
# =============================================================================

@pytest.fixture
def frozen_time():
    """Fixture for time-sensitive tests."""
    from datetime import datetime
    import time

    frozen = datetime(2024, 1, 15, 12, 0, 0)
    frozen_timestamp = frozen.timestamp()

    def mock_now(*args, **kwargs):
        return frozen

    def mock_time():
        return frozen_timestamp

    with patch("datetime.datetime") as mock_datetime:
        mock_datetime.now = mock_now
        mock_datetime.fromisoformat = datetime.fromisoformat
        with patch("time.time", mock_time):
            yield frozen
