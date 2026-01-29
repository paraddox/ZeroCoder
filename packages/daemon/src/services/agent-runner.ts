/**
 * Agent Runner Service
 * ====================
 *
 * Claude Agent SDK integration for running agents.
 * Adapted from container_scripts_ts/src/agent_app.ts
 */

import { query } from '@anthropic-ai/claude-agent-sdk';
import type { Options } from '@anthropic-ai/claude-agent-sdk';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { createLogger } from '../utils/logger.js';

const log = createLogger('agent-runner');

// Exit codes
export const EXIT_SUCCESS = 0;
export const EXIT_FAILURE = 1;
export const EXIT_GRACEFUL_STOP = 129;
export const EXIT_INTERRUPTED = 130;

// Default model
const DEFAULT_AGENT_MODEL = 'claude-sonnet-4-5-20250514';

// Config file path (relative to project directory)
const AGENT_CONFIG_FILE = 'prompts/.agent_config.json';

/** Agent types for different roles */
export type AgentType = 'initializer' | 'coder' | 'reviewer' | 'overseer';

/** Agent run result */
export interface AgentRunResult {
  exitCode: number;
  interrupted: boolean;
  error?: string;
}

/** Callback for agent output */
export type AgentOutputCallback = (line: string) => Promise<void>;

/**
 * Read agent model from environment or project config.
 */
function getAgentModel(projectDir: string): string {
  const envModel = process.env['AGENT_MODEL'];
  if (envModel) {
    log.info('Using model from environment', { model: envModel });
    return envModel;
  }

  const configPath = join(projectDir, AGENT_CONFIG_FILE);
  if (existsSync(configPath)) {
    try {
      const config = JSON.parse(readFileSync(configPath, 'utf8'));
      const model = config.agent_model || DEFAULT_AGENT_MODEL;
      log.info('Using model from config', { model, configPath });
      return model;
    } catch (e) {
      log.warn('Error reading config', { error: e instanceof Error ? e.message : String(e) });
    }
  }

  log.info('Using default model', { model: DEFAULT_AGENT_MODEL });
  return DEFAULT_AGENT_MODEL;
}

/**
 * Global state for tracking current agent run.
 */
let _currentRunAborted = false;

/**
 * Request abort of the current agent run.
 */
export function abortCurrentRun(): void {
  _currentRunAborted = true;
}

/**
 * Reset abort state for a new run.
 */
function resetAbortState(): void {
  _currentRunAborted = false;
}

/**
 * Run a Claude agent with the given prompt.
 */
export async function runAgent(
  prompt: string,
  projectDir: string,
  onOutput?: AgentOutputCallback,
  maxRetries: number = 3
): Promise<AgentRunResult> {
  resetAbortState();

  const model = getAgentModel(projectDir);

  const options: Options = {
    model,
    cwd: projectDir,
    permissionMode: 'bypassPermissions',
    settingSources: ['project'], // Load CLAUDE.md from project directory
  };

  let attempt = 0;
  let lastError: Error | null = null;
  let messageCount = 0;

  while (attempt < maxRetries) {
    attempt++;

    try {
      log.info('Starting agent', { attempt, maxRetries, model, projectDir });

      const queryResult = query({
        prompt,
        options,
      });

      for await (const message of queryResult) {
        messageCount++;

        // Check for abort
        if (_currentRunAborted) {
          log.info('Agent run aborted');
          return {
            exitCode: EXIT_GRACEFUL_STOP,
            interrupted: true,
          };
        }

        // Process message and call output callback
        if (message.type === 'assistant') {
          const content = message.message?.content;
          if (Array.isArray(content)) {
            for (const block of content) {
              if (block.type === 'text') {
                if (onOutput) {
                  await onOutput(block.text);
                }
                log.debug('Agent output', { text: block.text.substring(0, 100) });
              } else if (block.type === 'tool_use') {
                const toolMsg = `[TOOL] Using: ${block.name}`;
                if (onOutput) {
                  await onOutput(toolMsg);
                }
                log.debug('Agent tool use', { tool: block.name });
              }
            }
          }
        }
      }

      // Success
      log.info('Agent completed successfully', { messageCount });
      return {
        exitCode: EXIT_SUCCESS,
        interrupted: false,
      };
    } catch (e) {
      lastError = e instanceof Error ? e : new Error(String(e));
      log.error('Agent attempt failed', {
        attempt,
        maxRetries,
        error: lastError.message,
      });

      if (attempt < maxRetries) {
        const waitTime = Math.pow(2, attempt); // Exponential backoff
        log.info('Retrying', { waitSeconds: waitTime });
        await sleep(waitTime * 1000);
      }
    }
  }

  log.error('All attempts failed', { error: lastError?.message });
  return {
    exitCode: EXIT_FAILURE,
    interrupted: false,
    error: lastError?.message,
  };
}

/**
 * Sleep for the given milliseconds.
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Read a prompt file from the project directory.
 */
export function readPromptFile(projectDir: string, promptName: string): string | null {
  const promptPath = join(projectDir, 'prompts', `${promptName}.md`);
  if (existsSync(promptPath)) {
    return readFileSync(promptPath, 'utf8');
  }
  return null;
}
