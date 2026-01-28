/**
 * Spec Chat Session
 * =================
 *
 * Manages interactive spec creation conversation with Claude.
 * Uses the create-spec.md skill to guide users through app spec creation.
 */

import { query, type Options as SDKOptions, type PermissionMode } from '@anthropic-ai/claude-agent-sdk';
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { Mutex } from 'async-mutex';
import type { FileAttachment } from '@zerocoder/shared';

// =============================================================================
// Types
// =============================================================================

/** Message chunk types for streaming responses */
export interface MessageChunk {
  type: 'text' | 'question' | 'spec_complete' | 'file_written' | 'error' | 'response_done';
  content?: string;
  path?: string;
  questions?: unknown[];
  tool_id?: string;
}

/** Stored message in conversation history */
interface StoredMessage {
  role: 'user' | 'assistant';
  content: string;
  has_attachments?: boolean;
  timestamp: string;
}

// =============================================================================
// Session Registry
// =============================================================================

const sessions = new Map<string, SpecChatSession>();
const sessionsMutex = new Mutex();

// =============================================================================
// Spec Chat Session Class
// =============================================================================

export class SpecChatSession {
  readonly projectName: string;
  readonly projectDir: string;
  private messages: StoredMessage[] = [];
  private complete = false;

  constructor(projectName: string, projectDir: string) {
    this.projectName = projectName;
    this.projectDir = projectDir;
  }

  /**
   * Initialize session and get initial greeting from Claude.
   * Yields message chunks as they stream in.
   */
  async *start(): AsyncGenerator<MessageChunk, void, unknown> {
    // Load the create-spec skill
    const skillPath = join(process.cwd(), '.claude', 'commands', 'create-spec.md');

    if (!existsSync(skillPath)) {
      yield {
        type: 'error',
        content: `Spec creation skill not found at ${skillPath}`,
      };
      return;
    }

    let skillContent: string;
    try {
      skillContent = readFileSync(skillPath, 'utf-8');
    } catch (e) {
      yield {
        type: 'error',
        content: `Failed to read skill file: ${e}`,
      };
      return;
    }

    // Ensure project directory exists
    mkdirSync(this.projectDir, { recursive: true });

    // Delete app_spec.txt so Claude can create it fresh
    const promptsDir = join(this.projectDir, 'prompts');
    const appSpecPath = join(promptsDir, 'app_spec.txt');
    if (existsSync(appSpecPath)) {
      try {
        const { unlinkSync } = await import('node:fs');
        unlinkSync(appSpecPath);
        console.log('[SpecChat] Deleted scaffolded app_spec.txt for fresh spec creation');
      } catch {
        // Ignore unlink errors
      }
    }

    // Create security settings file
    const securitySettings = {
      sandbox: { enabled: false },
      permissions: {
        defaultMode: 'acceptEdits',
        allow: ['Read(./**)', 'Write(./**)', 'Edit(./**)', 'Glob(./**)'],
      },
    };
    const settingsFile = join(this.projectDir, '.claude_settings.json');
    writeFileSync(settingsFile, JSON.stringify(securitySettings, null, 2));

    // Replace $ARGUMENTS with absolute project path
    const projectPath = resolve(this.projectDir);
    const systemPrompt = skillContent.replace(/\$ARGUMENTS/g, projectPath);

    // Create Claude SDK options
    const options: SDKOptions = {
      model: 'claude-opus-4-5-20251101',
      cwd: projectPath,
      permissionMode: 'acceptEdits' as PermissionMode,
      allowDangerouslySkipPermissions: true,
      systemPrompt,
    };

    try {
      // Start the conversation
      const response = query({
        prompt: 'Begin the spec creation process.',
        options,
      });

      yield* this.processResponse(response);
      yield { type: 'response_done' };
    } catch (e) {
      const errorMessage = e instanceof Error ? e.message : String(e);
      console.error('[SpecChat] Failed to start spec chat:', e);
      yield {
        type: 'error',
        content: `Failed to start conversation: ${errorMessage}`,
      };
    }
  }

  /**
   * Send user message and stream Claude's response.
   */
  async *sendMessage(
    userMessage: string,
    attachments?: FileAttachment[]
  ): AsyncGenerator<MessageChunk, void, unknown> {
    // Store the user message
    this.messages.push({
      role: 'user',
      content: userMessage,
      has_attachments: Boolean(attachments && attachments.length > 0),
      timestamp: new Date().toISOString(),
    });

    try {
      // Build the prompt with attachments if present
      let prompt = userMessage;
      if (attachments && attachments.length > 0) {
        const parts: string[] = [userMessage];
        for (const att of attachments) {
          if ('textContent' in att) {
            parts.push(`[Attached file: ${att.filename}]\n\`\`\`\n${att.textContent}\n\`\`\``);
          } else {
            // For images, we need to use multimodal format
            // For now, just note that an image was attached
            parts.push(`[Image attached: ${att.filename}]`);
          }
        }
        prompt = parts.join('\n\n');
      }

      const options: SDKOptions = {
        model: 'claude-opus-4-5-20251101',
        cwd: resolve(this.projectDir),
        permissionMode: 'acceptEdits' as PermissionMode,
        allowDangerouslySkipPermissions: true,
      };

      const response = query({ prompt, options });
      yield* this.processResponse(response);
      yield { type: 'response_done' };
    } catch (e) {
      const errorMessage = e instanceof Error ? e.message : String(e);
      console.error('[SpecChat] Error during Claude query:', e);
      yield {
        type: 'error',
        content: `Error: ${errorMessage}`,
      };
    }
  }

  /**
   * Process the response stream from Claude SDK.
   */
  private async *processResponse(
    response: ReturnType<typeof query>
  ): AsyncGenerator<MessageChunk, void, unknown> {
    // Track pending writes for BOTH required files
    const pendingWrites: {
      app_spec: { tool_id: string; path: string } | null;
      initializer: { tool_id: string; path: string } | null;
    } = {
      app_spec: null,
      initializer: null,
    };

    // Track which files have been successfully written
    const filesWritten: {
      app_spec: boolean;
      initializer: boolean;
    } = {
      app_spec: false,
      initializer: false,
    };

    let specPath: string | null = null;

    for await (const message of response) {
      const msgType = message.type;

      if (msgType === 'assistant') {
        // Process content blocks in the assistant message
        const content = (message as { content?: unknown }).content;
        if (Array.isArray(content)) {
          for (const block of content) {
            if (typeof block === 'object' && block !== null) {
              const typedBlock = block as { type?: string; text?: string; name?: string; id?: string; input?: { file_path?: string } };

              if (typedBlock.type === 'text' && typedBlock.text) {
                // Text content
                yield { type: 'text', content: typedBlock.text };
                this.messages.push({
                  role: 'assistant',
                  content: typedBlock.text,
                  timestamp: new Date().toISOString(),
                });
              } else if (typedBlock.type === 'tool_use') {
                // Tool use - track file writes
                const toolName = typedBlock.name || '';
                const toolId = typedBlock.id || '';
                const filePath = typedBlock.input?.file_path || '';

                if ((toolName === 'Write' || toolName === 'Edit') && filePath) {
                  if (filePath.includes('app_spec.txt')) {
                    pendingWrites.app_spec = { tool_id: toolId, path: filePath };
                    console.log(`[SpecChat] ${toolName} tool called for app_spec.txt: ${filePath}`);
                  } else if (filePath.includes('initializer_prompt.md')) {
                    pendingWrites.initializer = { tool_id: toolId, path: filePath };
                    console.log(`[SpecChat] ${toolName} tool called for initializer_prompt.md: ${filePath}`);
                  }
                }
              }
            }
          }
        } else if (typeof content === 'string') {
          yield { type: 'text', content };
          this.messages.push({
            role: 'assistant',
            content,
            timestamp: new Date().toISOString(),
          });
        }
      } else if (msgType === 'result') {
        // Tool results - check for write confirmations
        const resultMsg = message as { result?: unknown; error?: unknown; tool_use_id?: string };
        const isError = resultMsg.error !== undefined;
        const toolUseId = resultMsg.tool_use_id || '';

        if (isError) {
          // Clear any pending writes that failed
          if (pendingWrites.app_spec && toolUseId === pendingWrites.app_spec.tool_id) {
            console.error('[SpecChat] app_spec write failed:', resultMsg.error);
            pendingWrites.app_spec = null;
          }
          if (pendingWrites.initializer && toolUseId === pendingWrites.initializer.tool_id) {
            console.error('[SpecChat] initializer write failed:', resultMsg.error);
            pendingWrites.initializer = null;
          }
        } else {
          // Tool succeeded - check which file was written
          if (pendingWrites.app_spec && toolUseId === pendingWrites.app_spec.tool_id) {
            const filePath = pendingWrites.app_spec.path;
            const fullPath = resolve(this.projectDir, filePath);
            if (existsSync(fullPath)) {
              console.log(`[SpecChat] app_spec.txt verified at: ${fullPath}`);
              filesWritten.app_spec = true;
              specPath = filePath;
              yield { type: 'file_written', path: filePath };
            } else {
              console.error(`[SpecChat] app_spec.txt not found after write: ${fullPath}`);
            }
            pendingWrites.app_spec = null;
          }

          if (pendingWrites.initializer && toolUseId === pendingWrites.initializer.tool_id) {
            const filePath = pendingWrites.initializer.path;
            const fullPath = resolve(this.projectDir, filePath);
            if (existsSync(fullPath)) {
              console.log(`[SpecChat] initializer_prompt.md verified at: ${fullPath}`);
              filesWritten.initializer = true;
              yield { type: 'file_written', path: filePath };
            } else {
              console.error(`[SpecChat] initializer_prompt.md not found after write: ${fullPath}`);
            }
            pendingWrites.initializer = null;
          }

          // Check if BOTH files are now written - only then signal completion
          if (filesWritten.app_spec && filesWritten.initializer) {
            console.log('[SpecChat] Both app_spec.txt and initializer_prompt.md verified - signaling completion');
            this.complete = true;
            yield { type: 'spec_complete', path: specPath || '' };
          }
        }
      } else if (msgType === 'system') {
        // Handle system messages if needed
        const sysMsg = message as { subtype?: string; content?: unknown };
        if (sysMsg.subtype === 'error' || sysMsg.subtype === 'completion') {
          // Handle completion or error
          console.log('[SpecChat] System message:', sysMsg.subtype, sysMsg.content);
        }
      }
    }
  }

  /**
   * Check if spec creation is complete.
   */
  isComplete(): boolean {
    return this.complete;
  }

  /**
   * Get all messages in the conversation.
   */
  getMessages(): StoredMessage[] {
    return [...this.messages];
  }

  /**
   * Clean up resources.
   */
  async close(): Promise<void> {
    // No explicit cleanup needed for SDK query-based approach
  }
}

// =============================================================================
// Session Management Functions
// =============================================================================

/**
 * Get an existing session for a project.
 */
export function getSession(projectName: string): SpecChatSession | undefined {
  return sessions.get(projectName);
}

/**
 * Create a new session for a project, closing any existing one.
 */
export async function createSession(
  projectName: string,
  projectDir: string
): Promise<SpecChatSession> {
  return sessionsMutex.runExclusive(async () => {
    // Get existing session to close later
    const oldSession = sessions.get(projectName);

    // Create new session
    const session = new SpecChatSession(projectName, projectDir);
    sessions.set(projectName, session);

    // Close old session outside the lock
    if (oldSession) {
      try {
        await oldSession.close();
      } catch (e) {
        console.warn(`[SpecChat] Error closing old session for ${projectName}:`, e);
      }
    }

    return session;
  });
}

/**
 * Remove and close a session.
 */
export async function removeSession(projectName: string): Promise<void> {
  return sessionsMutex.runExclusive(async () => {
    const session = sessions.get(projectName);
    sessions.delete(projectName);

    if (session) {
      try {
        await session.close();
      } catch (e) {
        console.warn(`[SpecChat] Error closing session for ${projectName}:`, e);
      }
    }
  });
}

/**
 * List all active session project names.
 */
export function listSessions(): string[] {
  return Array.from(sessions.keys());
}

/**
 * Close all active sessions. Called on server shutdown.
 */
export async function cleanupAllSessions(): Promise<void> {
  const sessionsToClose = await sessionsMutex.runExclusive(() => {
    const list = Array.from(sessions.values());
    sessions.clear();
    return list;
  });

  for (const session of sessionsToClose) {
    try {
      await session.close();
    } catch (e) {
      console.warn(`[SpecChat] Error closing session ${session.projectName}:`, e);
    }
  }
}
