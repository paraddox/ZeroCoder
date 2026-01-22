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

# Staggered startup delay in seconds between containers
CONTAINER_STARTUP_DELAY = 60

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

        # Local path is the projects dir (used for reading prompts/config locally)
        from registry import get_projects_dir
        self.project_dir = project_dir or (get_projects_dir() / project_name)

        # Container naming: init container vs coding containers
        if container_number == 0:  # Init container
            self.container_name = f"zerocoder-{project_name}-init"
            self._is_init_container = True
        else:  # Coding container
            self.container_name = f"zerocoder-{project_name}-{container_number}"
            self._is_init_container = False

        self._status: Literal["not_created", "running", "stopped", "completed"] = "not_created"
        self.started_at: datetime | None = None
        self._log_task: asyncio.Task | None = None

        # Track current agent type for OpenCode SDK routing
        self._current_agent_type: Literal["coder", "reviewer", "overseer"] = "coder"
        # Force Claude SDK for initializer (regardless of project model)
        self._force_claude_sdk: bool = False
        # Track current feature being worked on (detected from logs)
        self._current_feature: str | None = None
        # Model to use when forcing Claude SDK (defaults to Opus 4.5)
        self._forced_model: str = "claude-opus-4-5-20251101"

        # Note: Session state (user_started, graceful_stop_requested, restarting,
        # last_agent_was_overseer, is_milestone_overseer, last_activity) is now
        # stored in the database and accessed via registry functions.

        # Callbacks for WebSocket notifications
        self._output_callbacks: Set[Callable[[str], Awaitable[None]]] = set()
        self._status_callbacks: Set[Callable[[str], Awaitable[None]]] = set()
        self._callbacks_lock = threading.Lock()

        # Check initial container status
        self._sync_status()

    # =========================================================================
    # Session State Properties (DB-backed)
    # =========================================================================

    @property
    def _user_started(self) -> bool:
        """Check if user started this container (from database)."""
        from registry import is_user_started
        return is_user_started(self.project_name, self.container_number, self.container_type)

    @_user_started.setter
    def _user_started(self, value: bool) -> None:
        """Set user started state (to database)."""
        from registry import set_user_started
        set_user_started(self.project_name, self.container_number, value, self.container_type)

    @property
    def _graceful_stop_requested(self) -> bool:
        """Check if graceful stop was requested (from database)."""
        from registry import is_graceful_stop_requested
        return is_graceful_stop_requested(self.project_name, self.container_number, self.container_type)

    @_graceful_stop_requested.setter
    def _graceful_stop_requested(self, value: bool) -> None:
        """Set graceful stop requested state (to database)."""
        from registry import set_graceful_stop
        set_graceful_stop(self.project_name, self.container_number, value, self.container_type)

    @property
    def _restarting(self) -> bool:
        """Check if container is restarting (from database)."""
        from registry import is_restarting
        return is_restarting(self.project_name, self.container_number, self.container_type)

    @_restarting.setter
    def _restarting(self, value: bool) -> None:
        """Set restarting state (to database)."""
        from registry import set_restarting
        set_restarting(self.project_name, self.container_number, value, self.container_type)

    @property
    def _last_agent_was_overseer(self) -> bool:
        """Check if last agent was overseer (from database)."""
        from registry import get_overseer_flags
        last_was, _ = get_overseer_flags(self.project_name, self.container_number, self.container_type)
        return last_was

    @_last_agent_was_overseer.setter
    def _last_agent_was_overseer(self, value: bool) -> None:
        """Set last agent was overseer flag (to database)."""
        from registry import set_overseer_flags, get_overseer_flags
        _, is_milestone = get_overseer_flags(self.project_name, self.container_number, self.container_type)
        set_overseer_flags(self.project_name, self.container_number, value, is_milestone, self.container_type)

    @property
    def _is_milestone_overseer(self) -> bool:
        """Check if this is a milestone overseer (from database)."""
        from registry import get_overseer_flags
        _, is_milestone = get_overseer_flags(self.project_name, self.container_number, self.container_type)
        return is_milestone

    @_is_milestone_overseer.setter
    def _is_milestone_overseer(self, value: bool) -> None:
        """Set milestone overseer flag (to database)."""
        from registry import set_overseer_flags, get_overseer_flags
        last_was, _ = get_overseer_flags(self.project_name, self.container_number, self.container_type)
        set_overseer_flags(self.project_name, self.container_number, last_was, value, self.container_type)

    @property
    def last_activity(self) -> datetime | None:
        """Get last activity timestamp (from database)."""
        from registry import get_last_activity
        return get_last_activity(self.project_name, self.container_number, self.container_type)

    @last_activity.setter
    def last_activity(self, value: datetime | None) -> None:
        """Set last activity timestamp (to database)."""
        if value is not None:
            from registry import update_last_activity
            update_last_activity(self.project_name, self.container_number, self.container_type)

    def _sync_status(self) -> None:
        """Sync status with actual Docker container state (Docker is source of truth)."""
        # Preserve "completed" status - don't overwrite it
        if self._status == "completed":
            return

        # Note: user_started is now read from database on-demand via property

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
            else:
                # Load current_feature from DB if not already set in memory
                if self._current_feature is None and db_container.get("current_feature"):
                    self._current_feature = db_container.get("current_feature")

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
        """Whether the user explicitly started this container (from DB)."""
        return self._user_started  # Uses DB-backed property

    def has_open_features(self) -> bool:
        """Check if project has open features using BeadsManager."""
        from .beads_manager import get_cached_stats

        try:
            stats = get_cached_stats(self.project_name)
            return stats.get("pending", 0) + stats.get("in_progress", 0) > 0
        except Exception as e:
            logger.warning(f"Failed to check open features: {e}")
            return True  # Assume features exist on error (safer)

    # =========================================================================
    # Git State Recovery
    # =========================================================================

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

            def get_default_branch() -> str:
                """Get the default branch name from remote."""
                # Try to get from remote HEAD
                result = run_git(["git", "symbolic-ref", "refs/remotes/origin/HEAD"])
                if result.returncode == 0:
                    ref = result.stdout.strip()
                    return ref.split("/")[-1]
                # Try common default branch names
                for branch in ["main", "master", "develop"]:
                    result = run_git(["git", "rev-parse", "--verify", f"origin/{branch}"])
                    if result.returncode == 0:
                        return branch
                # Last resort: get first remote branch
                result = run_git(["git", "branch", "-r", "--list", "origin/*"])
                if result.returncode == 0 and result.stdout.strip():
                    first_branch = result.stdout.strip().split("\n")[0].strip()
                    # Remove "origin/" prefix and any "-> origin/X" pointer
                    if " -> " in first_branch:
                        first_branch = first_branch.split(" -> ")[1]
                    return first_branch.replace("origin/", "")
                return "main"  # Ultimate fallback

            default_branch = get_default_branch()

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

            # 4. Fetch latest from origin (explicit refspec ensures all branches are fetched)
            result = run_git(["git", "fetch", "origin", "+refs/heads/*:refs/remotes/origin/*"], timeout=60)
            if result.returncode != 0:
                logger.warning(f"git fetch failed after recovery: {result.stderr}")
                # Try one more gc + fetch in case of persistent ref issues
                run_git(["git", "gc", "--prune=now"], timeout=60)
                result = run_git(["git", "fetch", "origin", "+refs/heads/*:refs/remotes/origin/*"], timeout=60)

            # 5. Check current branch and status
            result = run_git(["git", "status", "--porcelain"])
            has_changes = bool(result.stdout.strip()) if result.returncode == 0 else False

            # 6. Reset to clean state - discard any uncommitted changes
            if has_changes:
                logger.info("Discarding uncommitted changes during git recovery")
                run_git(["git", "reset", "--hard", "HEAD"])
                run_git(["git", "clean", "-fd"])  # Remove untracked files

            # 7. Checkout and reset default branch to match origin
            result = run_git(["git", "checkout", default_branch])
            if result.returncode != 0:
                # May fail if branch doesn't exist or other git state issues
                logger.warning(f"Checkout {default_branch} failed: {result.stderr}")

            # Check if origin/default_branch exists before resetting
            result = run_git(["git", "rev-parse", "--verify", f"origin/{default_branch}"])
            if result.returncode == 0:
                result = run_git(["git", "reset", "--hard", f"origin/{default_branch}"])
                if result.returncode != 0:
                    logger.warning(f"Failed to reset to origin/{default_branch}: {result.stderr}")
            else:
                # Just reset to HEAD if remote ref doesn't exist
                run_git(["git", "reset", "--hard", "HEAD"])
                logger.warning(f"Remote ref origin/{default_branch} not found, reset to HEAD")

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
        Run before agent starts: pull latest code and sync beads.

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
            "unstaged changes",  # git pull --rebase requires clean state
            "uncommitted changes",
            "is already checked out",  # branch conflict
        ]

        def needs_recovery(stderr: str) -> bool:
            return any(pattern in stderr for pattern in recoverable_errors)

        def run_git(cmd: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["docker", "exec", "-u", "coder", self.container_name] + cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

        def get_default_branch() -> str:
            """Get the default branch name from remote."""
            # Try to get from remote HEAD
            result = run_git(["git", "symbolic-ref", "refs/remotes/origin/HEAD"])
            if result.returncode == 0:
                ref = result.stdout.strip()
                return ref.split("/")[-1]
            # Try common default branch names
            for branch in ["main", "master", "develop"]:
                result = run_git(["git", "rev-parse", "--verify", f"origin/{branch}"])
                if result.returncode == 0:
                    return branch
            # Last resort: get first remote branch
            result = run_git(["git", "branch", "-r", "--list", "origin/*"])
            if result.returncode == 0 and result.stdout.strip():
                first_branch = result.stdout.strip().split("\n")[0].strip()
                if " -> " in first_branch:
                    first_branch = first_branch.split(" -> ")[1]
                return first_branch.replace("origin/", "")
            return "main"  # Ultimate fallback

        try:
            await self._broadcast_output("[System] Syncing with remote before starting agent...")

            # Check if origin remote exists before attempting fetch
            origin_check = run_git(["git", "remote", "get-url", "origin"])
            has_origin = origin_check.returncode == 0
            if not has_origin:
                logger.warning(f"No origin remote configured in container - skipping fetch")
                await self._broadcast_output("[System] Warning: No origin remote - using existing code")

            # Detect default branch
            default_branch = get_default_branch()

            # Fetch latest, discard local changes, reset to origin/default_branch
            # Note: Use explicit refspec to ensure all remote branches are fetched
            if has_origin:
                commands = [
                    (["git", "fetch", "origin", "+refs/heads/*:refs/remotes/origin/*"], "Fetching from origin", False),
                    (["git", "reset", "--hard", "HEAD"], "Discarding local changes", True),
                    (["git", "clean", "-fd"], "Removing untracked files", True),
                    (["git", "reset", "--hard", f"origin/{default_branch}"], f"Resetting to origin/{default_branch}", False),
                ]
            else:
                # No origin - just clean up local state
                commands = [
                    (["git", "reset", "--hard", "HEAD"], "Discarding local changes", True),
                    (["git", "clean", "-fd"], "Removing untracked files", True),
                ]

            recovery_attempted = False
            for item in commands:
                cmd, desc = item[0], item[1]
                # is_critical indicates if failure should trigger recovery
                is_critical = item[2] if len(item) > 2 else True

                result = subprocess.run(
                    ["docker", "exec", "-u", "coder", self.container_name] + cmd,
                    capture_output=True,
                    text=True,
                    timeout=PRE_AGENT_SYNC_TIMEOUT,
                )
                if result.returncode != 0:
                    error_msg = result.stderr + result.stdout
                    logger.warning(f"{desc} failed: {error_msg}")

                    # Check for SSH/network errors that shouldn't trigger full recovery
                    ssh_errors = ["Host key verification failed", "Permission denied", "Connection refused", "Could not resolve host"]
                    is_ssh_error = any(e in error_msg for e in ssh_errors)

                    if is_ssh_error and "fetch" in desc.lower():
                        # SSH/network errors during fetch are non-fatal - container has code
                        logger.warning(f"Network/SSH error during fetch - continuing with existing code")
                        await self._broadcast_output("[System] Fetch failed (network/SSH) - using existing code...")
                        continue

                    # Check if this is a recoverable git error
                    if is_critical and not recovery_attempted and needs_recovery(error_msg):
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

        Uses BeadsSyncManager for reads (instant) and run_beads_write_command for writes.

        Returns:
            Tuple of (success, message)
        """
        from .beads_manager import get_beads_sync_manager
        from server.routers.beads_api import run_beads_write_command

        try:
            # READ: Get in_progress features locally (instant)
            manager = get_beads_sync_manager(self.project_name, self.git_url)
            features = manager.get_tasks_by_status("in_progress")

            if not features:
                return True, "No stuck features to recover"

            # WRITE: Reset each to open via host bd command
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

            # WRITE: Sync after recovery
            await run_beads_write_command(self.project_name, ["sync"])

            logger.info(f"Recovered {recovered} stuck features for {self.project_name}")
            return True, f"Recovered {recovered} stuck features"

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

                # Detect feature claim from echo output: "Claimed project-xxxx, working on branch..."
                # Or: "Working on feature: project-xxxx"
                claim_match = re.search(r'Claimed ([\w]+-[\w]+),', sanitized)
                if not claim_match:
                    claim_match = re.search(r'Working on feature: ([\w]+-[\w]+)', sanitized)
                if claim_match:
                    await self._set_current_feature(claim_match.group(1))

                # Detect feature complete: bd close project-xxxx
                close_match = re.search(r'bd close ([\w]+-[\w]+)', sanitized)
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
                # user_started set via DB-backed property
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
                # Update registry status
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

                # Create new standalone container (clones repo at runtime)
                # No volume mounts needed - SSH key is baked into image
                cmd = [
                    "docker", "run", "-d",
                    "--name", self.container_name,
                    # Enable host.docker.internal on Linux (works natively on Mac/Windows)
                    "--add-host", "host.docker.internal:host-gateway",
                    # Memory limits to prevent OOM crashes (agents can use 1GB+ RSS)
                    "--memory", "4g",
                    "--memory-swap", "4g",
                ]
                # Pass git URL for container to clone (always clones main branch)
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
                cmd.extend(["-e", f"CONTAINER_NUMBER={self.container_number}"])
                server_port = os.getenv("PORT", "8888")
                cmd.extend(["-e", f"HOST_API_URL=http://host.docker.internal:{server_port}"])
                # Pass TZ env var for Node.js if available
                tz = os.getenv("TZ")
                if tz:
                    cmd.extend(["-e", f"TZ={tz}"])
                cmd.append(CONTAINER_IMAGE)

                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode != 0:
                    return False, f"Failed to create container: {result.stderr}"

                # Register new container in database
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
            # user_started set via DB-backed property

            # Start log streaming
            self._log_task = asyncio.create_task(self._stream_logs())

            # Handle init container specially
            if self._is_init_container:
                # Wait for git clone to complete (entrypoint clones repo at startup)
                for attempt in range(30):  # Up to 60 seconds for clone
                    await asyncio.sleep(2)
                    check = subprocess.run(
                        ["docker", "exec", "-u", "coder", self.container_name,
                         "test", "-e", "/project/.git"],
                        capture_output=True,
                        text=True,
                    )
                    if check.returncode == 0:
                        logger.info(f"Init container {self.container_name}: repository cloned successfully")
                        break
                    logger.info(f"Waiting for git clone (attempt {attempt + 1}/30)")
                else:
                    return False, "Repository clone failed or timed out"

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
                # Wait for git clone to complete (entrypoint clones repo at startup)
                for attempt in range(30):  # Up to 60 seconds for clone
                    await asyncio.sleep(2)
                    check = subprocess.run(
                        ["docker", "exec", "-u", "coder", self.container_name,
                         "test", "-e", "/project/.git"],
                        capture_output=True,
                        text=True,
                    )
                    if check.returncode == 0:
                        logger.info(f"Container {self.container_name}: repository cloned successfully")
                        break
                    logger.info(f"Waiting for git clone (attempt {attempt + 1}/30)")
                else:
                    return False, "Repository clone failed or timed out"

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

    async def stop(self, preserve_user_started: bool = False) -> tuple[bool, str]:
        """
        Stop the container (don't remove it).

        Args:
            preserve_user_started: If True, don't reset the _user_started flag.
                                   Used during programmatic restarts to maintain auto-restart capability.

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

            # Reset graceful stop flag in database
            self._graceful_stop_requested = False

            # Reset user_started flag to prevent auto-restart (unless preserving for restart)
            # User explicitly stopped, so we shouldn't auto-restart
            if not preserve_user_started:
                logger.info(f"[STOP] Resetting _user_started flag for {self.container_name}")
                self._user_started = False
            else:
                logger.info(f"[STOP] Preserving _user_started flag for {self.container_name} (programmatic restart)")

            # Clear verification state if this container was running verification
            if self._last_agent_was_overseer:
                clear_verification_state(self.project_name)

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
            # Set flag in database (container queries API to check this)
            self._graceful_stop_requested = True

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
            return await self.restart_agent()

        # Handle graceful stop - exit code 129 or flag is set
        if exit_code == 129 or self._graceful_stop_requested:
            logger.info(f"Graceful stop completed for {self.container_name}")
            await self._broadcast_output("[System] Graceful stop completed")

            # Reset flag in database and stop container
            self._graceful_stop_requested = False
            await self.stop()
            return True, "Graceful stop completed"

        if exit_code == 0:
            # Success - determine next action
            logger.info(f"[EXIT] Agent exited successfully (code 0) in {self.container_name}, agent_type={self._current_agent_type}, _user_started={self._user_started}")

            # Handle reviewer completion - clear tracked feature and switch back to coder
            if self._current_agent_type == "reviewer":
                from registry import set_last_closed_feature
                set_last_closed_feature(self.project_name, self.container_number, None, self.container_type)
                logger.info(f"[REVIEWER] Review complete in {self.container_name}, switching to coder")
                self._current_agent_type = "coder"
                # Continue to normal coder restart flow below

            # Post-agent cleanup: remove feature branches
            cleanup_ok, cleanup_msg = await self.post_agent_cleanup()
            if not cleanup_ok:
                logger.warning(f"Post-agent cleanup failed: {cleanup_msg}")
                # Continue anyway - cleanup failure shouldn't block flow

            if self.has_open_features() and not self._graceful_stop_requested:
                # Features remain - check if we need to run reviewer first
                if self._current_agent_type == "coder":
                    from registry import get_last_closed_feature
                    closed_feature_id = get_last_closed_feature(
                        self.project_name, self.container_number, self.container_type
                    )
                    if closed_feature_id:
                        # Run reviewer before restarting coder
                        logger.info(f"[EXIT] Running reviewer for {closed_feature_id} in {self.container_name}")
                        await self._broadcast_output(f"[System] Running review for {closed_feature_id}...")
                        return await self.restart_with_reviewer(closed_feature_id)

                # No feature to review, or reviewer already ran - restart coding agent
                logger.info(f"[EXIT] Features remain in {self.container_name}, restarting coding agent...")
                await self._broadcast_output("[System] Session complete. Starting fresh context for next task...")

                # Check for 10% milestone BEFORE restarting (spawns overseer in parallel if milestone hit)
                await self._check_overseer_milestone()

                self._last_agent_was_overseer = False
                return await self.restart_agent()
            elif not self.has_open_features() and not self._graceful_stop_requested:
                # All features closed - determine verification flow
                if self._last_agent_was_overseer:
                    # Overseer completed - check if it's a milestone overseer or final overseer
                    clear_verification_state(self.project_name)  # Release lock first

                    if self._is_milestone_overseer:
                        # Milestone overseer completed - just stop, don't affect other containers
                        logger.info(f"Milestone overseer completed in {self.container_name}")
                        await self._broadcast_output("[System] Milestone verification complete.")
                        await self.stop()
                        self._is_milestone_overseer = False
                        return True, "Milestone verification complete"

                    if self.has_open_features():
                        # Overseer created new issues - restart all containers to work on them
                        logger.info(f"Overseer created new issues in {self.project_name}, restarting containers...")
                        await self._broadcast_output("[System] Verification found issues. Restarting to fix them...")
                        await self._restart_other_containers()
                        self._last_agent_was_overseer = False
                        return await self.restart_agent()
                    else:
                        # Project is truly complete
                        logger.info(f"Verification complete in {self.container_name}! All features verified.")
                        await self._broadcast_output("[System] Verification complete! All features verified.")
                        await self.stop()
                        self.status = "completed"
                        await self._stop_other_containers()
                        return True, "All features verified complete"
                else:
                    # Try to acquire verification lock - only one container runs overseer
                    if set_verification_running(self.project_name, True):
                        # We got the lock - run overseer directly (simplified flow)
                        logger.info(f"All features closed in {self.container_name}, running overseer verification...")
                        await self._broadcast_output("[System] All features complete. Running final verification...")
                        return await self.restart_with_overseer()
                    else:
                        # Another container is already running verification - wait (stop gracefully)
                        logger.info(f"Verification already running for {self.project_name}, stopping {self.container_name}")
                        await self._broadcast_output("[System] Verification running in another container. Waiting...")
                        await self.stop()
                        return True, "Stopped - verification running elsewhere"
            else:
                logger.info(f"[EXIT] Not restarting: graceful_stop={self._graceful_stop_requested}, has_open_features={self.has_open_features()}")
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

            # Auto-restart if features remain and graceful stop not requested
            if self.has_open_features() and not self._graceful_stop_requested:
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
                if "No such container" not in result.stderr:
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
        to restart Claude Code. If restart fails (e.g., due to git issues),
        falls back to removing and recreating the container.

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
            # Stop the container (preserve user_started so auto-restart continues working)
            await self.stop(preserve_user_started=True)

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

            # First attempt: normal restart (stop + start)
            success, message = await self.start(instruction)

            if success:
                return success, message

            # Fallback: if start failed (likely git issues), remove and recreate container
            logger.warning(
                f"{self.container_name}: Restart failed ({message}), "
                "attempting full container recreation"
            )
            await self.remove()
            success, message = await self.start(instruction)

            if not success:
                logger.error(
                    f"{self.container_name}: Container recreation also failed: {message}"
                )

            return success, message
        finally:
            self._restarting = False

    async def restart_with_reviewer(self, feature_id: str) -> tuple[bool, str]:
        """
        Restart the agent with the reviewer prompt to verify a closed feature.

        This is called after a coder session successfully closes a feature.
        The reviewer checks the implementation and may reopen the issue if unsatisfied.

        Args:
            feature_id: The feature ID to review (e.g., "beads-42")

        Returns:
            Tuple of (success, message)
        """
        logger.info(f"Starting reviewer for feature {feature_id} in container {self.container_name}")

        self._restarting = True
        try:
            # Stop the container (preserve user_started so auto-restart continues working)
            await self.stop(preserve_user_started=True)

            # Get the reviewer prompt with feature ID injected
            import sys
            from pathlib import Path
            root = Path(__file__).parent.parent.parent
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            from prompts import get_reviewer_prompt

            try:
                instruction = get_reviewer_prompt(self.project_dir, feature_id)
            except FileNotFoundError:
                # No reviewer template - skip review and restart coder
                logger.warning(f"No reviewer_prompt.md found, skipping review for {feature_id}")
                from registry import set_last_closed_feature
                set_last_closed_feature(self.project_name, self.container_number, None, self.container_type)
                return await self.restart_agent()

            # Mark that we're running reviewer agent
            self._current_agent_type = "reviewer"
            self._last_agent_was_overseer = False
            # Use project's configured model (not forced Claude SDK)
            self._force_claude_sdk = False

            # Start container with reviewer instruction
            return await self.start(instruction)
        finally:
            self._restarting = False

    async def _check_overseer_milestone(self) -> None:
        """
        Check if we've hit a new 10% milestone and spawn overseer if so.

        Overseer runs at every 10% milestone (10%, 20%, 30%, ... up to 90%).
        The overseer runs in parallel with coding agents (doesn't block them).
        """
        from .beads_manager import get_cached_stats
        from registry import get_overseer_milestone

        stats = get_cached_stats(self.project_name)
        if not stats or stats.get('total', 0) == 0:
            return

        # Calculate current milestone (floor to nearest 10%)
        percentage = stats.get('percentage', 0)
        current_milestone = int(percentage // 10) * 10
        last_milestone = get_overseer_milestone(self.project_name)

        # Trigger at 10%, 20%, 30%... up to 90% (not at 0% or 100%)
        if current_milestone > last_milestone and 0 < current_milestone < 100:
            logger.info(f"[{self.project_name}] Hit {current_milestone}% milestone - spawning overseer")
            await self._spawn_overseer_at_milestone(current_milestone)

    async def _spawn_overseer_at_milestone(self, milestone: int) -> None:
        """
        Spawn overseer container at 10% milestone (runs in parallel).

        The overseer runs in a separate container and doesn't block coding agents.
        It verifies implementations and creates issues for problems found.

        Args:
            milestone: The milestone percentage (10, 20, 30, ..., 90)
        """
        from registry import update_overseer_milestone
        from prompts import get_overseer_prompt

        # Update milestone tracker immediately to prevent duplicate triggers
        update_overseer_milestone(self.project_name, milestone)

        # Check if overseer already running (use existing verification lock)
        if not set_verification_running(self.project_name, True):
            logger.info(f"[{self.project_name}] Overseer already running, skipping milestone trigger")
            return

        try:
            await self._broadcast_output(f"[System] {milestone}% milestone reached - running quality verification...")

            # Create overseer container (use container_number=0 for overseer)
            overseer_manager = ContainerManager(
                project_name=self.project_name,
                git_url=self.git_url,
                container_number=0  # Overseer always uses container 0
            )
            overseer_manager._current_agent_type = "overseer"
            overseer_manager._is_milestone_overseer = True  # Track that this is a milestone run
            overseer_manager._last_agent_was_overseer = True  # Mark as overseer for exit handling
            overseer_manager._user_started = True  # Mark as user-started for proper handling

            # Get overseer prompt and start (runs in background, doesn't block)
            try:
                prompt = get_overseer_prompt(self.project_dir)
            except FileNotFoundError:
                logger.warning(f"[{self.project_name}] No overseer prompt found, skipping milestone verification")
                set_verification_running(self.project_name, False)
                return

            # Start overseer in background task (doesn't block coding agent)
            asyncio.create_task(self._run_milestone_overseer(overseer_manager, prompt, milestone))

        except Exception as e:
            logger.error(f"[{self.project_name}] Failed to spawn overseer: {e}")
            set_verification_running(self.project_name, False)

    async def _run_milestone_overseer(
        self,
        overseer_manager: "ContainerManager",
        prompt: str,
        milestone: int
    ) -> None:
        """
        Run the milestone overseer and handle its completion.

        This runs in a background task and releases the verification lock when done.
        """
        try:
            logger.info(f"[{self.project_name}] Starting milestone overseer at {milestone}%")
            success, message = await overseer_manager.start(prompt)
            if not success:
                logger.warning(f"[{self.project_name}] Milestone overseer failed to start: {message}")
        except Exception as e:
            logger.error(f"[{self.project_name}] Milestone overseer error: {e}")
        finally:
            # Note: verification lock is released in _handle_agent_exit when overseer completes
            # For milestone overseers, we release it here if the start failed
            if overseer_manager._status != "running":
                clear_verification_state(self.project_name)

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
            # Stop the container (preserve user_started so auto-restart continues working)
            await self.stop(preserve_user_started=True)

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
                    clear_verification_state(self.project_name)
                    return False, "No overseer_prompt.md found in project or templates"
            else:
                try:
                    instruction = overseer_prompt_path.read_text()
                except Exception as e:
                    clear_verification_state(self.project_name)
                    return False, f"Failed to read overseer prompt: {e}"

            # Mark that we're running overseer (final verification, not milestone)
            self._last_agent_was_overseer = True
            self._is_milestone_overseer = False  # This is the final 100% verification
            # Set agent type for OpenCode routing
            self._current_agent_type = "overseer"
            # Use project's configured model (not forced Claude SDK)
            self._force_claude_sdk = False

            # Start container with instruction
            success, message = await self.start(instruction)
            if not success:
                clear_verification_state(self.project_name)
            return success, message
        except Exception as e:
            clear_verification_state(self.project_name)
            raise
        finally:
            self._restarting = False

    async def _stop_other_containers(self) -> None:
        """Stop all other containers for this project (called when project complete)."""
        all_managers = get_all_container_managers(self.project_name)
        for manager in all_managers:
            if manager.container_number != self.container_number:
                if manager.status == "running":
                    logger.info(f"Stopping {manager.container_name} (project complete)")
                    await manager.stop()
                    manager.status = "completed"

    async def _restart_other_containers(self) -> None:
        """Restart stopped containers for this project (called when new issues found)."""
        all_managers = get_all_container_managers(self.project_name)
        for manager in all_managers:
            if manager.container_number != self.container_number:
                if manager.status == "stopped" and manager._user_started:
                    logger.info(f"Restarting {manager.container_name} (new issues to work on)")
                    manager._last_agent_was_overseer = False
                    await manager.restart_agent()

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

                # Create new standalone container (clones repo at runtime)
                # No volume mounts needed - SSH key is baked into image
                cmd = [
                    "docker", "run", "-d",
                    "--name", self.container_name,
                    # Enable host.docker.internal on Linux (works natively on Mac/Windows)
                    "--add-host", "host.docker.internal:host-gateway",
                    # Memory limits to prevent OOM crashes (agents can use 1GB+ RSS)
                    "--memory", "4g",
                    "--memory-swap", "4g",
                ]
                # Pass git URL for container to clone (always clones main branch)
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
                cmd.extend(["-e", f"CONTAINER_NUMBER={self.container_number}"])
                server_port = os.getenv("PORT", "8888")
                cmd.extend(["-e", f"HOST_API_URL=http://host.docker.internal:{server_port}"])
                # Pass TZ env var for Node.js if available
                tz = os.getenv("TZ")
                if tz:
                    cmd.extend(["-e", f"TZ={tz}"])
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

# Project-level verification state tracking (now DB-backed)
# Import functions from registry for verification state management
from registry import (
    is_verification_running,
    set_verification_running,
    clear_verification_state,
)


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
    """Get all container managers for a project (thread-safe)."""
    result = []
    with _managers_lock:
        if project_name in _managers:
            result.extend(_managers[project_name].values())
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
    """Force remove ALL containers on server shutdown.

    All containers are removed unconditionally when the server shuts down.
    Users must explicitly restart containers after server restart.
    """
    logger.info("Force removing all containers on shutdown...")

    # Force remove ALL zerocoder containers (both tracked and orphaned)
    # This is more reliable than stopping them one by one via managers
    await stop_orphaned_containers()

    with _managers_lock:
        _managers.clear()


async def stop_orphaned_containers() -> None:
    """Force remove any zerocoder-* containers not tracked in our registry."""
    try:
        # List all containers with zerocoder- prefix (including stopped)
        result = subprocess.run(
            ["docker", "ps", "-aq", "--filter", "name=zerocoder-"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            container_ids = result.stdout.strip().split("\n")
            for container_id in container_ids:
                if container_id:
                    logger.info(f"Force removing container: {container_id}")
                    subprocess.run(
                        ["docker", "rm", "-f", container_id],
                        capture_output=True,
                        timeout=10,
                    )
    except Exception as e:
        logger.warning(f"Error removing orphaned containers: {e}")


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
                manager._user_started = False  # Clear via DB-backed property
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


