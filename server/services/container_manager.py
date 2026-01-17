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
import random
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

# Idle timeout in minutes (for stopping inactive containers)
IDLE_TIMEOUT_MINUTES = 15

# Stuck agent timeout in minutes (agent running but no output)
# If an agent process is running but produces no log output for this long,
# it's considered stuck (e.g., OpenCode API hung) and will be restarted
AGENT_STUCK_TIMEOUT_MINUTES = 10

# Pre-agent sync timeout in seconds (per git/bd command)
# If sync takes longer than this, agent starts anyway with potentially stale code
PRE_AGENT_SYNC_TIMEOUT = 120


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
    r'sk-ant[a-zA-Z0-9_-]*',  # Anthropic API keys (sk-ant-...)
    r'sk-[a-zA-Z0-9]{20,}',  # Generic sk- keys with 20+ chars
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
        skip_db_persist: bool = False,  # Skip database registration (for hound containers)
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
        # Track current feature being worked on (detected from logs)
        self._current_feature: str | None = None
        # Model to use when forcing Claude SDK (defaults to Opus 4.5)
        self._forced_model: str = "claude-opus-4-5-20251101"

        # Skip database persistence (for hound containers that are in-memory only)
        self._skip_db_persist = skip_db_persist

        # Callbacks for WebSocket notifications
        self._output_callbacks: Set[Callable[[str], Awaitable[None]]] = set()
        self._status_callbacks: Set[Callable[[str], Awaitable[None]]] = set()
        self._callbacks_lock = threading.Lock()

        # Check initial container status
        self._sync_status()

    def _get_marker_file_path(self) -> Path:
        """Get path to the user-started marker file (per-container)."""
        # Use container-specific marker to avoid conflicts in multi-container setups
        # Each container (nexus-1, nexus-2, etc.) gets its own marker file
        return self.project_dir / f".agent_started.{self.container_number}"

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
        """Sync status with actual Docker container state (Docker is source of truth)."""
        # Preserve "completed" status - don't overwrite it
        if self._status == "completed":
            return

        # Always refresh user_started from marker file (may have been created externally)
        self._user_started = self._check_user_started_marker()

        # Docker is the source of truth - check Docker first
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Status}}", self.container_name],
                capture_output=True,
                text=True,
            )
            docker_exists = result.returncode == 0
            docker_status = result.stdout.strip() if docker_exists else None
        except Exception as e:
            logger.warning(f"Failed to check Docker container status: {e}")
            docker_exists = False
            docker_status = None

        # Import registry functions for DB sync
        from registry import get_container, create_container, delete_container

        if docker_exists:
            # Docker has this container - ensure DB reflects this
            db_container = get_container(self.project_name, self.container_number)
            if db_container is None:
                # Container exists in Docker but not in DB - register it
                try:
                    container_type = "init" if self._is_init_container else "coding"
                    create_container(
                        project_name=self.project_name,
                        container_number=self.container_number,
                        container_type=container_type
                    )
                    logger.info(f"Registered existing Docker container {self.container_name} in database")
                except Exception as e:
                    logger.warning(f"Failed to register container in database: {e}")

            # Set status based on Docker state
            if docker_status == "running":
                self._status = "running"
                # Initialize last_activity from container logs if not set
                if self.last_activity is None:
                    self._init_last_activity_from_logs()
            else:
                self._status = "stopped"
        else:
            # Docker doesn't have this container
            db_container = get_container(self.project_name, self.container_number)
            if db_container is not None:
                # DB thinks it exists but Docker doesn't - clean up DB
                try:
                    container_type = "init" if self._is_init_container else "coding"
                    delete_container(self.project_name, self.container_number, container_type)
                    logger.info(f"Removed stale DB entry for {self.container_name}")
                except Exception as e:
                    logger.warning(f"Failed to clean up stale container from database: {e}")

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

    async def _push_template_updates(self) -> None:
        """Commit and push updated template files to git.

        Called after refresh_project_prompts() to ensure containers
        get the latest templates when they clone/pull the repo.
        """
        try:
            # Stage prompts and CLAUDE.md
            await asyncio.to_thread(
                subprocess.run,
                ["git", "add", "prompts/", "CLAUDE.md"],
                cwd=self.project_dir,
                capture_output=True,
            )

            # Commit (may fail if no changes, that's OK)
            await asyncio.to_thread(
                subprocess.run,
                ["git", "commit", "-m", "chore: Update agent templates"],
                cwd=self.project_dir,
                capture_output=True,
            )

            # Push to remote
            result = await asyncio.to_thread(
                subprocess.run,
                ["git", "push"],
                cwd=self.project_dir,
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info("Pushed template updates to git")
        except Exception as e:
            logger.warning(f"Failed to push template updates: {e}")

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

    async def _set_current_feature(self, feature_id: str | None) -> None:
        """Update current feature and broadcast change via WebSocket."""
        if self._current_feature == feature_id:
            return

        self._current_feature = feature_id
        logger.info(f"[{self.container_name}] Current feature: {feature_id}")

        # Update database
        try:
            from registry import update_container_status
            update_container_status(
                project_name=self.project_name,
                container_number=self.container_number,
                current_feature=feature_id if feature_id else ""
            )
        except Exception as e:
            logger.warning(f"Failed to update current_feature in database: {e}")

        # Broadcast via WebSocket
        try:
            from server.websocket import manager as websocket_manager
            await websocket_manager.broadcast_to_project(self.project_name, {
                "type": "container_update",
                "container_number": self.container_number,
                "current_feature": feature_id
            })
        except Exception as e:
            logger.warning(f"Failed to broadcast current_feature update: {e}")

    def is_agent_stuck(self) -> bool:
        """Check if agent is running but not producing output (stuck).

        This detects scenarios where the agent process is alive but hung,
        e.g., OpenCode API not responding, network timeout, etc.
        """
        if self.last_activity is None:
            return False
        # Only consider stuck if agent is supposedly running
        if not self.is_agent_running():
            return False
        stuck_duration = datetime.now() - self.last_activity
        return stuck_duration > timedelta(minutes=AGENT_STUCK_TIMEOUT_MINUTES)

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

    async def recover_git_state(self) -> tuple[bool, str]:
        """
        Recover from corrupted git state (stuck rebase, ref locks, diverged branches).

        This handles common git issues that can occur when the agent crashes or
        is interrupted mid-operation:
        - Stuck rebase/merge/cherry-pick operations
        - Ref lock errors from stale locks
        - Diverged branches needing reset
        - Uncommitted changes blocking checkout

        Returns:
            Tuple of (success, message)
        """
        if self._status != "running":
            return False, "Container must be running for git recovery"

        try:
            await self._broadcast_output("[System] Recovering git state...")

            def run_git(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
                return subprocess.run(
                    ["docker", "exec", "-u", "coder", self.container_name] + cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

            # 1. Abort any stuck operations (rebase, merge, cherry-pick)
            for abort_cmd in [
                ["git", "rebase", "--abort"],
                ["git", "merge", "--abort"],
                ["git", "cherry-pick", "--abort"],
            ]:
                run_git(abort_cmd)  # Ignore errors - these fail if not in that state

            # 2. Fix ref locks with git gc
            result = run_git(["git", "gc", "--prune=now"], timeout=60)
            if result.returncode != 0:
                logger.warning(f"git gc failed: {result.stderr}")

            # 3. Prune stale remote refs
            result = run_git(["git", "remote", "prune", "origin"])
            if result.returncode != 0:
                logger.warning(f"git remote prune failed: {result.stderr}")

            # 4. Fetch latest from origin
            result = run_git(["git", "fetch", "origin"], timeout=60)
            if result.returncode != 0:
                logger.warning(f"git fetch failed after recovery: {result.stderr}")
                # Try one more gc + fetch in case of persistent ref issues
                run_git(["git", "gc", "--prune=now"], timeout=60)
                result = run_git(["git", "fetch", "origin"], timeout=60)

            # 5. Check current branch and status
            result = run_git(["git", "status", "--porcelain"])
            has_changes = bool(result.stdout.strip()) if result.returncode == 0 else False

            # 6. Reset to clean state - discard any uncommitted changes
            if has_changes:
                logger.info("Discarding uncommitted changes during git recovery")
                run_git(["git", "reset", "--hard", "HEAD"])
                run_git(["git", "clean", "-fd"])  # Remove untracked files

            # 7. Checkout and reset main to match origin/main
            run_git(["git", "checkout", "main"])
            result = run_git(["git", "reset", "--hard", "origin/main"])
            if result.returncode != 0:
                logger.warning(f"Failed to reset main to origin/main: {result.stderr}")
                return False, f"Failed to reset main: {result.stderr}"

            # 8. Clean up orphaned feature branches
            result = run_git(["git", "branch", "--list", "feature/*"])
            if result.returncode == 0 and result.stdout.strip():
                branches = [b.strip().lstrip("* ") for b in result.stdout.strip().split("\n") if b.strip()]
                for branch in branches:
                    if branch:
                        run_git(["git", "branch", "-D", branch])
                        logger.info(f"Deleted orphaned feature branch: {branch}")

            logger.info(f"Git state recovered for {self.project_name}")
            return True, "Git state recovered"

        except subprocess.TimeoutExpired:
            return False, "Git recovery timed out"
        except Exception as e:
            logger.exception(f"Error recovering git state for {self.project_name}")
            return False, f"Git recovery error: {e}"

    async def pre_agent_sync(self) -> tuple[bool, str]:
        """
        Run before agent starts: ensure beads-sync exists, pull latest code, sync beads.

        This ensures the container has the latest code and beads state before
        the agent starts working. If git commands fail with recoverable errors,
        automatically runs git recovery.

        Returns:
            Tuple of (success, message)
        """
        if self._status != "running":
            return False, "Container must be running for pre-agent sync"

        # Error patterns that indicate git state needs recovery
        recoverable_errors = [
            "cannot lock ref",
            "would be overwritten",
            "divergent branches",
            "rebase in progress",
            "You are currently",  # rebasing/merging/cherry-picking message
            "needs merge",
            "not possible because you have unmerged files",
        ]

        def needs_recovery(stderr: str) -> bool:
            return any(pattern in stderr for pattern in recoverable_errors)

        try:
            await self._broadcast_output("[System] Syncing with remote before starting agent...")

            # 1. Ensure beads-sync branch exists (migration for existing projects)
            success, msg = await self.ensure_beads_sync_branch()
            if not success:
                logger.warning(f"ensure_beads_sync_branch failed: {msg}")
                # Continue anyway - beads-sync may be optional for some setups

            # 2. Fetch and pull latest from main
            # Note: bd sync removed - beads operations now use host API
            commands = [
                (["git", "fetch", "origin"], "Fetching from origin"),
                (["git", "checkout", "main"], "Checking out main"),
                (["git", "pull", "origin", "main"], "Pulling latest from main"),
            ]

            recovery_attempted = False
            for cmd, desc in commands:
                result = subprocess.run(
                    ["docker", "exec", "-u", "coder", self.container_name] + cmd,
                    capture_output=True,
                    text=True,
                    timeout=PRE_AGENT_SYNC_TIMEOUT,
                )
                if result.returncode != 0:
                    error_msg = result.stderr + result.stdout
                    logger.warning(f"{desc} failed: {error_msg}")

                    # Check if this is a recoverable git error
                    if not recovery_attempted and needs_recovery(error_msg):
                        logger.info(f"Detected recoverable git error, attempting recovery...")
                        recovery_attempted = True
                        recovery_ok, recovery_msg = await self.recover_git_state()
                        if recovery_ok:
                            # Recovery succeeded, retry remaining commands
                            logger.info("Git recovery succeeded, continuing sync")
                            await self._broadcast_output("[System] Git state recovered, continuing sync...")
                            # Don't retry this specific command, continue to next
                            # (recovery already did fetch + checkout + reset)
                            continue
                        else:
                            logger.warning(f"Git recovery failed: {recovery_msg}")
                            # Continue anyway, maybe remaining commands will work

            logger.info(f"Pre-agent sync completed for {self.project_name}")
            return True, "Pre-agent sync completed"

        except subprocess.TimeoutExpired:
            return False, "Pre-agent sync timed out"
        except Exception as e:
            logger.exception(f"Error in pre-agent sync for {self.project_name}")
            return False, f"Pre-agent sync error: {e}"

    async def post_agent_cleanup(self) -> tuple[bool, str]:
        """
        Run cleanup script after agent session ends.

        This calls cleanup_session.sh which:
        - Aborts stuck git operations
        - Switches to main branch
        - Discards uncommitted changes
        - Deletes local feature branches
        - Pulls latest from main
        - Syncs beads state

        Returns:
            Tuple of (success, message)
        """
        if self._status != "running":
            return False, "Container must be running for cleanup"

        try:
            await self._broadcast_output("[System] Running session cleanup...")

            result = subprocess.run(
                ["docker", "exec", "-u", "coder", self.container_name,
                 "/app/cleanup_session.sh"],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode != 0:
                logger.warning(f"Cleanup script returned non-zero: {result.stderr}")

            logger.info(f"Session cleanup completed for {self.project_name}")
            return True, "Session cleanup completed"

        except subprocess.TimeoutExpired:
            return False, "Cleanup script timed out"
        except Exception as e:
            logger.exception(f"Error running cleanup for {self.project_name}")
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

                # Detect feature claim from echo output: "Claimed beads-X, working on branch..."
                # Or: "Working on feature: beads-X"
                claim_match = re.search(r'Claimed (beads-\d+),', sanitized)
                if not claim_match:
                    claim_match = re.search(r'Working on feature: (beads-\d+)', sanitized)
                if claim_match:
                    await self._set_current_feature(claim_match.group(1))

                # Detect feature complete: bd close beads-X
                close_match = re.search(r'bd close (beads-\d+)', sanitized)
                if close_match and self._current_feature == close_match.group(1):
                    await self._set_current_feature(None)

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
                # Push to git so container gets the latest when it clones/pulls
                await self._push_template_updates()
        except Exception as e:
            logger.warning(f"Failed to refresh prompts: {e}")

        self._sync_status()

        # Check if graceful stop was requested - don't restart
        if self._graceful_stop_requested:
            logger.info(f"Graceful stop requested, not starting {self.container_name}")
            return False, "Graceful stop requested"

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
                # Update registry status (skip for hound containers)
                if not self._skip_db_persist:
                    try:
                        from registry import update_container_status
                        update_container_status(
                            project_name=self.project_name,
                            container_number=self.container_number,
                            status='running'
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update container status in database: {e}")
            else:
                # Ensure Docker image exists (build if necessary)
                image_ok, image_msg = ensure_image_exists()
                if not image_ok:
                    return False, image_msg

                # Create new container with auth tokens from environment
                cmd = [
                    "docker", "run", "-d",
                    "--name", self.container_name,
                    # Enable host.docker.internal on Linux (works natively on Mac/Windows)
                    "--add-host", "host.docker.internal:host-gateway",
                ]
                # Pass git URL for cloning (container clones from git instead of volume mount)
                cmd.extend(["-e", f"GIT_REMOTE_URL={self.git_url}"])
                # Pass container type for setup_repo.sh (init vs coding)
                container_type = "init" if self._is_init_container else "coding"
                cmd.extend(["-e", f"CONTAINER_TYPE={container_type}"])
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
                # Pass project name and host API URL for beads_client.sh
                cmd.extend(["-e", f"PROJECT_NAME={self.project_name}"])
                server_port = os.getenv("PORT", "8888")
                cmd.extend(["-e", f"HOST_API_URL=http://host.docker.internal:{server_port}"])
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

                # Register new container in database (skip for hound containers)
                if not self._skip_db_persist:
                    try:
                        from registry import create_container, update_container_status
                        create_container(
                            project_name=self.project_name,
                            container_number=self.container_number,
                            container_type=self.container_type
                        )
                        # Get docker container ID
                        inspect_result = subprocess.run(
                            ["docker", "inspect", "--format", "{{.Id}}", self.container_name],
                            capture_output=True, text=True
                        )
                        docker_id = inspect_result.stdout.strip() if inspect_result.returncode == 0 else None
                        update_container_status(
                            project_name=self.project_name,
                            container_number=self.container_number,
                            docker_container_id=docker_id,
                            status='running'
                        )
                        logger.info(f"Registered container {self.container_name} in database")
                    except Exception as e:
                        logger.warning(f"Failed to register container in database: {e}")

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

                # Start agent in background task (non-blocking)
                # This allows the API to return immediately while agent runs
                asyncio.create_task(self._run_agent_with_monitoring(instruction))
                return True, f"Container started and agent spawned"

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
            # Update registry status
            try:
                from registry import update_container_status
                update_container_status(
                    project_name=self.project_name,
                    container_number=self.container_number,
                    status='stopped'
                )
            except Exception as e:
                logger.warning(f"Failed to update container status in database: {e}")
            return True, f"Container {self.container_name} stopped"

        except subprocess.TimeoutExpired:
            # Force kill
            subprocess.run(
                ["docker", "kill", self.container_name],
                capture_output=True
            )
            self.status = "stopped"
            # Update registry status
            try:
                from registry import update_container_status
                update_container_status(
                    project_name=self.project_name,
                    container_number=self.container_number,
                    status='stopped'
                )
            except Exception as e:
                logger.warning(f"Failed to update container status in database: {e}")
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

                # Consume stdout (docker logs -f handles broadcasting via _stream_logs)
                while True:
                    if process.stdout is None:
                        break
                    line = await process.stdout.readline()
                    if not line:
                        break
                    self._update_activity()

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

    async def _run_agent_with_monitoring(self, instruction: str) -> None:
        """
        Run agent in background and handle exit.

        This method is spawned as a background task by start() to allow
        non-blocking container startup. It runs the agent instruction and
        handles the exit code (which may trigger restarts or completion).

        Args:
            instruction: The instruction to send to the agent
        """
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
                # Features remain - restart coding agent
                # Note: Periodic hound reviews (every 10 completed tasks) now run
                # in parallel via dedicated hound container (hound_trigger_monitor)
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
            error_info = f"exit code {exit_code}, no state file"

            if state_file.exists():
                try:
                    state = json.loads(state_file.read_text())
                    error_info = state.get("error", f"exit code {exit_code}")
                    error_type = state.get("error_type", "Exception")
                    logger.error(f"Agent failed in {self.container_name}: {error_type}: {error_info}")
                    await self._broadcast_output(f"[System] Agent error: {error_type}: {error_info}")
                except Exception as e:
                    logger.warning(f"Failed to read agent state: {e}")
                    error_info = f"exit code {exit_code}, state read error: {e}"
            else:
                logger.error(f"Agent failed in {self.container_name}: {error_info}")
                await self._broadcast_output(f"[System] Agent failed: {error_info}")

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
        # Check if graceful stop was requested - don't restart
        if self._graceful_stop_requested:
            logger.info(f"Graceful stop requested, not restarting {self.container_name}")
            return False, "Graceful stop requested, not restarting"

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
            return {"last_milestone": 0}
        try:
            state = json.loads(state_file.read_text())
            # Migrate old format if needed
            if "last_run_closed_count" in state and "last_milestone" not in state:
                old_count = state.get("last_run_closed_count", 0)
                state["last_milestone"] = (old_count // 10) * 10
            return state
        except Exception as e:
            logger.warning(f"Failed to read hound state: {e}")
            return {"last_milestone": 0}

    def _save_hound_state(self, milestone: int) -> None:
        """Save hound state after hound runs."""
        state_file = Path(self.project_dir) / ".hound_state.json"
        try:
            state_file.write_text(json.dumps({
                "last_milestone": milestone,
                "last_run_at": datetime.now().isoformat(),
            }))
            logger.info(f"Saved hound state: last_milestone={milestone}")
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
                # bd stats --json returns nested structure: summary.closed_issues
                summary = stats.get("summary", {})
                return summary.get("closed_issues", 0)
        except Exception as e:
            logger.warning(f"Failed to get closed count: {e}")
        return 0

    def _should_run_hound(self) -> bool:
        """Check if completed_tasks % 10 == 0 and milestone not yet processed."""
        state = self._get_hound_state()
        last_milestone = state.get("last_milestone", 0)
        current_closed = self._get_closed_count()
        current_milestone = (current_closed // 10) * 10  # Round down to nearest 10

        # Trigger if we hit a new milestone (10, 20, 30, etc.)
        should_run = current_milestone > last_milestone and current_milestone > 0
        logger.info(f"Hound check: last_milestone={last_milestone}, current_closed={current_closed}, "
                   f"current_milestone={current_milestone}, should_run={should_run}")
        return should_run

    def _get_current_milestone(self) -> int:
        """Get the current milestone (nearest 10 below current closed count)."""
        current_closed = self._get_closed_count()
        return (current_closed // 10) * 10

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
            # Force Claude SDK for hound agent code reviews
            self._force_claude_sdk = True

            # Save current milestone for next hound trigger check
            current_milestone = self._get_current_milestone()
            self._save_hound_state(current_milestone)

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
                    # Enable host.docker.internal on Linux (works natively on Mac/Windows)
                    "--add-host", "host.docker.internal:host-gateway",
                ]
                # Pass git URL for cloning (container clones from git instead of volume mount)
                cmd.extend(["-e", f"GIT_REMOTE_URL={self.git_url}"])
                # Pass container type for setup_repo.sh (init vs coding)
                container_type = "init" if self._is_init_container else "coding"
                cmd.extend(["-e", f"CONTAINER_TYPE={container_type}"])
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
                # Pass project name and host API URL for beads_client.sh
                cmd.extend(["-e", f"PROJECT_NAME={self.project_name}"])
                server_port = os.getenv("PORT", "8888")
                cmd.extend(["-e", f"HOST_API_URL=http://host.docker.internal:{server_port}"])
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
            "current_feature": self._current_feature,
            "agent_type": self._current_agent_type,
            "sdk_type": "claude" if self._force_claude_sdk or not self._is_opencode_model() else "opencode",
        }


# Global registry of container managers: project -> {container_number -> manager}
_managers: dict[str, dict[int, ContainerManager]] = {}
_managers_lock = threading.Lock()

# Alias for backward compatibility with tests
_container_managers = _managers


def get_projects_dir() -> Path:
    """Get the projects directory path (wrapper for registry function)."""
    from registry import get_projects_dir as _get_projects_dir
    return _get_projects_dir()


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


def get_existing_container_manager(
    project_name: str,
    container_number: int = 1,
) -> ContainerManager | None:
    """
    Get an existing container manager WITHOUT creating one.

    Returns:
        ContainerManager if exists, None otherwise
    """
    with _managers_lock:
        if project_name in _managers:
            return _managers[project_name].get(container_number)
    return None


def get_all_container_managers(project_name: str) -> list[ContainerManager]:
    """Get all container managers for a project (thread-safe), including hound containers."""
    result = []
    with _managers_lock:
        if project_name in _managers:
            result.extend(_managers[project_name].values())
    # Also include hound container if present
    with _hound_lock:
        if project_name in _hound_containers:
            result.append(_hound_containers[project_name])
    return result


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
            container_type = container.container_type or 'coding'
            if container_type == "init" or container_number == 0:
                container_name = f"zerocoder-{project_name}-init"
            else:
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
                update_container_status(project_name, container_number, container_type, status="stopped")

    except Exception as e:
        logger.exception(f"Error restoring container managers: {e}")

    return restored


async def cleanup_stale_containers() -> int:
    """
    Remove container DB entries that don't exist in Docker.
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

        # Build container name (init containers use -init suffix, others use -N)
        if container_type == "init" or container_num == 0:
            container_name = f"zerocoder-{project_name}-init"
        else:
            container_name = f"zerocoder-{project_name}-{container_num}"

        # Check if exists in Docker
        result = await asyncio.to_thread(
            subprocess.run,
            ["docker", "inspect", container_name],
            capture_output=True
        )

        if result.returncode != 0:
            # Container doesn't exist in Docker - remove from DB and memory
            delete_container(project_name, container_num, container_type)
            clear_container_manager(project_name, container_num)
            logger.info(f"Removed stale container entry: {container_name}")
            cleaned += 1

    return cleaned


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
    """Stop containers on server shutdown.

    User-started containers with open features are preserved - they'll keep
    running and be restored when the server restarts. This prevents server
    restarts from killing active agent work.
    """
    logger.info("Cleaning up containers on shutdown...")

    # Collect all managers from nested dict
    all_managers = []
    with _managers_lock:
        for project_managers in _managers.values():
            all_managers.extend(project_managers.values())

    for manager in all_managers:
        try:
            if manager.status == "running":
                # Preserve user-started containers with work remaining
                if manager.user_started and manager.has_open_features():
                    logger.info(
                        f"Preserving container {manager.container_name} "
                        f"(user-started with open features)"
                    )
                    continue

                logger.info(f"Stopping container: {manager.container_name}")
                await manager.stop()
        except Exception as e:
            logger.warning(f"Error stopping container for {manager.project_name}-{manager.container_number}: {e}")

    # Don't stop orphaned containers - they might be user-started from before restart
    # The health monitor will handle them on next startup

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

        # Skip if graceful stop was requested
        if manager._graceful_stop_requested:
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
            continue

        # Handle stuck agent (running but no output for AGENT_STUCK_TIMEOUT_MINUTES)
        # This catches cases where agent process is alive but hung (e.g., API timeout)
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


# =============================================================================
# Dedicated Hound Container Support
# =============================================================================

# Hound trigger check interval in seconds (5 minutes)
HOUND_CHECK_INTERVAL = 300

# Track running hound containers to prevent duplicates
_hound_containers: dict[str, ContainerManager] = {}
_hound_lock = threading.Lock()


async def get_tasks_for_hound_review(project_name: str, container_name: str) -> list[str]:
    """
    Get tasks for hound review: 10 most recently closed + 10 random from older closed.

    Args:
        project_name: Name of the project
        container_name: Name of an existing coder container to query

    Returns:
        List of task IDs to review (up to 20)
    """
    try:
        # Get all closed tasks as JSON (higher limit to have pool for random selection)
        result = subprocess.run(
            ["docker", "exec", "-u", "coder", container_name,
             "bd", "--no-daemon", "list", "--status=closed", "--limit=100", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning(f"Failed to get closed tasks: {result.stderr}")
            return []

        # Parse JSON output
        all_closed = []
        try:
            tasks = json.loads(result.stdout) if result.stdout.strip() else []
            for task in tasks:
                task_id = task.get("id")
                if task_id:
                    all_closed.append(task_id)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse closed tasks JSON: {e}")
            return []

        if not all_closed:
            return []

        # Split into new (last 10) and older tasks
        new_tasks = all_closed[-10:]  # Most recent 10
        older_tasks = all_closed[:-10] if len(all_closed) > 10 else []

        # Random 10 from older closed tasks
        random_count = min(10, len(older_tasks))
        random_tasks = random.sample(older_tasks, random_count) if older_tasks else []

        result_tasks = new_tasks + random_tasks
        logger.info(f"Selected {len(new_tasks)} new + {len(random_tasks)} random = {len(result_tasks)} tasks for hound")
        return result_tasks

    except Exception as e:
        logger.exception(f"Error getting tasks for hound review: {e}")
        return []


async def spawn_hound_container(project_name: str, git_url: str, task_ids: list[str]) -> tuple[bool, str]:
    """
    Spawn a dedicated hound container for code review.

    The hound container:
    - Runs independently alongside coder containers
    - Reviews the specified tasks
    - Terminates when done (no restart loop)

    Args:
        project_name: Name of the project
        git_url: Git URL for the project repository
        task_ids: List of task IDs to review

    Returns:
        Tuple of (success, message)
    """
    container_name = f"zerocoder-{project_name}-hound"

    # Check if hound container already running
    with _hound_lock:
        if project_name in _hound_containers:
            existing = _hound_containers[project_name]
            if existing.status == "running":
                return False, "Hound container already running"

    logger.info(f"Spawning dedicated hound container {container_name} for {len(task_ids)} tasks")

    try:
        # Remove existing hound container if it exists
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True,
            timeout=30,
        )

        # Get project directory
        from registry import get_projects_dir
        project_dir = get_projects_dir() / project_name

        # Read the hound prompt
        hound_prompt_path = project_dir / "prompts" / "hound_prompt.md"
        if not hound_prompt_path.exists():
            from prompts import get_hound_prompt
            try:
                instruction = get_hound_prompt(project_dir)
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

        # Create hound container manager with container_number=-1 (special hound indicator)
        # We use a separate manager instance to not interfere with coding containers
        hound_manager = ContainerManager(
            project_name=project_name,
            git_url=git_url,
            container_number=-1,  # Special marker for hound container
            project_dir=project_dir,
            skip_db_persist=True,  # Hound containers are in-memory only
        )
        # Override the container name since -1 would give "zerocoder-{project}--1"
        hound_manager.container_name = container_name
        hound_manager._current_agent_type = "hound"
        # Force Claude SDK for hound agent code reviews
        hound_manager._force_claude_sdk = True

        # Register hound container
        with _hound_lock:
            _hound_containers[project_name] = hound_manager

        # Start the hound container
        success, message = await hound_manager.start(instruction)

        if success:
            # Save milestone after spawning hound
            milestone = hound_manager._get_current_milestone()
            hound_manager._save_hound_state(milestone)
            logger.info(f"Hound container {container_name} started successfully, saved milestone {milestone}")
        else:
            # Clean up on failure
            with _hound_lock:
                if project_name in _hound_containers:
                    del _hound_containers[project_name]

        return success, message

    except Exception as e:
        logger.exception(f"Error spawning hound container: {e}")
        with _hound_lock:
            if project_name in _hound_containers:
                del _hound_containers[project_name]
        return False, str(e)


def get_hound_container_status(project_name: str) -> str | None:
    """Get the status of the hound container for a project, if any."""
    with _hound_lock:
        if project_name in _hound_containers:
            return _hound_containers[project_name].status
    return None


async def cleanup_finished_hound_containers() -> list[str]:
    """Clean up hound containers that have finished."""
    cleaned = []
    with _hound_lock:
        to_remove = []
        for project_name, manager in _hound_containers.items():
            manager._sync_status()
            # Remove if stopped or completed (hound finished)
            if manager.status in ("stopped", "completed", "not_created"):
                to_remove.append(project_name)
                cleaned.append(manager.container_name)

        for project_name in to_remove:
            del _hound_containers[project_name]

    return cleaned


async def check_hound_triggers() -> list[str]:
    """
    Check all active projects and spawn hound containers where needed.

    Returns:
        List of project names where hound was triggered
    """
    triggered = []

    # Get all projects with running containers
    with _managers_lock:
        active_projects = []
        for project_name, containers in _managers.items():
            for manager in containers.values():
                if manager.status == "running" and manager.container_number > 0:
                    # Use this container for checking (coder container)
                    active_projects.append((project_name, manager))
                    break

    for project_name, manager in active_projects:
        try:
            # Skip if hound already running for this project
            if get_hound_container_status(project_name) == "running":
                continue

            # Check if hound should run
            if manager._should_run_hound():
                logger.info(f"Hound trigger condition met for {project_name}")

                # Get tasks for review
                task_ids = await get_tasks_for_hound_review(project_name, manager.container_name)
                if not task_ids:
                    logger.warning(f"No tasks found for hound review in {project_name}")
                    continue

                # Spawn hound container
                success, message = await spawn_hound_container(
                    project_name, manager.git_url, task_ids
                )
                if success:
                    triggered.append(project_name)
                    logger.info(f"Spawned hound container for {project_name}")
                else:
                    logger.error(f"Failed to spawn hound for {project_name}: {message}")

        except Exception as e:
            logger.exception(f"Error checking hound trigger for {project_name}: {e}")

    return triggered


async def start_hound_trigger_monitor() -> None:
    """
    Start a background task that periodically checks if hound should run.

    This runs every HOUND_CHECK_INTERVAL seconds and spawns dedicated hound
    containers for projects that have hit a new milestone (10, 20, 30... completed tasks).
    """
    logger.info(f"Starting hound trigger monitor (interval: {HOUND_CHECK_INTERVAL}s)")

    while True:
        try:
            await asyncio.sleep(HOUND_CHECK_INTERVAL)

            # Clean up finished hound containers first
            cleaned = await cleanup_finished_hound_containers()
            if cleaned:
                logger.info(f"Cleaned up finished hound containers: {cleaned}")

            # Check triggers and spawn hound containers
            triggered = await check_hound_triggers()
            if triggered:
                logger.info(f"Hound triggered for projects: {triggered}")

        except asyncio.CancelledError:
            logger.info("Hound trigger monitor stopped")
            break
        except Exception as e:
            logger.exception(f"Error in hound trigger monitor: {e}")
