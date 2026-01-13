"""
Container Manager
=================

Manages Docker containers for per-project Claude Code execution.
Each project gets its own sandboxed container.
"""

import asyncio
import json
import logging
import os
import re
import subprocess
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Awaitable, Callable, Literal, Set

logger = logging.getLogger(__name__)

# Container image name
CONTAINER_IMAGE = "zerocoder-project"

# Idle timeout in minutes
IDLE_TIMEOUT_MINUTES = 60

# Agent health check interval in seconds (10 minutes)
AGENT_HEALTH_CHECK_INTERVAL = 600

# Patterns for sensitive data that should be redacted from output
SENSITIVE_PATTERNS = [
    r'sk-[a-zA-Z0-9]{20,}',  # Anthropic API keys
    r'ANTHROPIC_API_KEY=[^\s]+',
    r'api[_-]?key[=:][^\s]+',
    r'token[=:][^\s]+',
    r'password[=:][^\s]+',
    r'secret[=:][^\s]+',
]


def sanitize_output(line: str) -> str:
    """Remove sensitive information from output lines."""
    for pattern in SENSITIVE_PATTERNS:
        line = re.sub(pattern, '[REDACTED]', line, flags=re.IGNORECASE)
    return line


class ContainerManager:
    """
    Manages a Docker container for a single project.

    Container lifecycle:
    - not_created: Project exists but container never started
    - running: Container is running, Claude Code is active
    - stopped: Container stopped (idle timeout or manual), can restart quickly
    - completed: All features done, container stopped
    """

    def __init__(
        self,
        project_name: str,
        project_dir: Path,
    ):
        """
        Initialize the container manager.

        Args:
            project_name: Name of the project
            project_dir: Absolute path to the project directory
        """
        self.project_name = project_name
        self.project_dir = project_dir
        self.container_name = f"zerocoder-{project_name}"

        self._status: Literal["not_created", "running", "stopped", "completed"] = "not_created"
        self.started_at: datetime | None = None
        self.last_activity: datetime | None = None
        self._log_task: asyncio.Task | None = None

        # Track if user started this container (for auto-restart monitoring)
        self._user_started: bool = False
        # Flag to prevent health monitor conflicts during restart
        self._restarting: bool = False
        # Track if the last agent was overseer (for completion detection)
        self._last_agent_was_overseer: bool = False
        # Track if graceful stop was requested
        self._graceful_stop_requested: bool = False

        # Callbacks for WebSocket notifications
        self._output_callbacks: Set[Callable[[str], Awaitable[None]]] = set()
        self._status_callbacks: Set[Callable[[str], Awaitable[None]]] = set()
        self._callbacks_lock = threading.Lock()

        # Check initial container status
        self._sync_status()

    def _sync_status(self) -> None:
        """Sync status with actual Docker container state."""
        # Preserve "completed" status - don't overwrite it
        if self._status == "completed":
            return

        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Status}}", self.container_name],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                docker_status = result.stdout.strip()
                if docker_status == "running":
                    self._status = "running"
                else:
                    self._status = "stopped"
            else:
                self._status = "not_created"
        except Exception as e:
            logger.warning(f"Failed to check container status: {e}")
            self._status = "not_created"

    @property
    def status(self) -> Literal["not_created", "running", "stopped", "completed"]:
        return self._status

    @status.setter
    def status(self, value: Literal["not_created", "running", "stopped", "completed"]):
        old_status = self._status
        self._status = value
        if old_status != value:
            self._notify_status_change(value)

    def _notify_status_change(self, status: str) -> None:
        """Notify all registered callbacks of status change."""
        with self._callbacks_lock:
            callbacks = list(self._status_callbacks)

        for callback in callbacks:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._safe_callback(callback, status))
            except RuntimeError:
                pass

    async def _safe_callback(self, callback: Callable, *args) -> None:
        """Safely execute a callback, catching and logging any errors."""
        try:
            await callback(*args)
        except Exception as e:
            logger.warning(f"Callback error: {e}")

    def add_output_callback(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Add a callback for output lines."""
        with self._callbacks_lock:
            self._output_callbacks.add(callback)

    def remove_output_callback(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Remove an output callback."""
        with self._callbacks_lock:
            self._output_callbacks.discard(callback)

    def add_status_callback(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Add a callback for status changes."""
        with self._callbacks_lock:
            self._status_callbacks.add(callback)

    def remove_status_callback(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Remove a status callback."""
        with self._callbacks_lock:
            self._status_callbacks.discard(callback)

    def _update_activity(self) -> None:
        """Update last activity timestamp."""
        self.last_activity = datetime.now()

    def is_idle(self) -> bool:
        """Check if container has been idle for longer than timeout."""
        if self.last_activity is None:
            return False
        idle_duration = datetime.now() - self.last_activity
        return idle_duration > timedelta(minutes=IDLE_TIMEOUT_MINUTES)

    def get_idle_seconds(self) -> int:
        """Get seconds since last activity."""
        if self.last_activity is None:
            return 0
        return int((datetime.now() - self.last_activity).total_seconds())

    def is_agent_running(self) -> bool:
        """Check if the agent process is running inside the container."""
        if self._status != "running":
            return False
        try:
            # Check for Python agent_app.py process
            result = subprocess.run(
                ["docker", "exec", self.container_name, "pgrep", "-f", "python.*agent_app"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning(f"Failed to check agent status: {e}")
            return False

    @property
    def user_started(self) -> bool:
        """Whether the user explicitly started this container."""
        return self._user_started

    def has_open_features(self) -> bool:
        """Check if project has open features remaining using cached stats."""
        from .feature_poller import get_cached_stats

        try:
            stats = get_cached_stats(self.project_name)
            open_count = stats.get("pending", 0) + stats.get("in_progress", 0)
            return open_count > 0
        except Exception as e:
            logger.warning(f"Failed to check open features from cache: {e}")
            # Fallback to direct file read (may fail due to permissions)
            return self._has_open_features_direct()

    def _has_open_features_direct(self) -> bool:
        """Fallback: Check open features by reading JSONL directly (may fail due to permissions)."""
        issues_file = self.project_dir / ".beads" / "issues.jsonl"
        if not issues_file.exists():
            return False
        try:
            open_count = 0
            with open(issues_file, "r") as f:
                for line in f:
                    try:
                        issue = json.loads(line.strip())
                        if issue.get("status") in ("open", "in_progress"):
                            open_count += 1
                    except json.JSONDecodeError:
                        continue
            return open_count > 0
        except Exception as e:
            logger.warning(f"Failed to read issues file directly: {e}")
            return False

    async def _broadcast_output(self, line: str) -> None:
        """Broadcast output line to all registered callbacks."""
        with self._callbacks_lock:
            callbacks = list(self._output_callbacks)

        for callback in callbacks:
            await self._safe_callback(callback, line)

    async def _stream_logs(self) -> None:
        """Stream container logs to callbacks."""
        try:
            process = await asyncio.create_subprocess_exec(
                "docker", "logs", "-f", "--tail", "0", self.container_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            while True:
                if process.stdout is None:
                    break

                line = await process.stdout.readline()
                if not line:
                    break

                decoded = line.decode("utf-8", errors="replace").rstrip()
                sanitized = sanitize_output(decoded)

                self._update_activity()
                await self._broadcast_output(sanitized)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Log streaming error: {e}")

    async def start(self, instruction: str | None = None) -> tuple[bool, str]:
        """
        Start or restart the container and optionally send an instruction.

        Args:
            instruction: Optional instruction to send to Claude Code

        Returns:
            Tuple of (success, message)
        """
        self._sync_status()

        if self._status == "running":
            # Container already running, just send instruction if provided
            if instruction:
                self._user_started = True  # Mark as user-started for auto-restart
                return await self.send_instruction(instruction)
            return True, "Container already running"

        try:
            if self._status == "stopped":
                # Restart existing container
                result = subprocess.run(
                    ["docker", "start", self.container_name],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    return False, f"Failed to start container: {result.stderr}"
            else:
                # Create new container with auth tokens from environment
                cmd = [
                    "docker", "run", "-d",
                    "--name", self.container_name,
                    "-v", f"{self.project_dir}:/project",
                ]
                # Pass OAuth token if available
                oauth_token = os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
                if oauth_token:
                    cmd.extend(["-e", f"CLAUDE_CODE_OAUTH_TOKEN={oauth_token}"])
                # Pass API key if available
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if api_key:
                    cmd.extend(["-e", f"ANTHROPIC_API_KEY={api_key}"])
                cmd.append(CONTAINER_IMAGE)

                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    return False, f"Failed to create container: {result.stderr}"

            self.started_at = datetime.now()
            self._update_activity()
            self.status = "running"
            self._user_started = True  # Mark as user-started for monitoring

            # Start log streaming
            self._log_task = asyncio.create_task(self._stream_logs())

            # Send instruction if provided
            if instruction:
                # Wait for Python and agent app to be available
                for attempt in range(10):
                    await asyncio.sleep(2)
                    check = subprocess.run(
                        ["docker", "exec", "-u", "coder", self.container_name,
                         "python", "-c", "import claude_agent_sdk; print('ok')"],
                        capture_output=True,
                        text=True,
                    )
                    if check.returncode == 0:
                        break
                    logger.info(f"Waiting for agent SDK to be ready (attempt {attempt + 1}/10)")
                else:
                    return False, "Agent SDK not available in container after 20 seconds"

                return await self.send_instruction(instruction)

            return True, f"Container {self.container_name} started"

        except Exception as e:
            logger.exception("Failed to start container")
            return False, f"Failed to start container: {e}"

    async def stop(self) -> tuple[bool, str]:
        """
        Stop the container (don't remove it).

        Returns:
            Tuple of (success, message)
        """
        logger.info(f"[STOP] Attempting to stop container {self.container_name}")
        self._sync_status()

        if self._status != "running":
            logger.warning(f"[STOP] Container {self.container_name} is not running, status: {self._status}")
            return False, "Container is not running"

        logger.info(f"[STOP] Container {self.container_name} status confirmed as running")
        try:
            # Cancel log streaming
            if self._log_task:
                self._log_task.cancel()
                try:
                    await self._log_task
                except asyncio.CancelledError:
                    pass

            # Clean up graceful stop flag if exists
            try:
                flag_file = Path(self.project_dir) / ".graceful_stop"
                if flag_file.exists():
                    flag_file.unlink()
                    logger.info(f"Cleaned up graceful stop flag for {self.container_name}")
            except Exception as e:
                logger.warning(f"Failed to clean up graceful stop flag: {e}")

            # Reset graceful stop flag in memory
            self._graceful_stop_requested = False

            # Reset user_started flag to prevent auto-restart
            # User explicitly stopped, so we shouldn't auto-restart
            logger.info(f"[STOP] Resetting _user_started flag for {self.container_name}")
            self._user_started = False

            logger.info(f"[STOP] Executing docker stop for {self.container_name}")
            result = subprocess.run(
                ["docker", "stop", self.container_name],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.error(f"[STOP] Failed to stop {self.container_name}: {result.stderr}")
                return False, f"Failed to stop container: {result.stderr}"

            logger.info(f"[STOP] Successfully stopped {self.container_name}")
            self.status = "stopped"
            return True, f"Container {self.container_name} stopped"

        except subprocess.TimeoutExpired:
            # Force kill
            subprocess.run(
                ["docker", "kill", self.container_name],
                capture_output=True
            )
            self.status = "stopped"
            return True, f"Container {self.container_name} killed (timeout)"
        except Exception as e:
            logger.exception("Failed to stop container")
            return False, f"Failed to stop container: {e}"

    async def graceful_stop(self) -> tuple[bool, str]:
        """
        Request graceful shutdown of agent after current session completes.

        Sets a flag file that the agent checks periodically. Falls back to
        force stop after 10 minutes if agent doesn't exit.

        Returns:
            Tuple of (success, message)
        """
        self._sync_status()

        if self._status != "running":
            return False, "Container is not running"

        # Check if already requested
        if self._graceful_stop_requested:
            return True, "Graceful stop already requested"

        try:
            # Set flag in memory
            self._graceful_stop_requested = True

            # Create flag file in project directory
            flag_file = Path(self.project_dir) / ".graceful_stop"
            flag_file.touch(mode=0o666)  # World-writable for container access

            logger.info(f"Graceful stop requested for {self.container_name}")
            await self._broadcast_output("[System] Graceful stop requested, completing current session...")

            # Start background task to monitor completion with timeout
            asyncio.create_task(self._monitor_graceful_stop())

            return True, "Graceful stop requested"

        except Exception as e:
            logger.exception("Failed to request graceful stop")
            self._graceful_stop_requested = False
            return False, f"Failed to request graceful stop: {e}"

    async def _monitor_graceful_stop(self) -> None:
        """
        Monitor graceful stop with 10-minute timeout.
        Falls back to force stop if timeout exceeded.
        """
        timeout_seconds = 10 * 60  # 10 minutes
        poll_interval = 5  # Check every 5 seconds

        try:
            elapsed = 0
            while elapsed < timeout_seconds:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                # Check if agent has stopped
                if not self.is_agent_running() or self._status != "running":
                    logger.info(f"Agent stopped gracefully in {self.container_name}")
                    return

            # Timeout exceeded - force stop
            logger.warning(f"Graceful stop timeout for {self.container_name}, forcing shutdown")
            await self._broadcast_output("[System] Graceful stop timeout, forcing shutdown...")
            await self.stop()

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception(f"Error monitoring graceful stop: {e}")

    async def send_instruction(self, instruction: str) -> tuple[bool, str]:
        """
        Send an instruction to the Agent SDK app running in the container.

        Uses stdin to pass the prompt to agent_app.py, avoiding shell escaping issues.

        Args:
            instruction: The instruction/prompt to send

        Returns:
            Tuple of (success, message)
        """
        self._sync_status()

        if self._status != "running":
            return False, "Container is not running"

        try:
            self._update_activity()

            # Write prompt to a temp file, then pipe to container via stdin
            # This avoids shell escaping issues with large prompts
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as f:
                f.write(instruction)
                prompt_file = f.name

            try:
                # Use docker exec with stdin to run the Python agent app
                # Run as 'coder' user (non-root) for proper permissions
                # Note: Using create_subprocess_exec (not shell) for security
                with open(prompt_file, "r", encoding="utf-8") as stdin_file:
                    process = await asyncio.create_subprocess_exec(
                        "docker", "exec", "-i", "-u", "coder", self.container_name,
                        "python", "/app/agent_app.py",
                        stdin=stdin_file,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                    )

                    # Stream output to callbacks
                    while True:
                        if process.stdout is None:
                            break
                        line = await process.stdout.readline()
                        if not line:
                            break
                        decoded = line.decode("utf-8", errors="replace").rstrip()
                        sanitized = sanitize_output(decoded)
                        self._update_activity()
                        await self._broadcast_output(sanitized)

                    await process.wait()
                    exit_code = process.returncode or 0

            finally:
                # Clean up temp file
                os.unlink(prompt_file)

            # Handle exit code with enhanced error recovery
            return await self._handle_agent_exit(exit_code)

        except Exception as e:
            logger.exception("Failed to send instruction")
            return False, f"Failed to send instruction: {e}"

    async def _handle_agent_exit(self, exit_code: int) -> tuple[bool, str]:
        """
        Handle agent exit with recovery logic.

        Exit codes:
        - 0: Success
        - 1: Failure (all retries exhausted)
        - 129: Graceful stop requested
        - 130: User interrupt (Ctrl+C)

        Agent flow:
        - If open features exist → restart coding agent
        - If no open features:
          - If last agent was NOT overseer → restart with overseer
          - If last agent WAS overseer → project is truly complete

        Args:
            exit_code: The exit code from the agent process

        Returns:
            Tuple of (success, message)
        """
        # Handle graceful stop - exit code 129 or flag is set
        if exit_code == 129 or self._graceful_stop_requested:
            logger.info(f"Graceful stop completed for {self.container_name}")
            await self._broadcast_output("[System] Graceful stop completed")

            # Clean up flag file
            try:
                flag_file = Path(self.project_dir) / ".graceful_stop"
                if flag_file.exists():
                    flag_file.unlink()
            except Exception as e:
                logger.warning(f"Failed to clean up graceful stop flag: {e}")

            # Reset flag and stop container
            self._graceful_stop_requested = False
            await self.stop()
            return True, "Graceful stop completed"

        if exit_code == 0:
            # Success - determine next action
            logger.info(f"[EXIT] Agent exited successfully (code 0) in {self.container_name}, _user_started={self._user_started}")
            if self._user_started and self.has_open_features():
                # Features remain - restart coding agent
                logger.info(f"[EXIT] Features remain in {self.container_name}, restarting coding agent...")
                await self._broadcast_output("[System] Session complete. Starting fresh context for next task...")
                self._last_agent_was_overseer = False
                return await self.restart_agent()
            elif self._user_started and not self.has_open_features():
                # All features closed - check if overseer already verified
                if self._last_agent_was_overseer:
                    # Overseer found nothing - project is truly complete
                    logger.info(f"Verification complete in {self.container_name}! All features verified.")
                    await self._broadcast_output("[System] Verification complete! All features verified.")
                    await self.stop()
                    self.status = "completed"
                    return True, "All features verified complete"
                else:
                    # Run overseer to verify implementations
                    logger.info(f"All features closed in {self.container_name}, running overseer verification...")
                    await self._broadcast_output("[System] All features complete. Running verification...")
                    return await self.restart_with_overseer()
            else:
                logger.info(f"[EXIT] Not restarting: _user_started={self._user_started}, has_open_features={self.has_open_features()}")
            return True, "Instruction completed"

        elif exit_code == 130:
            # User interrupt - don't auto-restart
            logger.info(f"Agent interrupted in {self.container_name}")
            await self._broadcast_output("[System] Agent interrupted by user")
            return True, "Agent interrupted"

        else:
            # Error - check state file for details and potentially restart
            state_file = self.project_dir / ".agent_state.json"
            error_info = "unknown error"

            if state_file.exists():
                try:
                    state = json.loads(state_file.read_text())
                    error_info = state.get("error", "unknown error")
                    error_type = state.get("error_type", "Exception")
                    logger.error(f"Agent failed in {self.container_name}: {error_type}: {error_info}")
                    await self._broadcast_output(f"[System] Agent error: {error_type}: {error_info}")
                except Exception as e:
                    logger.warning(f"Failed to read agent state: {e}")

            # Auto-restart if user started and features remain
            if self._user_started and self.has_open_features():
                await self._broadcast_output("[System] Auto-restarting after error...")
                await asyncio.sleep(5)  # Brief delay before restart
                self._last_agent_was_overseer = False
                return await self.restart_agent()
            else:
                return False, f"Agent failed: {error_info}"

    async def remove(self) -> tuple[bool, str]:
        """
        Remove the container completely.

        Returns:
            Tuple of (success, message)
        """
        # Stop first if running
        if self._status == "running":
            await self.stop()

        try:
            result = subprocess.run(
                ["docker", "rm", self.container_name],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                if "No such container" in result.stderr:
                    self.status = "not_created"
                    return True, "Container already removed"
                return False, f"Failed to remove container: {result.stderr}"

            self.status = "not_created"
            return True, f"Container {self.container_name} removed"

        except Exception as e:
            logger.exception("Failed to remove container")
            return False, f"Failed to remove container: {e}"

    async def restart_agent(self) -> tuple[bool, str]:
        """
        Restart the agent inside the container.

        This stops and restarts the container, then sends the coding prompt
        to restart Claude Code.

        Returns:
            Tuple of (success, message)
        """
        logger.info(f"Restarting agent in container {self.container_name}")

        self._restarting = True
        try:
            # Stop the container
            await self.stop()

            # Read the coding prompt from the project
            coding_prompt_path = self.project_dir / "prompts" / "coding_prompt.md"
            if not coding_prompt_path.exists():
                return False, "No coding_prompt.md found in project"

            try:
                instruction = coding_prompt_path.read_text()
            except Exception as e:
                return False, f"Failed to read coding prompt: {e}"

            # Mark that we're running coding agent (not overseer)
            self._last_agent_was_overseer = False

            # Start container with instruction
            return await self.start(instruction)
        finally:
            self._restarting = False

    async def restart_with_overseer(self) -> tuple[bool, str]:
        """
        Restart the agent with the overseer prompt.

        This is called when all features are closed to verify implementations.
        The overseer checks for incomplete/placeholder code and creates/reopens issues.

        Returns:
            Tuple of (success, message)
        """
        logger.info(f"Starting overseer verification in container {self.container_name}")

        self._restarting = True
        try:
            # Stop the container
            await self.stop()

            # Read the overseer prompt from the project
            overseer_prompt_path = self.project_dir / "prompts" / "overseer_prompt.md"
            if not overseer_prompt_path.exists():
                # Fall back to template if project-specific doesn't exist
                import sys
                from pathlib import Path
                root = Path(__file__).parent.parent.parent
                if str(root) not in sys.path:
                    sys.path.insert(0, str(root))
                from prompts import get_overseer_prompt
                try:
                    instruction = get_overseer_prompt(self.project_dir)
                except FileNotFoundError:
                    return False, "No overseer_prompt.md found in project or templates"
            else:
                try:
                    instruction = overseer_prompt_path.read_text()
                except Exception as e:
                    return False, f"Failed to read overseer prompt: {e}"

            # Mark that we're running overseer
            self._last_agent_was_overseer = True

            # Start container with instruction
            return await self.start(instruction)
        finally:
            self._restarting = False

    async def start_container_only(self) -> tuple[bool, str]:
        """
        Start the container without starting the agent.

        This is used for editing tasks when the agent isn't needed.
        The container will stay running until idle timeout.

        Returns:
            Tuple of (success, message)
        """
        self._sync_status()

        if self._status == "running":
            return True, "Container already running"

        try:
            if self._status == "stopped" or self._status == "completed":
                # Restart existing container
                result = subprocess.run(
                    ["docker", "start", self.container_name],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    return False, f"Failed to start container: {result.stderr}"
            else:
                # Create new container with auth tokens from environment
                cmd = [
                    "docker", "run", "-d",
                    "--name", self.container_name,
                    "-v", f"{self.project_dir}:/project",
                ]
                # Pass OAuth token if available
                oauth_token = os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
                if oauth_token:
                    cmd.extend(["-e", f"CLAUDE_CODE_OAUTH_TOKEN={oauth_token}"])
                # Pass API key if available
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if api_key:
                    cmd.extend(["-e", f"ANTHROPIC_API_KEY={api_key}"])
                cmd.append(CONTAINER_IMAGE)

                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    return False, f"Failed to create container: {result.stderr}"

            self.started_at = datetime.now()
            self._update_activity()
            self.status = "running"
            # Don't set _user_started - this is just for editing, not agent work

            # Start log streaming
            self._log_task = asyncio.create_task(self._stream_logs())

            return True, f"Container {self.container_name} started (idle mode)"

        except Exception as e:
            logger.exception("Failed to start container")
            return False, f"Failed to start container: {e}"

    def get_status_dict(self) -> dict:
        """Get current status as a dictionary."""
        self._sync_status()
        return {
            "status": self.status,
            "container_name": self.container_name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "idle_seconds": self.get_idle_seconds(),
            "agent_running": self.is_agent_running(),
            "user_started": self._user_started,
            "graceful_stop_requested": self._graceful_stop_requested,
        }


# Global registry of container managers per project
_managers: dict[str, ContainerManager] = {}
_managers_lock = threading.Lock()


def get_container_manager(
    project_name: str,
    project_dir: Path,
) -> ContainerManager:
    """Get or create a container manager for a project (thread-safe)."""
    with _managers_lock:
        if project_name not in _managers:
            _managers[project_name] = ContainerManager(project_name, project_dir)
        return _managers[project_name]


async def cleanup_idle_containers() -> list[str]:
    """
    Stop containers that have been idle for longer than the timeout.

    Returns:
        List of container names that were stopped
    """
    stopped = []

    with _managers_lock:
        managers = list(_managers.values())

    for manager in managers:
        if manager.status == "running" and manager.is_idle():
            success, _ = await manager.stop()
            if success:
                stopped.append(manager.container_name)
                logger.info(f"Stopped idle container: {manager.container_name}")

    return stopped


async def cleanup_all_containers() -> None:
    """Stop all running containers. Called on server shutdown."""
    logger.info("Stopping all zerocoder containers...")

    with _managers_lock:
        managers = list(_managers.values())

    for manager in managers:
        try:
            if manager.status == "running":
                logger.info(f"Stopping container: {manager.container_name}")
                await manager.stop()
        except Exception as e:
            logger.warning(f"Error stopping container for {manager.project_name}: {e}")

    # Also stop any orphaned containers not in our registry
    await stop_orphaned_containers()

    with _managers_lock:
        _managers.clear()


async def stop_orphaned_containers() -> None:
    """Stop any zerocoder-* containers not tracked in our registry."""
    try:
        # List all containers with zerocoder- prefix
        result = subprocess.run(
            ["docker", "ps", "-q", "--filter", "name=zerocoder-"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            container_ids = result.stdout.strip().split("\n")
            for container_id in container_ids:
                if container_id:
                    logger.info(f"Stopping orphaned container: {container_id}")
                    subprocess.run(
                        ["docker", "stop", container_id],
                        capture_output=True,
                        timeout=10,
                    )
    except Exception as e:
        logger.warning(f"Error stopping orphaned containers: {e}")


def check_docker_available() -> bool:
    """Check if Docker is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def check_image_exists() -> bool:
    """Check if the project container image exists."""
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", CONTAINER_IMAGE],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except Exception:
        return False


async def monitor_agent_health() -> list[str]:
    """
    Check health of agents in user-started containers and restart if needed.

    Only monitors containers that were explicitly started by the user.
    If a container is running but the claude process is not, it will be restarted.

    Returns:
        List of container names that were restarted
    """
    restarted = []

    with _managers_lock:
        managers = list(_managers.values())

    for manager in managers:
        # Only monitor user-started containers
        if not manager.user_started:
            continue

        # Skip if restart already in progress
        if manager._restarting:
            continue

        # Only check running containers
        if manager.status != "running":
            continue

        # Check if agent is running
        if not manager.is_agent_running():
            logger.warning(
                f"Agent not running in {manager.container_name}, restarting..."
            )
            try:
                success, message = await manager.restart_agent()
                if success:
                    restarted.append(manager.container_name)
                    logger.info(f"Successfully restarted agent in {manager.container_name}")
                else:
                    logger.error(f"Failed to restart agent in {manager.container_name}: {message}")
            except Exception as e:
                logger.exception(f"Error restarting agent in {manager.container_name}: {e}")

    return restarted


async def start_agent_health_monitor() -> None:
    """
    Start a background task that monitors agent health every AGENT_HEALTH_CHECK_INTERVAL seconds.

    This should be called when the server starts.
    """
    logger.info(f"Starting agent health monitor (interval: {AGENT_HEALTH_CHECK_INTERVAL}s)")

    while True:
        try:
            await asyncio.sleep(AGENT_HEALTH_CHECK_INTERVAL)
            restarted = await monitor_agent_health()
            if restarted:
                logger.info(f"Health check restarted agents: {restarted}")
        except asyncio.CancelledError:
            logger.info("Agent health monitor stopped")
            break
        except Exception as e:
            logger.exception(f"Error in agent health monitor: {e}")
