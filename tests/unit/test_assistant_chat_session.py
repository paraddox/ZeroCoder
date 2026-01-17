"""
Assistant Chat Session Unit Tests
=================================

Tests for the assistant chat session service including:
- Session lifecycle management
- System prompt generation
- Thread-safe session registry
- Error handling
"""

import json
import pytest
import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# System Prompt Tests
# =============================================================================

class TestGetAppSpecContext:
    """Tests for _get_app_spec_context function."""

    @pytest.mark.unit
    def test_returns_empty_when_no_spec(self, tmp_path):
        """Test returns empty string when no app_spec.txt exists."""
        from server.services.assistant_chat_session import _get_app_spec_context

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        result = _get_app_spec_context(project_dir)

        assert result == ""

    @pytest.mark.unit
    def test_returns_spec_content(self, tmp_path):
        """Test returns app spec content when file exists."""
        from server.services.assistant_chat_session import _get_app_spec_context

        project_dir = tmp_path / "test-project"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        spec_content = "<app-spec><name>Test App</name></app-spec>"
        (prompts_dir / "app_spec.txt").write_text(spec_content)

        result = _get_app_spec_context(project_dir)

        assert "Test App" in result
        assert "Project Specification" in result

    @pytest.mark.unit
    def test_truncates_large_spec(self, tmp_path):
        """Test truncates app spec content over 5000 characters."""
        from server.services.assistant_chat_session import _get_app_spec_context

        project_dir = tmp_path / "test-project"
        prompts_dir = project_dir / "prompts"
        prompts_dir.mkdir(parents=True)

        large_content = "x" * 10000
        (prompts_dir / "app_spec.txt").write_text(large_content)

        result = _get_app_spec_context(project_dir)

        assert "(truncated)" in result
        assert len(result) < 10000


class TestGetSystemPrompt:
    """Tests for get_system_prompt function."""

    @pytest.mark.unit
    def test_uses_template_when_available(self, tmp_path):
        """Test uses template file when it exists."""
        from server.services.assistant_chat_session import get_system_prompt

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        # Create a mock template
        template_dir = tmp_path / ".claude" / "templates"
        template_dir.mkdir(parents=True)
        template_content = "# Assistant for $PROJECT_NAME\n\n$APP_SPEC_CONTEXT"
        (template_dir / "assistant_prompt.template.md").write_text(template_content)

        with patch("server.services.assistant_chat_session.ROOT_DIR", tmp_path):
            result = get_system_prompt("my-project", project_dir)

        assert "my-project" in result

    @pytest.mark.unit
    def test_uses_fallback_prompt(self, tmp_path):
        """Test uses inline fallback prompt when no template."""
        from server.services.assistant_chat_session import get_system_prompt

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        # No template exists
        with patch("server.services.assistant_chat_session.ROOT_DIR", tmp_path):
            result = get_system_prompt("test-project", project_dir)

        assert "test-project" in result
        assert "Project Assistant" in result
        assert "IMPORTANT RULES" in result


# =============================================================================
# Session Registry Tests
# =============================================================================

class TestSessionRegistry:
    """Tests for the session registry functions."""

    @pytest.mark.unit
    def test_get_session_returns_none_when_not_exists(self):
        """Test get_session returns None for non-existent session."""
        from server.services.assistant_chat_session import get_session, _sessions, _sessions_lock

        with _sessions_lock:
            _sessions.clear()

        result = get_session("nonexistent-project")

        assert result is None

    @pytest.mark.unit
    def test_list_sessions_returns_empty_initially(self):
        """Test list_sessions returns empty list when no sessions."""
        from server.services.assistant_chat_session import list_sessions, _sessions, _sessions_lock

        with _sessions_lock:
            _sessions.clear()

        result = list_sessions()

        assert result == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_session_adds_to_registry(self, tmp_path):
        """Test create_session adds session to registry."""
        from server.services.assistant_chat_session import (
            create_session, get_session, _sessions, _sessions_lock
        )

        with _sessions_lock:
            _sessions.clear()

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = await create_session("test-project", project_dir)

        assert session is not None
        assert get_session("test-project") is session

        # Cleanup
        with _sessions_lock:
            _sessions.clear()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_session_closes_existing(self, tmp_path):
        """Test create_session closes existing session for same project."""
        from server.services.assistant_chat_session import (
            create_session, _sessions, _sessions_lock
        )

        with _sessions_lock:
            _sessions.clear()

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        # Create first session
        session1 = await create_session("test-project", project_dir)

        # Create second session for same project
        session2 = await create_session("test-project", project_dir)

        assert session1 is not session2
        # Only second session should be in registry
        with _sessions_lock:
            assert len(_sessions) == 1
            assert _sessions.get("test-project") is session2

        # Cleanup
        with _sessions_lock:
            _sessions.clear()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_remove_session_clears_registry(self, tmp_path):
        """Test remove_session removes session from registry."""
        from server.services.assistant_chat_session import (
            create_session, remove_session, get_session, _sessions, _sessions_lock
        )

        with _sessions_lock:
            _sessions.clear()

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = await create_session("test-project", project_dir)
        assert get_session("test-project") is not None

        await remove_session("test-project")

        assert get_session("test-project") is None

        # Cleanup
        with _sessions_lock:
            _sessions.clear()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cleanup_all_sessions(self, tmp_path):
        """Test cleanup_all_sessions clears all sessions."""
        from server.services.assistant_chat_session import (
            create_session, cleanup_all_sessions, list_sessions, _sessions, _sessions_lock
        )

        with _sessions_lock:
            _sessions.clear()

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        await create_session("project1", project_dir)
        await create_session("project2", project_dir)

        assert len(list_sessions()) == 2

        await cleanup_all_sessions()

        assert len(list_sessions()) == 0


# =============================================================================
# AssistantChatSession Tests
# =============================================================================

class TestAssistantChatSession:
    """Tests for AssistantChatSession class."""

    @pytest.mark.unit
    def test_initialization(self, tmp_path):
        """Test session initialization."""
        from server.services.assistant_chat_session import AssistantChatSession

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = AssistantChatSession("test-project", project_dir)

        assert session.project_name == "test-project"
        assert session.project_dir == project_dir
        assert session.conversation_id is None
        assert session.client is None
        assert isinstance(session.created_at, datetime)

    @pytest.mark.unit
    def test_initialization_with_conversation_id(self, tmp_path):
        """Test session initialization with existing conversation ID."""
        from server.services.assistant_chat_session import AssistantChatSession

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = AssistantChatSession("test-project", project_dir, conversation_id=123)

        assert session.conversation_id == 123

    @pytest.mark.unit
    def test_get_conversation_id(self, tmp_path):
        """Test get_conversation_id method."""
        from server.services.assistant_chat_session import AssistantChatSession

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = AssistantChatSession("test-project", project_dir, conversation_id=456)

        assert session.get_conversation_id() == 456

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_close_without_client(self, tmp_path):
        """Test close method when no client is initialized."""
        from server.services.assistant_chat_session import AssistantChatSession

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = AssistantChatSession("test-project", project_dir)

        # Should not raise
        await session.close()

        assert session.client is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_message_without_client_yields_error(self, tmp_path):
        """Test send_message yields error when client not initialized."""
        from server.services.assistant_chat_session import AssistantChatSession

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = AssistantChatSession("test-project", project_dir)

        messages = []
        async for msg in session.send_message("Hello"):
            messages.append(msg)

        assert len(messages) == 1
        assert messages[0]["type"] == "error"
        assert "not initialized" in messages[0]["content"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_message_without_conversation_id_yields_error(self, tmp_path):
        """Test send_message yields error when no conversation ID."""
        from server.services.assistant_chat_session import AssistantChatSession

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = AssistantChatSession("test-project", project_dir)
        session.client = MagicMock()  # Mock client exists

        messages = []
        async for msg in session.send_message("Hello"):
            messages.append(msg)

        assert len(messages) == 1
        assert messages[0]["type"] == "error"
        assert "conversation ID" in messages[0]["content"]


# =============================================================================
# Thread Safety Tests
# =============================================================================

class TestThreadSafety:
    """Tests for thread-safe operations."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_session_creation(self, tmp_path):
        """Test concurrent session creation is thread-safe."""
        from server.services.assistant_chat_session import (
            create_session, list_sessions, _sessions, _sessions_lock
        )

        with _sessions_lock:
            _sessions.clear()

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        import asyncio

        async def create_project_session(name):
            return await create_session(name, project_dir)

        # Create multiple sessions concurrently
        tasks = [create_project_session(f"project-{i}") for i in range(5)]
        sessions = await asyncio.gather(*tasks)

        assert len(sessions) == 5
        assert len(list_sessions()) == 5

        # Cleanup
        with _sessions_lock:
            _sessions.clear()

    @pytest.mark.unit
    def test_concurrent_list_sessions(self, tmp_path):
        """Test concurrent list_sessions calls are thread-safe."""
        from server.services.assistant_chat_session import (
            AssistantChatSession, list_sessions, _sessions, _sessions_lock
        )

        with _sessions_lock:
            _sessions.clear()
            # Add some sessions
            for i in range(5):
                _sessions[f"project-{i}"] = AssistantChatSession(
                    f"project-{i}", tmp_path
                )

        results = []
        errors = []

        def list_in_thread():
            try:
                result = list_sessions()
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=list_in_thread) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert all(len(r) == 5 for r in results)

        # Cleanup
        with _sessions_lock:
            _sessions.clear()


# =============================================================================
# Constants and Configuration Tests
# =============================================================================

class TestConstantsAndConfiguration:
    """Tests for module constants and configuration."""

    @pytest.mark.unit
    def test_readonly_builtin_tools(self):
        """Test readonly builtin tools are correctly defined."""
        from server.services.assistant_chat_session import READONLY_BUILTIN_TOOLS

        expected_tools = ["Read", "Glob", "Grep", "WebFetch", "WebSearch"]

        assert set(READONLY_BUILTIN_TOOLS) == set(expected_tools)
        # Should not contain write tools
        assert "Write" not in READONLY_BUILTIN_TOOLS
        assert "Edit" not in READONLY_BUILTIN_TOOLS
        assert "Bash" not in READONLY_BUILTIN_TOOLS

    @pytest.mark.unit
    def test_issue_creator_mcp_tool(self):
        """Test issue creator MCP tool name is correct."""
        from server.services.assistant_chat_session import ISSUE_CREATOR_MCP_TOOL

        assert ISSUE_CREATOR_MCP_TOOL == "mcp__issue-creator__create_issue"
