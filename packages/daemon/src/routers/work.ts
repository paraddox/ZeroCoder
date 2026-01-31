/**
 * Work Router
 * ===========
 *
 * POST /work - Receive repository for work assignment
 */

import { Hono } from 'hono';
import { HTTPException } from 'hono/http-exception';
import { z } from 'zod';

import { createLogger } from '../utils/logger.js';
import { setupRepository, getProjectPath } from '../services/repo-manager.js';
import { startWork, isRunning } from '../services/agent-orchestrator.js';

const log = createLogger('work-router');

const workRouter = new Hono();

/**
 * Request schema for POST /work
 * ssh_key is optional - if not provided, uses default SSH key (~/.ssh/id_ed25519)
 * This allows containers with baked-in SSH keys to work without passing the key.
 */
const WorkRequestSchema = z.object({
  repo_url: z.string().min(1),
  project_name: z.string().min(1).max(50),
  ssh_key: z.string().optional(),
});

/**
 * POST /work
 *
 * Receive repository for work assignment.
 *
 * 1. Save SSH key to ~/.ssh/zerocoder_{project_name}
 * 2. Clone repo if not exists (or pull if exists)
 * 3. Run bd onboard to sync beads
 * 4. Start agent flow
 */
workRouter.post('/work', async (c) => {
  // Check if already running
  if (isRunning()) {
    throw new HTTPException(409, { message: 'Agent is already running' });
  }

  // Parse and validate request
  const body = await c.req.json();
  const parseResult = WorkRequestSchema.safeParse(body);

  if (!parseResult.success) {
    throw new HTTPException(400, {
      message: `Validation error: ${parseResult.error.message}`,
    });
  }

  const { repo_url, project_name, ssh_key } = parseResult.data;

  log.info('Work request received', { project_name, repo_url, hasSshKey: !!ssh_key });

  // Set up the repository (ssh_key is optional - uses default if not provided)
  const setupResult = await setupRepository(repo_url, project_name, ssh_key);

  if (!setupResult.success) {
    throw new HTTPException(500, { message: setupResult.message });
  }

  const projectPath = setupResult.projectPath ?? getProjectPath(project_name);

  // Start the agent work
  const startResult = await startWork(project_name, repo_url, projectPath);

  if (!startResult.success) {
    throw new HTTPException(500, { message: startResult.message });
  }

  return c.json({
    success: true,
    message: 'Work started',
    project_name,
    project_path: projectPath,
  });
});

export { workRouter };
