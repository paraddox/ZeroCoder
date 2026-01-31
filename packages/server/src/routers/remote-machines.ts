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
  RegistryError,
} from '../db/crud.js';
import { deployDaemon, getDaemonStatus } from '../services/remote-machine-manager.js';

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

    client.connect({
      host,
      port,
      username,
      privateKey,
      readyTimeout: 30000,
      // Auto-accept host keys (equivalent to StrictHostKeyChecking=no)
      hostVerifier: () => true,
    });
  });
}

/**
 * Setup Claude config on remote machine to skip onboarding.
 * Creates ~/.claude.json with hasCompletedOnboarding: true
 */
async function setupClaudeConfig(
  host: string,
  port: number,
  username: string,
  sshKeyPath?: string | null
): Promise<void> {
  const expandedKeyPath = sshKeyPath ? sshKeyPath.replace(/^~/, homedir()) : undefined;
  const privateKey = expandedKeyPath ? readFileSync(expandedKeyPath) : undefined;

  return new Promise((resolve, reject) => {
    const client = new SSHClient();

    const timeout = setTimeout(() => {
      client.end();
      reject(new Error('Timeout setting up Claude config'));
    }, 15000);

    client.on('ready', () => {
      clearTimeout(timeout);
      // Install jq if needed, then merge hasCompletedOnboarding into existing config
      const cmd = `
        # Install jq if not available
        if ! command -v jq >/dev/null 2>&1; then
          if command -v apt-get >/dev/null 2>&1; then
            sudo apt-get update -qq && sudo apt-get install -y -qq jq >/dev/null 2>&1
          elif command -v yum >/dev/null 2>&1; then
            sudo yum install -y -q jq >/dev/null 2>&1
          elif command -v brew >/dev/null 2>&1; then
            brew install -q jq >/dev/null 2>&1
          fi
        fi

        # Merge or create config
        if [ -f ~/.claude.json ]; then
          tmp=$(mktemp) && jq '. + {"hasCompletedOnboarding": true}' ~/.claude.json > "$tmp" && mv "$tmp" ~/.claude.json
        else
          echo '{"hasCompletedOnboarding": true}' > ~/.claude.json
        fi
      `;
      client.exec(cmd, (err, stream) => {
        if (err) {
          client.end();
          reject(err);
          return;
        }
        stream.on('exit', () => {
          client.end();
          resolve();
        });
      });
    });

    client.on('error', (err: Error) => {
      clearTimeout(timeout);
      reject(err);
    });

    client.connect({
      host,
      port,
      username,
      privateKey,
      readyTimeout: 15000,
      hostVerifier: () => true,
    });
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

    // Set a timeout to prevent hanging forever
    const timeout = setTimeout(() => {
      console.log('[Test] Connection timeout after 30s');
      result.error = 'Connection timeout (30s)';
      client.end();
      resolve(result);
    }, 30000);

    client.on('ready', () => {
      clearTimeout(timeout);
      console.log('[Test] SSH connected, running checks...');
      result.connected = true;

      // Run all checks in one command (check common paths for claude)
      const cmd = 'echo "USER:$(whoami)" && echo "GIT:$(which git 2>/dev/null || echo missing)" && echo "CLAUDE:$(which claude 2>/dev/null || (test -x ~/.local/bin/claude && echo ~/.local/bin/claude) || echo missing)"';
      client.exec(cmd, (err, stream) => {
        if (err) {
          console.log('[Test] exec error:', err.message);
          result.error = err.message;
          client.end();
          resolve(result);
          return;
        }

        let stdout = '';
        stream.on('data', (data: Buffer) => {
          stdout += data.toString();
        });

        stream.on('exit', () => {
          console.log('[Test] Output:', stdout.trim());
          client.end();

          // Parse results
          const lines = stdout.trim().split('\n');
          for (const line of lines) {
            if (line.startsWith('USER:')) {
              result.user = line.substring(5);
            } else if (line.startsWith('GIT:')) {
              result.gitInstalled = !line.includes('missing');
            } else if (line.startsWith('CLAUDE:')) {
              result.claudeInstalled = !line.includes('missing');
            }
          }
          resolve(result);
        });
      });
    });

    client.on('error', (err: Error) => {
      clearTimeout(timeout);
      console.log('[Test] SSH error:', err.message);
      result.error = err.message;
      resolve(result);
    });

    console.log(`[Test] Connecting to ${machine.host}:${machine.port} as ${machine.username}...`);
    client.connect({
      host: machine.host,
      port: machine.port,
      username: machine.username,
      privateKey,
      readyTimeout: 30000,
      // Auto-accept host keys (equivalent to StrictHostKeyChecking=no)
      hostVerifier: () => true,
    });
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
  const machines = listRemoteMachines();
  const agents: Array<{
    machine_id: number;
    machine_name: string;
    status: string;
    current_repo: string | null;
    current_feature: string | null;
    agent_type: string | null;
  }> = [];

  // Query each machine's daemon for status
  for (const machine of machines) {
    const status = await getDaemonStatus(machine.id);
    if (status && status.status !== 'idle') {
      agents.push({
        machine_id: machine.id,
        machine_name: machine.name,
        status: status.status,
        current_repo: status.current_repo,
        current_feature: status.current_feature,
        agent_type: status.agent_type,
      });
    }
  }

  return c.json(agents);
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

  // Setup Claude config on remote machine (skip onboarding)
  try {
    await setupClaudeConfig(
      request.host,
      request.port,
      request.username,
      request.ssh_key_path
    );
    console.log(`Claude config created on ${request.host}`);
  } catch (e) {
    console.warn(`Failed to setup Claude config on ${request.host}:`, e);
    // Non-fatal - continue with machine add
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
  // Auto-deploy daemon by SCP-ing pre-built files (no longer needs ZEROCODER_REPO_URL)
  let daemonDeployed = false;
  let daemonError: string | null = null;
  try {
    const deployResult = await deployDaemon(machineId);
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
  console.log(`[Test] Starting test for machine ${machineId}`);

  if (isNaN(machineId)) {
    throw new HTTPException(400, { message: 'Invalid machine ID' });
  }

  const machine = getRemoteMachine(machineId);
  if (!machine) {
    throw new HTTPException(404, { message: 'Machine not found' });
  }

  console.log(`[Test] Testing ${machine.name} at ${machine.host}:${machine.port}`);
  const result = await testMachineWithDependencies(machine);
  console.log(`[Test] Result:`, result);

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
