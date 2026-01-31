/**
 * Remote Agent Router
 * ===================
 *
 * Endpoints for controlling agents on remote machines via daemon.
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
  listRemoteMachines,
} from '../db/crud.js';

import {
  deployDaemon,
  checkDaemonHealth,
  getDaemonStatus,
  assignWorkToDaemon,
  stopDaemon,
  shutdownDaemon,
  type DaemonStatus,
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
// Agent Routes (daemon-based)
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
 * POST /api/projects/:project_name/remote-agent/stop
 * Stop remote agents for a project (hard stop).
 */
remoteAgentRouter.post('/:project_name/remote-agent/stop', async (c) => {
  const projectName = c.req.param('project_name');

  // Get all machines and check which ones are running this project
  const machines = listRemoteMachines();
  const results = [];

  for (const machine of machines) {
    const status = await getDaemonStatus(machine.id);
    if (status && status.current_repo?.includes(projectName)) {
      const result = await stopDaemon(machine.id, true);
      results.push({ machine_id: machine.id, machine_name: machine.name, ...result });
    }
  }

  if (results.length === 0) {
    throw new HTTPException(404, { message: 'No remote agents running for this project' });
  }

  return c.json({ success: true, results });
});

/**
 * POST /api/projects/:project_name/remote-agent/graceful-stop
 * Request graceful stop for remote agents.
 */
remoteAgentRouter.post('/:project_name/remote-agent/graceful-stop', async (c) => {
  const projectName = c.req.param('project_name');

  // Get all machines and check which ones are running this project
  const machines = listRemoteMachines();
  const results = [];

  for (const machine of machines) {
    const status = await getDaemonStatus(machine.id);
    if (status && status.current_repo?.includes(projectName)) {
      const result = await stopDaemon(machine.id, false);
      results.push({ machine_id: machine.id, machine_name: machine.name, ...result });
    }
  }

  if (results.length === 0) {
    throw new HTTPException(404, { message: 'No remote agents running for this project' });
  }

  return c.json({ success: true, results });
});

/**
 * GET /api/projects/:project_name/remote-agent/status
 * Get status of remote agents for a project.
 * Queries all remote machines to find which ones are working on this project.
 */
remoteAgentRouter.get('/:project_name/remote-agent/status', async (c) => {
  const projectName = c.req.param('project_name');

  const machines = listRemoteMachines();
  const agents: Array<{
    machine_id: number;
    machine_name: string;
    status: DaemonStatus['status'];
    current_feature: string | null;
    agent_type: string | null;
    stats: DaemonStatus['stats'];
  }> = [];

  for (const machine of machines) {
    const status = await getDaemonStatus(machine.id);
    if (status && status.current_repo?.includes(projectName)) {
      agents.push({
        machine_id: machine.id,
        machine_name: machine.name,
        status: status.status,
        current_feature: status.current_feature,
        agent_type: status.agent_type,
        stats: status.stats,
      });
    }
  }

  return c.json(agents);
});

// =============================================================================
// Daemon Management Routes (machine-level)
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

  // Deploy daemon by SCP-ing pre-built files
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
