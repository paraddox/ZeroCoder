/**
 * Remote Agent Router Integration Tests
 *
 * Tests for remote agent control API endpoints.
 * Uses in-memory database with mocked SSH connections and remote machine manager.
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

// Mock CRUD functions
const mockCrudModule = {
  getProjectInfo: vi.fn(),
  getRemoteMachine: vi.fn(),
  createRemoteAgent: vi.fn(),
  updateRemoteAgent: vi.fn(),
  getRemoteAgentsForProject: vi.fn(),
  RegistryError: class RegistryError extends Error {
    constructor(message: string) {
      super(message);
      this.name = 'RegistryError';
    }
  },
};

vi.mock('../../db/crud.js', () => mockCrudModule);

// Mock Remote Machine Manager
const mockManagerStart = vi.fn();
const mockManagerStop = vi.fn();
const mockManagerGracefulStop = vi.fn();
const mockGetOrCreateRemoteManager = vi.fn();
const mockGetAllRemoteManagers = vi.fn();

vi.mock('../../services/remote-machine-manager.js', () => ({
  getOrCreateRemoteManager: mockGetOrCreateRemoteManager,
  getAllRemoteManagers: mockGetAllRemoteManagers,
}));

// =============================================================================
// Test Setup
// =============================================================================

let testCtx: TestContext;
let app: Hono;

beforeAll(async () => {
  testCtx = createTestDatabase();

  // Dynamically import router after mocks are set up
  const { remoteAgentRouter } = await import('../remote-agent.js');

  app = new Hono();
  app.onError((err, c) => {
    const status = 'status' in err ? (err.status as number) : 500;
    return c.json({ error: err.message, status }, status as 500);
  });
  app.route('/api/projects', remoteAgentRouter);
});

afterAll(() => {
  testCtx.cleanup();
  vi.clearAllMocks();
});

beforeEach(() => {
  clearTestDatabase(testCtx.sqlite);
  vi.clearAllMocks();

  // Reset default mock behaviors
  mockCrudModule.getProjectInfo.mockReturnValue({
    gitUrl: 'https://github.com/test/project.git',
    isNew: false,
    targetContainerCount: 1,
    localPath: '/tmp/test-project',
    createdAt: new Date().toISOString(),
  });
  mockCrudModule.getRemoteMachine.mockReturnValue({
    id: 1,
    name: 'test-server',
    host: '192.168.1.10',
    port: 22,
    username: 'root',
    sshKeyPath: null,
    status: 'online',
    lastCheckedAt: new Date().toISOString(),
    createdAt: new Date().toISOString(),
  });
  mockCrudModule.createRemoteAgent.mockReturnValue(1);
  mockCrudModule.updateRemoteAgent.mockReturnValue(true);
  mockCrudModule.getRemoteAgentsForProject.mockReturnValue([]);

  // Mock manager methods
  mockManagerStart.mockResolvedValue([true, 'Agent started successfully']);
  mockManagerStop.mockResolvedValue([true, 'Agent stopped']);
  mockManagerGracefulStop.mockResolvedValue([true, 'Graceful stop requested']);

  mockGetOrCreateRemoteManager.mockResolvedValue({
    start: mockManagerStart,
    stop: mockManagerStop,
    gracefulStop: mockManagerGracefulStop,
    agentNumber: 1,
  });

  mockGetAllRemoteManagers.mockReturnValue([]);
});

// =============================================================================
// Tests: POST /api/projects/:project_name/remote-agent/start
// =============================================================================

describe('POST /api/projects/:project_name/remote-agent/start', () => {
  it('starts a remote agent successfully', async () => {
    const res = await testRequest(app, 'POST', '/api/projects/test-project/remote-agent/start', {
      machine_id: 1,
    });

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; message: string; agent_id: number }>(res);
    expect(body.success).toBe(true);
    expect(body.message).toContain('Agent started on test-server');
    expect(body.agent_id).toBe(1);

    expect(mockCrudModule.createRemoteAgent).toHaveBeenCalledWith('test-project', 1, 1);
    expect(mockGetOrCreateRemoteManager).toHaveBeenCalledWith(
      'test-project',
      1,
      'https://github.com/test/project.git',
      1,
      1
    );
    expect(mockManagerStart).toHaveBeenCalled();
  });

  it('returns 404 when project does not exist', async () => {
    mockCrudModule.getProjectInfo.mockReturnValue(null);

    const res = await testRequest(app, 'POST', '/api/projects/nonexistent/remote-agent/start', {
      machine_id: 1,
    });

    expect(res.status).toBe(404);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('Project not found');
  });

  it('returns 404 when remote machine does not exist', async () => {
    mockCrudModule.getRemoteMachine.mockReturnValue(null);

    const res = await testRequest(app, 'POST', '/api/projects/test-project/remote-agent/start', {
      machine_id: 999,
    });

    expect(res.status).toBe(404);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('Remote machine not found');
  });

  it('returns 400 when project has no git URL', async () => {
    mockCrudModule.getProjectInfo.mockReturnValue({
      gitUrl: '',
      isNew: false,
      targetContainerCount: 1,
      localPath: '/tmp/test-project',
      createdAt: new Date().toISOString(),
    });

    const res = await testRequest(app, 'POST', '/api/projects/test-project/remote-agent/start', {
      machine_id: 1,
    });

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('Project has no git URL');
  });

  it('returns 500 when agent start fails', async () => {
    mockManagerStart.mockResolvedValue([false, 'SSH connection failed']);

    const res = await testRequest(app, 'POST', '/api/projects/test-project/remote-agent/start', {
      machine_id: 1,
    });

    expect(res.status).toBe(500);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('SSH connection failed');
  });

  it('rejects invalid request body', async () => {
    const res = await testRequest(app, 'POST', '/api/projects/test-project/remote-agent/start', {
      machine_id: 'invalid', // Should be a number
    });

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('Validation error');
  });

  it('assigns correct agent number for multiple agents on same machine', async () => {
    // Mock existing agents on machine 1
    mockCrudModule.getRemoteAgentsForProject.mockReturnValue([
      {
        id: 1,
        projectName: 'test-project',
        machineId: 1,
        machineName: 'test-server',
        agentNumber: 1,
        status: 'running',
        currentFeature: null,
        pid: 1234,
        gracefulStopRequested: false,
        restarting: false,
        lastActivityAt: new Date().toISOString(),
      },
      {
        id: 2,
        projectName: 'test-project',
        machineId: 1,
        machineName: 'test-server',
        agentNumber: 2,
        status: 'running',
        currentFeature: null,
        pid: 5678,
        gracefulStopRequested: false,
        restarting: false,
        lastActivityAt: new Date().toISOString(),
      },
    ]);

    mockCrudModule.createRemoteAgent.mockReturnValue(3);

    const res = await testRequest(app, 'POST', '/api/projects/test-project/remote-agent/start', {
      machine_id: 1,
    });

    expect(res.status).toBe(200);
    // Should create agent with number 3 (next available)
    expect(mockCrudModule.createRemoteAgent).toHaveBeenCalledWith('test-project', 1, 3);
    expect(mockGetOrCreateRemoteManager).toHaveBeenCalledWith(
      'test-project',
      1,
      'https://github.com/test/project.git',
      3,
      3
    );
  });
});

// =============================================================================
// Tests: POST /api/projects/:project_name/remote-agent/stop
// =============================================================================

describe('POST /api/projects/:project_name/remote-agent/stop', () => {
  it('stops all remote agents for a project', async () => {
    mockGetAllRemoteManagers.mockReturnValue([
      {
        agentNumber: 1,
        stop: mockManagerStop,
      },
      {
        agentNumber: 2,
        stop: vi.fn().mockResolvedValue([true, 'Agent stopped']),
      },
    ]);

    const res = await testRequest(app, 'POST', '/api/projects/test-project/remote-agent/stop');

    expect(res.status).toBe(200);
    const body = await parseResponse<{
      success: boolean;
      results: Array<{ agent_number: number; success: boolean; message: string }>;
    }>(res);
    expect(body.success).toBe(true);
    expect(body.results).toHaveLength(2);
    expect(body.results[0]?.agent_number).toBe(1);
    expect(body.results[0]?.success).toBe(true);
    expect(body.results[1]?.agent_number).toBe(2);
  });

  it('returns 404 when no remote agents are running', async () => {
    mockGetAllRemoteManagers.mockReturnValue([]);

    const res = await testRequest(app, 'POST', '/api/projects/test-project/remote-agent/stop');

    expect(res.status).toBe(404);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('No remote agents running');
  });
});

// =============================================================================
// Tests: POST /api/projects/:project_name/remote-agent/graceful-stop
// =============================================================================

describe('POST /api/projects/:project_name/remote-agent/graceful-stop', () => {
  it('requests graceful stop for all remote agents', async () => {
    mockGetAllRemoteManagers.mockReturnValue([
      {
        agentNumber: 1,
        gracefulStop: mockManagerGracefulStop,
      },
      {
        agentNumber: 2,
        gracefulStop: vi.fn().mockResolvedValue([true, 'Graceful stop requested']),
      },
    ]);

    const res = await testRequest(app, 'POST', '/api/projects/test-project/remote-agent/graceful-stop');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; message: string }>(res);
    expect(body.success).toBe(true);
    expect(body.message).toContain('Graceful stop requested for all remote agents');
  });

  it('returns 404 when no remote agents are running', async () => {
    mockGetAllRemoteManagers.mockReturnValue([]);

    const res = await testRequest(app, 'POST', '/api/projects/test-project/remote-agent/graceful-stop');

    expect(res.status).toBe(404);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('No remote agents running');
  });
});

// =============================================================================
// Tests: GET /api/projects/:project_name/remote-agent/status
// =============================================================================

describe('GET /api/projects/:project_name/remote-agent/status', () => {
  it('returns status of all remote agents for a project', async () => {
    const mockAgents = [
      {
        id: 1,
        projectName: 'test-project',
        machineId: 1,
        machineName: 'test-server',
        agentNumber: 1,
        status: 'running',
        currentFeature: 'feature-1',
        pid: 1234,
        gracefulStopRequested: false,
        restarting: false,
        lastActivityAt: new Date().toISOString(),
      },
      {
        id: 2,
        projectName: 'test-project',
        machineId: 2,
        machineName: 'another-server',
        agentNumber: 1,
        status: 'stopped',
        currentFeature: null,
        pid: null,
        gracefulStopRequested: false,
        restarting: false,
        lastActivityAt: null,
      },
    ];
    mockCrudModule.getRemoteAgentsForProject.mockReturnValue(mockAgents);

    const res = await testRequest(app, 'GET', '/api/projects/test-project/remote-agent/status');

    expect(res.status).toBe(200);
    const body = await parseResponse<typeof mockAgents>(res);
    expect(body).toHaveLength(2);
    expect(body[0]?.status).toBe('running');
    expect(body[0]?.machineName).toBe('test-server');
    expect(body[1]?.status).toBe('stopped');
    expect(body[1]?.machineName).toBe('another-server');
  });

  it('returns empty array when no agents exist', async () => {
    mockCrudModule.getRemoteAgentsForProject.mockReturnValue([]);

    const res = await testRequest(app, 'GET', '/api/projects/test-project/remote-agent/status');

    expect(res.status).toBe(200);
    const body = await parseResponse<unknown[]>(res);
    expect(body).toEqual([]);
  });
});
