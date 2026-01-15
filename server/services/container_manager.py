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
import sys

# Add root to path for imports
_root = Path(__file__).parent.parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from prompts import refresh_project_prompts

logger = logging.getLogger(__name__)

# Container image name
CONTAINER_IMAGE = "zerocoder-project"

# Path to Dockerfile for building the image
DOCKERFILE_PATH = Path(__file__).parent.parent.parent / "Dockerfile.project"

# Idle timeout in minutes
IDLE_TIMEOUT_MINUTES = 15


def image_exists(image_name: str = CONTAINER_IMAGE) -> bool:
    """Check if a Docker image exists."""
    result = subprocess.run(
        ["docker", "image", "inspect", image_name],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def build_image(image_name: str = CONTAINER_IMAGE) -> tuple[bool, str]:
    """
    Build the Docker image from Dockerfile.project.

    Returns:
        Tuple of (success, message)
    """
    if not DOCKERFILE_PATH.exists():
        return False, f"Dockerfile not found at {DOCKERFILE_PATH}"

    logger.info(f"Building Docker image {image_name}...")
    build_context = DOCKERFILE_PATH.parent

    result = subprocess.run(
        ["docker", "build", "-f", str(DOCKERFILE_PATH), "-t", image_name, str(build_context)],
        capture_output=True,
        text=True,
        timeout=600,  # 10 minute timeout for build
    )

    if result.returncode != 0:
        logger.error(f"Docker build failed: {result.stderr}")
        return False, f"Failed to build image: {result.stderr}"

    logger.info(f"Docker image {image_name} built successfully")
    return True, f"Image {image_name} built successfully"


def ensure_image_exists(image_name: str = CONTAINER_IMAGE) -> tuple[bool, str]:
    """
    Ensure the Docker image exists, building it if necessary.

    Returns:
        Tuple of (success, message)
    """
    if image_exists(image_name):
        return True, "Image exists"

    logger.info(f"Image {image_name} not found, building...")
    return build_image(image_name)

# Agent health check interval in seconds (5 minutes)
AGENT_HEALTH_CHECK_INTERVAL = 300

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
        git_url: str,
        container_number: int = 1,  # Container number for parallel execution (0 = init container)
        project_dir: Path | None = None,  # For local clone path (wizard/edit)
    ):
        """
        Initialize the container manager.

        Args:
            project_name: Name of the project
            git_url: Git URL for the project repository
            container_number: Container number (0 = init, 1-10 = coding containers)
            project_dir: Optional local clone path for wizard/edit mode
        """
        self.project_name = project_name
        self.git_url = git_url
        self.container_number = container_number
        # Local clone path for wizard/edit mode
        from registry import get_projects_dir
        self.project_dir = project_dir or get_projects_dir() / project_name

        # Container naming: init container vs coding containers
        if container_number == 0:  # Init container
            self.container_name = f"zerocoder-{project_name}-init"
            self._is_init_container = True
        else:  # Coding container
            self.container_name = f"zerocoder-{project_name}-{container_number}"
            self._is_init_container = False

        self._status: Literal["not_created", "running", "stopped", "completed"] = "not_created"
        self.started_at: datetime | None = None
        self.last_activity: datetime | None = None
        self._log_task: asyncio.Task | None = None

        # Track if user started this container (for auto-restart monitoring)
        # Restore from marker file if it exists (survives server restart)
        self._user_started: bool = self._check_user_started_marker()
        # Flag to prevent health monitor conflicts during restart
        self._restarting: bool = False
        # Track if the last agent was overseer (for completion detection)
        self._last_agent_was_overseer: bool = False
        # Track if the last agent was hound (for hound → overseer flow)
        self._last_agent_was_hound: bool = False
        # Track if graceful stop was requested
        self._graceful_stop_requested: bool = False
        # Track current agent type for OpenCode SDK routing
        self._current_agent_type: Literal["coder", "overseer", "hound"] = "coder"
        # Force Claude SDK for initializer (regardless of project model)
        self._force_claude_sdk: bool = False
        # Model to use when forcing Claude SDK (defaults to Opus 4.5)
        self._forced_model: str = "claude-opus-4-5-20251101"

        # Callbacks for WebSocket notifications
        self._output_callbacks: Set[Callable[[str], Awaitable[None]]] = set()
        self._status_callbacks: Set[Callable[[str], Awaitable[None]]] = set()
        self._callbacks_lock = threading.Lock()

        # Check initial container status
        self._sync_status()

    def _get_marker_file_path(self) -> Path:
        """Get path to the user-started marker file."""
        return self.project_dir / ".agent_started"

    def _check_user_started_marker(self) -> bool:
        """Check if user-started marker file exists."""
        return self._get_marker_file_path().exists()

    def _set_user_started_marker(self) -> None:
        """Create user-started marker file."""
        try:
            self._get_marker_file_path().touch()
        except Exception as e:
            logger.warning(f"Failed to create user-started marker: {e}")

    def _remove_user_started_marker(self) -> None:
        """Remove user-started marker file."""
        try:
            marker = self._get_marker_file_path()
            if marker.exists():
                marker.unlink()
        except Exception as e:
            logger.warning(f"Failed to remove user-started marker: {e}")

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
                    # Initialize last_activity from container logs if not set
                    if self.last_activity is None:
                        self._init_last_activity_from_logs()
                else:
                    self._status = "stopped"
            else:
                self._status = "not_created"
        except Exception as e:
            logger.warning(f"Failed to check container status: {e}")
            self._status = "not_created"

    def _init_last_activity_from_logs(self) -> None:
        """Initialize last_activity from container's last log timestamp."""
        try:
            # Get last log line with timestamp
            result = subprocess.run(
                ["docker", "logs", "--tail", "1", "--timestamps", self.container_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                # Docker timestamp format: 2026-01-15T01:50:15.745000000Z
                line = result.stdout.strip()
                # Extract timestamp (first space-separated part)
                timestamp_str = line.split()[0] if line else None
                if timestamp_str:
                    # Parse ISO format timestamp
                    # Remove nanoseconds (keep only microseconds) and handle Z suffix
                    ts = timestamp_str.replace('Z', '+00:00')
                    # Truncate nanoseconds to microseconds
                    if '.' in ts:
                        base, frac_and_tz = ts.split('.', 1)
                        # Find where timezone starts (+ or -)
                        for i, c in enumerate(frac_and_tz):
                            if c in '+-':
                                frac = frac_and_tz[:i][:6]  # Max 6 digits for microseconds
                                tz = frac_and_tz[i:]
                                ts = f"{base}.{frac}{tz}"
                                break
                    self.last_activity = datetime.fromisoformat(ts).replace(tzinfo=None)
                    logger.info(f"Initialized last_activity from logs: {self.last_activity}")
        except Exception as e:
            logger.debug(f"Could not init last_activity from logs: {e}")

    def _get_agent_model(self) -> str:
        """
        Read agent model from project config file.

        Returns:
            Model ID string (e.g., 'claude-sonnet-4-5-20250514' or 'glm-4-7')
        """
        config_path = self.project_dir / "prompts" / ".agent_config.json"
        default_model = "claude-sonnet-4-5-20250514"
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text())
                return config.get("agent_model", default_model)
            except Exception as e:
                logger.warning(f"Failed to read agent config: {e}")
        return default_model

    def _is_opencode_model(self) -> bool:
        """Check if the current model requires OpenCode SDK."""
        model = self._get_agent_model()
        return model == "glm-4-7"

    @property
    def status(self) -> Literal["not_created", "running", "stopped", "completed"]:
        return self._status

    @status.setter
    def status(self, value: Literal["not_created", "running", "stopped", "completed"]):
        old_status = self._status
        self._status = value
        if old_status != value:
            self._notify_status_change(value)

    @property
    def container_type(self) -> Literal["init", "coding"]:
        """Get the container type for registry calls."""
        return "init" if self._is_init_container else "coding"

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
            # Check for agent process based on model type
            if self._is_opencode_model():
                # Check for Node.js OpenCode agent process
                result = subprocess.run(
                    ["docker", "exec", self.container_name, "pgrep", "-f", "node.*opencode_agent_app"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            else:
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
        """Check if project has open features remaining using BeadsSyncManager."""
        from .beads_sync_manager import get_beads_sync_manager

        try:
            manager = get_beads_sync_manager(self.project_name, self.git_url)
            stats = manager.get_stats()
            open_count = stats.get("open", 0) + stats.get("in_progress", 0)
            return open_count > 0
        except Exception as e:
            logger.warning(f"Failed to check open features: {e}")
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
                    except json.JSONDecodeError as e:
                        logger.warning(f"Skipped corrupt JSON in {self.project_name} issues.jsonl: {e}")
                        continue
            return open_count > 0
        except Exception as e:
            logger.warning(f"Failed to read issues file directly: {e}")
            # On read error, assume features exist (safer than assuming none)
            return True

    # =========================================================================
    # Beads-Sync Branch Management (for parallel container coordination)
    # =========================================================================

    async def ensure_beads_sync_branch(self) -> tuple[bool, str]:
        """
        Ensure beads-sync branch exists on remote (migration for existing projects).

        This is called before agent starts to ensure the beads coordination
        branch exists. If it doesn't exist, creates it from main.

        Returns:
            Tuple of (success, message)
        """
        if self._status != "running":
            return False, "Container must be running to check beads-sync branch"

        try:
            # Check if beads-sync branch exists on remote
            check_result = subprocess.run(
                ["docker", "exec", "-u", "coder", self.container_name,
                 "git", "ls-remote", "--heads", "origin", "beads-sync"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if check_result.stdout.strip():
                # Branch exists - just configure beads to use it
                logger.info(f"beads-sync branch already exists for {self.project_name}")
                subprocess.run(
                    ["docker", "exec", "-u", "coder", self.container_name,
                     "bd", "config", "set", "sync.branch", "beads-sync"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                return True, "beads-sync branch already exists"

            # Branch doesn't exist - create it
            logger.info(f"Creating beads-sync branch for {self.project_name}")
            await self._broadcast_output("[System] Creating beads-sync branch for parallel coordination...")

            commands = [
                ["git", "checkout", "main"],
                ["git", "pull", "origin", "main"],
                ["bd", "config", "set", "sync.branch", "beads-sync"],
                ["git", "checkout", "-b", "beads-sync"],
                ["git", "push", "-u", "origin", "beads-sync"],
                ["git", "checkout", "main"],
                ["bd", "sync"],
            ]

            for cmd in commands:
                result = subprocess.run(
                    ["docker", "exec", "-u", "coder", self.container_name] + cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    logger.error(f"Failed to run {' '.join(cmd)}: {result.stderr}")
                    return False, f"Failed to create beads-sync branch: {result.stderr}"

            logger.info(f"Created beads-sync branch for {self.project_name}")
            return True, "beads-sync branch created"

        except subprocess.TimeoutExpired:
            return False, "Timeout checking/creating beads-sync branch"
        except Exception as e:
            logger.exception(f"Error ensuring beads-sync branch for {self.project_name}")
            return False, f"Error: {e}"

    async def pre_agent_sync(self) -> tuple[bool, str]:
        """
        Run before agent starts: ensure beads-sync exists, pull latest code, sync beads.

        This ensures the container has the latest code and beads state before
        the agent starts working.

        Returns:
            Tuple of (success, message)
        """
        if self._status != "running":
            return False, "Container must be running for pre-agent sync"

        try:
            await self._broadcast_output("[System] Syncing with remote before starting agent...")

            # 1. Ensure beads-sync branch exists (migration for existing projects)
            success, msg = await self.ensure_beads_sync_branch()
            if not success:
                logger.warning(f"ensure_beads_sync_branch failed: {msg}")
                # Continue anyway - beads-sync may be optional for some setups

            # 2. Fetch and pull latest from main
            commands = [
                (["git", "fetch", "origin"], "Fetching from origin"),
                (["git", "checkout", "main"], "Checking out main"),
                (["git", "pull", "origin", "main"], "Pulling latest from main"),
                (["bd", "sync"], "Syncing beads state"),
            ]

            for cmd, desc in commands:
                result = subprocess.run(
                    ["docker", "exec", "-u", "coder", self.container_name] + cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode != 0:
                    logger.warning(f"{desc} failed: {result.stderr}")
                    # Don't fail entirely - some commands may fail benignly
                    # (e.g., already on main, nothing to pull)

            logger.info(f"Pre-agent sync completed for {self.project_name}")
            return True, "Pre-agent sync completed"

        except subprocess.TimeoutExpired:
            return False, "Pre-agent sync timed out"
        except Exception as e:
            logger.exception(f"Error in pre-agent sync for {self.project_name}")
            return False, f"Pre-agent sync error: {e}"

    async def post_agent_cleanup(self) -> tuple[bool, str]:
        """
        Run after agent completes: cleanup feature branches.

        The agent has already merged to main and pushed. This just cleans up
        any leftover feature branches.

        Returns:
            Tuple of (success, message)
        """
        if self._status != "running":
            return False, "Container must be running for post-agent cleanup"

        try:
            # List feature branches
            result = subprocess.run(
                ["docker", "exec", "-u", "coder", self.container_name,
                 "git", "branch", "--list", "feature/*"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0 or not result.stdout.strip():
                return True, "No feature branches to clean up"

            # Clean up each feature branch
            branches = [b.strip().lstrip("* ") for b in result.stdout.strip().split("\n") if b.strip()]
            for branch in branches:
                if not branch:
                    continue

                # Delete local branch
                subprocess.run(
                    ["docker", "exec", "-u", "coder", self.container_name,
                     "git", "branch", "-d", branch],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                # Delete remote branch (may fail if already deleted)
                subprocess.run(
                    ["docker", "exec", "-u", "coder", self.container_name,
                     "git", "push", "origin", "--delete", branch],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

            logger.info(f"Cleaned up {len(branches)} feature branches for {self.project_name}")
            return True, f"Cleaned up {len(branches)} feature branches"

        except subprocess.TimeoutExpired:
            return False, "Post-agent cleanup timed out"
        except Exception as e:
            logger.exception(f"Error in post-agent cleanup for {self.project_name}")
            return False, f"Cleanup error: {e}"

    async def recover_stuck_features(self) -> tuple[bool, str]:
        """
        Reset any in_progress features to open (recovery after force-stop).

        This should be called on startup for existing projects to recover
        features that were left in_progress when containers were force-stopped.

        Returns:
            Tuple of (success, message)
        """
        if self._status != "running":
            return False, "Container must be running for recovery"

        try:
            # Get in_progress features
            result = subprocess.run(
                ["docker", "exec", "-u", "coder", self.container_name,
                 "bd", "list", "--status=in_progress", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0 or not result.stdout.strip():
                return True, "No stuck features to recover"

            try:
                features = json.loads(result.stdout)
            except json.JSONDecodeError:
                return True, "No stuck features to recover"

            if not features:
                return True, "No stuck features to recover"

            # Reset each to open
            recovered = 0
            for feature in features:
                feature_id = feature.get("id")
                if not feature_id:
                    continue

                logger.info(f"Recovering stuck feature: {feature_id}")
                await self._broadcast_output(f"[System] Recovering stuck feature: {feature_id}")

                update_result = subprocess.run(
                    ["docker", "exec", "-u", "coder", self.container_name,
                     "bd", "update", feature_id, "--status=open"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if update_result.returncode == 0:
                    recovered += 1

            # Sync after recovery
            subprocess.run(
                ["docker", "exec", "-u", "coder", self.container_name, "bd", "sync"],
                capture_output=True,
                text=True,
                timeout=60,
            )

            logger.info(f"Recovered {recovered} stuck features for {self.project_name}")
            return True, f"Recovered {recovered} stuck features"

        except subprocess.TimeoutExpired:
            return False, "Recovery timed out"
        except Exception as e:
            logger.exception(f"Error recovering stuck features for {self.project_name}")
            return False, f"Recovery error: {e}"

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
        # Refresh prompts from templates before starting
        try:
            updated = refresh_project_prompts(Path(self.project_dir))
            if updated:
                logger.info(f"Refreshed prompts from templates: {updated}")
        except Exception as e:
            logger.warning(f"Failed to refresh prompts: {e}")

        self._sync_status()

        if self._status == "running":
            # Container already running, just send instruction if provided
            if instruction:
                self._user_started = True  # Mark as user-started for auto-restart
                self._set_user_started_marker()
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
                # Ensure Docker image exists (build if necessary)
                image_ok, image_msg = ensure_image_exists()
                if not image_ok:
                    return False, image_msg

                # Create new container with auth tokens from environment
                cmd = [
                    "docker", "run", "-d",
                    "--name", self.container_name,
                ]
                # Pass git URL for cloning (container clones from git instead of volume mount)
                cmd.extend(["-e", f"GIT_REMOTE_URL={self.git_url}"])
                # Pass OAuth token if available
                oauth_token = os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
                if oauth_token:
                    cmd.extend(["-e", f"CLAUDE_CODE_OAUTH_TOKEN={oauth_token}"])
                # Pass API key if available
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if api_key:
                    cmd.extend(["-e", f"ANTHROPIC_API_KEY={api_key}"])
                # Pass Z.ai API key for OpenCode SDK (GLM-4.7 model)
                zhipu_key = os.getenv("ZHIPU_API_KEY")
                if zhipu_key:
                    cmd.extend(["-e", f"ZHIPU_API_KEY={zhipu_key}"])
                # Sync timezone with host
                if os.path.exists("/etc/localtime"):
                    cmd.extend(["-v", "/etc/localtime:/etc/localtime:ro"])
                if os.path.exists("/etc/timezone"):
                    cmd.extend(["-v", "/etc/timezone:/etc/timezone:ro"])
                    # Also pass TZ env var for Node.js (doesn't read /etc/localtime)
                    try:
                        with open("/etc/timezone", "r") as f:
                            tz = f.read().strip()
                            if tz:
                                cmd.extend(["-e", f"TZ={tz}"])
                    except Exception:
                        pass
                # Mount SSH key for git operations if configured
                # Mount to temp location; entrypoint copies with correct permissions
                ssh_key_path = os.getenv("GIT_SSH_KEY_PATH")
                if ssh_key_path:
                    expanded_path = os.path.expanduser(ssh_key_path)
                    if os.path.exists(expanded_path):
                        cmd.extend(["-v", f"{expanded_path}:/tmp/ssh_key:ro"])
                        logger.info(f"Added SSH key mount: {expanded_path}")
                cmd.append(CONTAINER_IMAGE)

                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    return False, f"Failed to create container: {result.stderr}"

            self.started_at = datetime.now()
            self._update_activity()
            self.status = "running"
            self._user_started = True  # Mark as user-started for monitoring
            self._set_user_started_marker()

            # Start log streaming
            self._log_task = asyncio.create_task(self._stream_logs())

            # Handle init container specially
            if self._is_init_container:
                # Wait for container to clone the repo (entrypoint clones from GIT_REMOTE_URL)
                # Check for /project/.git to exist, not just git --version
                for attempt in range(30):  # 60 seconds total (clone can take time)
                    await asyncio.sleep(2)
                    check = subprocess.run(
                        ["docker", "exec", "-u", "coder", self.container_name,
                         "test", "-d", "/project/.git"],
                        capture_output=True,
                        text=True,
                    )
                    if check.returncode == 0:
                        logger.info(f"Init container {self.container_name}: repo cloned successfully")
                        break
                    logger.info(f"Waiting for init container to clone repo (attempt {attempt + 1}/30)")
                else:
                    return False, "Init container failed to clone repo after 60 seconds"

                # Pre-agent sync: pull latest code and beads state
                sync_ok, sync_msg = await self.pre_agent_sync()
                if not sync_ok:
                    logger.warning(f"Pre-agent sync failed: {sync_msg}")
                    # Continue anyway - sync failure shouldn't block

                # Recovery: reset any stuck in_progress features to open
                recovery_ok, recovery_msg = await self.recover_stuck_features()
                if not recovery_ok:
                    logger.warning(f"Feature recovery failed: {recovery_msg}")
                    # Continue anyway - recovery failure shouldn't block

                if instruction:
                    # New project - run initializer prompt
                    logger.info(f"Init container running initializer for {self.project_name}")
                    await self._broadcast_output("[System] Running project initialization...")
                    return await self.send_instruction(instruction)
                else:
                    # Existing project recovery - just sync and stop
                    logger.info(f"Init container completed recovery for {self.project_name}")
                    await self._broadcast_output("[System] Project recovery complete, stopping init container...")
                    await self.stop()
                    return True, "Init container completed recovery"

            # Send instruction if provided (for coding containers)
            if instruction:
                # Wait for container to clone the repo (entrypoint clones from GIT_REMOTE_URL)
                for attempt in range(30):  # 60 seconds total (clone can take time)
                    await asyncio.sleep(2)
                    check = subprocess.run(
                        ["docker", "exec", "-u", "coder", self.container_name,
                         "test", "-d", "/project/.git"],
                        capture_output=True,
                        text=True,
                    )
                    if check.returncode == 0:
                        logger.info(f"Container {self.container_name}: repo cloned successfully")
                        break
                    logger.info(f"Waiting for container to clone repo (attempt {attempt + 1}/30)")
                else:
                    return False, "Container failed to clone repo after 60 seconds"

                # Wait for agent app to be available
                # If forcing Claude SDK (e.g., for initializer), always check for Claude SDK
                use_opencode = self._is_opencode_model() and not self._force_claude_sdk
                for attempt in range(10):
                    await asyncio.sleep(2)
                    if use_opencode:
                        # Check for OpenCode SDK (Node.js) - check if compiled agent exists
                        check = subprocess.run(
                            ["docker", "exec", "-u", "coder", self.container_name,
                             "test", "-f", "/app/dist/opencode_agent_app.js"],
                            capture_output=True,
                            text=True,
                        )
                    else:
                        # Check for Claude SDK (Python)
                        check = subprocess.run(
                            ["docker", "exec", "-u", "coder", self.container_name,
                             "python", "-c", "import claude_agent_sdk; print('ok')"],
                            capture_output=True,
                            text=True,
                        )
                    if check.returncode == 0:
                        break
                    sdk_name = "OpenCode SDK" if use_opencode else "Claude SDK"
                    logger.info(f"Waiting for {sdk_name} to be ready (attempt {attempt + 1}/10)")
                else:
                    sdk_name = "OpenCode SDK" if use_opencode else "Claude SDK"
                    return False, f"{sdk_name} not available in container after 20 seconds"

                # Pre-agent sync: pull latest code and beads state
                sync_ok, sync_msg = await self.pre_agent_sync()
                if not sync_ok:
                    logger.warning(f"Pre-agent sync failed: {sync_msg}")
                    # Continue anyway - sync failure shouldn't block agent

                # Recovery: reset any stuck in_progress features to open
                recovery_ok, recovery_msg = await self.recover_stuck_features()
                if not recovery_ok:
                    logger.warning(f"Feature recovery failed: {recovery_msg}")
                    # Continue anyway - recovery failure shouldn't block agent

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
            self._remove_user_started_marker()

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
        Monitor graceful stop with 20-minute timeout.
        Falls back to force stop if timeout exceeded.
        """
        timeout_seconds = 20 * 60  # 20 minutes
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

        Uses stdin to pass the prompt to agent_app.py (Claude) or
        opencode_agent_app.js (GLM-4.7), avoiding shell escaping issues.

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
                # Determine which agent app to use based on model
                # If _force_claude_sdk is set, always use Claude SDK (for initializer)
                use_opencode = self._is_opencode_model() and not self._force_claude_sdk

                if use_opencode:
                    # OpenCode SDK agent (GLM-4.7)
                    # Pass agent type via environment variable
                    agent_type = self._current_agent_type
                    logger.info(f"Using OpenCode agent ({agent_type}) for {self.container_name}")

                    with open(prompt_file, "r", encoding="utf-8") as stdin_file:
                        process = await asyncio.create_subprocess_exec(
                            "docker", "exec", "-i", "-u", "coder",
                            "-e", f"OPENCODE_AGENT_TYPE={agent_type}",
                            self.container_name,
                            "node", "/app/dist/opencode_agent_app.js",
                            stdin=stdin_file,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.STDOUT,
                        )
                else:
                    # Claude Agent SDK (Python)
                    # If forcing Claude SDK with a specific model, pass it as env var
                    if self._force_claude_sdk:
                        logger.info(f"Using Claude agent (forced, model={self._forced_model}) for {self.container_name}")
                        with open(prompt_file, "r", encoding="utf-8") as stdin_file:
                            process = await asyncio.create_subprocess_exec(
                                "docker", "exec", "-i", "-u", "coder",
                                "-e", f"AGENT_MODEL={self._forced_model}",
                                self.container_name,
                                "python", "/app/agent_app.py",
                                stdin=stdin_file,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.STDOUT,
                            )
                    else:
                        logger.info(f"Using Claude agent for {self.container_name}")
                        with open(prompt_file, "r", encoding="utf-8") as stdin_file:
                            process = await asyncio.create_subprocess_exec(
                                "docker", "exec", "-i", "-u", "coder", self.container_name,
                                "python", "/app/agent_app.py",
                                stdin=stdin_file,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.STDOUT,
                            )

                # Stream output to callbacks (common to both OpenCode and Claude)
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
        - 131: Context limit reached (restart with fresh context)

        Agent flow:
        - If init container → just stop, never restart
        - If open features exist → restart coding agent
        - If no open features:
          - If last agent was NOT overseer → restart with overseer
          - If last agent WAS overseer → project is truly complete

        Args:
            exit_code: The exit code from the agent process

        Returns:
            Tuple of (success, message)
        """
        # Init containers never restart - they complete their task and stop
        if self._is_init_container:
            logger.info(f"Init container {self.container_name} completed with exit code {exit_code}")
            await self._broadcast_output(f"[System] Init container completed (exit code: {exit_code})")
            await self.stop()
            if exit_code == 0:
                return True, "Init container completed successfully"
            else:
                return False, f"Init container failed with exit code {exit_code}"

        # Handle context limit - exit code 131 (restart with fresh context)
        if exit_code == 131:
            logger.info(f"Context limit reached in {self.container_name}, restarting with fresh context...")
            await self._broadcast_output("[System] Context limit reached. Restarting with fresh context...")
            self._last_agent_was_overseer = False
            self._last_agent_was_hound = False
            return await self.restart_agent()

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

            # Post-agent cleanup: remove feature branches
            cleanup_ok, cleanup_msg = await self.post_agent_cleanup()
            if not cleanup_ok:
                logger.warning(f"Post-agent cleanup failed: {cleanup_msg}")
                # Continue anyway - cleanup failure shouldn't block flow

            if self._user_started and self.has_open_features():
                # Features remain - check if hound should run (every 20 closed tasks)
                if self._should_run_hound():
                    logger.info(f"[EXIT] 20+ tasks closed since last hound, running hound review...")
                    await self._broadcast_output("[System] Periodic code review triggered. Running Hound agent...")
                    task_ids = await self.get_recent_closed_tasks(30)
                    self._last_agent_was_hound = False
                    self._last_agent_was_overseer = False
                    return await self.restart_with_hound(task_ids)
                # Otherwise restart coding agent
                logger.info(f"[EXIT] Features remain in {self.container_name}, restarting coding agent...")
                await self._broadcast_output("[System] Session complete. Starting fresh context for next task...")
                self._last_agent_was_overseer = False
                self._last_agent_was_hound = False
                return await self.restart_agent()
            elif self._user_started and not self.has_open_features():
                # All features closed - determine verification flow
                if self._last_agent_was_overseer:
                    # Overseer found nothing - project is truly complete
                    logger.info(f"Verification complete in {self.container_name}! All features verified.")
                    await self._broadcast_output("[System] Verification complete! All features verified.")
                    await self.stop()
                    self.status = "completed"
                    self._remove_user_started_marker()
                    return True, "All features verified complete"
                elif self._last_agent_was_hound:
                    # Hound just ran - now run overseer
                    logger.info(f"Hound review complete in {self.container_name}, running overseer verification...")
                    await self._broadcast_output("[System] Code review complete. Running final verification...")
                    return await self.restart_with_overseer()
                else:
                    # Run hound first before overseer
                    logger.info(f"All features closed in {self.container_name}, running hound review before overseer...")
                    await self._broadcast_output("[System] All features complete. Running code review before verification...")
                    task_ids = await self.get_recent_closed_tasks(30)
                    return await self.restart_with_hound(task_ids)
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
                self._last_agent_was_hound = False
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
            # Set agent type for OpenCode routing
            self._current_agent_type = "coder"
            # Use project's configured model (not forced Claude SDK)
            self._force_claude_sdk = False

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
            # Set agent type for OpenCode routing
            self._current_agent_type = "overseer"
            # Use project's configured model (not forced Claude SDK)
            self._force_claude_sdk = False

            # Start container with instruction
            return await self.start(instruction)
        finally:
            self._restarting = False

    # =========================================================================
    # Hound Agent Support
    # =========================================================================

    def _get_hound_state(self) -> dict:
        """Read hound state from project directory."""
        state_file = Path(self.project_dir) / ".hound_state.json"
        if not state_file.exists():
            return {"last_run_closed_count": 0}
        try:
            return json.loads(state_file.read_text())
        except Exception as e:
            logger.warning(f"Failed to read hound state: {e}")
            return {"last_run_closed_count": 0}

    def _save_hound_state(self, closed_count: int) -> None:
        """Save hound state after hound runs."""
        state_file = Path(self.project_dir) / ".hound_state.json"
        try:
            state_file.write_text(json.dumps({"last_run_closed_count": closed_count}))
            logger.info(f"Saved hound state: last_run_closed_count={closed_count}")
        except Exception as e:
            logger.warning(f"Failed to save hound state: {e}")

    def _get_closed_count(self) -> int:
        """Get current closed task count from beads stats."""
        try:
            result = subprocess.run(
                ["docker", "exec", "-u", "coder", self.container_name,
                 "bd", "stats", "--json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                stats = json.loads(result.stdout)
                return stats.get("closed", 0)
        except Exception as e:
            logger.warning(f"Failed to get closed count: {e}")
        return 0

    def _should_run_hound(self) -> bool:
        """Check if 20+ tasks closed since last hound run."""
        state = self._get_hound_state()
        last_count = state.get("last_run_closed_count", 0)
        current_count = self._get_closed_count()
        should_run = (current_count - last_count) >= 20
        logger.info(f"Hound check: last={last_count}, current={current_count}, should_run={should_run}")
        return should_run

    async def get_recent_closed_tasks(self, limit: int = 30) -> list[str]:
        """Get the last N closed task IDs from container."""
        try:
            result = subprocess.run(
                ["docker", "exec", "-u", "coder", self.container_name,
                 "bd", "list", "--status=closed", f"--limit={limit}"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                # Parse output - each line is a task (format: "id: title")
                task_ids = []
                for line in result.stdout.strip().split("\n"):
                    if line and ":" in line:
                        task_id = line.split(":")[0].strip()
                        if task_id:
                            task_ids.append(task_id)
                return task_ids
        except Exception as e:
            logger.warning(f"Failed to get recent closed tasks: {e}")
        return []

    async def restart_with_hound(self, task_ids: list[str]) -> tuple[bool, str]:
        """
        Restart the agent with the hound prompt.

        The hound reviews recently closed tasks and reopens incomplete ones.

        Args:
            task_ids: List of task IDs to review

        Returns:
            Tuple of (success, message)
        """
        logger.info(f"Starting hound review in container {self.container_name} for {len(task_ids)} tasks")

        self._restarting = True
        try:
            # Stop the container
            await self.stop()

            # Read the hound prompt from the project
            hound_prompt_path = self.project_dir / "prompts" / "hound_prompt.md"
            if not hound_prompt_path.exists():
                # Fall back to template if project-specific doesn't exist
                from prompts import get_hound_prompt
                try:
                    instruction = get_hound_prompt(self.project_dir)
                except FileNotFoundError:
                    return False, "No hound_prompt.md found in project or templates"
            else:
                try:
                    instruction = hound_prompt_path.read_text()
                except Exception as e:
                    return False, f"Failed to read hound prompt: {e}"

            # Inject task IDs into prompt
            task_list = "\n".join([f"- {task_id}" for task_id in task_ids])
            instruction = instruction.replace("{task_ids}", task_list)

            # Mark that we're running hound
            self._last_agent_was_hound = True
            self._last_agent_was_overseer = False
            # Set agent type for OpenCode routing
            self._current_agent_type = "hound"
            # Use project's configured model (not forced Claude SDK)
            self._force_claude_sdk = False

            # Save current closed count for next hound trigger check
            current_count = self._get_closed_count()
            self._save_hound_state(current_count)

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
                # Ensure Docker image exists (build if necessary)
                image_ok, image_msg = ensure_image_exists()
                if not image_ok:
                    return False, image_msg

                # Create new container with auth tokens from environment
                cmd = [
                    "docker", "run", "-d",
                    "--name", self.container_name,
                ]
                # Pass git URL for cloning (container clones from git instead of volume mount)
                cmd.extend(["-e", f"GIT_REMOTE_URL={self.git_url}"])
                # Pass OAuth token if available
                oauth_token = os.getenv("CLAUDE_CODE_OAUTH_TOKEN")
                if oauth_token:
                    cmd.extend(["-e", f"CLAUDE_CODE_OAUTH_TOKEN={oauth_token}"])
                # Pass API key if available
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if api_key:
                    cmd.extend(["-e", f"ANTHROPIC_API_KEY={api_key}"])
                # Pass Z.ai API key for OpenCode SDK (GLM-4.7 model)
                zhipu_key = os.getenv("ZHIPU_API_KEY")
                if zhipu_key:
                    cmd.extend(["-e", f"ZHIPU_API_KEY={zhipu_key}"])
                # Sync timezone with host
                if os.path.exists("/etc/localtime"):
                    cmd.extend(["-v", "/etc/localtime:/etc/localtime:ro"])
                if os.path.exists("/etc/timezone"):
                    cmd.extend(["-v", "/etc/timezone:/etc/timezone:ro"])
                    # Also pass TZ env var for Node.js (doesn't read /etc/localtime)
                    try:
                        with open("/etc/timezone", "r") as f:
                            tz = f.read().strip()
                            if tz:
                                cmd.extend(["-e", f"TZ={tz}"])
                    except Exception:
                        pass
                # Mount SSH key for git operations if configured
                # Mount to temp location; entrypoint copies with correct permissions
                ssh_key_path = os.getenv("GIT_SSH_KEY_PATH")
                if ssh_key_path:
                    expanded_path = os.path.expanduser(ssh_key_path)
                    if os.path.exists(expanded_path):
                        cmd.extend(["-v", f"{expanded_path}:/tmp/ssh_key:ro"])
                        logger.info(f"Added SSH key mount: {expanded_path}")
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
            "container_type": self.container_type,
            "container_number": self.container_number,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "idle_seconds": self.get_idle_seconds(),
            "agent_running": self.is_agent_running(),
            "user_started": self._user_started,
            "graceful_stop_requested": self._graceful_stop_requested,
        }


# Global registry of container managers: project -> {container_number -> manager}
_managers: dict[str, dict[int, ContainerManager]] = {}
_managers_lock = threading.Lock()


def get_container_manager(
    project_name: str,
    git_url: str,
    container_number: int = 1,
    project_dir: Path | None = None,
) -> ContainerManager:
    """
    Get or create a container manager for a project and container number (thread-safe).

    Args:
        project_name: Name of the project
        git_url: Git URL for the project repository
        container_number: Container number (0 = init container, 1-10 = coding containers)
        project_dir: Optional local clone path for wizard/edit mode

    Returns:
        ContainerManager instance for the specified project and container number
    """
    with _managers_lock:
        if project_name not in _managers:
            _managers[project_name] = {}
        if container_number not in _managers[project_name]:
            _managers[project_name][container_number] = ContainerManager(
                project_name, git_url, container_number, project_dir
            )
        return _managers[project_name][container_number]


def get_all_container_managers(project_name: str) -> list[ContainerManager]:
    """Get all container managers for a project (thread-safe)."""
    with _managers_lock:
        if project_name not in _managers:
            return []
        return list(_managers[project_name].values())


def get_projects_with_active_containers() -> list[str]:
    """
    Return list of project names that have at least one running container.

    Used by beads_sync_manager to only poll active projects.
    """
    with _managers_lock:
        active_projects = set()
        for project_name, containers in _managers.items():
            for manager in containers.values():
                if manager.status == "running":
                    active_projects.add(project_name)
                    break  # Found one running container, move to next project
        return list(active_projects)


def get_init_container_manager(
    project_name: str,
    git_url: str,
    project_dir: Path | None = None,
) -> ContainerManager:
    """
    Get or create the init container manager for a project (thread-safe).

    Init containers (container_number=0) are special containers that:
    - Run EVERY startup before coding containers
    - Perform recovery (in_progress -> open) for existing projects
    - Run initializer prompt for new projects
    - Exit after completing their task (never loop/restart)

    Args:
        project_name: Name of the project
        git_url: Git URL for the project repository
        project_dir: Optional local clone path for wizard/edit mode

    Returns:
        ContainerManager instance for the init container
    """
    return get_container_manager(project_name, git_url, container_number=0, project_dir=project_dir)


def clear_container_manager(project_name: str, container_number: int | None = None) -> None:
    """
    Clear cached container manager(s) for a project.

    Args:
        project_name: Name of the project
        container_number: If provided, clear only that container. If None, clear all.
    """
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
    Restore ContainerManager instances for existing containers on startup.

    This should be called during server startup to reconnect to any
    containers that may still be running from before the restart.

    Returns:
        Number of managers restored
    """
    import sys
    _root = Path(__file__).parent.parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

    from registry import list_containers, get_project_git_url, update_container_status

    restored = 0

    try:
        # Get all containers from registry
        containers = list_containers()

        for container in containers:
            project_name = container.project_name
            container_number = container.container_number
            docker_container_id = container.docker_container_id
            status = container.status

            # Skip containers that weren't running
            if status not in ("running", "stopping"):
                continue

            # Get git URL for this project
            git_url = get_project_git_url(project_name)
            if not git_url:
                logger.warning(f"No git URL for project {project_name}, skipping container restore")
                continue

            # Check if Docker container actually exists
            container_name = f"zerocoder-{project_name}-{container_number}"
            docker_exists = False

            if docker_container_id:
                try:
                    check = subprocess.run(
                        ["docker", "inspect", docker_container_id],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    docker_exists = check.returncode == 0
                except Exception:
                    pass

            if not docker_exists:
                # Try by name
                try:
                    check = subprocess.run(
                        ["docker", "inspect", container_name],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    docker_exists = check.returncode == 0
                except Exception:
                    pass

            if docker_exists:
                # Restore manager
                manager = ContainerManager(
                    project_name,
                    git_url,
                    container_number,
                )
                manager._sync_status()  # Sync with actual Docker state

                with _managers_lock:
                    if project_name not in _managers:
                        _managers[project_name] = {}
                    _managers[project_name][container_number] = manager

                restored += 1
                logger.info(f"Restored container manager for {container_name} (status: {manager.status})")
            else:
                # Docker container gone, update registry
                logger.info(f"Container {container_name} no longer exists, updating registry")
                container_type = container.container_type or 'coding'
                update_container_status(project_name, container_number, container_type, status="stopped")

    except Exception as e:
        logger.exception(f"Error restoring container managers: {e}")

    return restored


async def cleanup_idle_containers() -> list[str]:
    """
    Stop containers that have been idle for longer than the timeout.

    Returns:
        List of container names that were stopped
    """
    stopped = []

    # Collect all managers from nested dict
    all_managers = []
    with _managers_lock:
        for project_managers in _managers.values():
            all_managers.extend(project_managers.values())

    for manager in all_managers:
        if manager.status == "running" and manager.is_idle():
            success, _ = await manager.stop()
            if success:
                stopped.append(manager.container_name)
                logger.info(f"Stopped idle container: {manager.container_name}")

    return stopped


async def cleanup_all_containers() -> None:
    """Stop all running containers. Called on server shutdown."""
    logger.info("Stopping all zerocoder containers...")

    # Collect all managers from nested dict
    all_managers = []
    with _managers_lock:
        for project_managers in _managers.values():
            all_managers.extend(project_managers.values())

    for manager in all_managers:
        try:
            if manager.status == "running":
                logger.info(f"Stopping container: {manager.container_name}")
                await manager.stop()
        except Exception as e:
            logger.warning(f"Error stopping container for {manager.project_name}-{manager.container_number}: {e}")

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
    Handles two scenarios:
    1. Container is running but agent process died → restart agent
    2. Container itself stopped unexpectedly → restart container + agent

    Returns:
        List of container names that were restarted
    """
    restarted = []

    # Collect all managers from nested dict
    all_managers = []
    with _managers_lock:
        for project_managers in _managers.values():
            all_managers.extend(project_managers.values())

    for manager in all_managers:
        # Only monitor user-started containers
        if not manager.user_started:
            continue

        # Skip if restart already in progress
        if manager._restarting:
            continue

        # Sync status with Docker to get latest state
        manager._sync_status()

        # Skip completed containers (all features done)
        if manager.status == "completed":
            continue

        # Skip not_created containers
        if manager.status == "not_created":
            continue

        # Handle stopped container - restart it entirely
        if manager.status == "stopped":
            # Check if there are still features to work on
            if not manager.has_open_features():
                logger.info(f"Container {manager.container_name} stopped, no open features - marking complete")
                manager.status = "completed"
                manager._remove_user_started_marker()
                continue

            logger.warning(
                f"Container {manager.container_name} stopped unexpectedly (user_started=True), restarting..."
            )
            try:
                # Restart container and agent
                success, message = await manager.start()
                if success:
                    restarted.append(manager.container_name)
                    logger.info(f"Successfully restarted container {manager.container_name}")
                else:
                    logger.error(f"Failed to restart container {manager.container_name}: {message}")
            except Exception as e:
                logger.exception(f"Error restarting container {manager.container_name}: {e}")
            continue

        # Handle running container with dead agent process
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
