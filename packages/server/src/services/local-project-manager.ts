/**
 * Local Project Manager
 * =====================
 *
 * Manages local clones for projects used in:
 * - Spec creation wizard (new projects)
 * - Task editing (edit mode)
 *
 * Uses direct git clone stored at ~/.zerocoder/projects/{name}/
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import { existsSync, mkdirSync } from 'fs';
import { join } from 'path';
import { Mutex } from 'async-mutex';
import { getProjectsDir } from '../db/crud.js';

const execAsync = promisify(exec);

// =============================================================================
// Types
// =============================================================================

export interface TaskStats {
  open: number;
  in_progress: number;
  closed: number;
  total: number;
  percentage: number;
}

// Import BeadsTask type for internal use
import type { BeadsTask } from './beads-manager.js';

// =============================================================================
// LocalProjectManager Class
// =============================================================================

/**
 * Manages local clone for wizard and edit mode.
 */
export class LocalProjectManager {
  readonly projectName: string;
  readonly gitUrl: string;
  readonly localPath: string;

  constructor(projectName: string, gitUrl: string) {
    this.projectName = projectName;
    this.gitUrl = gitUrl;
    this.localPath = join(getProjectsDir(), projectName);
  }

  // ===========================================================================
  // Git Operations
  // ===========================================================================

  /**
   * Get the default branch name from remote.
   */
  private async getDefaultBranch(): Promise<string> {
    try {
      // Try to get from remote HEAD
      const { stdout } = await execAsync(
        `git -C "${this.localPath}" symbolic-ref refs/remotes/origin/HEAD`,
        { timeout: 10000 }
      );
      const ref = stdout.trim();
      if (ref) {
        return ref.split('/').pop() || 'main';
      }
    } catch {
      // Fall through to try common branch names
    }

    // Try common default branch names
    for (const branch of ['main', 'master', 'develop']) {
      try {
        await execAsync(
          `git -C "${this.localPath}" rev-parse --verify origin/${branch}`,
          { timeout: 10000 }
        );
        return branch;
      } catch {
        // Try next branch
      }
    }

    // Last resort: get first remote branch
    try {
      const { stdout } = await execAsync(
        `git -C "${this.localPath}" branch -r --list "origin/*"`,
        { timeout: 10000 }
      );
      const branches = stdout.trim().split('\n');
      if (branches.length > 0 && branches[0]) {
        let firstBranch = branches[0].trim();
        if (firstBranch.includes(' -> ')) {
          const parts = firstBranch.split(' -> ');
          if (parts[1]) {
            firstBranch = parts[1];
          }
        }
        return firstBranch.replace('origin/', '');
      }
    } catch {
      // Fall through to default
    }

    return 'main'; // Ultimate fallback
  }

  /**
   * Ensure the local clone exists for the project.
   *
   * @returns Tuple of [success, message]
   */
  async ensureCloned(): Promise<[boolean, string]> {
    // Check if already cloned
    if (existsSync(this.localPath) && existsSync(join(this.localPath, '.git'))) {
      return [true, 'Already cloned'];
    }

    try {
      // Create parent directory
      mkdirSync(this.localPath, { recursive: true });

      // Clone the repository
      const { stderr } = await execAsync(
        `git clone "${this.gitUrl}" "${this.localPath}"`,
        { timeout: 300000 } // 5 minute timeout for clone
      );

      if (stderr && !stderr.includes('Cloning into')) {
        // Some git versions output progress to stderr
        console.debug(`Clone output: ${stderr}`);
      }

      // Configure git user
      await execAsync(
        `git -C "${this.localPath}" config user.email "wizard@zerocoder.local"`,
        { timeout: 10000 }
      );
      await execAsync(
        `git -C "${this.localPath}" config user.name "ZeroCoder Wizard"`,
        { timeout: 10000 }
      );

      console.info(`Cloned ${this.projectName} to ${this.localPath}`);
      return [true, 'Cloned successfully'];
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.error(`Failed to clone ${this.projectName}: ${message}`);
      return [false, `Clone failed: ${message}`];
    }
  }

  /**
   * Pull latest changes from remote.
   *
   * @returns Tuple of [success, message]
   */
  async pullLatest(): Promise<[boolean, string]> {
    if (!existsSync(this.localPath)) {
      return this.ensureCloned();
    }

    try {
      const defaultBranch = await this.getDefaultBranch();

      // Fetch from origin
      try {
        await execAsync(
          `git -C "${this.localPath}" fetch origin`,
          { timeout: 60000 }
        );
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        console.warn(`Fetch failed: ${message}`);
      }

      // Reset to origin/default_branch
      await execAsync(
        `git -C "${this.localPath}" reset --hard origin/${defaultBranch}`,
        { timeout: 30000 }
      );

      return [true, 'Pulled successfully'];
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.warn(`Failed to pull latest for ${this.projectName}: ${message}`);
      return [false, `Pull error: ${message}`];
    }
  }

  /**
   * Sync beads state (run bd sync).
   *
   * @returns Tuple of [success, message]
   */
  async syncBeads(): Promise<[boolean, string]> {
    try {
      const { stderr } = await execAsync('bd sync', {
        cwd: this.localPath,
        timeout: 60000,
      });

      if (stderr && !stderr.includes('Already up to date')) {
        console.debug(`Beads sync stderr: ${stderr}`);
      }

      return [true, 'Synced successfully'];
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (message.includes('not found') || message.includes('ENOENT')) {
        return [false, 'beads CLI (bd) not found'];
      }
      console.warn(`Failed to sync beads for ${this.projectName}: ${message}`);
      return [false, `Sync error: ${message}`];
    }
  }

  /**
   * Push local changes to remote.
   *
   * @param message - Commit message
   * @returns Tuple of [success, message]
   */
  async pushChanges(message = 'Update tasks'): Promise<[boolean, string]> {
    try {
      const defaultBranch = await this.getDefaultBranch();

      // Add all changes
      await execAsync(
        `git -C "${this.localPath}" add .`,
        { timeout: 10000 }
      );

      // Check if there's anything to commit
      const { stdout: statusOutput } = await execAsync(
        `git -C "${this.localPath}" status --porcelain`,
        { timeout: 10000 }
      );

      if (statusOutput.trim()) {
        // There are changes to commit
        await execAsync(
          `git -C "${this.localPath}" commit -m "${message.replace(/"/g, '\\"')}"`,
          { timeout: 10000 }
        );
      }

      // Push
      await execAsync(
        `git -C "${this.localPath}" push origin ${defaultBranch}`,
        { timeout: 60000 }
      );

      // Sync beads (best effort)
      const [syncSuccess, syncMsg] = await this.syncBeads();
      if (!syncSuccess) {
        console.warn(`Beads sync failed after push: ${syncMsg}`);
        // Don't fail the whole operation if sync fails - changes are pushed
      }

      return [true, 'Changes pushed successfully'];
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      console.error(`Failed to push changes for ${this.projectName}: ${message}`);
      return [false, `Push error: ${message}`];
    }
  }

  // ===========================================================================
  // Task Management (Edit Mode)
  // ===========================================================================

  /**
   * Create a new task using bd create.
   *
   * @param title - Task title
   * @param description - Task description
   * @param priority - Priority (0-4)
   * @param taskType - Task type (feature, task, bug)
   * @returns Tuple of [success, message, taskId]
   */
  async createTask(
    title: string,
    description = '',
    priority = 2,
    taskType = 'feature'
  ): Promise<[boolean, string, string | null]> {
    try {
      const args = [
        'bd',
        'create',
        `--title="${title.replace(/"/g, '\\"')}"`,
        `--type=${taskType}`,
        `--priority=${priority}`,
      ];

      if (description) {
        args.push(`--description="${description.replace(/"/g, '\\"')}"`);
      }

      const { stdout } = await execAsync(args.join(' '), {
        cwd: this.localPath,
        timeout: 30000,
      });

      // Extract task ID from output (format: "Created beads-123")
      let taskId: string | null = null;
      const match = stdout.match(/(beads-\d+|\w+-\w+)/);
      if (match && match[1]) {
        taskId = match[1];
      }

      return [true, 'Task created', taskId];
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (message.includes('not found') || message.includes('ENOENT')) {
        return [false, 'beads CLI (bd) not found', null];
      }
      return [false, `Create error: ${message}`, null];
    }
  }

  /**
   * Update an existing task.
   *
   * @param taskId - Task ID (e.g., "beads-123")
   * @param status - New status (open, in_progress, closed)
   * @param priority - New priority (0-4)
   * @param title - New title
   * @returns Tuple of [success, message]
   */
  async updateTask(
    taskId: string,
    status?: string,
    priority?: number,
    title?: string
  ): Promise<[boolean, string]> {
    try {
      const args = ['bd', 'update', taskId];

      if (status) {
        args.push(`--status=${status}`);
      }
      if (priority !== undefined) {
        args.push(`--priority=${priority}`);
      }
      if (title) {
        args.push(`--title="${title.replace(/"/g, '\\"')}"`);
      }

      if (args.length === 3) {
        // No updates specified
        return [false, 'No updates specified'];
      }

      await execAsync(args.join(' '), {
        cwd: this.localPath,
        timeout: 30000,
      });

      return [true, 'Task updated'];
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (message.includes('not found') || message.includes('ENOENT')) {
        return [false, 'beads CLI (bd) not found'];
      }
      return [false, `Update error: ${message}`];
    }
  }

  /**
   * Delete a task.
   *
   * @param taskId - Task ID to delete
   * @returns Tuple of [success, message]
   */
  async deleteTask(taskId: string): Promise<[boolean, string]> {
    try {
      await execAsync(`bd delete ${taskId} --force`, {
        cwd: this.localPath,
        timeout: 30000,
      });

      return [true, 'Task deleted'];
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (message.includes('not found') || message.includes('ENOENT')) {
        return [false, 'beads CLI (bd) not found'];
      }
      return [false, `Delete error: ${message}`];
    }
  }

  /**
   * Close a task.
   *
   * @param taskId - Task ID to close
   * @param reason - Optional close reason
   * @returns Tuple of [success, message]
   */
  async closeTask(taskId: string, reason?: string): Promise<[boolean, string]> {
    try {
      let cmd = `bd close ${taskId}`;
      if (reason) {
        cmd += ` --reason="${reason.replace(/"/g, '\\"')}"`;
      }

      await execAsync(cmd, {
        cwd: this.localPath,
        timeout: 30000,
      });

      return [true, 'Task closed'];
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (message.includes('not found') || message.includes('ENOENT')) {
        return [false, 'beads CLI (bd) not found'];
      }
      return [false, `Close error: ${message}`];
    }
  }

  /**
   * Reopen a closed task.
   *
   * @param taskId - Task ID to reopen
   * @returns Tuple of [success, message]
   */
  async reopenTask(taskId: string): Promise<[boolean, string]> {
    try {
      await execAsync(`bd reopen ${taskId}`, {
        cwd: this.localPath,
        timeout: 30000,
      });

      return [true, 'Task reopened'];
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      if (message.includes('not found') || message.includes('ENOENT')) {
        return [false, 'beads CLI (bd) not found'];
      }
      return [false, `Reopen error: ${message}`];
    }
  }

  /**
   * Read tasks using bd CLI from local project directory.
   *
   * Uses bd list --json to query the SQLite database directly,
   * providing the authoritative source of truth.
   *
   * @returns List of task dictionaries
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
      const result = execSync('bd --no-daemon list --json --all --limit 0', {
        cwd: this.localPath,
        timeout: 30000,
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe'],
      });

      const stdout = result.trim();
      if (!stdout) {
        return [];
      }

      return JSON.parse(stdout) as BeadsTask[];
    } catch (error: unknown) {
      const err = error as { stderr?: string };
      console.debug(`bd list failed for ${this.projectName}:`, err.stderr || error);
      return [];
    }
  }

  /**
   * Get task statistics.
   *
   * @returns Task statistics
   */
  getStats(): TaskStats {
    const tasks = this.getTasks();
    const stats: TaskStats = {
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
}

// =============================================================================
// Global Registry
// =============================================================================

const projectManagers: Map<string, LocalProjectManager> = new Map();
const managersLock = new Mutex();

/**
 * Get or create a LocalProjectManager for a project.
 */
export async function getLocalProjectManager(
  projectName: string,
  gitUrl: string
): Promise<LocalProjectManager> {
  return managersLock.runExclusive(async () => {
    if (!projectManagers.has(projectName)) {
      projectManagers.set(projectName, new LocalProjectManager(projectName, gitUrl));
    }
    return projectManagers.get(projectName)!;
  });
}

/**
 * Get an existing LocalProjectManager for a project (synchronous).
 * Returns null if the manager doesn't exist yet.
 */
export function getLocalProjectManagerSync(projectName: string): LocalProjectManager | null {
  return projectManagers.get(projectName) ?? null;
}

/**
 * Clear cached LocalProjectManager for a project.
 */
export function clearLocalProjectManager(projectName: string): void {
  projectManagers.delete(projectName);
}

/**
 * Clear all cached LocalProjectManager instances.
 */
export function clearAllLocalProjectManagers(): void {
  projectManagers.clear();
}
