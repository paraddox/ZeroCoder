"""
Agent SDK Application
=====================

Claude Agent SDK-based orchestrator for running Claude in Docker containers.
Replaces the CLI-based `claude --print` approach with proper SDK integration.

Features:
- Retry logic with exponential backoff
- State persistence for crash recovery
- Structured logging with prefixes for parsing
- Graceful interrupt handling
- Exit codes for different failure modes
- Runtime model selection via config file
- API-based communication with host for state management
"""

import asyncio
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

import requests

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
)

# Host API configuration (set by container environment)
HOST_API_URL = os.environ.get("HOST_API_URL", "http://host.docker.internal:8888")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "")
CONTAINER_NUMBER = int(os.environ.get("CONTAINER_NUMBER", "1"))

# Default model for coder/overseer agents
DEFAULT_AGENT_MODEL = "glm-4-7"

# Config file path (relative to project directory)
AGENT_CONFIG_FILE = "prompts/.agent_config.json"

# Agent log file (shared with container entrypoint for docker logs visibility)
AGENT_LOG_FILE = Path("/var/log/agent.log")


def log_to_file(message: str) -> None:
    """Append message to agent log file for docker logs visibility."""
    try:
        timestamp = datetime.utcnow().isoformat()
        with open(AGENT_LOG_FILE, "a") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        # Ignore errors (file may not exist during local testing)
        pass


def log(message: str) -> None:
    """Log to both stdout and agent log file."""
    print(message, flush=True)
    log_to_file(message)


def get_agent_model(project_dir: str) -> str:
    """
    Read agent model from environment variable or project config file.

    Priority:
    1. AGENT_MODEL environment variable (for initializer override)
    2. Project config file (prompts/.agent_config.json)
    3. DEFAULT_AGENT_MODEL fallback

    Args:
        project_dir: Path to project directory

    Returns:
        Model ID string (defaults to DEFAULT_AGENT_MODEL if not configured)
    """
    # Check for environment variable override (used by initializer)
    env_model = os.environ.get("AGENT_MODEL")
    if env_model:
        log(f"[CONFIG] Using model from environment: {env_model}")
        return env_model

    config_path = Path(project_dir) / AGENT_CONFIG_FILE
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            model = config.get("agent_model", DEFAULT_AGENT_MODEL)
            log(f"[CONFIG] Using model from config: {model}")
            return model
        except Exception as e:
            log(f"[CONFIG] Error reading config, using default: {e}")
    else:
        log(f"[CONFIG] No config file, using default model: {DEFAULT_AGENT_MODEL}")
    return DEFAULT_AGENT_MODEL

# Set permissive umask so all files created are world-readable/writable
# This ensures host user can access files created by container user
os.umask(0o000)

# State file for crash recovery (in project dir so host can read it)
# Previous location (/home/coder/.agent_state.json) was inaccessible from host
STATE_FILE = Path("/project/.agent_state.json")


def save_state(state: dict) -> None:
    """Persist state for crash recovery."""
    state["updated_at"] = datetime.utcnow().isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_state() -> dict | None:
    """Load previous state if exists."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return None
    return None


def clear_state() -> None:
    """Clear state after successful completion."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def check_graceful_stop(project_dir: str) -> bool:
    """Check if graceful stop was requested via host API."""
    # Fall back to file check if API not available (backwards compatibility)
    flag_file = Path(project_dir) / ".graceful_stop"
    if flag_file.exists():
        return True

    # Query host API for graceful stop state
    if not PROJECT_NAME:
        return False

    try:
        url = f"{HOST_API_URL}/api/projects/{PROJECT_NAME}/agent/containers/{CONTAINER_NUMBER}/session"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("graceful_stop_requested", False)
    except Exception as e:
        log(f"[WARN] Failed to check graceful stop via API: {e}")

    return False


def send_heartbeat() -> dict:
    """Send heartbeat to host API and get current session state."""
    if not PROJECT_NAME:
        return {}

    try:
        url = f"{HOST_API_URL}/api/projects/{PROJECT_NAME}/agent/containers/{CONTAINER_NUMBER}/heartbeat"
        response = requests.post(url, timeout=5, json={"status": "running"})
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        log(f"[WARN] Failed to send heartbeat: {e}")

    return {}


def get_session_config() -> dict:
    """Get session configuration from host API."""
    if not PROJECT_NAME:
        return {}

    try:
        url = f"{HOST_API_URL}/api/projects/{PROJECT_NAME}/agent/containers/{CONTAINER_NUMBER}/session"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        log(f"[WARN] Failed to get session config: {e}")

    return {}


async def run_agent(prompt: str, project_dir: str, max_retries: int = 3) -> int:
    """
    Run agent with retry logic and error recovery.

    Args:
        prompt: The instruction/prompt to send to Claude
        project_dir: Working directory for the agent
        max_retries: Maximum number of retry attempts

    Returns:
        Exit code (0=success, 1=failure, 129=graceful_stop, 130=interrupted)
    """
    # Check session state and send initial heartbeat
    session = get_session_config()
    if session:
        if session.get("graceful_stop_requested"):
            log("[AGENT] Graceful stop already requested, exiting early")
            return 129
        if not session.get("should_continue", True):
            log("[AGENT] Session indicates should not continue")
            return 0
        log(f"[AGENT] Session validated - user_started: {session.get('user_started')}")

    # Send initial heartbeat
    send_heartbeat()

    # Get model from project config (can be changed at runtime)
    model = get_agent_model(project_dir)

    options = ClaudeAgentOptions(
        model=model,
        cwd=project_dir,
        permission_mode="bypassPermissions",
        setting_sources=["project"],  # Load CLAUDE.md from project directory
    )

    # Check for previous incomplete run
    prev_state = load_state()
    if prev_state and prev_state.get("status") == "in_progress":
        log("[RECOVERY] Detected previous incomplete run")
        log(f"[RECOVERY] Previous attempt: {prev_state.get('attempt', 'unknown')}")

    attempt = 0
    last_error = None
    message_count = 0
    heartbeat_interval = 10  # Send heartbeat every 10 messages

    while attempt < max_retries:
        attempt += 1
        try:
            save_state({
                "status": "in_progress",
                "attempt": attempt,
                "prompt_length": len(prompt),
                "started_at": datetime.utcnow().isoformat(),
            })

            log(f"[AGENT] Starting attempt {attempt}/{max_retries}")

            async for message in query(prompt=prompt, options=options):
                message_count += 1

                # Stream output to stdout (captured by docker logs)
                # Use typed checks per SDK documentation
                if isinstance(message, AssistantMessage):
                    # Text content from assistant
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            log(block.text)
                        elif isinstance(block, ToolUseBlock):
                            # Tool use events - log for debugging
                            log(f"[TOOL] Using: {block.name}")

                # Periodic heartbeat to keep host updated
                if message_count % heartbeat_interval == 0:
                    heartbeat_response = send_heartbeat()
                    if heartbeat_response.get("graceful_stop_requested"):
                        log("[AGENT] Graceful stop requested via heartbeat")
                        clear_state()
                        return 129

                # Check for graceful stop after processing each message
                if check_graceful_stop(project_dir):
                    log("[AGENT] Graceful stop requested, completing current session...")
                    clear_state()
                    return 129

            # Success - clear state and exit
            clear_state()
            log("[AGENT] Completed successfully")
            return 0

        except KeyboardInterrupt:
            log("[AGENT] Interrupted by user")
            save_state({
                "status": "interrupted",
                "attempt": attempt,
                "interrupted_at": datetime.utcnow().isoformat(),
            })
            return 130

        except Exception as e:
            last_error = e
            error_msg = f"[ERROR] Attempt {attempt}/{max_retries} failed: {e}"
            log(error_msg)

            if attempt < max_retries:
                wait_time = 2 ** attempt  # Exponential backoff: 2, 4, 8 seconds
                log(f"[RETRY] Waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)
            else:
                save_state({
                    "status": "failed",
                    "attempt": attempt,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "traceback": traceback.format_exc(),
                    "failed_at": datetime.utcnow().isoformat(),
                })

    log(f"[AGENT] All {max_retries} attempts failed. Last error: {last_error}")
    return 1


def main() -> int:
    """Main entry point."""
    # Read prompt from stdin
    prompt = sys.stdin.read()

    if not prompt.strip():
        log("[ERROR] No prompt provided via stdin")
        return 1

    log(f"[AGENT] Received prompt ({len(prompt)} chars)")

    # Run the agent
    return asyncio.run(run_agent(prompt, "/project"))


if __name__ == "__main__":
    sys.exit(main())
