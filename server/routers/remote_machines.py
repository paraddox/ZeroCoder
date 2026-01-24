"""
Remote Machines Router
======================

CRUD endpoints for managing SSH remote machines.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..schemas import RemoteMachineCreate, RemoteMachineResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/remote-machines", tags=["remote-machines"])


def _get_registry():
    """Lazy import of registry module."""
    import sys
    root = Path(__file__).parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import registry
    return registry


@router.get("", response_model=list[RemoteMachineResponse])
async def list_machines():
    """List all registered remote machines."""
    registry = _get_registry()
    machines = registry.list_remote_machines()
    return machines


@router.post("", response_model=RemoteMachineResponse)
async def add_machine(request: RemoteMachineCreate):
    """Add a new remote machine and test connectivity."""
    registry = _get_registry()

    # Validate SSH key path if provided
    if request.ssh_key_path:
        key_path = Path(request.ssh_key_path).expanduser()
        if not key_path.exists():
            raise HTTPException(status_code=400, detail=f"SSH key not found: {request.ssh_key_path}")

    # Test connectivity before adding
    try:
        import asyncssh
        connect_kwargs: dict = {
            "host": request.host,
            "port": request.port,
            "username": request.username,
            "known_hosts": None,
        }
        if request.ssh_key_path:
            connect_kwargs["client_keys"] = [str(Path(request.ssh_key_path).expanduser())]

        async with asyncssh.connect(**connect_kwargs) as conn:
            result = await conn.run("whoami", check=True)
            logger.info(f"SSH connectivity test passed for {request.host}: {result.stdout.strip()}")
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"SSH connection failed: {str(e)}"
        )

    # Add to registry
    try:
        machine_id = registry.add_remote_machine(
            name=request.name,
            host=request.host,
            port=request.port,
            username=request.username,
            ssh_key_path=request.ssh_key_path,
        )
    except registry.RegistryError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Update status to online after successful connection
    registry.update_remote_machine_status(machine_id, "online")

    machine = registry.get_remote_machine(machine_id)
    return machine


@router.delete("/{machine_id}")
async def remove_machine(machine_id: int):
    """Remove a remote machine."""
    registry = _get_registry()

    if not registry.remove_remote_machine(machine_id):
        raise HTTPException(status_code=404, detail="Machine not found")

    return {"success": True, "message": "Machine removed"}


@router.post("/{machine_id}/test")
async def test_machine(machine_id: int):
    """Test connectivity and check dependencies on a remote machine."""
    registry = _get_registry()

    machine = registry.get_remote_machine(machine_id)
    if not machine:
        raise HTTPException(status_code=404, detail="Machine not found")

    result = {
        "connected": False,
        "user": None,
        "git_installed": False,
        "claude_installed": False,
        "error": None,
    }

    try:
        import asyncssh
        connect_kwargs: dict = {
            "host": machine["host"],
            "port": machine["port"],
            "username": machine["username"],
            "known_hosts": None,
        }
        if machine["ssh_key_path"]:
            connect_kwargs["client_keys"] = [str(Path(machine["ssh_key_path"]).expanduser())]

        async with asyncssh.connect(**connect_kwargs) as conn:
            # Test basic connectivity
            whoami = await conn.run("whoami", check=True)
            result["connected"] = True
            result["user"] = whoami.stdout.strip()

            # Check git
            git_check = await conn.run("which git", check=False)
            result["git_installed"] = git_check.exit_status == 0

            # Check claude
            claude_check = await conn.run("which claude", check=False)
            result["claude_installed"] = claude_check.exit_status == 0

        registry.update_remote_machine_status(machine_id, "online")
    except Exception as e:
        result["error"] = str(e)
        registry.update_remote_machine_status(machine_id, "offline")

    return result
