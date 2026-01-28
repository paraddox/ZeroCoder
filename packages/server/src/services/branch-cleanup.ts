/**
 * Branch Cleanup Service
 * ======================
 *
 * Cleans up remote feature branches on server startup.
 */

import { exec } from 'child_process';
import { promisify } from 'util';
import { existsSync } from 'fs';
import { listRegisteredProjects, getProjectPath, getProjectGitUrl } from '../db/crud.js';

const execAsync = promisify(exec);

const FEATURE_BRANCH_PREFIX = 'feature/';

/**
 * Execute git command in project directory.
 */
async function runGit(workDir: string, args: string[], timeout = 30000): Promise<{ stdout: string; stderr: string }> {
  const { stdout, stderr } = await execAsync(`git ${args.join(' ')}`, {
    cwd: workDir,
    timeout,
  });
  return { stdout, stderr };
}

/**
 * Delete all remote feature branches for a project.
 * Uses the local project path.
 *
 * Returns number of branches deleted.
 */
export async function cleanupRemoteBranchesForProject(projectName: string, localPath: string): Promise<number> {
  if (!existsSync(localPath)) {
    console.warn(`No local clone found for ${projectName}`);
    return 0;
  }

  try {
    // Fetch to get current remote state
    await runGit(localPath, ['fetch', '--prune', 'origin'], 60000);

    // List remote branches
    const { stdout } = await runGit(localPath, ['branch', '-r', '--format=%(refname:short)'], 30000);

    // Find branches to delete
    const branchesToDelete: string[] = [];
    for (const line of stdout.trim().split('\n')) {
      if (!line) {
        continue;
      }
      const branch = line.replace('origin/', '').trim();
      if (branch && branch.startsWith(FEATURE_BRANCH_PREFIX)) {
        branchesToDelete.push(branch);
      }
    }

    if (branchesToDelete.length === 0) {
      return 0;
    }

    // Delete from remote
    let deleted = 0;
    for (const branch of branchesToDelete) {
      try {
        await runGit(localPath, ['push', 'origin', '--delete', branch], 30000);
        deleted++;
        console.info(`Deleted remote branch ${branch} from ${projectName}`);
      } catch (error) {
        console.warn(`Failed to delete branch ${branch} from ${projectName}:`, error);
      }
    }

    return deleted;
  } catch (error) {
    console.warn(`Error cleaning branches for ${projectName}:`, error);
    return 0;
  }
}

/**
 * Clean up remote feature branches for all registered projects.
 * Called on server startup.
 *
 * Returns dict of project_name -> branches_deleted.
 */
export async function cleanupAllRemoteBranches(): Promise<Record<string, number>> {
  const results: Record<string, number> = {};
  const projects = listRegisteredProjects();

  const projectNames = Object.keys(projects);
  if (projectNames.length === 0) {
    return results;
  }

  console.info(`Cleaning up remote feature branches for ${projectNames.length} projects...`);

  for (const name of projectNames) {
    const gitUrl = getProjectGitUrl(name);
    const localPath = getProjectPath(name);

    if (!gitUrl || !localPath) {
      continue;
    }

    const deleted = await cleanupRemoteBranchesForProject(name, localPath);
    if (deleted > 0) {
      results[name] = deleted;
    }
  }

  if (Object.keys(results).length > 0) {
    const total = Object.values(results).reduce((sum, count) => sum + count, 0);
    const projectCount = Object.keys(results).length;
    console.info(`Cleaned up ${total} remote feature branches across ${projectCount} projects`);
  }

  return results;
}
