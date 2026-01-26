/**
 * WebSocket Connection Manager
 * ============================
 *
 * Manages WebSocket connections per project with client tracking,
 * broadcast capabilities, and heartbeat/ping-pong support.
 *
 * Converted from server/websocket.py ConnectionManager class.
 */

import { WebSocket, type RawData } from 'ws';
import type { WSMessage } from '@zerocoder/shared';

/**
 * Validates project name to prevent path traversal and injection attacks.
 * Only allows alphanumeric characters, underscores, and hyphens.
 */
export function validateProjectName(name: string): boolean {
  return /^[a-zA-Z0-9_-]{1,50}$/.test(name);
}

/**
 * Manages WebSocket connections per project.
 *
 * Features:
 * - Client tracking per project
 * - Thread-safe connection management (via async operations)
 * - Broadcast to all clients of a project
 * - Automatic cleanup of dead connections
 * - Heartbeat ping/pong support
 */
export class ConnectionManager {
  /**
   * Map of project names to their active WebSocket connections.
   * Each project can have multiple simultaneous WebSocket clients.
   */
  private activeConnections: Map<string, Set<WebSocket>> = new Map();

  /**
   * Heartbeat interval in milliseconds.
   * Connections without a pong response will be terminated.
   */
  private readonly heartbeatIntervalMs = 30000;

  /**
   * Map of WebSocket to their heartbeat timer.
   */
  private heartbeatTimers: Map<WebSocket, NodeJS.Timeout> = new Map();

  /**
   * Accept and register a WebSocket connection for a project.
   *
   * @param ws - The WebSocket connection to register
   * @param projectName - The project this connection belongs to
   */
  connect(ws: WebSocket, projectName: string): void {
    if (!this.activeConnections.has(projectName)) {
      this.activeConnections.set(projectName, new Set());
    }

    this.activeConnections.get(projectName)!.add(ws);
    this.startHeartbeat(ws, projectName);

    // Handle cleanup on close
    ws.on('close', () => {
      this.disconnect(ws, projectName);
    });

    ws.on('error', () => {
      this.disconnect(ws, projectName);
    });
  }

  /**
   * Remove a WebSocket connection from a project.
   *
   * @param ws - The WebSocket connection to remove
   * @param projectName - The project this connection belongs to
   */
  disconnect(ws: WebSocket, projectName: string): void {
    const connections = this.activeConnections.get(projectName);
    if (connections) {
      connections.delete(ws);
      if (connections.size === 0) {
        this.activeConnections.delete(projectName);
      }
    }

    this.stopHeartbeat(ws);
  }

  /**
   * Broadcast a message to all connections for a project.
   * Automatically cleans up any dead connections encountered.
   *
   * @param projectName - The project to broadcast to
   * @param message - The message to send (will be JSON serialized)
   */
  async broadcastToProject(projectName: string, message: WSMessage | Record<string, unknown>): Promise<void> {
    const connections = this.activeConnections.get(projectName);
    if (!connections) {
      return;
    }

    // Take a snapshot to avoid iteration issues
    const connectionList = Array.from(connections);
    const deadConnections: WebSocket[] = [];

    const sendPromises = connectionList.map(async (ws) => {
      try {
        if (ws.readyState === WebSocket.OPEN) {
          await this.sendJson(ws, message);
        } else {
          deadConnections.push(ws);
        }
      } catch {
        deadConnections.push(ws);
      }
    });

    await Promise.allSettled(sendPromises);

    // Clean up dead connections
    for (const ws of deadConnections) {
      this.disconnect(ws, projectName);
    }
  }

  /**
   * Get the number of active connections for a project.
   *
   * @param projectName - The project to check
   * @returns Number of active WebSocket connections
   */
  getConnectionCount(projectName: string): number {
    return this.activeConnections.get(projectName)?.size ?? 0;
  }

  /**
   * Get all project names with active connections.
   *
   * @returns Array of project names
   */
  getActiveProjects(): string[] {
    return Array.from(this.activeConnections.keys());
  }

  /**
   * Send a JSON message to a specific WebSocket.
   * Wraps ws.send in a promise for async/await usage.
   *
   * @param ws - The WebSocket to send to
   * @param message - The message object to JSON serialize and send
   */
  sendJson(ws: WebSocket, message: WSMessage | Record<string, unknown>): Promise<void> {
    return new Promise((resolve, reject) => {
      if (ws.readyState !== WebSocket.OPEN) {
        reject(new Error('WebSocket is not open'));
        return;
      }

      ws.send(JSON.stringify(message), (err) => {
        if (err) {
          reject(err);
        } else {
          resolve();
        }
      });
    });
  }

  /**
   * Start heartbeat ping/pong for a WebSocket connection.
   * If no pong is received before the next ping, the connection is terminated.
   */
  private startHeartbeat(ws: WebSocket, projectName: string): void {
    let isAlive = true;

    ws.on('pong', () => {
      isAlive = true;
    });

    // Also handle client-side ping messages (from browser WebSocket)
    ws.on('message', (data: RawData) => {
      try {
        const message = JSON.parse(data.toString());
        if (message.type === 'ping') {
          this.sendJson(ws, { type: 'pong' }).catch(() => {
            // Connection may be closed, ignore
          });
        }
      } catch {
        // Not JSON or no type field, ignore
      }
    });

    const interval = setInterval(() => {
      if (!isAlive) {
        // No pong received since last ping
        this.disconnect(ws, projectName);
        ws.terminate();
        return;
      }

      isAlive = false;
      ws.ping();
    }, this.heartbeatIntervalMs);

    this.heartbeatTimers.set(ws, interval);
  }

  /**
   * Stop heartbeat for a WebSocket connection.
   */
  private stopHeartbeat(ws: WebSocket): void {
    const timer = this.heartbeatTimers.get(ws);
    if (timer) {
      clearInterval(timer);
      this.heartbeatTimers.delete(ws);
    }
  }

  /**
   * Close all connections and clean up.
   * Call this during server shutdown.
   */
  shutdown(): void {
    for (const connections of this.activeConnections.values()) {
      for (const ws of connections) {
        this.stopHeartbeat(ws);
        ws.close(1001, 'Server shutting down');
      }
      connections.clear();
    }
    this.activeConnections.clear();
  }
}

/**
 * Global singleton connection manager instance.
 * Use this for managing all WebSocket connections in the application.
 */
export const manager = new ConnectionManager();
