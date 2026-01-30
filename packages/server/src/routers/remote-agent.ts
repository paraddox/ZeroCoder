/**
 * Remote Agent Router
 * ===================
 *
 * Endpoints for controlling agents on remote machines.
 * Supports both legacy SSH-based agents and new daemon-based agents.
 *
 * Routes:
 * - POST /api/projects/:project_name/remote-agent/start
 * - POST /api/projects/:project_name/remote-agent/stop
 * - POST /api/projects/:project_name/remote-agent/graceful-stop
 * - GET /api/projects/:project_name/remote-agent/status
 * - POST /api/machines/:machine_id/daemon/deploy
 * - GET /api/machines/:machine_id/daemon/status
 * - GET /api/machines/:machine_id/daemon/health
 * - POST /api/machines/:machine_id/daemon/shutdown
 */

import { Hono } from 'hono';
import { HTTPException } from 'hono/http-exception';
import { readFileSync } from 'fs';
import { homedir } from 'os';

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
  deployDaemon,
  checkDaemonHealth,
  getDaemonStatus,
  assignWorkToDaemon,
  stopDaemon,
  shutdownDaemon,
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

// =============================================================================
// Daemon-based Agent Routes
// =============================================================================

/**
 * POST /api/projects/:project_name/remote-agent/daemon/start
 * Start work on a daemon-based remote agent.
 */
remoteAgentRouter.post('/:project_name/remote-agent/daemon/start', async (c) => {
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

  // Read SSH key for the project
  const sshKeyPath = process.env['GIT_SSH_KEY_PATH'] ?? `${homedir()}/.ssh/id_ed25519`;
  let sshKey: string;
  try {
    sshKey = readFileSync(sshKeyPath, 'utf8');
  } catch {
    throw new HTTPException(500, { message: `Cannot read SSH key from ${sshKeyPath}` });
  }

  // Assign work to daemon
  const result = await assignWorkToDaemon(request.machine_id, gitUrl, projectName, sshKey);

  if (!result.success) {
    throw new HTTPException(500, { message: result.message });
  }

  return c.json({
    success: true,
    message: `Work assigned to daemon on ${machine.name}`,
    machine_name: machine.name,
  });
});

/**
 * POST /api/projects/:project_name/remote-agent/daemon/stop
 * Stop daemon-based agent (hard stop).
 */
remoteAgentRouter.post('/:project_name/remote-agent/daemon/stop', async (c) => {
  // projectName intentionally unused - endpoint is per-machine, not per-project
  const request = await parseBody(c, RemoteAgentStartRequestSchema);

  const machine = getRemoteMachine(request.machine_id);
  if (!machine) {
    throw new HTTPException(404, { message: 'Remote machine not found' });
  }

  const result = await stopDaemon(request.machine_id, true);
  return c.json(result);
});

/**
 * POST /api/projects/:project_name/remote-agent/daemon/graceful-stop
 * Graceful stop daemon-based agent.
 */
remoteAgentRouter.post('/:project_name/remote-agent/daemon/graceful-stop', async (c) => {
  // projectName intentionally unused - endpoint is per-machine, not per-project
  const request = await parseBody(c, RemoteAgentStartRequestSchema);

  const machine = getRemoteMachine(request.machine_id);
  if (!machine) {
    throw new HTTPException(404, { message: 'Remote machine not found' });
  }

  const result = await stopDaemon(request.machine_id, false);
  return c.json(result);
});

// =============================================================================
// Daemon Management Routes (machine-level, not project-level)
// =============================================================================

/**
 * POST /api/machines/:machine_id/daemon/deploy
 * Deploy the daemon to a remote machine.
 */
remoteAgentRouter.post('/machines/:machine_id/daemon/deploy', async (c) => {
  const machineId = parseInt(c.req.param('machine_id'), 10);

  const machine = getRemoteMachine(machineId);
  if (!machine) {
    throw new HTTPException(404, { message: 'Remote machine not found' });
  }

  // Daemon secret for auth (optional)
  const daemonSecret = process.env['DAEMON_SECRET'];

  // Deploy daemon by SCP-ing pre-built files (no longer needs ZEROCODER_REPO_URL)
  const result = await deployDaemon(machineId, undefined, daemonSecret);

  if (!result.success) {
    throw new HTTPException(500, { message: result.message });
  }

  return c.json({
    success: true,
    message: result.message,
    port: result.port,
  });
});

/**
 * GET /api/machines/:machine_id/daemon/status
 * Get daemon status on a remote machine.
 */
remoteAgentRouter.get('/machines/:machine_id/daemon/status', async (c) => {
  const machineId = parseInt(c.req.param('machine_id'), 10);

  const machine = getRemoteMachine(machineId);
  if (!machine) {
    throw new HTTPException(404, { message: 'Remote machine not found' });
  }

  const status = await getDaemonStatus(machineId);

  if (!status) {
    return c.json({
      success: false,
      error: 'Could not reach daemon',
      machine_name: machine.name,
    });
  }

  return c.json({
    success: true,
    machine_name: machine.name,
    ...status,
  });
});

/**
 * GET /api/machines/:machine_id/daemon/health
 * Check daemon health on a remote machine.
 */
remoteAgentRouter.get('/machines/:machine_id/daemon/health', async (c) => {
  const machineId = parseInt(c.req.param('machine_id'), 10);

  const machine = getRemoteMachine(machineId);
  if (!machine) {
    throw new HTTPException(404, { message: 'Remote machine not found' });
  }

  const healthy = await checkDaemonHealth(machineId);

  return c.json({
    healthy,
    machine_name: machine.name,
  });
});

/**
 * POST /api/machines/:machine_id/daemon/shutdown
 * Shutdown daemon on a remote machine.
 */
remoteAgentRouter.post('/machines/:machine_id/daemon/shutdown', async (c) => {
  const machineId = parseInt(c.req.param('machine_id'), 10);

  const machine = getRemoteMachine(machineId);
  if (!machine) {
    throw new HTTPException(404, { message: 'Remote machine not found' });
  }

  const result = await shutdownDaemon(machineId);
  return c.json(result);
});

export { remoteAgentRouter };
