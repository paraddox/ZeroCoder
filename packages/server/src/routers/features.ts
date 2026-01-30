/**
 * Features Router
 * ===============
 *
 * API endpoints for feature/test case management using beads.
 * All beads operations run on the host via bd CLI commands.
 */

import { Hono } from 'hono';
import { HTTPException } from 'hono/http-exception';
import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';

import { z } from 'zod';
import {
  FeatureCreateSchema,
  FeatureUpdateSchema,
  type FeatureResponse,
} from '@zerocoder/shared';

import {
  getProjectPath,
  getProjectGitUrl,
} from '../db/crud.js';
import {
  getProjectTasks,
  getInProgressFeatureIds,
} from '../services/project-sync.js';

// =============================================================================
// Types
// =============================================================================

interface BeadsTask {
  id: string;
  title: string;
  status: string;
  priority: number;
  labels: string[];
  description?: string;
  body?: string;
}

interface FeatureListResponse {
  pending: FeatureResponse[];
  in_progress: FeatureResponse[];
  done: FeatureResponse[];
}

// =============================================================================
// Router Setup
// =============================================================================

const featuresRouter = new Hono();

// =============================================================================
// Validation Helpers
// =============================================================================

/**
 * Parse and validate JSON body with a Zod schema.
 */
async function parseBody<T extends z.ZodType>(
  c: { req: { json: () => Promise<unknown> } },
  schema: T
): Promise<z.infer<T>> {
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
function validateProjectName(name: string): string {
  if (!/^[a-zA-Z0-9_-]{1,50}$/.test(name)) {
    throw new HTTPException(400, { message: 'Invalid project name' });
  }
  return name;
}

// =============================================================================
// Beads CLI Helpers
// =============================================================================

/**
 * Run a bd command in the project directory.
 */
function runBeadsCommand(projectDir: string, args: string[]): { success: boolean; output: string; error?: string } {
  try {
    const result = execSync(['bd', '--no-daemon', ...args].join(' '), {
      cwd: projectDir,
      timeout: 30000,
      stdio: 'pipe',
      encoding: 'utf-8',
    });
    return { success: true, output: result.toString().trim() };
  } catch (e: unknown) {
    const err = e as Error & { stderr?: Buffer | string; stdout?: Buffer | string };
    const stderr = err.stderr?.toString() || err.message;

    // Handle DB out of sync error
    if (stderr.toLowerCase().includes('out of sync')) {
      try {
        execSync('bd --no-daemon sync --import-only', {
          cwd: projectDir,
          timeout: 30000,
          stdio: 'pipe',
        });
        // Retry the command
        const retryResult = execSync(['bd', '--no-daemon', ...args].join(' '), {
          cwd: projectDir,
          timeout: 30000,
          stdio: 'pipe',
          encoding: 'utf-8',
        });
        return { success: true, output: retryResult.toString().trim() };
      } catch {
        return { success: false, output: '', error: stderr };
      }
    }

    return { success: false, output: '', error: stderr };
  }
}

/**
 * Get all tasks from beads as JSON.
 */
function getBeadsTasks(projectDir: string): BeadsTask[] {
  const beadsDir = `${projectDir}/.beads`;
  if (!existsSync(beadsDir)) {
    return [];
  }

  const result = runBeadsCommand(projectDir, ['list', '--json', '--all', '--limit', '0']);
  if (!result.success || !result.output) {
    return [];
  }

  try {
    return JSON.parse(result.output) as BeadsTask[];
  } catch {
    return [];
  }
}

/**
 * Convert a beads task to feature format.
 */
function beadsTaskToFeature(task: BeadsTask): FeatureResponse {
  // Extract category from labels (first label)
  const labels = task.labels || [];
  const category = labels[0] || '';

  // Parse steps from description
  const description = task.description || task.body || '';
  const steps: string[] = [];
  if (description) {
    const stepMatches = description.match(/^\d+\.\s*(.+)$/gm);
    if (stepMatches) {
      for (const match of stepMatches) {
        const stepText = match.replace(/^\d+\.\s*/, '');
        steps.push(stepText);
      }
    }
  }

  const status = task.status || 'open';

  return {
    id: String(task.id),
    priority: task.priority ?? 999,
    category,
    name: task.title || '',
    description,
    steps,
    passes: status === 'closed',
    in_progress: status === 'in_progress',
  };
}

// =============================================================================
// Route Handlers
// =============================================================================

// GET /api/projects/:name/features - List all features
featuresRouter.get('/:name/features', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));
  const projectDir = getProjectPath(projectName);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${projectName}' not found in registry` });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  // Get features from beads (syncs from remote if project has remote agents)
  const tasks = getProjectTasks(projectName);
  const features = tasks.map(beadsTaskToFeature);

  // Get features currently being worked on (containers + remote agents)
  const inProgressIds = getInProgressFeatureIds(projectName);

  const pending: FeatureResponse[] = [];
  const inProgress: FeatureResponse[] = [];
  const done: FeatureResponse[] = [];

  for (const f of features) {
    if (f.passes) {
      done.push(f);
    } else if (inProgressIds.has(f.id) || f.in_progress) {
      inProgress.push(f);
    } else {
      pending.push(f);
    }
  }

  const response: FeatureListResponse = { pending, in_progress: inProgress, done };
  return c.json(response);
});

// POST /api/projects/:name/features - Create a new feature
featuresRouter.post('/:name/features', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));
  const feature = await parseBody(c, FeatureCreateSchema);
  const projectDir = getProjectPath(projectName);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${projectName}' not found in registry` });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  const gitUrl = getProjectGitUrl(projectName);
  if (!gitUrl) {
    throw new HTTPException(404, { message: 'Project has no git URL' });
  }

  // Build full description with steps if provided
  let fullDescription = feature.description;
  if (feature.steps && feature.steps.length > 0) {
    const stepText = feature.steps.map((s, i) => `${i + 1}. ${s}`).join('\n');
    if (feature.description) {
      fullDescription = `${feature.description}\n\n${stepText}`;
    } else {
      fullDescription = stepText;
    }
  }

  const priority = feature.priority ?? 2;
  const args = [
    'create',
    '--title', `"${feature.name.replace(/"/g, '\\"')}"`,
    '--type', 'feature',
    '--priority', `P${priority}`,
    '--json',
  ];

  if (fullDescription) {
    args.push('--description', `"${fullDescription.replace(/"/g, '\\"')}"`);
  }

  if (feature.category) {
    args.push('--labels', feature.category);
  }

  const result = runBeadsCommand(projectDir, args);

  if (!result.success) {
    throw new HTTPException(500, { message: `Failed to create feature: ${result.error}` });
  }

  // Try to parse the created feature from output
  let createdData: { id?: string } = {};
  try {
    createdData = JSON.parse(result.output);
  } catch {
    // Output might not be JSON
  }

  // If we got an ID, fetch the created feature
  if (createdData.id) {
    const tasks = getBeadsTasks(projectDir);
    const task = tasks.find(t => String(t.id) === String(createdData.id));
    if (task) {
      return c.json(beadsTaskToFeature(task));
    }
  }

  // Fallback: find by name
  const tasks = getBeadsTasks(projectDir);
  const task = tasks.find(t => t.title === feature.name);
  if (task) {
    return c.json(beadsTaskToFeature(task));
  }

  throw new HTTPException(500, { message: 'Failed to create feature' });
});

// GET /api/projects/:name/features/:featureId - Get a specific feature
featuresRouter.get('/:name/features/:featureId', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));
  const featureId = c.req.param('featureId');
  const projectDir = getProjectPath(projectName);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${projectName}' not found in registry` });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  const tasks = getBeadsTasks(projectDir);
  const task = tasks.find(t => String(t.id) === featureId);

  if (!task) {
    throw new HTTPException(404, { message: `Feature ${featureId} not found` });
  }

  return c.json(beadsTaskToFeature(task));
});

// DELETE /api/projects/:name/features/:featureId - Delete a feature
featuresRouter.delete('/:name/features/:featureId', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));
  const featureId = c.req.param('featureId');
  const projectDir = getProjectPath(projectName);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${projectName}' not found in registry` });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  // Check if feature exists first
  const tasks = getBeadsTasks(projectDir);
  const task = tasks.find(t => String(t.id) === featureId);
  if (!task) {
    throw new HTTPException(404, { message: `Feature ${featureId} not found` });
  }

  const result = runBeadsCommand(projectDir, ['delete', featureId, '--force']);

  if (!result.success) {
    throw new HTTPException(500, { message: `Failed to delete feature: ${result.error}` });
  }

  return c.json({ success: true, message: `Feature ${featureId} deleted` });
});

// PATCH /api/projects/:name/features/:featureId/skip - Skip a feature
featuresRouter.patch('/:name/features/:featureId/skip', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));
  const featureId = c.req.param('featureId');
  const projectDir = getProjectPath(projectName);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${projectName}' not found in registry` });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  // Check if feature exists
  const tasks = getBeadsTasks(projectDir);
  const task = tasks.find(t => String(t.id) === featureId);
  if (!task) {
    throw new HTTPException(404, { message: `Feature ${featureId} not found` });
  }

  // Set priority to P4 (backlog)
  const result = runBeadsCommand(projectDir, ['update', featureId, '--priority', 'P4']);

  if (!result.success) {
    throw new HTTPException(500, { message: `Failed to skip feature: ${result.error}` });
  }

  return c.json({ success: true, message: `Feature ${featureId} moved to end of queue` });
});

// PATCH /api/projects/:name/features/:featureId - Update a feature
featuresRouter.patch('/:name/features/:featureId', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));
  const featureId = c.req.param('featureId');
  const update = await parseBody(c, FeatureUpdateSchema);
  const projectDir = getProjectPath(projectName);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${projectName}' not found in registry` });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  // Check if feature exists
  const tasks = getBeadsTasks(projectDir);
  const task = tasks.find(t => String(t.id) === featureId);
  if (!task) {
    throw new HTTPException(404, { message: `Feature ${featureId} not found` });
  }

  const args = ['update', featureId];

  if (update.name !== null && update.name !== undefined) {
    args.push('--title', `"${update.name.replace(/"/g, '\\"')}"`);
  }

  // Build full description with steps if provided
  if (update.description !== null && update.description !== undefined || update.steps !== null && update.steps !== undefined) {
    let fullDescription = update.description ?? '';
    if (update.steps && update.steps.length > 0) {
      const stepText = update.steps.map((s, i) => `${i + 1}. ${s}`).join('\n');
      if (fullDescription) {
        fullDescription = `${fullDescription}\n\n${stepText}`;
      } else {
        fullDescription = stepText;
      }
    }
    if (fullDescription) {
      args.push('--description', `"${fullDescription.replace(/"/g, '\\"')}"`);
    }
  }

  if (update.priority !== null && update.priority !== undefined) {
    args.push('--priority', `P${update.priority}`);
  }

  // Must have at least one update
  if (args.length === 2) {
    throw new HTTPException(400, { message: 'No update fields provided' });
  }

  const result = runBeadsCommand(projectDir, args);

  if (!result.success) {
    throw new HTTPException(500, { message: `Failed to update feature: ${result.error}` });
  }

  // Handle category/label update separately if needed
  if (update.category !== null && update.category !== undefined) {
    runBeadsCommand(projectDir, ['label', featureId, '--set', update.category]);
  }

  // Fetch and return the updated feature
  const updatedTasks = getBeadsTasks(projectDir);
  const updatedTask = updatedTasks.find(t => String(t.id) === featureId);
  if (updatedTask) {
    return c.json(beadsTaskToFeature(updatedTask));
  }

  throw new HTTPException(500, { message: 'Failed to update feature' });
});

// PATCH /api/projects/:name/features/:featureId/reopen - Reopen a completed feature
featuresRouter.patch('/:name/features/:featureId/reopen', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));
  const featureId = c.req.param('featureId');
  const projectDir = getProjectPath(projectName);

  if (!projectDir) {
    throw new HTTPException(404, { message: `Project '${projectName}' not found in registry` });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  // Check if feature exists and is closed
  const tasks = getBeadsTasks(projectDir);
  const task = tasks.find(t => String(t.id) === featureId);
  if (!task) {
    throw new HTTPException(404, { message: `Feature ${featureId} not found` });
  }

  if (task.status !== 'closed') {
    throw new HTTPException(400, { message: 'Feature is not completed, cannot reopen' });
  }

  const result = runBeadsCommand(projectDir, ['reopen', featureId]);

  if (!result.success) {
    throw new HTTPException(500, { message: `Failed to reopen feature: ${result.error}` });
  }

  return c.json({ success: true, message: `Feature ${featureId} reopened` });
});

export { featuresRouter };
