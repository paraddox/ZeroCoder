"""
Remote Agent Router
===================

Endpoints for controlling agents on remote machines.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..schemas import RemoteAgentStartRequest, RemoteAgentStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["remote-agent"])


def _get_registry():
    """Lazy import of registry module."""
    import sys
    root = Path(__file__).parent.parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import registry
    return registry


@router.post("/{project_name}/remote-agent/start")
async def start_remote_agent(project_name: str, request: RemoteAgentStartRequest):
    """Start an agent on a remote machine for the given project."""
    registry = _get_registry()

    # Validate project exists
    project_info = registry.get_project_info(project_name)
    if not project_info:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate machine exists and is online
    machine = registry.get_remote_machine(request.machine_id)
    if not machine:
        raise HTTPException(status_code=404, detail="Remote machine not found")

    # Get git URL for the project
    git_url = registry.get_project_git_url(project_name)
    if not git_url:
        raise HTTPException(status_code=400, detail="Project has no git URL")

    # Determine agent number (find next available)
    existing_agents = registry.get_remote_agents_for_project(project_name)
    used_numbers = {a["agent_number"] for a in existing_agents if a["machine_id"] == request.machine_id}
    agent_number = 1
    while agent_number in used_numbers:
        agent_number += 1

    # Create agent record
    agent_id = registry.create_remote_agent(project_name, request.machine_id, agent_number)

    # Start the remote manager
    from ..services.remote_machine_manager import get_or_create_remote_manager

    try:
        manager = await get_or_create_remote_manager(
            project_name=project_name,
            machine_id=request.machine_id,
            git_url=git_url,
            agent_number=agent_number,
            agent_id=agent_id,
        )
        success, message = await manager.start()
        if not success:
            raise HTTPException(status_code=500, detail=message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start remote agent: {e}")
        registry.update_remote_agent(agent_id, status="stopped")
        raise HTTPException(status_code=500, detail=str(e))

    return {"success": True, "message": f"Agent started on {machine['name']}", "agent_id": agent_id}


@router.post("/{project_name}/remote-agent/stop")
async def stop_remote_agent(project_name: str):
    """Stop all remote agents for a project."""
    from ..services.remote_machine_manager import get_all_remote_managers

    managers = get_all_remote_managers(project_name)
    if not managers:
        raise HTTPException(status_code=404, detail="No remote agents running")

    results = []
    for manager in managers:
        success, msg = await manager.stop()
        results.append({"agent_number": manager.agent_number, "success": success, "message": msg})

    return {"success": True, "results": results}


@router.post("/{project_name}/remote-agent/graceful-stop")
async def graceful_stop_remote_agent(project_name: str):
    """Request graceful stop for all remote agents."""
    from ..services.remote_machine_manager import get_all_remote_managers

    registry = _get_registry()
    managers = get_all_remote_managers(project_name)
    if not managers:
        raise HTTPException(status_code=404, detail="No remote agents running")

    for manager in managers:
        await manager.graceful_stop()

    return {"success": True, "message": "Graceful stop requested for all remote agents"}


@router.get("/{project_name}/remote-agent/status", response_model=list[RemoteAgentStatusResponse])
async def get_remote_agent_status(project_name: str):
    """Get status of all remote agents for a project."""
    registry = _get_registry()
    agents = registry.get_remote_agents_for_project(project_name)
    return agents
