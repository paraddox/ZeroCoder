/**
 * Agent Executor
 * ==============
 *
 * TypeScript implementation for executing Claude agents using @anthropic-ai/claude-agent-sdk.
 * Handles agent spawning, prompt injection, and environment configuration.
 *
 * This service can be used for:
 * - Direct host-side agent execution (without containers)
 * - Inside containers as a TypeScript-based agent app
 * - Testing and development of agent workflows
 */

import { query, type Options as SDKOptions, type PermissionMode } from '@anthropic-ai/claude-agent-sdk';
import { EventEmitter } from 'node:events';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

// =============================================================================
// Types
// =============================================================================

/** Agent role determines the role and behavior */
export type AgentRole = 'coder' | 'reviewer' | 'overseer' | 'initializer';

/** Model selection */
export type ModelType = 'opus' | 'sonnet' | 'haiku';

/** Agent execution status */
export type ExecutionStatus = 'pending' | 'running' | 'completed' | 'failed' | 'stopped';

/** Exit codes for agent execution */
export const EXIT_CODES = {
  SUCCESS: 0,
  FAILURE: 1,
  GRACEFUL_STOP: 129,
  INTERRUPTED: 130,
  CONTEXT_LIMIT: 131,
} as const;

/** Message types from Claude Agent SDK */
export type MessageType =
  | 'assistant'
  | 'tool_call'
  | 'tool_result'
  | 'error'
  | 'system';

/** Agent configuration */
export interface AgentConfig {
  /** Role of agent (coder, reviewer, overseer, initializer) */
  agentRole: AgentRole;

  /** Model to use (opus, sonnet, haiku) */
  model?: ModelType;

  /** Full model ID override */
  modelId?: string;

  /** Working directory for the agent */
  workingDirectory: string;

  /** Custom system prompt to prepend */
  systemPrompt?: string;

  /** Permission mode: 'default' requires approval, 'bypassPermissions' auto-approves */
  permissionMode?: 'default' | 'bypassPermissions';

  /** Project name for identification */
  projectName?: string;

  /** Container number (if running in container) */
  containerNumber?: number;

  /** Host API URL for callbacks */
  hostApiUrl?: string;

  /** Heartbeat interval in milliseconds (default: 30000) */
  heartbeatInterval?: number;
}

/** Execution result */
export interface ExecutionResult {
  /** Exit code */
  exitCode: number;

  /** Whether execution was successful */
  success: boolean;

  /** Human-readable message */
  message: string;

  /** Total tokens used */
  tokensUsed?: number;

  /** Duration in milliseconds */
  durationMs?: number;
}

/** Output callback type */
export type OutputCallback = (line: string) => void | Promise<void>;

/** Status callback type */
export type StatusCallback = (status: ExecutionStatus) => void | Promise<void>;

/** Message callback for detailed message handling */
export type MessageCallback = (type: MessageType, content: unknown) => void | Promise<void>;

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Get the full model ID from a model type.
 */
function getModelId(model: ModelType | undefined, agentRole: AgentRole): string {
  // Use Opus 4.5 for initializer, Sonnet for others by default
  const defaultModel = agentRole === 'initializer' ? 'opus' : 'sonnet';
  const selectedModel = model || defaultModel;

  const modelMap: Record<ModelType, string> = {
    opus: 'claude-opus-4-5-20251101',
    sonnet: 'claude-sonnet-4-5-20250514',
    haiku: 'claude-haiku-4-5-20250514',
  };

  return modelMap[selectedModel];
}

/**
 * Read agent config from project directory.
 */
function readProjectConfig(workingDirectory: string): Record<string, unknown> {
  const configPath = join(workingDirectory, 'prompts', '.agent_config.json');
  if (existsSync(configPath)) {
    try {
      return JSON.parse(readFileSync(configPath, 'utf-8'));
    } catch {
      // Ignore parse errors
    }
  }
  return {};
}

/**
 * Sanitize output to remove sensitive information.
 */
const SENSITIVE_PATTERNS = [
  /sk-ant[a-zA-Z0-9_-]*/gi,
  /sk-[a-zA-Z0-9]{20,}/gi,
  /ANTHROPIC_API_KEY=[^\s]+/gi,
  /api[_-]?key[=:][^\s]+/gi,
  /token[=:][^\s]+/gi,
  /password[=:][^\s]+/gi,
  /secret[=:][^\s]+/gi,
];

function sanitizeOutput(line: string): string {
  let result = line;
  for (const pattern of SENSITIVE_PATTERNS) {
    result = result.replace(pattern, '[REDACTED]');
  }
  return result;
}

// =============================================================================
// AgentExecutor Class
// =============================================================================

/**
 * Executes Claude agents using the TypeScript Agent SDK.
 *
 * @example
 * ```typescript
 * const executor = new AgentExecutor({
 *   agentRole: 'coder',
 *   workingDirectory: '/path/to/project',
 *   projectName: 'my-project',
 * });
 *
 * executor.on('output', (line) => console.log(line));
 *
 * const result = await executor.execute('Implement the login feature');
 * ```
 */
export class AgentExecutor extends EventEmitter {
  private readonly config: Required<
    Pick<AgentConfig, 'agentRole' | 'workingDirectory' | 'permissionMode' | 'heartbeatInterval'>
  > & AgentConfig;

  private _status: ExecutionStatus = 'pending';
  private _abortController: AbortController | null = null;
  private _heartbeatTimer: NodeJS.Timeout | null = null;
  private _gracefulStopRequested = false;
  private _startTime: number = 0;
  private _messageCount = 0;

  // Callbacks
  private _outputCallbacks: OutputCallback[] = [];
  private _statusCallbacks: StatusCallback[] = [];
  private _messageCallbacks: MessageCallback[] = [];

  constructor(config: AgentConfig) {
    super();

    this.config = {
      ...config,
      permissionMode: config.permissionMode || 'bypassPermissions',
      heartbeatInterval: config.heartbeatInterval || 30000,
    };
  }

  // ===========================================================================
  // Public Properties
  // ===========================================================================

  get status(): ExecutionStatus {
    return this._status;
  }

  get isRunning(): boolean {
    return this._status === 'running';
  }

  get gracefulStopRequested(): boolean {
    return this._gracefulStopRequested;
  }

  // ===========================================================================
  // Callback Management
  // ===========================================================================

  addOutputCallback(callback: OutputCallback): void {
    this._outputCallbacks.push(callback);
  }

  removeOutputCallback(callback: OutputCallback): void {
    const index = this._outputCallbacks.indexOf(callback);
    if (index !== -1) {
      this._outputCallbacks.splice(index, 1);
    }
  }

  addStatusCallback(callback: StatusCallback): void {
    this._statusCallbacks.push(callback);
  }

  removeStatusCallback(callback: StatusCallback): void {
    const index = this._statusCallbacks.indexOf(callback);
    if (index !== -1) {
      this._statusCallbacks.splice(index, 1);
    }
  }

  addMessageCallback(callback: MessageCallback): void {
    this._messageCallbacks.push(callback);
  }

  removeMessageCallback(callback: MessageCallback): void {
    const index = this._messageCallbacks.indexOf(callback);
    if (index !== -1) {
      this._messageCallbacks.splice(index, 1);
    }
  }

  private async _broadcastOutput(line: string): Promise<void> {
    const sanitized = sanitizeOutput(line);
    this.emit('output', sanitized);
    for (const callback of this._outputCallbacks) {
      try {
        await callback(sanitized);
      } catch (e) {
        console.error('Output callback error:', e);
      }
    }
  }

  private async _broadcastStatus(status: ExecutionStatus): Promise<void> {
    this._status = status;
    this.emit('status', status);
    for (const callback of this._statusCallbacks) {
      try {
        await callback(status);
      } catch (e) {
        console.error('Status callback error:', e);
      }
    }
  }

  private async _broadcastMessage(type: MessageType, content: unknown): Promise<void> {
    this.emit('message', { type, content });
    for (const callback of this._messageCallbacks) {
      try {
        await callback(type, content);
      } catch (e) {
        console.error('Message callback error:', e);
      }
    }
  }

  // ===========================================================================
  // Execution Control
  // ===========================================================================

  /**
   * Execute the agent with the given prompt.
   */
  async execute(prompt: string): Promise<ExecutionResult> {
    if (this._status === 'running') {
      return {
        exitCode: EXIT_CODES.FAILURE,
        success: false,
        message: 'Agent is already running',
      };
    }

    this._startTime = Date.now();
    this._messageCount = 0;
    this._gracefulStopRequested = false;
    this._abortController = new AbortController();

    await this._broadcastStatus('running');
    await this._broadcastOutput(`[Agent] Starting ${this.config.agentRole} agent...`);

    // Start heartbeat if configured
    this._startHeartbeat();

    try {
      const result = await this._runAgent(prompt);
      return result;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      await this._broadcastOutput(`[Agent] Error: ${errorMessage}`);
      await this._broadcastStatus('failed');

      return {
        exitCode: EXIT_CODES.FAILURE,
        success: false,
        message: `Agent execution failed: ${errorMessage}`,
        durationMs: Date.now() - this._startTime,
      };
    } finally {
      this._stopHeartbeat();
      this._abortController = null;
    }
  }

  /**
   * Request graceful stop of the agent.
   */
  requestGracefulStop(): void {
    if (!this.isRunning) return;

    this._gracefulStopRequested = true;
    this._broadcastOutput('[Agent] Graceful stop requested, completing current task...');
  }

  /**
   * Force stop the agent immediately.
   */
  forceStop(): void {
    if (!this.isRunning) return;

    this._abortController?.abort();
    this._gracefulStopRequested = true;
    this._broadcastOutput('[Agent] Force stop triggered');
  }

  // ===========================================================================
  // Private Methods
  // ===========================================================================

  private async _runAgent(prompt: string): Promise<ExecutionResult> {
    // Read project config
    const projectConfig = readProjectConfig(this.config.workingDirectory);

    // Determine model
    const modelId = this.config.modelId ||
      (projectConfig.agent_model as string) ||
      getModelId(this.config.model, this.config.agentRole);

    await this._broadcastOutput(`[Agent] Model: ${modelId}`);
    await this._broadcastOutput(`[Agent] Working directory: ${this.config.workingDirectory}`);

    // Build agent options
    const options: SDKOptions = {
      model: modelId,
      cwd: this.config.workingDirectory,
      permissionMode: this.config.permissionMode as PermissionMode,
      allowDangerouslySkipPermissions: this.config.permissionMode === 'bypassPermissions',
    };

    try {
      const response = query({
        prompt,
        options,
      });

      // Process messages
      for await (const message of response) {
        // Check for abort
        if (this._abortController?.signal.aborted) {
          await this._broadcastOutput('[Agent] Execution aborted');
          return {
            exitCode: EXIT_CODES.INTERRUPTED,
            success: false,
            message: 'Agent execution was interrupted',
            durationMs: Date.now() - this._startTime,
          };
        }

        // Check for graceful stop
        if (this._gracefulStopRequested) {
          await this._broadcastOutput('[Agent] Graceful stop - completing current action...');
          // Don't break immediately - let the current action complete
        }

        this._messageCount++;
        await this._processMessage(message);

        // Check graceful stop after processing
        if (this._gracefulStopRequested && this._messageCount % 10 === 0) {
          // Check with host API if we should continue
          const shouldContinue = await this._checkShouldContinue();
          if (!shouldContinue) {
            await this._broadcastOutput('[Agent] Graceful stop completed');
            return {
              exitCode: EXIT_CODES.GRACEFUL_STOP,
              success: true,
              message: 'Agent stopped gracefully',
              durationMs: Date.now() - this._startTime,
            };
          }
        }
      }

      await this._broadcastOutput('[Agent] Execution completed successfully');
      await this._broadcastStatus('completed');

      return {
        exitCode: EXIT_CODES.SUCCESS,
        success: true,
        message: 'Agent execution completed',
        durationMs: Date.now() - this._startTime,
      };
    } catch (error) {
      // Handle specific error types
      const errorMessage = error instanceof Error ? error.message : String(error);

      if (errorMessage.includes('context_length_exceeded') ||
          errorMessage.includes('max_tokens')) {
        await this._broadcastOutput('[Agent] Context limit reached');
        await this._broadcastStatus('completed');

        return {
          exitCode: EXIT_CODES.CONTEXT_LIMIT,
          success: true,
          message: 'Context limit reached - requires fresh session',
          durationMs: Date.now() - this._startTime,
        };
      }

      throw error;
    }
  }

  private async _processMessage(message: {
    type: string;
    content?: unknown;
    subtype?: string;
    tool_name?: string;
    input?: unknown;
    result?: unknown;
    error?: unknown;
    session_id?: string;
    agent_name?: string;
  }): Promise<void> {
    switch (message.type) {
      case 'assistant':
        await this._handleAssistantMessage(message.content);
        break;

      case 'tool_call':
        await this._broadcastOutput(`[Tool] ${message.tool_name || 'unknown'}`);
        await this._broadcastMessage('tool_call', {
          tool: message.tool_name,
          input: message.input,
        });
        break;

      case 'tool_result':
        await this._broadcastMessage('tool_result', {
          tool: message.tool_name,
          result: message.result,
        });
        break;

      case 'error':
        await this._broadcastOutput(`[Error] ${JSON.stringify(message.error)}`);
        await this._broadcastMessage('error', message.error);
        break;

      case 'system':
        await this._handleSystemMessage(message);
        break;

      default:
        // Log other message types for debugging
        console.debug('Unknown message type:', message.type);
    }
  }

  private async _handleAssistantMessage(content: unknown): Promise<void> {
    if (typeof content === 'string') {
      // Simple text content
      const lines = content.split('\n');
      for (const line of lines) {
        if (line.trim()) {
          await this._broadcastOutput(line);
        }
      }
    } else if (Array.isArray(content)) {
      // Block content (TextBlock, ToolUseBlock, etc.)
      for (const block of content) {
        if (typeof block === 'object' && block !== null) {
          const typedBlock = block as { type?: string; text?: string; name?: string };
          if (typedBlock.type === 'text' && typedBlock.text) {
            const lines = typedBlock.text.split('\n');
            for (const line of lines) {
              if (line.trim()) {
                await this._broadcastOutput(line);
              }
            }
          } else if (typedBlock.type === 'tool_use') {
            await this._broadcastOutput(`[Tool] Using: ${typedBlock.name || 'unknown'}`);
          }
        }
      }
    }

    await this._broadcastMessage('assistant', content);
  }

  private async _handleSystemMessage(message: {
    subtype?: string;
    session_id?: string;
    agent_name?: string;
  }): Promise<void> {
    const { subtype, session_id, agent_name } = message;

    switch (subtype) {
      case 'init':
        await this._broadcastOutput(`[System] Session initialized: ${session_id || 'unknown'}`);
        break;
      case 'completion':
        await this._broadcastOutput('[System] Task completed');
        break;
      case 'subagent_start':
        await this._broadcastOutput(`[System] Subagent started: ${agent_name || 'unknown'}`);
        break;
      case 'subagent_end':
        await this._broadcastOutput(`[System] Subagent completed: ${agent_name || 'unknown'}`);
        break;
      default:
        console.debug('Unknown system subtype:', subtype);
    }

    await this._broadcastMessage('system', message);
  }

  private _startHeartbeat(): void {
    if (!this.config.hostApiUrl || !this.config.projectName) return;

    this._heartbeatTimer = setInterval(async () => {
      try {
        await this._sendHeartbeat();
      } catch (e) {
        console.debug('Heartbeat failed:', e);
      }
    }, this.config.heartbeatInterval);
  }

  private _stopHeartbeat(): void {
    if (this._heartbeatTimer) {
      clearInterval(this._heartbeatTimer);
      this._heartbeatTimer = null;
    }
  }

  private async _sendHeartbeat(): Promise<{ graceful_stop_requested: boolean }> {
    if (!this.config.hostApiUrl || !this.config.projectName) {
      return { graceful_stop_requested: false };
    }

    const containerNumber = this.config.containerNumber ?? 1;
    const url = `${this.config.hostApiUrl}/api/projects/${this.config.projectName}/agent/containers/${containerNumber}/heartbeat`;

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (response.ok) {
        const data = await response.json() as { graceful_stop_requested?: boolean };
        if (data.graceful_stop_requested) {
          this._gracefulStopRequested = true;
        }
        return { graceful_stop_requested: data.graceful_stop_requested ?? false };
      }
    } catch {
      // Ignore heartbeat failures
    }

    return { graceful_stop_requested: false };
  }

  private async _checkShouldContinue(): Promise<boolean> {
    if (!this.config.hostApiUrl || !this.config.projectName) {
      return !this._gracefulStopRequested;
    }

    const containerNumber = this.config.containerNumber ?? 1;
    const url = `${this.config.hostApiUrl}/api/projects/${this.config.projectName}/agent/containers/${containerNumber}/session`;

    try {
      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json() as { should_continue?: boolean };
        return data.should_continue ?? !this._gracefulStopRequested;
      }
    } catch {
      // On error, default to checking graceful stop flag
    }

    return !this._gracefulStopRequested;
  }
}

// =============================================================================
// Factory Functions
// =============================================================================

/**
 * Create an executor for a coder agent.
 */
export function createCoderAgent(
  workingDirectory: string,
  options?: Partial<Omit<AgentConfig, 'agentRole' | 'workingDirectory'>>
): AgentExecutor {
  return new AgentExecutor({
    agentRole: 'coder',
    workingDirectory,
    ...options,
  });
}

/**
 * Create an executor for a reviewer agent.
 */
export function createReviewerAgent(
  workingDirectory: string,
  options?: Partial<Omit<AgentConfig, 'agentRole' | 'workingDirectory'>>
): AgentExecutor {
  return new AgentExecutor({
    agentRole: 'reviewer',
    workingDirectory,
    ...options,
  });
}

/**
 * Create an executor for an overseer agent.
 */
export function createOverseerAgent(
  workingDirectory: string,
  options?: Partial<Omit<AgentConfig, 'agentRole' | 'workingDirectory'>>
): AgentExecutor {
  return new AgentExecutor({
    agentRole: 'overseer',
    workingDirectory,
    ...options,
  });
}

/**
 * Create an executor for an initializer agent.
 */
export function createInitializerAgent(
  workingDirectory: string,
  options?: Partial<Omit<AgentConfig, 'agentRole' | 'workingDirectory'>>
): AgentExecutor {
  return new AgentExecutor({
    agentRole: 'initializer',
    workingDirectory,
    model: 'opus', // Initializer always uses Opus
    ...options,
  });
}

// =============================================================================
// Docker Container Integration
// =============================================================================

/**
 * Execute an agent inside a Docker container using the TypeScript SDK.
 * This is an alternative to the Python agent_app.py approach.
 */
export async function executeAgentInContainer(
  containerName: string,
  prompt: string,
  config: {
    agentRole: AgentRole;
    model?: ModelType;
    modelId?: string;
    projectName: string;
    containerNumber: number;
    hostApiUrl?: string;
  },
  callbacks?: {
    onOutput?: OutputCallback;
    onStatus?: StatusCallback;
    onMessage?: MessageCallback;
  }
): Promise<ExecutionResult> {
  const { spawn } = await import('node:child_process');

  return new Promise((resolve) => {
    const env = [
      `-e`, `AGENT_TYPE=${config.agentRole}`,
      `-e`, `PROJECT_NAME=${config.projectName}`,
      `-e`, `CONTAINER_NUMBER=${config.containerNumber}`,
    ];

    if (config.modelId) {
      env.push('-e', `AGENT_MODEL=${config.modelId}`);
    } else if (config.model) {
      env.push('-e', `AGENT_MODEL=${getModelId(config.model, config.agentRole)}`);
    }

    if (config.hostApiUrl) {
      env.push('-e', `HOST_API_URL=${config.hostApiUrl}`);
    }

    // Run the TypeScript agent app inside the container
    const args = [
      'exec', '-i', '-u', 'coder',
      ...env,
      containerName,
      'node', '/app/dist/ts-agent-app.js',
    ];

    const proc = spawn('docker', args, {
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    // Send prompt via stdin
    proc.stdin?.write(prompt);
    proc.stdin?.end();

    // Handle output
    proc.stdout?.on('data', (data: Buffer) => {
      const lines = data.toString().split('\n');
      for (const line of lines) {
        if (line.trim()) {
          callbacks?.onOutput?.(sanitizeOutput(line));
        }
      }
    });

    proc.stderr?.on('data', (data: Buffer) => {
      const lines = data.toString().split('\n');
      for (const line of lines) {
        if (line.trim()) {
          callbacks?.onOutput?.(sanitizeOutput(line));
        }
      }
    });

    proc.on('close', (code: number | null) => {
      const exitCode = code ?? 1;

      callbacks?.onStatus?.(exitCode === 0 ? 'completed' : 'failed');

      resolve({
        exitCode,
        success: exitCode === 0 || exitCode === EXIT_CODES.GRACEFUL_STOP || exitCode === EXIT_CODES.CONTEXT_LIMIT,
        message: exitCode === 0
          ? 'Agent execution completed'
          : exitCode === EXIT_CODES.GRACEFUL_STOP
            ? 'Agent stopped gracefully'
            : exitCode === EXIT_CODES.CONTEXT_LIMIT
              ? 'Context limit reached'
              : `Agent failed with exit code ${exitCode}`,
      });
    });

    proc.on('error', (error: Error) => {
      callbacks?.onStatus?.('failed');
      resolve({
        exitCode: EXIT_CODES.FAILURE,
        success: false,
        message: `Failed to spawn agent process: ${error.message}`,
      });
    });
  });
}
