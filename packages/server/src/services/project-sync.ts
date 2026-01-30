/**
 * Project Sync Service
 * ====================
 *
 * Centralized service for syncing project repositories that have remote agents.
 * When remote agents commit changes (features closed, etc.), this service
 * periodically pulls those changes so the local kanban board reflects them.
 *
 * Key responsibilities:
 * - Track projects with active remote agents
 * - Periodically git pull and bd sync --import-only for those projects
 * - Provide feature data that includes remote agent work
 */

import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';

import {
  getProjectPath,
  getRemoteAgentsForProject,
  listProjectContainers,
  type RemoteAgentInfo,
} from '../db/crud.js';
import { getBeadsManagerSync, type BeadsTask, type Feature } from './beads-manager.js';

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
 * Check if a project has any remote agents (active or recent).
 */
export function hasRemoteAgents(projectName: string): boolean {
  try {
    const remoteAgents = getRemoteAgentsForProject(projectName);
    return remoteAgents.length > 0;
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
export function syncProjectIfNeeded(projectName: string): boolean {
  // Only sync projects with remote agents
  if (!hasRemoteAgents(projectName)) {
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
export function forceSyncProject(projectName: string): boolean {
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
export function getProjectTasks(projectName: string): BeadsTask[] {
  // Sync if needed (for remote agent projects)
  syncProjectIfNeeded(projectName);

  // Use BeadsManager to get tasks
  const manager = getBeadsManagerSync(projectName);
  if (manager) {
    return manager.getTasks();
  }

  return [];
}

/**
 * Get features in UI format, syncing first if needed.
 */
export function getProjectFeatures(projectName: string): Feature[] {
  // Sync if needed (for remote agent projects)
  syncProjectIfNeeded(projectName);

  // Use BeadsManager to get features
  const manager = getBeadsManagerSync(projectName);
  if (manager) {
    return manager.getFeatures();
  }

  return [];
}

/**
 * Get feature IDs currently being worked on by containers AND remote agents.
 *
 * This provides a unified view of all in-progress features across
 * local Docker containers and remote machines.
 */
export function getInProgressFeatureIds(projectName: string): Set<string> {
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

  // Get from remote agents
  try {
    const remoteAgents = getRemoteAgentsForProject(projectName);
    for (const agent of remoteAgents) {
      if (agent.currentFeature && agent.status === 'running') {
        inProgress.add(agent.currentFeature);
      }
    }
  } catch {
    // Ignore remote agent errors
  }

  return inProgress;
}

/**
 * Get all remote agents for a project.
 */
export function getRemoteAgents(projectName: string): RemoteAgentInfo[] {
  try {
    return getRemoteAgentsForProject(projectName);
  } catch {
    return [];
  }
}
