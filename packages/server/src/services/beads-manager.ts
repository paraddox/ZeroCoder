/**
 * Beads Manager
 * =============
 *
 * Unified manager for all beads operations. Reads directly from the project
 * directory's SQLite database via the `bd` CLI.
 *
 * Key design decisions:
 * - Single Mutex per project for all operations (read/write/sync)
 * - Reads use `bd list --json` for authoritative SQLite database access
 * - Writes go through bd CLI, acquire lock, and sync after
 * - Uses project directory directly (~/.zerocoder/projects/{name}/)
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import { existsSync, mkdirSync } from 'fs';
import { join } from 'path';
import { Mutex } from 'async-mutex';
import * as lockfile from 'proper-lockfile';
import { getProjectsDir, getProjectGitUrl, listValidProjects } from '../db/crud.js';

const execAsync = promisify(exec);

// =============================================================================
// Types
// =============================================================================

export interface BeadsTask {
  id: string;
  title: string;
  description?: string;
  body?: string;
  status: 'open' | 'in_progress' | 'closed';
  priority: number;
  labels: string[];
  assignee?: string;
  type?: string;
}

export interface BeadsStats {
  open: number;
  in_progress: number;
  closed: number;
  total: number;
  percentage: number;
}

export interface Feature {
  id: string;
  priority: number;
  category: string;
  name: string;
  description: string;
  steps: string[];
  passes: boolean;
  in_progress: boolean;
}

export interface FeatureStats {
  pending: number;
  in_progress: number;
  done: number;
  total: number;
  percentage: number;
}

interface CommandResult<T = unknown> {
  success?: boolean;
  data?: T;
  output?: string;
  error?: string;
}

// =============================================================================
// BeadsManager Class
// =============================================================================

/**
 * Unified manager for all beads operations on a single project.
 *
 * Handles:
 * - Read operations (via bd CLI from project directory)
 * - Write operations (bd CLI commands with locking)
 * - Sync operations (push changes to remote)
 *
 * Uses the project directory directly (~/.zerocoder/projects/{name}/).
 */
export class BeadsManager {
  readonly projectName: string;
  readonly gitRemoteUrl: string;
  readonly localPath: string;
  private readonly mutex: Mutex;
  private _lastPull: Date | null = null;

  /** Get last pull timestamp. */
  get lastPull(): Date | null {
    return this._lastPull;
  }

  constructor(projectName: string, gitRemoteUrl: string) {
    this.projectName = projectName;
    this.gitRemoteUrl = gitRemoteUrl;
    this.localPath = join(getProjectsDir(), projectName);
    this.mutex = new Mutex();
  }

  // ===========================================================================
  // File-Based Locking for Cross-Process Coordination
  // ===========================================================================

  private getLockPath(): string {
    return join(this.localPath, '.beads', '.sync.lock');
  }

  /**
   * Acquire file lock for cross-process coordination.
   *
   * Uses proper-lockfile for platform-agnostic file locking.
   * This prevents both host and container from running bd commands simultaneously.
   *
   * @returns Release function to unlock
   */
  private async acquireFileLock(): Promise<() => Promise<void>> {
    const lockPath = this.getLockPath();
    const lockDir = join(this.localPath, '.beads');

    // Ensure .beads directory exists
    if (!existsSync(lockDir)) {
      mkdirSync(lockDir, { recursive: true });
    }

    // Create lock file if it doesn't exist
    const fs = await import('fs/promises');
    if (!existsSync(lockPath)) {
      await fs.writeFile(lockPath, '', 'utf-8');
    }

    // Acquire lock with retry options
    const release = await lockfile.lock(lockPath, {
      retries: {
        retries: 10,
        factor: 1.5,
        minTimeout: 100,
        maxTimeout: 1000,
      },
      stale: 30000, // Consider lock stale after 30 seconds
    });

    return release;
  }

  // ===========================================================================
  // Project Directory Operations
  // ===========================================================================

  /**
   * Check if the project directory exists.
   *
   * LocalProjectManager handles cloning, so we just verify the path exists.
   *
   * @returns Tuple of [success, message]
   */
  async ensureProjectExists(): Promise<[boolean, string]> {
    if (existsSync(this.localPath) && existsSync(join(this.localPath, '.git'))) {
      return [true, 'Project exists'];
    }
    return [false, `Project directory not found: ${this.localPath}`];
  }

  /**
   * @deprecated Use ensureProjectExists() instead.
   */
  async ensureCloned(): Promise<[boolean, string]> {
    return this.ensureProjectExists();
  }

  /**
   * Pull latest from remote main branch.
   */
  async pullLatest(): Promise<[boolean, string]> {
    if (!existsSync(this.localPath)) {
      return [false, 'Project directory does not exist'];
    }

    return this.mutex.runExclusive(async () => {
      try {
        await execAsync('git pull --ff-only', {
          cwd: this.localPath,
          timeout: 30000,
        });
        this._lastPull = new Date();
        return [true, 'Pulled successfully'] as [boolean, string];
      } catch (error) {
        // Pull failed - log but don't error (project may have local changes)
        console.debug(`Git pull skipped for ${this.projectName}:`, error);
        return [true, 'Pull skipped (local changes or up-to-date)'] as [boolean, string];
      }
    });
  }

  // ===========================================================================
  // Read Operations - Via bd CLI (queries SQLite database)
  // ===========================================================================

  /**
   * Read tasks using bd CLI from local project directory.
   *
   * This queries the SQLite database directly via bd list --json,
   * providing the authoritative source of truth.
   */
  getTasks(): BeadsTask[] {
    if (!existsSync(this.localPath)) {
      return [];
    }

    const beadsDir = join(this.localPath, '.beads');
    if (!existsSync(beadsDir)) {
      return [];
    }

    try {
      const { execSync } = require('child_process');
      let result = execSync('bd --no-daemon list --json --all --limit 0', {
        cwd: this.localPath,
        timeout: 30000,
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe'],
      });

      const stdout = (result as string).trim();
      if (!stdout) {
        return [];
      }

      return JSON.parse(stdout) as BeadsTask[];
    } catch (error: unknown) {
      // Handle out of sync error - auto-recover
      const err = error as { stderr?: string; status?: number };
      if (err.stderr && err.stderr.toLowerCase().includes('out of sync')) {
        console.info(`Beads DB out of sync for ${this.projectName}, importing JSONL...`);
        try {
          const { execSync } = require('child_process');
          execSync('bd --no-daemon sync --import-only', {
            cwd: this.localPath,
            timeout: 30000,
            encoding: 'utf-8',
            stdio: ['pipe', 'pipe', 'pipe'],
          });

          const retryResult = execSync('bd --no-daemon list --json --all --limit 0', {
            cwd: this.localPath,
            timeout: 30000,
            encoding: 'utf-8',
            stdio: ['pipe', 'pipe', 'pipe'],
          });

          const stdout = (retryResult as string).trim();
          if (!stdout) {
            return [];
          }
          return JSON.parse(stdout) as BeadsTask[];
        } catch (syncError) {
          console.warn(`bd sync --import-only failed for ${this.projectName}:`, syncError);
          return [];
        }
      }

      console.debug(`bd list failed for ${this.projectName}:`, error);
      return [];
    }
  }

  /**
   * Calculate stats from local tasks.
   */
  getStats(): BeadsStats {
    const tasks = this.getTasks();
    const stats: BeadsStats = {
      open: 0,
      in_progress: 0,
      closed: 0,
      total: tasks.length,
      percentage: 0,
    };

    for (const task of tasks) {
      const status = task.status || 'open';
      if (status === 'open') {
        stats.open++;
      } else if (status === 'in_progress') {
        stats.in_progress++;
      } else if (status === 'closed') {
        stats.closed++;
      }
    }

    if (stats.total > 0) {
      stats.percentage = Math.round((stats.closed / stats.total) * 1000) / 10;
    }

    return stats;
  }

  /**
   * Get features in UI-compatible format.
   */
  getFeatures(): Feature[] {
    return tasksToFeatures(this.getTasks());
  }

  /**
   * Get tasks filtered by status.
   */
  getTasksByStatus(status: string): BeadsTask[] {
    return this.getTasks().filter((t) => t.status === status);
  }

  // ===========================================================================
  // Write Operations - via bd CLI (from BeadsAPI)
  // Acquires lock and syncs after
  // ===========================================================================

  /**
   * Low-level bd command runner with cross-process file locking.
   */
  private async runBd(args: string[], timeout = 60000, useFileLock = true): Promise<CommandResult> {
    let release: (() => Promise<void>) | null = null;

    try {
      // Acquire file lock for cross-process coordination
      if (useFileLock) {
        release = await this.acquireFileLock();
      }

      const { stdout } = await execAsync(`bd --no-daemon ${args.join(' ')}`, {
        cwd: this.localPath,
        timeout,
      });

      const output = stdout.trim();
      if (!output) {
        return { success: true, data: [] };
      }

      try {
        return { success: true, data: JSON.parse(output) };
      } catch {
        // Some commands return plain text
        return { success: true, output };
      }
    } catch (error: unknown) {
      const err = error as { stderr?: string; code?: number; message?: string };
      const errorMsg = err.stderr?.trim() || err.message || `Command failed`;

      // Don't log warning for "another sync in progress" - it's expected behavior
      if (!errorMsg.toLowerCase().includes('another sync is in progress')) {
        console.warn(`bd command failed: bd ${args.join(' ')} - ${errorMsg}`);
      }
      return { error: errorMsg };
    } finally {
      // Always release the file lock
      if (release) {
        try {
          await release();
        } catch (e) {
          console.warn('Error releasing file lock:', e);
        }
      }
    }
  }

  /**
   * Run bd sync to synchronize with git remote.
   *
   * This is best-effort - failures are logged but don't cause errors.
   * Called internally after write operations.
   */
  private async syncWithRemote(): Promise<boolean> {
    const result = await this.runBd(['sync'], 30000);
    if (result.error) {
      // "another sync is in progress" is not an error - just means we're already syncing
      if (result.error.toLowerCase().includes('another sync is in progress')) {
        console.debug(`bd sync skipped for ${this.projectName}: already in progress`);
        return true; // Consider this success - sync is happening
      }
      console.warn(`bd sync failed (best-effort): ${result.error}`);
      return false;
    }
    console.debug(`bd sync completed for ${this.projectName}`);
    return true;
  }

  /**
   * Sync beads with git remote.
   *
   * Acquires lock to prevent conflicts.
   */
  async sync(): Promise<[boolean, string]> {
    return this.mutex.runExclusive(async () => {
      const success = await this.syncWithRemote();
      if (success) {
        return [true, 'Synced successfully'] as [boolean, string];
      }
      return [false, 'Sync failed'] as [boolean, string];
    });
  }

  /**
   * Run a read command (no sync).
   *
   * Reads from local beads database. Background poller handles remote sync.
   */
  async runReadCommand(args: string[]): Promise<CommandResult> {
    if (!existsSync(this.localPath)) {
      return { error: `Project directory not found: ${this.localPath}` };
    }

    return this.mutex.runExclusive(async () => {
      return this.runBd(args);
    });
  }

  /**
   * Run a write command with project-level locking.
   *
   * Write operations (create, update, close, reopen) are serialized
   * per-project to avoid race conditions. Syncs AFTER the write to push changes.
   */
  async runWriteCommand(args: string[], skipLock = false): Promise<CommandResult> {
    if (!existsSync(this.localPath)) {
      return { error: `Project directory not found: ${this.localPath}` };
    }

    const doWrite = async (): Promise<CommandResult> => {
      // Run the write command
      const result = await this.runBd(args);

      // Sync after write to push changes to remote
      if (!result.error) {
        await this.syncWithRemote();
      }

      return result;
    };

    if (skipLock) {
      return doWrite();
    }
    return this.mutex.runExclusive(doWrite);
  }

  // ===========================================================================
  // High-level Write Operations
  // ===========================================================================

  /**
   * Create a new issue.
   */
  async createIssue(
    title: string,
    type = 'task',
    priority = 2,
    description = '',
    labels?: string[]
  ): Promise<CommandResult> {
    const args = ['create', '--title', `"${title.replace(/"/g, '\\"')}"`, '--type', type, '--priority', `P${priority}`, '--json'];

    if (description) {
      args.push('--description', `"${description.replace(/"/g, '\\"')}"`);
    }

    if (labels && labels.length > 0) {
      args.push('--labels', labels.join(','));
    }

    return this.runWriteCommand(args);
  }

  /**
   * Update an issue's fields.
   */
  async updateIssue(
    issueId: string,
    updates: {
      title?: string;
      description?: string;
      status?: string;
      priority?: number;
      assignee?: string;
    }
  ): Promise<CommandResult> {
    const args = ['update', issueId];

    if (updates.title !== undefined) {
      args.push('--title', `"${updates.title.replace(/"/g, '\\"')}"`);
    }
    if (updates.description !== undefined) {
      args.push('--description', `"${updates.description.replace(/"/g, '\\"')}"`);
    }
    if (updates.status !== undefined) {
      args.push('--status', updates.status);
    }
    if (updates.priority !== undefined) {
      args.push('--priority', `P${updates.priority}`);
    }
    if (updates.assignee !== undefined) {
      args.push('--assignee', updates.assignee);
    }

    // Must have at least one update
    if (args.length === 2) {
      return { error: 'No update fields provided' };
    }

    return this.runWriteCommand(args);
  }

  /**
   * Close an issue.
   */
  async closeIssue(issueId: string, reason?: string): Promise<CommandResult> {
    const args = ['close', issueId];
    if (reason) {
      args.push('--reason', `"${reason.replace(/"/g, '\\"')}"`);
    }
    return this.runWriteCommand(args);
  }

  /**
   * Reopen a closed issue.
   */
  async reopenIssue(issueId: string): Promise<CommandResult> {
    return this.runWriteCommand(['reopen', issueId]);
  }

  /**
   * Add a dependency between issues.
   */
  async addDependency(issueId: string, dependsOn: string): Promise<CommandResult> {
    return this.runWriteCommand(['dep', 'add', issueId, dependsOn]);
  }

  /**
   * Add a comment to an issue.
   */
  async addComment(issueId: string, comment: string): Promise<CommandResult> {
    return this.runWriteCommand(['comments', 'add', issueId, `"${comment.replace(/"/g, '\\"')}"`]);
  }

  /**
   * Delete an issue.
   */
  async deleteIssue(issueId: string): Promise<CommandResult> {
    return this.runWriteCommand(['delete', issueId, '--force']);
  }

  // ===========================================================================
  // Feature-Level Operations (for UI compatibility)
  // ===========================================================================

  /**
   * Get a single feature by ID.
   */
  getFeature(featureId: string): Feature | null {
    const tasks = this.getTasks();
    for (const task of tasks) {
      if (String(task.id) === String(featureId)) {
        return taskToFeature(task);
      }
    }
    return null;
  }

  /**
   * Create a new feature.
   */
  async createFeature(
    name: string,
    category = '',
    description = '',
    steps?: string[],
    priority = 999
  ): Promise<Feature | null> {
    // Build full description with steps if provided
    let fullDescription = description;
    if (steps && steps.length > 0) {
      const stepText = steps.map((step, i) => `${i + 1}. ${step}`).join('\n');
      if (description) {
        fullDescription = `${description}\n\n${stepText}`;
      } else {
        fullDescription = stepText;
      }
    }

    const labels = category ? [category] : undefined;

    const result = await this.createIssue(name, 'feature', priority, fullDescription, labels);

    if (result.error) {
      console.warn(`Failed to create feature: ${result.error}`);
      return null;
    }

    // Extract created issue ID from result
    const data = result.data as Record<string, unknown> | undefined;
    if (data && typeof data === 'object') {
      const issueId = data.id as string | undefined;
      if (issueId) {
        return this.getFeature(issueId);
      }
    }

    // Fallback: get the most recently created feature with this name
    const tasks = this.getTasks();
    for (const task of tasks) {
      if (task.title === name) {
        return taskToFeature(task);
      }
    }

    return null;
  }

  /**
   * Update a feature's fields.
   */
  async updateFeature(
    featureId: string,
    updates: {
      name?: string;
      description?: string;
      priority?: number;
      category?: string;
      steps?: string[];
    }
  ): Promise<Feature | null> {
    // Get current feature to merge with updates
    const current = this.getFeature(featureId);
    if (!current) {
      return null;
    }

    // Build full description with steps if provided
    let finalDescription = updates.description;
    if (updates.steps !== undefined) {
      const stepText = updates.steps.map((step, i) => `${i + 1}. ${step}`).join('\n');
      const baseDesc = updates.description ?? '';
      if (baseDesc) {
        finalDescription = `${baseDesc}\n\n${stepText}`;
      } else {
        finalDescription = stepText;
      }
    }

    // Update via beads CLI
    const result = await this.updateIssue(featureId, {
      title: updates.name,
      description: finalDescription,
      priority: updates.priority,
    });

    if (result.error) {
      console.warn(`Failed to update feature: ${result.error}`);
      return null;
    }

    // Handle category/label update separately if needed
    if (updates.category !== undefined) {
      await this.runWriteCommand(['label', featureId, '--set', updates.category]);
    }

    return this.getFeature(featureId);
  }

  /**
   * Delete a feature.
   */
  async deleteFeature(featureId: string): Promise<boolean> {
    const result = await this.deleteIssue(featureId);
    return !result.error;
  }

  /**
   * Skip a feature by setting its priority to P4 (backlog).
   */
  async skipFeature(featureId: string): Promise<{ success?: boolean; message?: string; error?: string } | null> {
    // Verify feature exists
    const feature = this.getFeature(featureId);
    if (!feature) {
      return null;
    }

    const result = await this.updateIssue(featureId, { priority: 4 });
    if (result.error) {
      return { error: result.error };
    }

    return { success: true, message: `Feature ${featureId} moved to backlog` };
  }

  /**
   * Reopen a closed feature.
   */
  async reopenFeature(featureId: string): Promise<Feature | null> {
    const result = await this.reopenIssue(featureId);
    if (result.error) {
      return null;
    }
    return this.getFeature(featureId);
  }
}

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Convert a single beads task to feature format for UI compatibility.
 */
function taskToFeature(task: BeadsTask): Feature {
  // Extract category from labels (first label)
  const labels = task.labels || [];
  const category = labels[0] || '';

  // Parse steps from description if available
  const description = task.description || task.body || '';
  let steps: string[] = [];
  if (description) {
    const stepMatches = description.match(/^\d+\.\s*(.+)$/gm);
    if (stepMatches) {
      steps = stepMatches.map((m) => m.replace(/^\d+\.\s*/, ''));
    }
  }

  const status = task.status || 'open';

  return {
    id: task.id || '',
    priority: task.priority ?? 999,
    category,
    name: task.title || '',
    description,
    steps,
    passes: status === 'closed',
    in_progress: status === 'in_progress',
  };
}

/**
 * Convert beads tasks to feature format for UI compatibility.
 */
function tasksToFeatures(tasks: BeadsTask[]): Feature[] {
  return tasks.map(taskToFeature);
}

// =============================================================================
// Global Manager Registry
// =============================================================================

const managers: Map<string, BeadsManager> = new Map();
const managersLock = new Mutex();

/**
 * Get or create a BeadsManager for a project.
 *
 * @throws Error if git_url not provided and manager doesn't exist
 */
export async function getBeadsManager(projectName: string, gitUrl?: string): Promise<BeadsManager> {
  return managersLock.runExclusive(async () => {
    if (!managers.has(projectName)) {
      let url = gitUrl;
      if (!url) {
        // Try to get git_url from registry
        url = getProjectGitUrl(projectName) ?? undefined;
      }

      if (!url) {
        throw new Error(`No git URL available for project ${projectName}`);
      }

      managers.set(projectName, new BeadsManager(projectName, url));
    }
    return managers.get(projectName)!;
  });
}

/**
 * Get an existing BeadsManager for a project (synchronous, no creation).
 *
 * This is for use in synchronous contexts that need to read cached data.
 * Returns null if the manager doesn't exist yet.
 */
export function getBeadsManagerSync(projectName: string): BeadsManager | null {
  return managers.get(projectName) ?? null;
}

/**
 * Clear cached BeadsManager for a project.
 */
export function clearBeadsManager(projectName: string): void {
  managers.delete(projectName);
}

// =============================================================================
// Convenience Functions (API-compatible with BeadsSyncManager)
// =============================================================================

/**
 * Get stats for a project from the local project directory.
 *
 * This is a convenience function for use by progress.ts and other modules
 * that don't have the git_url handy.
 */
export function getCachedStats(projectName: string): FeatureStats {
  let manager = getBeadsManagerSync(projectName);

  if (!manager) {
    // Try to create one from registry
    try {
      const gitUrl = getProjectGitUrl(projectName);
      if (gitUrl) {
        manager = new BeadsManager(projectName, gitUrl);
        managers.set(projectName, manager);
      }
    } catch (e) {
      console.debug(`Failed to get stats for ${projectName}:`, e);
    }
  }

  if (manager) {
    const stats = manager.getStats();
    return {
      pending: stats.open,
      in_progress: stats.in_progress,
      done: stats.closed,
      total: stats.total,
      percentage: stats.percentage,
    };
  }

  return { pending: 0, in_progress: 0, done: 0, total: 0, percentage: 0 };
}

/**
 * Get features for a project from the local project directory.
 *
 * This is a convenience function for use by progress.ts and other modules.
 */
export function getCachedFeatures(projectName: string): Feature[] {
  let manager = getBeadsManagerSync(projectName);

  if (!manager) {
    // Try to create one from registry
    try {
      const gitUrl = getProjectGitUrl(projectName);
      if (gitUrl) {
        manager = new BeadsManager(projectName, gitUrl);
        managers.set(projectName, manager);
      }
    } catch (e) {
      console.debug(`Failed to get features for ${projectName}:`, e);
    }
  }

  return manager?.getFeatures() ?? [];
}

// =============================================================================
// Initialization and Background Polling
// =============================================================================

/**
 * Initialize BeadsManagers for all registered projects on server startup.
 *
 * This creates manager instances for all projects that have local clones.
 * LocalProjectManager handles actual cloning - we just verify paths exist.
 */
export async function initializeAllProjects(): Promise<Map<string, boolean>> {
  const results = new Map<string, boolean>();
  const projects = listValidProjects();
  console.info(`Initializing beads managers for ${projects.length} registered projects`);

  for (const project of projects) {
    const gitUrl = getProjectGitUrl(project.name);
    if (gitUrl) {
      const manager = await getBeadsManager(project.name, gitUrl);
      const [success, message] = await manager.ensureProjectExists();
      results.set(project.name, success);
      if (success) {
        console.debug(`Beads manager initialized for ${project.name}: ${message}`);
      } else {
        console.info(`Beads manager init for ${project.name}: ${message}`);
      }
    } else {
      console.debug(`Skipping ${project.name}: no git URL`);
    }
  }

  const successes = Array.from(results.values()).filter((v) => v).length;
  console.info(`Beads manager initialization complete: ${successes}/${results.size} successful`);
  return results;
}

/**
 * Sync beads for projects with active containers.
 *
 * This is now a lightweight operation since we read directly from
 * the project directory's SQLite database.
 */
export async function pullAllBeadsSync(): Promise<Map<string, boolean>> {
  // Import dynamically to avoid circular dependencies
  const { getProjectsWithActiveContainers } = await import('./container-manager.js');

  const activeProjects = getProjectsWithActiveContainers();
  if (activeProjects.length === 0) {
    return new Map();
  }

  const results = new Map<string, boolean>();
  for (const projectName of activeProjects) {
    const manager = getBeadsManagerSync(projectName);
    if (manager) {
      // Just run bd sync to push any local changes
      const success = await manager['syncWithRemote']();
      results.set(projectName, success);
    }
  }

  return results;
}

// Background polling task intervals
const POLL_INTERVAL_IDLE = 30000; // 30 seconds when no containers running
const POLL_INTERVAL_ACTIVE = 10000; // 10 seconds when containers are running

/**
 * Check if any containers are running.
 */
async function hasRunningContainers(): Promise<boolean> {
  try {
    const { getAllManagers } = await import('./container-manager.js');
    const allManagers = getAllManagers();
    return Array.from(allManagers.values()).some((m) => m.status === 'running');
  } catch {
    return false;
  }
}

/**
 * Start a background task that syncs beads for active projects.
 *
 * Since we now read directly from the project directory, this is mainly
 * for pushing local changes to remote (bd sync).
 *
 * Uses dynamic polling interval:
 * - 10 seconds when containers are running (for faster sync)
 * - 30 seconds when idle (to reduce resource usage)
 *
 * This should be called when the server starts.
 */
export async function startBeadsSyncPoller(): Promise<void> {
  console.info(`Starting beads sync poller (idle: ${POLL_INTERVAL_IDLE / 1000}s, active: ${POLL_INTERVAL_ACTIVE / 1000}s)`);

  const poll = async () => {
    try {
      const hasContainers = await hasRunningContainers();
      const interval = hasContainers ? POLL_INTERVAL_ACTIVE : POLL_INTERVAL_IDLE;

      const results = await pullAllBeadsSync();
      if (results.size > 0) {
        const successes = Array.from(results.values()).filter((v) => v).length;
        console.debug(`Beads sync poll: ${successes}/${results.size} successful (interval: ${interval / 1000}s)`);
      }

      // Schedule next poll
      setTimeout(poll, interval);
    } catch (error) {
      console.error('Error in beads sync poller:', error);
      // Continue polling even on error
      setTimeout(poll, POLL_INTERVAL_IDLE);
    }
  };

  // Start the polling loop
  setTimeout(poll, POLL_INTERVAL_ACTIVE);
}

// =============================================================================
// Backwards Compatibility Aliases
// =============================================================================

/**
 * Backwards compatibility: Get a BeadsManager.
 *
 * This is a synchronous wrapper that creates the manager if needed.
 * Use getBeadsManager() for async contexts.
 */
export function getBeadsSyncManager(projectName: string, gitRemoteUrl: string): BeadsManager {
  if (!managers.has(projectName)) {
    managers.set(projectName, new BeadsManager(projectName, gitRemoteUrl));
  }
  return managers.get(projectName)!;
}
