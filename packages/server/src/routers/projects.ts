/**
 * Projects Router
 * ===============
 *
 * API endpoints for project management.
 * Uses project registry for path lookups instead of fixed generations/ directory.
 */

import { Hono } from 'hono';
import { HTTPException } from 'hono/http-exception';
import { existsSync, readFileSync, writeFileSync, unlinkSync, mkdirSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { execSync } from 'node:child_process';

import {
  ProjectCreateSchema,
  ProjectPromptsUpdateSchema,
  ProjectSettingsUpdateSchema,
  WizardStatusSchema,
  AddExistingRepoRequestSchema,
  ContainerCountUpdateSchema,
  TaskCreateSchema,
  TaskUpdateSchema,
} from '@zerocoder/shared';

import {
  registerProject,
  unregisterProject,
  getProjectPath,
  getProjectInfo,
  getProjectsDir,
  listRegisteredProjects,
  validateProjectName,
  updateTargetContainerCount,
  listProjectContainers,
} from '../db/crud.js';

import {
  hasProjectPrompts,
  scaffoldProjectPrompts,
  scaffoldExistingRepo,
  getProjectPromptsDir,
} from '../utils/prompts.js';

import { countPassingTests } from '../utils/progress.js';

// =============================================================================
// Constants
// =============================================================================

const DEFAULT_AGENT_MODEL = 'glm-4-7';
const AGENT_CONFIG_FILENAME = '.agent_config.json';
const VALID_MODELS = ['claude-opus-4-5-20251101', 'claude-sonnet-4-5-20250514', 'glm-4-7', 'minimax-m2-1'];

// Track projects in edit mode (in-memory for simplicity)
const editModeProjects = new Set<string>();

// =============================================================================
// Router Setup
// =============================================================================

const projectsRouter = new Hono();

// =============================================================================
// Validation Helpers
// =============================================================================

/**
 * Parse and validate JSON body with a Zod schema.
 */
async function parseBody<T>(c: { req: { json: () => Promise<unknown> } }, schema: { safeParse: (data: unknown) => { success: true; data: T } | { success: false; error: { message: string } } }): Promise<T> {
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

/**
 * Validate task ID format (e.g., 'beads-123', 'feat-42').
 */
function validateTaskId(taskId: string): string {
  if (!/^[a-zA-Z]+-\d+$/.test(taskId)) {
    throw new HTTPException(400, { message: `Invalid task ID format: ${taskId}` });
  }
  return taskId;
}

// =============================================================================
// Helper Functions
// =============================================================================

interface ProjectStats {
  passing: number;
  in_progress: number;
  total: number;
  percentage: number;
}

/**
 * Get statistics for a project.
 */
function getProjectStats(projectDir: string, projectName?: string): ProjectStats {
  const [passing, inProgress, total] = countPassingTests(projectDir, projectName);
  const percentage = total > 0 ? Math.round((passing / total) * 1000) / 10 : 0;
  return {
    passing,
    in_progress: inProgress,
    total,
    percentage,
  };
}

/**
 * Get the path to the wizard status file.
 */
function getWizardStatusPath(projectDir: string): string {
  return join(projectDir, 'prompts', '.wizard_status.json');
}

/**
 * Check if a project has an incomplete wizard (status file exists but no spec).
 */
function checkWizardIncomplete(projectDir: string, hasSpec: boolean): boolean {
  if (hasSpec) {
    return false;
  }
  const wizardFile = getWizardStatusPath(projectDir);
  return existsSync(wizardFile);
}

/**
 * Get the path to the agent config file.
 */
function getAgentConfigPath(projectDir: string): string {
  return join(projectDir, 'prompts', AGENT_CONFIG_FILENAME);
}

/**
 * Read the agent model from project config file.
 */
function readAgentModel(projectDir: string): string {
  const configPath = getAgentConfigPath(projectDir);
  if (existsSync(configPath)) {
    try {
      const config = JSON.parse(readFileSync(configPath, 'utf-8'));
      return config.agent_model || DEFAULT_AGENT_MODEL;
    } catch (e) {
      console.warn(`Failed to read agent config for ${projectDir}, using default: ${e}`);
    }
  }
  return DEFAULT_AGENT_MODEL;
}

/**
 * Write the agent model to project config file.
 */
function writeAgentConfig(projectDir: string, agentModel: string): void {
  const configPath = getAgentConfigPath(projectDir);
  mkdirSync(join(projectDir, 'prompts'), { recursive: true });

  // Read existing config if it exists
  let config: Record<string, unknown> = {};
  if (existsSync(configPath)) {
    try {
      config = JSON.parse(readFileSync(configPath, 'utf-8'));
    } catch {
      // Ignore read errors
    }
  }

  // Update the model
  config.agent_model = agentModel;
  writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf-8');
}

/**
 * Clone a git repository to the specified destination.
 */
function cloneRepository(gitUrl: string, destination: string): { success: boolean; message: string } {
  if (!gitUrl.startsWith('https://') && !gitUrl.startsWith('git@')) {
    return { success: false, message: 'Invalid git URL. Must start with https:// or git@' };
  }

  try {
    execSync(`git clone ${gitUrl} ${destination}`, {
      timeout: 300000, // 5 minute timeout
      stdio: 'pipe',
    });
    return { success: true, message: 'Repository cloned successfully' };
  } catch (e: unknown) {
    const err = e as Error & { killed?: boolean; stderr?: Buffer };
    if (err.killed) {
      return { success: false, message: 'Git clone timed out after 5 minutes' };
    }
    const stderr = err.stderr?.toString() || err.message;
    return { success: false, message: `Git clone failed: ${stderr}` };
  }
}

/**
 * Initialize beads in the project directory if not already initialized.
 */
function initBeadsIfNeeded(projectDir: string): { success: boolean; message: string } {
  const beadsConfig = join(projectDir, '.beads', 'config.yaml');

  if (existsSync(beadsConfig)) {
    return { success: true, message: 'Beads already initialized' };
  }

  try {
    execSync('bd init --prefix feat', {
      cwd: projectDir,
      timeout: 30000,
      stdio: 'pipe',
    });
    return { success: true, message: 'Beads initialized successfully' };
  } catch (e: unknown) {
    const err = e as Error & { code?: string; stderr?: Buffer };
    if (err.code === 'ENOENT') {
      return { success: false, message: 'beads CLI (bd) not found. Please install beads.' };
    }
    const stderr = err.stderr?.toString() || err.message;
    return { success: false, message: `Beads init failed: ${stderr}` };
  }
}

/**
 * Get live status from Docker for a container.
 */
function getDockerContainerStatus(containerName: string): string | null {
  try {
    const result = execSync(`docker inspect -f "{{.State.Status}}" ${containerName}`, {
      timeout: 5000,
      stdio: 'pipe',
    });
    const dockerStatus = result.toString().trim();
    return dockerStatus === 'running' ? 'running' : 'stopped';
  } catch {
    return null; // Container doesn't exist
  }
}

// =============================================================================
// Route Handlers
// =============================================================================

// GET /api/projects - List all projects
projectsRouter.get('/', async (c) => {
  const projects = listRegisteredProjects();
  const result = [];

  for (const [name, info] of Object.entries(projects)) {
    const localPath = info.localPath;

    // Skip if local clone doesn't exist
    if (!existsSync(localPath)) {
      continue;
    }

    const hasSpec = hasProjectPrompts(localPath);
    const stats = getProjectStats(localPath, name);
    const wizardIncomplete = checkWizardIncomplete(localPath, hasSpec);
    const agentModel = readAgentModel(localPath);

    // Get aggregate agent status across all containers for this project
    let agentStatus: string | null = null;
    let agentRunning = false;
    try {
      const containers = listProjectContainers(name, 'coding');
      if (containers.length > 0) {
        const statuses = containers.map((cm) => cm.status);
        if (statuses.includes('running')) {
          agentStatus = 'running';
          agentRunning = true;
        } else if (statuses.includes('completed')) {
          agentStatus = 'completed';
        } else if (statuses.includes('stopped')) {
          agentStatus = 'stopped';
        } else {
          agentStatus = 'not_created';
        }
      } else {
        agentStatus = 'not_created';
      }
    } catch {
      // If error checking containers, leave as null
    }

    result.push({
      name,
      git_url: info.gitUrl,
      local_path: localPath,
      is_new: info.isNew,
      has_spec: hasSpec,
      wizard_incomplete: wizardIncomplete,
      stats,
      target_container_count: info.targetContainerCount,
      agent_status: agentStatus,
      agent_running: agentRunning,
      agent_model: agentModel,
    });
  }

  return c.json(result);
});

// POST /api/projects - Create a new project
projectsRouter.post('/', async (c) => {
  const project = await parseBody(c, ProjectCreateSchema);
  const name = validateProjectNameParam(project.name);
  const projectsDir = getProjectsDir();
  const localPath = join(projectsDir, name);

  // Check if project name already registered
  const existing = getProjectPath(name);
  if (existing && existsSync(existing)) {
    throw new HTTPException(409, { message: `Project '${name}' already exists` });
  }

  // Clone the repository
  if (!existsSync(localPath)) {
    const result = cloneRepository(project.git_url, localPath);
    if (!result.success) {
      throw new HTTPException(500, { message: result.message });
    }
  }

  // Scaffold prompts
  scaffoldProjectPrompts(localPath);

  // Register in registry
  try {
    await registerProject(name, project.git_url);
  } catch (e) {
    throw new HTTPException(500, { message: `Failed to register project: ${e}` });
  }

  return c.json({
    name,
    git_url: project.git_url,
    local_path: localPath.replace(/\\/g, '/'),
    is_new: project.is_new,
    has_spec: false,
    stats: { passing: 0, in_progress: 0, total: 0, percentage: 0 },
    target_container_count: 1,
  });
});

// GET /api/projects/:name - Get project details
projectsRouter.get('/:name', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  const info = getProjectInfo(name);

  if (!info) {
    throw new HTTPException(404, { message: `Project '${name}' not found in registry` });
  }

  if (!existsSync(info.localPath)) {
    throw new HTTPException(404, { message: `Project directory no longer exists: ${info.localPath}` });
  }

  const hasSpec = hasProjectPrompts(info.localPath);
  const stats = getProjectStats(info.localPath, name);
  const promptsDir = getProjectPromptsDir(info.localPath);
  const agentModel = readAgentModel(info.localPath);

  return c.json({
    name,
    git_url: info.gitUrl,
    local_path: info.localPath,
    is_new: info.isNew,
    has_spec: hasSpec,
    stats,
    prompts_dir: promptsDir,
    target_container_count: info.targetContainerCount,
    agent_model: agentModel,
  });
});

// DELETE /api/projects/:name - Delete a project
projectsRouter.delete('/:name', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  const deleteFiles = c.req.query('delete_files') === 'true';
  const projectDir = getProjectPath(name);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  // Check if agent is running
  const lockFile = join(projectDir, '.agent.lock');
  if (existsSync(lockFile)) {
    throw new HTTPException(409, {
      message: 'Cannot delete project while agent is running. Stop the agent first.',
    });
  }

  // Optionally delete files
  if (deleteFiles && existsSync(projectDir)) {
    try {
      rmSync(projectDir, { recursive: true, force: true });
    } catch (e) {
      throw new HTTPException(500, { message: `Failed to delete project files: ${e}` });
    }
  }

  // Unregister from registry
  await unregisterProject(name);

  return c.json({
    success: true,
    message: `Project '${name}' deleted` + (deleteFiles ? ' (files removed)' : ' (files preserved)'),
  });
});

// GET /api/projects/:name/prompts - Get project prompts
projectsRouter.get('/:name/prompts', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  const projectDir = getProjectPath(name);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  const promptsDir = getProjectPromptsDir(projectDir);

  const readFile = (filename: string): string => {
    const filepath = join(promptsDir, filename);
    if (existsSync(filepath)) {
      try {
        return readFileSync(filepath, 'utf-8');
      } catch {
        return '';
      }
    }
    return '';
  };

  return c.json({
    app_spec: readFile('app_spec.txt'),
    initializer_prompt: readFile('initializer_prompt.md'),
    coding_prompt: readFile('coding_prompt.md'),
  });
});

// PUT /api/projects/:name/prompts - Update project prompts
projectsRouter.put('/:name/prompts', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  const prompts = await parseBody(c, ProjectPromptsUpdateSchema);
  const projectDir = getProjectPath(name);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  const promptsDir = getProjectPromptsDir(projectDir);
  mkdirSync(promptsDir, { recursive: true });

  const writeFile = (filename: string, content: string | null | undefined): void => {
    if (content !== null && content !== undefined) {
      const filepath = join(promptsDir, filename);
      writeFileSync(filepath, content, 'utf-8');
    }
  };

  writeFile('app_spec.txt', prompts.app_spec);
  writeFile('initializer_prompt.md', prompts.initializer_prompt);
  writeFile('coding_prompt.md', prompts.coding_prompt);

  return c.json({ success: true, message: 'Prompts updated' });
});

// GET /api/projects/:name/stats - Get project statistics
projectsRouter.get('/:name/stats', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  const projectDir = getProjectPath(name);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  return c.json(getProjectStats(projectDir, name));
});

// GET /api/projects/:name/wizard-status - Get wizard status
projectsRouter.get('/:name/wizard-status', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  const projectDir = getProjectPath(name);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  const wizardFile = getWizardStatusPath(projectDir);
  if (!existsSync(wizardFile)) {
    return c.json(null);
  }

  try {
    const data = JSON.parse(readFileSync(wizardFile, 'utf-8'));
    return c.json(data);
  } catch (e) {
    throw new HTTPException(500, { message: `Invalid wizard status file: ${e}` });
  }
});

// PUT /api/projects/:name/wizard-status - Update wizard status
projectsRouter.put('/:name/wizard-status', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  const status = await parseBody(c, WizardStatusSchema);
  const projectDir = getProjectPath(name);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  const wizardFile = getWizardStatusPath(projectDir);
  mkdirSync(join(projectDir, 'prompts'), { recursive: true });
  writeFileSync(wizardFile, JSON.stringify(status, null, 2), 'utf-8');

  return c.json(status);
});

// DELETE /api/projects/:name/wizard-status - Delete wizard status
projectsRouter.delete('/:name/wizard-status', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  const projectDir = getProjectPath(name);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  const wizardFile = getWizardStatusPath(projectDir);
  if (existsSync(wizardFile)) {
    unlinkSync(wizardFile);
  }

  return c.json({ success: true, message: 'Wizard status cleared' });
});

// PATCH /api/projects/:name/settings - Update project settings
projectsRouter.patch('/:name/settings', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  const settings = await parseBody(c, ProjectSettingsUpdateSchema);
  const projectDir = getProjectPath(name);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  // Validate the model ID
  if (!VALID_MODELS.includes(settings.agent_model)) {
    throw new HTTPException(400, {
      message: `Invalid model. Must be one of: ${VALID_MODELS.join(', ')}`,
    });
  }

  // Write the config (local-only, not committed to git)
  writeAgentConfig(projectDir, settings.agent_model);

  return c.json({
    success: true,
    message: `Agent model set to ${settings.agent_model}`,
    agent_model: settings.agent_model,
  });
});

// GET /api/projects/:name/settings - Get project settings
projectsRouter.get('/:name/settings', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  const projectDir = getProjectPath(name);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  return c.json({
    agent_model: readAgentModel(projectDir),
  });
});

// POST /api/projects/add-existing - Add an existing repository
projectsRouter.post('/add-existing', async (c) => {
  const request = await parseBody(c, AddExistingRepoRequestSchema);
  const name = validateProjectNameParam(request.name);
  const projectsDir = getProjectsDir();
  const localPath = join(projectsDir, name);

  // Check if project name already registered
  const existing = getProjectPath(name);
  if (existing && existsSync(existing)) {
    throw new HTTPException(409, { message: `Project '${name}' already exists` });
  }

  // Clone the repository
  if (!existsSync(localPath)) {
    const result = cloneRepository(request.git_url, localPath);
    if (!result.success) {
      throw new HTTPException(500, { message: result.message });
    }
  }

  // Initialize beads if needed
  const beadsResult = initBeadsIfNeeded(localPath);
  if (!beadsResult.success) {
    throw new HTTPException(500, { message: beadsResult.message });
  }

  // Scaffold minimal prompts (preserving existing files)
  scaffoldExistingRepo(localPath);

  // Register with is_new=False (existing project, no wizard)
  try {
    await registerProject(name, request.git_url);
  } catch (e) {
    throw new HTTPException(500, { message: `Failed to register project: ${e}` });
  }

  // Get stats (beads should be initialized now)
  const stats = getProjectStats(localPath, name);

  return c.json({
    name,
    git_url: request.git_url,
    local_path: localPath.replace(/\\/g, '/'),
    is_new: false,
    has_spec: false, // Existing repos don't have app_spec
    wizard_incomplete: false,
    stats,
    target_container_count: 1,
  });
});

// PUT /api/projects/:name/containers/count - Update container count
projectsRouter.put('/:name/containers/count', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  const body = await parseBody(c, ContainerCountUpdateSchema);

  if (!getProjectPath(name)) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  const success = updateTargetContainerCount(name, body.target_count);

  if (!success) {
    throw new HTTPException(500, { message: 'Failed to update container count' });
  }

  return c.json({ success: true, target_count: body.target_count });
});

// GET /api/projects/:name/containers - List project containers
projectsRouter.get('/:name/containers', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));

  if (!getProjectPath(name)) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  // Get all containers from database
  const containers = listProjectContainers(name);
  const result = [];

  for (const cm of containers) {
    // Skip containers with invalid container numbers
    if (cm.containerNumber < 0) {
      continue;
    }

    let dockerName: string;
    if (cm.containerType === 'init' || cm.containerNumber === 0) {
      dockerName = `zerocoder-${name}-init`;
    } else {
      dockerName = `zerocoder-${name}-${cm.containerNumber}`;
    }

    // Get live status from Docker
    const liveStatus = getDockerContainerStatus(dockerName);
    const finalStatus = liveStatus || cm.status;

    result.push({
      id: cm.containerNumber,
      container_number: cm.containerNumber,
      container_type: cm.containerType,
      status: finalStatus,
      current_feature: cm.currentFeature,
      docker_container_id: cm.dockerContainerId,
      agent_type: null, // TODO: track agent type
      sdk_type: null, // TODO: track SDK type
    });
  }

  return c.json(result);
});

// POST /api/projects/:name/stop - Stop all containers
projectsRouter.post('/:name/stop', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  // const graceful = c.req.query('graceful') !== 'false'; // TODO: Use when implementing

  if (!getProjectPath(name)) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  // TODO: Implement container stopping via container manager
  // For now, return a placeholder response
  return c.json({
    success: true,
    message: 'Stop endpoint not yet implemented in TypeScript',
    stopped: 0,
  });
});

// =============================================================================
// Edit Mode Endpoints
// =============================================================================

// POST /api/projects/:name/edit/start - Enter edit mode
projectsRouter.post('/:name/edit/start', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  const projectDir = getProjectPath(name);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  // Check if already in edit mode
  if (editModeProjects.has(name)) {
    return c.json({ success: true, message: 'Already in edit mode', edit_mode: true });
  }

  // TODO: Check if agents are running
  // TODO: Pull latest and sync beads via LocalProjectManager

  editModeProjects.add(name);

  return c.json({ success: true, message: 'Edit mode started', edit_mode: true });
});

// POST /api/projects/:name/edit/save - Save and exit edit mode
projectsRouter.post('/:name/edit/save', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  // const commitMessage = c.req.query('commit_message') || 'Update tasks'; // TODO: Use when implementing

  if (!getProjectPath(name)) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  if (!editModeProjects.has(name)) {
    throw new HTTPException(400, { message: 'Project is not in edit mode' });
  }

  // TODO: Push changes via LocalProjectManager

  editModeProjects.delete(name);

  return c.json({ success: true, message: 'Changes saved and edit mode exited', edit_mode: false });
});

// POST /api/projects/:name/tasks - Create a task
projectsRouter.post('/:name/tasks', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  await parseBody(c, TaskCreateSchema); // Validate body but don't use yet

  if (!getProjectPath(name)) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  if (!editModeProjects.has(name)) {
    throw new HTTPException(400, {
      message: 'Project must be in edit mode to create tasks. Call POST /{name}/edit/start first.',
    });
  }

  // TODO: Create task via LocalProjectManager

  return c.json({
    success: true,
    message: 'Task creation not yet implemented in TypeScript',
    task_id: null,
  });
});

// PATCH /api/projects/:name/tasks/:taskId - Update a task
projectsRouter.patch('/:name/tasks/:taskId', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  validateTaskId(c.req.param('taskId')); // Validate but don't use yet
  await parseBody(c, TaskUpdateSchema); // Validate body but don't use yet

  if (!getProjectPath(name)) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  if (!editModeProjects.has(name)) {
    throw new HTTPException(400, {
      message: 'Project must be in edit mode to update tasks. Call POST /{name}/edit/start first.',
    });
  }

  // TODO: Update task via LocalProjectManager

  return c.json({ success: true, message: 'Task update not yet implemented in TypeScript' });
});

// DELETE /api/projects/:name/tasks/:taskId - Delete a task
projectsRouter.delete('/:name/tasks/:taskId', async (c) => {
  const name = validateProjectNameParam(c.req.param('name'));
  validateTaskId(c.req.param('taskId')); // Validate but don't use yet

  if (!getProjectPath(name)) {
    throw new HTTPException(404, { message: `Project '${name}' not found` });
  }

  if (!editModeProjects.has(name)) {
    throw new HTTPException(400, {
      message: 'Project must be in edit mode to delete tasks. Call POST /{name}/edit/start first.',
    });
  }

  // TODO: Delete task via LocalProjectManager

  return c.json({ success: true, message: 'Task deletion not yet implemented in TypeScript' });
});

export { projectsRouter };
