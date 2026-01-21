"""
Issue Creator MCP Server
========================

Exposes a create_issue tool that routes through BeadsManager,
using the same code path as the frontend feature creation.

Environment Variables:
    PROJECT_NAME: Name of the project
    PROJECT_DIR: Absolute path to the project directory
    PYTHONPATH: Should include the root directory of ZeroCoder
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to path for imports
ROOT_DIR = Path(__file__).parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get project info from environment
PROJECT_NAME = os.environ.get("PROJECT_NAME", "")
PROJECT_DIR = os.environ.get("PROJECT_DIR", "")

server = Server("issue-creator")


def _is_sandbox_running(project_name: str) -> bool:
    """Check if any E2B sandbox is running for this project."""
    from server.services.e2b_sandbox_manager import _managers, _managers_lock

    with _managers_lock:
        if project_name not in _managers:
            return False
        # Check if any sandbox for this project is running
        for manager in _managers[project_name].values():
            if manager.status == "running":
                return True
        return False


async def _trigger_feature_refresh(project_name: str) -> None:
    """
    Trigger a beads sync to push changes to remote.
    Called after creating an issue so changes are persisted.
    """
    from server.services.beads_manager import get_beads_manager
    from registry import get_project_git_url

    try:
        git_url = get_project_git_url(project_name)
        if git_url:
            manager = await get_beads_manager(project_name, git_url)
            success, msg = await manager.sync()
            if success:
                logger.info(f"Beads synced for {project_name}")
            else:
                logger.warning(f"Beads sync failed for {project_name}: {msg}")
        else:
            logger.warning(f"No git URL found for project {project_name}")
    except Exception as e:
        # Don't fail the issue creation if sync fails
        logger.warning(f"Failed to sync beads: {e}")


async def ensure_sandbox_running(project_name: str) -> tuple[bool, str]:
    """
    Ensure an E2B sandbox is running for write operations.
    Auto-starts the sandbox if it's stopped (without starting the agent).
    """
    from server.services.e2b_sandbox_manager import (
        get_container_manager,
        check_e2b_available,
    )
    from registry import get_project_git_url

    if _is_sandbox_running(project_name):
        return True, "Sandbox already running"

    # Check E2B availability
    available, msg = check_e2b_available()
    if not available:
        return False, msg

    # Get git URL for sandbox
    git_url = get_project_git_url(project_name)
    if not git_url:
        return False, "No git URL found for project"

    # Get manager and start sandbox
    manager = get_container_manager(project_name, git_url)
    success, message = await manager.start_sandbox_only()

    return success, message


@server.list_tools()
async def list_tools():
    """List available tools."""
    return [
        Tool(
            name="create_issue",
            description="""Create a new issue/feature in the project's beads tracker.

Use this when the user wants to create a new feature, task, or bug report.
The issue will be created in the project's .beads/ directory via the host BeadsManager.

IMPORTANT: Always get user confirmation before creating an issue.
Show them the draft and ask for approval.

Parameters:
- title: Short, descriptive title for the issue (required)
- description: Detailed description with context, implementation steps, acceptance criteria (required)
- priority: 0-4 where 0=critical, 1=high, 2=medium (default), 3=low, 4=backlog
- category: Optional category label (e.g., "ui", "api", "auth")
- steps: Optional list of implementation steps (will be added as checklist)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Issue title (concise, descriptive)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description with context, implementation steps, and acceptance criteria"
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Priority 0-4 (0=critical, 1=high, 2=medium, 3=low, 4=backlog)",
                        "default": 2,
                        "minimum": 0,
                        "maximum": 4
                    },
                    "category": {
                        "type": "string",
                        "description": "Category label (e.g., 'ui', 'api', 'auth')"
                    },
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Implementation steps as checklist items"
                    }
                },
                "required": ["title", "description"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""
    if name != "create_issue":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    if not PROJECT_NAME:
        return [TextContent(
            type="text",
            text="Error: PROJECT_NAME environment variable not set"
        )]

    # Ensure sandbox is running (for beads sync to work)
    success, msg = await ensure_sandbox_running(PROJECT_NAME)
    if not success:
        return [TextContent(type="text", text=f"Error starting sandbox: {msg}")]

    # Import here to avoid circular imports
    from server.services.beads_manager import get_beads_manager
    from registry import get_project_git_url

    try:
        title = arguments.get("title", "")
        description = arguments.get("description", "")
        priority = arguments.get("priority", 2)
        category = arguments.get("category", "")
        steps = arguments.get("steps", [])

        logger.info(f"Creating issue: {title}")

        # Get git URL for beads manager
        git_url = get_project_git_url(PROJECT_NAME)
        if not git_url:
            return [TextContent(type="text", text="Error: No git URL found for project")]

        # Create issue via BeadsManager (host-based)
        manager = await get_beads_manager(PROJECT_NAME, git_url)

        # Build the bd create command
        args = ["create", "--title", title, "--priority", str(priority)]
        if category:
            args.extend(["--labels", category])

        # Build description with steps
        full_description = description
        if steps:
            full_description += "\n\n## Implementation Steps\n"
            for step in steps:
                full_description += f"- [ ] {step}\n"

        args.extend(["--body", full_description])

        # Run the create command
        result = await manager.run_write_command(args)

        if result.get("error"):
            logger.error(f"Failed to create issue: {result['error']}")
            return [TextContent(type="text", text=f"Error: {result['error']}")]

        # Extract issue ID from result
        feature_id = result.get("id") or result.get("issue_id")
        if feature_id:
            result_msg = f"Created issue: {feature_id}\nTitle: {title}"
            if category:
                result_msg += f"\nCategory: {category}"
            result_msg += f"\nPriority: P{priority}"
            logger.info(f"Created issue: {feature_id}")

            # Trigger immediate sync to push changes
            await _trigger_feature_refresh(PROJECT_NAME)

            return [TextContent(type="text", text=result_msg)]
        else:
            logger.error("Failed to create issue - no ID returned")
            return [TextContent(type="text", text="Error: Failed to create issue - no ID returned")]

    except Exception as e:
        logger.exception(f"Error creating issue: {e}")
        return [TextContent(type="text", text=f"Error creating issue: {str(e)}")]


async def main():
    """Run the MCP server."""
    logger.info(f"Starting issue-creator MCP server for project: {PROJECT_NAME}")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
