/**
 * Agent Orchestrator Service
 * ==========================
 *
 * Manages the agent flow:
 *   bd onboard → bd stats → initializer/coder/reviewer/overseer loop
 *
 * Adapted from container-manager.ts
 */

import { exec, execSync } from 'node:child_process';
import { promisify } from 'node:util';

import { createLogger } from '../utils/logger.js';
import { runAgent, abortCurrentRun, readPromptFile, type AgentType, type AgentOutputCallback } from './agent-runner.js';

const execAsync = promisify(exec);
const log = createLogger('orchestrator');

/** Agent session status */
export type SessionStatus = 'idle' | 'running' | 'stopping' | 'stopped';

/** Current work assignment */
interface CurrentWork {
  projectName: string;
  repoUrl: string;
  projectPath: string;
}

/** Beads stats from `bd stats` */
interface BeadsStats {
  total: number;
  open: number;
  inProgress: number;
  closed: number;
}

/** Global orchestrator state */
let _currentWork: CurrentWork | null = null;
let _sessionStatus: SessionStatus = 'idle';
let _currentAgentType: AgentType | null = null;
let _currentFeature: string | null = null;
let _stopAfterSession = false;
let _hardStop = false;
let _outputCallback: AgentOutputCallback | null = null;

/**
 * Get current session status.
 */
export function getStatus(): {
  status: SessionStatus;
  currentRepo: string | null;
  currentFeature: string | null;
  agentType: AgentType | null;
  stats: BeadsStats | null;
} {
  return {
    status: _sessionStatus,
    currentRepo: _currentWork?.repoUrl ?? null,
    currentFeature: _currentFeature,
    agentType: _currentAgentType,
    stats: _currentWork ? getBeadsStatsSync(_currentWork.projectPath) : null,
  };
}

/**
 * Set the output callback for agent messages.
 */
export function setOutputCallback(callback: AgentOutputCallback | null): void {
  _outputCallback = callback;
}

/**
 * Parse beads stats from `bd stats` output.
 */
function parseBeadsStats(output: string): BeadsStats {
  // Example output:
  // Project: my-project
  // Open: 5, In Progress: 2, Closed: 10, Total: 17
  const match = output.match(/Open:\s*(\d+).*In Progress:\s*(\d+).*Closed:\s*(\d+).*Total:\s*(\d+)/i);
  if (match) {
    return {
      open: parseInt(match[1] ?? '0', 10),
      inProgress: parseInt(match[2] ?? '0', 10),
      closed: parseInt(match[3] ?? '0', 10),
      total: parseInt(match[4] ?? '0', 10),
    };
  }
  return { total: 0, open: 0, inProgress: 0, closed: 0 };
}

/**
 * Get beads stats synchronously (from cache or blocking call).
 */
function getBeadsStatsSync(projectPath: string): BeadsStats | null {
  try {
    const output = execSync('bd stats', {
      cwd: projectPath,
      timeout: 10000,
      encoding: 'utf8',
    }) as string;
    return parseBeadsStats(output);
  } catch {
    return null;
  }
}

/**
 * Get beads stats asynchronously.
 */
async function getBeadsStats(projectPath: string): Promise<BeadsStats> {
  try {
    const { stdout } = await execAsync('bd stats', {
      cwd: projectPath,
      timeout: 30000,
    });
    return parseBeadsStats(stdout);
  } catch (err) {
    log.warn('Failed to get beads stats', { error: err instanceof Error ? err.message : String(err) });
    return { total: 0, open: 0, inProgress: 0, closed: 0 };
  }
}

/**
 * Run bd onboard to sync beads.
 */
async function runBdOnboard(projectPath: string): Promise<void> {
  log.info('Running bd onboard');
  try {
    await execAsync('bd onboard', { cwd: projectPath, timeout: 120000 });
    log.info('bd onboard completed');
  } catch (err) {
    log.warn('bd onboard failed (may be expected)', { error: err instanceof Error ? err.message : String(err) });
  }
}

/**
 * Get the prompt for a specific agent type.
 */
function getPromptForAgent(projectPath: string, agentType: AgentType, featureId?: string): string {
  let promptFile: string;
  switch (agentType) {
    case 'initializer':
      promptFile = 'initializer_prompt';
      break;
    case 'coder':
      promptFile = 'coding_prompt';
      break;
    case 'reviewer':
      promptFile = 'reviewer_prompt';
      break;
    case 'overseer':
      promptFile = 'overseer_prompt';
      break;
  }

  let prompt = readPromptFile(projectPath, promptFile);

  if (!prompt) {
    // Fallback prompts
    switch (agentType) {
      case 'initializer':
        prompt = 'Read prompts/app_spec.txt and create beads issues for each feature. Set up the project structure.';
        break;
      case 'coder':
        prompt = 'Claim the next available feature using `bd claim` and implement it. Follow the workflow in AGENTS.md.';
        break;
      case 'reviewer':
        prompt = `Review the implementation of feature ${featureId}. Approve or reopen with detailed feedback.`;
        break;
      case 'overseer':
        prompt = 'Run quality verification: test suite, spec verification (if app_spec.txt exists), and code quality scan.';
        break;
    }
  }

  // Replace placeholders
  if (featureId && prompt.includes('{FEATURE_ID}')) {
    prompt = prompt.replace(/\{FEATURE_ID\}/g, featureId);
  }

  return prompt;
}

/**
 * Determine the next agent type to run based on current stats.
 */
function determineNextAgent(stats: BeadsStats, lastAgent: AgentType | null): AgentType | null {
  // If no features exist, run initializer
  if (stats.total === 0) {
    return 'initializer';
  }

  // If all done, run overseer for final verification
  if (stats.open === 0 && stats.inProgress === 0) {
    if (lastAgent !== 'overseer') {
      return 'overseer';
    }
    return null; // Complete
  }

  // Check for 10% milestones for overseer
  const percentage = (stats.closed / stats.total) * 100;
  const milestone = Math.floor(percentage / 10) * 10;

  // Run overseer at milestones (10%, 20%, etc.) if not just ran
  if (milestone > 0 && milestone % 10 === 0 && lastAgent !== 'overseer') {
    // Simple heuristic: run overseer occasionally
    // In production, track last milestone in state
    if (Math.random() < 0.2) {
      return 'overseer';
    }
  }

  // Default: run coder
  return 'coder';
}

/**
 * Run a single agent session.
 */
async function runAgentSession(agentType: AgentType, projectPath: string, featureId?: string): Promise<boolean> {
  _currentAgentType = agentType;
  _currentFeature = featureId ?? null;

  log.info('Starting agent session', { agentType, featureId });

  const prompt = getPromptForAgent(projectPath, agentType, featureId);

  const result = await runAgent(prompt, projectPath, async (line) => {
    if (_outputCallback) {
      await _outputCallback(line);
    }
  });

  _currentAgentType = null;
  _currentFeature = null;

  if (result.interrupted) {
    log.info('Agent session interrupted');
    return false;
  }

  if (result.exitCode !== 0) {
    log.warn('Agent session failed', { exitCode: result.exitCode, error: result.error });
  } else {
    log.info('Agent session completed');
  }

  return true;
}

/**
 * Main agent orchestration loop.
 */
async function orchestrationLoop(projectPath: string): Promise<void> {
  let lastAgent: AgentType | null = null;

  while (!_hardStop && !_stopAfterSession) {
    // Run bd onboard at start of each iteration
    await runBdOnboard(projectPath);

    // Get current stats
    const stats = await getBeadsStats(projectPath);
    log.info('Current stats', stats as unknown as Record<string, unknown>);

    // Determine next agent
    const nextAgent = determineNextAgent(stats, lastAgent);

    if (!nextAgent) {
      log.info('All work complete');
      break;
    }

    // Run the agent
    const shouldContinue = await runAgentSession(nextAgent, projectPath);

    // Sync beads changes to git remote after each session
    try {
      await execAsync('bd sync', { cwd: projectPath, timeout: 30000 });
      log.info('Beads synced to remote');
    } catch (err) {
      log.warn('Failed to sync beads', { error: err instanceof Error ? err.message : String(err) });
    }

    if (!shouldContinue) {
      log.info('Agent interrupted, stopping');
      break;
    }

    lastAgent = nextAgent;

    // Check if we should stop after this session
    if (_stopAfterSession) {
      log.info('Graceful stop requested, stopping after session');
      break;
    }

    // Small delay between sessions
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
}

/**
 * Start working on a project.
 */
export async function startWork(
  projectName: string,
  repoUrl: string,
  projectPath: string
): Promise<{ success: boolean; message: string }> {
  if (_sessionStatus !== 'idle' && _sessionStatus !== 'stopped') {
    return {
      success: false,
      message: `Cannot start: session is ${_sessionStatus}`,
    };
  }

  _currentWork = { projectName, repoUrl, projectPath };
  _sessionStatus = 'running';
  _stopAfterSession = false;
  _hardStop = false;

  log.info('Starting work', { projectName, repoUrl, projectPath });

  // Run orchestration loop in background
  orchestrationLoop(projectPath)
    .then(() => {
      log.info('Orchestration loop completed');
      _sessionStatus = 'stopped';
    })
    .catch((err) => {
      log.error('Orchestration loop error', { error: err instanceof Error ? err.message : String(err) });
      _sessionStatus = 'stopped';
    });

  return {
    success: true,
    message: 'Work started',
  };
}

/**
 * Request graceful stop (finish current session then stop).
 */
export function requestGracefulStop(): void {
  log.info('Graceful stop requested');
  _stopAfterSession = true;
  _sessionStatus = 'stopping';
}

/**
 * Request hard stop (immediate).
 */
export function requestHardStop(): void {
  log.info('Hard stop requested');
  _hardStop = true;
  _stopAfterSession = true;
  _sessionStatus = 'stopping';
  abortCurrentRun();
}

/**
 * Wait for session status to become 'stopped' with timeout.
 * Returns true if stopped, false if timeout.
 */
export async function waitForStopped(timeoutMs: number = 5000): Promise<boolean> {
  const start = Date.now();
  while (_sessionStatus === 'stopping' && Date.now() - start < timeoutMs) {
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  return _sessionStatus === 'stopped';
}

/**
 * Get current session status value.
 */
export function getSessionStatus(): SessionStatus {
  return _sessionStatus;
}

/**
 * Graceful shutdown for daemon exit.
 */
export async function gracefulShutdown(): Promise<void> {
  log.info('Graceful shutdown');
  requestHardStop();

  // Wait for session to stop (max 30 seconds)
  let waited = 0;
  while (_sessionStatus === 'running' || _sessionStatus === 'stopping') {
    await new Promise((resolve) => setTimeout(resolve, 100));
    waited += 100;
    if (waited > 30000) {
      log.warn('Shutdown timeout, forcing exit');
      break;
    }
  }
}

/**
 * Check if currently running.
 */
export function isRunning(): boolean {
  return _sessionStatus === 'running';
}

/**
 * Reset state (for testing).
 */
export function resetState(): void {
  _currentWork = null;
  _sessionStatus = 'idle';
  _currentAgentType = null;
  _currentFeature = null;
  _stopAfterSession = false;
  _hardStop = false;
  _outputCallback = null;
}
