/**
 * Project Sync Service
 * ====================
 *
 * Centralized service for syncing project repositories that have remote agents.
 * When remote agents commit changes (features closed, etc.), this service
 * periodically pulls those changes so the local kanban board reflects them.
 *
 * Key responsibilities:
 * - Track projects with active remote agents (via daemon status)
 * - Periodically git pull and bd sync --import-only for those projects
 * - Provide feature data that includes remote agent work
 */

import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

import {
  getProjectPath,
  getProjectGitUrl,
  listProjectContainers,
  listRemoteMachines,
} from '../db/crud.js';
import {
  getBeadsManager,
  getBeadsManagerSync,
  type BeadsTask,
  type Feature,
} from './beads-manager.js';
import { getDaemonStatus } from './remote-machine-manager.js';

// =============================================================================
// Constants
// =============================================================================

/** Minimum interval between syncs for the same project (60 seconds) */
const SYNC_INTERVAL_MS = 60000;

// =============================================================================
// State
// =============================================================================

/** Track last sync time per project */
const lastSyncTime = new Map<string, number>();

// =============================================================================
// Core Sync Functions
// =============================================================================

/**
 * Check if a project has any remote agents running (via daemon status).
 */
export async function hasRemoteAgents(projectName: string): Promise<boolean> {
  try {
    const machines = listRemoteMachines();
    for (const machine of machines) {
      const status = await getDaemonStatus(machine.id);
      if (status && status.current_repo?.includes(projectName)) {
        return true;
      }
    }
    return false;
  } catch {
    return false;
  }
}

/**
 * Sync a project's repo from git remote if it has remote agents.
 *
 * This pulls the latest changes from git and imports the beads JSONL
 * into the local SQLite database.
 *
 * @returns true if sync was performed, false if skipped or failed
 */
export async function syncProjectIfNeeded(projectName: string): Promise<boolean> {
  // Only sync projects with remote agents
  if (!(await hasRemoteAgents(projectName))) {
    return false;
  }

  // Check if we synced recently
  const lastSync = lastSyncTime.get(projectName) || 0;
  const now = Date.now();
  if (now - lastSync < SYNC_INTERVAL_MS) {
    return false; // Skip - too soon
  }

  const projectDir = getProjectPath(projectName);
  if (!projectDir || !existsSync(projectDir)) {
    return false;
  }

  // Check if .git exists
  if (!existsSync(join(projectDir, '.git'))) {
    return false;
  }

  try {
    // 1. Pull latest changes from git (fast-forward only to avoid conflicts)
    execSync('git pull --ff-only --quiet', {
      cwd: projectDir,
      timeout: 30000,
      stdio: 'pipe',
    });

    // 2. Import beads JSONL into local SQLite DB
    //    This updates the local db with any changes from remote agents
    execSync('bd --no-daemon sync --import-only', {
      cwd: projectDir,
      timeout: 30000,
      stdio: 'pipe',
    });

    lastSyncTime.set(projectName, now);
    console.debug(`Project ${projectName} synced from remote`);
    return true;
  } catch (error) {
    // Log but don't fail - sync is best-effort
    console.debug(`Project sync skipped for ${projectName}:`, error);
    return false;
  }
}

/**
 * Force a sync regardless of the interval (for on-demand refresh).
 */
export async function forceSyncProject(projectName: string): Promise<boolean> {
  // Clear the last sync time to force a sync
  lastSyncTime.delete(projectName);
  return syncProjectIfNeeded(projectName);
}

// =============================================================================
// Feature Data Access
// =============================================================================

/**
 * Get beads tasks for a project, syncing first if needed.
 *
 * This is the centralized way to get features that accounts for
 * remote agent changes.
 */
export async function getProjectTasks(projectName: string): Promise<BeadsTask[]> {
  // Sync if needed (for remote agent projects)
  await syncProjectIfNeeded(projectName);

  // Use BeadsManager to get tasks
  let manager = getBeadsManagerSync(projectName);

  // Lazy initialization if manager doesn't exist
  if (!manager) {
    try {
      const gitUrl = getProjectGitUrl(projectName);
      if (gitUrl) {
        manager = await getBeadsManager(projectName, gitUrl);
      }
    } catch (e) {
      console.debug(`Failed to initialize BeadsManager for ${projectName}:`, e);
    }
  }

  return manager?.getTasks() ?? [];
}

/**
 * Get features in UI format, syncing first if needed.
 */
export async function getProjectFeatures(projectName: string): Promise<Feature[]> {
  // Sync if needed (for remote agent projects)
  await syncProjectIfNeeded(projectName);

  // Use BeadsManager to get features
  let manager = getBeadsManagerSync(projectName);

  // Lazy initialization if manager doesn't exist
  if (!manager) {
    try {
      const gitUrl = getProjectGitUrl(projectName);
      if (gitUrl) {
        manager = await getBeadsManager(projectName, gitUrl);
      }
    } catch (e) {
      console.debug(`Failed to initialize BeadsManager for ${projectName}:`, e);
    }
  }

  return manager?.getFeatures() ?? [];
}

/**
 * Get feature IDs currently being worked on by containers AND remote agents.
 *
 * This provides a unified view of all in-progress features across
 * local Docker containers and remote machines.
 */
export async function getInProgressFeatureIds(projectName: string): Promise<Set<string>> {
  const inProgress = new Set<string>();

  // Get from Docker containers
  try {
    const containers = listProjectContainers(projectName);
    for (const c of containers) {
      if (c.currentFeature) {
        inProgress.add(c.currentFeature);
      }
    }
  } catch {
    // Ignore container errors
  }

  // Get from remote agents (via daemon status)
  try {
    const machines = listRemoteMachines();
    for (const machine of machines) {
      const status = await getDaemonStatus(machine.id);
      if (status && status.current_repo?.includes(projectName) && status.current_feature) {
        inProgress.add(status.current_feature);
      }
    }
  } catch {
    // Ignore remote agent errors
  }

  return inProgress;
}

/**
 * Get info about remote agents working on a project.
 * Returns daemon status for each machine working on the project.
 */
export async function getRemoteAgentInfo(projectName: string): Promise<Array<{
  machineId: number;
  machineName: string;
  status: string;
  currentFeature: string | null;
  agentType: string | null;
}>> {
  const agents: Array<{
    machineId: number;
    machineName: string;
    status: string;
    currentFeature: string | null;
    agentType: string | null;
  }> = [];

  try {
    const machines = listRemoteMachines();
    for (const machine of machines) {
      const status = await getDaemonStatus(machine.id);
      if (status && status.current_repo?.includes(projectName)) {
        agents.push({
          machineId: machine.id,
          machineName: machine.name,
          status: status.status,
          currentFeature: status.current_feature,
          agentType: status.agent_type,
        });
      }
    }
  } catch {
    // Ignore errors
  }

  return agents;
}
