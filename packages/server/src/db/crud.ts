/**
 * Database CRUD Functions
 * =======================
 *
 * TypeScript functions mirroring registry.py exports for project, container,
 * remote machine, and remote agent management.
 */

import { eq, and, inArray, lt } from 'drizzle-orm';
import { db } from './index.js';
import {
  projects,
  containers,
  featureCache,
  featureStatsCache,
  remoteMachines,
  remoteAgents,
  projectVerificationState,
  type Container,
  type RemoteAgent,
  type ContainerType,
  type ContainerStatus,
} from './schema.js';
import { homedir } from 'os';
import { join } from 'path';
import { existsSync, accessSync, constants, mkdirSync } from 'fs';

// =============================================================================
// Exceptions
// =============================================================================

export class RegistryError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RegistryError';
  }
}

export class RegistryNotFound extends RegistryError {
  constructor(message: string) {
    super(message);
    this.name = 'RegistryNotFound';
  }
}

// =============================================================================
// Path Helper Functions
// =============================================================================

/**
 * Get the config directory.
 * Uses ZEROCODER_DATA_DIR environment variable if set (for Docker),
 * otherwise defaults to ~/.zerocoder/
 */
export function getConfigDir(): string {
  const dataDir = process.env['ZEROCODER_DATA_DIR'];
  const configDir = dataDir ? join(dataDir, 'zerocoder') : join(homedir(), '.zerocoder');
  if (!existsSync(configDir)) {
    mkdirSync(configDir, { recursive: true });
  }
  return configDir;
}

/**
 * Get the projects directory for local clones.
 * Projects are cloned to ~/.zerocoder/projects/{name}/ for wizard and edit mode.
 */
export function getProjectsDir(): string {
  const projectsDir = join(getConfigDir(), 'projects');
  if (!existsSync(projectsDir)) {
    mkdirSync(projectsDir, { recursive: true });
  }
  return projectsDir;
}

/**
 * Get the path to the registry database.
 */
export function getRegistryPath(): string {
  return join(getConfigDir(), 'registry.db');
}

// =============================================================================
// Validation Functions
// =============================================================================

/**
 * Validate a project name.
 */
export function validateProjectName(name: string): { valid: boolean; error?: string } {
  if (!/^[a-zA-Z0-9_-]{1,50}$/.test(name)) {
    return {
      valid: false,
      error: 'Invalid project name. Use only letters, numbers, hyphens, and underscores (1-50 chars).',
    };
  }
  return { valid: true };
}

/**
 * Validate a git URL format.
 */
export function validateGitUrl(gitUrl: string): { valid: boolean; error?: string } {
  if (!gitUrl) {
    return { valid: false, error: 'Git URL cannot be empty' };
  }
  if (!gitUrl.startsWith('https://') && !gitUrl.startsWith('git@')) {
    return { valid: false, error: 'Git URL must start with https:// or git@' };
  }
  return { valid: true };
}

/**
 * Validate that a project path is accessible and writable.
 */
export function validateProjectPath(path: string): { valid: boolean; error?: string } {
  if (!existsSync(path)) {
    return { valid: false, error: `Path does not exist: ${path}` };
  }

  try {
    accessSync(path, constants.R_OK);
  } catch {
    return { valid: false, error: `No read permission: ${path}` };
  }

  try {
    accessSync(path, constants.W_OK);
  } catch {
    return { valid: false, error: `No write permission: ${path}` };
  }

  return { valid: true };
}

// =============================================================================
// Project CRUD Functions
// =============================================================================

export interface ProjectInfo {
  gitUrl: string;
  isNew: boolean;
  targetContainerCount: number;
  localPath: string;
  createdAt: string | null;
}

/**
 * Register a new project in the registry.
 */
export async function registerProject(name: string, gitUrl: string): Promise<void> {
  const nameValidation = validateProjectName(name);
  if (!nameValidation.valid) {
    throw new Error(nameValidation.error);
  }

  const urlValidation = validateGitUrl(gitUrl);
  if (!urlValidation.valid) {
    throw new Error(urlValidation.error);
  }

  const existing = db.select().from(projects).where(eq(projects.name, name)).get();
  if (existing) {
    throw new RegistryError(`Project '${name}' already exists in registry`);
  }

  db.insert(projects)
    .values({
      name,
      gitUrl,
      targetContainerCount: 1,
      createdAt: new Date().toISOString(),
    })
    .run();
}

/**
 * Remove a project from the registry.
 */
export async function unregisterProject(name: string): Promise<boolean> {
  const result = db.delete(projects).where(eq(projects.name, name)).run();
  return result.changes > 0;
}

/**
 * Look up a project's local clone path by name.
 */
export function getProjectPath(name: string): string | null {
  const project = db.select().from(projects).where(eq(projects.name, name)).get();
  if (!project) {
    return null;
  }
  return join(getProjectsDir(), name);
}

/**
 * Look up a project's git URL by name.
 */
export function getProjectGitUrl(name: string): string | null {
  const project = db.select().from(projects).where(eq(projects.name, name)).get();
  return project?.gitUrl ?? null;
}

/**
 * Get all registered projects.
 */
export function listRegisteredProjects(): Record<string, ProjectInfo> {
  const allProjects = db.select().from(projects).all();
  const projectsDir = getProjectsDir();
  const result: Record<string, ProjectInfo> = {};

  for (const p of allProjects) {
    const localPath = join(projectsDir, p.name);
    const hasBeads = existsSync(join(localPath, '.beads', 'beads.db'));
    result[p.name] = {
      gitUrl: p.gitUrl,
      isNew: !hasBeads,
      targetContainerCount: p.targetContainerCount,
      localPath,
      createdAt: p.createdAt,
    };
  }
  return result;
}

/**
 * Get full info about a project.
 */
export function getProjectInfo(name: string): ProjectInfo | null {
  const project = db.select().from(projects).where(eq(projects.name, name)).get();
  if (!project) {
    return null;
  }
  const localPath = join(getProjectsDir(), project.name);
  const hasBeads = existsSync(join(localPath, '.beads', 'beads.db'));
  return {
    gitUrl: project.gitUrl,
    isNew: !hasBeads,
    targetContainerCount: project.targetContainerCount,
    localPath,
    createdAt: project.createdAt,
  };
}

/**
 * Update a project's git URL.
 */
export function updateProjectGitUrl(name: string, newGitUrl: string): boolean {
  const urlValidation = validateGitUrl(newGitUrl);
  if (!urlValidation.valid) {
    throw new Error(urlValidation.error);
  }

  const result = db.update(projects).set({ gitUrl: newGitUrl }).where(eq(projects.name, name)).run();
  return result.changes > 0;
}

/**
 * Update a project's target container count.
 */
export function updateTargetContainerCount(name: string, count: number): boolean {
  if (count < 1 || count > 10) {
    throw new Error('Container count must be between 1 and 10');
  }

  const result = db.update(projects).set({ targetContainerCount: count }).where(eq(projects.name, name)).run();
  return result.changes > 0;
}

/**
 * Remove projects from registry whose local clones no longer exist.
 */
export function cleanupStaleProjects(): string[] {
  const allProjects = db.select().from(projects).all();
  const removed: string[] = [];
  const projectsDir = getProjectsDir();

  for (const project of allProjects) {
    const localPath = join(projectsDir, project.name);
    if (!existsSync(localPath)) {
      db.delete(projects).where(eq(projects.name, project.name)).run();
      removed.push(project.name);
    }
  }

  return removed;
}

/**
 * List all projects that have valid, accessible local clones.
 */
export function listValidProjects(): (ProjectInfo & { name: string })[] {
  const allProjects = db.select().from(projects).all();
  const valid: (ProjectInfo & { name: string })[] = [];
  const projectsDir = getProjectsDir();

  for (const p of allProjects) {
    const localPath = join(projectsDir, p.name);
    const validation = validateProjectPath(localPath);
    if (validation.valid) {
      const hasBeads = existsSync(join(localPath, '.beads', 'beads.db'));
      valid.push({
        name: p.name,
        gitUrl: p.gitUrl,
        isNew: !hasBeads,
        targetContainerCount: p.targetContainerCount,
        localPath,
        createdAt: p.createdAt,
      });
    }
  }
  return valid;
}

// =============================================================================
// Container CRUD Functions
// =============================================================================

export interface ContainerInfo {
  id: number;
  projectName: string;
  containerNumber: number;
  containerType: string;
  dockerContainerId: string | null;
  status: string;
  currentFeature: string | null;
  createdAt: string | null;
}

/**
 * Create or get an existing container record.
 * If a container with the same (projectName, containerNumber, containerType)
 * already exists, returns its ID and resets its status to 'created'.
 */
export function createContainer(
  projectName: string,
  containerNumber: number,
  containerType: ContainerType = 'coding'
): number {
  // Check if container already exists
  const existing = db
    .select()
    .from(containers)
    .where(
      and(
        eq(containers.projectName, projectName),
        eq(containers.containerNumber, containerNumber),
        eq(containers.containerType, containerType)
      )
    )
    .get();

  if (existing) {
    // Reset status for reuse
    db.update(containers)
      .set({ status: 'created', currentFeature: null })
      .where(eq(containers.id, existing.id))
      .run();
    return existing.id;
  }

  // Create new container
  const result = db
    .insert(containers)
    .values({
      projectName,
      containerNumber,
      containerType,
      status: 'created',
      createdAt: new Date().toISOString(),
    })
    .run();

  return Number(result.lastInsertRowid);
}

/**
 * Get a container record by project, number, and type.
 */
export function getContainer(
  projectName: string,
  containerNumber: number,
  containerType: ContainerType = 'coding'
): ContainerInfo | null {
  const container = db
    .select()
    .from(containers)
    .where(
      and(
        eq(containers.projectName, projectName),
        eq(containers.containerNumber, containerNumber),
        eq(containers.containerType, containerType)
      )
    )
    .get();

  if (!container) {
    return null;
  }

  return {
    id: container.id,
    projectName: container.projectName,
    containerNumber: container.containerNumber,
    containerType: container.containerType,
    dockerContainerId: container.dockerContainerId,
    status: container.status,
    currentFeature: container.currentFeature,
    createdAt: container.createdAt,
  };
}

/**
 * Delete a container record from the database.
 */
export function deleteContainer(
  projectName: string,
  containerNumber: number,
  containerType: ContainerType = 'coding'
): boolean {
  const result = db
    .delete(containers)
    .where(
      and(
        eq(containers.projectName, projectName),
        eq(containers.containerNumber, containerNumber),
        eq(containers.containerType, containerType)
      )
    )
    .run();
  return result.changes > 0;
}

/**
 * Delete containers with invalid container_number (e.g., -1).
 */
export function deleteInvalidContainers(projectName: string): number {
  const result = db
    .delete(containers)
    .where(and(eq(containers.projectName, projectName), lt(containers.containerNumber, 0)))
    .run();
  return result.changes;
}

/**
 * List all containers across all projects.
 */
export function listContainers(statusFilter?: ContainerStatus[]): Container[] {
  if (statusFilter && statusFilter.length > 0) {
    return db.select().from(containers).where(inArray(containers.status, statusFilter)).all();
  }
  return db.select().from(containers).all();
}

/**
 * List all containers for a project.
 */
export function listProjectContainers(
  projectName: string,
  containerType?: ContainerType
): ContainerInfo[] {
  let query = db.select().from(containers).where(eq(containers.projectName, projectName));

  if (containerType) {
    query = db
      .select()
      .from(containers)
      .where(and(eq(containers.projectName, projectName), eq(containers.containerType, containerType)));
  }

  const results = query.all();
  return results.map((c) => ({
    id: c.id,
    projectName: c.projectName,
    containerNumber: c.containerNumber,
    containerType: c.containerType,
    dockerContainerId: c.dockerContainerId,
    status: c.status,
    currentFeature: c.currentFeature,
    createdAt: c.createdAt,
  }));
}

/**
 * Update a container's status and/or docker ID.
 */
export function updateContainerStatus(
  projectName: string,
  containerNumber: number,
  containerType: ContainerType = 'coding',
  updates: {
    status?: ContainerStatus;
    dockerContainerId?: string;
    currentFeature?: string | null;
  }
): boolean {
  const setValues: Partial<Container> = {};

  if (updates.status !== undefined) {
    setValues.status = updates.status;
  }
  if (updates.dockerContainerId !== undefined) {
    setValues.dockerContainerId = updates.dockerContainerId;
  }
  if (updates.currentFeature !== undefined) {
    setValues.currentFeature = updates.currentFeature || null;
  }

  if (Object.keys(setValues).length === 0) {
    return false;
  }

  const result = db
    .update(containers)
    .set(setValues)
    .where(
      and(
        eq(containers.projectName, projectName),
        eq(containers.containerNumber, containerNumber),
        eq(containers.containerType, containerType)
      )
    )
    .run();

  return result.changes > 0;
}

/**
 * Delete all container records for a project.
 */
export function deleteAllProjectContainers(projectName: string): number {
  const result = db.delete(containers).where(eq(containers.projectName, projectName)).run();
  return result.changes;
}

/**
 * List all containers across all projects as dicts.
 */
export function listAllContainers(): Array<{
  projectName: string;
  containerNumber: number;
  containerType: string;
  status: string;
}> {
  const all = db.select().from(containers).all();
  return all.map((c) => ({
    projectName: c.projectName,
    containerNumber: c.containerNumber,
    containerType: c.containerType || 'coding',
    status: c.status,
  }));
}

// =============================================================================
// Session State Functions
// =============================================================================

/**
 * Clear all session-scoped state on server startup.
 */
export function clearSessionState(): void {
  db.delete(containers).run();
  db.delete(remoteAgents).run();
  db.delete(featureCache).run();
  db.delete(featureStatsCache).run();
  db.delete(projectVerificationState).run();
}

/**
 * Set the user_started state for a container.
 */
export function setUserStarted(
  projectName: string,
  containerNumber: number,
  started: boolean,
  containerType: ContainerType = 'coding'
): boolean {
  const result = db
    .update(containers)
    .set({ userStartedAt: started ? new Date().toISOString() : null })
    .where(
      and(
        eq(containers.projectName, projectName),
        eq(containers.containerNumber, containerNumber),
        eq(containers.containerType, containerType)
      )
    )
    .run();
  return result.changes > 0;
}

/**
 * Check if a container was user-started in this session.
 */
export function isUserStarted(
  projectName: string,
  containerNumber: number,
  containerType: ContainerType = 'coding'
): boolean {
  const container = db
    .select({ userStartedAt: containers.userStartedAt })
    .from(containers)
    .where(
      and(
        eq(containers.projectName, projectName),
        eq(containers.containerNumber, containerNumber),
        eq(containers.containerType, containerType)
      )
    )
    .get();
  return container?.userStartedAt != null;
}

/**
 * Set the graceful_stop_requested state for a container.
 */
export function setGracefulStop(
  projectName: string,
  containerNumber: number,
  requested: boolean,
  containerType: ContainerType = 'coding'
): boolean {
  const result = db
    .update(containers)
    .set({ gracefulStopRequested: requested })
    .where(
      and(
        eq(containers.projectName, projectName),
        eq(containers.containerNumber, containerNumber),
        eq(containers.containerType, containerType)
      )
    )
    .run();
  return result.changes > 0;
}

/**
 * Check if graceful stop was requested for a container.
 */
export function isGracefulStopRequested(
  projectName: string,
  containerNumber: number,
  containerType: ContainerType = 'coding'
): boolean {
  const container = db
    .select({ gracefulStopRequested: containers.gracefulStopRequested })
    .from(containers)
    .where(
      and(
        eq(containers.projectName, projectName),
        eq(containers.containerNumber, containerNumber),
        eq(containers.containerType, containerType)
      )
    )
    .get();
  return container?.gracefulStopRequested ?? false;
}

/**
 * Set the restarting state for a container.
 */
export function setRestarting(
  projectName: string,
  containerNumber: number,
  restarting: boolean,
  containerType: ContainerType = 'coding'
): boolean {
  const result = db
    .update(containers)
    .set({ restarting })
    .where(
      and(
        eq(containers.projectName, projectName),
        eq(containers.containerNumber, containerNumber),
        eq(containers.containerType, containerType)
      )
    )
    .run();
  return result.changes > 0;
}

/**
 * Check if a container is currently restarting.
 */
export function isRestarting(
  projectName: string,
  containerNumber: number,
  containerType: ContainerType = 'coding'
): boolean {
  const container = db
    .select({ restarting: containers.restarting })
    .from(containers)
    .where(
      and(
        eq(containers.projectName, projectName),
        eq(containers.containerNumber, containerNumber),
        eq(containers.containerType, containerType)
      )
    )
    .get();
  return container?.restarting ?? false;
}

/**
 * Set the overseer-related flags for a container.
 */
export function setOverseerFlags(
  projectName: string,
  containerNumber: number,
  lastWasOverseer: boolean,
  isMilestone: boolean,
  containerType: ContainerType = 'coding'
): boolean {
  const result = db
    .update(containers)
    .set({
      lastAgentWasOverseer: lastWasOverseer,
      isMilestoneOverseer: isMilestone,
    })
    .where(
      and(
        eq(containers.projectName, projectName),
        eq(containers.containerNumber, containerNumber),
        eq(containers.containerType, containerType)
      )
    )
    .run();
  return result.changes > 0;
}

/**
 * Get the overseer-related flags for a container.
 */
export function getOverseerFlags(
  projectName: string,
  containerNumber: number,
  containerType: ContainerType = 'coding'
): { lastAgentWasOverseer: boolean; isMilestoneOverseer: boolean } {
  const container = db
    .select({
      lastAgentWasOverseer: containers.lastAgentWasOverseer,
      isMilestoneOverseer: containers.isMilestoneOverseer,
    })
    .from(containers)
    .where(
      and(
        eq(containers.projectName, projectName),
        eq(containers.containerNumber, containerNumber),
        eq(containers.containerType, containerType)
      )
    )
    .get();
  return {
    lastAgentWasOverseer: container?.lastAgentWasOverseer ?? false,
    isMilestoneOverseer: container?.isMilestoneOverseer ?? false,
  };
}

/**
 * Update the last_activity_at timestamp for a container.
 */
export function updateLastActivity(
  projectName: string,
  containerNumber: number,
  containerType: ContainerType = 'coding'
): boolean {
  const result = db
    .update(containers)
    .set({ lastActivityAt: new Date().toISOString() })
    .where(
      and(
        eq(containers.projectName, projectName),
        eq(containers.containerNumber, containerNumber),
        eq(containers.containerType, containerType)
      )
    )
    .run();
  return result.changes > 0;
}

/**
 * Get the last_activity_at timestamp for a container.
 */
export function getLastActivity(
  projectName: string,
  containerNumber: number,
  containerType: ContainerType = 'coding'
): Date | null {
  const container = db
    .select({ lastActivityAt: containers.lastActivityAt })
    .from(containers)
    .where(
      and(
        eq(containers.projectName, projectName),
        eq(containers.containerNumber, containerNumber),
        eq(containers.containerType, containerType)
      )
    )
    .get();
  return container?.lastActivityAt ? new Date(container.lastActivityAt) : null;
}

/**
 * Store the last feature closed by this container (for reviewer agent).
 */
export function setLastClosedFeature(
  projectName: string,
  containerNumber: number,
  featureId: string | null,
  containerType: ContainerType = 'coding'
): boolean {
  const result = db
    .update(containers)
    .set({ lastClosedFeature: featureId })
    .where(
      and(
        eq(containers.projectName, projectName),
        eq(containers.containerNumber, containerNumber),
        eq(containers.containerType, containerType)
      )
    )
    .run();
  return result.changes > 0;
}

/**
 * Get the last feature closed by this container.
 */
export function getLastClosedFeature(
  projectName: string,
  containerNumber: number,
  containerType: ContainerType = 'coding'
): string | null {
  const container = db
    .select({ lastClosedFeature: containers.lastClosedFeature })
    .from(containers)
    .where(
      and(
        eq(containers.projectName, projectName),
        eq(containers.containerNumber, containerNumber),
        eq(containers.containerType, containerType)
      )
    )
    .get();
  return container?.lastClosedFeature ?? null;
}

// =============================================================================
// Overseer Milestone Tracking Functions
// =============================================================================

/**
 * Get the last overseer milestone for a project.
 */
export function getOverseerMilestone(projectName: string): number {
  const cache = db
    .select({ lastOverseerMilestone: featureStatsCache.lastOverseerMilestone })
    .from(featureStatsCache)
    .where(eq(featureStatsCache.projectName, projectName))
    .get();
  return cache?.lastOverseerMilestone ?? 0;
}

/**
 * Update the last overseer milestone for a project.
 */
export function updateOverseerMilestone(projectName: string, milestone: number): boolean {
  const result = db
    .update(featureStatsCache)
    .set({ lastOverseerMilestone: milestone })
    .where(eq(featureStatsCache.projectName, projectName))
    .run();
  return result.changes > 0;
}

export interface CachedStats {
  pending: number;
  inProgress: number;
  done: number;
  total: number;
  percentage: number;
  lastOverseerMilestone: number;
  lastPolledAt: string | null;
  pollError: string | null;
}

/**
 * Get cached feature stats for a project.
 */
export function getCachedStats(projectName: string): CachedStats | null {
  const cache = db.select().from(featureStatsCache).where(eq(featureStatsCache.projectName, projectName)).get();
  if (!cache) {
    return null;
  }
  return {
    pending: cache.pendingCount,
    inProgress: cache.inProgressCount,
    done: cache.doneCount,
    total: cache.totalCount,
    percentage: cache.percentage,
    lastOverseerMilestone: cache.lastOverseerMilestone,
    lastPolledAt: cache.lastPolledAt,
    pollError: cache.pollError,
  };
}

// =============================================================================
// Project Verification State Functions
// =============================================================================

/**
 * Set verification running state for a project.
 * Returns false if already running (couldn't acquire lock).
 */
export function setVerificationRunning(projectName: string, running: boolean): boolean {
  const state = db
    .select()
    .from(projectVerificationState)
    .where(eq(projectVerificationState.projectName, projectName))
    .get();

  if (running) {
    if (state?.verificationRunning) {
      return false; // Already running, can't acquire
    }
    if (state) {
      db.update(projectVerificationState)
        .set({ verificationRunning: true, startedAt: new Date().toISOString() })
        .where(eq(projectVerificationState.projectName, projectName))
        .run();
    } else {
      db.insert(projectVerificationState)
        .values({
          projectName,
          verificationRunning: true,
          startedAt: new Date().toISOString(),
        })
        .run();
    }
  } else {
    if (state) {
      db.update(projectVerificationState)
        .set({ verificationRunning: false, startedAt: null })
        .where(eq(projectVerificationState.projectName, projectName))
        .run();
    }
  }
  return true;
}

/**
 * Check if verification is running for a project.
 */
export function isVerificationRunning(projectName: string): boolean {
  const state = db
    .select({ verificationRunning: projectVerificationState.verificationRunning })
    .from(projectVerificationState)
    .where(eq(projectVerificationState.projectName, projectName))
    .get();
  return state?.verificationRunning ?? false;
}

/**
 * Clear verification state for a project.
 */
export function clearVerificationState(projectName: string): void {
  db.delete(projectVerificationState).where(eq(projectVerificationState.projectName, projectName)).run();
}

// =============================================================================
// Remote Machine CRUD Functions
// =============================================================================

export interface RemoteMachineInfo {
  id: number;
  name: string;
  host: string;
  port: number;
  username: string;
  sshKeyPath: string | null;
  status: string;
  lastCheckedAt: string | null;
  createdAt: string | null;
  // Daemon fields
  daemonPort: number | null;
  daemonPid: number | null;
  daemonLastSeen: string | null;
}

/**
 * Add a remote machine to the registry.
 */
export function addRemoteMachine(
  name: string,
  host: string,
  port: number = 22,
  username: string = 'root',
  sshKeyPath?: string
): number {
  const existing = db.select().from(remoteMachines).where(eq(remoteMachines.name, name)).get();
  if (existing) {
    throw new RegistryError(`Remote machine '${name}' already exists`);
  }

  const result = db
    .insert(remoteMachines)
    .values({
      name,
      host,
      port,
      username,
      sshKeyPath: sshKeyPath ?? null,
      status: 'unknown',
      createdAt: new Date().toISOString(),
    })
    .run();

  return Number(result.lastInsertRowid);
}

/**
 * Remove a remote machine from the registry.
 */
export function removeRemoteMachine(machineId: number): boolean {
  const result = db.delete(remoteMachines).where(eq(remoteMachines.id, machineId)).run();
  return result.changes > 0;
}

/**
 * List all registered remote machines.
 */
export function listRemoteMachines(): RemoteMachineInfo[] {
  const machines = db.select().from(remoteMachines).all();
  return machines.map((m) => ({
    id: m.id,
    name: m.name,
    host: m.host,
    port: m.port,
    username: m.username,
    sshKeyPath: m.sshKeyPath,
    status: m.status,
    lastCheckedAt: m.lastCheckedAt,
    createdAt: m.createdAt,
    daemonPort: m.daemonPort,
    daemonPid: m.daemonPid,
    daemonLastSeen: m.daemonLastSeen,
  }));
}

/**
 * Get a remote machine by ID.
 */
export function getRemoteMachine(machineId: number): RemoteMachineInfo | null {
  const m = db.select().from(remoteMachines).where(eq(remoteMachines.id, machineId)).get();
  if (!m) {
    return null;
  }
  return {
    id: m.id,
    name: m.name,
    host: m.host,
    port: m.port,
    username: m.username,
    sshKeyPath: m.sshKeyPath,
    status: m.status,
    lastCheckedAt: m.lastCheckedAt,
    createdAt: m.createdAt,
    daemonPort: m.daemonPort,
    daemonPid: m.daemonPid,
    daemonLastSeen: m.daemonLastSeen,
  };
}

/**
 * Update a remote machine's status.
 */
export function updateRemoteMachineStatus(machineId: number, status: string): boolean {
  const result = db
    .update(remoteMachines)
    .set({ status, lastCheckedAt: new Date().toISOString() })
    .where(eq(remoteMachines.id, machineId))
    .run();
  return result.changes > 0;
}

/**
 * Update a remote machine's fields.
 */
export function updateRemoteMachine(
  machineId: number,
  updates: {
    status?: string;
    daemonPort?: number;
    daemonPid?: number | null;
    daemonLastSeen?: string;
  }
): boolean {
  const setValues: Record<string, unknown> = {};

  if (updates.status !== undefined) {
    setValues['status'] = updates.status;
    setValues['lastCheckedAt'] = new Date().toISOString();
  }
  if (updates.daemonPort !== undefined) {
    setValues['daemonPort'] = updates.daemonPort;
  }
  if (updates.daemonPid !== undefined) {
    setValues['daemonPid'] = updates.daemonPid;
  }
  if (updates.daemonLastSeen !== undefined) {
    setValues['daemonLastSeen'] = updates.daemonLastSeen;
  }

  if (Object.keys(setValues).length === 0) {
    return false;
  }

  const result = db
    .update(remoteMachines)
    .set(setValues)
    .where(eq(remoteMachines.id, machineId))
    .run();
  return result.changes > 0;
}

// =============================================================================
// Remote Agent CRUD Functions
// =============================================================================

export interface RemoteAgentInfo {
  id: number;
  projectName: string;
  machineId: number;
  machineName: string;
  agentNumber: number;
  status: string;
  currentFeature: string | null;
  pid: number | null;
  gracefulStopRequested: boolean;
  restarting: boolean;
  lastActivityAt: string | null;
}

/**
 * Create or get an existing remote agent record.
 */
export function createRemoteAgent(projectName: string, machineId: number, agentNumber: number = 1): number {
  const existing = db
    .select()
    .from(remoteAgents)
    .where(
      and(
        eq(remoteAgents.projectName, projectName),
        eq(remoteAgents.machineId, machineId),
        eq(remoteAgents.agentNumber, agentNumber)
      )
    )
    .get();

  if (existing) {
    db.update(remoteAgents)
      .set({
        status: 'created',
        currentFeature: null,
        pid: null,
        gracefulStopRequested: false,
        restarting: false,
      })
      .where(eq(remoteAgents.id, existing.id))
      .run();
    return existing.id;
  }

  const result = db
    .insert(remoteAgents)
    .values({
      projectName,
      machineId,
      agentNumber,
      status: 'created',
      createdAt: new Date().toISOString(),
    })
    .run();

  return Number(result.lastInsertRowid);
}

/**
 * Update a remote agent's state.
 */
export function updateRemoteAgent(
  agentId: number,
  updates: {
    status?: string;
    currentFeature?: string | null;
    pid?: number | null;
    gracefulStopRequested?: boolean;
    restarting?: boolean;
  }
): boolean {
  const setValues: Partial<RemoteAgent> = {};

  if (updates.status !== undefined) {
    setValues.status = updates.status;
  }
  if (updates.currentFeature !== undefined) {
    setValues.currentFeature = updates.currentFeature || null;
  }
  if (updates.pid !== undefined) {
    setValues.pid = updates.pid;
  }
  if (updates.gracefulStopRequested !== undefined) {
    setValues.gracefulStopRequested = updates.gracefulStopRequested;
  }
  if (updates.restarting !== undefined) {
    setValues.restarting = updates.restarting;
  }

  setValues.lastActivityAt = new Date().toISOString();

  const result = db.update(remoteAgents).set(setValues).where(eq(remoteAgents.id, agentId)).run();
  return result.changes > 0;
}

/**
 * Get all remote agents for a project.
 */
export function getRemoteAgentsForProject(projectName: string): RemoteAgentInfo[] {
  const agents = db.select().from(remoteAgents).where(eq(remoteAgents.projectName, projectName)).all();

  return agents.map((a) => {
    const machine = db.select().from(remoteMachines).where(eq(remoteMachines.id, a.machineId)).get();
    return {
      id: a.id,
      projectName: a.projectName,
      machineId: a.machineId,
      machineName: machine?.name ?? 'unknown',
      agentNumber: a.agentNumber,
      status: a.status,
      currentFeature: a.currentFeature,
      pid: a.pid,
      gracefulStopRequested: a.gracefulStopRequested,
      restarting: a.restarting,
      lastActivityAt: a.lastActivityAt,
    };
  });
}

/**
 * Get a remote agent by ID.
 */
export function getRemoteAgent(agentId: number): RemoteAgentInfo | null {
  const a = db.select().from(remoteAgents).where(eq(remoteAgents.id, agentId)).get();
  if (!a) {
    return null;
  }

  const machine = db.select().from(remoteMachines).where(eq(remoteMachines.id, a.machineId)).get();
  return {
    id: a.id,
    projectName: a.projectName,
    machineId: a.machineId,
    machineName: machine?.name ?? 'unknown',
    agentNumber: a.agentNumber,
    status: a.status,
    currentFeature: a.currentFeature,
    pid: a.pid,
    gracefulStopRequested: a.gracefulStopRequested,
    restarting: a.restarting,
    lastActivityAt: a.lastActivityAt,
  };
}

/**
 * Delete a remote agent record.
 */
export function deleteRemoteAgent(agentId: number): boolean {
  const result = db.delete(remoteAgents).where(eq(remoteAgents.id, agentId)).run();
  return result.changes > 0;
}
