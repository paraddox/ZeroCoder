/**
 * Remote Machine Manager
 * ======================
 *
 * Manages agent lifecycle on remote machines via SSH.
 * Same callback patterns as ContainerManager for WebSocket integration.
 *
 * Converted from server/services/remote_machine_manager.py
 */

import { Client as SSHClient, type ClientChannel } from 'ssh2';
import { Mutex } from 'async-mutex';
import { homedir } from 'os';

import {
  getRemoteMachine,
  updateRemoteAgent,
  getRemoteAgent,
  type RemoteMachineInfo,
} from '../db/crud.js';

// =============================================================================
// Types
// =============================================================================

export type RemoteAgentStatus = 'created' | 'running' | 'stopped';

// Use type aliases to avoid conflicts with agent-executor.ts
export type RemoteOutputCallback = (line: string) => Promise<void>;
export type RemoteStatusCallback = (status: RemoteAgentStatus) => Promise<void>;

// =============================================================================
// Global Manager Registry
// =============================================================================

const _remoteManagers: Map<string, Map<number, RemoteMachineManager>> = new Map();
const _managersLock = new Mutex();

// =============================================================================
// RemoteMachineManager Class
// =============================================================================

/**
 * Manages a single agent process on a remote machine via SSH.
 */
export class RemoteMachineManager {
  public readonly projectName: string;
  public readonly machineId: number;
  public readonly gitUrl: string;
  public readonly agentNumber: number;
  public readonly agentId: number;

  private _status: RemoteAgentStatus = 'created';
  private _connection: SSHClient | null = null;
  private _process: ClientChannel | null = null;
  private _outputCallbacks: RemoteOutputCallback[] = [];
  private _statusCallbacks: RemoteStatusCallback[] = [];
  private _streamTask: Promise<void> | null = null;
  private _machineConfig: RemoteMachineInfo | null = null;

  constructor(
    projectName: string,
    machineId: number,
    gitUrl: string,
    agentNumber: number,
    agentId: number
  ) {
    this.projectName = projectName;
    this.machineId = machineId;
    this.gitUrl = gitUrl;
    this.agentNumber = agentNumber;
    this.agentId = agentId;
  }

  // ===========================================================================
  // Properties
  // ===========================================================================

  get status(): RemoteAgentStatus {
    return this._status;
  }

  private set status(value: RemoteAgentStatus) {
    const oldStatus = this._status;
    this._status = value;
    if (oldStatus !== value) {
      void this._broadcastStatus(value);
    }
  }

  get machineName(): string {
    return this._machineConfig?.name ?? 'unknown';
  }

  // ===========================================================================
  // Callback Methods
  // ===========================================================================

  addOutputCallback(callback: RemoteOutputCallback): void {
    this._outputCallbacks.push(callback);
  }

  removeOutputCallback(callback: RemoteOutputCallback): void {
    const index = this._outputCallbacks.indexOf(callback);
    if (index !== -1) {
      this._outputCallbacks.splice(index, 1);
    }
  }

  addStatusCallback(callback: RemoteStatusCallback): void {
    this._statusCallbacks.push(callback);
  }

  removeStatusCallback(callback: RemoteStatusCallback): void {
    const index = this._statusCallbacks.indexOf(callback);
    if (index !== -1) {
      this._statusCallbacks.splice(index, 1);
    }
  }

  private async _broadcastOutput(line: string): Promise<void> {
    for (const cb of [...this._outputCallbacks]) {
      try {
        await cb(line);
      } catch {
        // Ignore callback errors
      }
    }
  }

  private async _broadcastStatus(status: RemoteAgentStatus): Promise<void> {
    updateRemoteAgent(this.agentId, { status });
    for (const cb of [...this._statusCallbacks]) {
      try {
        await cb(status);
      } catch {
        // Ignore callback errors
      }
    }
  }

  // ===========================================================================
  // SSH Connection Methods
  // ===========================================================================

  private async _getConnection(): Promise<SSHClient> {
    if (this._connection !== null) {
      // Check if connection is still alive by trying to exec a simple command
      try {
        await this._execCommand('true', 5000);
        return this._connection;
      } catch {
        this._connection = null;
      }
    }

    const machine = getRemoteMachine(this.machineId);
    if (!machine) {
      throw new Error(`Machine ${this.machineId} not found`);
    }

    this._machineConfig = machine;

    const privateKeyPath = machine.sshKeyPath
      ? machine.sshKeyPath.replace(/^~/, homedir())
      : undefined;

    return new Promise((resolve, reject) => {
      const client = new SSHClient();

      client.on('ready', () => {
        this._connection = client;
        resolve(client);
      });

      client.on('error', (err: Error) => {
        reject(err);
      });

      const connectConfig: {
        host: string;
        port: number;
        username: string;
        privateKeyPath?: string;
      } = {
        host: machine.host,
        port: machine.port,
        username: machine.username,
      };

      if (privateKeyPath) {
        connectConfig.privateKeyPath = privateKeyPath;
      }

      client.connect(connectConfig);
    });
  }

  private async _execCommand(command: string, timeout = 30000): Promise<{ exitCode: number; stdout: string; stderr: string }> {
    return new Promise((resolve, reject) => {
      if (!this._connection) {
        reject(new Error('No SSH connection'));
        return;
      }

      let stdout = '';
      let stderr = '';

      const timeoutId = setTimeout(() => {
        reject(new Error('Command timeout'));
      }, timeout);

      this._connection!.exec(command, (err: Error | undefined, stream: ClientChannel) => {
        if (err) {
          clearTimeout(timeoutId);
          reject(err);
          return;
        }

        stream.on('data', (data: Buffer) => {
          stdout += data.toString();
        });

        stream.stderr.on('data', (data: Buffer) => {
          stderr += data.toString();
        });

        stream.on('close', (exitCode: number) => {
          clearTimeout(timeoutId);
          resolve({ exitCode, stdout, stderr });
        });

        stream.on('error', (err: Error) => {
          clearTimeout(timeoutId);
          reject(err);
        });
      });
    });
  }

  // ===========================================================================
  // Agent Lifecycle Methods
  // ===========================================================================

  /**
   * Start the agent on the remote machine.
   */
  async start(): Promise<[boolean, string]> {
    try {
      await this._getConnection();
      await this._broadcastStatus('running');

      // Setup workspace
      const workspace = `~/zerocoder/${this.projectName}`;
      await this._broadcastOutput(`[system] Setting up workspace: ${workspace}`);

      // Create workspace and clone/update repo
      const setupCmd = `
        mkdir -p ${workspace} &&
        cd ${workspace} &&
        if [ -d .git ]; then
          git fetch --all && git reset --hard origin/main 2>/dev/null || git reset --hard origin/master
        else
          cd ~ && rm -rf ${workspace} &&
          git clone ${this.gitUrl} ${workspace}
        fi
      `;

      const result = await this._execCommand(setupCmd, 120000);
      if (result.exitCode !== 0) {
        const errorMsg = result.stderr.trim() || 'Unknown setup error';
        await this._broadcastOutput(`[system] Setup error: ${errorMsg}`);
        await this._broadcastStatus('stopped');
        return [false, `Workspace setup failed: ${errorMsg}`];
      }

      await this._broadcastOutput('[system] Workspace ready, starting agent...');

      // Build environment variables for the agent
      const envVars = this._buildEnvVars();
      const envExport = Object.entries(envVars)
        .map(([k, v]) => `export ${k}="${v}"`)
        .join('; ');

      // Start claude agent
      const agentCmd =
        `cd ${workspace} && ${envExport} ` +
        `claude --dangerously-skip-permissions -p ` +
        `"$(cat ${workspace}/prompts/coding_prompt.md 2>/dev/null || echo 'Implement the next available feature')"`;

      // Start process and stream output
      return new Promise((resolve, reject) => {
        if (!this._connection) {
          reject(new Error('No SSH connection'));
          return;
        }

        this._connection.exec(agentCmd, (err: Error | undefined, stream: ClientChannel) => {
          if (err) {
            reject(err);
            return;
          }

          this._process = stream;

          // Get PID - this is a simplification, actual PID tracking would need more work
          void this._execCommand('echo $!').then((pidResult) => {
            const pid = parseInt(pidResult.stdout.trim(), 10);
            if (!isNaN(pid)) {
              updateRemoteAgent(this.agentId, { status: 'running', pid });
            }
          });

          // Start output streaming task
          this._streamTask = this._streamOutput();

          resolve([true, 'Agent started successfully']);
        });
      });
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      console.error(`Failed to start remote agent: ${error}`);
      await this._broadcastStatus('stopped');
      return [false, error];
    }
  }

  private async _streamOutput(): Promise<void> {
    if (!this._process) return;

    try {
      this._process.on('data', async (data: Buffer) => {
        const lines = data.toString().split('\n');
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed) {
            await this._broadcastOutput(trimmed);
            // Update activity timestamp
            updateRemoteAgent(this.agentId, {});
          }
        }
      });

      this._process.stderr?.on('data', async (data: Buffer) => {
        const lines = data.toString().split('\n');
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed) {
            await this._broadcastOutput(trimmed);
          }
        }
      });

      await new Promise<void>((resolve) => {
        this._process!.on('close', async (exitCode: number) => {
          await this._broadcastOutput(`[system] Agent exited with code ${exitCode}`);
          await this._handleAgentExit(exitCode);
          resolve();
        });
      });
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      console.error(`Error streaming remote output: ${error}`);
      await this._broadcastStatus('stopped');
    }
  }

  private async _handleAgentExit(_exitCode: number | null): Promise<void> {
    const agent = getRemoteAgent(this.agentId);
    if (!agent) {
      await this._broadcastStatus('stopped');
      return;
    }

    if (agent.gracefulStopRequested) {
      await this._broadcastOutput('[system] Graceful stop - not restarting');
      await this._broadcastStatus('stopped');
      return;
    }

    // Auto-restart if not graceful stop
    await this._broadcastOutput('[system] Agent exited, restarting...');
    updateRemoteAgent(this.agentId, { restarting: true });
    await this._sleep(5000);
    await this.restartAgent();
  }

  /**
   * Force stop the agent on the remote machine.
   */
  async stop(): Promise<[boolean, string]> {
    try {
      // Cancel stream task
      if (this._streamTask) {
        // We can't really cancel the promise, but we can ignore its result
        this._streamTask = null;
      }

      // Close the process stream
      if (this._process) {
        this._process.close();
        this._process = null;
      }

      // Also kill by PID on remote
      const agent = getRemoteAgent(this.agentId);
      if (agent?.pid) {
        try {
          await this._execCommand(`kill -9 ${agent.pid} 2>/dev/null`, 5000);
        } catch {
          // Ignore
        }
      }

      // Kill any claude processes for this project
      try {
        await this._execCommand(
          `pkill -f 'claude.*zerocoder/${this.projectName}' 2>/dev/null`,
          5000
        );
      } catch {
        // Ignore
      }

      await this._broadcastStatus('stopped');
      updateRemoteAgent(this.agentId, { status: 'stopped', pid: null });

      return [true, 'Agent stopped'];
    } catch (e) {
      const error = e instanceof Error ? e.message : String(e);
      console.error(`Error stopping remote agent: ${error}`);
      return [false, error];
    }
  }

  /**
   * Request graceful stop - agent finishes current work then stops.
   */
  async gracefulStop(): Promise<[boolean, string]> {
    updateRemoteAgent(this.agentId, { gracefulStopRequested: true });
    await this._broadcastOutput('[system] Graceful stop requested - finishing current work');
    return [true, 'Graceful stop requested'];
  }

  /**
   * Check if the agent process is running on the remote machine.
   */
  async isAgentRunning(): Promise<boolean> {
    const agent = getRemoteAgent(this.agentId);
    if (!agent?.pid) {
      return false;
    }

    try {
      const result = await this._execCommand(`kill -0 ${agent.pid} 2>/dev/null`, 5000);
      return result.exitCode === 0;
    } catch {
      return false;
    }
  }

  /**
   * Restart the agent process.
   */
  async restartAgent(): Promise<[boolean, string]> {
    updateRemoteAgent(this.agentId, { restarting: true, gracefulStopRequested: false });
    await this.stop();
    await this._sleep(2000);
    updateRemoteAgent(this.agentId, { restarting: false });
    return this.start();
  }

  /**
   * Close SSH connection and clean up.
   */
  async close(): Promise<void> {
    if (this._streamTask) {
      this._streamTask = null;
    }
    if (this._process) {
      this._process.close();
      this._process = null;
    }
    if (this._connection) {
      this._connection.end();
      this._connection = null;
    }
  }

  // ===========================================================================
  // Private Helper Methods
  // ===========================================================================

  private _buildEnvVars(): Record<string, string> {
    const env: Record<string, string> = {};

    // Pass API key
    const apiKey = process.env['ANTHROPIC_API_KEY'] ?? '';
    if (apiKey) {
      env['ANTHROPIC_API_KEY'] = apiKey;
    }

    // Project info
    env['PROJECT_NAME'] = this.projectName;
    env['CONTAINER_NUMBER'] = String(this.agentNumber);

    // Host API URL for callbacks (graceful stop checks, beads API)
    const hostApi = process.env['HOST_API_URL'] ?? '';
    if (hostApi) {
      env['HOST_API_URL'] = hostApi;
    }

    return env;
  }

  private _sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}

// =============================================================================
// Global Manager Registry Functions
// =============================================================================

/**
 * Get or create a remote machine manager instance.
 */
export async function getOrCreateRemoteManager(
  projectName: string,
  machineId: number,
  gitUrl: string,
  agentNumber: number,
  agentId: number
): Promise<RemoteMachineManager> {
  return _managersLock.runExclusive(() => {
    if (!_remoteManagers.has(projectName)) {
      _remoteManagers.set(projectName, new Map());
    }
    const projectManagers = _remoteManagers.get(projectName)!;

    if (projectManagers.has(agentId)) {
      return projectManagers.get(agentId)!;
    }

    const manager = new RemoteMachineManager(
      projectName,
      machineId,
      gitUrl,
      agentNumber,
      agentId
    );
    projectManagers.set(agentId, manager);
    return manager;
  });
}

/**
 * Get an existing remote manager WITHOUT creating one.
 */
export function getExistingRemoteManager(
  projectName: string,
  agentId: number
): RemoteMachineManager | null {
  const projectManagers = _remoteManagers.get(projectName);
  return projectManagers?.get(agentId) ?? null;
}

/**
 * Get all remote managers for a project.
 */
export function getAllRemoteManagers(projectName: string): RemoteMachineManager[] {
  const projectManagers = _remoteManagers.get(projectName);
  return projectManagers ? Array.from(projectManagers.values()) : [];
}

/**
 * Clear cached remote manager(s) for a project.
 */
export async function clearRemoteManager(
  projectName: string,
  agentId?: number
): Promise<void> {
  await _managersLock.runExclusive(async () => {
    if (!_remoteManagers.has(projectName)) return;

    if (agentId !== undefined) {
      const manager = _remoteManagers.get(projectName)?.get(agentId);
      if (manager) {
        await manager.close();
        _remoteManagers.get(projectName)?.delete(agentId);
      }
    } else {
      // Close all managers for this project
      for (const manager of _remoteManagers.get(projectName)!.values()) {
        await manager.close();
      }
      _remoteManagers.delete(projectName);
    }
  });
}

/**
 * Close all SSH connections and clean up managers.
 */
export async function cleanupAllRemoteManagers(): Promise<void> {
  for (const projectManagers of _remoteManagers.values()) {
    for (const manager of projectManagers.values()) {
      await manager.close();
    }
  }
  _remoteManagers.clear();
}
