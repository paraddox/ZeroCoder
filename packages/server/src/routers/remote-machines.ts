/**
 * Remote Machines Router
 * ======================
 *
 * CRUD endpoints for managing SSH remote machines.
 * Converted from server/routers/remote_machines.py
 */

import { Hono } from 'hono';
import { HTTPException } from 'hono/http-exception';
import { existsSync, readFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { Client as SSHClient } from 'ssh2';

import { RemoteMachineCreateSchema } from '@zerocoder/shared';

import {
  addRemoteMachine,
  removeRemoteMachine,
  listRemoteMachines,
  getRemoteMachine,
  updateRemoteMachineStatus,
  getAllActiveRemoteAgents,
  RegistryError,
} from '../db/crud.js';
import { deployDaemon } from '../services/remote-machine-manager.js';

// =============================================================================
// Router Setup
// =============================================================================

const remoteMachinesRouter = new Hono();

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
// SSH Connection Helper
// =============================================================================

/**
 * Test SSH connectivity to a remote machine.
 * Returns the username from 'whoami' if successful.
 */
async function testSSHConnection(
  host: string,
  port: number,
  username: string,
  sshKeyPath?: string | null
): Promise<string> {
  const expandedKeyPath = sshKeyPath ? sshKeyPath.replace(/^~/, homedir()) : undefined;
  const privateKey = expandedKeyPath ? readFileSync(expandedKeyPath) : undefined;

  return new Promise((resolve, reject) => {
    const client = new SSHClient();

    client.on('ready', () => {
      // Execute whoami command to verify connectivity
      client.exec('whoami', (err, stream) => {
        if (err) {
          client.end();
          reject(err);
          return;
        }

        let stdout = '';
        stream.on('data', (data: Buffer) => {
          stdout += data.toString();
        });

        stream.on('close', () => {
          client.end();
          resolve(stdout.trim());
        });

        stream.on('error', (err: Error) => {
          client.end();
          reject(err);
        });
      });
    });

    client.on('error', (err: Error) => {
      reject(err);
    });

    const connectConfig: {
      host: string;
      port: number;
      username: string;
      privateKey?: Buffer;
    } = {
      host,
      port,
      username,
    };

    if (privateKey) {
      connectConfig.privateKey = privateKey;
    }

    client.connect(connectConfig);
  });
}

/**
 * Test SSH connection and check for installed dependencies.
 */
async function testMachineWithDependencies(
  machine: {
    host: string;
    port: number;
    username: string;
    sshKeyPath: string | null;
  }
): Promise<{
  connected: boolean;
  user: string | null;
  gitInstalled: boolean;
  claudeInstalled: boolean;
  error: string | null;
}> {
  const result = {
    connected: false,
    user: null as string | null,
    gitInstalled: false,
    claudeInstalled: false,
    error: null as string | null,
  };

  const expandedKeyPath = machine.sshKeyPath
    ? machine.sshKeyPath.replace(/^~/, homedir())
    : undefined;
  const privateKey = expandedKeyPath ? readFileSync(expandedKeyPath) : undefined;

  return new Promise((resolve) => {
    const client = new SSHClient();

    client.on('ready', () => {
      result.connected = true;

      // Run whoami
      client.exec('whoami', (err, stream) => {
        if (err) {
          result.error = err.message;
          client.end();
          resolve(result);
          return;
        }

        let stdout = '';
        stream.on('data', (data: Buffer) => {
          stdout += data.toString();
        });

        stream.on('close', () => {
          result.user = stdout.trim();

          // Check git
          client.exec('which git', (gitErr, gitStream) => {
            if (gitErr) {
              result.gitInstalled = false;
            } else {
              gitStream.on('close', (gitCode: number) => {
                result.gitInstalled = gitCode === 0;

                // Check claude
                client.exec('which claude', (claudeErr, claudeStream) => {
                  if (claudeErr) {
                    result.claudeInstalled = false;
                    client.end();
                    resolve(result);
                  } else {
                    claudeStream.on('close', (claudeCode: number) => {
                      result.claudeInstalled = claudeCode === 0;
                      client.end();
                      resolve(result);
                    });
                  }
                });
              });
            }
          });
        });
      });
    });

    client.on('error', (err: Error) => {
      result.error = err.message;
      resolve(result);
    });

    const connectConfig: {
      host: string;
      port: number;
      username: string;
      privateKey?: Buffer;
    } = {
      host: machine.host,
      port: machine.port,
      username: machine.username,
    };

    if (privateKey) {
      connectConfig.privateKey = privateKey;
    }

    client.connect(connectConfig);
  });
}

// =============================================================================
// Route Handlers
// =============================================================================

// GET /api/remote-machines - List all registered remote machines
remoteMachinesRouter.get('/', async (c) => {
  const machines = listRemoteMachines();
  return c.json(machines);
});

// GET /api/remote-machines/agents/all - Get all active remote agents across all projects
remoteMachinesRouter.get('/agents/all', async (c) => {
  const agents = getAllActiveRemoteAgents();
  // Convert to snake_case for API response
  return c.json(
    agents.map((a) => ({
      id: a.id,
      project_name: a.projectName,
      machine_id: a.machineId,
      machine_name: a.machineName,
      agent_number: a.agentNumber,
      status: a.status,
      current_feature: a.currentFeature,
      pid: a.pid,
      graceful_stop_requested: a.gracefulStopRequested,
      restarting: a.restarting,
      last_activity_at: a.lastActivityAt,
    }))
  );
});

// POST /api/remote-machines - Add a new remote machine
remoteMachinesRouter.post('/', async (c) => {
  const request = await parseBody(c, RemoteMachineCreateSchema);

  // Validate SSH key path if provided
  if (request.ssh_key_path) {
    const keyPath = request.ssh_key_path.replace(/^~/, homedir());
    if (!existsSync(keyPath)) {
      throw new HTTPException(400, { message: `SSH key not found: ${request.ssh_key_path}` });
    }
  }

  // Validate Git SSH key path if provided
  if (request.git_ssh_key_path) {
    const gitKeyPath = request.git_ssh_key_path.replace(/^~/, homedir());
    if (!existsSync(gitKeyPath)) {
      throw new HTTPException(400, { message: `Git SSH key not found: ${request.git_ssh_key_path}` });
    }
  }

  // Test connectivity before adding
  try {
    const whoamiResult = await testSSHConnection(
      request.host,
      request.port,
      request.username,
      request.ssh_key_path
    );
    console.log(`SSH connectivity test passed for ${request.host}: ${whoamiResult}`);
  } catch (e) {
    const errorMsg = e instanceof Error ? e.message : String(e);
    throw new HTTPException(400, { message: `SSH connection failed: ${errorMsg}` });
  }

  // Add to registry
  let machineId: number;
  try {
    machineId = addRemoteMachine(
      request.name,
      request.host,
      request.port,
      request.username,
      request.ssh_key_path ?? undefined,
      request.git_ssh_key_path ?? undefined
    );
  } catch (e) {
    if (e instanceof RegistryError) {
      throw new HTTPException(409, { message: e.message });
    }
    throw e;
  }

  // Update status to online after successful connection
  updateRemoteMachineStatus(machineId, 'online');

  const machine = getRemoteMachine(machineId);
  if (!machine) {
    throw new HTTPException(500, { message: 'Failed to retrieve created machine' });
  }

  // Auto-deploy daemon after machine add
  let daemonDeployed = false;
  let daemonError: string | null = null;
  try {
    // Use the ZeroCoder repo URL from environment or default to GitHub
    const zerocoderRepoUrl = process.env['ZEROCODER_REPO_URL'] ?? 'https://github.com/your-org/ZeroCoder.git';
    const deployResult = await deployDaemon(machineId, zerocoderRepoUrl);
    daemonDeployed = deployResult.success;
    if (!deployResult.success) {
      daemonError = deployResult.message;
      console.warn(`Failed to auto-deploy daemon to ${request.name}: ${deployResult.message}`);
    } else {
      console.log(`Daemon deployed to ${request.name} on port ${deployResult.port}`);
    }
  } catch (e) {
    daemonError = e instanceof Error ? e.message : String(e);
    console.warn(`Exception deploying daemon to ${request.name}: ${daemonError}`);
  }

  return c.json({
    ...machine,
    daemon_deployed: daemonDeployed,
    daemon_error: daemonError,
  });
});

// DELETE /api/remote-machines/:machineId - Remove a remote machine
remoteMachinesRouter.delete('/:machineId', async (c) => {
  const machineIdParam = c.req.param('machineId');
  const machineId = parseInt(machineIdParam, 10);

  if (isNaN(machineId)) {
    throw new HTTPException(400, { message: 'Invalid machine ID' });
  }

  const removed = removeRemoteMachine(machineId);
  if (!removed) {
    throw new HTTPException(404, { message: 'Machine not found' });
  }

  return c.json({ success: true, message: 'Machine removed' });
});

// POST /api/remote-machines/:machineId/test - Test connectivity and check dependencies
remoteMachinesRouter.post('/:machineId/test', async (c) => {
  const machineIdParam = c.req.param('machineId');
  const machineId = parseInt(machineIdParam, 10);

  if (isNaN(machineId)) {
    throw new HTTPException(400, { message: 'Invalid machine ID' });
  }

  const machine = getRemoteMachine(machineId);
  if (!machine) {
    throw new HTTPException(404, { message: 'Machine not found' });
  }

  const result = await testMachineWithDependencies(machine);

  // Update status based on connection result
  if (result.connected) {
    updateRemoteMachineStatus(machineId, 'online');
  } else {
    updateRemoteMachineStatus(machineId, 'offline');
  }

  return c.json({
    connected: result.connected,
    user: result.user,
    git_installed: result.gitInstalled,
    claude_installed: result.claudeInstalled,
    error: result.error,
  });
});

export { remoteMachinesRouter };
