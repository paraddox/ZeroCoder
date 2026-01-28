/**
 * Remote Agent Router
 * ===================
 *
 * Endpoints for controlling agents on remote machines.
 * Converted from server/routers/remote_agent.py
 *
 * Routes:
 * - POST /api/projects/:project_name/remote-agent/start
 * - POST /api/projects/:project_name/remote-agent/stop
 * - POST /api/projects/:project_name/remote-agent/graceful-stop
 * - GET /api/projects/:project_name/remote-agent/status
 */

import { Hono } from 'hono';
import { HTTPException } from 'hono/http-exception';

import { RemoteAgentStartRequestSchema } from '@zerocoder/shared';

import {
  getProjectInfo,
  getRemoteMachine,
  createRemoteAgent,
  updateRemoteAgent,
  getRemoteAgentsForProject,
} from '../db/crud.js';

import {
  getOrCreateRemoteManager,
  getAllRemoteManagers,
} from '../services/remote-machine-manager.js';

// =============================================================================
// Router Setup
// =============================================================================

const remoteAgentRouter = new Hono();

// =============================================================================
// Validation Helpers
// =============================================================================

/**
 * Parse and validate JSON body with a Zod schema.
 */
async function parseBody<T>(
  c: { req: { json: () => Promise<unknown> } },
  schema: { safeParse: (data: unknown) => { success: true; data: T } | { success: false; error: { message: string } } }
): Promise<T> {
  const body = await c.req.json();
  const result = schema.safeParse(body);
  if (!result.success) {
    throw new HTTPException(400, { message: `Validation error: ${result.error.message}` });
  }
  return result.data;
}

// =============================================================================
// Route Handlers
// =============================================================================

/**
 * POST /api/projects/:project_name/remote-agent/start
 * Start an agent on a remote machine for the given project.
 */
remoteAgentRouter.post('/:project_name/remote-agent/start', async (c) => {
  const projectName = c.req.param('project_name');
  const request = await parseBody(c, RemoteAgentStartRequestSchema);

  // Validate project exists
  const projectInfo = getProjectInfo(projectName);
  if (!projectInfo) {
    throw new HTTPException(404, { message: 'Project not found' });
  }

  // Validate machine exists
  const machine = getRemoteMachine(request.machine_id);
  if (!machine) {
    throw new HTTPException(404, { message: 'Remote machine not found' });
  }

  // Get git URL for the project
  const gitUrl = projectInfo.gitUrl;
  if (!gitUrl) {
    throw new HTTPException(400, { message: 'Project has no git URL' });
  }

  // Determine agent number (find next available)
  const existingAgents = getRemoteAgentsForProject(projectName);
  const usedNumbers = new Set(
    existingAgents
      .filter((a) => a.machineId === request.machine_id)
      .map((a) => a.agentNumber)
  );
  let agentNumber = 1;
  while (usedNumbers.has(agentNumber)) {
    agentNumber++;
  }

  // Create agent record
  const agentId = createRemoteAgent(projectName, request.machine_id, agentNumber);

  // Start the remote manager
  try {
    const manager = await getOrCreateRemoteManager(
      projectName,
      request.machine_id,
      gitUrl,
      agentNumber,
      agentId
    );
    const [success, message] = await manager.start();
    if (!success) {
      throw new HTTPException(500, { message });
    }

    return c.json({
      success: true,
      message: `Agent started on ${machine.name}`,
      agent_id: agentId,
    });
  } catch (e) {
    if (e instanceof HTTPException) {
      throw e;
    }
    const errorMsg = e instanceof Error ? e.message : String(e);
    console.error(`Failed to start remote agent: ${errorMsg}`);
    updateRemoteAgent(agentId, { status: 'stopped' });
    throw new HTTPException(500, { message: errorMsg });
  }
});

/**
 * POST /api/projects/:project_name/remote-agent/stop
 * Stop all remote agents for a project.
 */
remoteAgentRouter.post('/:project_name/remote-agent/stop', async (c) => {
  const projectName = c.req.param('project_name');

  const managers = getAllRemoteManagers(projectName);
  if (managers.length === 0) {
    throw new HTTPException(404, { message: 'No remote agents running' });
  }

  const results = [];
  for (const manager of managers) {
    const [success, msg] = await manager.stop();
    results.push({
      agent_number: manager.agentNumber,
      success,
      message: msg,
    });
  }

  return c.json({ success: true, results });
});

/**
 * POST /api/projects/:project_name/remote-agent/graceful-stop
 * Request graceful stop for all remote agents.
 */
remoteAgentRouter.post('/:project_name/remote-agent/graceful-stop', async (c) => {
  const projectName = c.req.param('project_name');

  const managers = getAllRemoteManagers(projectName);
  if (managers.length === 0) {
    throw new HTTPException(404, { message: 'No remote agents running' });
  }

  for (const manager of managers) {
    await manager.gracefulStop();
  }

  return c.json({
    success: true,
    message: 'Graceful stop requested for all remote agents',
  });
});

/**
 * GET /api/projects/:project_name/remote-agent/status
 * Get status of all remote agents for a project.
 */
remoteAgentRouter.get('/:project_name/remote-agent/status', async (c) => {
  const projectName = c.req.param('project_name');

  const agents = getRemoteAgentsForProject(projectName);
  return c.json(agents);
});

export { remoteAgentRouter };
