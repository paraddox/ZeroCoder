"""
Remote Machine Manager
======================

Manages agent lifecycle on remote machines via SSH.
Same callback patterns as ContainerManager for WebSocket integration.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine

import asyncssh

# Lazy registry import
_registry = None


def _get_registry():
    global _registry
    if _registry is None:
        root = Path(__file__).parent.parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        import registry
        _registry = registry
    return _registry


logger = logging.getLogger(__name__)

# Global registry of remote managers: {project_name: {agent_id: RemoteMachineManager}}
_remote_managers: dict[str, dict[int, "RemoteMachineManager"]] = {}


class RemoteMachineManager:
    """Manages a single agent process on a remote machine via SSH."""

    def __init__(
        self,
        project_name: str,
        machine_id: int,
        git_url: str,
        agent_number: int,
        agent_id: int,
    ):
        self.project_name = project_name
        self.machine_id = machine_id
        self.git_url = git_url
        self.agent_number = agent_number
        self.agent_id = agent_id

        self.status = "created"
        self._connection: asyncssh.SSHClientConnection | None = None
        self._process: asyncssh.SSHClientProcess | None = None
        self._output_callbacks: list[Callable[[str], Coroutine]] = []
        self._status_callbacks: list[Callable[[str], Coroutine]] = []
        self._stream_task: asyncio.Task | None = None
        self._machine_config: dict[str, Any] | None = None

    @property
    def machine_name(self) -> str:
        if self._machine_config:
            return self._machine_config.get("name", "unknown")
        return "unknown"

    def add_output_callback(self, callback: Callable[[str], Coroutine]):
        self._output_callbacks.append(callback)

    def remove_output_callback(self, callback: Callable[[str], Coroutine]):
        try:
            self._output_callbacks.remove(callback)
        except ValueError:
            pass

    def add_status_callback(self, callback: Callable[[str], Coroutine]):
        self._status_callbacks.append(callback)

    def remove_status_callback(self, callback: Callable[[str], Coroutine]):
        try:
            self._status_callbacks.remove(callback)
        except ValueError:
            pass

    async def _broadcast_output(self, line: str):
        for cb in list(self._output_callbacks):
            try:
                await cb(line)
            except Exception:
                pass

    async def _broadcast_status(self, status: str):
        self.status = status
        registry = _get_registry()
        registry.update_remote_agent(self.agent_id, status=status)
        for cb in list(self._status_callbacks):
            try:
                await cb(status)
            except Exception:
                pass

    async def _get_connection(self) -> asyncssh.SSHClientConnection:
        """Get or create SSH connection to the remote machine."""
        if self._connection is not None:
            try:
                # Quick check if connection is still alive
                await self._connection.run("true", check=True, timeout=5)
                return self._connection
            except Exception:
                self._connection = None

        registry = _get_registry()
        machine = registry.get_remote_machine(self.machine_id)
        if not machine:
            raise RuntimeError(f"Machine {self.machine_id} not found")

        self._machine_config = machine

        connect_kwargs: dict = {
            "host": machine["host"],
            "port": machine["port"],
            "username": machine["username"],
            "known_hosts": None,
        }
        if machine["ssh_key_path"]:
            connect_kwargs["client_keys"] = [str(Path(machine["ssh_key_path"]).expanduser())]

        self._connection = await asyncssh.connect(**connect_kwargs)
        return self._connection

    async def start(self) -> tuple[bool, str]:
        """Start the agent on the remote machine."""
        try:
            conn = await self._get_connection()
            await self._broadcast_status("running")

            # Setup workspace
            workspace = f"~/zerocoder/{self.project_name}"
            await self._broadcast_output(f"[system] Setting up workspace: {workspace}")

            # Create workspace and clone/update repo
            setup_cmds = f"""
                mkdir -p {workspace} &&
                cd {workspace} &&
                if [ -d .git ]; then
                    git fetch --all && git reset --hard origin/main 2>/dev/null || git reset --hard origin/master
                else
                    cd ~ && rm -rf {workspace} &&
                    git clone {self.git_url} {workspace}
                fi
            """
            result = await conn.run(setup_cmds, check=False)
            if result.exit_status != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown setup error"
                await self._broadcast_output(f"[system] Setup error: {error_msg}")
                await self._broadcast_status("stopped")
                return False, f"Workspace setup failed: {error_msg}"

            await self._broadcast_output("[system] Workspace ready, starting agent...")

            # Build environment variables for the agent
            env_vars = self._build_env_vars()
            env_export = " ".join(f'export {k}="{v}";' for k, v in env_vars.items())

            # Start claude agent
            agent_cmd = (
                f"cd {workspace} && {env_export} "
                f"claude --dangerously-skip-permissions -p "
                f"\"$(cat {workspace}/prompts/coding_prompt.md 2>/dev/null || echo 'Implement the next available feature')\""
            )

            # Start process and stream output
            self._process = await conn.create_process(
                agent_cmd,
                stderr=asyncssh.STDOUT,
            )

            # Get PID
            pid_result = await conn.run(f"echo $!", check=False)
            pid = None
            if pid_result.stdout.strip().isdigit():
                pid = int(pid_result.stdout.strip())

            registry = _get_registry()
            registry.update_remote_agent(self.agent_id, status="running", pid=pid)

            # Start output streaming task
            self._stream_task = asyncio.create_task(self._stream_output())

            return True, "Agent started successfully"

        except Exception as e:
            logger.error(f"Failed to start remote agent: {e}")
            await self._broadcast_status("stopped")
            return False, str(e)

    async def _stream_output(self):
        """Stream output from the SSH process."""
        try:
            if not self._process or not self._process.stdout:
                return

            async for line in self._process.stdout:
                line = line.rstrip('\n')
                if line:
                    await self._broadcast_output(line)

                    # Update activity timestamp
                    registry = _get_registry()
                    registry.update_remote_agent(self.agent_id)

            # Process exited
            exit_status = self._process.exit_status
            await self._broadcast_output(f"[system] Agent exited with code {exit_status}")
            await self._handle_agent_exit(exit_status)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error streaming remote output: {e}")
            await self._broadcast_status("stopped")

    async def _handle_agent_exit(self, exit_code: int | None):
        """Handle agent process exit - restart or mark stopped."""
        registry = _get_registry()
        agent = registry.get_remote_agent(self.agent_id)
        if not agent:
            await self._broadcast_status("stopped")
            return

        if agent.get("graceful_stop_requested"):
            await self._broadcast_output("[system] Graceful stop - not restarting")
            await self._broadcast_status("stopped")
            return

        # Auto-restart if not graceful stop
        await self._broadcast_output("[system] Agent exited, restarting...")
        registry.update_remote_agent(self.agent_id, restarting=True)
        await asyncio.sleep(5)
        await self.restart_agent()

    async def stop(self) -> tuple[bool, str]:
        """Force stop the agent on the remote machine."""
        try:
            if self._stream_task:
                self._stream_task.cancel()
                try:
                    await self._stream_task
                except asyncio.CancelledError:
                    pass

            if self._process:
                self._process.terminate()
                await asyncio.sleep(2)
                try:
                    self._process.kill()
                except Exception:
                    pass
                self._process = None

            # Also kill by PID on remote
            registry = _get_registry()
            agent = registry.get_remote_agent(self.agent_id)
            if agent and agent.get("pid"):
                try:
                    conn = await self._get_connection()
                    await conn.run(f"kill -9 {agent['pid']} 2>/dev/null", check=False)
                except Exception:
                    pass

            # Kill any claude processes for this project
            try:
                conn = await self._get_connection()
                await conn.run(
                    f"pkill -f 'claude.*zerocoder/{self.project_name}' 2>/dev/null",
                    check=False,
                )
            except Exception:
                pass

            await self._broadcast_status("stopped")
            registry.update_remote_agent(self.agent_id, status="stopped", pid=0)

            return True, "Agent stopped"
        except Exception as e:
            logger.error(f"Error stopping remote agent: {e}")
            return False, str(e)

    async def graceful_stop(self) -> tuple[bool, str]:
        """Request graceful stop - agent finishes current work then stops."""
        registry = _get_registry()
        registry.update_remote_agent(self.agent_id, graceful_stop_requested=True)
        await self._broadcast_output("[system] Graceful stop requested - finishing current work")
        return True, "Graceful stop requested"

    async def is_agent_running(self) -> bool:
        """Check if the agent process is running on the remote machine."""
        registry = _get_registry()
        agent = registry.get_remote_agent(self.agent_id)
        if not agent or not agent.get("pid"):
            return False

        try:
            conn = await self._get_connection()
            result = await conn.run(f"kill -0 {agent['pid']} 2>/dev/null", check=False)
            return result.exit_status == 0
        except Exception:
            return False

    async def restart_agent(self) -> tuple[bool, str]:
        """Restart the agent process."""
        registry = _get_registry()
        registry.update_remote_agent(self.agent_id, restarting=True, graceful_stop_requested=False)
        await self.stop()
        await asyncio.sleep(2)
        registry.update_remote_agent(self.agent_id, restarting=False)
        return await self.start()

    async def close(self):
        """Close SSH connection and clean up."""
        if self._stream_task:
            self._stream_task.cancel()
        if self._connection:
            self._connection.close()
            self._connection = None

    def _build_env_vars(self) -> dict[str, str]:
        """Build environment variables for the remote agent."""
        env = {}

        # Pass API key
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if api_key:
            env["ANTHROPIC_API_KEY"] = api_key

        # Project info
        env["PROJECT_NAME"] = self.project_name
        env["CONTAINER_NUMBER"] = str(self.agent_number)

        # Host API URL for callbacks (graceful stop checks, beads API)
        host_api = os.getenv("HOST_API_URL", "")
        if host_api:
            env["HOST_API_URL"] = host_api

        return env


# =============================================================================
# Global Manager Registry
# =============================================================================

async def get_or_create_remote_manager(
    project_name: str,
    machine_id: int,
    git_url: str,
    agent_number: int,
    agent_id: int,
) -> RemoteMachineManager:
    """Get or create a remote machine manager instance."""
    if project_name not in _remote_managers:
        _remote_managers[project_name] = {}

    if agent_id in _remote_managers[project_name]:
        return _remote_managers[project_name][agent_id]

    manager = RemoteMachineManager(
        project_name=project_name,
        machine_id=machine_id,
        git_url=git_url,
        agent_number=agent_number,
        agent_id=agent_id,
    )
    _remote_managers[project_name][agent_id] = manager
    return manager


def get_all_remote_managers(project_name: str) -> list[RemoteMachineManager]:
    """Get all remote managers for a project."""
    if project_name not in _remote_managers:
        return []
    return list(_remote_managers[project_name].values())


async def cleanup_all_remote_managers():
    """Close all SSH connections and clean up managers."""
    for project_managers in _remote_managers.values():
        for manager in project_managers.values():
            await manager.close()
    _remote_managers.clear()
