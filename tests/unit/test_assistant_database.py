"""
Assistant Database Unit Tests
=============================

Tests for the assistant chat database operations including:
- Conversation creation and retrieval
- Message storage and ordering
- Database isolation
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Conversation Tests
# =============================================================================

class TestConversationOperations:
    """Tests for conversation database operations."""

    @pytest.mark.unit
    def test_create_conversation(self, tmp_path):
        """Test creating a new conversation."""
        from server.services.assistant_database import create_conversation, _get_db_path

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch.object(
            __import__('server.services.assistant_database', fromlist=['_get_db_path']),
            '_get_db_path',
            return_value=tmp_path / "assistant.db"
        ):
            conv = create_conversation(project_dir, "test-project")

        assert conv is not None
        assert conv.id is not None
        assert conv.project_name == "test-project"

    @pytest.mark.unit
    def test_get_conversation_returns_none_for_invalid_id(self, tmp_path):
        """Test get_conversation returns None for non-existent ID."""
        from server.services.assistant_database import get_conversation

        with patch(
            'server.services.assistant_database._get_db_path',
            return_value=tmp_path / "assistant.db"
        ):
            result = get_conversation(tmp_path, 99999)

        assert result is None

    @pytest.mark.unit
    def test_list_conversations_empty(self, tmp_path):
        """Test list_conversations returns empty list initially."""
        from server.services.assistant_database import list_conversations

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch(
            'server.services.assistant_database._get_db_path',
            return_value=tmp_path / "assistant.db"
        ):
            result = list_conversations(project_dir)

        assert result == []

    @pytest.mark.unit
    def test_list_conversations_after_creation(self, tmp_path):
        """Test list_conversations returns created conversations."""
        from server.services.assistant_database import (
            create_conversation, list_conversations
        )

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch(
            'server.services.assistant_database._get_db_path',
            return_value=tmp_path / "assistant.db"
        ):
            conv1 = create_conversation(project_dir, "test-project")
            conv2 = create_conversation(project_dir, "test-project")
            result = list_conversations(project_dir)

        assert len(result) == 2


# =============================================================================
# Message Tests
# =============================================================================

class TestMessageOperations:
    """Tests for message database operations."""

    @pytest.mark.unit
    def test_add_message_user(self, tmp_path):
        """Test adding a user message."""
        from server.services.assistant_database import (
            create_conversation, add_message, get_messages
        )

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch(
            'server.services.assistant_database._get_db_path',
            return_value=tmp_path / "assistant.db"
        ):
            conv = create_conversation(project_dir, "test-project")
            add_message(project_dir, conv.id, "user", "Hello!")
            messages = get_messages(project_dir, conv.id)

        assert len(messages) == 1
        assert messages[0].role == "user"
        assert messages[0].content == "Hello!"

    @pytest.mark.unit
    def test_add_message_assistant(self, tmp_path):
        """Test adding an assistant message."""
        from server.services.assistant_database import (
            create_conversation, add_message, get_messages
        )

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch(
            'server.services.assistant_database._get_db_path',
            return_value=tmp_path / "assistant.db"
        ):
            conv = create_conversation(project_dir, "test-project")
            add_message(project_dir, conv.id, "assistant", "Hi there!")
            messages = get_messages(project_dir, conv.id)

        assert len(messages) == 1
        assert messages[0].role == "assistant"
        assert messages[0].content == "Hi there!"

    @pytest.mark.unit
    def test_message_ordering(self, tmp_path):
        """Test messages are returned in correct order."""
        from server.services.assistant_database import (
            create_conversation, add_message, get_messages
        )

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch(
            'server.services.assistant_database._get_db_path',
            return_value=tmp_path / "assistant.db"
        ):
            conv = create_conversation(project_dir, "test-project")
            add_message(project_dir, conv.id, "user", "Message 1")
            add_message(project_dir, conv.id, "assistant", "Message 2")
            add_message(project_dir, conv.id, "user", "Message 3")
            messages = get_messages(project_dir, conv.id)

        assert len(messages) == 3
        assert messages[0].content == "Message 1"
        assert messages[1].content == "Message 2"
        assert messages[2].content == "Message 3"

    @pytest.mark.unit
    def test_get_messages_empty(self, tmp_path):
        """Test get_messages returns empty list for conversation without messages."""
        from server.services.assistant_database import (
            create_conversation, get_messages
        )

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch(
            'server.services.assistant_database._get_db_path',
            return_value=tmp_path / "assistant.db"
        ):
            conv = create_conversation(project_dir, "test-project")
            messages = get_messages(project_dir, conv.id)

        assert messages == []

    @pytest.mark.unit
    def test_get_messages_invalid_conversation(self, tmp_path):
        """Test get_messages returns empty list for invalid conversation ID."""
        from server.services.assistant_database import get_messages

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        with patch(
            'server.services.assistant_database._get_db_path',
            return_value=tmp_path / "assistant.db"
        ):
            messages = get_messages(project_dir, 99999)

        assert messages == []


# =============================================================================
# Database Path Tests
# =============================================================================

class TestDatabasePath:
    """Tests for database path handling."""

    @pytest.mark.unit
    def test_database_created_in_project_dir(self, tmp_path):
        """Test database is created within project directory."""
        from server.services.assistant_database import create_conversation

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        create_conversation(project_dir, "test-project")

        db_path = project_dir / ".assistant" / "conversations.db"
        assert db_path.exists()

    @pytest.mark.unit
    def test_database_directory_created(self, tmp_path):
        """Test .assistant directory is created if not exists."""
        from server.services.assistant_database import create_conversation

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        assert not (project_dir / ".assistant").exists()

        create_conversation(project_dir, "test-project")

        assert (project_dir / ".assistant").exists()


# =============================================================================
# Isolation Tests
# =============================================================================

class TestDatabaseIsolation:
    """Tests for database isolation between projects."""

    @pytest.mark.unit
    def test_separate_databases_per_project(self, tmp_path):
        """Test each project has its own database."""
        from server.services.assistant_database import (
            create_conversation, list_conversations
        )

        project1_dir = tmp_path / "project1"
        project2_dir = tmp_path / "project2"
        project1_dir.mkdir()
        project2_dir.mkdir()

        conv1 = create_conversation(project1_dir, "project1")
        conv2 = create_conversation(project2_dir, "project2")

        list1 = list_conversations(project1_dir)
        list2 = list_conversations(project2_dir)

        assert len(list1) == 1
        assert len(list2) == 1
        assert list1[0].project_name == "project1"
        assert list2[0].project_name == "project2"

    @pytest.mark.unit
    def test_messages_isolated_by_conversation(self, tmp_path):
        """Test messages are isolated between conversations."""
        from server.services.assistant_database import (
            create_conversation, add_message, get_messages
        )

        project_dir = tmp_path / "test-project"
        project_dir.mkdir()

        conv1 = create_conversation(project_dir, "test-project")
        conv2 = create_conversation(project_dir, "test-project")

        add_message(project_dir, conv1.id, "user", "Conv 1 message")
        add_message(project_dir, conv2.id, "user", "Conv 2 message")

        messages1 = get_messages(project_dir, conv1.id)
        messages2 = get_messages(project_dir, conv2.id)

        assert len(messages1) == 1
        assert len(messages2) == 1
        assert messages1[0].content == "Conv 1 message"
        assert messages2[0].content == "Conv 2 message"
