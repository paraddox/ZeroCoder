/**
 * Assistant Chat Session
 * ======================
 *
 * Manages conversational assistant sessions for projects.
 * The assistant can:
 * - Answer questions about the codebase and features (read-only)
 * - Manage issues/features via the issue-manager MCP server
 *
 * TypeScript port of server/services/assistant_chat_session.py
 */

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import {
  addMessage,
  createConversation,
} from './assistant-database.js';

// getSystemPrompt and getAppSpecContext are defined for future use with Claude SDK
// They are currently unused but kept for when the Claude SDK integration is added

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function getAppSpecContext(projectDir: string): string {
  const appSpecPath = join(projectDir, 'prompts', 'app_spec.txt');
  if (!existsSync(appSpecPath)) {
    return '';
  }

  try {
    const content = readFileSync(appSpecPath, 'utf-8');
    if (content.length > 5000) {
      return content.slice(0, 5000) + '\n... (truncated)';
    }
    return `## Project Specification\n\n${content}`;
  } catch (e) {
    console.warn(`[AssistantChatSession] Failed to read app_spec.txt:`, e);
    return '';
  }
}

// Unused for now - will be used when Claude SDK is integrated
// @ts-expect-error - intentionally unused
function _unusedGetSystemPrompt(projectName: string, projectDir: string): string {
  // Try to load from template first
  const templatePath = join(process.cwd(), '.claude', 'templates', 'assistant_prompt.template.md');

  if (existsSync(templatePath)) {
    try {
      let prompt = readFileSync(templatePath, 'utf-8');
      prompt = prompt.replace(/\$PROJECT_NAME/g, projectName);
      prompt = prompt.replace(/\$APP_SPEC_CONTEXT/g, getAppSpecContext(projectDir));
      return prompt;
    } catch (e) {
      console.warn(`[AssistantChatSession] Failed to load assistant prompt template:`, e);
    }
  }

  // Fallback to inline prompt
  const appSpecContext = getAppSpecContext(projectDir);

  return `# Project Assistant for "${projectName}"

You are a helpful project assistant with two capabilities:

## 1. Codebase Exploration (Read-Only)
- Read and analyze source code files
- Search for patterns and implementations
- Look up documentation online

## 2. Feature/Issue Creation
- Create issues in the project's beads tracker using the \`create_issue\` tool
- Ask clarifying questions to refine requirements
- Always confirm before creating an issue

## IMPORTANT RULES
1. You CANNOT modify code - No writing, editing, or deleting source files
2. You CAN create issues - Use the \`create_issue\` tool
3. Always confirm before creating - Show the user what you'll create first

${appSpecContext}

## Guidelines
1. Be concise and helpful
2. Reference specific file paths and line numbers
3. Search the codebase before answering
4. If unsure, say so rather than guessing`;
}

/**
 * Message chunk types for streaming responses
 */
export type MessageChunk =
  | { type: 'conversation_created'; conversation_id: number }
  | { type: 'text'; content: string }
  | { type: 'tool_call'; tool: string; input: Record<string, unknown> }
  | { type: 'issue_created'; id: string; title: string }
  | { type: 'response_done' }
  | { type: 'error'; content: string };

/**
 * Manages a read-only assistant conversation for a project.
 *
 * Uses Claude Opus 4.5 with only read-only tools enabled.
 * Persists conversation history to SQLite.
 */
export class AssistantChatSession {
  projectName: string;
  projectDir: string;
  conversationId: number | null;
  client: unknown | null;
  createdAt: Date;

  constructor(projectName: string, projectDir: string, conversationId: number | null = null) {
    this.projectName = projectName;
    this.projectDir = projectDir;
    this.conversationId = conversationId;
    this.client = null;
    this.createdAt = new Date();
  }

  /**
   * Get the current conversation ID.
   */
  getConversationId(): number | null {
    return this.conversationId;
  }

  /**
   * Clean up resources and close the Claude client.
   */
  async close(): Promise<void> {
    // Note: SDK client cleanup would go here
    // For now, we just null out the reference
    this.client = null;

    // Sync beads issues to git after session ends
    try {
      const { execSync } = await import('node:child_process');

      // Export DB to JSONL
      execSync('bd --no-daemon sync', {
        cwd: this.projectDir,
        stdio: 'pipe',
        timeout: 30000,
      });

      // Check if issues.jsonl has changes
      try {
        execSync('git diff --quiet .beads/issues.jsonl', {
          cwd: this.projectDir,
          stdio: 'pipe',
          timeout: 10000,
        });
        // If we get here, no changes
        console.log(`[AssistantChatSession] No beads changes to sync for ${this.projectName}`);
      } catch {
        // Has changes - commit and push
        execSync('git add .beads/issues.jsonl', {
          cwd: this.projectDir,
          stdio: 'pipe',
          timeout: 30000,
        });
        execSync('git commit -m "chore: sync beads issues from assistant"', {
          cwd: this.projectDir,
          stdio: 'pipe',
          timeout: 30000,
        });
        execSync('git push', {
          cwd: this.projectDir,
          stdio: 'pipe',
          timeout: 30000,
        });
        console.log(`[AssistantChatSession] Beads issues synced and pushed for ${this.projectName}`);
      }
    } catch (e) {
      console.warn(`[AssistantChatSession] Beads sync error for ${this.projectName}:`, e);
    }
  }

  /**
   * Initialize session with the Claude client.
   *
   * Creates a new conversation if none exists, then sends an initial greeting.
   * Yields message chunks as they stream in.
   */
  async *start(): AsyncGenerator<MessageChunk> {
    // Create a new conversation if we don't have one
    if (this.conversationId === null) {
      const conv = createConversation(this.projectDir, this.projectName);
      this.conversationId = conv.id;
      yield { type: 'conversation_created', conversation_id: conv.id };
    }

    // Pull latest changes before starting assistant
    try {
      const { execSync } = await import('node:child_process');
      execSync('git pull --ff-only', {
        cwd: this.projectDir,
        stdio: 'pipe',
        timeout: 30000,
      });
      console.log(`[AssistantChatSession] Git pull succeeded for ${this.projectName}`);
    } catch (e) {
      console.warn(`[AssistantChatSession] Git pull error for ${this.projectName}:`, e);
    }

    // For now, we simulate the client initialization
    // In a full implementation, this would use the claude-agent-sdk
    console.log(`[AssistantChatSession] Initializing Claude client for ${this.projectName}`);

    // Send initial greeting
    try {
      const greeting = `Hello! I'm your project assistant for **${this.projectName}**. I can help you:\n\n- Explore and understand the codebase\n- Answer questions about the project\n- Create new features/issues\n\nWhat would you like to do?`;

      // Store the greeting in the database
      if (this.conversationId) {
        addMessage(this.projectDir, this.conversationId, 'assistant', greeting);
      }

      yield { type: 'text', content: greeting };
      yield { type: 'response_done' };
    } catch (e) {
      console.error(`[AssistantChatSession] Failed to send greeting:`, e);
      yield { type: 'error', content: `Failed to start conversation: ${e instanceof Error ? e.message : String(e)}` };
    }
  }

  /**
   * Send user message and stream Claude's response.
   */
  async *sendMessage(userMessage: string): AsyncGenerator<MessageChunk> {
    if (!this.client) {
      yield { type: 'error', content: 'Session not initialized. Call start() first.' };
      return;
    }

    if (this.conversationId === null) {
      yield { type: 'error', content: 'No conversation ID set.' };
      return;
    }

    // Store user message in database
    addMessage(this.projectDir, this.conversationId, 'user', userMessage);

    try {
      // For now, we simulate the response
      // In a full implementation, this would query Claude via the SDK
      const response = `I received your message: "${userMessage}"\n\nNote: This is a placeholder response. The full implementation would use the claude-agent-sdk to query Claude.`;

      yield { type: 'text', content: response };

      // Store the complete response in the database
      if (this.conversationId) {
        addMessage(this.projectDir, this.conversationId, 'assistant', response);
      }

      yield { type: 'response_done' };
    } catch (e) {
      console.error(`[AssistantChatSession] Error during message processing:`, e);
      yield { type: 'error', content: `Error: ${e instanceof Error ? e.message : String(e)}` };
    }
  }
}

// Session registry with mutex safety
const _sessions: Map<string, AssistantChatSession> = new Map();
let _sessionsLock = false;

async function acquireLock(): Promise<void> {
  while (_sessionsLock) {
    await new Promise(resolve => setTimeout(resolve, 10));
  }
  _sessionsLock = true;
}

function releaseLock(): void {
  _sessionsLock = false;
}

/**
 * Get an existing session for a project.
 */
export function getSession(projectName: string): AssistantChatSession | null {
  return _sessions.get(projectName) ?? null;
}

/**
 * Create a new session for a project, closing any existing one.
 */
export async function createSession(
  projectName: string,
  projectDir: string,
  conversationId: number | null = null
): Promise<AssistantChatSession> {
  await acquireLock();
  let oldSession: AssistantChatSession | null = null;

  try {
    oldSession = _sessions.get(projectName) ?? null;
    const session = new AssistantChatSession(projectName, projectDir, conversationId);
    _sessions.set(projectName, session);

    if (oldSession) {
      try {
        await oldSession.close();
      } catch (e) {
        console.warn(`[AssistantChatSession] Error closing old session for ${projectName}:`, e);
      }
    }

    return session;
  } finally {
    releaseLock();
  }
}

/**
 * Remove and close a session.
 */
export async function removeSession(projectName: string): Promise<void> {
  await acquireLock();
  const session = _sessions.get(projectName);
  _sessions.delete(projectName);
  releaseLock();

  if (session) {
    try {
      await session.close();
    } catch (e) {
      console.warn(`[AssistantChatSession] Error closing session for ${projectName}:`, e);
    }
  }
}

/**
 * List all active session project names.
 */
export function listSessions(): string[] {
  return Array.from(_sessions.keys());
}

/**
 * Close all active sessions. Called on server shutdown.
 */
export async function cleanupAllSessions(): Promise<void> {
  await acquireLock();
  const sessionsToClose = Array.from(_sessions.values());
  _sessions.clear();
  releaseLock();

  for (const session of sessionsToClose) {
    try {
      await session.close();
    } catch (e) {
      console.warn(`[AssistantChatSession] Error closing session ${session.projectName}:`, e);
    }
  }
}
