"""
Agent Application (Direct CLI Version)
======================================

Claude CLI-based orchestrator for running Claude in E2B sandboxes.
Uses subprocess to call claude directly, bypassing the SDK.

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
import subprocess
import traceback
from datetime import datetime, timezone
from pathlib import Path

import requests

# Host API configuration (set by container environment)
HOST_API_URL = os.environ.get("HOST_API_URL", "http://host.docker.internal:8888")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "")
CONTAINER_NUMBER = int(os.environ.get("CONTAINER_NUMBER", "1"))

# Default model for coder/overseer agents
DEFAULT_AGENT_MODEL = "sonnet"

# Config file path (relative to project directory)
AGENT_CONFIG_FILE = "prompts/.agent_config.json"

# Agent log file (shared with container entrypoint for docker logs visibility)
AGENT_LOG_FILE = Path("/var/log/agent.log")


def log_to_file(message: str) -> None:
    """Append message to agent log file for docker logs visibility."""
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
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
            model = config.get("model", config.get("agent_model", DEFAULT_AGENT_MODEL))
            log(f"[CONFIG] Using model from config: {model}")
            return model
        except Exception as e:
            log(f"[CONFIG] Error reading config, using default: {e}")
    else:
        log(f"[CONFIG] No config file, using default model: {DEFAULT_AGENT_MODEL}")
    return DEFAULT_AGENT_MODEL


# Set permissive umask so all files created are world-readable/writable
os.umask(0o000)

# State file for crash recovery (in project dir so host can read it)
# Use environment variable for project dir or default to /home/user/project for E2B
PROJECT_DIR = os.environ.get("PROJECT_DIR", "/home/user/project")
STATE_FILE = Path(f"{PROJECT_DIR}/.agent_state.json")


def save_state(state: dict) -> None:
    """Persist state for crash recovery."""
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
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


def run_claude_cli(prompt: str, project_dir: str, model: str) -> tuple[int, str]:
    """
    Run claude CLI directly via subprocess.

    Args:
        prompt: The instruction/prompt to send to Claude
        project_dir: Working directory for the agent
        model: Model to use (e.g., 'sonnet', 'opus')

    Returns:
        Tuple of (exit_code, output)
    """
    # Build the claude command
    cmd = [
        "claude",
        "-p", prompt,
        "--model", model,
        "--allowedTools", "Bash,Read,Write,Edit,Glob,Grep,LS",
        "--max-turns", "100",
    ]

    log(f"[CLI] Running claude with model: {model}")

    try:
        # Run claude and capture output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=project_dir,
            text=True,
            bufsize=1,  # Line buffered
        )

        output_lines = []
        if process.stdout:
            for line in process.stdout:
                log(line.rstrip())
                output_lines.append(line)

                # Check for graceful stop periodically
                if check_graceful_stop(project_dir):
                    log("[AGENT] Graceful stop requested, terminating...")
                    process.terminate()
                    return 129, "\n".join(output_lines)

        process.wait()
        return process.returncode, "\n".join(output_lines)

    except Exception as e:
        log(f"[ERROR] Failed to run claude CLI: {e}")
        return 1, str(e)


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

    # Check for previous incomplete run
    prev_state = load_state()
    if prev_state and prev_state.get("status") == "in_progress":
        log("[RECOVERY] Detected previous incomplete run")
        log(f"[RECOVERY] Previous attempt: {prev_state.get('attempt', 'unknown')}")

    attempt = 0
    last_error = None

    while attempt < max_retries:
        attempt += 1
        try:
            save_state({
                "status": "in_progress",
                "attempt": attempt,
                "prompt_length": len(prompt),
                "started_at": datetime.now(timezone.utc).isoformat(),
            })

            log(f"[AGENT] Starting attempt {attempt}/{max_retries}")

            # Run claude CLI directly
            exit_code, output = run_claude_cli(prompt, project_dir, model)

            if exit_code == 0:
                # Success - clear state and exit
                clear_state()
                log("[AGENT] Completed successfully")
                return 0
            elif exit_code == 129:
                # Graceful stop
                clear_state()
                return 129
            else:
                raise RuntimeError(f"Claude CLI exited with code {exit_code}")

        except KeyboardInterrupt:
            log("[AGENT] Interrupted by user")
            save_state({
                "status": "interrupted",
                "attempt": attempt,
                "interrupted_at": datetime.now(timezone.utc).isoformat(),
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
                    "failed_at": datetime.now(timezone.utc).isoformat(),
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
    return asyncio.run(run_agent(prompt, PROJECT_DIR))


if __name__ == "__main__":
    sys.exit(main())
