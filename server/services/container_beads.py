"""
Container Beads Client
======================

Sends beads commands to containers via docker exec.
All beads operations are routed through this client to avoid permission issues.
"""

import asyncio
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_container_name(project_name: str) -> str:
    """Get Docker container name for a project."""
    return f"zerocoder-{project_name}"


async def send_beads_command(project_name: str, command: dict, timeout: int = 30) -> dict:
    """
    Send a beads command to the container via docker exec.

    Args:
        project_name: Name of the project
        command: Command dict with 'action' and other fields
        timeout: Timeout in seconds

    Returns:
        Result dict from container script

    Raises:
        RuntimeError: If command fails or container not running
    """
    container_name = get_container_name(project_name)
    command_json = json.dumps(command)

    try:
        # Use docker exec with stdin
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", "-i", "-u", "coder", container_name,
            "python", "/app/beads_commands.py",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=command_json.encode()),
            timeout=timeout
        )

        if proc.returncode != 0:
            error_msg = stderr.decode().strip() if stderr else "Unknown error"
            logger.error(f"Container command failed: {error_msg}")
            raise RuntimeError(f"Container command failed: {error_msg}")

        # Parse JSON response
        result = json.loads(stdout.decode())
        return result

    except asyncio.TimeoutError:
        logger.error(f"Container command timed out after {timeout}s")
        raise RuntimeError(f"Container command timed out after {timeout}s")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON response from container: {e}")
        raise RuntimeError(f"Invalid JSON response from container: {e}")
    except Exception as e:
        logger.error(f"Failed to send command to container: {e}")
        raise RuntimeError(f"Failed to send command to container: {e}")


def send_beads_command_sync(project_name: str, command: dict, timeout: int = 30) -> dict:
    """
    Synchronous version of send_beads_command.
    Uses subprocess directly instead of asyncio.
    """
    import subprocess

    container_name = get_container_name(project_name)
    command_json = json.dumps(command)

    try:
        result = subprocess.run(
            ["docker", "exec", "-i", "-u", "coder", container_name,
             "python", "/app/beads_commands.py"],
            input=command_json.encode(),
            capture_output=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            error_msg = result.stderr.decode().strip() if result.stderr else "Unknown error"
            logger.error(f"Container command failed: {error_msg}")
            raise RuntimeError(f"Container command failed: {error_msg}")

        # Parse JSON response
        return json.loads(result.stdout.decode())

    except subprocess.TimeoutExpired:
        logger.error(f"Container command timed out after {timeout}s")
        raise RuntimeError(f"Container command timed out after {timeout}s")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON response from container: {e}")
        raise RuntimeError(f"Invalid JSON response from container: {e}")
    except Exception as e:
        logger.error(f"Failed to send command to container: {e}")
        raise RuntimeError(f"Failed to send command to container: {e}")


class ContainerBeadsClient:
    """
    Client for beads operations via container.
    Routes all beads commands through docker exec to avoid permission issues.
    """

    def __init__(self, project_name: str):
        self.project_name = project_name

    def is_container_running(self) -> bool:
        """Check if the container is running."""
        from .container_manager import _managers, _managers_lock

        with _managers_lock:
            manager = _managers.get(self.project_name)
            return manager is not None and manager.status == "running"

    async def list_all(self) -> list[dict]:
        """List all features."""
        result = await send_beads_command(self.project_name, {"action": "list"})
        if result.get("success"):
            return result.get("features", [])
        return []

    async def get_feature(self, feature_id: str) -> dict | None:
        """Get a single feature by ID."""
        result = await send_beads_command(
            self.project_name,
            {"action": "get", "feature_id": feature_id}
        )
        if result.get("success"):
            return result.get("feature")
        return None

    async def create(
        self,
        name: str,
        category: str = "",
        description: str = "",
        steps: list[str] | None = None,
        priority: int = 999,
    ) -> str | None:
        """Create a new feature."""
        result = await send_beads_command(
            self.project_name,
            {
                "action": "create",
                "data": {
                    "name": name,
                    "category": category,
                    "description": description,
                    "steps": steps or [],
                    "priority": priority,
                },
            }
        )
        if result.get("success"):
            feature = result.get("feature", {})
            return feature.get("id") or result.get("feature_id")
        return None

    async def update(
        self,
        feature_id: str,
        name: str | None = None,
        description: str | None = None,
        priority: int | None = None,
        category: str | None = None,
        steps: list[str] | None = None,
    ) -> dict | None:
        """Update a feature's fields."""
        data = {}
        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if priority is not None:
            data["priority"] = priority
        if category is not None:
            data["category"] = category
        if steps is not None:
            data["steps"] = steps

        result = await send_beads_command(
            self.project_name,
            {"action": "update", "feature_id": feature_id, "data": data}
        )
        if result.get("success"):
            return result.get("feature")
        return None

    async def delete(self, feature_id: str) -> bool:
        """Delete a feature."""
        result = await send_beads_command(
            self.project_name,
            {"action": "delete", "feature_id": feature_id}
        )
        return result.get("success", False)

    async def skip(self, feature_id: str) -> dict | None:
        """Skip a feature by setting priority to P4."""
        result = await send_beads_command(
            self.project_name,
            {"action": "skip", "feature_id": feature_id}
        )
        if result.get("success"):
            return result
        if "error" in result:
            return {"error": result["error"]}
        return None

    async def reopen(self, feature_id: str) -> dict | None:
        """Reopen a closed feature."""
        result = await send_beads_command(
            self.project_name,
            {"action": "reopen", "feature_id": feature_id}
        )
        if result.get("success"):
            return result.get("feature")
        return None

    async def init(self) -> bool:
        """Initialize beads in the project."""
        result = await send_beads_command(
            self.project_name,
            {"action": "init"}
        )
        return result.get("success", False)

    async def get_stats(self) -> dict:
        """Get feature statistics."""
        result = await send_beads_command(self.project_name, {"action": "list"})
        if result.get("success"):
            return result.get("stats", {})
        return {"pending": 0, "in_progress": 0, "done": 0, "total": 0, "percentage": 0.0}
