"""
Issue Management MCP Server
============================

Exposes tools for managing issues in the project's beads tracker:
create, list, update, close, reopen, delete, and add dependencies.

Environment Variables:
    PROJECT_NAME: Name of the project
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

server = Server("issue-manager")


@server.list_tools()
async def list_tools():
    """List available tools."""
    return [
        Tool(
            name="list_issues",
            description="""List issues in the project's beads tracker.

Use this to view the current state of issues before making changes.
This is a read-only operation - no confirmation needed.

Parameters:
- status: Filter by status ("open", "in_progress", "closed"). Omit to show all.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by status: open, in_progress, closed. Omit for all.",
                        "enum": ["open", "in_progress", "closed"],
                    }
                },
            },
        ),
        Tool(
            name="create_issue",
            description="""Create a new issue/feature in the project's beads tracker.

Use this when the user wants to create a new feature, task, or bug report.
The issue will be created in the project's local .beads/ directory.

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
                        "description": "Issue title (concise, descriptive)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description with context, implementation steps, and acceptance criteria",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Priority 0-4 (0=critical, 1=high, 2=medium, 3=low, 4=backlog)",
                        "default": 2,
                        "minimum": 0,
                        "maximum": 4,
                    },
                    "category": {
                        "type": "string",
                        "description": "Category label (e.g., 'ui', 'api', 'auth')",
                    },
                    "steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Implementation steps as checklist items",
                    },
                },
                "required": ["title", "description"],
            },
        ),
        Tool(
            name="update_issue",
            description="""Update an existing issue's fields.

IMPORTANT: Always confirm with the user before modifying an issue.
Show them what will change and get explicit approval.

Parameters:
- issue_id: The issue ID to update (required, e.g., "beads-1")
- title: New title (optional)
- description: New description (optional)
- priority: New priority 0-4 (optional)
- category: New category label (optional)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_id": {
                        "type": "string",
                        "description": "Issue ID (e.g., 'beads-1')",
                    },
                    "title": {
                        "type": "string",
                        "description": "New title",
                    },
                    "description": {
                        "type": "string",
                        "description": "New description",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "New priority 0-4",
                        "minimum": 0,
                        "maximum": 4,
                    },
                    "category": {
                        "type": "string",
                        "description": "New category label",
                    },
                },
                "required": ["issue_id"],
            },
        ),
        Tool(
            name="close_issue",
            description="""Close an issue, marking it as done.

IMPORTANT: Always confirm with the user before closing an issue.

Parameters:
- issue_id: The issue ID to close (required, e.g., "beads-1")
- reason: Optional reason for closing""",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_id": {
                        "type": "string",
                        "description": "Issue ID to close (e.g., 'beads-1')",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Optional reason for closing",
                    },
                },
                "required": ["issue_id"],
            },
        ),
        Tool(
            name="reopen_issue",
            description="""Reopen a previously closed issue.

IMPORTANT: Always confirm with the user before reopening an issue.

Parameters:
- issue_id: The issue ID to reopen (required, e.g., "beads-1")""",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_id": {
                        "type": "string",
                        "description": "Issue ID to reopen (e.g., 'beads-1')",
                    },
                },
                "required": ["issue_id"],
            },
        ),
        Tool(
            name="delete_issue",
            description="""Permanently delete an issue from the tracker.

WARNING: This action is permanent and cannot be undone.
IMPORTANT: Always confirm with the user before deleting. Warn them it's permanent.

Parameters:
- issue_id: The issue ID to delete (required, e.g., "beads-1")""",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_id": {
                        "type": "string",
                        "description": "Issue ID to delete (e.g., 'beads-1')",
                    },
                },
                "required": ["issue_id"],
            },
        ),
        Tool(
            name="add_dependency",
            description="""Add a dependency between two issues (A depends on B).

This means issue_id cannot be started until depends_on is completed.
IMPORTANT: Always confirm with the user before adding a dependency.

Parameters:
- issue_id: The issue that depends on another (required)
- depends_on: The issue that must be completed first (required)""",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_id": {
                        "type": "string",
                        "description": "Issue that depends on another (e.g., 'beads-2')",
                    },
                    "depends_on": {
                        "type": "string",
                        "description": "Issue that must be completed first (e.g., 'beads-1')",
                    },
                },
                "required": ["issue_id", "depends_on"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    """Handle tool calls."""
    if not PROJECT_NAME:
        return [TextContent(
            type="text",
            text="Error: PROJECT_NAME environment variable not set",
        )]

    from server.services.beads_manager import get_beads_manager

    try:
        manager = await get_beads_manager(PROJECT_NAME)

        # Validate project directory exists
        success, msg = await manager.ensure_project_exists()
        if not success:
            return [TextContent(type="text", text=f"Error: {msg}")]

        match name:
            case "list_issues":
                return await _handle_list_issues(manager, arguments)
            case "create_issue":
                return await _handle_create_issue(manager, arguments)
            case "update_issue":
                return await _handle_update_issue(manager, arguments)
            case "close_issue":
                return await _handle_close_issue(manager, arguments)
            case "reopen_issue":
                return await _handle_reopen_issue(manager, arguments)
            case "delete_issue":
                return await _handle_delete_issue(manager, arguments)
            case "add_dependency":
                return await _handle_add_dependency(manager, arguments)
            case _:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        logger.exception(f"Error in {name}: {e}")
        return [TextContent(type="text", text=f"Error in {name}: {str(e)}")]


async def _handle_list_issues(manager, arguments: dict):
    """List issues, optionally filtered by status."""
    status_filter = arguments.get("status")
    tasks = manager.get_tasks()

    if status_filter:
        tasks = [t for t in tasks if t.get("status") == status_filter]

    if not tasks:
        filter_msg = f" with status '{status_filter}'" if status_filter else ""
        return [TextContent(type="text", text=f"No issues found{filter_msg}.")]

    lines = []
    for t in tasks:
        labels = t.get("labels", [])
        label_str = f" [{', '.join(labels)}]" if labels else ""
        priority = t.get("priority", "?")
        lines.append(
            f"- {t.get('id', '?')} | P{priority} | {t.get('status', 'open')} | "
            f"{t.get('title', 'Untitled')}{label_str}"
        )

    header = f"Issues ({len(tasks)}):"
    if status_filter:
        header = f"Issues with status '{status_filter}' ({len(tasks)}):"

    return [TextContent(type="text", text=f"{header}\n" + "\n".join(lines))]


async def _handle_create_issue(manager, arguments: dict):
    """Create a new issue."""
    title = arguments.get("title", "")
    description = arguments.get("description", "")
    priority = arguments.get("priority", 2)
    category = arguments.get("category", "")
    steps = arguments.get("steps", [])

    # Format steps into description
    full_description = description
    if steps:
        step_text = "\n".join(f"{i+1}. {step}" for i, step in enumerate(steps))
        if description:
            full_description = f"{description}\n\n{step_text}"
        else:
            full_description = step_text

    labels = [category] if category else None

    logger.info(f"Creating issue: {title}")

    result = await manager.create_issue(
        title=title,
        description=full_description,
        priority=priority,
        labels=labels,
    )

    if "error" in result:
        logger.error(f"Failed to create issue: {result['error']}")
        return [TextContent(type="text", text=f"Error: {result['error']}")]

    data = result.get("data", {})
    issue_id = data.get("id", "unknown") if isinstance(data, dict) else "unknown"

    result_msg = f"Created issue: {issue_id}\nTitle: {title}"
    if category:
        result_msg += f"\nCategory: {category}"
    result_msg += f"\nPriority: P{priority}"
    logger.info(f"Created issue: {issue_id}")

    return [TextContent(type="text", text=result_msg)]


async def _handle_update_issue(manager, arguments: dict):
    """Update an existing issue."""
    issue_id = arguments.get("issue_id", "")
    title = arguments.get("title")
    description = arguments.get("description")
    priority = arguments.get("priority")
    category = arguments.get("category")

    if not any([title, description, priority is not None, category]):
        return [TextContent(type="text", text="Error: No update fields provided. Specify at least one of: title, description, priority, category.")]

    # category maps to labels via update_issue's limited interface;
    # beads update doesn't support labels directly, so we handle it via description note
    # For now, pass what the manager supports
    result = await manager.update_issue(
        issue_id=issue_id,
        title=title,
        description=description,
        priority=priority,
    )

    if "error" in result:
        return [TextContent(type="text", text=f"Error: {result['error']}")]

    updated_fields = []
    if title:
        updated_fields.append(f"title='{title}'")
    if description:
        updated_fields.append("description (updated)")
    if priority is not None:
        updated_fields.append(f"priority=P{priority}")
    if category:
        updated_fields.append(f"category='{category}'")

    return [TextContent(
        type="text",
        text=f"Updated issue {issue_id}: {', '.join(updated_fields)}",
    )]


async def _handle_close_issue(manager, arguments: dict):
    """Close an issue."""
    issue_id = arguments.get("issue_id", "")
    reason = arguments.get("reason")

    result = await manager.close_issue(issue_id, reason)

    if "error" in result:
        return [TextContent(type="text", text=f"Error: {result['error']}")]

    msg = f"Closed issue {issue_id}."
    if reason:
        msg += f" Reason: {reason}"
    return [TextContent(type="text", text=msg)]


async def _handle_reopen_issue(manager, arguments: dict):
    """Reopen a closed issue."""
    issue_id = arguments.get("issue_id", "")

    result = await manager.reopen_issue(issue_id)

    if "error" in result:
        return [TextContent(type="text", text=f"Error: {result['error']}")]

    return [TextContent(type="text", text=f"Reopened issue {issue_id}.")]


async def _handle_delete_issue(manager, arguments: dict):
    """Delete an issue permanently."""
    issue_id = arguments.get("issue_id", "")

    result = await manager.delete_issue(issue_id)

    if "error" in result:
        return [TextContent(type="text", text=f"Error: {result['error']}")]

    return [TextContent(type="text", text=f"Deleted issue {issue_id}. This action is permanent.")]


async def _handle_add_dependency(manager, arguments: dict):
    """Add a dependency between issues."""
    issue_id = arguments.get("issue_id", "")
    depends_on = arguments.get("depends_on", "")

    result = await manager.add_dependency(issue_id, depends_on)

    if "error" in result:
        return [TextContent(type="text", text=f"Error: {result['error']}")]

    return [TextContent(
        type="text",
        text=f"Added dependency: {issue_id} now depends on {depends_on}.",
    )]


async def main():
    """Run the MCP server."""
    logger.info(f"Starting issue-manager MCP server for project: {PROJECT_NAME}")
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
