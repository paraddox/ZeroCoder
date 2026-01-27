/**
 * Agent Router
 * ============
 *
 * API endpoints for agent/container control (start/stop/send instruction).
 * Uses ContainerManager for per-project Docker containers.
 */

import { Hono } from 'hono';
import { HTTPException } from 'hono/http-exception';
import { existsSync, readFileSync, readdirSync, unlinkSync } from 'node:fs';
import { join } from 'node:path';
import { execSync, spawnSync } from 'node:child_process';

import { AgentStartRequestSchema } from '@zerocoder/shared';

import {
  getProjectPath,
  getProjectGitUrl,
  getProjectInfo,
  validateProjectName,
  getContainer,
  createContainer,
  updateContainerStatus,
  deleteContainer,
  listProjectContainers,
  isGracefulStopRequested,
  setGracefulStop,
  updateLastActivity,
} from '../db/crud.js';

import type { ContainerType } from '../db/schema.js';

import {
  getInitializerPrompt,
  getCodingPrompt,
  getCodingPromptYolo,
  getOverseerPrompt,
  isExistingRepoProject,
} from '../utils/prompts.js';

import { hasFeatures, hasOpenFeatures } from '../utils/progress.js';

// =============================================================================
// Constants
// =============================================================================

const CONTAINER_STARTUP_DELAY = 60; // seconds between container starts

// =============================================================================
// Helpers
// =============================================================================

/**
 * Sleep helper for staggered startup.
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// =============================================================================
// Router Setup
// =============================================================================

const agentRouter = new Hono();

// =============================================================================
// Validation Helpers
// =============================================================================

/**
 * Parse and validate JSON body with a Zod schema.
 */
async function parseBody<T>(
  c: { req: { json: () => Promise<unknown> } },
  schema: {
    safeParse: (data: unknown) => { success: true; data: T } | { success: false; error: { message: string } };
  }
): Promise<T> {
  const body = await c.req.json();
  const result = schema.safeParse(body);
  if (!result.success) {
    throw new HTTPException(400, { message: `Validation error: ${result.error.message}` });
  }
  return result.data;
}

/**
 * Validate and sanitize project name to prevent path traversal.
 */
function validateProjectNameParam(name: string): string {
  const validation = validateProjectName(name);
  if (!validation.valid) {
    throw new HTTPException(400, { message: validation.error });
  }
  return name;
}

// =============================================================================
// Docker Helper Functions
// =============================================================================

/**
 * Check if Docker is available.
 */
function checkDockerAvailable(): boolean {
  try {
    execSync('docker info', { timeout: 5000, stdio: 'pipe' });
    return true;
  } catch {
    return false;
  }
}

/**
 * Check if the zerocoder-project image exists.
 */
function checkImageExists(): boolean {
  try {
    const result = execSync('docker images -q zerocoder-project', {
      timeout: 5000,
      stdio: 'pipe',
    });
    return result.toString().trim().length > 0;
  } catch {
    return false;
  }
}

/**
 * Get the Docker container name for a project and container number.
 */
function getContainerName(projectName: string, containerNumber: number): string {
  if (containerNumber === 0) {
    return `zerocoder-${projectName}-init`;
  }
  return `zerocoder-${projectName}-${containerNumber}`;
}

/**
 * Get Docker container status.
 */
function getDockerContainerStatus(containerName: string): string | null {
  try {
    const result = execSync(`docker inspect -f "{{.State.Status}}" ${containerName}`, {
      timeout: 5000,
      stdio: 'pipe',
    });
    const status = result.toString().trim();
    return status === 'running' ? 'running' : 'stopped';
  } catch {
    return null; // Container doesn't exist
  }
}

/**
 * Check if a Docker container is running.
 */
function isContainerRunning(containerName: string): boolean {
  return getDockerContainerStatus(containerName) === 'running';
}

/**
 * Check if a process (agent) is running inside a container.
 */
function isAgentRunning(containerName: string): boolean {
  try {
    // Check if claude process is running in container
    const result = execSync(`docker exec ${containerName} pgrep -f "claude"`, {
      timeout: 5000,
      stdio: 'pipe',
    });
    return result.toString().trim().length > 0;
  } catch {
    return false;
  }
}

// =============================================================================
// Git Recovery Functions
// =============================================================================

/**
 * Pre-flight check: Recover from corrupted git state before starting agents.
 */
function runGitRecovery(projectDir: string): { success: boolean; message: string } {
  const gitDir = join(projectDir, '.git');
  if (!existsSync(gitDir)) {
    return { success: true, message: 'Not a git repo' };
  }

  const messages: string[] = [];

  const runGit = (args: string[]): { success: boolean; stdout: string; stderr: string } => {
    try {
      const result = spawnSync('git', ['-C', projectDir, ...args], {
        timeout: 30000,
        encoding: 'utf-8',
      });
      return {
        success: result.status === 0,
        stdout: result.stdout || '',
        stderr: result.stderr || '',
      };
    } catch (e) {
      return { success: false, stdout: '', stderr: String(e) };
    }
  };

  try {
    // 1. Abort any stuck operations
    const abortOps: [string[], string][] = [
      [['rebase', '--abort'], 'rebase'],
      [['merge', '--abort'], 'merge'],
      [['cherry-pick', '--abort'], 'cherry-pick'],
    ];

    for (const [cmd, opName] of abortOps) {
      const result = runGit(cmd);
      if (result.success) {
        messages.push(`Aborted stuck ${opName}`);
      }
    }

    // 2. Check origin remote exists
    const remoteResult = runGit(['remote', 'get-url', 'origin']);
    if (!remoteResult.success) {
      messages.push('Warning: No origin remote configured');
    }

    // 3. Clean up any ref locks
    if (existsSync(gitDir)) {
      const cleanLocks = (dir: string): void => {
        try {
          const entries = readdirSync(dir, { withFileTypes: true });
          for (const entry of entries) {
            if (entry.isFile() && entry.name.endsWith('.lock')) {
              try {
                unlinkSync(join(dir, entry.name));
                messages.push(`Removed stale lock: ${entry.name}`);
              } catch {
                // Ignore
              }
            } else if (entry.isDirectory()) {
              cleanLocks(join(dir, entry.name));
            }
          }
        } catch {
          // Ignore
        }
      };
      cleanLocks(gitDir);
    }

    // 4. Check for divergent branches and fix
    const statusResult = runGit(['status', '--porcelain', '-b']);
    if (statusResult.success && statusResult.stdout.includes('[')) {
      if (statusResult.stdout.includes('ahead') && statusResult.stdout.includes('behind')) {
        messages.push('Detected divergent branches');

        // Fetch and reset to remote
        const fetchResult = runGit(['fetch', 'origin']);
        if (fetchResult.success) {
          // Determine default branch
          let defaultBranch = 'main';
          const mainCheck = runGit(['rev-parse', '--verify', 'origin/main']);
          if (!mainCheck.success) {
            const masterCheck = runGit(['rev-parse', '--verify', 'origin/master']);
            if (masterCheck.success) {
              defaultBranch = 'master';
            }
          }

          const resetResult = runGit(['reset', '--hard', `origin/${defaultBranch}`]);
          if (resetResult.success) {
            messages.push(`Reset to origin/${defaultBranch}`);
          }
        }
      }
    }

    if (messages.length > 0) {
      return { success: true, message: messages.join('; ') };
    }
    return { success: true, message: 'Git state OK' };
  } catch (e) {
    return { success: false, message: `Git recovery error: ${e}` };
  }
}

// =============================================================================
// Prompt Selection
// =============================================================================

/**
 * Determine the appropriate prompt based on project state.
 */
function getAgentPrompt(
  projectDir: string,
  projectName: string,
  yoloMode: boolean = false
): { prompt: string; promptType: string; agentType: string; useInitializer: boolean } {
  const isExisting = isExistingRepoProject(projectDir);

  if (!hasFeatures(projectDir, projectName)) {
    if (isExisting) {
      // Existing repo with no features - go straight to coding
      return {
        prompt: getCodingPrompt(projectDir),
        promptType: 'coding (existing repo)',
        agentType: 'coder',
        useInitializer: false,
      };
    } else {
      // New project with no features - run initializer
      return {
        prompt: getInitializerPrompt(projectDir),
        promptType: 'initializer',
        agentType: 'coder',
        useInitializer: true,
      };
    }
  } else if (hasOpenFeatures(projectDir, projectName)) {
    // Open features exist - run coding agent
    if (yoloMode) {
      return {
        prompt: getCodingPromptYolo(projectDir),
        promptType: 'coding (yolo)',
        agentType: 'coder',
        useInitializer: false,
      };
    }
    return {
      prompt: getCodingPrompt(projectDir),
      promptType: 'coding',
      agentType: 'coder',
      useInitializer: false,
    };
  } else {
    // Features exist but all closed - run overseer for verification
    return {
      prompt: getOverseerPrompt(projectDir),
      promptType: 'overseer',
      agentType: 'overseer',
      useInitializer: false,
    };
  }
}

// =============================================================================
// Route Handlers
// =============================================================================

// GET /api/projects/:name/agent/status - Get agent status
agentRouter.get('/status', async (c) => {
  const projectName = validateProjectNameParam(c.req.param('name') ?? '');

  // Check if a container exists in database
  const container = getContainer(projectName, 1, 'coding');

  if (!container) {
    // No container created yet - return default status
    return c.json({
      status: 'not_created',
      container_name: getContainerName(projectName, 1),
      started_at: null,
      idle_seconds: 0,
      agent_running: false,
      graceful_stop_requested: false,
    });
  }

  // Get live status from Docker
  const containerName = getContainerName(projectName, container.containerNumber);
  const dockerStatus = getDockerContainerStatus(containerName);
  const agentRunning = dockerStatus === 'running' ? isAgentRunning(containerName) : false;

  const status = dockerStatus || container.status;
  const gracefulStop = isGracefulStopRequested(projectName, container.containerNumber, 'coding');

  return c.json({
    status,
    container_name: containerName,
    started_at: container.createdAt,
    idle_seconds: 0, // TODO: Calculate from last activity
    agent_running: agentRunning,
    graceful_stop_requested: gracefulStop,
  });
});

// POST /api/projects/:name/agent/start - Start the agent
agentRouter.post('/start', async (c) => {
  const projectName = validateProjectNameParam(c.req.param('name') ?? '');

  // Check Docker availability
  if (!checkDockerAvailable()) {
    throw new HTTPException(503, {
      message: 'Docker is not available. Please ensure Docker is installed and running.',
    });
  }

  if (!checkImageExists()) {
    throw new HTTPException(503, {
      message:
        "Container image 'zerocoder-project' not found. Run: DOCKER_BUILDKIT=1 docker build --secret id=ssh_key,src=$HOME/.ssh/id_ed25519 -f Dockerfile.project -t zerocoder-project .",
    });
  }

  // Get project info
  const projectDir = getProjectPath(projectName);
  const gitUrl = getProjectGitUrl(projectName);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${projectName}' not found in registry` });
  }

  if (!gitUrl) {
    throw new HTTPException(404, { message: `Project '${projectName}' has no git URL` });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: `Project directory not found: ${projectDir}` });
  }

  // Parse request body
  let instruction: string | null = null;
  let yoloMode = false;
  try {
    const body = await parseBody(c, AgentStartRequestSchema);
    instruction = body.instruction ?? null;
    yoloMode = body.yolo_mode ?? false;
  } catch {
    // Use defaults if body parsing fails
  }

  // Determine the instruction to send
  let agentType = 'coder';
  let useInitializer = false;

  if (!instruction) {
    // Auto-determine based on project state
    try {
      const promptInfo = getAgentPrompt(projectDir, projectName, yoloMode);
      instruction = promptInfo.prompt;
      agentType = promptInfo.agentType;
      useInitializer = promptInfo.useInitializer;
      console.log(`[Agent] Auto-selected ${promptInfo.promptType} prompt for ${projectName}`);
    } catch (e) {
      throw new HTTPException(400, { message: `Could not load prompt: ${e}` });
    }
  }

  // Create or get container record
  const containerId = createContainer(projectName, 1, 'coding');
  updateContainerStatus(projectName, 1, 'coding', { status: 'running' });

  // TODO: Actually start the Docker container and send instruction
  // For now, return a placeholder response
  console.log(`[Agent] Would start container for ${projectName} with ${agentType} agent`);
  if (useInitializer) {
    console.log(`[Agent] Initializer will use Claude SDK with Opus 4.5`);
  }

  return c.json({
    success: true,
    status: 'running',
    message: `Agent start requested (container ID: ${containerId})`,
  });
});

// POST /api/projects/:name/agent/start-all - Start all containers
agentRouter.post('/start-all', async (c) => {
  const projectName = validateProjectNameParam(c.req.param('name') ?? '');

  // Check Docker availability
  if (!checkDockerAvailable()) {
    throw new HTTPException(503, {
      message: 'Docker is not available. Please ensure Docker is installed and running.',
    });
  }

  if (!checkImageExists()) {
    throw new HTTPException(503, {
      message:
        "Container image 'zerocoder-project' not found. Run: DOCKER_BUILDKIT=1 docker build --secret id=ssh_key,src=$HOME/.ssh/id_ed25519 -f Dockerfile.project -t zerocoder-project .",
    });
  }

  // Get project info
  const projectInfo = getProjectInfo(projectName);
  if (!projectInfo) {
    throw new HTTPException(404, { message: `Project '${projectName}' not found in registry` });
  }

  if (!projectInfo.gitUrl) {
    throw new HTTPException(404, { message: `Project '${projectName}' has no git URL` });
  }

  const projectDir = getProjectPath(projectName);
  if (!projectDir || !existsSync(projectDir)) {
    throw new HTTPException(404, { message: `Project directory not found for '${projectName}'` });
  }

  const targetCount = projectInfo.targetContainerCount;
  const gitUrl = projectInfo.gitUrl;

  // Pre-flight git health check
  if (existsSync(join(projectDir, '.git'))) {
    const recoveryResult = runGitRecovery(projectDir);
    if (recoveryResult.success && recoveryResult.message !== 'Git state OK') {
      console.log(`[StartAll] Pre-flight recovery: ${recoveryResult.message}`);
    } else if (!recoveryResult.success) {
      console.log(`[StartAll] Pre-flight recovery warning: ${recoveryResult.message}`);
    }
  }

  // Import container manager functions
  const { getContainerManager } = await import('../services/container-manager.js');

  // Check if project has features
  const projectHasFeatures = hasFeatures(projectDir, projectName);

  // ==========================================================================
  // PHASE 1: Init container (only for projects without features)
  // ==========================================================================
  if (!projectHasFeatures) {
    console.log(`[StartAll] Phase 1: Running full initializer for new project ${projectName}`);

    // Get init container manager
    const initManager = await getContainerManager(projectName, gitUrl, 0, projectDir);

    // Load initializer prompt
    let initInstruction: string;
    try {
      initInstruction = getInitializerPrompt(projectDir);
    } catch (e) {
      throw new HTTPException(400, { message: `Could not load initializer prompt: ${e}` });
    }

    // Force Claude SDK with Opus 4.5 for initializer
    initManager['_forceClaudeSdk'] = true;
    initManager['_forcedModel'] = 'claude-opus-4-5-20251101';

    // Start init container with instruction
    const [initSuccess, initMessage] = await initManager.start(initInstruction);
    if (!initSuccess) {
      return c.json({
        success: false,
        status: initManager.status,
        message: `Phase 1 (init) failed: ${initMessage}`,
      });
    }

    // Wait for init container to finish
    console.log(`[StartAll] Waiting for init container to complete...`);
    while (await initManager.isAgentRunning()) {
      await sleep(2000);
    }

    console.log(`[StartAll] Phase 1 complete. Init container finished.`);
  } else {
    console.log(`[StartAll] Phase 1: Host-side recovery for existing project ${projectName}`);

    // Revert any in_progress tasks to open on the host side
    // TODO: Implement task cleanup service
    // const reverted = await revertInProgressTasksForProject(projectName, projectDir);
    // if (reverted > 0) {
    //   console.log(`[StartAll] Reverted ${reverted} in_progress task(s) to open`);
    // }

    console.log(`[StartAll] Phase 1 complete. Recovery finished.`);
  }

  // ==========================================================================
  // PHASE 2: Spawn N coding containers with staggered startup
  // ==========================================================================
  console.log(`[StartAll] Phase 2: Spawning ${targetCount} coding container(s)...`);

  // Load coding prompt for all containers
  let codingPrompt: string;
  try {
    codingPrompt = getCodingPrompt(projectDir);
  } catch (e) {
    throw new HTTPException(400, { message: `Could not load coding prompt: ${e}` });
  }

  // Create managers for all coding containers
  const codingManagers: Awaited<ReturnType<typeof getContainerManager>>[] = [];
  for (let i = 1; i <= targetCount; i++) {
    const manager = await getContainerManager(projectName, gitUrl, i, projectDir);
    codingManagers.push(manager);
  }

  // Start coding containers with staggered delays
  const results: { success: boolean; message: string }[] = [];

  for (let i = 0; i < codingManagers.length; i++) {
    const containerNum = i + 1;
    const manager = codingManagers[i];

    if (!manager) continue;

    // Stagger starts (skip delay for first container)
    if (i > 0) {
      console.log(`[StartAll] Waiting ${CONTAINER_STARTUP_DELAY}s before starting container ${containerNum}...`);
      await sleep(CONTAINER_STARTUP_DELAY * 1000);
    }

    try {
      console.log(`[StartAll] Starting coding container ${containerNum}...`);

      // Configure for coding agent
      manager['_currentAgentType'] = 'coder';
      manager['_forceClaudeSdk'] = false;

      // Start container first (without agent)
      const [containerOk, containerMsg] = await manager.startContainerOnly();
      if (!containerOk) {
        results.push({ success: false, message: `Container ${containerNum} failed: ${containerMsg}` });
        continue;
      }

      // Wait a moment for container to stabilize
      await sleep(2000);

      // Start agent as fire-and-forget background task
      manager.sendInstruction(codingPrompt).catch((err) => {
        console.error(`[StartAll] Agent error in container ${containerNum}: ${err}`);
      });

      results.push({ success: true, message: `Container ${containerNum} started, agent launching` });
      console.log(`[StartAll] Container ${containerNum} started, agent launching in background`);
    } catch (e) {
      console.error(`[StartAll] Error starting container ${containerNum}: ${e}`);
      results.push({ success: false, message: `Container ${containerNum}: ${e}` });
    }
  }

  // Analyze results
  const successes = results.filter((r) => r.success).length;
  const failures = results.filter((r) => !r.success);
  const allSuccess = successes === targetCount;

  let message: string;
  if (failures.length > 0) {
    message = `Started ${successes}/${targetCount} coding containers. Failures: ${failures.map((f) => f.message).join('; ')}`;
  } else {
    message = `Successfully started init + ${targetCount} coding container(s)`;
  }

  return c.json({
    success: allSuccess,
    status: allSuccess ? 'running' : successes === 0 ? 'error' : 'partial',
    message,
  });
});

// POST /api/projects/:name/agent/stop - Stop all containers
agentRouter.post('/stop', async (c) => {
  const projectName = validateProjectNameParam(c.req.param('name') ?? '');

  // Get all containers for this project
  const containers = listProjectContainers(projectName);

  if (containers.length === 0) {
    return c.json({
      success: true,
      status: 'stopped',
      message: 'No containers to stop',
    });
  }

  let successes = 0;
  for (const container of containers) {
    const containerName = getContainerName(projectName, container.containerNumber);

    try {
      // Stop the Docker container
      execSync(`docker stop ${containerName}`, { timeout: 30000, stdio: 'pipe' });
      updateContainerStatus(projectName, container.containerNumber, container.containerType as ContainerType, {
        status: 'stopped',
      });
      successes++;
    } catch {
      // Container might not exist or already stopped
      updateContainerStatus(projectName, container.containerNumber, container.containerType as ContainerType, {
        status: 'stopped',
      });
    }
  }

  return c.json({
    success: successes === containers.length,
    status: successes === containers.length ? 'stopped' : 'partial',
    message: `Stopped ${successes}/${containers.length} containers`,
  });
});

// POST /api/projects/:name/agent/graceful-stop - Request graceful shutdown
agentRouter.post('/graceful-stop', async (c) => {
  const projectName = validateProjectNameParam(c.req.param('name') ?? '');

  // Get all containers for this project
  const containers = listProjectContainers(projectName);

  if (containers.length === 0) {
    return c.json({
      success: true,
      status: 'stopped',
      message: 'No containers to stop',
    });
  }

  let successes = 0;
  for (const container of containers) {
    // Set graceful stop flag
    setGracefulStop(projectName, container.containerNumber, true, container.containerType as ContainerType);
    successes++;
  }

  // TODO: Broadcast to WebSocket

  return c.json({
    success: successes === containers.length,
    status: successes > 0 ? 'stopping' : 'error',
    message: `Graceful stop requested for ${successes}/${containers.length} containers`,
  });
});

// POST /api/projects/:name/agent/instruction - Send instruction to running container
agentRouter.post('/instruction', async (c) => {
  const projectName = validateProjectNameParam(c.req.param('name') ?? '');

  const request = await parseBody(c, AgentStartRequestSchema);

  if (!request.instruction) {
    throw new HTTPException(400, { message: 'instruction is required' });
  }

  // Check if container is running
  const container = getContainer(projectName, 1, 'coding');
  if (!container) {
    throw new HTTPException(400, { message: 'Container not found' });
  }

  const containerName = getContainerName(projectName, 1);
  if (!isContainerRunning(containerName)) {
    throw new HTTPException(400, { message: `Container is not running (status: ${container.status})` });
  }

  // TODO: Actually send instruction to container

  return c.json({
    success: true,
    status: 'running',
    message: 'Instruction sent',
  });
});

// DELETE /api/projects/:name/agent/container - Remove container
agentRouter.delete('/container', async (c) => {
  const projectName = validateProjectNameParam(c.req.param('name') ?? '');

  const containerName = getContainerName(projectName, 1);

  try {
    // Remove Docker container
    execSync(`docker rm -f ${containerName}`, { timeout: 30000, stdio: 'pipe' });
  } catch {
    // Container might not exist
  }

  // Remove from database
  deleteContainer(projectName, 1, 'coding');

  return c.json({
    success: true,
    status: 'stopped',
    message: 'Container removed',
  });
});

// POST /api/projects/:name/agent/container/start - Start container only (no agent)
agentRouter.post('/container/start', async (c) => {
  const projectName = validateProjectNameParam(c.req.param('name') ?? '');

  // Check Docker availability
  if (!checkDockerAvailable()) {
    throw new HTTPException(503, {
      message: 'Docker is not available. Please ensure Docker is installed and running.',
    });
  }

  if (!checkImageExists()) {
    throw new HTTPException(503, {
      message:
        "Container image 'zerocoder-project' not found. Run: DOCKER_BUILDKIT=1 docker build --secret id=ssh_key,src=$HOME/.ssh/id_ed25519 -f Dockerfile.project -t zerocoder-project .",
    });
  }

  // Get project info
  const projectDir = getProjectPath(projectName);
  const gitUrl = getProjectGitUrl(projectName);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${projectName}' not found in registry` });
  }

  if (!gitUrl) {
    throw new HTTPException(404, { message: `Project '${projectName}' has no git URL` });
  }

  // Create container record
  createContainer(projectName, 1, 'coding');

  // TODO: Actually start Docker container

  return c.json({
    success: true,
    status: 'running',
    message: 'Container started (agent not launched)',
  });
});

// POST /api/projects/:name/agent/pause - Deprecated
agentRouter.post('/pause', async () => {
  throw new HTTPException(400, {
    message: 'Pause is not supported for containers. Use stop instead.',
  });
});

// POST /api/projects/:name/agent/resume - Deprecated
agentRouter.post('/resume', async () => {
  throw new HTTPException(400, {
    message: 'Resume is not supported for containers. Use start instead.',
  });
});

// =============================================================================
// Container Session Endpoints (for container-to-host communication)
// =============================================================================

// GET /api/projects/:name/agent/containers/:containerNumber/session
agentRouter.get('/containers/:containerNumber/session', async (c) => {
  const projectName = validateProjectNameParam(c.req.param('name') ?? '');
  const containerNumber = parseInt(c.req.param('containerNumber') ?? '1', 10);

  const containerType: ContainerType = containerNumber === 0 ? 'init' : 'coding';
  const gracefulStop = isGracefulStopRequested(projectName, containerNumber, containerType);

  // Check if there are open features
  const projectDir = getProjectPath(projectName);
  const openFeatures = projectDir ? hasOpenFeatures(projectDir, projectName) : false;

  // Get model config from project directory
  let config: Record<string, unknown> = {};
  if (projectDir) {
    const configPath = join(projectDir, 'prompts', '.agent_config.json');
    if (existsSync(configPath)) {
      try {
        config = JSON.parse(readFileSync(configPath, 'utf-8'));
      } catch {
        // Ignore parse errors
      }
    }
  }

  // Determine if container should continue
  let shouldContinue: boolean;
  if (containerType === 'init') {
    // Init containers only run if NO features exist yet
    const anyFeatures = projectDir ? hasFeatures(projectDir, projectName) : false;
    shouldContinue = !anyFeatures && !gracefulStop;
  } else {
    // Coding containers continue if there are open features
    shouldContinue = openFeatures && !gracefulStop;
  }

  return c.json({
    should_continue: shouldContinue,
    graceful_stop_requested: gracefulStop,
    has_open_features: openFeatures,
    config,
  });
});

// POST /api/projects/:name/agent/containers/:containerNumber/heartbeat
agentRouter.post('/containers/:containerNumber/heartbeat', async (c) => {
  const projectName = validateProjectNameParam(c.req.param('name') ?? '');
  const containerNumber = parseInt(c.req.param('containerNumber') ?? '1', 10);

  const containerType: ContainerType = containerNumber === 0 ? 'init' : 'coding';

  // Update last activity timestamp
  updateLastActivity(projectName, containerNumber, containerType);

  // Check if graceful stop requested
  const gracefulStop = isGracefulStopRequested(projectName, containerNumber, containerType);

  return c.json({
    acknowledged: true,
    graceful_stop_requested: gracefulStop,
  });
});

// POST /api/projects/:name/agent/containers/:containerNumber/exit
agentRouter.post('/containers/:containerNumber/exit', async (c) => {
  const projectName = validateProjectNameParam(c.req.param('name') ?? '');
  const containerNumber = parseInt(c.req.param('containerNumber') ?? '1', 10);

  const containerType: ContainerType = containerNumber === 0 ? 'init' : 'coding';
  const gracefulStop = isGracefulStopRequested(projectName, containerNumber, containerType);

  // Check if there are open features
  const projectDir = getProjectPath(projectName);
  const openFeatures = projectDir ? hasOpenFeatures(projectDir, projectName) : false;

  // Determine if restart is needed
  const shouldRestart = openFeatures && !gracefulStop;

  return c.json({
    restart: shouldRestart,
    prompt: shouldRestart ? 'coding' : null,
    has_open_features: openFeatures,
    graceful_stop_requested: gracefulStop,
  });
});

export { agentRouter };
