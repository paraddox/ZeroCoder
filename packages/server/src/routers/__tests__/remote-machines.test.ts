/**
 * Remote Machines Router Integration Tests
 *
 * Tests for remote machine management API endpoints.
 * Uses in-memory database with mocked SSH connections.
 */

import { describe, it, expect, beforeEach, beforeAll, afterAll, vi } from 'vitest';
import { Hono } from 'hono';
import {
  createTestDatabase,
  clearTestDatabase,
  testRequest,
  parseResponse,
  type TestContext,
} from './test-utils.js';

// =============================================================================
// Mock Setup
// =============================================================================

// Mock filesystem operations
const mockExistsSync = vi.fn();

vi.mock('node:fs', () => ({
  existsSync: (...args: unknown[]) => mockExistsSync(...args),
}));

// Mock ssh2
const mockSSHConnect = vi.fn();
const mockSSHExec = vi.fn();
const mockSSHEnd = vi.fn();
const mockOnReady = vi.fn();
const mockOnError = vi.fn();

vi.mock('ssh2', () => ({
  Client: vi.fn().mockImplementation(() => ({
    connect: mockSSHConnect,
    exec: mockSSHExec,
    end: mockSSHEnd,
    on: vi.fn((event: string, handler: unknown) => {
      if (event === 'ready') {
        mockOnReady.mockImplementation(() => (handler as () => void)());
      } else if (event === 'error') {
        mockOnError.mockImplementation((err: Error) => (handler as (err: Error) => void)(err));
      }
    }),
  })),
}));

// Mock CRUD functions
const mockCrudModule = {
  addRemoteMachine: vi.fn(),
  removeRemoteMachine: vi.fn(),
  listRemoteMachines: vi.fn(),
  getRemoteMachine: vi.fn(),
  updateRemoteMachineStatus: vi.fn(),
  RegistryError: class RegistryError extends Error {
    constructor(message: string) {
      super(message);
      this.name = 'RegistryError';
    }
  },
};

vi.mock('../../db/crud.js', () => mockCrudModule);

// =============================================================================
// Test Setup
// =============================================================================

let testCtx: TestContext;
let app: Hono;

beforeAll(async () => {
  testCtx = createTestDatabase();

  // Dynamically import router after mocks are set up
  const { remoteMachinesRouter } = await import('../remote-machines.js');

  app = new Hono();
  app.onError((err, c) => {
    const status = 'status' in err ? (err.status as number) : 500;
    return c.json({ error: err.message, status }, status as 500);
  });
  app.route('/api/remote-machines', remoteMachinesRouter);
});

afterAll(() => {
  testCtx.cleanup();
  vi.clearAllMocks();
});

beforeEach(() => {
  clearTestDatabase(testCtx.sqlite);
  vi.clearAllMocks();

  // Reset default mock behaviors
  mockExistsSync.mockReturnValue(true);
  mockCrudModule.listRemoteMachines.mockReturnValue([]);
  mockCrudModule.getRemoteMachine.mockReturnValue(null);
  mockCrudModule.addRemoteMachine.mockReturnValue(1);
  mockCrudModule.removeRemoteMachine.mockReturnValue(true);
  mockCrudModule.updateRemoteMachineStatus.mockReturnValue(true);
});

// =============================================================================
// Tests: GET /api/remote-machines - List all remote machines
// =============================================================================

describe('GET /api/remote-machines', () => {
  it('returns empty array when no machines exist', async () => {
    const res = await testRequest(app, 'GET', '/api/remote-machines');

    expect(res.status).toBe(200);
    const body = await parseResponse<unknown[]>(res);
    expect(body).toEqual([]);
  });

  it('returns list of registered machines', async () => {
    // Mock listRemoteMachines to return test machines
    mockCrudModule.listRemoteMachines.mockReturnValue([
      {
        id: 1,
        name: 'server-1',
        host: '192.168.1.10',
        port: 22,
        username: 'root',
        sshKeyPath: '/home/user/.ssh/id_rsa',
        status: 'online',
        lastCheckedAt: new Date().toISOString(),
        createdAt: new Date().toISOString(),
      },
      {
        id: 2,
        name: 'server-2',
        host: '192.168.1.11',
        port: 2222,
        username: 'ubuntu',
        sshKeyPath: null,
        status: 'offline',
        lastCheckedAt: null,
        createdAt: new Date().toISOString(),
      },
    ]);

    const res = await testRequest(app, 'GET', '/api/remote-machines');

    expect(res.status).toBe(200);
    const body = await parseResponse<Array<{ id: number; name: string; host: string; port: number; status: string }>>(res);
    expect(body).toHaveLength(2);
    expect(body[0]?.name).toBe('server-1');
    expect(body[0]?.host).toBe('192.168.1.10');
    expect(body[0]?.status).toBe('online');
    expect(body[1]?.name).toBe('server-2');
    expect(body[1]?.port).toBe(2222);
  });
});

// =============================================================================
// Tests: POST /api/remote-machines - Add a new remote machine
// =============================================================================

describe('POST /api/remote-machines', () => {
  it('adds a new machine successfully', async () => {
    // Mock getRemoteMachine to return the newly created machine
    mockCrudModule.getRemoteMachine.mockReturnValue({
      id: 1,
      name: 'new-server',
      host: '192.168.1.100',
      port: 22,
      username: 'root',
      sshKeyPath: '/home/user/.ssh/id_rsa',
      status: 'online',
      lastCheckedAt: new Date().toISOString(),
      createdAt: new Date().toISOString(),
    });

    // Mock successful SSH connection
    mockSSHExec.mockImplementation((_cmd: string, callback: unknown) => {
      const stream = {
        on: vi.fn((event: string, handler: unknown) => {
          if (event === 'data') {
            // whoami returns 'root'
            (handler as (data: Buffer) => void)(Buffer.from('root\n'));
          } else if (event === 'close') {
            (handler as (code: number) => void)(0);
          }
        }),
      };
      (callback as (err: Error | undefined, stream: unknown) => void)(undefined, stream);
    });

    // Trigger ready event after connect
    mockSSHConnect.mockImplementation(() => {
      setTimeout(() => mockOnReady(), 0);
    });

    const res = await testRequest(app, 'POST', '/api/remote-machines', {
      name: 'new-server',
      host: '192.168.1.100',
      port: 22,
      username: 'root',
      ssh_key_path: '/home/user/.ssh/id_rsa',
    });

    expect(res.status).toBe(200);
    const body = await parseResponse<{ id: number; name: string; host: string; status: string }>(res);
    expect(body.name).toBe('new-server');
    expect(body.host).toBe('192.168.1.100');
    expect(body.status).toBe('online');
  });

  it('rejects invalid request body', async () => {
    const res = await testRequest(app, 'POST', '/api/remote-machines', {
      name: '', // Invalid: empty name
      host: '192.168.1.100',
    });

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('Validation error');
  });

  it('rejects when SSH key file does not exist', async () => {
    mockExistsSync.mockReturnValue(false);

    const res = await testRequest(app, 'POST', '/api/remote-machines', {
      name: 'new-server',
      host: '192.168.1.100',
      port: 22,
      username: 'root',
      ssh_key_path: '/nonexistent/key',
    });

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('SSH key not found');
  });

  it('rejects when SSH connection fails', async () => {
    mockExistsSync.mockReturnValue(true);

    // Mock SSH connection failure
    mockSSHConnect.mockImplementation(() => {
      setTimeout(() => mockOnError(new Error('Connection refused')), 0);
    });

    const res = await testRequest(app, 'POST', '/api/remote-machines', {
      name: 'new-server',
      host: '192.168.1.100',
      port: 22,
      username: 'root',
    });

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('SSH connection failed');
  });

  it('rejects duplicate machine names', async () => {
    // Mock addRemoteMachine to throw RegistryError for duplicate
    mockCrudModule.addRemoteMachine.mockImplementation(() => {
      throw new mockCrudModule.RegistryError("Remote machine 'existing-server' already exists");
    });

    // Mock successful SSH connection
    mockSSHExec.mockImplementation((_cmd: string, callback: unknown) => {
      const stream = {
        on: vi.fn((event: string, handler: unknown) => {
          if (event === 'data') {
            (handler as (data: Buffer) => void)(Buffer.from('root\n'));
          } else if (event === 'close') {
            (handler as (code: number) => void)(0);
          }
        }),
      };
      (callback as (err: Error | undefined, stream: unknown) => void)(undefined, stream);
    });

    mockSSHConnect.mockImplementation(() => {
      setTimeout(() => mockOnReady(), 0);
    });

    const res = await testRequest(app, 'POST', '/api/remote-machines', {
      name: 'existing-server',
      host: '192.168.1.100',
      port: 22,
      username: 'root',
    });

    expect(res.status).toBe(409);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('already exists');
  });
});

// =============================================================================
// Tests: DELETE /api/remote-machines/:machineId - Remove a remote machine
// =============================================================================

describe('DELETE /api/remote-machines/:machineId', () => {
  it('removes a machine successfully', async () => {
    // Mock removeRemoteMachine to return true
    mockCrudModule.removeRemoteMachine.mockReturnValue(true);

    const res = await testRequest(app, 'DELETE', '/api/remote-machines/1');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; message: string }>(res);
    expect(body.success).toBe(true);
    expect(body.message).toContain('Machine removed');
    expect(mockCrudModule.removeRemoteMachine).toHaveBeenCalledWith(1);
  });

  it('returns 404 for non-existent machine', async () => {
    // Mock removeRemoteMachine to return false (machine not found)
    mockCrudModule.removeRemoteMachine.mockReturnValue(false);

    const res = await testRequest(app, 'DELETE', '/api/remote-machines/999');

    expect(res.status).toBe(404);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('Machine not found');
  });

  it('returns 400 for invalid machine ID', async () => {
    const res = await testRequest(app, 'DELETE', '/api/remote-machines/invalid');

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('Invalid machine ID');
  });
});

// =============================================================================
// Tests: POST /api/remote-machines/:machineId/test - Test connectivity
// =============================================================================

describe('POST /api/remote-machines/:machineId/test', () => {
  it('tests connectivity and returns success', async () => {
    // Mock getRemoteMachine to return test machine
    mockCrudModule.getRemoteMachine.mockReturnValue({
      id: 1,
      name: 'test-server',
      host: '192.168.1.10',
      port: 22,
      username: 'root',
      sshKeyPath: null,
      status: 'unknown',
      lastCheckedAt: null,
      createdAt: new Date().toISOString(),
    });

    // Mock successful SSH connection with dependency checks
    mockSSHExec.mockImplementation((cmd: string, callback: unknown) => {
      const stream = {
        on: vi.fn((event: string, handler: unknown) => {
          if (event === 'data') {
            if (cmd === 'whoami') {
              (handler as (data: Buffer) => void)(Buffer.from('root\n'));
            }
          } else if (event === 'close') {
            if (cmd === 'which git') {
              (handler as (code: number) => void)(0); // git installed
            } else if (cmd === 'which claude') {
              (handler as (code: number) => void)(1); // claude not installed
            } else {
              (handler as (code: number) => void)(0);
            }
          }
        }),
      };
      (callback as (err: Error | undefined, stream: unknown) => void)(undefined, stream);
    });

    mockSSHConnect.mockImplementation(() => {
      setTimeout(() => mockOnReady(), 0);
    });

    const res = await testRequest(app, 'POST', '/api/remote-machines/1/test');

    expect(res.status).toBe(200);
    const body = await parseResponse<{
      connected: boolean;
      user: string;
      git_installed: boolean;
      claude_installed: boolean;
      error: string | null;
    }>(res);
    expect(body.connected).toBe(true);
    expect(body.user).toBe('root');
    expect(body.git_installed).toBe(true);
    expect(body.claude_installed).toBe(false);
    expect(body.error).toBeNull();
  });

  it('returns failure when machine is unreachable', async () => {
    // Mock getRemoteMachine to return test machine
    mockCrudModule.getRemoteMachine.mockReturnValue({
      id: 1,
      name: 'unreachable-server',
      host: '192.168.1.99',
      port: 22,
      username: 'root',
      sshKeyPath: null,
      status: 'unknown',
      lastCheckedAt: null,
      createdAt: new Date().toISOString(),
    });

    // Mock SSH connection failure
    mockSSHConnect.mockImplementation(() => {
      setTimeout(() => mockOnError(new Error('Connection timeout')), 0);
    });

    const res = await testRequest(app, 'POST', '/api/remote-machines/1/test');

    expect(res.status).toBe(200);
    const body = await parseResponse<{
      connected: boolean;
      user: null;
      git_installed: boolean;
      claude_installed: boolean;
      error: string;
    }>(res);
    expect(body.connected).toBe(false);
    expect(body.user).toBeNull();
    expect(body.git_installed).toBe(false);
    expect(body.claude_installed).toBe(false);
    expect(body.error).toContain('Connection timeout');
  });

  it('returns 404 for non-existent machine', async () => {
    const res = await testRequest(app, 'POST', '/api/remote-machines/999/test');

    expect(res.status).toBe(404);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('Machine not found');
  });

  it('returns 400 for invalid machine ID', async () => {
    const res = await testRequest(app, 'POST', '/api/remote-machines/invalid/test');

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('Invalid machine ID');
  });
});
