"""
Issue Creator MCP Server
========================

Exposes a create_issue tool that routes through ContainerBeadsClient,
using the same code path as the frontend feature creation.

Environment Variables:
    PROJECT_NAME: Name of the project
    PROJECT_DIR: Absolute path to the project directory
    PYTHONPATH: Should include the root directory of ZeroCoder
"""

import asyncio
import json
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


def _is_container_running(project_name: str) -> bool:
    """Check if the container is running for this project."""
    from server.services.container_manager import _managers, _managers_lock

    with _managers_lock:
        manager = _managers.get(project_name)
        return manager is not None and manager.status == "running"


async def _trigger_feature_refresh(project_name: str) -> None:
    """
    Trigger an immediate feature poll to sync container data to host cache.
    Called after creating an issue so UI updates immediately.
    """
    from server.services.feature_poller import poll_container_features, update_feature_cache

    container_name = f"zerocoder-{project_name}"

    try:
        data = await poll_container_features(container_name, project_name)
        if data:
            update_feature_cache(project_name, data)
            logger.info(f"Feature cache refreshed for {project_name}")
        else:
            logger.warning(f"Feature poll returned no data for {project_name}")
    except Exception as e:
        # Don't fail the issue creation if refresh fails
        logger.warning(f"Failed to refresh feature cache: {e}")


async def ensure_container_running(project_name: str, project_dir: Path) -> tuple[bool, str]:
    """
    Ensure the container is running for write operations.
    Auto-starts the container if it's stopped (without starting the agent).
    """
    from server.services.container_manager import (
        get_container_manager,
        check_docker_available,
        check_image_exists,
    )

    if _is_container_running(project_name):
        return True, "Container already running"

    # Check Docker availability
    if not check_docker_available():
        return False, "Docker is not available. Please ensure Docker is installed and running."

    if not check_image_exists():
        return False, "Container image 'zerocoder-project' not found. Run: docker build -f Dockerfile.project -t zerocoder-project ."

    # Get manager and start container
    manager = get_container_manager(project_name, project_dir)
    success, message = await manager.start_container_only()

    return success, message


@server.list_tools()
async def list_tools():
    """List available tools."""
    return [
        Tool(
            name="create_issue",
            description="""Create a new issue/feature in the project's beads tracker.

Use this when the user wants to create a new feature, task, or bug report.
The issue will be created in the project's .beads/ directory via the container.

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

    if not PROJECT_NAME or not PROJECT_DIR:
        return [TextContent(
            type="text",
            text="Error: PROJECT_NAME and PROJECT_DIR environment variables not set"
        )]

    project_dir = Path(PROJECT_DIR)

    # Ensure container is running
    success, msg = await ensure_container_running(PROJECT_NAME, project_dir)
    if not success:
        return [TextContent(type="text", text=f"Error starting container: {msg}")]

    # Import here to avoid circular imports
    from server.services.container_beads import ContainerBeadsClient

    # Create issue via ContainerBeadsClient
    client = ContainerBeadsClient(PROJECT_NAME)

    try:
        title = arguments.get("title", "")
        description = arguments.get("description", "")
        priority = arguments.get("priority", 2)
        category = arguments.get("category", "")
        steps = arguments.get("steps", [])

        logger.info(f"Creating issue: {title}")

        feature_id = await client.create(
            name=title,
            description=description,
            category=category,
            steps=steps,
            priority=priority,
        )

        if feature_id:
            result_msg = f"Created issue: {feature_id}\nTitle: {title}"
            if category:
                result_msg += f"\nCategory: {category}"
            result_msg += f"\nPriority: P{priority}"
            logger.info(f"Created issue: {feature_id}")

            # Trigger immediate feature poll to sync to host
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
