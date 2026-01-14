/**
 * OpenCode Agent Application
 * ==========================
 *
 * OpenCode SDK-based orchestrator for running GLM-4.7 agents in Docker containers.
 * Mirrors the behavior of agent_app.py but uses OpenCode SDK instead of Claude Agent SDK.
 *
 * Features:
 * - Reads prompt from stdin
 * - Selects agent based on OPENCODE_AGENT_TYPE env var
 * - Streams output to stdout (for docker logs)
 * - Handles exit codes matching Python agent (0=success, 1=failure, 129=graceful_stop, 130=interrupted)
 */

import { createOpencode } from "@opencode-ai/sdk";
import * as fs from "fs";
import * as path from "path";

// Exit codes matching agent_app.py
const EXIT_SUCCESS = 0;
const EXIT_FAILURE = 1;
const EXIT_GRACEFUL_STOP = 129;
const EXIT_INTERRUPTED = 130;

// Project directory (mounted in container)
const PROJECT_DIR = "/project";

// Graceful stop flag file
const GRACEFUL_STOP_FLAG = path.join(PROJECT_DIR, ".graceful_stop");

// Agent log file (shared with container entrypoint for docker logs visibility)
const AGENT_LOG_FILE = "/var/log/agent.log";

/**
 * Append message to agent log file for docker logs visibility
 */
function appendToLogFile(message: string): void {
  try {
    const timestamp = new Date().toISOString();
    fs.appendFileSync(AGENT_LOG_FILE, `[${timestamp}] ${message}\n`);
  } catch {
    // Ignore errors (file may not exist during local testing)
  }
}

/**
 * Read all input from stdin
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
 * Check if graceful stop was requested
 */
function checkGracefulStop(): boolean {
  try {
    return fs.existsSync(GRACEFUL_STOP_FLAG);
  } catch {
    return false;
  }
}

/**
 * Log with prefix for parsing
 * Outputs to both stdout (for Python backend streaming) and log file (for docker logs)
 */
function log(prefix: string, message: string): void {
  const formatted = `[${prefix}] ${message}`;
  console.log(formatted);
  appendToLogFile(formatted);
}

/**
 * Run the OpenCode agent with async prompts and event streaming
 */
async function runAgent(prompt: string, agentType: string): Promise<number> {
  log("AGENT", `Starting OpenCode agent: ${agentType}`);
  log("AGENT", `Prompt length: ${prompt.length} chars`);

  let opencode: { client: any; server: { url: string; close(): void } } | null = null;
  let eventStream: { cancel: () => void } | null = null;

  try {
    // Initialize OpenCode - this starts both the server and client
    // Use a random port to avoid conflicts with lingering servers
    const port = 5000 + Math.floor(Math.random() * 1000);
    log("AGENT", `Starting OpenCode server on port ${port}...`);
    opencode = await createOpencode({ port });
    log("AGENT", `OpenCode server started at ${opencode.server.url}`);

    const client = opencode.client;

    // Create a new session
    log("AGENT", "Creating session...");
    const sessionResult = await client.session.create();
    const sessionId = sessionResult?.data?.id || sessionResult?.id;
    if (!sessionId) {
      log("ERROR", "Failed to create session - no session ID returned");
      log("ERROR", `Session response: ${JSON.stringify(sessionResult)}`);
      return EXIT_FAILURE;
    }
    log("AGENT", `Session created: ${sessionId}`);

    // Track session completion
    let sessionComplete = false;
    let sessionError: string | null = null;

    // Subscribe to global events BEFORE sending prompt
    log("AGENT", "Subscribing to events...");
    const eventResult = await client.global.event({
      onSseEvent: (event: any) => {
        const payload = event?.data?.payload || event?.payload;
        if (!payload) return;

        const eventType = payload.type;
        const props = payload.properties;

        // Only process events for our session
        if (props?.sessionID && props.sessionID !== sessionId) return;

        switch (eventType) {
          case "message.part.updated":
            // Stream text updates
            if (props?.delta) {
              process.stdout.write(props.delta);
              appendToLogFile(props.delta);
            } else if (props?.part?.type === "text" && props?.part?.text) {
              console.log(props.part.text);
              appendToLogFile(props.part.text);
            } else if (props?.part?.type === "tool-invocation" || props?.part?.type === "tool_use") {
              const toolName = props.part?.name || props.part?.toolName || "unknown";
              log("TOOL", `Using: ${toolName}`);
            }
            break;

          case "session.idle":
            log("AGENT", "Session completed");
            sessionComplete = true;
            break;

          case "session.error":
            sessionError = props?.error || "Unknown session error";
            log("ERROR", `Session error: ${sessionError}`);
            sessionComplete = true;
            break;

          case "file.edited":
            log("FILE", `Edited: ${props?.file}`);
            break;

          case "todo.updated":
            log("TODO", `Updated: ${props?.todo?.content || "unknown"}`);
            break;
        }
      },
      onSseError: (error: any) => {
        log("ERROR", `SSE error: ${error?.message || String(error)}`);
      },
    });
    eventStream = eventResult;

    // Send the prompt asynchronously (returns immediately)
    log("AGENT", `Sending prompt to ${agentType} agent...`);
    await client.session.promptAsync({
      path: { id: sessionId },
      body: {
        parts: [{ type: "text", text: prompt }],
      },
    });
    log("AGENT", "Prompt sent, waiting for completion...");

    // Wait for session to complete (with timeout and graceful stop check)
    const maxWaitMs = 60 * 60 * 1000; // 60 minutes max
    const checkIntervalMs = 1000;
    let elapsedMs = 0;

    while (!sessionComplete && elapsedMs < maxWaitMs) {
      await new Promise(resolve => setTimeout(resolve, checkIntervalMs));
      elapsedMs += checkIntervalMs;

      // Check for graceful stop
      if (checkGracefulStop()) {
        log("AGENT", "Graceful stop requested, aborting session...");
        try {
          await client.session.abort({ path: { id: sessionId } });
        } catch {
          // Ignore abort errors
        }
        return EXIT_GRACEFUL_STOP;
      }
    }

    if (!sessionComplete) {
      log("ERROR", "Session timed out after 60 minutes");
      return EXIT_FAILURE;
    }

    if (sessionError) {
      log("ERROR", `Session failed: ${sessionError}`);
      return EXIT_FAILURE;
    }

    log("AGENT", "Completed successfully");
    return EXIT_SUCCESS;

  } catch (err: unknown) {
    const error = err as Error;

    if (err && typeof err === 'object' && 'status' in err) {
      const apiErr = err as { status?: number; message?: string };
      log("ERROR", `API Error (${apiErr.status}): ${apiErr.message || error.message}`);

      if (apiErr.status === 401) {
        log("ERROR", "Authentication failed - check ZHIPU_API_KEY");
      } else if (apiErr.status === 429) {
        log("ERROR", "Rate limited - retry after delay");
      }
    } else if (error.message?.includes("timeout") || error.message?.includes("ETIMEDOUT")) {
      log("ERROR", "Request timed out");
    } else if (error.message?.includes("ECONNREFUSED") || error.message?.includes("ENOTFOUND")) {
      log("ERROR", `Connection failed: ${error.message}`);
    } else {
      log("ERROR", `Unexpected error: ${error.message || String(err)}`);
    }

    return EXIT_FAILURE;
  } finally {
    // Clean up
    if (eventStream?.cancel) {
      try {
        eventStream.cancel();
      } catch {
        // Ignore cancel errors
      }
    }
    if (opencode?.server) {
      log("AGENT", "Closing OpenCode server...");
      opencode.server.close();
    }
  }
}

/**
 * Main entry point
 */
async function main(): Promise<void> {
  // Get agent type from environment
  const agentType = process.env.OPENCODE_AGENT_TYPE || "coder";
  log("CONFIG", `Agent type: ${agentType}`);

  // Read prompt from stdin
  const prompt = await readStdin();

  if (!prompt.trim()) {
    log("ERROR", "No prompt provided via stdin");
    process.exit(EXIT_FAILURE);
  }

  log("AGENT", `Received prompt (${prompt.length} chars)`);

  // Handle interrupt signal
  process.on("SIGINT", () => {
    log("AGENT", "Interrupted by user");
    process.exit(EXIT_INTERRUPTED);
  });

  process.on("SIGTERM", () => {
    log("AGENT", "Terminated");
    process.exit(EXIT_GRACEFUL_STOP);
  });

  // Run the agent
  const exitCode = await runAgent(prompt, agentType);
  process.exit(exitCode);
}

// Run main
main().catch((error) => {
  console.error("[FATAL]", error);
  process.exit(EXIT_FAILURE);
});
