/**
 * Repository Manager Service
 * ==========================
 *
 * Handles git clone/pull operations and SSH key setup per repository.
 */

import { exec } from 'node:child_process';
import { promisify } from 'node:util';
import { existsSync, mkdirSync, writeFileSync, chmodSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { homedir } from 'node:os';

import { getConfig } from '../utils/config.js';
import { createLogger } from '../utils/logger.js';

const execAsync = promisify(exec);
const log = createLogger('repo-manager');

export interface RepoSetupResult {
  success: boolean;
  message: string;
  projectPath?: string;
}

/**
 * Get the path to the SSH key file for a project.
 * Falls back to default id_ed25519 key if project-specific key doesn't exist.
 */
function getSshKeyPath(projectName: string): string {
  const projectKey = join(homedir(), '.ssh', `zerocoder_${projectName}`);
  if (existsSync(projectKey)) {
    return projectKey;
  }
  // Fall back to default key (used in Docker containers)
  const defaultKey = join(homedir(), '.ssh', 'id_ed25519');
  if (existsSync(defaultKey)) {
    return defaultKey;
  }
  return projectKey; // Return project key path even if it doesn't exist
}

/**
 * Get the project workspace directory.
 */
export function getProjectPath(projectName: string): string {
  const config = getConfig();
  return join(config.workspaceDir, projectName);
}

/**
 * Set up the SSH key for a repository.
 * Saves the key to ~/.ssh/zerocoder_{project} with mode 600.
 */
async function setupSshKey(projectName: string, sshKey: string): Promise<void> {
  const keyPath = getSshKeyPath(projectName);
  const sshDir = dirname(keyPath);

  // Ensure ~/.ssh exists
  if (!existsSync(sshDir)) {
    mkdirSync(sshDir, { recursive: true, mode: 0o700 });
  }

  // Write the key file
  writeFileSync(keyPath, sshKey, { mode: 0o600 });

  // Ensure proper permissions
  chmodSync(keyPath, 0o600);

  log.info('SSH key configured', { keyPath });
}

/**
 * Configure git to use the project-specific SSH key.
 */
async function configureGitSsh(projectPath: string, projectName: string): Promise<void> {
  const keyPath = getSshKeyPath(projectName);
  const sshCommand = `ssh -i ${keyPath} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new`;

  // Set the sshCommand in the repo's git config
  await execAsync(`git config core.sshCommand "${sshCommand}"`, {
    cwd: projectPath,
  });

  log.info('Git SSH configured', { projectPath, keyPath });
}

/**
 * Clone a repository if it doesn't exist.
 */
async function cloneRepo(repoUrl: string, projectPath: string, projectName: string): Promise<void> {
  const keyPath = getSshKeyPath(projectName);
  const sshCommand = `ssh -i ${keyPath} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new`;

  // Ensure parent directory exists
  const parentDir = dirname(projectPath);
  if (!existsSync(parentDir)) {
    mkdirSync(parentDir, { recursive: true });
  }

  log.info('Cloning repository', { repoUrl, projectPath });

  const result = await execAsync(
    `GIT_SSH_COMMAND="${sshCommand}" git clone "${repoUrl}" "${projectPath}"`,
    { timeout: 300000 } // 5 minute timeout
  );

  if (result.stderr && !result.stderr.includes('Cloning into')) {
    log.warn('Clone stderr', { stderr: result.stderr });
  }

  log.info('Repository cloned successfully');
}

/**
 * Pull latest changes from the remote.
 */
async function pullRepo(projectPath: string): Promise<void> {
  log.info('Pulling latest changes', { projectPath });

  // Fetch all and reset to origin/main (or master)
  try {
    await execAsync('git fetch --all', { cwd: projectPath, timeout: 120000 });

    // Try main first, then master
    try {
      await execAsync('git reset --hard origin/main', { cwd: projectPath, timeout: 30000 });
    } catch {
      await execAsync('git reset --hard origin/master', { cwd: projectPath, timeout: 30000 });
    }

    log.info('Repository updated');
  } catch (err) {
    log.error('Failed to pull', { error: err instanceof Error ? err.message : String(err) });
    throw err;
  }
}

/**
 * Run `bd onboard` to sync beads with the remote.
 */
async function onboardBeads(projectPath: string): Promise<void> {
  log.info('Running bd onboard', { projectPath });

  try {
    await execAsync('bd onboard', {
      cwd: projectPath,
      timeout: 120000, // 2 minute timeout
    });
    log.info('Beads onboarded successfully');
  } catch (err) {
    // bd onboard may fail if this is a fresh project without beads
    log.warn('bd onboard failed (may be expected for new projects)', {
      error: err instanceof Error ? err.message : String(err),
    });
  }
}

/**
 * Set up a repository for work.
 *
 * 1. Save SSH key (if provided)
 * 2. Clone repo if not exists (or pull if exists)
 * 3. Configure git to use the SSH key
 * 4. Run bd onboard to sync beads
 *
 * @param sshKey - Optional SSH key. If not provided, uses default ~/.ssh/id_ed25519
 */
export async function setupRepository(
  repoUrl: string,
  projectName: string,
  sshKey?: string
): Promise<RepoSetupResult> {
  const projectPath = getProjectPath(projectName);

  try {
    // Step 1: Set up SSH key (only if provided)
    if (sshKey) {
      await setupSshKey(projectName, sshKey);
    } else {
      log.info('No SSH key provided, using default key');
    }

    // Step 2: Clone or pull
    if (existsSync(join(projectPath, '.git'))) {
      // Configure SSH first for existing repos
      await configureGitSsh(projectPath, projectName);
      await pullRepo(projectPath);
    } else {
      await cloneRepo(repoUrl, projectPath, projectName);
      await configureGitSsh(projectPath, projectName);
    }

    // Step 3: Run bd onboard
    await onboardBeads(projectPath);

    return {
      success: true,
      message: 'Repository set up successfully',
      projectPath,
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    log.error('Repository setup failed', { error: message });
    return {
      success: false,
      message: `Repository setup failed: ${message}`,
    };
  }
}

/**
 * Check if a project exists locally.
 */
export function projectExists(projectName: string): boolean {
  const projectPath = getProjectPath(projectName);
  return existsSync(join(projectPath, '.git'));
}
