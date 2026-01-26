/**
 * Project WebSocket Handler
 * =========================
 *
 * WebSocket endpoint for real-time project updates.
 * Handles /ws/projects/{project_name} connections.
 *
 * Streams:
 * - Progress updates (passing/total counts)
 * - Agent status changes
 * - Agent stdout/stderr lines
 * - Container list updates
 *
 * Converted from server/websocket.py project_websocket function.
 */

import { WebSocket, type RawData } from 'ws';
import type { IncomingMessage } from 'node:http';
import type {
  WSProgressMessage,
  WSAgentStatusMessage,
  WSLogMessage,
  WSContainersMessage,
  AgentStatus,
  AgentType,
  SdkType,
} from '@zerocoder/shared';
import { manager, validateProjectName } from './connection-manager.js';

/**
 * Logger interface for consistency with Python implementation.
 * TODO: Replace with proper logging library.
 */
const logger = {
  info: (msg: string) => console.log(`[WS] ${msg}`),
  warning: (msg: string) => console.warn(`[WS] ${msg}`),
  error: (msg: string) => console.error(`[WS] ${msg}`),
};

/**
 * Progress polling interval in milliseconds.
 */
const PROGRESS_POLL_INTERVAL_MS = 2000;

/**
 * Container callback registration check interval in milliseconds.
 */
const CALLBACK_CHECK_INTERVAL_MS = 2000;

/**
 * Container info for WebSocket messages.
 */
interface ContainerInfo {
  number: number;
  type: 'init' | 'coding';
  agent_type?: AgentType;
  sdk_type?: SdkType;
  source?: 'docker' | 'remote';
  machine_name?: string;
}

/**
 * Output callback type for container managers.
 */
type OutputCallback = (line: string) => Promise<void>;

/**
 * Status callback type for container managers.
 */
type StatusCallback = (status: string) => Promise<void>;

/**
 * Registered callback info for cleanup.
 */
interface RegisteredCallback {
  manager: ContainerManagerLike;
  outputCallback: OutputCallback;
  statusCallback: StatusCallback;
}

/**
 * Interface for container manager-like objects.
 * Matches the interface expected from both ContainerManager and RemoteMachineManager.
 */
interface ContainerManagerLike {
  container_number?: number;
  agent_number?: number;
  agent_id?: number;
  machine_id?: number;
  machine_name?: string;
  status: string;
  _current_agent_type?: AgentType;
  _force_claude_sdk?: boolean;
  _is_opencode_model?: () => boolean;
  add_output_callback: (cb: OutputCallback) => void;
  add_status_callback: (cb: StatusCallback) => void;
  remove_output_callback: (cb: OutputCallback) => void;
  remove_status_callback: (cb: StatusCallback) => void;
}

/**
 * Project context interface for registry lookups.
 * TODO: Import from registry module when converted.
 */
interface ProjectContext {
  path: string;
  gitUrl: string | null;
}

/**
 * Progress stats from beads.
 */
interface ProgressStats {
  passing: number;
  inProgress: number;
  total: number;
}

// ============================================================================
// Stub functions - to be replaced when dependencies are converted
// ============================================================================

/**
 * Get project path and git URL from registry.
 * TODO: Import from registry module when converted.
 */
async function getProjectContext(_projectName: string): Promise<ProjectContext | null> {
  // Stub - will be replaced with actual registry lookup
  // For now, return null to indicate project not found
  return null;
}

/**
 * Get progress stats for a project.
 * TODO: Import from progress module when converted.
 */
async function getProgressStats(_projectPath: string, _projectName: string): Promise<ProgressStats> {
  // Stub - will be replaced with actual progress lookup
  return { passing: 0, inProgress: 0, total: 0 };
}

/**
 * Get all container managers for a project.
 * TODO: Import from container_manager when converted.
 */
function getAllContainerManagers(_projectName: string): ContainerManagerLike[] {
  // Stub - will be replaced with actual container manager lookup
  return [];
}

/**
 * Get all remote managers for a project.
 * TODO: Import from remote_machine_manager when converted.
 */
function getAllRemoteManagers(_projectName: string): ContainerManagerLike[] {
  // Stub - will be replaced with actual remote manager lookup
  return [];
}

// ============================================================================
// WebSocket Handler Implementation
// ============================================================================

/**
 * Send containers list to a WebSocket client.
 */
async function sendContainersList(
  ws: WebSocket,
  projectName: string
): Promise<void> {
  const dockerManagers = getAllContainerManagers(projectName);
  const remoteManagers = getAllRemoteManagers(projectName);

  const containers: ContainerInfo[] = [];

  // Add docker containers
  for (const cm of dockerManagers) {
    const sdkType: SdkType =
      cm._force_claude_sdk || !cm._is_opencode_model?.()
        ? 'claude'
        : 'opencode';

    containers.push({
      number: cm.container_number ?? 0,
      type: 'coding',
      agent_type: cm._current_agent_type,
      sdk_type: sdkType,
      source: 'docker',
    });
  }

  // Add remote agents
  for (const rm of remoteManagers) {
    containers.push({
      number: rm.agent_number ?? 0,
      type: 'coding',
      agent_type: 'coder',
      sdk_type: 'claude',
      source: 'remote',
      machine_name: rm.machine_name,
    });
  }

  const message: WSContainersMessage = {
    type: 'containers',
    containers,
  };

  await manager.sendJson(ws, message);
}

/**
 * Create output callback for a container.
 */
function makeOutputCallback(
  ws: WebSocket,
  containerNumber: number
): OutputCallback {
  return async (line: string): Promise<void> => {
    try {
      const message: WSLogMessage = {
        type: 'log',
        line,
        timestamp: new Date().toISOString(),
        container_number: containerNumber,
      };
      await manager.sendJson(ws, message);
    } catch {
      // Connection may be closed, ignore
    }
  };
}

/**
 * Create status callback for a container.
 */
function makeStatusCallback(
  ws: WebSocket,
  containerNumber: number,
  cm: ContainerManagerLike
): StatusCallback {
  return async (status: string): Promise<void> => {
    try {
      const agentType = cm._current_agent_type ?? 'coder';
      const sdkType: SdkType =
        cm._force_claude_sdk || !cm._is_opencode_model?.()
          ? 'claude'
          : 'opencode';
      const source: 'docker' | 'remote' = cm.machine_id ? 'remote' : 'docker';

      const message: WSAgentStatusMessage = {
        type: 'agent_status',
        status: status as AgentStatus,
        container_number: containerNumber,
        agent_type: agentType,
        sdk_type: sdkType,
      };

      // Add machine_name for remote agents
      if (source === 'remote' && cm.machine_name) {
        (message as WSAgentStatusMessage & { machine_name?: string }).machine_name =
          cm.machine_name;
      }

      await manager.sendJson(ws, message);
    } catch {
      // Connection may be closed, ignore
    }
  };
}

/**
 * Poll progress and send updates.
 * Runs as a background task until cancelled.
 */
async function pollProgress(
  ws: WebSocket,
  projectName: string,
  projectPath: string,
  abortSignal: AbortSignal
): Promise<void> {
  let lastPassing = -1;
  let lastInProgress = -1;
  let lastTotal = -1;

  while (!abortSignal.aborted) {
    try {
      const stats = await getProgressStats(projectPath, projectName);

      // Only send if changed
      if (
        stats.passing !== lastPassing ||
        stats.inProgress !== lastInProgress ||
        stats.total !== lastTotal
      ) {
        lastPassing = stats.passing;
        lastInProgress = stats.inProgress;
        lastTotal = stats.total;

        const percentage =
          stats.total > 0
            ? Math.round((stats.passing / stats.total) * 1000) / 10
            : 0;

        const message: WSProgressMessage = {
          type: 'progress',
          passing: stats.passing,
          in_progress: stats.inProgress,
          total: stats.total,
          percentage,
        };

        await manager.sendJson(ws, message);
      }

      // Wait for next poll interval
      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(resolve, PROGRESS_POLL_INTERVAL_MS);
        abortSignal.addEventListener('abort', () => {
          clearTimeout(timeout);
          reject(new Error('Aborted'));
        }, { once: true });
      });
    } catch (err) {
      if (abortSignal.aborted) break;
      logger.warning(`Progress polling error: ${err}`);
      break;
    }
  }
}

/**
 * Register callbacks for new containers.
 * Runs as a background task until cancelled.
 */
async function registerNewContainerCallbacks(
  ws: WebSocket,
  projectName: string,
  registeredCallbacks: RegisteredCallback[],
  registeredContainerNums: Set<number>,
  registeredRemoteIds: Set<number>,
  abortSignal: AbortSignal
): Promise<void> {
  logger.info(`Started callback registration task for ${projectName}`);

  while (!abortSignal.aborted) {
    try {
      // Wait before checking
      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(resolve, CALLBACK_CHECK_INTERVAL_MS);
        abortSignal.addEventListener('abort', () => {
          clearTimeout(timeout);
          reject(new Error('Aborted'));
        }, { once: true });
      });

      // Check for new docker containers
      const currentManagers = getAllContainerManagers(projectName);
      for (const cm of currentManagers) {
        const containerNum = cm.container_number ?? 0;
        if (!registeredContainerNums.has(containerNum)) {
          const outputCb = makeOutputCallback(ws, containerNum);
          const statusCb = makeStatusCallback(ws, containerNum, cm);
          cm.add_output_callback(outputCb);
          cm.add_status_callback(statusCb);
          registeredCallbacks.push({
            manager: cm,
            outputCallback: outputCb,
            statusCallback: statusCb,
          });
          registeredContainerNums.add(containerNum);

          logger.info(`Registered callbacks for new container ${containerNum}`);
          await sendContainersList(ws, projectName);
        }
      }

      // Check for new remote managers
      const currentRemote = getAllRemoteManagers(projectName);
      for (const rm of currentRemote) {
        const remoteId = rm.agent_id ?? 0;
        if (!registeredRemoteIds.has(remoteId)) {
          const remoteNum = 100 + (rm.agent_number ?? 0);
          const outputCb = makeOutputCallback(ws, remoteNum);
          const statusCb = makeStatusCallback(ws, remoteNum, rm);
          rm.add_output_callback(outputCb);
          rm.add_status_callback(statusCb);
          registeredCallbacks.push({
            manager: rm,
            outputCallback: outputCb,
            statusCallback: statusCb,
          });
          registeredRemoteIds.add(remoteId);

          logger.info(`Registered callbacks for new remote agent ${remoteId}`);
          await sendContainersList(ws, projectName);
        }
      }
    } catch (err) {
      if (abortSignal.aborted) break;
      logger.warning(`Error checking for new containers: ${err}`);
    }
  }
}

/**
 * Handle an incoming WebSocket message.
 */
function handleIncomingMessage(
  ws: WebSocket,
  data: RawData
): void {
  try {
    const message = JSON.parse(data.toString());

    // Handle ping
    if (message.type === 'ping') {
      manager.sendJson(ws, { type: 'pong' }).catch(() => {
        // Connection may be closed, ignore
      });
    }
  } catch {
    logger.warning('Invalid JSON from WebSocket');
  }
}

/**
 * Handle a project WebSocket connection.
 *
 * This is the main handler for /ws/projects/{project_name} connections.
 * It validates the project, sets up callbacks, and streams updates.
 *
 * @param ws - The WebSocket connection
 * @param projectName - The project name from the URL path
 */
export async function handleProjectWebSocket(
  ws: WebSocket,
  projectName: string
): Promise<void> {
  // Validate project name
  if (!validateProjectName(projectName)) {
    ws.close(4000, 'Invalid project name');
    return;
  }

  // Get project context from registry
  const context = await getProjectContext(projectName);
  if (!context) {
    ws.close(4004, 'Project not found in registry');
    return;
  }

  if (!context.gitUrl) {
    ws.close(4004, 'Project has no git URL');
    return;
  }

  // Register with connection manager
  manager.connect(ws, projectName);

  // Get existing container managers and register callbacks
  const dockerManagers = getAllContainerManagers(projectName);
  const remoteManagers = getAllRemoteManagers(projectName);

  const registeredCallbacks: RegisteredCallback[] = [];
  const registeredContainerNums = new Set<number>();
  const registeredRemoteIds = new Set<number>();

  // Register callbacks for docker containers
  for (const cm of dockerManagers) {
    const containerNum = cm.container_number ?? 0;
    const outputCb = makeOutputCallback(ws, containerNum);
    const statusCb = makeStatusCallback(ws, containerNum, cm);
    cm.add_output_callback(outputCb);
    cm.add_status_callback(statusCb);
    registeredCallbacks.push({
      manager: cm,
      outputCallback: outputCb,
      statusCallback: statusCb,
    });
    registeredContainerNums.add(containerNum);
  }

  // Register callbacks for remote managers
  for (const rm of remoteManagers) {
    const remoteNum = 100 + (rm.agent_number ?? 0);
    const outputCb = makeOutputCallback(ws, remoteNum);
    const statusCb = makeStatusCallback(ws, remoteNum, rm);
    rm.add_output_callback(outputCb);
    rm.add_status_callback(statusCb);
    registeredCallbacks.push({
      manager: rm,
      outputCallback: outputCb,
      statusCallback: statusCb,
    });
    registeredRemoteIds.add(rm.agent_id ?? 0);
  }

  // Create abort controller for background tasks
  const abortController = new AbortController();

  // Start background tasks
  const pollTask = pollProgress(
    ws,
    projectName,
    context.path,
    abortController.signal
  );

  const callbackTask = registerNewContainerCallbacks(
    ws,
    projectName,
    registeredCallbacks,
    registeredContainerNums,
    registeredRemoteIds,
    abortController.signal
  );

  try {
    // Send initial status
    const firstManager = dockerManagers[0];
    const initialStatus: AgentStatus =
      firstManager
        ? (firstManager.status as AgentStatus)
        : 'not_created';

    await manager.sendJson(ws, {
      type: 'agent_status',
      status: initialStatus,
    } satisfies WSAgentStatusMessage);

    // Send initial progress
    const stats = await getProgressStats(context.path, projectName);
    const percentage =
      stats.total > 0
        ? Math.round((stats.passing / stats.total) * 1000) / 10
        : 0;

    await manager.sendJson(ws, {
      type: 'progress',
      passing: stats.passing,
      in_progress: stats.inProgress,
      total: stats.total,
      percentage,
    } satisfies WSProgressMessage);

    // Send containers list
    await sendContainersList(ws, projectName);

    // Handle incoming messages
    ws.on('message', (data) => handleIncomingMessage(ws, data));

    // Wait for close
    await new Promise<void>((resolve) => {
      ws.on('close', resolve);
      ws.on('error', resolve);
    });
  } finally {
    // Cancel background tasks
    abortController.abort();

    // Wait for tasks to finish
    await Promise.allSettled([pollTask, callbackTask]);

    // Unregister callbacks
    for (const { manager: cm, outputCallback, statusCallback } of registeredCallbacks) {
      cm.remove_output_callback(outputCallback);
      cm.remove_status_callback(statusCallback);
    }

    // Disconnect from manager (already handled by connection-manager on close)
  }
}

/**
 * Extract project name from WebSocket upgrade request URL.
 *
 * @param req - The incoming HTTP request
 * @returns The project name or null if not a valid project WebSocket URL
 */
export function extractProjectName(req: IncomingMessage): string | null {
  const url = req.url;
  if (!url) return null;

  // Match /ws/projects/{project_name}
  const match = url.match(/^\/ws\/projects\/([^/?]+)/);
  if (!match || !match[1]) return null;
  return match[1];
}

/**
 * Check if a request is a project WebSocket upgrade request.
 *
 * @param req - The incoming HTTP request
 * @returns True if this is a project WebSocket request
 */
export function isProjectWebSocketRequest(req: IncomingMessage): boolean {
  return extractProjectName(req) !== null;
}
