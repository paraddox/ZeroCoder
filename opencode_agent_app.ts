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
 */
function log(prefix: string, message: string): void {
  console.log(`[${prefix}] ${message}`);
}

/**
 * Run the OpenCode agent
 */
async function runAgent(prompt: string, agentType: string): Promise<number> {
  log("AGENT", `Starting OpenCode agent: ${agentType}`);
  log("AGENT", `Prompt length: ${prompt.length} chars`);

  let opencode: { client: any; server: { url: string; close(): void } } | null = null;

  try {
    // Initialize OpenCode - this starts both the server and client
    log("AGENT", "Starting OpenCode server...");
    opencode = await createOpencode();
    log("AGENT", `OpenCode server started at ${opencode.server.url}`);

    const client = opencode.client;

    // Create a new session
    log("AGENT", "Creating session...");
    const sessionResult = await client.session.create();
    const sessionId = sessionResult.data?.id;
    if (!sessionId) {
      log("ERROR", "Failed to create session - no session ID returned");
      return EXIT_FAILURE;
    }
    log("AGENT", `Session created: ${sessionId}`);

    // Send the prompt to the agent using session.prompt()
    log("AGENT", `Sending prompt to ${agentType} agent...`);
    const response = await client.session.prompt({
      path: { id: sessionId },
      body: {
        parts: [{ type: "text", text: prompt }],
      },
    });

    // Process response parts
    if (response.data?.parts) {
      for (const part of response.data.parts) {
        if (part.type === "text") {
          // Output text content
          console.log(part.text);
        } else if (part.type === "tool-invocation" || part.type === "tool_use") {
          log("TOOL", `Using: ${(part as any).name || (part as any).toolName || "unknown"}`);
        }
      }
    } else if (response.error) {
      log("ERROR", `API returned error: ${JSON.stringify(response.error)}`);
      return EXIT_FAILURE;
    }

    // Check for graceful stop after processing
    if (checkGracefulStop()) {
      log("AGENT", "Graceful stop requested, completing session...");
      return EXIT_GRACEFUL_STOP;
    }

    log("AGENT", "Completed successfully");
    return EXIT_SUCCESS;

  } catch (err: unknown) {
    const error = err as Error;

    // Check if it's an API error from the SDK
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
    // Clean up - close the server
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
