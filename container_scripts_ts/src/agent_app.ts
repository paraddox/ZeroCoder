/**
 * Agent SDK Application
 * =====================
 *
 * Claude Agent SDK-based orchestrator for running Claude in Docker containers.
 * TypeScript port of agent_app.py using @anthropic-ai/claude-agent-sdk npm package.
 *
 * Features:
 * - Retry logic with exponential backoff
 * - State persistence for crash recovery
 * - Structured logging with prefixes for parsing
 * - Graceful interrupt handling
 * - Exit codes for different failure modes
 * - Runtime model selection via config file
 * - API-based communication with host for state management
 */

import { query } from "@anthropic-ai/claude-agent-sdk";
import type { Options } from "@anthropic-ai/claude-agent-sdk";
import * as fs from "fs";
import * as path from "path";

// Exit codes
const EXIT_SUCCESS = 0;
const EXIT_FAILURE = 1;
const EXIT_GRACEFUL_STOP = 129;
const EXIT_INTERRUPTED = 130;

// Host API configuration (set by container environment)
const HOST_API_URL = process.env.HOST_API_URL || "http://host.docker.internal:8888";
const PROJECT_NAME = process.env.PROJECT_NAME || "";
const CONTAINER_NUMBER = parseInt(process.env.CONTAINER_NUMBER || "1", 10);

// Default model for coder/overseer agents
const DEFAULT_AGENT_MODEL = "claude-sonnet-4-5-20250514";

// Config file path (relative to project directory)
const AGENT_CONFIG_FILE = "prompts/.agent_config.json";

// Agent log file (shared with container entrypoint for docker logs visibility)
const AGENT_LOG_FILE = "/var/log/agent.log";

// Project directory
const PROJECT_DIR = "/project";

// State file for crash recovery (in project dir so host can read it)
const STATE_FILE = path.join(PROJECT_DIR, ".agent_state.json");

// Graceful stop flag file (backwards compatibility)
const GRACEFUL_STOP_FLAG = path.join(PROJECT_DIR, ".graceful_stop");

/**
 * Get local ISO timestamp.
 */
function getLocalTimestamp(): string {
  const now = new Date();
  return now.toISOString();
}

/**
 * Append message to agent log file for docker logs visibility.
 */
function logToFile(message: string): void {
  try {
    const timestamp = getLocalTimestamp();
    fs.appendFileSync(AGENT_LOG_FILE, `[${timestamp}] ${message}\n`);
  } catch {
    // Ignore errors (file may not exist during local testing)
  }
}

/**
 * Log to both stdout and agent log file.
 */
function log(message: string): void {
  console.log(message);
  logToFile(message);
}

/**
 * Read agent model from environment variable or project config file.
 *
 * Priority:
 * 1. AGENT_MODEL environment variable (for initializer override)
 * 2. Project config file (prompts/.agent_config.json)
 * 3. DEFAULT_AGENT_MODEL fallback
 */
function getAgentModel(projectDir: string): string {
  // Check for environment variable override (used by initializer)
  const envModel = process.env.AGENT_MODEL;
  if (envModel) {
    log(`[CONFIG] Using model from environment: ${envModel}`);
    return envModel;
  }

  const configPath = path.join(projectDir, AGENT_CONFIG_FILE);
  if (fs.existsSync(configPath)) {
    try {
      const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
      const model = config.agent_model || DEFAULT_AGENT_MODEL;
      log(`[CONFIG] Using model from config: ${model}`);
      return model;
    } catch (e) {
      log(`[CONFIG] Error reading config, using default: ${e}`);
    }
  } else {
    log(`[CONFIG] No config file, using default model: ${DEFAULT_AGENT_MODEL}`);
  }
  return DEFAULT_AGENT_MODEL;
}

/**
 * Persist state for crash recovery.
 */
function saveState(state: Record<string, unknown>): void {
  try {
    state.updated_at = getLocalTimestamp();
    fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
  } catch {
    // Ignore errors
  }
}

/**
 * Load previous state if exists.
 */
function loadState(): Record<string, unknown> | null {
  if (fs.existsSync(STATE_FILE)) {
    try {
      return JSON.parse(fs.readFileSync(STATE_FILE, "utf8"));
    } catch {
      return null;
    }
  }
  return null;
}

/**
 * Clear state after successful completion.
 */
function clearState(): void {
  if (fs.existsSync(STATE_FILE)) {
    try {
      fs.unlinkSync(STATE_FILE);
    } catch {
      // Ignore errors
    }
  }
}

/**
 * Check if graceful stop was requested via host API.
 */
async function checkGracefulStop(projectDir: string): Promise<boolean> {
  // Fall back to file check if API not available (backwards compatibility)
  const flagFile = path.join(projectDir, ".graceful_stop");
  if (fs.existsSync(flagFile)) {
    return true;
  }

  // Query host API for graceful stop state
  if (!PROJECT_NAME) {
    return false;
  }

  try {
    const url = `${HOST_API_URL}/api/projects/${PROJECT_NAME}/agent/containers/${CONTAINER_NUMBER}/session`;
    const response = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (response.ok) {
      const data = (await response.json()) as { graceful_stop_requested?: boolean };
      return data.graceful_stop_requested === true;
    }
  } catch (e) {
    log(`[WARN] Failed to check graceful stop via API: ${e}`);
  }

  return false;
}

/**
 * Send heartbeat to host API and get current session state.
 */
async function sendHeartbeat(): Promise<Record<string, unknown>> {
  if (!PROJECT_NAME) {
    return {};
  }

  try {
    const url = `${HOST_API_URL}/api/projects/${PROJECT_NAME}/agent/containers/${CONTAINER_NUMBER}/heartbeat`;
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "running" }),
      signal: AbortSignal.timeout(5000),
    });
    if (response.ok) {
      return (await response.json()) as Record<string, unknown>;
    }
  } catch (e) {
    log(`[WARN] Failed to send heartbeat: ${e}`);
  }

  return {};
}

/**
 * Get session configuration from host API.
 */
async function getSessionConfig(): Promise<Record<string, unknown>> {
  if (!PROJECT_NAME) {
    return {};
  }

  try {
    const url = `${HOST_API_URL}/api/projects/${PROJECT_NAME}/agent/containers/${CONTAINER_NUMBER}/session`;
    const response = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (response.ok) {
      return (await response.json()) as Record<string, unknown>;
    }
  } catch (e) {
    log(`[WARN] Failed to get session config: ${e}`);
  }

  return {};
}

/**
 * Sleep for the specified number of milliseconds.
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Run agent with retry logic and error recovery.
 */
async function runAgent(
  prompt: string,
  projectDir: string,
  maxRetries: number = 3
): Promise<number> {
  // Check session state and send initial heartbeat
  const session = await getSessionConfig();
  if (session && typeof session === "object") {
    if (session.graceful_stop_requested) {
      log("[AGENT] Graceful stop already requested, exiting early");
      return EXIT_GRACEFUL_STOP;
    }
    if (session.should_continue === false) {
      log("[AGENT] Session indicates should not continue");
      return EXIT_SUCCESS;
    }
    log(`[AGENT] Session validated - user_started: ${session.user_started}`);
  }

  // Send initial heartbeat
  await sendHeartbeat();

  // Get model from project config (can be changed at runtime)
  const model = getAgentModel(projectDir);

  const options: Options = {
    model,
    cwd: projectDir,
    permissionMode: "bypassPermissions",
    settingSources: ["project"], // Load CLAUDE.md from project directory
  };

  // Check for previous incomplete run
  const prevState = loadState();
  if (prevState && prevState.status === "in_progress") {
    log("[RECOVERY] Detected previous incomplete run");
    log(`[RECOVERY] Previous attempt: ${prevState.attempt ?? "unknown"}`);
  }

  let attempt = 0;
  let lastError: Error | null = null;
  let messageCount = 0;
  const heartbeatInterval = 10; // Send heartbeat every 10 messages

  while (attempt < maxRetries) {
    attempt++;
    try {
      saveState({
        status: "in_progress",
        attempt,
        prompt_length: prompt.length,
        started_at: getLocalTimestamp(),
      });

      log(`[AGENT] Starting attempt ${attempt}/${maxRetries}`);

      const queryResult = query({
        prompt,
        options,
      });

      for await (const message of queryResult) {
        messageCount++;

        // Stream output to stdout (captured by docker logs)
        // Check message type and handle accordingly
        if (message.type === "assistant") {
          // Text content from assistant
          const content = message.message?.content;
          if (Array.isArray(content)) {
            for (const block of content) {
              if (block.type === "text") {
                log(block.text);
              } else if (block.type === "tool_use") {
                // Tool use events - log for debugging
                log(`[TOOL] Using: ${block.name}`);
              }
            }
          }
        }

        // Periodic heartbeat to keep host updated
        if (messageCount % heartbeatInterval === 0) {
          const heartbeatResponse = await sendHeartbeat();
          if (heartbeatResponse.graceful_stop_requested) {
            log("[AGENT] Graceful stop requested via heartbeat");
            clearState();
            return EXIT_GRACEFUL_STOP;
          }
        }

        // Check for graceful stop after processing each message
        if (await checkGracefulStop(projectDir)) {
          log("[AGENT] Graceful stop requested, completing current session...");
          clearState();
          return EXIT_GRACEFUL_STOP;
        }
      }

      // Success - clear state and exit
      clearState();
      log("[AGENT] Completed successfully");
      return EXIT_SUCCESS;
    } catch (e) {
      lastError = e instanceof Error ? e : new Error(String(e));
      const errorMsg = `[ERROR] Attempt ${attempt}/${maxRetries} failed: ${lastError.message}`;
      log(errorMsg);

      if (attempt < maxRetries) {
        const waitTime = Math.pow(2, attempt); // Exponential backoff: 2, 4, 8 seconds
        log(`[RETRY] Waiting ${waitTime}s before retry...`);
        await sleep(waitTime * 1000);
      } else {
        saveState({
          status: "failed",
          attempt,
          error: lastError.message,
          error_type: lastError.name,
          failed_at: getLocalTimestamp(),
        });
      }
    }
  }

  log(`[AGENT] All ${maxRetries} attempts failed. Last error: ${lastError?.message}`);
  return EXIT_FAILURE;
}

/**
 * Read all input from stdin.
 */
async function readStdin(): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => {
      resolve(data);
    });
    process.stdin.on("error", reject);
  });
}

/**
 * Main entry point.
 */
async function main(): Promise<number> {
  // Handle interrupt signal
  process.on("SIGINT", () => {
    log("[AGENT] Interrupted by user");
    saveState({
      status: "interrupted",
      interrupted_at: getLocalTimestamp(),
    });
    process.exit(EXIT_INTERRUPTED);
  });

  process.on("SIGTERM", () => {
    log("[AGENT] Terminated");
    saveState({
      status: "terminated",
      terminated_at: getLocalTimestamp(),
    });
    process.exit(EXIT_GRACEFUL_STOP);
  });

  // Read prompt from stdin
  const prompt = await readStdin();

  if (!prompt.trim()) {
    log("[ERROR] No prompt provided via stdin");
    return EXIT_FAILURE;
  }

  log(`[AGENT] Received prompt (${prompt.length} chars)`);

  // Run the agent
  return runAgent(prompt, PROJECT_DIR);
}

// Run main
main()
  .then((exitCode) => {
    process.exit(exitCode);
  })
  .catch((error) => {
    log(`[FATAL] ${error}`);
    process.exit(EXIT_FAILURE);
  });
