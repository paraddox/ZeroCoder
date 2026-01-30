/**
 * Container Manager
 * =================
 *
 * Manages Docker containers for per-project Claude Code execution.
 * Each project gets its own sandboxed container.
 *
 * Converted from server/services/container_manager.py
 */

import { spawn, spawnSync } from 'node:child_process';
import { promisify } from 'node:util';
import { exec } from 'node:child_process';
import { existsSync, writeFileSync, unlinkSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { Mutex } from 'async-mutex';

import {
  CallbackManager,
  createContainerCallbackManager,
  type OutputCallback,
  type StatusCallback,
} from '../websocket/callback-system.js';
import {
  getProjectsDir,
  getContainer,
  createContainer as createContainerRecord,
  deleteContainer as deleteContainerRecord,
  updateContainerStatus,
  setUserStarted,
  isUserStarted,
  setGracefulStop,
  isGracefulStopRequested,
  setRestarting,
  isRestarting,
  setOverseerFlags,
  getOverseerFlags,
  updateLastActivity,
  getLastActivity,
  setLastClosedFeature,
  getLastClosedFeature,
  listContainers,
  listAllContainers,
  setVerificationRunning,
  clearVerificationState,
  getOverseerMilestone,
  updateOverseerMilestone,
  getProjectGitUrl,
} from '../db/crud.js';
import { type ContainerType } from '../db/schema.js';
import { getCachedStats } from './beads-manager.js';
import { refreshProjectPrompts, getReviewerPrompt, getOverseerPrompt } from '../utils/prompts.js';

const execAsync = promisify(exec);

// Get __dirname equivalent for ES modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// =============================================================================
// Constants
// =============================================================================

/** Staggered startup delay in seconds between containers */
export const CONTAINER_STARTUP_DELAY = 60;

/** Container image name */
export const CONTAINER_IMAGE = 'zerocoder-project';

/** Path to Dockerfile for building the image */
const DOCKERFILE_PATH = join(__dirname, '../../../../Dockerfile.project');

/** Idle timeout in minutes (for stopping inactive containers) */
export const IDLE_TIMEOUT_MINUTES = 15;

/** Stuck agent timeout in minutes (agent running but no output) */
export const AGENT_STUCK_TIMEOUT_MINUTES = 10;

/** Pre-agent sync timeout in ms (per git/bd command) */
export const PRE_AGENT_SYNC_TIMEOUT = 120000;

/** Agent health check interval in seconds (5 minutes) */
export const AGENT_HEALTH_CHECK_INTERVAL = 300;

/** Agent status type */
export type AgentStatus = 'not_created' | 'running' | 'stopped' | 'completed';

/** Agent type for OpenCode routing */
export type AgentType = 'coder' | 'reviewer' | 'overseer';

// =============================================================================
// Sensitive Data Patterns (for output sanitization)
// =============================================================================

const SENSITIVE_PATTERNS = [
  /sk-ant[a-zA-Z0-9_-]*/gi, // Anthropic API keys
  /sk-[a-zA-Z0-9]{20,}/gi, // Generic sk- keys
  /ANTHROPIC_API_KEY=[^\s]+/gi,
  /api[_-]?key[=:][^\s]+/gi,
  /token[=:][^\s]+/gi,
  /password[=:][^\s]+/gi,
  /secret[=:][^\s]+/gi,
];

/**
 * Remove sensitive information from output lines.
 */
export function sanitizeOutput(line: string): string {
  let result = line;
  for (const pattern of SENSITIVE_PATTERNS) {
    result = result.replace(pattern, '[REDACTED]');
  }
  return result;
}

// =============================================================================
// Docker Image Management
// =============================================================================

/**
 * Check if a Docker image exists.
 */
export async function imageExists(imageName: string = CONTAINER_IMAGE): Promise<boolean> {
  try {
    await execAsync(`docker image inspect ${imageName}`);
    return true;
  } catch {
    return false;
  }
}

/**
 * Build the Docker image from Dockerfile.project.
 */
export async function buildImage(imageName: string = CONTAINER_IMAGE): Promise<[boolean, string]> {
  if (!existsSync(DOCKERFILE_PATH)) {
    return [false, `Dockerfile not found at ${DOCKERFILE_PATH}`];
  }

  console.log(`Building Docker image ${imageName}...`);
  const buildContext = dirname(DOCKERFILE_PATH);

  try {
    await execAsync(
      `docker build -f "${DOCKERFILE_PATH}" -t ${imageName} "${buildContext}"`,
      { timeout: 600000 } // 10 minute timeout
    );
    console.log(`Docker image ${imageName} built successfully`);
    return [true, `Image ${imageName} built successfully`];
  } catch (err) {
    const error = err as Error;
    console.error(`Docker build failed: ${error.message}`);
    return [false, `Failed to build image: ${error.message}`];
  }
}

/**
 * Ensure the Docker image exists, building it if necessary.
 */
export async function ensureImageExists(imageName: string = CONTAINER_IMAGE): Promise<[boolean, string]> {
  if (await imageExists(imageName)) {
    return [true, 'Image exists'];
  }

  console.log(`Image ${imageName} not found, building...`);
  return buildImage(imageName);
}

/**
 * Check if Docker is available and running.
 */
export async function checkDockerAvailable(): Promise<boolean> {
  try {
    await execAsync('docker info', { timeout: 5000 });
    return true;
  } catch {
    return false;
  }
}

/**
 * Check if the project container image exists.
 */
export async function checkImageExists(): Promise<boolean> {
  return imageExists(CONTAINER_IMAGE);
}

// =============================================================================
// ContainerManager Class
// =============================================================================

/**
 * Manages a Docker container for a single project.
 *
 * Container lifecycle:
 * - not_created: Project exists but container never started
 * - running: Container is running, Claude Code is active
 * - stopped: Container stopped (idle timeout or manual), can restart quickly
 * - completed: All features done, container stopped
 */
export class ContainerManager {
  public readonly projectName: string;
  public readonly gitUrl: string;
  public readonly containerNumber: number;
  public readonly projectDir: string;
  public readonly containerName: string;

  private _isInitContainer: boolean;
  private _status: AgentStatus = 'not_created';
  private _startedAt: Date | null = null;
  private _logAbortController: AbortController | null = null;

  // Agent tracking
  private _currentAgentType: AgentType = 'coder';
  private _forceClaudeSdk: boolean = false;
  private _currentFeature: string | null = null;
  private _forcedModel: string = 'claude-opus-4-5-20251101';
  private _agentDispatched: boolean = false;

  // Callback manager
  private _callbacks: CallbackManager;

  /**
   * Initialize the container manager.
   */
  constructor(
    projectName: string,
    gitUrl: string,
    containerNumber: number = 1,
    projectDir?: string
  ) {
    this.projectName = projectName;
    this.gitUrl = gitUrl;
    this.containerNumber = containerNumber;

    // Local path for reading prompts/config
    this.projectDir = projectDir || join(getProjectsDir(), projectName);

    // Container naming: init container vs coding containers
    if (containerNumber === 0) {
      this.containerName = `zerocoder-${projectName}-init`;
      this._isInitContainer = true;
    } else {
      this.containerName = `zerocoder-${projectName}-${containerNumber}`;
      this._isInitContainer = false;
    }

    this._callbacks = createContainerCallbackManager();

    // Check initial container status
    this._syncStatus();
  }

  // ===========================================================================
  // Properties
  // ===========================================================================

  get status(): AgentStatus {
    return this._status;
  }

  set status(value: AgentStatus) {
    const oldStatus = this._status;
    this._status = value;
    if (oldStatus !== value) {
      this._callbacks.notifyStatusChange(value);
    }
  }

  get containerType(): ContainerType {
    return this._isInitContainer ? 'init' : 'coding';
  }

  get startedAt(): Date | null {
    return this._startedAt;
  }

  get userStarted(): boolean {
    return isUserStarted(this.projectName, this.containerNumber, this.containerType);
  }

  // ===========================================================================
  // Session State Properties (DB-backed)
  // ===========================================================================

  private get _userStarted(): boolean {
    return isUserStarted(this.projectName, this.containerNumber, this.containerType);
  }

  private set _userStarted(value: boolean) {
    setUserStarted(this.projectName, this.containerNumber, value, this.containerType);
  }

  private get _gracefulStopRequested(): boolean {
    return isGracefulStopRequested(this.projectName, this.containerNumber, this.containerType);
  }

  private set _gracefulStopRequested(value: boolean) {
    setGracefulStop(this.projectName, this.containerNumber, value, this.containerType);
  }

  private get _restarting(): boolean {
    return isRestarting(this.projectName, this.containerNumber, this.containerType);
  }

  private set _restarting(value: boolean) {
    setRestarting(this.projectName, this.containerNumber, value, this.containerType);
  }

  private get _lastAgentWasOverseer(): boolean {
    const { lastAgentWasOverseer } = getOverseerFlags(
      this.projectName,
      this.containerNumber,
      this.containerType
    );
    return lastAgentWasOverseer;
  }

  private set _lastAgentWasOverseer(value: boolean) {
    const { isMilestoneOverseer } = getOverseerFlags(
      this.projectName,
      this.containerNumber,
      this.containerType
    );
    setOverseerFlags(this.projectName, this.containerNumber, value, isMilestoneOverseer, this.containerType);
  }

  private get _isMilestoneOverseer(): boolean {
    const { isMilestoneOverseer } = getOverseerFlags(
      this.projectName,
      this.containerNumber,
      this.containerType
    );
    return isMilestoneOverseer;
  }

  private set _isMilestoneOverseer(value: boolean) {
    const { lastAgentWasOverseer } = getOverseerFlags(
      this.projectName,
      this.containerNumber,
      this.containerType
    );
    setOverseerFlags(this.projectName, this.containerNumber, lastAgentWasOverseer, value, this.containerType);
  }

  private get lastActivity(): Date | null {
    return getLastActivity(this.projectName, this.containerNumber, this.containerType);
  }

  private set lastActivity(_value: Date | null) {
    // Only update if value is not null
    updateLastActivity(this.projectName, this.containerNumber, this.containerType);
  }

  // ===========================================================================
  // Callback Methods
  // ===========================================================================

  addOutputCallback(callback: OutputCallback): void {
    this._callbacks.addOutputCallback(callback);
  }

  removeOutputCallback(callback: OutputCallback): void {
    this._callbacks.removeOutputCallback(callback);
  }

  addStatusCallback(callback: StatusCallback): void {
    this._callbacks.addStatusCallback(callback);
  }

  removeStatusCallback(callback: StatusCallback): void {
    this._callbacks.removeStatusCallback(callback);
  }

  private async _broadcastOutput(line: string): Promise<void> {
    await this._callbacks.broadcastOutput(line);
  }

  // ===========================================================================
  // Status & Activity Methods
  // ===========================================================================

  private _updateActivity(): void {
    this.lastActivity = new Date();
  }

  /**
   * Check if container has been idle for longer than timeout.
   */
  isIdle(): boolean {
    const lastAct = this.lastActivity;
    if (!lastAct) return false;
    const idleDuration = Date.now() - lastAct.getTime();
    return idleDuration > IDLE_TIMEOUT_MINUTES * 60 * 1000;
  }

  /**
   * Get seconds since last activity.
   */
  getIdleSeconds(): number {
    const lastAct = this.lastActivity;
    if (!lastAct) return 0;
    return Math.floor((Date.now() - lastAct.getTime()) / 1000);
  }

  /**
   * Check if agent is running but not producing output (stuck).
   */
  isAgentStuck(): boolean {
    const lastAct = this.lastActivity;
    if (!lastAct) return false;
    if (!this.isAgentRunningSync()) return false;
    const stuckDuration = Date.now() - lastAct.getTime();
    return stuckDuration > AGENT_STUCK_TIMEOUT_MINUTES * 60 * 1000;
  }

  /**
   * Check if the agent process is running inside the container (sync version).
   */
  isAgentRunningSync(): boolean {
    if (this._status !== 'running') return false;
    try {
      const checkCmd = this._isOpenCodeModel()
        ? ['docker', 'exec', this.containerName, 'pgrep', '-f', 'node.*opencode_agent_app']
        : ['docker', 'exec', this.containerName, 'pgrep', '-f', 'node.*agent_app'];
      const cmd = checkCmd[0];
      if (!cmd) return false;
      const result = spawnSync(cmd, checkCmd.slice(1), { timeout: 5000 });
      return result.status === 0;
    } catch {
      return false;
    }
  }

  /**
   * Check if the agent process is running inside the container (async version).
   */
  async isAgentRunning(): Promise<boolean> {
    if (this._status !== 'running') return false;
    try {
      const checkCmd = this._isOpenCodeModel()
        ? `docker exec ${this.containerName} pgrep -f "node.*opencode_agent_app"`
        : `docker exec ${this.containerName} pgrep -f "node.*agent_app"`;
      await execAsync(checkCmd, { timeout: 5000 });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Sync status with actual Docker container state (Docker is source of truth).
   */
  private _syncStatus(): void {
    // Preserve "completed" status
    if (this._status === 'completed') return;

    try {
      const result = spawnSync('docker', [
        'inspect',
        '-f',
        '{{.State.Status}}',
        this.containerName,
      ]);

      const dockerExists = result.status === 0;
      const dockerStatus = result.stdout?.toString().trim();

      if (dockerExists) {
        // Docker has this container - ensure DB reflects this
        const dbContainer = getContainer(this.projectName, this.containerNumber, this.containerType);
        if (!dbContainer) {
          try {
            createContainerRecord(this.projectName, this.containerNumber, this.containerType);
            console.log(`Registered existing Docker container ${this.containerName} in database`);
          } catch (e) {
            console.warn(`Failed to register container in database: ${e}`);
          }
        } else if (!this._currentFeature && dbContainer.currentFeature) {
          this._currentFeature = dbContainer.currentFeature;
        }

        if (dockerStatus === 'running') {
          this._status = 'running';
          if (!this.lastActivity) {
            this._initLastActivityFromLogs();
          }
        } else {
          this._status = 'stopped';
        }
      } else {
        // Docker doesn't have this container
        const dbContainer = getContainer(this.projectName, this.containerNumber, this.containerType);
        if (dbContainer) {
          try {
            deleteContainerRecord(this.projectName, this.containerNumber, this.containerType);
            console.log(`Removed stale DB entry for ${this.containerName}`);
          } catch (e) {
            console.warn(`Failed to clean up stale container from database: ${e}`);
          }
        }
        this._status = 'not_created';
      }
    } catch (e) {
      console.warn(`Failed to check Docker container status: ${e}`);
    }
  }

  /**
   * Initialize last_activity from container's last log timestamp.
   */
  private _initLastActivityFromLogs(): void {
    try {
      const result = spawnSync(
        'docker',
        ['logs', '--tail', '1', '--timestamps', this.containerName],
        { timeout: 5000 }
      );
      const line = result.stdout?.toString().trim();
      if (line) {
        const timestampStr = line.split(' ')[0];
        if (timestampStr) {
          const ts = timestampStr.replace('Z', '+00:00');
          this.lastActivity = new Date(ts);
          console.log(`Initialized last_activity from logs: ${this.lastActivity}`);
        }
      }
    } catch (e) {
      console.debug(`Could not init last_activity from logs: ${e}`);
    }
  }

  // ===========================================================================
  // Model & SDK Detection
  // ===========================================================================

  /**
   * Read agent model from project config file.
   */
  private _getAgentModel(): string {
    const configPath = join(this.projectDir, 'prompts', '.agent_config.json');
    const defaultModel = 'claude-sonnet-4-5-20250514';
    if (existsSync(configPath)) {
      try {
        const config = JSON.parse(readFileSync(configPath, 'utf-8'));
        return config.agent_model || defaultModel;
      } catch (e) {
        console.warn(`Failed to read agent config: ${e}`);
      }
    }
    return defaultModel;
  }

  /**
   * Check if the current model requires OpenCode SDK.
   */
  private _isOpenCodeModel(): boolean {
    const model = this._getAgentModel();
    return model === 'glm-4-7' || model === 'minimax-m2-1';
  }

  // ===========================================================================
  // Feature Management
  // ===========================================================================

  /**
   * Update current feature and broadcast change via WebSocket.
   */
  private async _setCurrentFeature(featureId: string | null): Promise<void> {
    if (this._currentFeature === featureId) return;

    this._currentFeature = featureId;
    console.log(`[${this.containerName}] Current feature: ${featureId}`);

    // Update database
    try {
      updateContainerStatus(this.projectName, this.containerNumber, this.containerType, {
        currentFeature: featureId,
      });
    } catch (e) {
      console.warn(`Failed to update current_feature in database: ${e}`);
    }

    // TODO: Broadcast via WebSocket when websocket manager is implemented
  }

  /**
   * Check if project has open features.
   */
  hasOpenFeatures(): boolean {
    try {
      const stats = getCachedStats(this.projectName);
      if (!stats) return true;
      return (stats.pending || 0) + (stats.in_progress || 0) > 0;
    } catch (e) {
      console.warn(`Failed to check open features: ${e}`);
      return true; // Assume features exist on error (safer)
    }
  }

  // ===========================================================================
  // Git State Recovery
  // ===========================================================================

  /**
   * Recover from corrupted git state (stuck rebase, ref locks, diverged branches).
   */
  async recoverGitState(): Promise<[boolean, string]> {
    if (this._status !== 'running') {
      return [false, 'Container must be running for git recovery'];
    }

    try {
      await this._broadcastOutput('[System] Recovering git state...');

      const runGit = async (cmd: string[], timeout = 30000): Promise<{ returncode: number; stdout: string; stderr: string }> => {
        try {
          const { stdout, stderr } = await execAsync(
            `docker exec -u coder ${this.containerName} ${cmd.join(' ')}`,
            { timeout }
          );
          return { returncode: 0, stdout, stderr };
        } catch (err: unknown) {
          const error = err as { stdout?: string; stderr?: string; code?: number };
          return { returncode: error.code || 1, stdout: error.stdout || '', stderr: error.stderr || '' };
        }
      };

      const getDefaultBranch = async (): Promise<string> => {
        let result = await runGit(['git', 'symbolic-ref', 'refs/remotes/origin/HEAD']);
        if (result.returncode === 0) {
          const ref = result.stdout.trim();
          return ref.split('/').pop() || 'main';
        }
        for (const branch of ['main', 'master', 'develop']) {
          result = await runGit(['git', 'rev-parse', '--verify', `origin/${branch}`]);
          if (result.returncode === 0) return branch;
        }
        return 'main';
      };

      const defaultBranch = await getDefaultBranch();

      // 1. Abort stuck operations
      for (const abortCmd of [
        ['git', 'rebase', '--abort'],
        ['git', 'merge', '--abort'],
        ['git', 'cherry-pick', '--abort'],
      ]) {
        await runGit(abortCmd);
      }

      // 2. Fix ref locks with git gc
      await runGit(['git', 'gc', '--prune=now'], 60000);

      // 3. Prune stale remote refs
      await runGit(['git', 'remote', 'prune', 'origin']);

      // 4. Fetch latest
      await runGit(['git', 'fetch', 'origin', '+refs/heads/*:refs/remotes/origin/*'], 60000);

      // 5. Check for changes
      const statusResult = await runGit(['git', 'status', '--porcelain']);
      const hasChanges = Boolean(statusResult.stdout.trim());

      // 6. Reset to clean state
      if (hasChanges) {
        console.log('Discarding uncommitted changes during git recovery');
        await runGit(['git', 'reset', '--hard', 'HEAD']);
        await runGit(['git', 'clean', '-fd']);
      }

      // 7. Checkout and reset default branch
      await runGit(['git', 'checkout', defaultBranch]);

      const verifyResult = await runGit(['git', 'rev-parse', '--verify', `origin/${defaultBranch}`]);
      if (verifyResult.returncode === 0) {
        await runGit(['git', 'reset', '--hard', `origin/${defaultBranch}`]);
      } else {
        await runGit(['git', 'reset', '--hard', 'HEAD']);
      }

      // 8. Clean up orphaned feature branches
      const branchResult = await runGit(['git', 'branch', '--list', 'feature/*']);
      if (branchResult.returncode === 0 && branchResult.stdout.trim()) {
        const branches = branchResult.stdout
          .trim()
          .split('\n')
          .map((b) => b.trim().replace(/^\* /, ''))
          .filter(Boolean);
        for (const branch of branches) {
          await runGit(['git', 'branch', '-D', branch]);
          console.log(`Deleted orphaned feature branch: ${branch}`);
        }
      }

      console.log(`Git state recovered for ${this.projectName}`);
      return [true, 'Git state recovered'];
    } catch (e) {
      console.error(`Error recovering git state for ${this.projectName}: ${e}`);
      return [false, `Git recovery error: ${e}`];
    }
  }

  /**
   * Run before agent starts: pull latest code and sync beads.
   */
  async preAgentSync(): Promise<[boolean, string]> {
    if (this._status !== 'running') {
      return [false, 'Container must be running for pre-agent sync'];
    }

    const recoverableErrors = [
      'cannot lock ref',
      'would be overwritten',
      'divergent branches',
      'rebase in progress',
      'You are currently',
      'needs merge',
      'not possible because you have unmerged files',
      'unstaged changes',
      'uncommitted changes',
      'is already checked out',
    ];

    const needsRecovery = (stderr: string): boolean =>
      recoverableErrors.some((pattern) => stderr.includes(pattern));

    const runGit = async (cmd: string[]): Promise<{ returncode: number; stdout: string; stderr: string }> => {
      try {
        const { stdout, stderr } = await execAsync(
          `docker exec -u coder ${this.containerName} ${cmd.join(' ')}`,
          { timeout: PRE_AGENT_SYNC_TIMEOUT }
        );
        return { returncode: 0, stdout, stderr };
      } catch (err: unknown) {
        const error = err as { stdout?: string; stderr?: string; code?: number };
        return { returncode: error.code || 1, stdout: error.stdout || '', stderr: error.stderr || '' };
      }
    };

    const getDefaultBranch = async (): Promise<string> => {
      let result = await runGit(['git', 'symbolic-ref', 'refs/remotes/origin/HEAD']);
      if (result.returncode === 0) {
        return result.stdout.trim().split('/').pop() || 'main';
      }
      for (const branch of ['main', 'master', 'develop']) {
        result = await runGit(['git', 'rev-parse', '--verify', `origin/${branch}`]);
        if (result.returncode === 0) return branch;
      }
      return 'main';
    };

    try {
      await this._broadcastOutput('[System] Syncing with remote before starting agent...');

      const originCheck = await runGit(['git', 'remote', 'get-url', 'origin']);
      const hasOrigin = originCheck.returncode === 0;

      if (!hasOrigin) {
        console.warn('No origin remote configured in container - skipping fetch');
        await this._broadcastOutput('[System] Warning: No origin remote - using existing code');
      }

      const defaultBranch = await getDefaultBranch();

      type CommandTuple = [string[], string, boolean];
      const commands: CommandTuple[] = hasOrigin
        ? [
            [['git', 'fetch', 'origin', '+refs/heads/*:refs/remotes/origin/*'], 'Fetching from origin', false],
            [['git', 'reset', '--hard', 'HEAD'], 'Discarding local changes', true],
            [['git', 'clean', '-fd'], 'Removing untracked files', true],
            [['git', 'reset', '--hard', `origin/${defaultBranch}`], `Resetting to origin/${defaultBranch}`, false],
          ]
        : [
            [['git', 'reset', '--hard', 'HEAD'], 'Discarding local changes', true],
            [['git', 'clean', '-fd'], 'Removing untracked files', true],
          ];

      let recoveryAttempted = false;

      for (const [cmd, desc, isCritical] of commands) {
        const result = await runGit(cmd);

        if (result.returncode !== 0) {
          const errorMsg = result.stderr + result.stdout;
          console.warn(`${desc} failed: ${errorMsg}`);

          const sshErrors = ['Host key verification failed', 'Permission denied', 'Connection refused', 'Could not resolve host'];
          const isSshError = sshErrors.some((e) => errorMsg.includes(e));

          if (isSshError && desc.toLowerCase().includes('fetch')) {
            console.warn('Network/SSH error during fetch - continuing with existing code');
            await this._broadcastOutput('[System] Fetch failed (network/SSH) - using existing code...');
            continue;
          }

          if (isCritical && !recoveryAttempted && needsRecovery(errorMsg)) {
            console.log('Detected recoverable git error, attempting recovery...');
            recoveryAttempted = true;
            const [recoveryOk] = await this.recoverGitState();
            if (recoveryOk) {
              console.log('Git recovery succeeded, continuing sync');
              await this._broadcastOutput('[System] Git state recovered, continuing sync...');
              continue;
            }
          }
        }
      }

      console.log(`Pre-agent sync completed for ${this.projectName}`);
      return [true, 'Pre-agent sync completed'];
    } catch (e) {
      console.error(`Error in pre-agent sync for ${this.projectName}: ${e}`);
      return [false, `Pre-agent sync error: ${e}`];
    }
  }

  /**
   * Run cleanup script after agent session ends.
   */
  async postAgentCleanup(): Promise<[boolean, string]> {
    if (this._status !== 'running') {
      return [false, 'Container must be running for cleanup'];
    }

    try {
      await this._broadcastOutput('[System] Running session cleanup...');

      await execAsync(
        `docker exec -u coder ${this.containerName} /app/cleanup_session.sh`,
        { timeout: 120000 }
      );

      console.log(`Session cleanup completed for ${this.projectName}`);
      return [true, 'Session cleanup completed'];
    } catch (e) {
      console.warn(`Cleanup script error: ${e}`);
      return [false, `Cleanup error: ${e}`];
    }
  }

  /**
   * Reset any in_progress features to open (recovery after force-stop).
   */
  async recoverStuckFeatures(): Promise<[boolean, string]> {
    // TODO: Implement when BeadsSyncManager is converted
    return [true, 'No stuck features to recover'];
  }

  // ===========================================================================
  // Container Lifecycle Methods
  // ===========================================================================

  /**
   * Start or restart the container and optionally send an instruction.
   */
  async start(instruction?: string): Promise<[boolean, string]> {
    // Refresh prompts from templates before starting
    try {
      const updated = refreshProjectPrompts(this.projectDir);
      if (updated.length > 0) {
        console.log(`Refreshed prompts from templates: ${updated.join(', ')}`);
      }
    } catch (e) {
      console.warn(`Failed to refresh prompts: ${e}`);
    }

    this._syncStatus();

    // Check if graceful stop was requested
    if (this._gracefulStopRequested) {
      console.log(`Graceful stop requested, not starting ${this.containerName}`);
      return [false, 'Graceful stop requested'];
    }

    if (this._status === 'running') {
      if (instruction) {
        if (this._agentDispatched) {
          console.warn(`Agent already dispatched for ${this.containerName}, skipping duplicate start`);
          return [true, 'Agent already running'];
        }
        this._userStarted = true;
        this._agentDispatched = true;
        return this.sendInstruction(instruction);
      }
      return [true, 'Container already running'];
    }

    try {
      if (this._status === 'stopped') {
        // Restart existing container
        const { stderr } = await execAsync(`docker start ${this.containerName}`);
        if (stderr && stderr.includes('Error')) {
          return [false, `Failed to start container: ${stderr}`];
        }
        updateContainerStatus(this.projectName, this.containerNumber, this.containerType, {
          status: 'running',
        });
      } else {
        // Ensure Docker image exists
        const [imageOk, imageMsg] = await ensureImageExists();
        if (!imageOk) {
          return [false, imageMsg];
        }

        // Create new standalone container
        const cmd = [
          'docker', 'run', '-d',
          '--name', this.containerName,
          '--add-host', 'host.docker.internal:host-gateway',
          '--memory', '64g',
          '--memory-swap', '64g',
        ];

        // Pass environment variables
        cmd.push('-e', `GIT_REMOTE_URL=${this.gitUrl}`);
        cmd.push('-e', `CONTAINER_TYPE=${this._isInitContainer ? 'init' : 'coding'}`);
        cmd.push('-e', `PROJECT_NAME=${this.projectName}`);
        cmd.push('-e', `CONTAINER_NUMBER=${this.containerNumber}`);

        const serverPort = process.env['PORT'] || '8888';
        cmd.push('-e', `HOST_API_URL=http://host.docker.internal:${serverPort}`);

        // Pass API keys if available
        for (const envName of ['CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_API_KEY', 'ZHIPU_API_KEY', 'MINIMAX_API_KEY', 'TZ']) {
          const envValue = process.env[envName];
          if (envValue) {
            cmd.push('-e', `${envName}=${envValue}`);
          }
        }

        cmd.push(CONTAINER_IMAGE);

        const { stderr } = await execAsync(cmd.join(' '));
        if (stderr && stderr.includes('Error')) {
          return [false, `Failed to create container: ${stderr}`];
        }

        // Register in database
        createContainerRecord(this.projectName, this.containerNumber, this.containerType);

        // Get docker container ID
        try {
          const { stdout: dockerId } = await execAsync(
            `docker inspect --format "{{.Id}}" ${this.containerName}`
          );
          updateContainerStatus(this.projectName, this.containerNumber, this.containerType, {
            dockerContainerId: dockerId.trim(),
            status: 'running',
          });
        } catch {
          updateContainerStatus(this.projectName, this.containerNumber, this.containerType, {
            status: 'running',
          });
        }
      }

      this._startedAt = new Date();
      this._updateActivity();
      this.status = 'running';
      this._userStarted = true;

      // Start log streaming
      this._startLogStreaming();

      // Wait for git clone to complete
      for (let attempt = 0; attempt < 30; attempt++) {
        await this._sleep(2000);
        try {
          await execAsync(`docker exec -u coder ${this.containerName} test -e /project/.git`);
          console.log(`Container ${this.containerName}: repository cloned successfully`);
          break;
        } catch {
          console.log(`Waiting for git clone (attempt ${attempt + 1}/30)`);
          if (attempt === 29) {
            return [false, 'Repository clone failed or timed out'];
          }
        }
      }

      // Pre-agent sync
      const [syncOk, syncMsg] = await this.preAgentSync();
      if (!syncOk) {
        console.warn(`Pre-agent sync failed: ${syncMsg}`);
      }

      // Recovery
      const [recoveryOk, recoveryMsg] = await this.recoverStuckFeatures();
      if (!recoveryOk) {
        console.warn(`Feature recovery failed: ${recoveryMsg}`);
      }

      if (instruction) {
        // Wait for SDK to be ready
        const useOpencode = this._isOpenCodeModel() && !this._forceClaudeSdk;
        for (let attempt = 0; attempt < 10; attempt++) {
          await this._sleep(2000);
          try {
            if (useOpencode) {
              await execAsync(`docker exec -u coder ${this.containerName} test -f /app/dist/opencode_agent_app.js`);
            } else {
              await execAsync(`docker exec -u coder ${this.containerName} test -f /app/container_scripts_ts/dist/agent_app.js`);
            }
            break;
          } catch {
            const sdkName = useOpencode ? 'OpenCode SDK' : 'Claude SDK';
            console.log(`Waiting for ${sdkName} to be ready (attempt ${attempt + 1}/10)`);
            if (attempt === 9) {
              return [false, `${sdkName} not available in container after 20 seconds`];
            }
          }
        }

        if (this._agentDispatched) {
          console.warn(`Agent already dispatched for ${this.containerName}, skipping duplicate`);
          return [true, 'Agent already dispatched'];
        }
        this._agentDispatched = true;

        // Start agent in background (non-blocking)
        this._runAgentWithMonitoring(instruction);
        return [true, 'Container started and agent spawned'];
      }

      return [true, `Container ${this.containerName} started`];
    } catch (e) {
      console.error(`Failed to start container: ${e}`);
      return [false, `Failed to start container: ${e}`];
    }
  }

  /**
   * Stop the container (don't remove it).
   */
  async stop(preserveUserStarted = false): Promise<[boolean, string]> {
    console.log(`[STOP] Attempting to stop container ${this.containerName}`);
    this._syncStatus();

    if (this._status !== 'running') {
      console.warn(`[STOP] Container ${this.containerName} is not running, status: ${this._status}`);
      return [false, 'Container is not running'];
    }

    try {
      // Cancel log streaming
      if (this._logAbortController) {
        this._logAbortController.abort();
        this._logAbortController = null;
      }

      // Reset flags
      this._gracefulStopRequested = false;
      if (!preserveUserStarted) {
        this._userStarted = false;
      }

      // Clear verification state if needed
      if (this._lastAgentWasOverseer) {
        clearVerificationState(this.projectName);
      }

      console.log(`[STOP] Executing docker stop for ${this.containerName}`);
      await execAsync(`docker stop ${this.containerName}`, { timeout: 30000 });

      this._agentDispatched = false;
      this.status = 'stopped';
      updateContainerStatus(this.projectName, this.containerNumber, this.containerType, {
        status: 'stopped',
      });

      console.log(`[STOP] Successfully stopped ${this.containerName}`);
      return [true, `Container ${this.containerName} stopped`];
    } catch {
      // Force kill on timeout
      try {
        await execAsync(`docker kill ${this.containerName}`);
      } catch {
        // Ignore
      }
      this.status = 'stopped';
      updateContainerStatus(this.projectName, this.containerNumber, this.containerType, {
        status: 'stopped',
      });
      return [true, `Container ${this.containerName} killed (timeout)`];
    }
  }

  /**
   * Request graceful shutdown of agent after current session completes.
   */
  async gracefulStop(): Promise<[boolean, string]> {
    this._syncStatus();

    if (this._status !== 'running') {
      return [false, 'Container is not running'];
    }

    if (this._gracefulStopRequested) {
      return [true, 'Graceful stop already requested'];
    }

    try {
      this._gracefulStopRequested = true;
      console.log(`Graceful stop requested for ${this.containerName}`);
      await this._broadcastOutput('[System] Graceful stop requested, completing current session...');

      // Start monitoring with timeout
      this._monitorGracefulStop();

      return [true, 'Graceful stop requested'];
    } catch (e) {
      this._gracefulStopRequested = false;
      return [false, `Failed to request graceful stop: ${e}`];
    }
  }

  /**
   * Start the container without starting the agent.
   * Used for multi-container orchestration where agents are started separately.
   */
  async startContainerOnly(): Promise<[boolean, string]> {
    // Refresh prompts from templates before starting
    try {
      const updated = refreshProjectPrompts(this.projectDir);
      if (updated.length > 0) {
        console.log(`Refreshed prompts from templates: ${updated.join(', ')}`);
      }
    } catch (e) {
      console.warn(`Failed to refresh prompts: ${e}`);
    }

    this._syncStatus();

    if (this._status === 'running') {
      return [true, 'Container already running'];
    }

    try {
      if (this._status === 'stopped') {
        // Restart existing container
        const { stderr } = await execAsync(`docker start ${this.containerName}`);
        if (stderr && stderr.includes('Error')) {
          return [false, `Failed to start container: ${stderr}`];
        }
        updateContainerStatus(this.projectName, this.containerNumber, this.containerType, {
          status: 'running',
        });
      } else {
        // Ensure Docker image exists
        const [imageOk, imageMsg] = await ensureImageExists();
        if (!imageOk) {
          return [false, imageMsg];
        }

        // Create new standalone container
        const cmd = [
          'docker', 'run', '-d',
          '--name', this.containerName,
          '--add-host', 'host.docker.internal:host-gateway',
          '--memory', '64g',
          '--memory-swap', '64g',
        ];

        // Pass environment variables
        cmd.push('-e', `GIT_REMOTE_URL=${this.gitUrl}`);
        cmd.push('-e', `CONTAINER_TYPE=${this._isInitContainer ? 'init' : 'coding'}`);
        cmd.push('-e', `PROJECT_NAME=${this.projectName}`);
        cmd.push('-e', `CONTAINER_NUMBER=${this.containerNumber}`);

        const serverPort = process.env['PORT'] || '8888';
        cmd.push('-e', `HOST_API_URL=http://host.docker.internal:${serverPort}`);

        // Pass API keys if available
        for (const envName of ['CLAUDE_CODE_OAUTH_TOKEN', 'ANTHROPIC_API_KEY', 'ZHIPU_API_KEY', 'MINIMAX_API_KEY', 'TZ']) {
          const envValue = process.env[envName];
          if (envValue) {
            cmd.push('-e', `${envName}=${envValue}`);
          }
        }

        cmd.push(CONTAINER_IMAGE);

        const { stderr } = await execAsync(cmd.join(' '));
        if (stderr && stderr.includes('Error')) {
          return [false, `Failed to create container: ${stderr}`];
        }

        // Register in database
        createContainerRecord(this.projectName, this.containerNumber, this.containerType);

        // Get docker container ID
        try {
          const { stdout: dockerId } = await execAsync(
            `docker inspect --format "{{.Id}}" ${this.containerName}`
          );
          updateContainerStatus(this.projectName, this.containerNumber, this.containerType, {
            dockerContainerId: dockerId.trim(),
            status: 'running',
          });
        } catch {
          updateContainerStatus(this.projectName, this.containerNumber, this.containerType, {
            status: 'running',
          });
        }
      }

      this._startedAt = new Date();
      this._updateActivity();
      this.status = 'running';
      this._userStarted = true;

      // Start log streaming
      this._startLogStreaming();

      // Wait for git clone to complete
      for (let attempt = 0; attempt < 30; attempt++) {
        await this._sleep(2000);
        try {
          await execAsync(`docker exec -u coder ${this.containerName} test -e /project/.git`);
          console.log(`Container ${this.containerName}: repository cloned successfully`);
          break;
        } catch {
          console.log(`Waiting for git clone (attempt ${attempt + 1}/30)`);
          if (attempt === 29) {
            return [false, 'Repository clone failed or timed out'];
          }
        }
      }

      // Pre-agent sync
      const [syncOk, syncMsg] = await this.preAgentSync();
      if (!syncOk) {
        console.warn(`Pre-agent sync failed: ${syncMsg}`);
      }

      return [true, `Container ${this.containerName} started (agent not launched)`];
    } catch (e) {
      console.error(`Failed to start container: ${e}`);
      return [false, `Failed to start container: ${e}`];
    }
  }

  /**
   * Remove the container completely.
   */
  async remove(): Promise<[boolean, string]> {
    if (this._status === 'running') {
      await this.stop();
    }

    try {
      await execAsync(`docker rm ${this.containerName}`);
      this.status = 'not_created';
      return [true, `Container ${this.containerName} removed`];
    } catch (e) {
      const error = e as Error;
      if (!error.message.includes('No such container')) {
        return [false, `Failed to remove container: ${error.message}`];
      }
      this.status = 'not_created';
      return [true, `Container ${this.containerName} removed`];
    }
  }

  /**
   * Send an instruction to the agent.
   */
  async sendInstruction(instruction: string): Promise<[boolean, string]> {
    this._syncStatus();

    if (this._status !== 'running') {
      return [false, 'Container is not running'];
    }

    try {
      this._updateActivity();

      // Write prompt to temp file
      const promptFile = join(tmpdir(), `prompt-${Date.now()}.txt`);
      writeFileSync(promptFile, instruction, 'utf-8');

      try {
        const useOpencode = this._isOpenCodeModel() && !this._forceClaudeSdk;
        const model = this._forceClaudeSdk ? this._forcedModel : this._getAgentModel();

        let cmd: string[];
        if (useOpencode) {
          const agentType = this._currentAgentType;
          console.log(`Using OpenCode agent (${agentType}, model=${model}) for ${this.containerName}`);
          cmd = [
            'docker', 'exec', '-i', '-u', 'coder',
            '-e', `OPENCODE_AGENT_TYPE=${agentType}`,
            '-e', `AGENT_MODEL=${model}`,
            this.containerName,
            'node', '/app/dist/opencode_agent_app.js',
          ];
        } else {
          console.log(`Using Claude agent (model=${model}) for ${this.containerName}`);
          cmd = [
            'docker', 'exec', '-i', '-u', 'coder',
            '-e', `AGENT_MODEL=${model}`,
            this.containerName,
            'node', '/app/container_scripts_ts/dist/agent_app.js',
          ];
        }

        // Spawn process with stdin from file
        const exitCode = await this._runAgentProcess(cmd, promptFile);
        unlinkSync(promptFile);

        return this._handleAgentExit(exitCode);
      } catch (e) {
        try {
          unlinkSync(promptFile);
        } catch {
          // Ignore
        }
        throw e;
      }
    } catch (e) {
      console.error(`Failed to send instruction: ${e}`);
      return [false, `Failed to send instruction: ${e}`];
    }
  }

  /**
   * Restart the agent inside the container.
   */
  async restartAgent(): Promise<[boolean, string]> {
    if (this._gracefulStopRequested) {
      console.log(`Graceful stop requested, not restarting ${this.containerName}`);
      return [false, 'Graceful stop requested, not restarting'];
    }

    console.log(`Restarting agent in container ${this.containerName}`);

    this._restarting = true;
    try {
      await this.stop(true); // Preserve user_started

      // Read coding prompt
      const codingPromptPath = join(this.projectDir, 'prompts', 'coding_prompt.md');
      if (!existsSync(codingPromptPath)) {
        return [false, 'No coding_prompt.md found in project'];
      }

      const instruction = readFileSync(codingPromptPath, 'utf-8');

      this._lastAgentWasOverseer = false;
      this._currentAgentType = 'coder';
      this._forceClaudeSdk = false;

      let [success, message] = await this.start(instruction);

      if (!success) {
        // Fallback: remove and recreate container
        console.warn(`${this.containerName}: Restart failed (${message}), attempting full recreation`);
        await this.remove();
        [success, message] = await this.start(instruction);
      }

      return [success, message];
    } finally {
      this._restarting = false;
    }
  }

  /**
   * Restart the agent with the reviewer prompt.
   */
  async restartWithReviewer(featureId: string): Promise<[boolean, string]> {
    console.log(`Starting reviewer for feature ${featureId} in container ${this.containerName}`);

    this._restarting = true;
    try {
      await this.stop(true);

      let instruction: string;
      try {
        instruction = getReviewerPrompt(this.projectDir, featureId);
      } catch {
        console.warn(`No reviewer_prompt.md found, skipping review for ${featureId}`);
        setLastClosedFeature(this.projectName, this.containerNumber, null, this.containerType);
        return this.restartAgent();
      }

      this._currentAgentType = 'reviewer';
      this._lastAgentWasOverseer = false;
      this._forceClaudeSdk = false;

      return this.start(instruction);
    } finally {
      this._restarting = false;
    }
  }

  /**
   * Restart the agent with the overseer prompt.
   */
  async restartWithOverseer(): Promise<[boolean, string]> {
    console.log(`Starting overseer verification in container ${this.containerName}`);

    this._restarting = true;
    try {
      await this.stop(true);

      let instruction: string;
      try {
        instruction = getOverseerPrompt(this.projectDir);
      } catch {
        clearVerificationState(this.projectName);
        return [false, 'No overseer_prompt.md found in project or templates'];
      }

      this._lastAgentWasOverseer = true;
      this._isMilestoneOverseer = false;
      this._currentAgentType = 'overseer';
      this._forceClaudeSdk = false;

      const [success, message] = await this.start(instruction);
      if (!success) {
        clearVerificationState(this.projectName);
      }
      return [success, message];
    } catch (e) {
      clearVerificationState(this.projectName);
      throw e;
    } finally {
      this._restarting = false;
    }
  }

  /**
   * Get current status as a dictionary.
   */
  getStatusDict(): Record<string, unknown> {
    this._syncStatus();
    return {
      status: this.status,
      container_name: this.containerName,
      container_type: this.containerType,
      container_number: this.containerNumber,
      started_at: this._startedAt?.toISOString() || null,
      idle_seconds: this.getIdleSeconds(),
      agent_running: false, // Will be updated by async check
      user_started: this._userStarted,
      graceful_stop_requested: this._gracefulStopRequested,
      current_feature: this._currentFeature,
      agent_type: this._currentAgentType,
      sdk_type: this._forceClaudeSdk || !this._isOpenCodeModel() ? 'claude' : 'opencode',
    };
  }

  // ===========================================================================
  // Private Helper Methods
  // ===========================================================================

  private _sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  private _startLogStreaming(): void {
    this._logAbortController = new AbortController();
    const { signal } = this._logAbortController;

    const proc = spawn('docker', ['logs', '-f', '--tail', '0', this.containerName], {
      signal,
    });

    proc.stdout?.on('data', (data: Buffer) => {
      const lines = data.toString().split('\n');
      for (const line of lines) {
        if (line.trim()) {
          const sanitized = sanitizeOutput(line);
          this._updateActivity();
          this._broadcastOutput(sanitized);

          // Detect feature claim
          const claimMatch = sanitized.match(/Claimed ([\w]+-[\w]+),/) || sanitized.match(/Working on feature: ([\w]+-[\w]+)/);
          if (claimMatch?.[1]) {
            this._setCurrentFeature(claimMatch[1]);
          }

          // Detect feature close
          const closeMatch = sanitized.match(/bd close ([\w]+-[\w]+)/);
          if (closeMatch?.[1] && this._currentFeature === closeMatch[1]) {
            this._setCurrentFeature(null);
          }
        }
      }
    });

    proc.stderr?.on('data', (data: Buffer) => {
      const lines = data.toString().split('\n');
      for (const line of lines) {
        if (line.trim()) {
          this._broadcastOutput(sanitizeOutput(line));
        }
      }
    });
  }

  private async _runAgentProcess(cmd: string[], promptFile: string): Promise<number> {
    return new Promise((resolve) => {
      const command = cmd[0];
      if (!command) {
        resolve(1);
        return;
      }

      const proc = spawn(command, cmd.slice(1), {
        stdio: ['pipe', 'pipe', 'pipe'],
      });

      const promptContent = readFileSync(promptFile, 'utf-8');
      proc.stdin?.write(promptContent);
      proc.stdin?.end();

      proc.stdout?.on('data', () => {
        this._updateActivity();
      });

      proc.on('close', (code: number | null) => {
        resolve(code || 0);
      });

      proc.on('error', () => {
        resolve(1);
      });
    });
  }

  private async _runAgentWithMonitoring(instruction: string): Promise<void> {
    try {
      const [success, message] = await this.sendInstruction(instruction);
      if (!success) {
        console.error(`Agent instruction failed: ${message}`);
        await this._broadcastOutput(`[System] Agent failed: ${message}`);
      }
    } catch (e) {
      console.error(`Error running agent: ${e}`);
      await this._broadcastOutput(`[System] Agent error: ${e}`);
    }
  }

  private async _monitorGracefulStop(): Promise<void> {
    const timeoutMs = 20 * 60 * 1000; // 20 minutes
    const pollInterval = 5000;
    let elapsed = 0;

    while (elapsed < timeoutMs) {
      await this._sleep(pollInterval);
      elapsed += pollInterval;

      if (!(await this.isAgentRunning()) || this._status !== 'running') {
        console.log(`Agent stopped gracefully in ${this.containerName}`);
        return;
      }
    }

    console.warn(`Graceful stop timeout for ${this.containerName}, forcing shutdown`);
    await this._broadcastOutput('[System] Graceful stop timeout, forcing shutdown...');
    await this.stop();
  }

  private async _handleAgentExit(exitCode: number): Promise<[boolean, string]> {
    // If container already stopped, don't process
    if (this._status === 'stopped' || this._status === 'not_created') {
      console.log(`[EXIT] Ignoring exit code ${exitCode} for ${this.containerName} (status=${this._status})`);
      return [true, `Container already ${this._status}, ignoring exit`];
    }

    // Init containers never restart
    if (this._isInitContainer) {
      console.log(`Init container ${this.containerName} completed with exit code ${exitCode}`);
      await this._broadcastOutput(`[System] Init container completed (exit code: ${exitCode})`);
      await this.stop();
      return exitCode === 0
        ? [true, 'Init container completed successfully']
        : [false, `Init container failed with exit code ${exitCode}`];
    }

    // Handle context limit (exit code 131)
    if (exitCode === 131) {
      console.log(`Context limit reached in ${this.containerName}, restarting with fresh context...`);
      await this._broadcastOutput('[System] Context limit reached. Restarting with fresh context...');
      this._lastAgentWasOverseer = false;
      return this.restartAgent();
    }

    // Handle graceful stop (exit code 129 or flag)
    if (exitCode === 129 || this._gracefulStopRequested) {
      console.log(`Graceful stop completed for ${this.containerName}`);
      await this._broadcastOutput('[System] Graceful stop completed');
      this._gracefulStopRequested = false;
      await this.stop();
      return [true, 'Graceful stop completed'];
    }

    if (exitCode === 0) {
      console.log(`[EXIT] Agent exited successfully (code 0) in ${this.containerName}`);

      // Handle reviewer completion
      if (this._currentAgentType === 'reviewer') {
        setLastClosedFeature(this.projectName, this.containerNumber, null, this.containerType);
        console.log(`[REVIEWER] Review complete in ${this.containerName}, switching to coder`);
        this._currentAgentType = 'coder';
      }

      // Post-agent cleanup
      await this.postAgentCleanup();

      if (this.hasOpenFeatures() && !this._gracefulStopRequested) {
        // Check for reviewer first
        if (this._currentAgentType === 'coder') {
          const closedFeatureId = getLastClosedFeature(this.projectName, this.containerNumber, this.containerType);
          if (closedFeatureId) {
            console.log(`[EXIT] Running reviewer for ${closedFeatureId} in ${this.containerName}`);
            await this._broadcastOutput(`[System] Running review for ${closedFeatureId}...`);
            return this.restartWithReviewer(closedFeatureId);
          }
        }

        console.log(`[EXIT] Features remain in ${this.containerName}, restarting coding agent...`);
        await this._broadcastOutput('[System] Session complete. Starting fresh context for next task...');

        await this._checkOverseerMilestone();
        this._lastAgentWasOverseer = false;
        return this.restartAgent();
      } else if (!this.hasOpenFeatures() && !this._gracefulStopRequested) {
        if (this._lastAgentWasOverseer) {
          clearVerificationState(this.projectName);

          if (this._isMilestoneOverseer) {
            console.log(`Milestone overseer completed in ${this.containerName}`);
            await this._broadcastOutput('[System] Milestone verification complete.');
            await this.stop();
            this._isMilestoneOverseer = false;
            return [true, 'Milestone verification complete'];
          }

          if (this.hasOpenFeatures()) {
            console.log(`Overseer created new issues in ${this.projectName}, restarting containers...`);
            await this._broadcastOutput('[System] Verification found issues. Restarting to fix them...');
            await this._restartOtherContainers();
            this._lastAgentWasOverseer = false;
            return this.restartAgent();
          } else {
            console.log(`Verification complete in ${this.containerName}! All features verified.`);
            await this._broadcastOutput('[System] Verification complete! All features verified.');
            await this.stop();
            this.status = 'completed';
            await this._stopOtherContainers();
            return [true, 'All features verified complete'];
          }
        } else {
          if (setVerificationRunning(this.projectName, true)) {
            console.log(`All features closed in ${this.containerName}, running overseer verification...`);
            await this._broadcastOutput('[System] All features complete. Running final verification...');
            return this.restartWithOverseer();
          } else {
            console.log(`Verification already running for ${this.projectName}, stopping ${this.containerName}`);
            await this._broadcastOutput('[System] Verification running in another container. Waiting...');
            await this.stop();
            return [true, 'Stopped - verification running elsewhere'];
          }
        }
      }

      return [true, 'Instruction completed'];
    } else if (exitCode === 130) {
      console.log(`Agent interrupted in ${this.containerName}`);
      await this._broadcastOutput('[System] Agent interrupted by user');
      return [true, 'Agent interrupted'];
    } else {
      console.error(`Agent failed in ${this.containerName}: exit code ${exitCode}`);
      await this._broadcastOutput(`[System] Agent failed: exit code ${exitCode}`);

      if (this.hasOpenFeatures() && !this._gracefulStopRequested) {
        await this._broadcastOutput('[System] Auto-restarting after error...');
        await this._sleep(5000);
        this._lastAgentWasOverseer = false;
        return this.restartAgent();
      }

      return [false, `Agent failed: exit code ${exitCode}`];
    }
  }

  private async _checkOverseerMilestone(): Promise<void> {
    const stats = getCachedStats(this.projectName);
    if (!stats || (stats.total || 0) === 0) return;

    const percentage = stats.percentage || 0;
    const currentMilestone = Math.floor(percentage / 10) * 10;
    const lastMilestone = getOverseerMilestone(this.projectName);

    if (currentMilestone > lastMilestone && currentMilestone > 0 && currentMilestone < 100) {
      console.log(`[${this.projectName}] Hit ${currentMilestone}% milestone - spawning overseer`);
      await this._spawnOverseerAtMilestone(currentMilestone);
    }
  }

  private async _spawnOverseerAtMilestone(milestone: number): Promise<void> {
    updateOverseerMilestone(this.projectName, milestone);

    if (!setVerificationRunning(this.projectName, true)) {
      console.log(`[${this.projectName}] Overseer already running, skipping milestone trigger`);
      return;
    }

    try {
      await this._broadcastOutput(`[System] ${milestone}% milestone reached - running quality verification...`);

      const overseerManager = new ContainerManager(this.projectName, this.gitUrl, 0);
      overseerManager._currentAgentType = 'overseer';
      overseerManager._isMilestoneOverseer = true;
      overseerManager._lastAgentWasOverseer = true;
      overseerManager._userStarted = true;

      let prompt: string;
      try {
        prompt = getOverseerPrompt(this.projectDir);
      } catch {
        console.warn(`[${this.projectName}] No overseer prompt found, skipping milestone verification`);
        setVerificationRunning(this.projectName, false);
        return;
      }

      // Run in background (don't await)
      this._runMilestoneOverseer(overseerManager, prompt, milestone);
    } catch (e) {
      console.error(`[${this.projectName}] Failed to spawn overseer: ${e}`);
      setVerificationRunning(this.projectName, false);
    }
  }

  private async _runMilestoneOverseer(overseerManager: ContainerManager, prompt: string, milestone: number): Promise<void> {
    try {
      console.log(`[${this.projectName}] Starting milestone overseer at ${milestone}%`);
      const [success, message] = await overseerManager.start(prompt);
      if (!success) {
        console.warn(`[${this.projectName}] Milestone overseer failed to start: ${message}`);
      }
    } catch (e) {
      console.error(`[${this.projectName}] Milestone overseer error: ${e}`);
    } finally {
      if (overseerManager._status !== 'running') {
        clearVerificationState(this.projectName);
      }
    }
  }

  private async _stopOtherContainers(): Promise<void> {
    const allManagers = getAllContainerManagers(this.projectName);
    for (const manager of allManagers) {
      if (manager.containerNumber !== this.containerNumber && manager.status === 'running') {
        console.log(`Stopping ${manager.containerName} (project complete)`);
        await manager.stop();
        manager.status = 'completed';
      }
    }
  }

  private async _restartOtherContainers(): Promise<void> {
    const allManagers = getAllContainerManagers(this.projectName);
    for (const manager of allManagers) {
      if (manager.containerNumber !== this.containerNumber) {
        if (manager.status === 'stopped' && manager._userStarted) {
          console.log(`Restarting ${manager.containerName} (new issues to work on)`);
          manager._lastAgentWasOverseer = false;
          await manager.restartAgent();
        }
      }
    }
  }
}

// =============================================================================
// Global Manager Registry
// =============================================================================

const _managers: Map<string, Map<number, ContainerManager>> = new Map();
const _managersLock = new Mutex();

/**
 * Get or create a container manager for a project and container number.
 */
export async function getContainerManager(
  projectName: string,
  gitUrl: string,
  containerNumber: number = 1,
  projectDir?: string
): Promise<ContainerManager> {
  return _managersLock.runExclusive(() => {
    if (!_managers.has(projectName)) {
      _managers.set(projectName, new Map());
    }
    const projectManagers = _managers.get(projectName)!;
    if (!projectManagers.has(containerNumber)) {
      projectManagers.set(containerNumber, new ContainerManager(projectName, gitUrl, containerNumber, projectDir));
    }
    return projectManagers.get(containerNumber)!;
  });
}

/**
 * Get an existing container manager WITHOUT creating one.
 */
export function getExistingContainerManager(
  projectName: string,
  containerNumber: number = 1
): ContainerManager | null {
  const projectManagers = _managers.get(projectName);
  return projectManagers?.get(containerNumber) || null;
}

/**
 * Get all container managers for a project.
 */
export function getAllContainerManagers(projectName: string): ContainerManager[] {
  const projectManagers = _managers.get(projectName);
  return projectManagers ? Array.from(projectManagers.values()) : [];
}

/**
 * Get all managers across all projects.
 * Returns a Map of container info objects keyed by container name.
 */
export function getAllManagers(): Map<string, { projectName: string; containerNumber: number; status: AgentStatus }> {
  const result = new Map<string, { projectName: string; containerNumber: number; status: AgentStatus }>();
  for (const [projectName, projectManagers] of _managers) {
    for (const [containerNumber, manager] of projectManagers) {
      result.set(manager.containerName, {
        projectName,
        containerNumber,
        status: manager.status,
      });
    }
  }
  return result;
}

/**
 * Return list of project names that have at least one running container.
 */
export function getProjectsWithActiveContainers(): string[] {
  const activeProjects: Set<string> = new Set();
  for (const [projectName, containers] of _managers) {
    for (const manager of containers.values()) {
      if (manager.status === 'running') {
        activeProjects.add(projectName);
        break;
      }
    }
  }
  return Array.from(activeProjects);
}

/**
 * Get or create the init container manager for a project.
 */
export async function getInitContainerManager(
  projectName: string,
  gitUrl: string,
  projectDir?: string
): Promise<ContainerManager> {
  return getContainerManager(projectName, gitUrl, 0, projectDir);
}

/**
 * Clear cached container manager(s) for a project.
 */
export async function clearContainerManager(
  projectName: string,
  containerNumber?: number
): Promise<void> {
  await _managersLock.runExclusive(() => {
    if (!_managers.has(projectName)) return;

    if (containerNumber !== undefined) {
      _managers.get(projectName)?.delete(containerNumber);
    } else {
      _managers.delete(projectName);
    }
  });
}

// =============================================================================
// Health & Cleanup Functions
// =============================================================================

/**
 * Restore ContainerManager instances for existing containers on startup.
 */
export async function restoreManagersFromRegistry(): Promise<number> {
  let restored = 0;

  try {
    const containers = listContainers();

    for (const container of containers) {
      const { projectName, containerNumber, status, dockerContainerId, containerType } = container;

      if (status !== 'running' && status !== 'stopping') continue;

      const gitUrl = getProjectGitUrl(projectName);
      if (!gitUrl) {
        console.warn(`No git URL for project ${projectName}, skipping container restore`);
        continue;
      }

      const containerName =
        containerType === 'init' || containerNumber === 0
          ? `zerocoder-${projectName}-init`
          : `zerocoder-${projectName}-${containerNumber}`;

      let dockerExists = false;

      if (dockerContainerId) {
        try {
          await execAsync(`docker inspect ${dockerContainerId}`);
          dockerExists = true;
        } catch {
          // Not found
        }
      }

      if (!dockerExists) {
        try {
          await execAsync(`docker inspect ${containerName}`);
          dockerExists = true;
        } catch {
          // Not found
        }
      }

      if (dockerExists) {
        const manager = new ContainerManager(projectName, gitUrl, containerNumber);
        manager['_syncStatus']();

        await _managersLock.runExclusive(() => {
          if (!_managers.has(projectName)) {
            _managers.set(projectName, new Map());
          }
          _managers.get(projectName)!.set(containerNumber, manager);
        });

        restored++;
        console.log(`Restored container manager for ${containerName} (status: ${manager.status})`);
      } else {
        console.log(`Container ${containerName} no longer exists, updating registry`);
        const ct: ContainerType = (containerType === 'init' || containerType === 'coding') ? containerType : 'coding';
        updateContainerStatus(projectName, containerNumber, ct, {
          status: 'stopped',
        });
      }
    }
  } catch (e) {
    console.error(`Error restoring container managers: ${e}`);
  }

  return restored;
}

/**
 * Remove container DB entries that don't exist in Docker.
 */
export async function cleanupStaleContainers(): Promise<number> {
  const allContainers = listAllContainers();
  let cleaned = 0;

  for (const c of allContainers) {
    const { projectName, containerNumber, containerType = 'coding' } = c;
    const containerName =
      containerType === 'init' || containerNumber === 0
        ? `zerocoder-${projectName}-init`
        : `zerocoder-${projectName}-${containerNumber}`;

    try {
      await execAsync(`docker inspect ${containerName}`);
    } catch {
      // Container doesn't exist
      deleteContainerRecord(projectName, containerNumber, containerType as ContainerType);
      await clearContainerManager(projectName, containerNumber);
      console.log(`Removed stale container entry: ${containerName}`);
      cleaned++;
    }
  }

  return cleaned;
}

/**
 * Stop containers that have been idle for longer than the timeout.
 */
export async function cleanupIdleContainers(): Promise<string[]> {
  const stopped: string[] = [];

  for (const [, projectManagers] of _managers) {
    for (const manager of projectManagers.values()) {
      if (manager.status === 'running' && manager.isIdle()) {
        const [success] = await manager.stop();
        if (success) {
          stopped.push(manager.containerName);
          console.log(`Stopped idle container: ${manager.containerName}`);
        }
      }
    }
  }

  return stopped;
}

/**
 * Force remove ALL containers on server shutdown.
 */
export async function cleanupAllContainers(): Promise<void> {
  console.log('Force removing all containers on shutdown...');
  await stopOrphanedContainers();
  _managers.clear();
}

/**
 * Force remove any zerocoder-* containers not tracked in our registry.
 */
export async function stopOrphanedContainers(): Promise<void> {
  try {
    const { stdout } = await execAsync('docker ps -aq --filter "name=zerocoder-"');
    if (stdout.trim()) {
      const containerIds = stdout.trim().split('\n');
      for (const containerId of containerIds) {
        if (containerId) {
          console.log(`Force removing container: ${containerId}`);
          await execAsync(`docker rm -f ${containerId}`).catch(() => {});
        }
      }
    }
  } catch (e) {
    console.warn(`Error removing orphaned containers: ${e}`);
  }
}

/**
 * Check health of agents in user-started containers and restart if needed.
 */
export async function monitorAgentHealth(): Promise<string[]> {
  const restarted: string[] = [];

  for (const [, projectManagers] of _managers) {
    for (const manager of projectManagers.values()) {
      if (!manager.userStarted) continue;
      if (manager['_gracefulStopRequested']) continue;
      if (manager['_restarting']) continue;

      manager['_syncStatus']();

      if (manager.status === 'completed' || manager.status === 'not_created') continue;

      if (manager.status === 'stopped') {
        if (!manager.hasOpenFeatures()) {
          console.log(`Container ${manager.containerName} stopped, no open features - marking complete`);
          manager.status = 'completed';
          manager['_userStarted'] = false;
          continue;
        }

        console.warn(`Container ${manager.containerName} stopped unexpectedly, restarting...`);
        try {
          const [success] = await manager.start();
          if (success) {
            restarted.push(manager.containerName);
            console.log(`Successfully restarted container ${manager.containerName}`);
          }
        } catch (e) {
          console.error(`Error restarting container ${manager.containerName}: ${e}`);
        }
        continue;
      }

      if (manager.status === 'running' && !(await manager.isAgentRunning())) {
        console.warn(`Agent not running in ${manager.containerName}, restarting agent...`);
        try {
          const [success] = await manager.restartAgent();
          if (success) {
            restarted.push(manager.containerName);
          }
        } catch (e) {
          console.error(`Error restarting agent in ${manager.containerName}: ${e}`);
        }
        continue;
      }

      if (manager.status === 'running' && manager.isAgentStuck()) {
        console.warn(`Agent stuck in ${manager.containerName}, restarting agent...`);
        try {
          const [success] = await manager.restartAgent();
          if (success) {
            restarted.push(manager.containerName);
          }
        } catch (e) {
          console.error(`Error restarting stuck agent in ${manager.containerName}: ${e}`);
        }
      }
    }
  }

  return restarted;
}

// =============================================================================
// Background Monitor Loops
// =============================================================================

/** Idle container check interval in seconds (1 minute) */
const IDLE_CHECK_INTERVAL = 60;

/** AbortController for graceful shutdown of background monitors */
let _shutdownController: AbortController | null = null;

/**
 * Start the agent health monitoring loop.
 * Runs every 5 minutes to check for crashed/stuck agents and restart them.
 */
export async function startAgentHealthMonitor(): Promise<void> {
  console.log(`Starting agent health monitor (interval: ${AGENT_HEALTH_CHECK_INTERVAL}s)`);

  while (!_shutdownController?.signal.aborted) {
    try {
      // Sleep first, then check (matches Python behavior)
      await sleep(AGENT_HEALTH_CHECK_INTERVAL * 1000, _shutdownController?.signal);

      const restarted = await monitorAgentHealth();
      if (restarted.length > 0) {
        console.log(`Health check restarted agents: ${restarted.join(', ')}`);
      }
    } catch (error) {
      // AbortError means graceful shutdown
      if (error instanceof Error && error.name === 'AbortError') {
        console.log('Agent health monitor shutting down...');
        break;
      }
      console.error(`Error in agent health monitor: ${error}`);
    }
  }
}

/**
 * Start the idle container monitoring loop.
 * Runs every 60 seconds to stop containers idle for > 15 minutes.
 */
export async function startIdleContainerMonitor(): Promise<void> {
  console.log(`Starting idle container monitor (interval: ${IDLE_CHECK_INTERVAL}s, timeout: ${IDLE_TIMEOUT_MINUTES}m)`);

  while (!_shutdownController?.signal.aborted) {
    try {
      // Sleep first, then check
      await sleep(IDLE_CHECK_INTERVAL * 1000, _shutdownController?.signal);

      const stopped = await cleanupIdleContainers();
      if (stopped.length > 0) {
        console.log(`Idle monitor stopped containers: ${stopped.join(', ')}`);
      }
    } catch (error) {
      // AbortError means graceful shutdown
      if (error instanceof Error && error.name === 'AbortError') {
        console.log('Idle container monitor shutting down...');
        break;
      }
      console.error(`Error in idle container monitor: ${error}`);
    }
  }
}

/**
 * Sleep helper that respects abort signals for graceful shutdown.
 */
function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'));
      return;
    }

    const timeout = setTimeout(resolve, ms);

    signal?.addEventListener('abort', () => {
      clearTimeout(timeout);
      reject(new DOMException('Aborted', 'AbortError'));
    }, { once: true });
  });
}

/**
 * Initialize background monitors.
 * Call this when the server starts.
 */
export function initializeBackgroundMonitors(): void {
  _shutdownController = new AbortController();

  // Run remote machine checkup at startup (non-blocking)
  import('./remote-machine-manager.js')
    .then(({ checkupRemoteMachines }) => checkupRemoteMachines())
    .catch((err) => {
      console.error('Remote machine checkup failed:', err);
    });

  // Start both monitors (they run as background promises)
  startAgentHealthMonitor().catch((err) => {
    if (err?.name !== 'AbortError') {
      console.error('Agent health monitor failed:', err);
    }
  });

  startIdleContainerMonitor().catch((err) => {
    if (err?.name !== 'AbortError') {
      console.error('Idle container monitor failed:', err);
    }
  });
}

/**
 * Shutdown background monitors and cleanup all containers.
 * Call this on server shutdown (SIGINT/SIGTERM).
 */
export async function shutdownBackgroundMonitors(): Promise<void> {
  console.log('Shutting down background monitors...');

  // Signal all monitors to stop
  _shutdownController?.abort();

  // Give monitors a moment to clean up
  await new Promise((resolve) => setTimeout(resolve, 100));

  // Cleanup all containers
  await cleanupAllContainers();

  console.log('Background monitors shut down.');
}
