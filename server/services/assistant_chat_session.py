"""
Assistant Chat Session
======================

Manages conversational assistant sessions for projects.
The assistant can:
- Answer questions about the codebase and features (read-only)
- Create new issues/features via the issue-creator MCP server
"""

import json
import logging
import os
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator, Optional

from claude_agent_sdk import (
    ClaudeAgentOptions,
    ClaudeSDKClient,
    CLINotFoundError,
    ProcessError,
    CLIConnectionError,
)

from .assistant_database import (
    add_message,
    create_conversation,
)

logger = logging.getLogger(__name__)

# Root directory of the project
ROOT_DIR = Path(__file__).parent.parent.parent

# Read-only built-in tools (no Write, Edit, Bash)
READONLY_BUILTIN_TOOLS = [
    "Read",
    "Glob",
    "Grep",
    "WebFetch",
    "WebSearch",
]

# Issue creation MCP tool - routes through container like frontend
ISSUE_CREATOR_MCP_TOOL = "mcp__issue-creator__create_issue"


def _get_app_spec_context(project_dir: Path) -> str:
    """Get app spec content for context, truncated if too long."""
    app_spec_path = project_dir / "prompts" / "app_spec.txt"
    if not app_spec_path.exists():
        return ""

    try:
        content = app_spec_path.read_text(encoding="utf-8")
        if len(content) > 5000:
            content = content[:5000] + "\n... (truncated)"
        return f"## Project Specification\n\n{content}"
    except Exception as e:
        logger.warning(f"Failed to read app_spec.txt: {e}")
        return ""


def get_system_prompt(project_name: str, project_dir: Path) -> str:
    """Generate the system prompt for the assistant with project context."""
    # Try to load from template first
    template_path = ROOT_DIR / ".claude" / "templates" / "assistant_prompt.template.md"

    if template_path.exists():
        try:
            prompt = template_path.read_text(encoding="utf-8")
            prompt = prompt.replace("$PROJECT_NAME", project_name)
            prompt = prompt.replace("$APP_SPEC_CONTEXT", _get_app_spec_context(project_dir))
            return prompt
        except Exception as e:
            logger.warning(f"Failed to load assistant prompt template: {e}")

    # Fallback to inline prompt
    app_spec_context = _get_app_spec_context(project_dir)

    return f"""# Project Assistant for "{project_name}"

You are a helpful project assistant with two capabilities:

## 1. Codebase Exploration (Read-Only)
- Read and analyze source code files
- Search for patterns and implementations
- Look up documentation online

## 2. Feature/Issue Creation
- Create issues in the project's beads tracker using the `create_issue` tool
- Ask clarifying questions to refine requirements
- Always confirm before creating an issue

## IMPORTANT RULES
1. You CANNOT modify code - No writing, editing, or deleting source files
2. You CAN create issues - Use the `create_issue` tool
3. Always confirm before creating - Show the user what you'll create first

{app_spec_context}

## Guidelines
1. Be concise and helpful
2. Reference specific file paths and line numbers
3. Search the codebase before answering
4. If unsure, say so rather than guessing"""


class AssistantChatSession:
    """
    Manages a read-only assistant conversation for a project.

    Uses Claude Opus 4.5 with only read-only tools enabled.
    Persists conversation history to SQLite.
    """

    def __init__(self, project_name: str, project_dir: Path, conversation_id: Optional[int] = None):
        """
        Initialize the session.

        Args:
            project_name: Name of the project
            project_dir: Absolute path to the project directory
            conversation_id: Optional existing conversation ID to resume
        """
        self.project_name = project_name
        self.project_dir = project_dir
        self.conversation_id = conversation_id
        self.client: Optional[ClaudeSDKClient] = None
        self._client_entered: bool = False
        self.created_at = datetime.now()

    async def close(self) -> None:
        """Clean up resources and close the Claude client."""
        if self.client and self._client_entered:
            try:
                await self.client.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing Claude client: {e}")
            finally:
                self._client_entered = False
                self.client = None

    async def start(self) -> AsyncGenerator[dict, None]:
        """
        Initialize session with the Claude client.

        Creates a new conversation if none exists, then sends an initial greeting.
        Yields message chunks as they stream in.
        """
        # Create a new conversation if we don't have one
        if self.conversation_id is None:
            conv = create_conversation(self.project_dir, self.project_name)
            self.conversation_id = conv.id
            yield {"type": "conversation_created", "conversation_id": self.conversation_id}

        # Build permissions list for read-only access + issue creation
        permissions_list = [
            "Read(./**)",
            "Glob(./**)",
            "Grep(./**)",
            "WebFetch",
            "WebSearch",
            ISSUE_CREATOR_MCP_TOOL,
        ]

        # Create security settings file
        security_settings = {
            "sandbox": {"enabled": False},
            "permissions": {
                "defaultMode": "bypassPermissions",
                "allow": permissions_list,
            },
        }
        settings_file = self.project_dir / ".claude_assistant_settings.json"
        with open(settings_file, "w") as f:
            json.dump(security_settings, f, indent=2)

        # Build MCP servers config - issue creator for feature creation
        mcp_servers = {
            "issue-creator": {
                "command": sys.executable,
                "args": ["-m", "mcp_server.issue_creator_mcp"],
                "env": {
                    **os.environ,
                    "PROJECT_NAME": self.project_name,
                    "PROJECT_DIR": str(self.project_dir.resolve()),
                    "PYTHONPATH": str(ROOT_DIR.resolve()),
                },
            },
        }

        # Get system prompt with project context
        system_prompt = get_system_prompt(self.project_name, self.project_dir)

        # Use system Claude CLI
        system_cli = shutil.which("claude")

        # Build allowed tools list - read-only only, plus issue creation
        allowed_tools = [
            *READONLY_BUILTIN_TOOLS,
            ISSUE_CREATOR_MCP_TOOL,
        ]

        # Define stderr callback for logging CLI output
        def handle_cli_stderr(line: str) -> None:
            logger.debug(f"Claude CLI: {line}")

        try:
            self.client = ClaudeSDKClient(
                options=ClaudeAgentOptions(
                    model="claude-opus-4-5-20251101",
                    cli_path=system_cli,
                    system_prompt=system_prompt,
                    allowed_tools=allowed_tools,
                    mcp_servers=mcp_servers,
                    permission_mode="bypassPermissions",
                    max_turns=100,
                    cwd=str(self.project_dir.resolve()),
                    settings=str(settings_file.resolve()),
                    stderr=handle_cli_stderr,  # Use callback instead of deprecated debug_stderr
                )
            )
            # Manual context manager handling required because this session
            # spans multiple HTTP requests and needs to stay alive between them.
            # We can't use 'async with' because that would close the client
            # at the end of the start() method.
            await self.client.__aenter__()
            self._client_entered = True
        except CLINotFoundError:
            logger.error("Claude Code CLI not found")
            yield {
                "type": "error",
                "content": "Claude Code CLI not installed. Install with: curl -fsSL https://claude.ai/install.sh | bash",
            }
            return
        except ProcessError as e:
            logger.error(f"Claude process failed with exit code {e.exit_code}: {e.stderr}")
            yield {"type": "error", "content": f"Claude process error: {str(e)}"}
            return
        except CLIConnectionError as e:
            logger.error(f"Failed to connect to Claude: {e}")
            yield {"type": "error", "content": f"Connection error: {str(e)}"}
            return
        except Exception as e:
            logger.exception("Unexpected error creating Claude client")
            yield {"type": "error", "content": f"Failed to initialize assistant: {str(e)}"}
            return

        # Send initial greeting
        try:
            greeting = f"Hello! I'm your project assistant for **{self.project_name}**. I can help you:\n\n- Explore and understand the codebase\n- Answer questions about the project\n- Create new features/issues\n\nWhat would you like to do?"

            # Store the greeting in the database
            add_message(self.project_dir, self.conversation_id, "assistant", greeting)

            yield {"type": "text", "content": greeting}
            yield {"type": "response_done"}
        except Exception as e:
            logger.exception("Failed to send greeting")
            yield {"type": "error", "content": f"Failed to start conversation: {str(e)}"}

    async def send_message(self, user_message: str) -> AsyncGenerator[dict, None]:
        """
        Send user message and stream Claude's response.

        Args:
            user_message: The user's message

        Yields:
            Message chunks:
            - {"type": "text", "content": str}
            - {"type": "tool_call", "tool": str, "input": dict}
            - {"type": "response_done"}
            - {"type": "error", "content": str}
        """
        if not self.client:
            yield {"type": "error", "content": "Session not initialized. Call start() first."}
            return

        if self.conversation_id is None:
            yield {"type": "error", "content": "No conversation ID set."}
            return

        # Store user message in database
        add_message(self.project_dir, self.conversation_id, "user", user_message)

        try:
            async for chunk in self._query_claude(user_message):
                yield chunk
            yield {"type": "response_done"}
        except Exception as e:
            logger.exception("Error during Claude query")
            yield {"type": "error", "content": f"Error: {str(e)}"}

    async def _query_claude(self, message: str) -> AsyncGenerator[dict, None]:
        """
        Internal method to query Claude and stream responses.

        Handles tool calls, text responses, and issue creation events.
        """
        import re

        if not self.client:
            return

        # Send message to Claude
        await self.client.query(message)

        full_response = ""

        # Track pending issue creation tool calls
        pending_issue_create: dict | None = None

        # Stream the response
        async for msg in self.client.receive_response():
            msg_type = type(msg).__name__

            if msg_type == "AssistantMessage" and hasattr(msg, "content"):
                for block in msg.content:
                    block_type = type(block).__name__

                    if block_type == "TextBlock" and hasattr(block, "text"):
                        text = block.text
                        if text:
                            full_response += text
                            yield {"type": "text", "content": text}

                    elif block_type == "ToolUseBlock" and hasattr(block, "name"):
                        tool_name = block.name
                        tool_input = getattr(block, "input", {})
                        tool_id = getattr(block, "id", "")

                        # Track issue creation calls
                        if tool_name == ISSUE_CREATOR_MCP_TOOL or tool_name == "create_issue":
                            pending_issue_create = {
                                "tool_id": tool_id,
                                "title": tool_input.get("title", ""),
                            }
                            yield {
                                "type": "tool_call",
                                "tool": "create_issue",
                                "input": {"title": tool_input.get("title", "")},
                            }
                        else:
                            yield {
                                "type": "tool_call",
                                "tool": tool_name,
                                "input": tool_input,
                            }

            elif msg_type == "UserMessage" and hasattr(msg, "content"):
                # Tool results - check for issue creation success
                for block in msg.content:
                    block_type = type(block).__name__
                    if block_type == "ToolResultBlock":
                        content = getattr(block, "content", "")
                        tool_use_id = getattr(block, "tool_use_id", "")
                        is_error = getattr(block, "is_error", False)

                        # Check if this is an issue creation result
                        if pending_issue_create and not is_error:
                            # Parse issue ID from result
                            content_str = str(content)
                            if "Created issue:" in content_str:
                                match = re.search(r"Created issue:\s*(\S+)", content_str)
                                if match:
                                    issue_id = match.group(1)
                                    yield {
                                        "type": "issue_created",
                                        "id": issue_id,
                                        "title": pending_issue_create.get("title", ""),
                                    }
                                pending_issue_create = None

        # Store the complete response in the database
        if full_response and self.conversation_id:
            add_message(self.project_dir, self.conversation_id, "assistant", full_response)

    def get_conversation_id(self) -> Optional[int]:
        """Get the current conversation ID."""
        return self.conversation_id


# Session registry with thread safety
_sessions: dict[str, AssistantChatSession] = {}
_sessions_lock = threading.Lock()


def get_session(project_name: str) -> Optional[AssistantChatSession]:
    """Get an existing session for a project."""
    with _sessions_lock:
        return _sessions.get(project_name)


async def create_session(
    project_name: str,
    project_dir: Path,
    conversation_id: Optional[int] = None
) -> AssistantChatSession:
    """
    Create a new session for a project, closing any existing one.

    Args:
        project_name: Name of the project
        project_dir: Absolute path to the project directory
        conversation_id: Optional conversation ID to resume
    """
    old_session: Optional[AssistantChatSession] = None

    with _sessions_lock:
        old_session = _sessions.pop(project_name, None)
        session = AssistantChatSession(project_name, project_dir, conversation_id)
        _sessions[project_name] = session

    if old_session:
        try:
            await old_session.close()
        except Exception as e:
            logger.warning(f"Error closing old session for {project_name}: {e}")

    return session


async def remove_session(project_name: str) -> None:
    """Remove and close a session."""
    session: Optional[AssistantChatSession] = None

    with _sessions_lock:
        session = _sessions.pop(project_name, None)

    if session:
        try:
            await session.close()
        except Exception as e:
            logger.warning(f"Error closing session for {project_name}: {e}")


def list_sessions() -> list[str]:
    """List all active session project names."""
    with _sessions_lock:
        return list(_sessions.keys())


async def cleanup_all_sessions() -> None:
    """Close all active sessions. Called on server shutdown."""
    sessions_to_close: list[AssistantChatSession] = []

    with _sessions_lock:
        sessions_to_close = list(_sessions.values())
        _sessions.clear()

    for session in sessions_to_close:
        try:
            await session.close()
        except Exception as e:
            logger.warning(f"Error closing session {session.project_name}: {e}")
