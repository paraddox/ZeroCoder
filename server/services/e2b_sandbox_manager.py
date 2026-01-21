"""
E2B Sandbox Manager
====================

Manages E2B cloud sandboxes for running Claude Agent SDK.
Replaces ContainerManager with the same API surface but using E2B sandboxes
instead of Docker containers.

Key differences from Docker:
- Sandboxes are created via E2B API (not local Docker)
- SSH key passed via environment variable (base64 encoded)
- Host API must be publicly accessible (no host.docker.internal)
- 5-minute idle timeout for cost optimization
"""

import asyncio
import base64
import logging
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable

from e2b import AsyncSandbox

logger = logging.getLogger(__name__)

# Path to e2b_template directory containing setup scripts
E2B_TEMPLATE_DIR = Path(__file__).parent.parent.parent / "e2b_template"

# E2B configuration
# Use code-interpreter-v1 template by default (has 2GB RAM)
# Set E2B_TEMPLATE_ID env var to override
E2B_TEMPLATE_ID = os.environ.get("E2B_TEMPLATE_ID") or "code-interpreter-v1"
E2B_SANDBOX_TIMEOUT = int(os.environ.get("E2B_SANDBOX_TIMEOUT", "300"))  # 5 minutes default
E2B_API_KEY = os.environ.get("E2B_API_KEY", "")

# Environment variables for sandbox
HOST_API_URL = os.environ.get("HOST_API_URL", "")  # Must be publicly accessible
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY", "")
SSH_PRIVATE_KEY_BASE64 = os.environ.get("SSH_PRIVATE_KEY_BASE64", "")

# If SSH_PRIVATE_KEY_BASE64 not set, try to read from GIT_SSH_KEY_PATH or default
if not SSH_PRIVATE_KEY_BASE64:
    # First check GIT_SSH_KEY_PATH env var, then default to ~/.ssh/id_ed25519
    git_ssh_key_path = os.environ.get("GIT_SSH_KEY_PATH", "")
    if git_ssh_key_path:
        ssh_key_path = Path(git_ssh_key_path).expanduser()
    else:
        ssh_key_path = Path.home() / ".ssh" / "id_ed25519"

    if ssh_key_path.exists():
        SSH_PRIVATE_KEY_BASE64 = base64.b64encode(ssh_key_path.read_bytes()).decode()
        logger.info(f"Loaded SSH key from {ssh_key_path}")


def sanitize_output(line: str) -> str:
    """Remove ANSI escape codes and sensitive data from output."""
    # Remove ANSI escape sequences
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    line = ansi_escape.sub('', line)
    # Remove potential API keys (Anthropic, OpenAI)
    line = re.sub(r'sk-ant-[a-zA-Z0-9-]+', '[REDACTED]', line)
    line = re.sub(r'sk-[a-zA-Z0-9]+', '[REDACTED]', line)
    # Remove common sensitive patterns (password, token, secret, key)
    line = re.sub(r'(password|token|secret|api_key|apikey|auth)=\S+', r'\1=[REDACTED]', line, flags=re.IGNORECASE)
    # Remove GitHub tokens
    line = re.sub(r'ghp_[a-zA-Z0-9]+', '[REDACTED]', line)
    line = re.sub(r'github_pat_[a-zA-Z0-9_]+', '[REDACTED]', line)
    return line


class E2BSandboxManager:
    """
    Manages a single E2B sandbox for a project.

    Provides the same API surface as ContainerManager but uses E2B cloud sandboxes
    instead of Docker containers.
    """

    def __init__(
        self,
        project_name: str,
        git_url: str,
        container_number: int = 1,
        project_dir: Path | None = None,
    ):
        """
        Initialize sandbox manager.

        Args:
            project_name: Name of the project
            git_url: Git URL for the project repository
            container_number: Container/sandbox number (0 = init, 1-10 = coding)
            project_dir: Optional local clone path (for wizard/edit mode)
        """
        self.project_name = project_name
        self.git_url = git_url
        self.container_number = container_number

        # Determine container type based on number
        self._is_init_container = container_number == 0
        self.container_type = "init" if self._is_init_container else "coding"

        # Container name (for compatibility with existing code)
        if self._is_init_container:
            self.container_name = f"zerocoder-{project_name}-init"
        else:
            self.container_name = f"zerocoder-{project_name}-{container_number}"

        # Project directory (local clone for wizard, or remote via git_url)
        if project_dir:
            self.project_dir = Path(project_dir)
        else:
            from registry import get_projects_dir
            self.project_dir = get_projects_dir() / project_name

        # E2B sandbox state
        self._sandbox: AsyncSandbox | None = None
        self._sandbox_id: str | None = None
        self._agent_pid: int | None = None

        # Sandbox paths (set during environment preparation)
        self._sandbox_home: str = "/home/user"
        self._sandbox_app_dir: str = "/home/user/app"
        self._sandbox_project_dir: str = "/home/user/project"

        # Status tracking
        self._status = "not_created"
        self.started_at: datetime | None = None
        self._last_activity: datetime | None = None

        # User/session state (DB-backed via properties)
        self._user_started_cache: bool | None = None
        self._graceful_stop_requested_cache: bool | None = None
        self._current_feature: str | None = None
        self._current_agent_type: str = "coder"
        self._last_agent_was_overseer: bool = False
        self._is_milestone_overseer: bool = False
        self._force_claude_sdk: bool = False
        self._forced_model: str | None = None
        self._restarting: bool = False

        # Callback registrations
        self._output_callbacks: list[Callable[[str], Awaitable[None]]] = []
        self._status_callbacks: list[Callable[[str], Awaitable[None]]] = []
        self._callbacks_lock = threading.Lock()

        # Background tasks
        self._output_task: asyncio.Task | None = None

    @property
    def status(self) -> str:
        """Get current status."""
        return self._status

    @status.setter
    def status(self, value: str) -> None:
        """Set status and notify callbacks."""
        old_status = self._status
        self._status = value
        if old_status != value:
            asyncio.create_task(self._broadcast_status(value))

    @property
    def _user_started(self) -> bool:
        """Check if container was user-started (DB-backed)."""
        if self._user_started_cache is not None:
            return self._user_started_cache

        try:
            from registry import is_user_started
            self._user_started_cache = is_user_started(
                self.project_name, self.container_number, self.container_type
            )
            return self._user_started_cache or False
        except Exception:
            return False

    @_user_started.setter
    def _user_started(self, value: bool) -> None:
        """Set user-started flag (DB-backed)."""
        self._user_started_cache = value
        try:
            from registry import set_user_started
            set_user_started(
                self.project_name, self.container_number, value, self.container_type
            )
        except Exception as e:
            logger.warning(f"Failed to persist user_started: {e}")

    @property
    def _graceful_stop_requested(self) -> bool:
        """Check if graceful stop was requested (DB-backed)."""
        if self._graceful_stop_requested_cache is not None:
            return self._graceful_stop_requested_cache

        try:
            from registry import is_graceful_stop_requested
            self._graceful_stop_requested_cache = is_graceful_stop_requested(
                self.project_name, self.container_number, self.container_type
            )
            return self._graceful_stop_requested_cache or False
        except Exception:
            return False

    @_graceful_stop_requested.setter
    def _graceful_stop_requested(self, value: bool) -> None:
        """Set graceful stop flag (DB-backed)."""
        self._graceful_stop_requested_cache = value
        try:
            from registry import set_graceful_stop
            set_graceful_stop(
                self.project_name, self.container_number, value, self.container_type
            )
        except Exception as e:
            logger.warning(f"Failed to persist graceful_stop: {e}")

    def _update_activity(self) -> None:
        """Update last activity timestamp."""
        self._last_activity = datetime.now()

    def get_idle_seconds(self) -> int:
        """Get seconds since last activity."""
        if not self._last_activity:
            return 0
        return int((datetime.now() - self._last_activity).total_seconds())

    def is_idle(self) -> bool:
        """Check if sandbox has been idle too long."""
        return self.get_idle_seconds() > E2B_SANDBOX_TIMEOUT

    def is_agent_stuck(self) -> bool:
        """Check if agent is running but not producing output (stuck).

        This detects scenarios where the agent process is alive but hung,
        e.g., API not responding, network timeout, etc.
        """
        if self._last_activity is None:
            return False
        # Only consider stuck if agent is supposedly running
        if not self.is_agent_running():
            return False
        # Check if idle time exceeds stuck timeout (10 minutes)
        return self.get_idle_seconds() > 600  # AGENT_STUCK_TIMEOUT_SECONDS

    def register_output_callback(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Register callback for output streaming."""
        with self._callbacks_lock:
            if callback not in self._output_callbacks:
                self._output_callbacks.append(callback)

    def unregister_output_callback(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Unregister output callback."""
        with self._callbacks_lock:
            if callback in self._output_callbacks:
                self._output_callbacks.remove(callback)

    def register_status_callback(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Register callback for status changes."""
        with self._callbacks_lock:
            if callback not in self._status_callbacks:
                self._status_callbacks.append(callback)

    def unregister_status_callback(self, callback: Callable[[str], Awaitable[None]]) -> None:
        """Unregister status callback."""
        with self._callbacks_lock:
            if callback in self._status_callbacks:
                self._status_callbacks.remove(callback)

    async def _safe_callback(self, callback: Callable, *args) -> None:
        """Safely invoke a callback, logging any errors."""
        try:
            await callback(*args)
        except Exception as e:
            logger.warning(f"Callback error: {e}")

    async def _broadcast_output(self, line: str) -> None:
        """Broadcast output line to all registered callbacks."""
        with self._callbacks_lock:
            callbacks = list(self._output_callbacks)

        for callback in callbacks:
            await self._safe_callback(callback, line)

    async def _broadcast_status(self, status: str) -> None:
        """Broadcast status change to all registered callbacks."""
        with self._callbacks_lock:
            callbacks = list(self._status_callbacks)

        for callback in callbacks:
            await self._safe_callback(callback, status)

    def _get_sandbox_envs(self) -> dict[str, str]:
        """Get environment variables for the sandbox."""
        envs = {
            "GIT_REMOTE_URL": self.git_url,
            "PROJECT_NAME": self.project_name,
            "CONTAINER_NUMBER": str(self.container_number),
            "CONTAINER_TYPE": self.container_type,
        }

        # SSH key for git clone
        if SSH_PRIVATE_KEY_BASE64:
            envs["SSH_PRIVATE_KEY_BASE64"] = SSH_PRIVATE_KEY_BASE64

        # Host API URL (must be publicly accessible)
        if HOST_API_URL:
            envs["HOST_API_URL"] = HOST_API_URL
        else:
            logger.warning("HOST_API_URL not set - beads operations will fail")

        # API keys
        if ANTHROPIC_API_KEY:
            envs["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
        if ZHIPU_API_KEY:
            envs["ZHIPU_API_KEY"] = ZHIPU_API_KEY

        # OAuth token if available
        oauth_token = os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
        if oauth_token:
            envs["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token

        # Timezone
        tz = os.getenv("TZ")
        if tz:
            envs["TZ"] = tz

        return envs

    async def _prepare_sandbox_environment(self) -> tuple[bool, str]:
        """
        Prepare the sandbox environment by uploading necessary files.

        This is needed when using the default E2B template instead of
        a custom template with pre-installed files.

        Creates:
        - ~/app/setup_sandbox.sh - Sandbox setup script
        - ~/app/agent_app.py - Claude Agent SDK application
        - ~/project/ - Working directory for the project
        - ~/.ssh/ - SSH directory for git operations
        """
        if not self._sandbox:
            return False, "Sandbox not created"

        try:
            await self._broadcast_output("[System] Preparing sandbox environment...")

            # Get user home directory
            home_result = await self._sandbox.commands.run("echo $HOME")
            home_dir = home_result.stdout.strip() or "/home/user"

            app_dir = f"{home_dir}/app"
            project_dir = f"{home_dir}/project"
            ssh_dir = f"{home_dir}/.ssh"

            # Create directories
            mkdir_cmd = f"mkdir -p {app_dir} {project_dir} {ssh_dir}"
            logger.info(f"Running mkdir command: {mkdir_cmd}")
            await self._sandbox.commands.run(mkdir_cmd)

            # Configure SSH for github.com
            ssh_config = f"""Host github.com
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    IdentityFile {ssh_dir}/id_ed25519
"""
            await self._sandbox.files.write(f"{ssh_dir}/config", ssh_config)
            await self._sandbox.commands.run(f"chmod 600 {ssh_dir}/config")

            # Upload setup script (modify paths for user home)
            setup_script_path = E2B_TEMPLATE_DIR / "setup_sandbox.sh"
            if setup_script_path.exists():
                setup_content = setup_script_path.read_text()
                # Replace hardcoded paths with user home paths
                setup_content = setup_content.replace("/root/.ssh", f"{ssh_dir}")
                setup_content = setup_content.replace('PROJECT_DIR="/project"', f'PROJECT_DIR="{project_dir}"')
                await self._sandbox.files.write(f"{app_dir}/setup_sandbox.sh", setup_content)
                await self._sandbox.commands.run(f"chmod +x {app_dir}/setup_sandbox.sh")
            else:
                return False, f"Setup script not found: {setup_script_path}"

            # Upload agent app (modify paths for user home)
            agent_app_path = E2B_TEMPLATE_DIR / "agent_app.py"
            if agent_app_path.exists():
                agent_content = agent_app_path.read_text()
                # Replace hardcoded paths
                agent_content = agent_content.replace('"/project"', f'"{project_dir}"')
                agent_content = agent_content.replace('Path("/project', f'Path("{project_dir}')
                await self._sandbox.files.write(f"{app_dir}/agent_app.py", agent_content)
            else:
                return False, f"Agent app not found: {agent_app_path}"

            # Store paths for later use
            self._sandbox_home = home_dir
            self._sandbox_app_dir = app_dir
            self._sandbox_project_dir = project_dir

            # Install required Python packages
            await self._broadcast_output("[System] Installing Python dependencies...")
            install_result = await self._sandbox.commands.run(
                "pip install requests claude-agent-sdk --quiet",
                timeout=120,
            )

            if install_result.exit_code != 0:
                logger.warning(f"pip install warning: {install_result.stderr}")

            # Install Claude Code CLI (requires Node.js)
            await self._broadcast_output("[System] Installing Claude Code CLI...")
            # Check if Node.js is available
            node_check = await self._sandbox.commands.run("which node || echo 'not found'")
            if "not found" in node_check.stdout:
                logger.warning("Node.js not available in sandbox - trying to install")
                await self._sandbox.commands.run(
                    "curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y nodejs",
                    timeout=180,
                )

            # Install Claude Code CLI to user's local npm directory (avoids permission issues)
            npm_prefix = f"{home_dir}/.npm-global"
            await self._sandbox.commands.run(f"mkdir -p {npm_prefix}")
            await self._sandbox.commands.run(f"npm config set prefix {npm_prefix}")

            claude_install = await self._sandbox.commands.run(
                f"PATH={npm_prefix}/bin:$PATH npm install -g @anthropic-ai/claude-code",
                timeout=180,
            )
            if claude_install.exit_code != 0:
                logger.warning(f"Claude Code CLI install warning: {claude_install.stderr}")
            else:
                logger.info("Claude Code CLI installed successfully")

            # Verify claude is accessible
            verify_result = await self._sandbox.commands.run(
                f"PATH={npm_prefix}/bin:$PATH claude --version",
                timeout=30,
            )
            if verify_result.exit_code != 0:
                logger.warning(f"Claude CLI verification failed: {verify_result.stderr}")
            else:
                logger.info(f"Claude CLI version: {verify_result.stdout.strip()}")

            # Test claude authentication
            oauth_token = os.getenv("CLAUDE_CODE_OAUTH_TOKEN", "")
            if oauth_token:
                auth_test = await self._sandbox.commands.run(
                    f"PATH={npm_prefix}/bin:$PATH CLAUDE_CODE_OAUTH_TOKEN={oauth_token} claude -p 'Say hello' --max-turns 1 2>&1 || echo 'AUTH_FAILED'",
                    timeout=60,
                )
                logger.info(f"Claude auth test result (exit={auth_test.exit_code}): {auth_test.stdout[:200] if auth_test.stdout else 'no output'}...")

            # Create symlink for claude in a standard location
            await self._sandbox.commands.run(
                f"ln -sf {npm_prefix}/bin/claude /usr/local/bin/claude 2>/dev/null || sudo ln -sf {npm_prefix}/bin/claude /usr/local/bin/claude 2>/dev/null || true"
            )

            # Add npm-global/bin to PATH for future commands
            await self._sandbox.commands.run(
                f"echo 'export PATH={npm_prefix}/bin:$PATH' >> {home_dir}/.bashrc"
            )

            await self._broadcast_output("[System] Environment prepared")
            return True, "Environment prepared"

        except Exception as e:
            logger.exception("Failed to prepare sandbox environment")
            return False, f"Failed to prepare environment: {e}"

    async def _sync_status(self) -> None:
        """Sync status with actual sandbox state."""
        if self._sandbox_id:
            try:
                # Try to connect to existing sandbox
                self._sandbox = await AsyncSandbox.connect(self._sandbox_id)
                is_running = await self._sandbox.is_running()
                if is_running:
                    self._status = "running"
                else:
                    self._status = "stopped"
                    self._sandbox = None
            except Exception:
                # Sandbox no longer exists
                self._status = "not_created"
                self._sandbox = None
                self._sandbox_id = None
        elif self._sandbox:
            try:
                is_running = await self._sandbox.is_running()
                if is_running:
                    self._status = "running"
                else:
                    self._status = "stopped"
            except Exception:
                self._status = "not_created"
                self._sandbox = None

    def is_agent_running(self) -> bool:
        """Check if agent process is currently running."""
        if not self._sandbox or self._agent_pid is None:
            return False

        try:
            # Run synchronously for compatibility with existing code
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context, need to check differently
                # Return cached state based on whether we have an active PID
                return self._agent_pid is not None
            else:
                processes = asyncio.run(self._sandbox.commands.list())
                return any(p.pid == self._agent_pid for p in processes)
        except Exception:
            return False

    def has_open_features(self) -> bool:
        """Check if project has open features remaining."""
        from .beads_manager import get_beads_sync_manager

        try:
            manager = get_beads_sync_manager(self.project_name, self.git_url)
            open_tasks = manager.get_tasks_by_status("open")
            in_progress = manager.get_tasks_by_status("in_progress")
            return len(open_tasks) + len(in_progress) > 0
        except Exception as e:
            logger.warning(f"Failed to check open features: {e}")
            return False

    async def start(self, instruction: str | None = None) -> tuple[bool, str]:
        """
        Start or restart the sandbox and optionally send an instruction.

        Args:
            instruction: Optional instruction to send to Claude Code

        Returns:
            Tuple of (success, message)
        """
        # Refresh prompts from templates before starting
        try:
            from prompts import refresh_project_prompts
            updated = refresh_project_prompts(self.project_dir)
            if updated:
                logger.info(f"Refreshed prompts from templates: {updated}")
        except Exception as e:
            logger.warning(f"Failed to refresh prompts: {e}")

        await self._sync_status()

        # Check if graceful stop was requested - don't restart
        if self._graceful_stop_requested:
            logger.info(f"Graceful stop requested, not starting {self.container_name}")
            return False, "Graceful stop requested"

        if self._status == "running":
            # Sandbox already running, just send instruction if provided
            if instruction:
                self._user_started = True
                return await self.send_instruction(instruction)
            return True, "Sandbox already running"

        try:
            # Create new sandbox
            logger.info(f"Creating E2B sandbox for {self.container_name}")
            await self._broadcast_output(f"[System] Creating E2B sandbox...")

            self._sandbox = await AsyncSandbox.create(
                template=E2B_TEMPLATE_ID,
                timeout=E2B_SANDBOX_TIMEOUT,
                envs=self._get_sandbox_envs(),
            )
            self._sandbox_id = self._sandbox.sandbox_id

            # Update registry with sandbox ID
            try:
                from registry import create_container, update_container_status
                create_container(
                    project_name=self.project_name,
                    container_number=self.container_number,
                    container_type=self.container_type
                )
                update_container_status(
                    project_name=self.project_name,
                    container_number=self.container_number,
                    container_type=self.container_type,
                    docker_container_id=self._sandbox_id,  # Store sandbox ID
                    status='running'
                )
            except Exception as e:
                logger.warning(f"Failed to update registry: {e}")

            self.started_at = datetime.now()
            self._update_activity()
            self.status = "running"
            self._user_started = True

            # Prepare sandbox environment (upload scripts, install dependencies)
            # This is needed when using the default E2B template
            prep_ok, prep_msg = await self._prepare_sandbox_environment()
            if not prep_ok:
                logger.error(f"Environment preparation failed: {prep_msg}")
                await self._broadcast_output(f"[System] Environment setup failed: {prep_msg}")
                return False, prep_msg

            # Run setup script to clone repo and configure SSH
            await self._broadcast_output("[System] Setting up repository...")
            app_dir = getattr(self, '_sandbox_app_dir', '/home/user/app')
            setup_result = await self._sandbox.commands.run(
                f"{app_dir}/setup_sandbox.sh",
                timeout=120,
                on_stdout=lambda out: asyncio.create_task(self._broadcast_output(out)),
                on_stderr=lambda err: asyncio.create_task(self._broadcast_output(f"[stderr] {err}")),
            )

            if setup_result.exit_code != 0:
                logger.error(f"Setup failed: {setup_result.stderr}")
                await self._broadcast_output(f"[System] Setup failed: {setup_result.stderr}")
                return False, f"Repository setup failed: {setup_result.stderr}"

            await self._broadcast_output("[System] Repository cloned successfully")

            # Handle init container specially
            if self._is_init_container:
                # Recovery: reset any stuck in_progress features to open
                recovery_ok, recovery_msg = await self.recover_stuck_features()
                if not recovery_ok:
                    logger.warning(f"Feature recovery failed: {recovery_msg}")

                if instruction:
                    # New project - run initializer prompt
                    logger.info(f"Init sandbox running initializer for {self.project_name}")
                    await self._broadcast_output("[System] Running project initialization...")
                    return await self.send_instruction(instruction)
                else:
                    # Existing project recovery - just stop
                    logger.info(f"Init sandbox completed recovery for {self.project_name}")
                    await self._broadcast_output("[System] Project recovery complete, stopping init sandbox...")
                    await self.stop()
                    return True, "Init sandbox completed recovery"

            # Send instruction if provided (for coding sandboxes)
            if instruction:
                # Recovery: reset any stuck in_progress features
                recovery_ok, recovery_msg = await self.recover_stuck_features()
                if not recovery_ok:
                    logger.warning(f"Feature recovery failed: {recovery_msg}")

                # Start agent in background task (non-blocking)
                asyncio.create_task(self._run_agent_with_monitoring(instruction))
                return True, "Sandbox started and agent spawned"

            return True, f"Sandbox {self.container_name} started"

        except Exception as e:
            logger.exception("Failed to start sandbox")
            return False, f"Failed to start sandbox: {e}"

    async def start_sandbox_only(self) -> tuple[bool, str]:
        """
        Start the sandbox without starting the agent.

        This is used for editing tasks when the agent isn't needed.
        The sandbox will stay running until idle timeout.

        Returns:
            Tuple of (success, message)
        """
        await self._sync_status()

        if self._status == "running":
            return True, "Sandbox already running"

        try:
            # Create new sandbox
            logger.info(f"Creating E2B sandbox (idle mode) for {self.container_name}")

            self._sandbox = await AsyncSandbox.create(
                template=E2B_TEMPLATE_ID,
                timeout=E2B_SANDBOX_TIMEOUT,
                envs=self._get_sandbox_envs(),
            )
            self._sandbox_id = self._sandbox.sandbox_id

            # Update registry
            try:
                from registry import create_container, update_container_status
                create_container(
                    project_name=self.project_name,
                    container_number=self.container_number,
                    container_type=self.container_type
                )
                update_container_status(
                    project_name=self.project_name,
                    container_number=self.container_number,
                    container_type=self.container_type,
                    docker_container_id=self._sandbox_id,
                    status='running'
                )
            except Exception as e:
                logger.warning(f"Failed to update registry: {e}")

            self.started_at = datetime.now()
            self._update_activity()
            self.status = "running"
            # Don't set _user_started - this is just for editing

            # Prepare sandbox environment (upload scripts, install dependencies)
            prep_ok, prep_msg = await self._prepare_sandbox_environment()
            if not prep_ok:
                logger.error(f"Environment preparation failed: {prep_msg}")
                return False, prep_msg

            # Run setup script to clone repo
            await self._broadcast_output("[System] Setting up repository...")
            app_dir = getattr(self, '_sandbox_app_dir', '/home/user/app')
            setup_result = await self._sandbox.commands.run(
                f"{app_dir}/setup_sandbox.sh",
                timeout=120,
            )

            if setup_result.exit_code != 0:
                logger.error(f"Setup failed: {setup_result.stderr}")
                return False, f"Repository setup failed: {setup_result.stderr}"

            return True, f"Sandbox {self.container_name} started (idle mode)"

        except Exception as e:
            logger.exception("Failed to start sandbox")
            return False, f"Failed to start sandbox: {e}"

    async def stop(self, preserve_user_started: bool = False) -> tuple[bool, str]:
        """
        Stop the sandbox.

        Args:
            preserve_user_started: If True, don't reset the _user_started flag.

        Returns:
            Tuple of (success, message)
        """
        logger.info(f"[STOP] Attempting to stop sandbox {self.container_name}")
        await self._sync_status()

        if self._status != "running":
            logger.warning(f"[STOP] Sandbox {self.container_name} is not running, status: {self._status}")
            return False, "Sandbox is not running"

        try:
            # Cancel output streaming task
            if self._output_task:
                self._output_task.cancel()
                try:
                    await self._output_task
                except asyncio.CancelledError:
                    pass

            # Reset graceful stop flag
            self._graceful_stop_requested = False

            # Reset user_started unless preserving for restart
            if not preserve_user_started:
                logger.info(f"[STOP] Resetting _user_started flag for {self.container_name}")
                self._user_started = False

            # Clear verification state if running
            if self._last_agent_was_overseer:
                from registry import clear_verification_state
                clear_verification_state(self.project_name)

            # Kill the sandbox
            logger.info(f"[STOP] Killing E2B sandbox {self.container_name}")
            if self._sandbox:
                await self._sandbox.kill()

            self._sandbox = None
            self._sandbox_id = None
            self._agent_pid = None
            self.status = "stopped"

            # Update registry
            try:
                from registry import update_container_status
                update_container_status(
                    project_name=self.project_name,
                    container_number=self.container_number,
                    container_type=self.container_type,
                    status='stopped'
                )
            except Exception as e:
                logger.warning(f"Failed to update registry: {e}")

            logger.info(f"[STOP] Successfully stopped {self.container_name}")
            return True, f"Sandbox {self.container_name} stopped"

        except Exception as e:
            logger.exception("Failed to stop sandbox")
            return False, f"Failed to stop sandbox: {e}"

    async def graceful_stop(self) -> tuple[bool, str]:
        """
        Request graceful shutdown of agent after current session completes.

        Returns:
            Tuple of (success, message)
        """
        await self._sync_status()

        if self._status != "running":
            return False, "Sandbox is not running"

        if self._graceful_stop_requested:
            return True, "Graceful stop already requested"

        try:
            self._graceful_stop_requested = True
            logger.info(f"Graceful stop requested for {self.container_name}")
            await self._broadcast_output("[System] Graceful stop requested, completing current session...")

            # Start background task to monitor completion
            asyncio.create_task(self._monitor_graceful_stop())

            return True, "Graceful stop requested"

        except Exception as e:
            logger.exception("Failed to request graceful stop")
            self._graceful_stop_requested = False
            return False, f"Failed to request graceful stop: {e}"

    async def _monitor_graceful_stop(self) -> None:
        """Monitor graceful stop with 20-minute timeout."""
        timeout_seconds = 20 * 60
        poll_interval = 5

        try:
            elapsed = 0
            while elapsed < timeout_seconds:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

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

    async def remove(self) -> tuple[bool, str]:
        """
        Remove the sandbox completely.

        Returns:
            Tuple of (success, message)
        """
        # Stop first if running
        if self._status == "running":
            await self.stop()

        try:
            # Sandbox is already killed by stop(), just clean up state
            self._sandbox = None
            self._sandbox_id = None
            self._agent_pid = None
            self.status = "not_created"

            return True, f"Sandbox {self.container_name} removed"

        except Exception as e:
            logger.exception("Failed to remove sandbox")
            return False, f"Failed to remove sandbox: {e}"

    async def send_instruction(self, instruction: str) -> tuple[bool, str]:
        """
        Send an instruction to the Agent SDK app running in the sandbox.

        Args:
            instruction: The instruction/prompt to send

        Returns:
            Tuple of (success, message)
        """
        await self._sync_status()

        if self._status != "running" or not self._sandbox:
            return False, "Sandbox is not running"

        try:
            self._update_activity()

            # Get sandbox paths
            home_dir = getattr(self, '_sandbox_home', '/home/user')
            app_dir = getattr(self, '_sandbox_app_dir', f'{home_dir}/app')
            project_dir = getattr(self, '_sandbox_project_dir', f'{home_dir}/project')

            # Write prompt to temp file in sandbox
            prompt_path = f"{home_dir}/prompt.txt"
            await self._sandbox.files.write(prompt_path, instruction)

            logger.info(f"Starting agent in {self.container_name}")
            await self._broadcast_output("[System] Starting agent...")

            # Start agent in background with PATH including npm-global bin
            npm_bin = f"{home_dir}/.npm-global/bin"

            # Build environment with PATH and credentials
            agent_envs = {
                "PATH": f"{npm_bin}:/usr/local/bin:/usr/bin:/bin",
            }
            if ANTHROPIC_API_KEY:
                agent_envs["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
                logger.info(f"Passing ANTHROPIC_API_KEY to agent (length: {len(ANTHROPIC_API_KEY)})")
            oauth_token = os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
            if oauth_token:
                agent_envs["CLAUDE_CODE_OAUTH_TOKEN"] = oauth_token
                logger.info(f"Passing CLAUDE_CODE_OAUTH_TOKEN to agent (length: {len(oauth_token)}, starts with: {oauth_token[:15]}...)")

            # Create a wrapper script to ensure PATH and env vars are properly set
            wrapper_script = f"""#!/bin/bash
export PATH={npm_bin}:$PATH
export CLAUDE_CODE_OAUTH_TOKEN="${{CLAUDE_CODE_OAUTH_TOKEN}}"
export ANTHROPIC_API_KEY="${{ANTHROPIC_API_KEY}}"
export HOME={home_dir}
cd {project_dir}
python {app_dir}/agent_app.py
"""
            wrapper_path = f"{home_dir}/run_agent.sh"
            await self._sandbox.files.write(wrapper_path, wrapper_script)
            await self._sandbox.commands.run(f"chmod +x {wrapper_path}")

            handle = await self._sandbox.commands.run(
                f"{wrapper_path} < {prompt_path}",
                background=True,
                cwd=project_dir,
                envs=agent_envs,
                timeout=0,  # Disable timeout for long-running agent
                on_stdout=lambda out: asyncio.create_task(self._handle_stdout(out)),
                on_stderr=lambda err: asyncio.create_task(self._handle_stderr(err)),
            )

            self._agent_pid = handle.pid

            # Wait for agent to complete
            result = await handle.wait()
            exit_code = result.exit_code

            self._agent_pid = None

            # Handle exit code
            return await self._handle_agent_exit(exit_code)

        except Exception as e:
            logger.exception("Failed to send instruction")
            return False, f"Failed to send instruction: {e}"

    async def _handle_stdout(self, data: str) -> None:
        """Handle stdout from agent."""
        self._update_activity()
        sanitized = sanitize_output(data.rstrip())
        await self._broadcast_output(sanitized)

        # Detect feature claim
        claim_match = re.search(r'Claimed ([\w]+-[\w]+),', sanitized)
        if not claim_match:
            claim_match = re.search(r'Working on feature: ([\w]+-[\w]+)', sanitized)
        if claim_match:
            await self._set_current_feature(claim_match.group(1))

        # Detect feature close
        close_match = re.search(r'bd close ([\w]+-[\w]+)', sanitized)
        if close_match and self._current_feature == close_match.group(1):
            await self._set_current_feature(None)

    async def _handle_stderr(self, data: str) -> None:
        """Handle stderr from agent."""
        self._update_activity()
        sanitized = sanitize_output(data.rstrip())
        await self._broadcast_output(f"[stderr] {sanitized}")

    async def _set_current_feature(self, feature_id: str | None) -> None:
        """Update the currently worked-on feature."""
        self._current_feature = feature_id
        try:
            from registry import update_container_status
            # Use empty string to clear, otherwise set the feature
            update_container_status(
                self.project_name, self.container_number, self.container_type,
                current_feature=feature_id if feature_id else ""
            )
        except Exception as e:
            logger.warning(f"Failed to update current feature: {e}")

    async def _run_agent_with_monitoring(self, instruction: str) -> None:
        """Run agent in background and handle exit."""
        try:
            success, message = await self.send_instruction(instruction)
            if not success:
                logger.error(f"Agent instruction failed: {message}")
                await self._broadcast_output(f"[System] Agent failed: {message}")
        except Exception as e:
            logger.exception(f"Error running agent: {e}")
            await self._broadcast_output(f"[System] Agent error: {e}")

    async def _handle_agent_exit(self, exit_code: int) -> tuple[bool, str]:
        """
        Handle agent exit with recovery logic.

        Exit codes:
        - 0: Success
        - 1: Failure
        - 129: Graceful stop
        - 130: User interrupt
        - 131: Context limit (restart)
        """
        from registry import (
            clear_verification_state,
            set_verification_running,
            get_last_closed_feature,
            set_last_closed_feature,
        )

        # Init containers never restart
        if self._is_init_container:
            logger.info(f"Init sandbox {self.container_name} completed with exit code {exit_code}")
            await self._broadcast_output(f"[System] Init sandbox completed (exit code: {exit_code})")
            await self.stop()
            if exit_code == 0:
                return True, "Init sandbox completed successfully"
            else:
                return False, f"Init sandbox failed with exit code {exit_code}"

        # Handle context limit - restart with fresh context
        if exit_code == 131:
            logger.info(f"Context limit reached in {self.container_name}, restarting...")
            await self._broadcast_output("[System] Context limit reached. Restarting with fresh context...")
            self._last_agent_was_overseer = False
            return await self.restart_agent()

        # Handle graceful stop
        if exit_code == 129 or self._graceful_stop_requested:
            logger.info(f"Graceful stop completed for {self.container_name}")
            await self._broadcast_output("[System] Graceful stop completed")
            self._graceful_stop_requested = False
            await self.stop()
            return True, "Graceful stop completed"

        if exit_code == 0:
            # Success - determine next action
            logger.info(f"[EXIT] Agent exited successfully in {self.container_name}")

            # Handle reviewer completion
            if self._current_agent_type == "reviewer":
                set_last_closed_feature(self.project_name, self.container_number, None, self.container_type)
                logger.info(f"[REVIEWER] Review complete in {self.container_name}")
                self._current_agent_type = "coder"

            if self.has_open_features() and not self._graceful_stop_requested:
                # Features remain - check for reviewer first
                if self._current_agent_type == "coder":
                    closed_feature_id = get_last_closed_feature(
                        self.project_name, self.container_number, self.container_type
                    )
                    if closed_feature_id:
                        logger.info(f"[EXIT] Running reviewer for {closed_feature_id}")
                        await self._broadcast_output(f"[System] Running review for {closed_feature_id}...")
                        return await self.restart_with_reviewer(closed_feature_id)

                # Restart coding agent
                logger.info(f"[EXIT] Features remain, restarting coding agent...")
                await self._broadcast_output("[System] Session complete. Starting fresh context...")

                # Check for 10% milestone
                await self._check_overseer_milestone()

                self._last_agent_was_overseer = False
                return await self.restart_agent()

            elif not self.has_open_features() and not self._graceful_stop_requested:
                # All features closed
                if self._last_agent_was_overseer:
                    clear_verification_state(self.project_name)

                    if self._is_milestone_overseer:
                        logger.info(f"Milestone overseer completed in {self.container_name}")
                        await self._broadcast_output("[System] Milestone verification complete.")
                        await self.stop()
                        self._is_milestone_overseer = False
                        return True, "Milestone verification complete"

                    if self.has_open_features():
                        # Overseer created new issues
                        logger.info(f"Overseer created new issues, restarting...")
                        await self._broadcast_output("[System] Verification found issues. Restarting...")
                        await self._restart_other_containers()
                        self._last_agent_was_overseer = False
                        return await self.restart_agent()
                    else:
                        # Project complete
                        logger.info(f"Verification complete in {self.container_name}!")
                        await self._broadcast_output("[System] Verification complete! All features verified.")
                        await self.stop()
                        self.status = "completed"
                        await self._stop_other_containers()
                        return True, "All features verified complete"
                else:
                    # Try to acquire verification lock
                    if set_verification_running(self.project_name, True):
                        logger.info(f"All features closed, running overseer verification...")
                        await self._broadcast_output("[System] All features complete. Running final verification...")
                        return await self.restart_with_overseer()
                    else:
                        logger.info(f"Verification already running, stopping {self.container_name}")
                        await self._broadcast_output("[System] Verification running in another container. Waiting...")
                        await self.stop()
                        return True, "Stopped - verification running elsewhere"

            return True, "Instruction completed"

        elif exit_code == 130:
            # User interrupt
            logger.info(f"Agent interrupted in {self.container_name}")
            await self._broadcast_output("[System] Agent interrupted by user")
            return True, "Agent interrupted"

        else:
            # Error - potentially restart
            logger.error(f"Agent failed in {self.container_name}: exit code {exit_code}")
            await self._broadcast_output(f"[System] Agent failed: exit code {exit_code}")

            if self.has_open_features() and not self._graceful_stop_requested:
                await self._broadcast_output("[System] Auto-restarting after error...")
                await asyncio.sleep(5)
                self._last_agent_was_overseer = False
                return await self.restart_agent()
            else:
                return False, f"Agent failed with exit code {exit_code}"

    async def restart_agent(self) -> tuple[bool, str]:
        """Restart the agent with the coding prompt."""
        if self._graceful_stop_requested:
            logger.info(f"Graceful stop requested, not restarting {self.container_name}")
            return False, "Graceful stop requested, not restarting"

        logger.info(f"Restarting agent in sandbox {self.container_name}")

        self._restarting = True
        try:
            # Stop the sandbox (preserve user_started)
            await self.stop(preserve_user_started=True)

            # Read coding prompt
            coding_prompt_path = self.project_dir / "prompts" / "coding_prompt.md"
            if not coding_prompt_path.exists():
                return False, "No coding_prompt.md found in project"

            try:
                instruction = coding_prompt_path.read_text()
            except Exception as e:
                return False, f"Failed to read coding prompt: {e}"

            self._last_agent_was_overseer = False
            self._current_agent_type = "coder"
            self._force_claude_sdk = False

            return await self.start(instruction)
        finally:
            self._restarting = False

    async def restart_with_reviewer(self, feature_id: str) -> tuple[bool, str]:
        """Restart the agent with the reviewer prompt."""
        logger.info(f"Starting reviewer for feature {feature_id} in sandbox {self.container_name}")

        self._restarting = True
        try:
            await self.stop(preserve_user_started=True)

            from prompts import get_reviewer_prompt

            try:
                instruction = get_reviewer_prompt(self.project_dir, feature_id)
            except FileNotFoundError:
                logger.warning(f"No reviewer_prompt.md found, skipping review for {feature_id}")
                from registry import set_last_closed_feature
                set_last_closed_feature(self.project_name, self.container_number, None, self.container_type)
                return await self.restart_agent()

            self._current_agent_type = "reviewer"
            self._last_agent_was_overseer = False
            self._force_claude_sdk = False

            return await self.start(instruction)
        finally:
            self._restarting = False

    async def restart_with_overseer(self) -> tuple[bool, str]:
        """Restart the agent with the overseer prompt."""
        from registry import clear_verification_state

        logger.info(f"Starting overseer verification in sandbox {self.container_name}")

        self._restarting = True
        try:
            await self.stop(preserve_user_started=True)

            overseer_prompt_path = self.project_dir / "prompts" / "overseer_prompt.md"
            if not overseer_prompt_path.exists():
                from prompts import get_overseer_prompt
                try:
                    instruction = get_overseer_prompt(self.project_dir)
                except FileNotFoundError:
                    clear_verification_state(self.project_name)
                    return False, "No overseer_prompt.md found"
            else:
                try:
                    instruction = overseer_prompt_path.read_text()
                except Exception as e:
                    clear_verification_state(self.project_name)
                    return False, f"Failed to read overseer prompt: {e}"

            self._last_agent_was_overseer = True
            self._is_milestone_overseer = False
            self._current_agent_type = "overseer"
            self._force_claude_sdk = False

            success, message = await self.start(instruction)
            if not success:
                clear_verification_state(self.project_name)
            return success, message
        except Exception as e:
            clear_verification_state(self.project_name)
            raise
        finally:
            self._restarting = False

    async def _check_overseer_milestone(self) -> None:
        """Check if we've hit a new 10% milestone and spawn overseer if so."""
        from .beads_manager import get_cached_stats
        from registry import get_overseer_milestone, set_verification_running

        stats = get_cached_stats(self.project_name)
        if not stats or stats.get('total', 0) == 0:
            return

        percentage = stats.get('percentage', 0)
        current_milestone = int(percentage // 10) * 10
        last_milestone = get_overseer_milestone(self.project_name)

        if current_milestone > last_milestone and 0 < current_milestone < 100:
            logger.info(f"[{self.project_name}] Hit {current_milestone}% milestone - spawning overseer")
            await self._spawn_overseer_at_milestone(current_milestone)

    async def _spawn_overseer_at_milestone(self, milestone: int) -> None:
        """Spawn overseer sandbox at 10% milestone."""
        from registry import update_overseer_milestone, set_verification_running
        from prompts import get_overseer_prompt

        update_overseer_milestone(self.project_name, milestone)

        if not set_verification_running(self.project_name, True):
            logger.info(f"[{self.project_name}] Overseer already running, skipping milestone trigger")
            return

        try:
            await self._broadcast_output(f"[System] {milestone}% milestone reached - running quality verification...")

            overseer_manager = E2BSandboxManager(
                project_name=self.project_name,
                git_url=self.git_url,
                container_number=0
            )
            overseer_manager._current_agent_type = "overseer"
            overseer_manager._is_milestone_overseer = True
            overseer_manager._last_agent_was_overseer = True
            overseer_manager._user_started = True

            try:
                prompt = get_overseer_prompt(self.project_dir)
            except FileNotFoundError:
                logger.warning(f"[{self.project_name}] No overseer prompt found")
                from registry import clear_verification_state
                clear_verification_state(self.project_name)
                return

            asyncio.create_task(self._run_milestone_overseer(overseer_manager, prompt, milestone))

        except Exception as e:
            logger.error(f"[{self.project_name}] Failed to spawn overseer: {e}")
            from registry import clear_verification_state
            clear_verification_state(self.project_name)

    async def _run_milestone_overseer(
        self,
        overseer_manager: "E2BSandboxManager",
        prompt: str,
        milestone: int
    ) -> None:
        """Run the milestone overseer and handle its completion."""
        from registry import clear_verification_state

        try:
            logger.info(f"[{self.project_name}] Starting milestone overseer at {milestone}%")
            success, message = await overseer_manager.start(prompt)
            if not success:
                logger.warning(f"[{self.project_name}] Milestone overseer failed to start: {message}")
        except Exception as e:
            logger.error(f"[{self.project_name}] Milestone overseer error: {e}")
        finally:
            if overseer_manager._status != "running":
                clear_verification_state(self.project_name)

    async def _stop_other_containers(self) -> None:
        """Stop all other sandboxes for this project."""
        all_managers = get_all_container_managers(self.project_name)
        for manager in all_managers:
            if manager.container_number != self.container_number:
                if manager.status == "running":
                    logger.info(f"Stopping {manager.container_name} (project complete)")
                    await manager.stop()
                    manager.status = "completed"

    async def _restart_other_containers(self) -> None:
        """Restart stopped sandboxes for this project."""
        all_managers = get_all_container_managers(self.project_name)
        for manager in all_managers:
            if manager.container_number != self.container_number:
                if manager.status == "stopped" and manager._user_started:
                    logger.info(f"Restarting {manager.container_name} (new issues to work on)")
                    manager._last_agent_was_overseer = False
                    await manager.restart_agent()

    async def recover_stuck_features(self) -> tuple[bool, str]:
        """Reset any in_progress features to open."""
        from .beads_manager import get_beads_sync_manager
        from server.routers.beads_api import run_beads_write_command

        try:
            manager = get_beads_sync_manager(self.project_name, self.git_url)
            features = manager.get_tasks_by_status("in_progress")

            if not features:
                return True, "No stuck features to recover"

            recovered = 0
            for feature in features:
                feature_id = feature.get("id")
                if not feature_id:
                    continue

                logger.info(f"Recovering stuck feature: {feature_id}")
                await self._broadcast_output(f"[System] Recovering stuck feature: {feature_id}")

                result = await run_beads_write_command(
                    self.project_name,
                    ["update", feature_id, "--status", "open"]
                )
                if "error" not in result:
                    recovered += 1

            await run_beads_write_command(self.project_name, ["sync"])

            logger.info(f"Recovered {recovered} stuck features for {self.project_name}")
            return True, f"Recovered {recovered} stuck features"

        except Exception as e:
            logger.exception(f"Error recovering stuck features for {self.project_name}")
            return False, f"Recovery error: {e}"

    def get_status_dict(self) -> dict:
        """Get current status as a dictionary."""
        return {
            "status": self.status,
            "container_name": self.container_name,
            "container_type": self.container_type,
            "container_number": self.container_number,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "idle_seconds": self.get_idle_seconds(),
            "agent_running": self.is_agent_running(),
            "user_started": self._user_started,
            "graceful_stop_requested": self._graceful_stop_requested,
            "current_feature": self._current_feature,
            "agent_type": self._current_agent_type,
            "sdk_type": "e2b",
        }


# Global registry of sandbox managers: project -> {container_number -> manager}
_managers: dict[str, dict[int, E2BSandboxManager]] = {}
_managers_lock = threading.Lock()

# Alias for backward compatibility
_container_managers = _managers


def get_projects_dir() -> Path:
    """Get the projects directory path."""
    from registry import get_projects_dir as _get_projects_dir
    return _get_projects_dir()


def get_container_manager(
    project_name: str,
    git_url: str,
    container_number: int = 1,
    project_dir: Path | None = None,
) -> E2BSandboxManager:
    """
    Get or create a sandbox manager for a project and container number.

    Args:
        project_name: Name of the project
        git_url: Git URL for the project repository
        container_number: Container number (0 = init, 1-10 = coding)
        project_dir: Optional local clone path

    Returns:
        E2BSandboxManager instance
    """
    with _managers_lock:
        if project_name not in _managers:
            _managers[project_name] = {}
        if container_number not in _managers[project_name]:
            _managers[project_name][container_number] = E2BSandboxManager(
                project_name, git_url, container_number, project_dir
            )
        return _managers[project_name][container_number]


def get_existing_container_manager(
    project_name: str,
    container_number: int = 1,
) -> E2BSandboxManager | None:
    """Get an existing sandbox manager WITHOUT creating one."""
    with _managers_lock:
        if project_name in _managers:
            return _managers[project_name].get(container_number)
    return None


def get_all_container_managers(project_name: str) -> list[E2BSandboxManager]:
    """Get all sandbox managers for a project."""
    result = []
    with _managers_lock:
        if project_name in _managers:
            result.extend(_managers[project_name].values())
    return result


def get_projects_with_active_containers() -> list[str]:
    """Return list of project names that have at least one running sandbox."""
    with _managers_lock:
        active_projects = set()
        for project_name, containers in _managers.items():
            for manager in containers.values():
                if manager.status == "running":
                    active_projects.add(project_name)
                    break
        return list(active_projects)


def get_init_container_manager(
    project_name: str,
    git_url: str,
    project_dir: Path | None = None,
) -> E2BSandboxManager:
    """Get or create the init sandbox manager for a project."""
    return get_container_manager(project_name, git_url, container_number=0, project_dir=project_dir)


def clear_container_manager(project_name: str, container_number: int | None = None) -> None:
    """Clear cached sandbox manager(s) for a project."""
    with _managers_lock:
        if project_name not in _managers:
            return
        if container_number is not None:
            if container_number in _managers[project_name]:
                del _managers[project_name][container_number]
        else:
            del _managers[project_name]


async def restore_managers_from_registry() -> int:
    """
    Restore E2BSandboxManager instances for existing sandboxes on startup.

    Returns:
        Number of managers restored
    """
    from registry import list_containers, get_project_git_url, update_container_status

    restored = 0

    try:
        containers = list_containers()

        for container in containers:
            project_name = container.project_name
            container_number = container.container_number
            sandbox_id = container.docker_container_id  # Stores sandbox_id
            status = container.status

            if status not in ("running", "stopping"):
                continue

            git_url = get_project_git_url(project_name)
            if not git_url:
                logger.warning(f"No git URL for project {project_name}, skipping restore")
                continue

            # Try to reconnect to sandbox
            if sandbox_id:
                try:
                    sandbox = await AsyncSandbox.connect(sandbox_id)
                    is_running = await sandbox.is_running()

                    if is_running:
                        manager = E2BSandboxManager(
                            project_name,
                            git_url,
                            container_number,
                        )
                        manager._sandbox = sandbox
                        manager._sandbox_id = sandbox_id
                        manager._status = "running"

                        with _managers_lock:
                            if project_name not in _managers:
                                _managers[project_name] = {}
                            _managers[project_name][container_number] = manager

                        restored += 1
                        logger.info(f"Restored sandbox manager for {manager.container_name}")
                    else:
                        update_container_status(project_name, container_number, status="stopped")
                except Exception as e:
                    logger.info(f"Sandbox {sandbox_id} no longer exists: {e}")
                    update_container_status(project_name, container_number, status="stopped")

    except Exception as e:
        logger.exception(f"Error restoring sandbox managers: {e}")

    return restored


async def cleanup_idle_containers() -> list[str]:
    """Stop sandboxes that have been idle for longer than the timeout."""
    stopped = []

    all_managers = []
    with _managers_lock:
        for project_managers in _managers.values():
            all_managers.extend(project_managers.values())

    for manager in all_managers:
        if manager.status == "running" and manager.is_idle():
            success, _ = await manager.stop()
            if success:
                stopped.append(manager.container_name)
                logger.info(f"Stopped idle sandbox: {manager.container_name}")

    return stopped


async def cleanup_all_containers() -> None:
    """Force remove ALL sandboxes on server shutdown."""
    logger.info("Force removing all sandboxes on shutdown...")

    all_managers = []
    with _managers_lock:
        for project_managers in _managers.values():
            all_managers.extend(project_managers.values())

    for manager in all_managers:
        try:
            if manager._sandbox:
                await manager._sandbox.kill()
        except Exception as e:
            logger.warning(f"Failed to kill sandbox {manager.container_name}: {e}")


def check_e2b_available() -> tuple[bool, str]:
    """Check if E2B is configured and available."""
    if not E2B_API_KEY:
        return False, "E2B_API_KEY not set in environment"

    if not HOST_API_URL:
        return False, "HOST_API_URL not set - required for sandbox-to-host communication"

    return True, "E2B is available"


# =============================================================================
# Health Monitoring
# =============================================================================

# Health check interval (5 minutes)
AGENT_HEALTH_CHECK_INTERVAL = 300

# Stuck agent timeout (10 minutes of no output)
AGENT_STUCK_TIMEOUT_SECONDS = 600


async def cleanup_stale_containers() -> int:
    """
    Remove sandbox DB entries that no longer exist in E2B.
    Called on server startup to ensure clean state.

    Returns:
        Number of stale container entries cleaned up.
    """
    from registry import list_all_containers, delete_container

    all_containers = list_all_containers()
    cleaned = 0

    for c in all_containers:
        project_name = c["project_name"]
        container_num = c["container_number"]
        container_type = c.get("container_type", "coding")
        sandbox_id = c.get("docker_container_id")  # Stores sandbox_id

        if not sandbox_id:
            # No sandbox ID - probably never created
            delete_container(project_name, container_num, container_type)
            clear_container_manager(project_name, container_num)
            logger.info(f"Removed stale container entry (no sandbox ID): zerocoder-{project_name}-{container_num}")
            cleaned += 1
            continue

        # Try to connect to the sandbox
        try:
            sandbox = await AsyncSandbox.connect(sandbox_id)
            is_running = await sandbox.is_running()
            if not is_running:
                delete_container(project_name, container_num, container_type)
                clear_container_manager(project_name, container_num)
                logger.info(f"Removed stale container entry (sandbox stopped): zerocoder-{project_name}-{container_num}")
                cleaned += 1
        except Exception:
            # Sandbox doesn't exist anymore
            delete_container(project_name, container_num, container_type)
            clear_container_manager(project_name, container_num)
            logger.info(f"Removed stale container entry (sandbox gone): zerocoder-{project_name}-{container_num}")
            cleaned += 1

    return cleaned


async def monitor_agent_health() -> list[str]:
    """
    Check health of all running sandboxes and restart stuck/dead agents.

    Called periodically by the health monitor task.

    Returns:
        List of container names that were restarted.
    """
    restarted = []

    # Collect all managers
    all_managers = []
    with _managers_lock:
        for project_managers in _managers.values():
            all_managers.extend(project_managers.values())

    for manager in all_managers:
        # Skip containers that weren't started by user
        if not manager._user_started:
            continue

        # Skip completed or not created containers
        if manager.status in ("not_created", "completed"):
            continue

        # Handle stopped sandbox - restart if features remain
        if manager.status == "stopped":
            if not manager.has_open_features():
                logger.info(f"Sandbox {manager.container_name} stopped, no open features - marking complete")
                manager.status = "completed"
                manager._user_started = False
                continue

            logger.warning(
                f"Sandbox {manager.container_name} stopped unexpectedly (user_started=True), restarting..."
            )
            try:
                success, message = await manager.start()
                if success:
                    restarted.append(manager.container_name)
                    logger.info(f"Successfully restarted sandbox {manager.container_name}")
                else:
                    logger.error(f"Failed to restart sandbox {manager.container_name}: {message}")
            except Exception as e:
                logger.exception(f"Error restarting sandbox {manager.container_name}: {e}")
            continue

        # Handle running sandbox with dead agent process
        if manager.status == "running" and not manager.is_agent_running():
            logger.warning(
                f"Agent not running in {manager.container_name}, restarting agent..."
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
            continue

        # Handle stuck agent (running but no output for AGENT_STUCK_TIMEOUT)
        if manager.status == "running" and manager.is_agent_stuck():
            idle_mins = manager.get_idle_seconds() // 60
            logger.warning(
                f"Agent stuck in {manager.container_name} (no output for {idle_mins} min), restarting..."
            )
            await manager._broadcast_output(
                f"[System] Agent stuck (no output for {idle_mins} min), restarting..."
            )
            try:
                success, message = await manager.restart_agent()
                if success:
                    restarted.append(manager.container_name)
                    logger.info(f"Successfully restarted stuck agent in {manager.container_name}")
                else:
                    logger.error(f"Failed to restart stuck agent in {manager.container_name}: {message}")
            except Exception as e:
                logger.exception(f"Error restarting stuck agent in {manager.container_name}: {e}")

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
