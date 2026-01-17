"""
WebSocket Handlers
==================

Real-time updates for project progress and agent output.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Set

from fastapi import WebSocket, WebSocketDisconnect

from .services.container_manager import get_all_container_managers

# Lazy imports
_count_passing_tests = None

logger = logging.getLogger(__name__)


def _get_project_path(project_name: str) -> Path:
    """Get project path from registry."""
    import sys
    root = Path(__file__).parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from registry import get_project_path
    return get_project_path(project_name)


def _get_project_git_url(project_name: str) -> str | None:
    """Get project git URL from registry."""
    import sys
    root = Path(__file__).parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from registry import get_project_git_url
    return get_project_git_url(project_name)


def _get_count_passing_tests():
    """Lazy import of count_passing_tests."""
    global _count_passing_tests
    if _count_passing_tests is None:
        import sys
        root = Path(__file__).parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from progress import count_passing_tests
        _count_passing_tests = count_passing_tests
    return _count_passing_tests


async def _send_containers_list(websocket: WebSocket, project_name: str):
    """Send containers list with agent info to the WebSocket client."""
    all_managers = get_all_container_managers(project_name)

    container_list = []
    for cm in all_managers:
        container_info = {
            "number": cm.container_number,
            "type": cm.container_type,
            "agent_type": cm._current_agent_type,
            "sdk_type": "claude" if cm._force_claude_sdk or not cm._is_opencode_model() else "opencode",
        }
        container_list.append(container_info)

    await websocket.send_json({
        "type": "containers",
        "containers": container_list,
    })


class ConnectionManager:
    """Manages WebSocket connections per project."""

    def __init__(self):
        # project_name -> set of WebSocket connections
        self.active_connections: dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, project_name: str):
        """Accept a WebSocket connection for a project."""
        await websocket.accept()

        async with self._lock:
            if project_name not in self.active_connections:
                self.active_connections[project_name] = set()
            self.active_connections[project_name].add(websocket)

    async def disconnect(self, websocket: WebSocket, project_name: str):
        """Remove a WebSocket connection."""
        async with self._lock:
            if project_name in self.active_connections:
                self.active_connections[project_name].discard(websocket)
                if not self.active_connections[project_name]:
                    del self.active_connections[project_name]

    async def broadcast_to_project(self, project_name: str, message: dict):
        """Broadcast a message to all connections for a project."""
        async with self._lock:
            connections = list(self.active_connections.get(project_name, set()))

        dead_connections = []

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)

        # Clean up dead connections
        if dead_connections:
            async with self._lock:
                for connection in dead_connections:
                    if project_name in self.active_connections:
                        self.active_connections[project_name].discard(connection)

    def get_connection_count(self, project_name: str) -> int:
        """Get number of active connections for a project."""
        return len(self.active_connections.get(project_name, set()))


# Global connection manager
manager = ConnectionManager()


def validate_project_name(name: str) -> bool:
    """Validate project name to prevent path traversal."""
    return bool(re.match(r'^[a-zA-Z0-9_-]{1,50}$', name))


async def poll_progress(websocket: WebSocket, project_name: str, project_dir: Path):
    """Poll database for progress changes and send updates.

    Uses cached data when container is running to avoid permission issues.
    """
    count_passing_tests = _get_count_passing_tests()
    last_passing = -1
    last_in_progress = -1
    last_total = -1

    while True:
        try:
            # Pass project_name to enable cache lookup when container is running
            passing, in_progress, total = count_passing_tests(project_dir, project_name)

            # Only send if changed
            if passing != last_passing or in_progress != last_in_progress or total != last_total:
                last_passing = passing
                last_in_progress = in_progress
                last_total = total
                percentage = (passing / total * 100) if total > 0 else 0

                await websocket.send_json({
                    "type": "progress",
                    "passing": passing,
                    "in_progress": in_progress,
                    "total": total,
                    "percentage": round(percentage, 1),
                })

            await asyncio.sleep(2)  # Poll every 2 seconds
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Progress polling error: {e}")
            break


async def project_websocket(websocket: WebSocket, project_name: str):
    """
    WebSocket endpoint for project updates.

    Streams:
    - Progress updates (passing/total counts)
    - Agent status changes
    - Agent stdout/stderr lines
    """
    if not validate_project_name(project_name):
        await websocket.close(code=4000, reason="Invalid project name")
        return

    project_dir = _get_project_path(project_name)
    if not project_dir:
        await websocket.close(code=4004, reason="Project not found in registry")
        return

    if not project_dir.exists():
        await websocket.close(code=4004, reason="Project directory not found")
        return

    git_url = _get_project_git_url(project_name)
    if not git_url:
        await websocket.close(code=4004, reason="Project has no git URL")
        return

    await manager.connect(websocket, project_name)

    # Get all existing container managers for this project and register callbacks
    # Note: Don't pre-create a manager - only use managers that already exist
    # Managers are created when the user starts containers via the Start button
    all_managers = get_all_container_managers(project_name)

    # Create callback factory that captures container_number
    def make_output_callback(container_num: int):
        async def on_output(line: str):
            """Handle agent output - broadcast to this WebSocket with container info."""
            try:
                await websocket.send_json({
                    "type": "log",
                    "line": line,
                    "timestamp": datetime.now().isoformat(),
                    "container_number": container_num,
                })
            except Exception:
                pass  # Connection may be closed
        return on_output

    def make_status_callback(container_num: int, cm: "ContainerManager"):
        async def on_status_change(status: str):
            """Handle status change - broadcast to this WebSocket."""
            try:
                await websocket.send_json({
                    "type": "agent_status",
                    "status": status,
                    "container_number": container_num,
                    "agent_type": cm._current_agent_type,
                    "sdk_type": "claude" if cm._force_claude_sdk or not cm._is_opencode_model() else "opencode",
                })
            except Exception:
                pass  # Connection may be closed
        return on_status_change

    # Register callbacks for all containers and store them for cleanup
    registered_callbacks: list[tuple] = []  # (manager, output_cb, status_cb)
    registered_container_nums: set[int] = set()
    for cm in all_managers:
        output_cb = make_output_callback(cm.container_number)
        status_cb = make_status_callback(cm.container_number, cm)
        cm.add_output_callback(output_cb)
        cm.add_status_callback(status_cb)
        registered_callbacks.append((cm, output_cb, status_cb))
        registered_container_nums.add(cm.container_number)

    # Background task to register callbacks for newly created containers
    async def register_new_container_callbacks():
        """Periodically check for new containers and register callbacks."""
        logger.info(f"[WS] Started callback registration task for {project_name}")
        while True:
            try:
                await asyncio.sleep(2)  # Check every 2 seconds

                current_managers = get_all_container_managers(project_name)
                if current_managers:
                    logger.info(f"[WS] Found {len(current_managers)} managers, registered: {registered_container_nums}")
                for cm in current_managers:
                    if cm.container_number not in registered_container_nums:
                        # New container found - register callbacks
                        output_cb = make_output_callback(cm.container_number)
                        status_cb = make_status_callback(cm.container_number, cm)
                        cm.add_output_callback(output_cb)
                        cm.add_status_callback(status_cb)
                        registered_callbacks.append((cm, output_cb, status_cb))
                        registered_container_nums.add(cm.container_number)

                        logger.info(f"Registered callbacks for new container {cm.container_number}")

                        # Send updated containers list to UI with agent info
                        await _send_containers_list(websocket, project_name)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error checking for new containers: {e}")

    # Start background tasks
    poll_task = asyncio.create_task(poll_progress(websocket, project_name, project_dir))
    callback_registration_task = asyncio.create_task(register_new_container_callbacks())

    try:
        # Send initial status (use first manager's status, or "not_created" if none)
        initial_status = all_managers[0].status if all_managers else "not_created"
        await websocket.send_json({
            "type": "agent_status",
            "status": initial_status,
        })

        # Send initial progress (pass project_name for cache lookup)
        count_passing_tests = _get_count_passing_tests()
        passing, in_progress, total = count_passing_tests(project_dir, project_name)
        percentage = (passing / total * 100) if total > 0 else 0
        await websocket.send_json({
            "type": "progress",
            "passing": passing,
            "in_progress": in_progress,
            "total": total,
            "percentage": round(percentage, 1),
        })

        # Send registered containers list with agent info
        await _send_containers_list(websocket, project_name)

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for any incoming messages (ping/pong, commands, etc.)
                data = await websocket.receive_text()
                message = json.loads(data)

                # Handle ping
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from WebSocket: {data[:100] if data else 'empty'}")
            except Exception as e:
                logger.warning(f"WebSocket error: {e}")
                break

    finally:
        # Clean up background tasks
        poll_task.cancel()
        callback_registration_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass
        try:
            await callback_registration_task
        except asyncio.CancelledError:
            pass

        # Unregister callbacks from all containers
        for cm, output_cb, status_cb in registered_callbacks:
            cm.remove_output_callback(output_cb)
            cm.remove_status_callback(status_cb)

        # Disconnect from manager
        await manager.disconnect(websocket, project_name)
