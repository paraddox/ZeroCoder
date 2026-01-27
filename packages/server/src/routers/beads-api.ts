/**
 * Beads API Router
 * ================
 *
 * Host-based API wrapper for beads commands. Agents call these endpoints instead
 * of running `bd` directly. The host runs `bd` commands on the project directory.
 *
 * This provides:
 * - Centralized beads access (no direct bd in containers)
 * - Concurrency control via unified BeadsManager
 * - Consistent JSON responses
 */

import { Hono } from 'hono';
import { HTTPException } from 'hono/http-exception';
import { z } from 'zod';

import {
  getBeadsManager,
  type BeadsTask,
} from '../services/beads-manager.js';
import {
  getContainer,
  updateContainerStatus,
  setLastClosedFeature,
} from '../db/crud.js';

// =============================================================================
// Validation Helpers
// =============================================================================

/**
 * Validate and sanitize project name to prevent path traversal.
 */
function validateProjectName(name: string): string {
  if (!/^[a-zA-Z0-9_-]{1,50}$/.test(name)) {
    throw new HTTPException(400, { message: 'Invalid project name' });
  }
  return name;
}

/**
 * Validate issue ID format.
 */
function validateIssueId(issueId: string): string {
  // Allow formats like: beads-1, feat-42, project-abc123
  if (!/^[a-zA-Z]+-[a-zA-Z0-9]+$/.test(issueId)) {
    throw new HTTPException(400, { message: 'Invalid issue ID format' });
  }
  return issueId;
}

// =============================================================================
// Request/Response Schemas
// =============================================================================

const IssueCreateSchema = z.object({
  title: z.string().min(1).max(200),
  description: z.string().default(''),
  type: z.string().default('task'), // task, bug, feature, epic
  priority: z.number().int().min(0).max(4).default(2), // 0=P0 (critical) to 4=P4 (backlog)
  labels: z.array(z.string()).default([]),
});

const IssueUpdateSchema = z.object({
  title: z.string().optional(),
  description: z.string().optional(),
  status: z.string().optional(), // open, in_progress, closed
  priority: z.number().int().min(0).max(4).optional(),
  assignee: z.string().optional(),
});

const IssueCloseSchema = z.object({
  reason: z.string().optional(),
});

const DependencyAddSchema = z.object({
  issue_id: z.string(),
  depends_on: z.string(),
});

const CommentAddSchema = z.object({
  comment: z.string().min(1),
});

// =============================================================================
// Helper Functions
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
 * Get container number from X-Container-Number header.
 */
function getContainerNumber(c: { req: { header: (name: string) => string | undefined } }): number | null {
  const header = c.req.header('X-Container-Number');
  if (header) {
    const num = parseInt(header, 10);
    if (!isNaN(num)) {
      return num;
    }
  }
  return null;
}

// =============================================================================
// Router Setup
// =============================================================================

const beadsApiRouter = new Hono();

// =============================================================================
// Route Handlers
// =============================================================================

// GET /api/projects/:name/beads/list - List all issues
beadsApiRouter.get('/:name/beads/list', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));
  const status = c.req.query('status');

  try {
    const manager = await getBeadsManager(projectName);
    let tasks: BeadsTask[];

    if (status) {
      tasks = manager.getTasksByStatus(status);
    } else {
      tasks = manager.getTasks();
    }

    return c.json(tasks);
  } catch (error) {
    const err = error as Error;
    throw new HTTPException(500, { message: err.message });
  }
});

// GET /api/projects/:name/beads/ready - List issues ready for work
beadsApiRouter.get('/:name/beads/ready', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));

  try {
    const manager = await getBeadsManager(projectName);
    const result = await manager.runReadCommand(['ready', '--json']);

    if (result.error) {
      throw new HTTPException(500, { message: result.error });
    }

    return c.json(result.data ?? []);
  } catch (error) {
    if (error instanceof HTTPException) throw error;
    const err = error as Error;
    throw new HTTPException(500, { message: err.message });
  }
});

// GET /api/projects/:name/beads/show/:issueId - Get issue details
beadsApiRouter.get('/:name/beads/show/:issueId', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));
  const issueId = validateIssueId(c.req.param('issueId'));

  try {
    const manager = await getBeadsManager(projectName);
    const result = await manager.runReadCommand(['show', issueId, '--json']);

    if (result.error) {
      if (result.error.toLowerCase().includes('not found')) {
        throw new HTTPException(404, { message: `Issue ${issueId} not found` });
      }
      throw new HTTPException(500, { message: result.error });
    }

    const data = result.data;
    if (Array.isArray(data) && data.length > 0) {
      return c.json(data[0]);
    }
    return c.json(data);
  } catch (error) {
    if (error instanceof HTTPException) throw error;
    const err = error as Error;
    throw new HTTPException(500, { message: err.message });
  }
});

// GET /api/projects/:name/beads/stats - Get project statistics
beadsApiRouter.get('/:name/beads/stats', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));

  try {
    const manager = await getBeadsManager(projectName);
    const stats = manager.getStats();
    return c.json(stats);
  } catch (error) {
    const err = error as Error;
    throw new HTTPException(500, { message: err.message });
  }
});

// POST /api/projects/:name/beads/create - Create a new issue
beadsApiRouter.post('/:name/beads/create', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));
  const issue = await parseBody(c, IssueCreateSchema);

  try {
    const manager = await getBeadsManager(projectName);
    const result = await manager.createIssue(
      issue.title,
      issue.type,
      issue.priority,
      issue.description,
      issue.labels.length > 0 ? issue.labels : undefined
    );

    if (result.error) {
      throw new HTTPException(500, { message: result.error });
    }

    return c.json(result.data ?? { success: true });
  } catch (error) {
    if (error instanceof HTTPException) throw error;
    const err = error as Error;
    throw new HTTPException(500, { message: err.message });
  }
});

// POST /api/projects/:name/beads/claim - Atomically claim the next available issue
beadsApiRouter.post('/:name/beads/claim', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));
  const containerNumber = getContainerNumber(c);

  try {
    const manager = await getBeadsManager(projectName);

    // Get list of ready issues (open, no blockers)
    const readyResult = await manager.runReadCommand(['ready', '--json']);
    if (readyResult.error) {
      throw new HTTPException(500, { message: readyResult.error });
    }

    const allIssues = (readyResult.data ?? []) as BeadsTask[];
    // Filter to only open issues (bd ready includes in_progress)
    const issues = allIssues.filter((i) => i.status === 'open');

    if (issues.length === 0) {
      return c.json({ success: false, message: 'No issues available to claim', issue: null });
    }

    // Get the first available open issue
    const issue = issues[0]!;
    const issueId = issue.id;

    if (!issueId) {
      throw new HTTPException(500, { message: 'Issue missing ID' });
    }

    // Claim it - update to in_progress
    const updateResult = await manager.updateIssue(issueId, { status: 'in_progress' });

    if (updateResult.error) {
      throw new HTTPException(500, { message: updateResult.error });
    }

    // Update container's current_feature in DB
    if (containerNumber !== null) {
      try {
        updateContainerStatus(projectName, containerNumber, 'coding', { currentFeature: issueId });
        console.debug(`Set current_feature=${issueId} for container ${containerNumber}`);
      } catch (e) {
        console.warn(`Failed to update container current_feature: ${e}`);
        // Don't fail the claim for tracking errors
      }
    }

    return c.json({
      success: true,
      message: `Claimed issue ${issueId}`,
      issue,
    });
  } catch (error) {
    if (error instanceof HTTPException) throw error;
    const err = error as Error;
    throw new HTTPException(500, { message: err.message });
  }
});

// PATCH /api/projects/:name/beads/update/:issueId - Update an issue
beadsApiRouter.patch('/:name/beads/update/:issueId', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));
  const issueId = validateIssueId(c.req.param('issueId'));
  const update = await parseBody(c, IssueUpdateSchema);

  // Must have at least one update field
  if (
    update.title === undefined &&
    update.description === undefined &&
    update.status === undefined &&
    update.priority === undefined &&
    update.assignee === undefined
  ) {
    throw new HTTPException(400, { message: 'No update fields provided' });
  }

  try {
    const manager = await getBeadsManager(projectName);
    const result = await manager.updateIssue(issueId, update);

    if (result.error) {
      if (result.error.toLowerCase().includes('not found')) {
        throw new HTTPException(404, { message: `Issue ${issueId} not found` });
      }
      throw new HTTPException(500, { message: result.error });
    }

    return c.json({ success: true, message: `Issue ${issueId} updated` });
  } catch (error) {
    if (error instanceof HTTPException) throw error;
    const err = error as Error;
    throw new HTTPException(500, { message: err.message });
  }
});

// POST /api/projects/:name/beads/close/:issueId - Close an issue
beadsApiRouter.post('/:name/beads/close/:issueId', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));
  const issueId = validateIssueId(c.req.param('issueId'));
  const containerNumber = getContainerNumber(c);

  let body: z.infer<typeof IssueCloseSchema> | null = null;
  try {
    body = await parseBody(c, IssueCloseSchema);
  } catch {
    // Body is optional for close
  }

  try {
    const manager = await getBeadsManager(projectName);
    const result = await manager.closeIssue(issueId, body?.reason);

    if (result.error) {
      if (result.error.toLowerCase().includes('not found')) {
        throw new HTTPException(404, { message: `Issue ${issueId} not found` });
      }
      throw new HTTPException(500, { message: result.error });
    }

    // Track which container closed this feature
    if (containerNumber !== null) {
      try {
        setLastClosedFeature(projectName, containerNumber, issueId);
        console.debug(`Tracked closed feature ${issueId} for container ${containerNumber}`);

        // Clear current_feature if it matches the closed issue
        const container = getContainer(projectName, containerNumber, 'coding');
        if (container && container.currentFeature === issueId) {
          updateContainerStatus(projectName, containerNumber, 'coding', { currentFeature: '' });
          console.debug(`Cleared current_feature for container ${containerNumber}`);
        }
      } catch (e) {
        console.warn(`Failed to track closed feature: ${e}`);
        // Don't fail the close operation for tracking errors
      }
    }

    return c.json({ success: true, message: `Issue ${issueId} closed` });
  } catch (error) {
    if (error instanceof HTTPException) throw error;
    const err = error as Error;
    throw new HTTPException(500, { message: err.message });
  }
});

// POST /api/projects/:name/beads/reopen/:issueId - Reopen an issue
beadsApiRouter.post('/:name/beads/reopen/:issueId', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));
  const issueId = validateIssueId(c.req.param('issueId'));

  try {
    const manager = await getBeadsManager(projectName);
    const result = await manager.reopenIssue(issueId);

    if (result.error) {
      if (result.error.toLowerCase().includes('not found')) {
        throw new HTTPException(404, { message: `Issue ${issueId} not found` });
      }
      throw new HTTPException(500, { message: result.error });
    }

    return c.json({ success: true, message: `Issue ${issueId} reopened` });
  } catch (error) {
    if (error instanceof HTTPException) throw error;
    const err = error as Error;
    throw new HTTPException(500, { message: err.message });
  }
});

// POST /api/projects/:name/beads/sync - Sync with git remote
beadsApiRouter.post('/:name/beads/sync', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));

  try {
    const manager = await getBeadsManager(projectName);
    const [success, message] = await manager.sync();

    if (!success) {
      throw new HTTPException(500, { message });
    }

    return c.json({ success: true, message: 'Beads synced with remote' });
  } catch (error) {
    if (error instanceof HTTPException) throw error;
    const err = error as Error;
    throw new HTTPException(500, { message: err.message });
  }
});

// POST /api/projects/:name/beads/dep/add - Add a dependency
beadsApiRouter.post('/:name/beads/dep/add', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));
  const body = await parseBody(c, DependencyAddSchema);

  const issueId = validateIssueId(body.issue_id);
  const dependsOn = validateIssueId(body.depends_on);

  try {
    const manager = await getBeadsManager(projectName);
    const result = await manager.addDependency(issueId, dependsOn);

    if (result.error) {
      throw new HTTPException(500, { message: result.error });
    }

    return c.json({ success: true, message: `Added dependency: ${issueId} depends on ${dependsOn}` });
  } catch (error) {
    if (error instanceof HTTPException) throw error;
    const err = error as Error;
    throw new HTTPException(500, { message: err.message });
  }
});

// POST /api/projects/:name/beads/comments/:issueId - Add a comment
beadsApiRouter.post('/:name/beads/comments/:issueId', async (c) => {
  const projectName = validateProjectName(c.req.param('name'));
  const issueId = validateIssueId(c.req.param('issueId'));
  const body = await parseBody(c, CommentAddSchema);

  try {
    const manager = await getBeadsManager(projectName);
    const result = await manager.addComment(issueId, body.comment);

    if (result.error) {
      if (result.error.toLowerCase().includes('not found')) {
        throw new HTTPException(404, { message: `Issue ${issueId} not found` });
      }
      throw new HTTPException(500, { message: result.error });
    }

    return c.json({ success: true, message: `Comment added to ${issueId}` });
  } catch (error) {
    if (error instanceof HTTPException) throw error;
    const err = error as Error;
    throw new HTTPException(500, { message: err.message });
  }
});

export { beadsApiRouter };
