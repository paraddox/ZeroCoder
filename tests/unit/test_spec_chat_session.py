"""
Spec Chat Session Unit Tests
============================

Tests for the spec creation chat session service including:
- Session lifecycle management
- Multimodal message handling
- File tracking and verification
- Thread-safe session registry
"""

import json
import pytest
import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Multimodal Message Tests
# =============================================================================

class TestMakeMultimodalMessage:
    """Tests for _make_multimodal_message function."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_yields_properly_formatted_message(self):
        """Test yields message in correct format."""
        from server.services.spec_chat_session import _make_multimodal_message

        content_blocks = [{"type": "text", "text": "Hello"}]

        messages = []
        async for msg in _make_multimodal_message(content_blocks):
            messages.append(msg)

        assert len(messages) == 1
        assert messages[0]["type"] == "user"
        assert messages[0]["message"]["role"] == "user"
        assert messages[0]["message"]["content"] == content_blocks
        assert messages[0]["parent_tool_use_id"] is None
        assert messages[0]["session_id"] == "default"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_handles_multiple_content_blocks(self):
        """Test handles multiple content blocks."""
        from server.services.spec_chat_session import _make_multimodal_message

        content_blocks = [
            {"type": "text", "text": "Hello"},
            {"type": "image", "source": {"type": "base64", "data": "abc"}},
        ]

        messages = []
        async for msg in _make_multimodal_message(content_blocks):
            messages.append(msg)

        assert len(messages) == 1
        assert len(messages[0]["message"]["content"]) == 2


# =============================================================================
# SpecChatSession Tests
# =============================================================================

class TestSpecChatSession:
    """Tests for SpecChatSession class."""

    @pytest.mark.unit
    def test_initialization(self, tmp_path):
        """Test session initialization."""
        from server.services.spec_chat_session import SpecChatSession

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = SpecChatSession("test-project", project_dir)

        assert session.project_name == "test-project"
        assert session.project_dir == project_dir
        assert session.client is None
        assert session.messages == []
        assert session.complete is False
        assert isinstance(session.created_at, datetime)

    @pytest.mark.unit
    def test_is_complete_initially_false(self, tmp_path):
        """Test is_complete returns False initially."""
        from server.services.spec_chat_session import SpecChatSession

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = SpecChatSession("test-project", project_dir)

        assert session.is_complete() is False

    @pytest.mark.unit
    def test_is_complete_after_completion(self, tmp_path):
        """Test is_complete returns True after completion."""
        from server.services.spec_chat_session import SpecChatSession

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = SpecChatSession("test-project", project_dir)
        session.complete = True

        assert session.is_complete() is True

    @pytest.mark.unit
    def test_get_messages_returns_copy(self, tmp_path):
        """Test get_messages returns a copy of messages."""
        from server.services.spec_chat_session import SpecChatSession

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = SpecChatSession("test-project", project_dir)
        session.messages = [{"role": "user", "content": "test"}]

        messages = session.get_messages()

        assert messages == session.messages
        assert messages is not session.messages  # Should be a copy

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_close_without_client(self, tmp_path):
        """Test close method when no client is initialized."""
        from server.services.spec_chat_session import SpecChatSession

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = SpecChatSession("test-project", project_dir)

        # Should not raise
        await session.close()

        assert session.client is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_message_without_client_yields_error(self, tmp_path):
        """Test send_message yields error when client not initialized."""
        from server.services.spec_chat_session import SpecChatSession

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = SpecChatSession("test-project", project_dir)

        messages = []
        async for msg in session.send_message("Hello"):
            messages.append(msg)

        assert len(messages) == 1
        assert messages[0]["type"] == "error"
        assert "not initialized" in messages[0]["content"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_start_without_skill_file_yields_error(self, tmp_path):
        """Test start yields error when skill file not found."""
        from server.services.spec_chat_session import SpecChatSession

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = SpecChatSession("test-project", project_dir)

        with patch("server.services.spec_chat_session.ROOT_DIR", tmp_path):
            messages = []
            async for msg in session.start():
                messages.append(msg)

        assert len(messages) == 1
        assert messages[0]["type"] == "error"
        assert "not found" in messages[0]["content"]


# =============================================================================
# Session Registry Tests
# =============================================================================

class TestSpecSessionRegistry:
    """Tests for the spec session registry functions."""

    @pytest.mark.unit
    def test_get_session_returns_none_when_not_exists(self):
        """Test get_session returns None for non-existent session."""
        from server.services.spec_chat_session import get_session, _sessions, _sessions_lock

        with _sessions_lock:
            _sessions.clear()

        result = get_session("nonexistent-project")

        assert result is None

    @pytest.mark.unit
    def test_list_sessions_returns_empty_initially(self):
        """Test list_sessions returns empty list when no sessions."""
        from server.services.spec_chat_session import list_sessions, _sessions, _sessions_lock

        with _sessions_lock:
            _sessions.clear()

        result = list_sessions()

        assert result == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_session_adds_to_registry(self, tmp_path):
        """Test create_session adds session to registry."""
        from server.services.spec_chat_session import (
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
        from server.services.spec_chat_session import (
            create_session, _sessions, _sessions_lock
        )

        with _sessions_lock:
            _sessions.clear()

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session1 = await create_session("test-project", project_dir)
        session2 = await create_session("test-project", project_dir)

        assert session1 is not session2
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
        from server.services.spec_chat_session import (
            create_session, remove_session, get_session, _sessions, _sessions_lock
        )

        with _sessions_lock:
            _sessions.clear()

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        await create_session("test-project", project_dir)
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
        from server.services.spec_chat_session import (
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
# Message Storage Tests
# =============================================================================

class TestMessageStorage:
    """Tests for message storage in sessions."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_message_stores_user_message(self, tmp_path):
        """Test send_message stores user message in history."""
        from server.services.spec_chat_session import SpecChatSession

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = SpecChatSession("test-project", project_dir)
        session.client = MagicMock()  # Mock client

        # Consume the generator to trigger message storage
        async for _ in session.send_message("Hello", attachments=None):
            pass

        # Check message was stored (even though client error occurred)
        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "user"
        assert session.messages[0]["content"] == "Hello"
        assert session.messages[0]["has_attachments"] is False
        assert "timestamp" in session.messages[0]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_send_message_with_attachments_stores_flag(self, tmp_path):
        """Test send_message stores attachment flag."""
        from server.services.spec_chat_session import SpecChatSession
        from server.schemas import ImageAttachment

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        session = SpecChatSession("test-project", project_dir)
        session.client = MagicMock()

        # Create a mock attachment
        attachment = MagicMock(spec=ImageAttachment)
        attachment.isText = False
        attachment.mimeType = "image/png"
        attachment.base64Data = "abc123"
        attachment.filename = "test.png"

        # Consume the generator
        async for _ in session.send_message("Hello", attachments=[attachment]):
            pass

        assert session.messages[0]["has_attachments"] is True


# =============================================================================
# Thread Safety Tests
# =============================================================================

class TestSpecSessionThreadSafety:
    """Tests for thread-safe operations."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_concurrent_session_creation(self, tmp_path):
        """Test concurrent session creation is thread-safe."""
        from server.services.spec_chat_session import (
            create_session, list_sessions, _sessions, _sessions_lock
        )

        with _sessions_lock:
            _sessions.clear()

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        import asyncio

        async def create_project_session(name):
            return await create_session(name, project_dir)

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
        from server.services.spec_chat_session import (
            SpecChatSession, list_sessions, _sessions, _sessions_lock
        )

        with _sessions_lock:
            _sessions.clear()
            for i in range(5):
                _sessions[f"project-{i}"] = SpecChatSession(
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
