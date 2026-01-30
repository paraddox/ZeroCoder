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
import { homedir, tmpdir } from 'os';
import { readFileSync, existsSync, mkdirSync, cpSync, rmSync, createWriteStream } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { execSync } from 'child_process';
import { createGzip } from 'zlib';
import { pack } from 'tar-fs';
import { pipeline } from 'stream/promises';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

import {
  getRemoteMachine,
  updateRemoteAgent,
  updateRemoteMachine,
  getRemoteAgent,
  listRemoteMachines,
  getAllActiveRemoteAgents,
  type RemoteMachineInfo,
} from '../db/crud.js';

// =============================================================================
// Daemon API Types
// =============================================================================

export interface DaemonStatus {
  status: 'idle' | 'running' | 'stopping' | 'stopped';
  current_repo: string | null;
  current_feature: string | null;
  agent_type: string | null;
  stats: {
    completed: number;
    remaining: number;
    total: number;
  } | null;
}

export interface DaemonHealthResponse {
  healthy: boolean;
  timestamp: string;
}

export interface DaemonVersionResponse {
  version: string;
  name: string;
}

export interface DaemonWorkRequest {
  repo_url: string;
  project_name: string;
  ssh_key: string;
}

/** Default daemon port */
const DEFAULT_DAEMON_PORT = 9999;

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

      client.connect({
        host: machine.host,
        port: machine.port,
        username: machine.username,
        privateKey: privateKeyPath ? readFileSync(privateKeyPath.replace(/^~/, homedir())) : undefined,
        readyTimeout: 30000,
        // Auto-accept host keys (equivalent to StrictHostKeyChecking=no)
        hostVerifier: () => true,
      });
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

    // Pass Claude Code OAuth token for authentication
    const oauthToken = process.env['CLAUDE_CODE_OAUTH_TOKEN'] ?? '';
    if (oauthToken) {
      env['CLAUDE_CODE_OAUTH_TOKEN'] = oauthToken;
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

// =============================================================================
// Daemon Deployment & API Functions
// =============================================================================

/** Cache for daemon tarball path to avoid rebuilding on every deploy */
let _cachedDaemonTarball: string | null = null;

/**
 * Get the path to the daemon package directory.
 * Works both in development (src/) and production (dist/).
 */
function getDaemonPackageDir(): string {
  // __dirname is packages/server/src/services or packages/server/dist/services
  // We need packages/daemon
  return join(__dirname, '../../../daemon');
}

/**
 * Create a tarball of the daemon package for deployment.
 * Includes dist/, package.json, and production node_modules.
 *
 * @returns Path to the created tarball
 */
async function createDaemonTarball(): Promise<string> {
  // Return cached tarball if it exists and is recent
  if (_cachedDaemonTarball && existsSync(_cachedDaemonTarball)) {
    return _cachedDaemonTarball;
  }

  const daemonDir = getDaemonPackageDir();
  const distDir = join(daemonDir, 'dist');

  // Verify daemon is built
  if (!existsSync(distDir)) {
    throw new Error(
      'Daemon not built. Run: pnpm --filter @zerocoder/daemon build'
    );
  }

  console.log('[daemon] Creating deployment tarball...');

  // Create temp directory for bundle
  const bundleDir = join(tmpdir(), `zerocoder-daemon-bundle-${Date.now()}`);
  const daemonBundleDir = join(bundleDir, 'zerocoder-daemon');
  mkdirSync(daemonBundleDir, { recursive: true });

  // Copy dist/ directory
  cpSync(distDir, join(daemonBundleDir, 'dist'), { recursive: true });

  // Copy package.json
  cpSync(join(daemonDir, 'package.json'), join(daemonBundleDir, 'package.json'));

  // Install production dependencies
  console.log('[daemon] Installing production dependencies...');
  execSync('npm install --omit=dev', {
    cwd: daemonBundleDir,
    stdio: 'pipe',
  });

  // Create tarball
  const tarballPath = join(tmpdir(), `zerocoder-daemon-${Date.now()}.tar.gz`);
  const tarStream = pack(bundleDir);
  const gzipStream = createGzip();
  const outputStream = createWriteStream(tarballPath);

  await pipeline(tarStream, gzipStream, outputStream);

  // Clean up bundle dir
  rmSync(bundleDir, { recursive: true, force: true });

  // Cache the tarball path
  _cachedDaemonTarball = tarballPath;

  console.log(`[daemon] Tarball created: ${tarballPath}`);
  return tarballPath;
}

/**
 * Transfer a file to remote machine via SFTP.
 */
async function scpFile(
  client: SSHClient,
  localPath: string,
  remotePath: string
): Promise<void> {
  return new Promise((resolve, reject) => {
    client.sftp((err, sftp) => {
      if (err) {
        reject(err);
        return;
      }

      sftp.fastPut(localPath, remotePath, (err) => {
        if (err) {
          reject(err);
          return;
        }
        resolve();
      });
    });
  });
}

/**
 * Upload file content to remote machine via SFTP.
 * Creates parent directories as needed.
 */
async function uploadFileContent(
  client: SSHClient,
  content: string,
  remotePath: string
): Promise<void> {
  return new Promise((resolve, reject) => {
    client.sftp((err, sftp) => {
      if (err) {
        reject(err);
        return;
      }

      // Ensure .ssh directory exists (mode 700)
      sftp.mkdir('.ssh', { mode: 0o700 }, () => {
        // Ignore error if directory already exists
        const writeStream = sftp.createWriteStream(remotePath, { mode: 0o600 });
        writeStream.on('error', reject);
        writeStream.on('close', () => resolve());
        writeStream.end(content);
      });
    });
  });
}

/**
 * Setup git SSH key on remote machine.
 * Copies the configured gitSshKeyPath to the remote and configures git to use it.
 */
async function setupGitSshKey(
  client: SSHClient,
  machine: RemoteMachineInfo
): Promise<void> {
  if (!machine.gitSshKeyPath) {
    console.log(`[daemon:${machine.name}] No gitSshKeyPath configured, skipping SSH key setup`);
    return;
  }

  // Read SSH key from local machine
  const keyPath = machine.gitSshKeyPath.replace(/^~/, homedir());
  let sshKeyContent: string;
  try {
    sshKeyContent = readFileSync(keyPath, 'utf8');
  } catch (e) {
    console.warn(`[daemon:${machine.name}] Cannot read git SSH key from ${keyPath}: ${e}`);
    return;
  }

  console.log(`[daemon:${machine.name}] Setting up git SSH key...`);

  // Upload SSH key via SFTP
  const remoteKeyPath = '.ssh/zerocoder-git';
  await uploadFileContent(client, sshKeyContent, remoteKeyPath);

  // Configure SSH and git
  const setupScript = `
    # Set key permissions
    chmod 600 ~/.ssh/zerocoder-git

    # Add common git hosts to known_hosts
    ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts 2>/dev/null
    ssh-keyscan -t ed25519 gitlab.com >> ~/.ssh/known_hosts 2>/dev/null
    ssh-keyscan -t ed25519 bitbucket.org >> ~/.ssh/known_hosts 2>/dev/null

    # Configure SSH to use this key for git hosts
    cat >> ~/.ssh/config << 'SSHCONFIG'

# ZeroCoder git SSH key
Host github.com gitlab.com bitbucket.org
  IdentityFile ~/.ssh/zerocoder-git
  IdentitiesOnly yes
  StrictHostKeyChecking no
SSHCONFIG

    echo "Git SSH key configured"
  `;

  await execRemoteCommand(client, setupScript, machine.name);
  console.log(`[daemon:${machine.name}] Git SSH key setup complete`);
}

/**
 * Execute a command on remote machine via SSH.
 */
async function execRemoteCommand(
  client: SSHClient,
  command: string,
  machineName: string,
  timeout: number = 300000
): Promise<{ exitCode: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    let stdout = '';
    let stderr = '';

    const timeoutId = setTimeout(() => {
      reject(new Error(`Command timed out after ${timeout}ms`));
    }, timeout);

    client.exec(command, (err, stream) => {
      if (err) {
        clearTimeout(timeoutId);
        reject(err);
        return;
      }

      stream.on('data', (data: Buffer) => {
        stdout += data.toString();
        console.log(`[daemon:${machineName}] ${data.toString().trim()}`);
      });

      stream.stderr.on('data', (data: Buffer) => {
        stderr += data.toString();
        console.log(`[daemon:${machineName}:err] ${data.toString().trim()}`);
      });

      stream.on('close', (exitCode: number) => {
        clearTimeout(timeoutId);
        resolve({ exitCode, stdout, stderr });
      });
    });
  });
}

/**
 * Deploy the daemon to a remote machine via SSH.
 * Copies pre-built daemon files directly instead of cloning the repo.
 *
 * New deployment flow:
 * 1. Build daemon tarball locally (if not cached)
 * 2. SCP tarball to remote machine
 * 3. Extract tarball, install Node.js (via nvm), start daemon
 */
export async function deployDaemon(
  machineId: number,
  _zerocoderRepoUrl?: string, // Kept for backwards compatibility, no longer used
  daemonSecret?: string
): Promise<{ success: boolean; message: string; port?: number }> {
  const machine = getRemoteMachine(machineId);
  if (!machine) {
    return { success: false, message: `Machine ${machineId} not found` };
  }

  const port = machine.daemonPort ?? DEFAULT_DAEMON_PORT;

  console.log(`[daemon] Deploying to ${machine.name} (${machine.host}:${machine.port})...`);

  // Step 1: Create daemon tarball locally
  let tarballPath: string;
  try {
    tarballPath = await createDaemonTarball();
  } catch (e) {
    return {
      success: false,
      message: `Failed to create daemon tarball: ${e instanceof Error ? e.message : String(e)}`,
    };
  }

  // Create SSH connection
  const client = new SSHClient();

  return new Promise((resolve) => {
    client.on('ready', async () => {
      try {
        // Setup git SSH key first (if configured)
        await setupGitSshKey(client, machine);

        console.log(`[daemon:${machine.name}] Uploading daemon tarball...`);

        // Step 2: SCP tarball to remote
        const remoteTarball = '~/zerocoder-daemon.tar.gz';
        await scpFile(client, tarballPath, remoteTarball);
        console.log(`[daemon:${machine.name}] Tarball uploaded`);

        // Step 3: Extract and start daemon
        const installScript = `
#!/bin/bash
set -e

echo "=== Installing ZeroCoder daemon ==="

# Install nvm if not present
if [ ! -d "$HOME/.nvm" ]; then
  echo "Installing nvm..."
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
fi

# Load nvm
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

# Install Node.js 24 if needed
if ! command -v node &> /dev/null || [ $(node --version | sed 's/v//' | cut -d. -f1) -lt 20 ]; then
  echo "Installing Node.js 24..."
  nvm install 24
  nvm use 24
  nvm alias default 24
fi

echo "Node.js version: $(node --version)"

# Stop existing daemon
echo "Stopping existing daemon..."
pkill -f "node.*zerocoder-daemon.*index.js" 2>/dev/null || true

# Extract tarball
echo "Extracting daemon files..."
cd ~
rm -rf zerocoder-daemon
tar -xzf zerocoder-daemon.tar.gz
rm zerocoder-daemon.tar.gz

# Start daemon
echo "Starting daemon on port ${port}..."
cd ~/zerocoder-daemon
export DAEMON_PORT=${port}
${daemonSecret ? `export DAEMON_SECRET="${daemonSecret}"` : ''}
nohup node dist/index.js > ~/zerocoder-daemon.log 2>&1 &
sleep 2

# Verify daemon started
if pgrep -f "node.*zerocoder-daemon.*index.js" > /dev/null; then
  echo "=== Daemon started successfully on port ${port} ==="
else
  echo "ERROR: Daemon failed to start. Check ~/zerocoder-daemon.log"
  exit 1
fi
`;

        const result = await execRemoteCommand(client, `bash -s <<'EOFSCRIPT'\n${installScript}\nEOFSCRIPT`, machine.name);

        client.end();

        if (result.exitCode === 0) {
          updateRemoteMachine(machineId, {
            daemonPort: port,
            daemonLastSeen: new Date().toISOString(),
          });

          resolve({
            success: true,
            message: `Daemon deployed to ${machine.name}`,
            port,
          });
        } else {
          resolve({
            success: false,
            message: `Deployment failed: ${result.stderr.trim() || result.stdout.trim()}`,
          });
        }
      } catch (e) {
        client.end();
        resolve({
          success: false,
          message: `Deployment error: ${e instanceof Error ? e.message : String(e)}`,
        });
      }
    });

    client.on('error', (err) => {
      resolve({
        success: false,
        message: `SSH connection error: ${err.message}`,
      });
    });

    const privateKeyPath = machine.sshKeyPath
      ? machine.sshKeyPath.replace(/^~/, homedir())
      : undefined;

    let privateKey: Buffer | undefined;
    if (privateKeyPath) {
      try {
        privateKey = readFileSync(privateKeyPath);
      } catch (e) {
        resolve({
          success: false,
          message: `Cannot read SSH key from ${privateKeyPath}: ${e instanceof Error ? e.message : String(e)}`,
        });
        return;
      }
    }

    client.connect({
      host: machine.host,
      port: machine.port,
      username: machine.username,
      privateKey,
      readyTimeout: 30000,
      hostVerifier: () => true,
    });
  });
}

/**
 * Clear the cached daemon tarball (call when daemon code changes).
 */
export function clearDaemonTarballCache(): void {
  if (_cachedDaemonTarball && existsSync(_cachedDaemonTarball)) {
    rmSync(_cachedDaemonTarball, { force: true });
  }
  _cachedDaemonTarball = null;
}

/**
 * Call a daemon API endpoint.
 */
export async function callDaemonApi<T>(
  machineId: number,
  method: 'GET' | 'POST',
  endpoint: string,
  body?: unknown,
  timeoutMs: number = 30000
): Promise<{ success: boolean; data?: T; error?: string }> {
  const machine = getRemoteMachine(machineId);
  if (!machine) {
    return { success: false, error: `Machine ${machineId} not found` };
  }

  const port = machine.daemonPort ?? DEFAULT_DAEMON_PORT;
  const url = `http://${machine.host}:${port}${endpoint}`;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  // Add auth header if we have a daemon secret
  const daemonSecret = process.env['DAEMON_SECRET'];
  if (daemonSecret) {
    headers['Authorization'] = `Bearer ${daemonSecret}`;
  }

  try {
    const response = await fetch(url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(timeoutMs),
    });

    if (!response.ok) {
      const errorText = await response.text();
      return {
        success: false,
        error: `HTTP ${response.status}: ${errorText}`,
      };
    }

    const data = await response.json() as T;

    // Update last seen timestamp
    updateRemoteMachine(machineId, {
      daemonLastSeen: new Date().toISOString(),
    });

    return { success: true, data };
  } catch (e) {
    return {
      success: false,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

/**
 * Check daemon health on a remote machine.
 */
export async function checkDaemonHealth(machineId: number): Promise<boolean> {
  const result = await callDaemonApi<DaemonHealthResponse>(
    machineId,
    'GET',
    '/health',
    undefined,
    5000
  );
  return result.success && result.data?.healthy === true;
}

/**
 * Get daemon status from a remote machine.
 */
export async function getDaemonStatus(machineId: number): Promise<DaemonStatus | null> {
  const result = await callDaemonApi<DaemonStatus>(machineId, 'GET', '/status');
  return result.success ? (result.data ?? null) : null;
}

/**
 * Assign work to a daemon.
 */
export async function assignWorkToDaemon(
  machineId: number,
  repoUrl: string,
  projectName: string,
  sshKey: string
): Promise<{ success: boolean; message: string }> {
  const body: DaemonWorkRequest = {
    repo_url: repoUrl,
    project_name: projectName,
    ssh_key: sshKey,
  };

  const result = await callDaemonApi<{ success: boolean; message: string }>(
    machineId,
    'POST',
    '/work',
    body,
    60000 // 1 minute timeout for work assignment (includes clone time)
  );

  if (result.success && result.data) {
    return result.data;
  }

  return {
    success: false,
    message: result.error ?? 'Unknown error',
  };
}

/**
 * Assign work to a daemon using the machine's configured git SSH key.
 * Reads the SSH key from the machine's gitSshKeyPath field.
 */
export async function assignWorkToDaemonWithMachineKey(
  machineId: number,
  repoUrl: string,
  projectName: string
): Promise<{ success: boolean; message: string }> {
  const machine = getRemoteMachine(machineId);
  if (!machine) {
    return { success: false, message: `Machine ${machineId} not found` };
  }

  // Read SSH key from the machine's gitSshKeyPath
  let sshKey = '';
  if (machine.gitSshKeyPath) {
    const keyPath = machine.gitSshKeyPath.replace(/^~/, homedir());
    try {
      sshKey = readFileSync(keyPath, 'utf8');
    } catch (e) {
      return {
        success: false,
        message: `Cannot read git SSH key from ${machine.gitSshKeyPath}: ${e instanceof Error ? e.message : String(e)}`,
      };
    }
  }

  return assignWorkToDaemon(machineId, repoUrl, projectName, sshKey);
}

/**
 * Stop daemon on a remote machine (graceful or hard).
 */
export async function stopDaemon(
  machineId: number,
  hard: boolean = false
): Promise<{ success: boolean; message: string }> {
  const endpoint = hard ? '/stop/hard' : '/stop/graceful';
  const result = await callDaemonApi<{ success: boolean; message: string }>(
    machineId,
    'POST',
    endpoint
  );

  if (result.success && result.data) {
    return result.data;
  }

  return {
    success: false,
    message: result.error ?? 'Unknown error',
  };
}

/**
 * Shutdown daemon on a remote machine.
 */
export async function shutdownDaemon(machineId: number): Promise<{ success: boolean; message: string }> {
  const result = await callDaemonApi<{ success: boolean; message: string }>(
    machineId,
    'POST',
    '/shutdown',
    undefined,
    5000
  );

  if (result.success && result.data) {
    return result.data;
  }

  return {
    success: false,
    message: result.error ?? 'Unknown error',
  };
}

// =============================================================================
// Remote Machine Checkup Functions
// =============================================================================

/**
 * Get local daemon version from package.json.
 */
function getLocalDaemonVersion(): string {
  const daemonPkgPath = join(getDaemonPackageDir(), 'package.json');
  try {
    const pkg = JSON.parse(readFileSync(daemonPkgPath, 'utf-8'));
    return pkg.version ?? '0.0.0';
  } catch {
    console.warn('[checkup] Could not read daemon package.json, defaulting to 0.0.0');
    return '0.0.0';
  }
}

/**
 * Get daemon version from a remote machine.
 */
export async function getDaemonVersion(machineId: number): Promise<string | null> {
  const result = await callDaemonApi<DaemonVersionResponse>(
    machineId,
    'GET',
    '/version',
    undefined,
    5000
  );
  return result.success ? result.data?.version ?? null : null;
}

/**
 * Check if a remote machine is idle (safe to update).
 * A machine is idle when:
 * - Daemon status is 'idle' or daemon is unreachable
 * - No current_feature in progress
 * - No remote agents with status 'running' on that machine
 */
export async function isMachineIdle(machineId: number): Promise<boolean> {
  // Check daemon status
  const status = await getDaemonStatus(machineId);
  if (status) {
    // Daemon is reachable - check if it's busy
    if (status.status !== 'idle') {
      return false; // Daemon is busy
    }
    if (status.current_feature) {
      return false; // Feature in progress
    }
  }
  // If daemon is unreachable, we still consider it idle (can be updated)

  // Check for running agents on this machine
  const agents = getAllActiveRemoteAgents();
  const hasRunningAgent = agents.some(
    (a) => a.machineId === machineId && a.status === 'running'
  );

  return !hasRunningAgent;
}

export interface CheckupResult {
  checked: string[];
  updated: string[];
  skipped: string[];
  errors: string[];
}

/**
 * Run checkup on all remote machines at server startup.
 * Only updates idle machines. Checks:
 * - Daemon version (updates if outdated)
 * - Git SSH key (deployed during deployDaemon)
 * - Prerequisites (installed during deployDaemon)
 */
export async function checkupRemoteMachines(): Promise<CheckupResult> {
  const machines = listRemoteMachines();
  const results: CheckupResult = {
    checked: [],
    updated: [],
    skipped: [],
    errors: [],
  };

  if (machines.length === 0) {
    console.log('[checkup] No remote machines configured');
    return results;
  }

  const localVersion = getLocalDaemonVersion();
  console.log(`[checkup] Starting remote machine checkup (${machines.length} machines, local daemon v${localVersion})...`);

  // Process machines sequentially to avoid overwhelming network
  for (const machine of machines) {
    results.checked.push(machine.name);

    try {
      // Check if machine is idle
      const idle = await isMachineIdle(machine.id);
      if (!idle) {
        console.log(`[checkup:${machine.name}] Busy, skipping update`);
        results.skipped.push(machine.name);
        continue;
      }

      // Check daemon version
      const remoteVersion = await getDaemonVersion(machine.id);
      const needsUpdate = !remoteVersion || remoteVersion !== localVersion;

      if (needsUpdate) {
        console.log(`[checkup:${machine.name}] Updating daemon (${remoteVersion ?? 'not installed'} → ${localVersion})`);
        const result = await deployDaemon(machine.id);
        if (result.success) {
          updateRemoteMachine(machine.id, { daemonVersion: localVersion });
          results.updated.push(machine.name);
          console.log(`[checkup:${machine.name}] Update complete`);
        } else {
          results.errors.push(`${machine.name}: ${result.message}`);
          console.error(`[checkup:${machine.name}] Update failed: ${result.message}`);
        }
      } else {
        console.log(`[checkup:${machine.name}] Up to date (v${remoteVersion})`);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error(`[checkup:${machine.name}] Error: ${msg}`);
      results.errors.push(`${machine.name}: ${msg}`);
    }
  }

  console.log(`[checkup] Complete. Updated: ${results.updated.length}, Skipped: ${results.skipped.length}, Errors: ${results.errors.length}`);
  return results;
}
