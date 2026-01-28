/**
 * Task Cleanup Service
 * ====================
 *
 * Handles cleanup of stale task states on server startup.
 * Reverts all in_progress tasks to open for all registered projects.
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import { existsSync } from 'fs';
import { join } from 'path';
import { listValidProjects, getProjectsDir } from '../db/crud.js';

const execAsync = promisify(exec);

interface BdCommandResult {
  success?: boolean;
  data?: unknown;
  output?: string;
  error?: string;
}

interface BeadsTask {
  id: string;
  title: string;
  status: 'open' | 'in_progress' | 'closed';
  priority: number;
  labels: string[];
}

/**
 * Run bd command in project directory.
 */
async function runBd(projectPath: string, args: string[], timeout = 60000): Promise<BdCommandResult> {
  try {
    const { stdout, stderr } = await execAsync(`bd --no-daemon ${args.join(' ')}`, {
      cwd: projectPath,
      timeout,
    });

    if (stderr && stderr.trim()) {
      return { error: stderr.trim() };
    }

    const output = stdout.trim();
    if (!output) {
      return { success: true };
    }

    try {
      return { success: true, data: JSON.parse(output) };
    } catch {
      return { success: true, output };
    }
  } catch (error: unknown) {
    const err = error as { stderr?: string; message?: string };
    return { error: err.stderr?.trim() || err.message || 'Command failed' };
  }
}

/**
 * Revert all in_progress tasks to open for a single project.
 * Returns number of tasks reverted.
 */
export async function revertInProgressTasksForProject(projectName: string, projectPath: string): Promise<number> {
  // Get all in_progress tasks
  const result = await runBd(projectPath, ['list', '--json', '--status', 'in_progress']);
  if (result.error) {
    console.warn(`Failed to list in_progress tasks for ${projectName}: ${result.error}`);
    return 0;
  }

  const tasks = (result.data as BeadsTask[]) || [];
  if (!tasks || tasks.length === 0) {
    return 0;
  }

  let reverted = 0;
  for (const task of tasks) {
    const taskId = task.id;
    if (!taskId) {
      continue;
    }

    // Revert to open status
    const updateResult = await runBd(projectPath, ['update', taskId, '--status=open']);
    if (!updateResult.error) {
      reverted++;
      console.debug(`Reverted ${taskId} to open in ${projectName}`);
    } else {
      console.warn(`Failed to revert ${taskId}: ${updateResult.error}`);
    }
  }

  // Sync after changes
  if (reverted > 0) {
    await runBd(projectPath, ['sync']);
  }

  return reverted;
}

/**
 * Revert all in_progress tasks to open for all registered projects.
 * Called on server startup.
 * Returns dict of project_name -> tasks_reverted.
 */
export async function revertAllInProgressTasks(): Promise<Record<string, number>> {
  const results: Record<string, number> = {};
  const projects = listValidProjects();
  const projectsDir = getProjectsDir();

  if (!projects || projects.length === 0) {
    return results;
  }

  console.info(`Checking ${projects.length} projects for stale in_progress tasks...`);

  for (const project of projects) {
    const projectName = project.name;
    const projectPath = join(projectsDir, projectName);

    if (!existsSync(projectPath)) {
      continue;
    }

    // Check if .beads directory exists
    const beadsDir = join(projectPath, '.beads');
    if (!existsSync(beadsDir)) {
      continue;
    }

    const reverted = await revertInProgressTasksForProject(projectName, projectPath);
    if (reverted > 0) {
      results[projectName] = reverted;
    }
  }

  if (Object.keys(results).length > 0) {
    const total = Object.values(results).reduce((sum, count) => sum + count, 0);
    const projectCount = Object.keys(results).length;
    console.info(`Reverted ${total} in_progress tasks to open across ${projectCount} projects`);
  }

  return results;
}
