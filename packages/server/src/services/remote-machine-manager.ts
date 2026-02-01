/**
 * Remote Machine Manager
 * ======================
 *
 * Manages daemon deployment and communication on remote machines.
 * The daemon runs on remote machines and handles agent lifecycle.
 */

import { Client as SSHClient, type ClientChannel } from 'ssh2';
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
  updateRemoteMachine,
  listRemoteMachines,
  type RemoteMachineInfo,
} from '../db/crud.js';

// =============================================================================
// SSH Config Parsing
// =============================================================================

interface SSHConfigHost {
  host: string;
  hostname?: string;
  port?: number;
  user?: string;
  identityFile?: string;
}

/**
 * Parse ~/.ssh/config to resolve SSH aliases.
 * Returns resolved config if alias found, null otherwise.
 *
 * The ssh2 library doesn't read ~/.ssh/config, so SSH aliases like "cld2"
 * won't work directly. This function resolves them to actual hostnames.
 */
function resolveSSHAlias(alias: string): SSHConfigHost | null {
  const configPath = `${homedir()}/.ssh/config`;
  try {
    const content = readFileSync(configPath, 'utf-8');
    const lines = content.split('\n');

    let currentHost: SSHConfigHost | null = null;
    let foundMatch = false;

    for (const line of lines) {
      const trimmed = line.trim();
      if (trimmed.startsWith('#') || !trimmed) continue;

      const parts = trimmed.split(/\s+/);
      const key = parts[0];
      const value = parts.slice(1).join(' ');

      if (!key) continue;

      if (key.toLowerCase() === 'host') {
        // Check if previous host was our match
        if (foundMatch && currentHost) {
          return currentHost;
        }
        // Start new host block
        const patterns = value.split(/\s+/);
        foundMatch = patterns.some(p => {
          if (p.includes('*')) {
            const regex = new RegExp('^' + p.replace(/\*/g, '.*') + '$');
            return regex.test(alias);
          }
          return p === alias;
        });
        currentHost = foundMatch ? { host: alias } : null;
      } else if (currentHost && foundMatch) {
        switch (key.toLowerCase()) {
          case 'hostname':
            currentHost.hostname = value;
            break;
          case 'port':
            currentHost.port = parseInt(value, 10);
            break;
          case 'user':
            currentHost.user = value;
            break;
          case 'identityfile':
            currentHost.identityFile = value.replace(/^~/, homedir());
            break;
        }
      }
    }

    // Handle last host in file
    if (foundMatch && currentHost) {
      return currentHost;
    }
  } catch {
    // SSH config doesn't exist or isn't readable
  }
  return null;
}

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

    client.exec(command, (err, stream: ClientChannel) => {
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

      // Listen to 'exit' event for the exit code (ssh2 provides it here, not in 'close')
      let exitCodeValue: number | null = null;
      stream.on('exit', (code: number | null) => {
        exitCodeValue = code;
      });

      stream.on('close', () => {
        clearTimeout(timeoutId);
        // Use 0 as default if exit code was null (shouldn't happen but be safe)
        resolve({ exitCode: exitCodeValue ?? 0, stdout, stderr });
      });
    });
  });
}

/**
 * Deploy the daemon to a remote machine via SSH.
 * Copies pre-built daemon files directly instead of cloning the repo.
 *
 * Deployment flow:
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
        const remoteTarball = 'zerocoder-daemon.tar.gz';
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

# Stop existing daemon (use fuser to kill by port, more reliable than pattern matching)
echo "Stopping existing daemon..."
fuser -k ${port}/tcp 2>/dev/null || true
# Also try pkill as backup for processes that might not have bound to port yet
pkill -f "zerocoder-daemon/dist/index.js" 2>/dev/null || true
pkill -f "node.*dist/index.js" 2>/dev/null || true
sleep 1

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
# Get full path to node since nohup won't have nvm in PATH
NODE_PATH=$(which node)
echo "Using node at: $NODE_PATH"
# Use full path to index.js so pgrep can find it
nohup $NODE_PATH ~/zerocoder-daemon/dist/index.js > ~/zerocoder-daemon.log 2>&1 &
sleep 2

# Verify daemon started
if pgrep -f "zerocoder-daemon/dist/index.js" > /dev/null; then
  echo "=== Daemon started successfully on port ${port} ==="
  exit 0
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

    // Resolve SSH alias from ~/.ssh/config
    const sshConfig = resolveSSHAlias(machine.host);
    const host = sshConfig?.hostname ?? machine.host;
    const sshPort = sshConfig?.port ?? machine.port ?? 22;
    const username = sshConfig?.user ?? machine.username ?? 'root';
    const privateKeyPath = sshConfig?.identityFile
      ?? (machine.sshKeyPath ? machine.sshKeyPath.replace(/^~/, homedir()) : undefined);

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
      host,
      port: sshPort,
      username,
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

  // Resolve SSH alias to get actual hostname for daemon API calls
  const sshConfig = resolveSSHAlias(machine.host);
  const host = sshConfig?.hostname ?? machine.host;
  const port = machine.daemonPort ?? DEFAULT_DAEMON_PORT;
  const url = `http://${host}:${port}${endpoint}`;

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
 * Check if daemon process is running via SSH.
 * Returns true if the daemon process is found on the remote machine.
 */
export async function isDaemonProcessRunning(machineId: number): Promise<boolean> {
  const machine = getRemoteMachine(machineId);
  if (!machine) {
    return false;
  }

  const client = new SSHClient();

  return new Promise((resolve) => {
    const timeout = setTimeout(() => {
      client.end();
      resolve(false);
    }, 10000);

    client.on('ready', () => {
      clearTimeout(timeout);
      const cmd = 'pgrep -f "zerocoder-daemon/dist/index.js" > /dev/null && echo "RUNNING" || echo "NOT_RUNNING"';

      client.exec(cmd, (err, stream: ClientChannel) => {
        if (err) {
          client.end();
          resolve(false);
          return;
        }

        let stdout = '';
        stream.on('data', (data: Buffer) => {
          stdout += data.toString();
        });

        stream.on('close', () => {
          client.end();
          resolve(stdout.includes('RUNNING'));
        });
      });
    });

    client.on('error', () => {
      clearTimeout(timeout);
      resolve(false);
    });

    // Resolve SSH alias and connect
    const sshConfig = resolveSSHAlias(machine.host);
    const host = sshConfig?.hostname ?? machine.host;
    const sshPort = sshConfig?.port ?? machine.port ?? 22;
    const username = sshConfig?.user ?? machine.username ?? 'root';
    const privateKeyPath = sshConfig?.identityFile
      ?? (machine.sshKeyPath ? machine.sshKeyPath.replace(/^~/, homedir()) : undefined);

    let privateKey: Buffer | undefined;
    if (privateKeyPath) {
      try {
        privateKey = readFileSync(privateKeyPath);
      } catch {
        resolve(false);
        return;
      }
    }

    client.connect({
      host,
      port: sshPort,
      username,
      privateKey,
      readyTimeout: 10000,
      hostVerifier: () => true,
    });
  });
}

/**
 * Force kill daemon via SSH (fuser -k, pkill fallback).
 */
export async function forceKillDaemon(machineId: number): Promise<{
  success: boolean;
  method: 'fuser' | 'pkill' | 'already_dead';
  message: string;
}> {
  const machine = getRemoteMachine(machineId);
  if (!machine) {
    return { success: false, method: 'already_dead', message: `Machine ${machineId} not found` };
  }

  const port = machine.daemonPort ?? DEFAULT_DAEMON_PORT;
  const client = new SSHClient();

  return new Promise((resolve) => {
    const timeout = setTimeout(() => {
      client.end();
      resolve({ success: false, method: 'already_dead', message: 'SSH connection timeout' });
    }, 15000);

    client.on('ready', () => {
      clearTimeout(timeout);

      // Kill script: try fuser first, then pkill, then check if already dead
      const killScript = `
PORT=${port}
# Try fuser first (kills by port)
fuser -k $PORT/tcp 2>/dev/null && echo "KILLED_BY_PORT" && exit 0
# Fallback to pkill
pkill -9 -f "zerocoder-daemon/dist/index.js" 2>/dev/null && echo "KILLED_BY_PKILL" && exit 0
# Check if already dead
pgrep -f "zerocoder-daemon/dist/index.js" > /dev/null || { echo "ALREADY_DEAD"; exit 0; }
echo "KILL_FAILED"; exit 1
`;

      client.exec(`bash -s <<'EOFKILL'\n${killScript}\nEOFKILL`, (err, stream: ClientChannel) => {
        if (err) {
          client.end();
          resolve({ success: false, method: 'already_dead', message: `SSH exec error: ${err.message}` });
          return;
        }

        let stdout = '';
        stream.on('data', (data: Buffer) => {
          stdout += data.toString();
        });

        stream.on('close', (code: number) => {
          client.end();

          if (stdout.includes('KILLED_BY_PORT')) {
            resolve({ success: true, method: 'fuser', message: 'Killed via fuser (port)' });
          } else if (stdout.includes('KILLED_BY_PKILL')) {
            resolve({ success: true, method: 'pkill', message: 'Killed via pkill' });
          } else if (stdout.includes('ALREADY_DEAD')) {
            resolve({ success: true, method: 'already_dead', message: 'Process was already dead' });
          } else {
            resolve({ success: false, method: 'already_dead', message: `Kill failed (exit code ${code})` });
          }
        });
      });
    });

    client.on('error', (err) => {
      clearTimeout(timeout);
      resolve({ success: false, method: 'already_dead', message: `SSH error: ${err.message}` });
    });

    // Resolve SSH alias and connect
    const sshConfig = resolveSSHAlias(machine.host);
    const host = sshConfig?.hostname ?? machine.host;
    const sshPort = sshConfig?.port ?? machine.port ?? 22;
    const username = sshConfig?.user ?? machine.username ?? 'root';
    const privateKeyPath = sshConfig?.identityFile
      ?? (machine.sshKeyPath ? machine.sshKeyPath.replace(/^~/, homedir()) : undefined);

    let privateKey: Buffer | undefined;
    if (privateKeyPath) {
      try {
        privateKey = readFileSync(privateKeyPath);
      } catch (e) {
        resolve({
          success: false,
          method: 'already_dead',
          message: `Cannot read SSH key: ${e instanceof Error ? e.message : String(e)}`,
        });
        return;
      }
    }

    client.connect({
      host,
      port: sshPort,
      username,
      privateKey,
      readyTimeout: 15000,
      hostVerifier: () => true,
    });
  });
}

/**
 * Robust stop with escalation strategy.
 * 1. Try API stop (10s timeout)
 * 2. Verify status changed (5s polling)
 * 3. If still running, SSH kill
 * 4. Verify process dead
 */
export async function robustStopDaemon(
  machineId: number,
  hard: boolean = false
): Promise<{
  success: boolean;
  method: 'api' | 'ssh_kill' | 'already_stopped';
  message: string;
  verified: boolean;
  duration_ms: number;
}> {
  const startTime = Date.now();
  const machine = getRemoteMachine(machineId);

  if (!machine) {
    return {
      success: false,
      method: 'already_stopped',
      message: `Machine ${machineId} not found`,
      verified: false,
      duration_ms: Date.now() - startTime,
    };
  }

  console.log(`[robust-stop:${machine.name}] Starting robust stop (hard=${hard})`);

  // Step 1: Check current daemon status
  const initialStatus = await getDaemonStatus(machineId);

  // If daemon is already idle/stopped, return early
  if (!initialStatus || initialStatus.status === 'idle' || initialStatus.status === 'stopped') {
    console.log(`[robust-stop:${machine.name}] Already stopped/idle`);
    return {
      success: true,
      method: 'already_stopped',
      message: 'Daemon was already stopped or idle',
      verified: true,
      duration_ms: Date.now() - startTime,
    };
  }

  // Step 2: Try API stop
  console.log(`[robust-stop:${machine.name}] Attempting API stop...`);
  const endpoint = hard ? '/stop/hard' : '/stop/graceful';
  const apiResult = await callDaemonApi<{ success: boolean; message: string; status: string }>(
    machineId,
    'POST',
    endpoint,
    undefined,
    10000 // 10s timeout for API call
  );

  if (apiResult.success && apiResult.data) {
    console.log(`[robust-stop:${machine.name}] API responded: ${apiResult.data.message}`);

    // Step 3: Verify status changed (poll for up to 5 seconds)
    const pollStart = Date.now();
    while (Date.now() - pollStart < 5000) {
      const status = await getDaemonStatus(machineId);
      if (!status || status.status === 'idle' || status.status === 'stopped') {
        console.log(`[robust-stop:${machine.name}] Verified stopped via API`);
        return {
          success: true,
          method: 'api',
          message: 'Stopped via daemon API',
          verified: true,
          duration_ms: Date.now() - startTime,
        };
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }

    console.log(`[robust-stop:${machine.name}] API succeeded but status didn't change, escalating to SSH kill`);
  } else {
    console.log(`[robust-stop:${machine.name}] API failed: ${apiResult.error}, escalating to SSH kill`);
  }

  // Step 4: SSH force kill
  console.log(`[robust-stop:${machine.name}] Attempting SSH force kill...`);
  const killResult = await forceKillDaemon(machineId);

  if (!killResult.success) {
    console.log(`[robust-stop:${machine.name}] SSH kill failed: ${killResult.message}`);
    return {
      success: false,
      method: 'ssh_kill',
      message: `SSH kill failed: ${killResult.message}`,
      verified: false,
      duration_ms: Date.now() - startTime,
    };
  }

  console.log(`[robust-stop:${machine.name}] SSH kill succeeded (${killResult.method})`);

  // Step 5: Verify process is dead via SSH
  await new Promise((resolve) => setTimeout(resolve, 1000)); // Brief wait for process to fully exit
  const stillRunning = await isDaemonProcessRunning(machineId);

  if (stillRunning) {
    console.log(`[robust-stop:${machine.name}] Warning: process still running after SSH kill`);
    return {
      success: false,
      method: 'ssh_kill',
      message: 'SSH kill executed but process still running',
      verified: false,
      duration_ms: Date.now() - startTime,
    };
  }

  console.log(`[robust-stop:${machine.name}] Verified stopped via SSH`);
  return {
    success: true,
    method: 'ssh_kill',
    message: `Stopped via SSH ${killResult.method}`,
    verified: true,
    duration_ms: Date.now() - startTime,
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
 * A machine is idle when the daemon status is 'idle' or unreachable.
 */
export async function isMachineIdle(machineId: number): Promise<boolean> {
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
  return true;
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
