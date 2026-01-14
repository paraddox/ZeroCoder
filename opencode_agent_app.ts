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
 * Structured trace logging for frontend consumption
 * Outputs JSON traces with [TRACE] prefix for parsing
 */
function logTrace(
  event: "tool.start" | "tool.end" | "thinking" | "text" | "file.edit" | "error",
  data: Record<string, unknown>
): void {
  const trace = {
    type: "trace",
    event,
    timestamp: new Date().toISOString(),
    data,
  };
  const formatted = `[TRACE] ${JSON.stringify(trace)}`;
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

    // Subscribe to events using SDK's global event stream
    log("AGENT", "Subscribing to events...");
    let stream: any = null;

    try {
      const eventResult = await client.global.event();
      stream = eventResult?.stream;
    } catch (e: any) {
      log("ERROR", `Failed to subscribe to events: ${e.message}`);
    }

    eventStream = stream ? { cancel: () => stream.controller?.abort() } : null;

    // Process events in background (only if we have a stream)
    const eventProcessor = stream ? (async () => {
      try {
        for await (const event of stream) {
          // Extract payload (events are wrapped)
          const payload = event?.payload || event;
          const eventType = payload?.type;
          const props = payload?.properties || payload;

          // Only process events for our session
          const partSessionId = props?.part?.sessionID || props?.sessionID;
          if (partSessionId && partSessionId !== sessionId) continue;

          switch (eventType) {
            case "message.part.updated":
            case "message.updated":
              const part = props?.part;

              // Handle reasoning/thinking content (GLM-4.7)
              // Only log complete thinking blocks, not every delta (too noisy)
              if (part?.type === "reasoning" || part?.type === "thinking") {
                // Skip deltas - too noisy for logs
                // Only log if we have substantial complete content (over 100 chars)
                if (!props?.delta && part?.text && part.text.length > 100) {
                  // Extract first line as summary
                  const firstLine = part.text.split('\n')[0].slice(0, 150);
                  log("THINKING", firstLine);
                }
              }
              // Handle text content - only log complete text, not every token delta
              else if (part?.type === "text") {
                // Skip deltas - too noisy
                // Only log complete text blocks
                if (!props?.delta && part?.text && part.text.length > 20) {
                  const firstLine = part.text.split('\n')[0].slice(0, 200);
                  log("TEXT", firstLine);
                }
              }
              // Handle tool invocations
              else if (part?.type === "tool-invocation" || part?.type === "tool_use" || part?.type === "tool-call") {
                const toolName = part?.name || part?.toolName || "unknown";
                const toolArgs = part?.args || part?.input || part?.arguments || {};
                log("TOOL", `Using: ${toolName}`);
                logTrace("tool.start", {
                  toolName,
                  toolArgs,
                  toolId: part?.id,
                });
              }
              // Handle tool results
              else if (part?.type === "tool-result" || part?.type === "tool_result") {
                const toolName = part?.name || part?.toolName || "unknown";
                const result = part?.result || part?.output;
                logTrace("tool.end", {
                  toolName,
                  toolId: part?.id,
                  result: typeof result === "string" ? result.slice(0, 500) : result,
                });
              }
              break;

            case "session.idle":
              log("AGENT", "Session completed");
              sessionComplete = true;
              break;

            case "session.error":
              sessionError = props?.error || "Unknown session error";
              log("ERROR", `Session error: ${sessionError}`);
              logTrace("error", { message: sessionError });
              sessionComplete = true;
              break;

            case "file.edited":
              log("FILE", `Edited: ${props?.file}`);
              logTrace("file.edit", {
                file: props?.file,
                additions: props?.additions,
                deletions: props?.deletions,
              });
              break;

            case "todo.updated":
              log("TODO", `Updated: ${props?.todo?.content || "unknown"}`);
              break;

            case "tool.result":
            case "tool_result":
              logTrace("tool.end", {
                toolName: props?.name || props?.toolName || "unknown",
                toolId: props?.id || props?.toolCallId,
                result: typeof props?.result === "string" ? props.result.slice(0, 500) : props?.result,
              });
              break;
          }

          // Exit loop if session is complete
          if (sessionComplete) break;
        }
      } catch (err: any) {
        // Stream was cancelled or errored
        if (!sessionComplete) {
          log("ERROR", `Event stream error: ${err?.message || String(err)}`);
        }
      }
    })() : null;

    // Don't await eventProcessor - let it run in background

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
