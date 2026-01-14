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
"""

import asyncio
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
)

# Default model for coder/overseer agents
DEFAULT_AGENT_MODEL = "glm-4-7"

# Config file path (relative to project directory)
AGENT_CONFIG_FILE = "prompts/.agent_config.json"


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
        print(f"[CONFIG] Using model from environment: {env_model}", flush=True)
        return env_model

    config_path = Path(project_dir) / AGENT_CONFIG_FILE
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            model = config.get("agent_model", DEFAULT_AGENT_MODEL)
            print(f"[CONFIG] Using model from config: {model}", flush=True)
            return model
        except Exception as e:
            print(f"[CONFIG] Error reading config, using default: {e}", flush=True)
    else:
        print(f"[CONFIG] No config file, using default model: {DEFAULT_AGENT_MODEL}", flush=True)
    return DEFAULT_AGENT_MODEL

# Set permissive umask so all files created are world-readable/writable
# This ensures host user can access files created by container user
os.umask(0o000)

# State file for crash recovery (in coder's home, not project dir due to permissions)
STATE_FILE = Path("/home/coder/.agent_state.json")


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
    """Check if graceful stop was requested via flag file."""
    flag_file = Path(project_dir) / ".graceful_stop"
    return flag_file.exists()


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
        print("[RECOVERY] Detected previous incomplete run", flush=True)
        print(f"[RECOVERY] Previous attempt: {prev_state.get('attempt', 'unknown')}", flush=True)

    attempt = 0
    last_error = None

    while attempt < max_retries:
        attempt += 1
        try:
            save_state({
                "status": "in_progress",
                "attempt": attempt,
                "prompt_length": len(prompt),
                "started_at": datetime.utcnow().isoformat(),
            })

            print(f"[AGENT] Starting attempt {attempt}/{max_retries}", flush=True)

            async for message in query(prompt=prompt, options=options):
                # Stream output to stdout (captured by docker logs)
                # Use typed checks per SDK documentation
                if isinstance(message, AssistantMessage):
                    # Text content from assistant
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            print(block.text, flush=True)
                        elif isinstance(block, ToolUseBlock):
                            # Tool use events - log for debugging
                            print(f"[TOOL] Using: {block.name}", flush=True)

                # Check for graceful stop after processing each message
                if check_graceful_stop(project_dir):
                    print("[AGENT] Graceful stop requested, completing current session...", flush=True)
                    clear_state()
                    return 129

            # Success - clear state and exit
            clear_state()
            print("[AGENT] Completed successfully", flush=True)
            return 0

        except KeyboardInterrupt:
            print("[AGENT] Interrupted by user", flush=True)
            save_state({
                "status": "interrupted",
                "attempt": attempt,
                "interrupted_at": datetime.utcnow().isoformat(),
            })
            return 130

        except Exception as e:
            last_error = e
            error_msg = f"[ERROR] Attempt {attempt}/{max_retries} failed: {e}"
            print(error_msg, flush=True)

            if attempt < max_retries:
                wait_time = 2 ** attempt  # Exponential backoff: 2, 4, 8 seconds
                print(f"[RETRY] Waiting {wait_time}s before retry...", flush=True)
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

    print(f"[AGENT] All {max_retries} attempts failed. Last error: {last_error}", flush=True)
    return 1


def main() -> int:
    """Main entry point."""
    # Read prompt from stdin
    prompt = sys.stdin.read()

    if not prompt.strip():
        print("[ERROR] No prompt provided via stdin", flush=True)
        return 1

    print(f"[AGENT] Received prompt ({len(prompt)} chars)", flush=True)

    # Run the agent
    return asyncio.run(run_agent(prompt, "/project"))


if __name__ == "__main__":
    sys.exit(main())
