/**
 * WebSocket Connection Manager Tests
 *
 * Tests for connection lifecycle, message broadcasting, and heartbeat handling.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { WebSocket } from 'ws';
import { ConnectionManager, validateProjectName } from '../connection-manager.js';

// =============================================================================
// Mock WebSocket
// =============================================================================

/**
 * Create a mock WebSocket with event emitter functionality.
 */
function createMockWebSocket(options: { readyState?: number } = {}): WebSocket {
  const listeners: Record<string, ((...args: unknown[]) => void)[]> = {};

  const ws = {
    readyState: options.readyState ?? WebSocket.OPEN,
    OPEN: WebSocket.OPEN,
    CLOSED: WebSocket.CLOSED,
    CONNECTING: WebSocket.CONNECTING,
    CLOSING: WebSocket.CLOSING,

    on: vi.fn((event: string, callback: (...args: unknown[]) => void) => {
      if (!listeners[event]) {
        listeners[event] = [];
      }
      listeners[event].push(callback);
      return ws;
    }),

    send: vi.fn((_data: unknown, optionsOrCallback?: unknown, callback?: unknown) => {
      // Handle both signatures: send(data, cb) and send(data, options, cb)
      const cb = typeof optionsOrCallback === 'function' ? optionsOrCallback : callback;
      if (typeof cb === 'function') {
        cb();
      }
    }),

    ping: vi.fn(),

    terminate: vi.fn(),

    close: vi.fn((code?: number, reason?: string) => {
      ws.readyState = WebSocket.CLOSED;
      // Trigger close event
      const closeListeners = listeners['close'] || [];
      for (const listener of closeListeners) {
        listener(code, reason);
      }
    }),

    // Helper to emit events for testing
    _emit: (event: string, ...args: unknown[]) => {
      const eventListeners = listeners[event] || [];
      for (const listener of eventListeners) {
        listener(...args);
      }
    },

    // Helper to check listeners
    _getListeners: (event: string) => listeners[event] || [],
  };

  return ws as unknown as WebSocket;
}

// =============================================================================
// Tests: validateProjectName
// =============================================================================

describe('validateProjectName', () => {
  it('accepts valid alphanumeric names', () => {
    expect(validateProjectName('myproject')).toBe(true);
    expect(validateProjectName('MyProject123')).toBe(true);
    expect(validateProjectName('project_name')).toBe(true);
    expect(validateProjectName('project-name')).toBe(true);
  });

  it('accepts names with hyphens and underscores', () => {
    expect(validateProjectName('my-project')).toBe(true);
    expect(validateProjectName('my_project')).toBe(true);
    expect(validateProjectName('my-project_123')).toBe(true);
  });

  it('rejects empty names', () => {
    expect(validateProjectName('')).toBe(false);
  });

  it('rejects names with spaces', () => {
    expect(validateProjectName('my project')).toBe(false);
    expect(validateProjectName(' project')).toBe(false);
    expect(validateProjectName('project ')).toBe(false);
  });

  it('rejects names with special characters', () => {
    expect(validateProjectName('project@name')).toBe(false);
    expect(validateProjectName('project/name')).toBe(false);
    expect(validateProjectName('project..name')).toBe(false);
    expect(validateProjectName('../etc/passwd')).toBe(false);
  });

  it('rejects names longer than 50 characters', () => {
    expect(validateProjectName('a'.repeat(50))).toBe(true);
    expect(validateProjectName('a'.repeat(51))).toBe(false);
  });
});

// =============================================================================
// Tests: ConnectionManager - Connection Lifecycle
// =============================================================================

describe('ConnectionManager - Connection Lifecycle', () => {
  let manager: ConnectionManager;

  beforeEach(() => {
    manager = new ConnectionManager();
  });

  afterEach(() => {
    manager.shutdown();
  });

  it('connect() adds WebSocket to project connections', () => {
    const ws = createMockWebSocket();

    manager.connect(ws, 'my-project');

    expect(manager.getConnectionCount('my-project')).toBe(1);
    expect(manager.getActiveProjects()).toContain('my-project');
  });

  it('connect() supports multiple connections per project', () => {
    const ws1 = createMockWebSocket();
    const ws2 = createMockWebSocket();
    const ws3 = createMockWebSocket();

    manager.connect(ws1, 'my-project');
    manager.connect(ws2, 'my-project');
    manager.connect(ws3, 'my-project');

    expect(manager.getConnectionCount('my-project')).toBe(3);
  });

  it('connect() registers close handler', () => {
    const ws = createMockWebSocket();

    manager.connect(ws, 'my-project');

    expect(ws.on).toHaveBeenCalledWith('close', expect.any(Function));
  });

  it('connect() registers error handler', () => {
    const ws = createMockWebSocket();

    manager.connect(ws, 'my-project');

    expect(ws.on).toHaveBeenCalledWith('error', expect.any(Function));
  });

  it('disconnect() removes WebSocket from project connections', () => {
    const ws = createMockWebSocket();

    manager.connect(ws, 'my-project');
    expect(manager.getConnectionCount('my-project')).toBe(1);

    manager.disconnect(ws, 'my-project');
    expect(manager.getConnectionCount('my-project')).toBe(0);
  });

  it('disconnect() removes project entry when last connection leaves', () => {
    const ws = createMockWebSocket();

    manager.connect(ws, 'my-project');
    expect(manager.getActiveProjects()).toContain('my-project');

    manager.disconnect(ws, 'my-project');
    expect(manager.getActiveProjects()).not.toContain('my-project');
  });

  it('disconnect() handles non-existent project gracefully', () => {
    const ws = createMockWebSocket();

    // Should not throw
    expect(() => manager.disconnect(ws, 'nonexistent')).not.toThrow();
  });

  it('auto-disconnects on WebSocket close event', () => {
    const ws = createMockWebSocket();

    manager.connect(ws, 'my-project');
    expect(manager.getConnectionCount('my-project')).toBe(1);

    // Simulate close event
    (ws as unknown as { _emit: (event: string) => void })._emit('close');

    expect(manager.getConnectionCount('my-project')).toBe(0);
  });

  it('auto-disconnects on WebSocket error event', () => {
    const ws = createMockWebSocket();

    manager.connect(ws, 'my-project');
    expect(manager.getConnectionCount('my-project')).toBe(1);

    // Simulate error event
    (ws as unknown as { _emit: (event: string) => void })._emit('error');

    expect(manager.getConnectionCount('my-project')).toBe(0);
  });

  it('supports multiple projects simultaneously', () => {
    const ws1 = createMockWebSocket();
    const ws2 = createMockWebSocket();

    manager.connect(ws1, 'project-a');
    manager.connect(ws2, 'project-b');

    expect(manager.getConnectionCount('project-a')).toBe(1);
    expect(manager.getConnectionCount('project-b')).toBe(1);
    expect(manager.getActiveProjects()).toHaveLength(2);
  });
});

// =============================================================================
// Tests: ConnectionManager - Message Broadcasting
// =============================================================================

describe('ConnectionManager - Message Broadcasting', () => {
  let manager: ConnectionManager;

  beforeEach(() => {
    manager = new ConnectionManager();
  });

  afterEach(() => {
    manager.shutdown();
  });

  it('broadcastToProject sends to all project connections', async () => {
    const ws1 = createMockWebSocket();
    const ws2 = createMockWebSocket();

    manager.connect(ws1, 'my-project');
    manager.connect(ws2, 'my-project');

    await manager.broadcastToProject('my-project', { type: 'test', data: 'hello' });

    expect(ws1.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'test', data: 'hello' }),
      expect.any(Function)
    );
    expect(ws2.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'test', data: 'hello' }),
      expect.any(Function)
    );
  });

  it('broadcastToProject does nothing for non-existent project', async () => {
    // Should not throw
    await expect(
      manager.broadcastToProject('nonexistent', { type: 'test' })
    ).resolves.not.toThrow();
  });

  it('broadcastToProject cleans up dead connections', async () => {
    const wsActive = createMockWebSocket();
    const wsDead = createMockWebSocket({ readyState: WebSocket.CLOSED });

    manager.connect(wsActive, 'my-project');
    manager.connect(wsDead, 'my-project');

    expect(manager.getConnectionCount('my-project')).toBe(2);

    await manager.broadcastToProject('my-project', { type: 'test' });

    // Dead connection should be removed
    expect(manager.getConnectionCount('my-project')).toBe(1);
  });

  it('broadcastToProject handles send errors gracefully', async () => {
    const wsGood = createMockWebSocket();
    const wsBad = createMockWebSocket();

    // Override send to invoke callback with error
    Object.defineProperty(wsBad, 'send', {
      value: vi.fn((_data: unknown, callback?: unknown) => {
        if (typeof callback === 'function') {
          (callback as (err?: Error) => void)(new Error('Send failed'));
        }
      }),
      writable: true,
    });

    manager.connect(wsGood, 'my-project');
    manager.connect(wsBad, 'my-project');

    // Should not throw
    await manager.broadcastToProject('my-project', { type: 'test' });

    // Good connection should still receive
    expect(wsGood.send).toHaveBeenCalled();

    // Bad connection should be cleaned up
    expect(manager.getConnectionCount('my-project')).toBe(1);
  });

  it('sendJson rejects when WebSocket is not open', async () => {
    const ws = createMockWebSocket({ readyState: WebSocket.CLOSED });

    await expect(manager.sendJson(ws, { type: 'test' })).rejects.toThrow(
      'WebSocket is not open'
    );
  });

  it('sendJson resolves on successful send', async () => {
    const ws = createMockWebSocket();

    await expect(manager.sendJson(ws, { type: 'test' })).resolves.toBeUndefined();
    expect(ws.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'test' }),
      expect.any(Function)
    );
  });

  it('sendJson rejects on send error', async () => {
    const ws = createMockWebSocket();
    // Override send to invoke callback with error
    Object.defineProperty(ws, 'send', {
      value: vi.fn((_data: unknown, callback?: unknown) => {
        if (typeof callback === 'function') {
          (callback as (err?: Error) => void)(new Error('Network error'));
        }
      }),
      writable: true,
    });

    await expect(manager.sendJson(ws, { type: 'test' })).rejects.toThrow('Network error');
  });
});

// =============================================================================
// Tests: ConnectionManager - Heartbeat
// =============================================================================

describe('ConnectionManager - Heartbeat', () => {
  let manager: ConnectionManager;

  beforeEach(() => {
    vi.useFakeTimers();
    manager = new ConnectionManager();
  });

  afterEach(() => {
    manager.shutdown();
    vi.useRealTimers();
  });

  it('starts heartbeat ping on connect', () => {
    const ws = createMockWebSocket();

    manager.connect(ws, 'my-project');

    // Advance past heartbeat interval (30 seconds)
    vi.advanceTimersByTime(30000);

    expect(ws.ping).toHaveBeenCalled();
  });

  it('terminates connection when no pong received', () => {
    const ws = createMockWebSocket();

    manager.connect(ws, 'my-project');

    // First ping
    vi.advanceTimersByTime(30000);
    expect(ws.ping).toHaveBeenCalledTimes(1);

    // No pong received, second interval triggers terminate
    vi.advanceTimersByTime(30000);

    expect(ws.terminate).toHaveBeenCalled();
    expect(manager.getConnectionCount('my-project')).toBe(0);
  });

  it('keeps connection alive when pong received', () => {
    const ws = createMockWebSocket();

    manager.connect(ws, 'my-project');

    // First ping
    vi.advanceTimersByTime(30000);
    expect(ws.ping).toHaveBeenCalledTimes(1);

    // Simulate pong
    (ws as unknown as { _emit: (event: string) => void })._emit('pong');

    // Second interval - should just ping again
    vi.advanceTimersByTime(30000);

    expect(ws.terminate).not.toHaveBeenCalled();
    expect(ws.ping).toHaveBeenCalledTimes(2);
  });

  it('responds to client ping messages with pong', async () => {
    const ws = createMockWebSocket();

    manager.connect(ws, 'my-project');

    // Simulate client ping message
    (ws as unknown as { _emit: (event: string, data: Buffer) => void })._emit(
      'message',
      Buffer.from(JSON.stringify({ type: 'ping' }))
    );

    // Wait for async send
    await vi.runAllTimersAsync();

    expect(ws.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'pong' }),
      expect.any(Function)
    );
  });

  it('ignores non-JSON messages', () => {
    const ws = createMockWebSocket();

    manager.connect(ws, 'my-project');

    // Should not throw on invalid JSON
    expect(() => {
      (ws as unknown as { _emit: (event: string, data: Buffer) => void })._emit(
        'message',
        Buffer.from('not json')
      );
    }).not.toThrow();
  });

  it('ignores messages without type field', () => {
    const ws = createMockWebSocket();

    manager.connect(ws, 'my-project');

    // Should not throw when type is missing
    expect(() => {
      (ws as unknown as { _emit: (event: string, data: Buffer) => void })._emit(
        'message',
        Buffer.from(JSON.stringify({ data: 'hello' }))
      );
    }).not.toThrow();
  });

  it('stops heartbeat on disconnect', () => {
    const ws = createMockWebSocket();

    manager.connect(ws, 'my-project');
    manager.disconnect(ws, 'my-project');

    // Advance past heartbeat interval
    vi.advanceTimersByTime(60000);

    // Ping should not be called after disconnect
    expect(ws.ping).not.toHaveBeenCalled();
  });
});

// =============================================================================
// Tests: ConnectionManager - Shutdown
// =============================================================================

describe('ConnectionManager - Shutdown', () => {
  let manager: ConnectionManager;

  beforeEach(() => {
    manager = new ConnectionManager();
  });

  it('closes all connections on shutdown', () => {
    const ws1 = createMockWebSocket();
    const ws2 = createMockWebSocket();
    const ws3 = createMockWebSocket();

    manager.connect(ws1, 'project-a');
    manager.connect(ws2, 'project-a');
    manager.connect(ws3, 'project-b');

    manager.shutdown();

    expect(ws1.close).toHaveBeenCalledWith(1001, 'Server shutting down');
    expect(ws2.close).toHaveBeenCalledWith(1001, 'Server shutting down');
    expect(ws3.close).toHaveBeenCalledWith(1001, 'Server shutting down');
  });

  it('clears all tracking data on shutdown', () => {
    const ws = createMockWebSocket();

    manager.connect(ws, 'my-project');
    expect(manager.getActiveProjects()).toHaveLength(1);

    manager.shutdown();

    expect(manager.getActiveProjects()).toHaveLength(0);
    expect(manager.getConnectionCount('my-project')).toBe(0);
  });
});

// =============================================================================
// Tests: ConnectionManager - Utility Methods
// =============================================================================

describe('ConnectionManager - Utility Methods', () => {
  let manager: ConnectionManager;

  beforeEach(() => {
    manager = new ConnectionManager();
  });

  afterEach(() => {
    manager.shutdown();
  });

  it('getConnectionCount returns 0 for unknown project', () => {
    expect(manager.getConnectionCount('nonexistent')).toBe(0);
  });

  it('getActiveProjects returns empty array when no connections', () => {
    expect(manager.getActiveProjects()).toEqual([]);
  });

  it('getActiveProjects returns all projects with connections', () => {
    const ws1 = createMockWebSocket();
    const ws2 = createMockWebSocket();

    manager.connect(ws1, 'project-a');
    manager.connect(ws2, 'project-b');

    const projects = manager.getActiveProjects();
    expect(projects).toHaveLength(2);
    expect(projects).toContain('project-a');
    expect(projects).toContain('project-b');
  });
});
