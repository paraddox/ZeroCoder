/**
 * Remote Agent Router Integration Tests
 *
 * Tests for daemon-based remote agent control API endpoints.
 * Uses mocked daemon API calls and CRUD functions.
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
  listRemoteMachines: vi.fn(),
  RegistryError: class RegistryError extends Error {
    constructor(message: string) {
      super(message);
      this.name = 'RegistryError';
    }
  },
};

vi.mock('../../db/crud.js', () => mockCrudModule);

// Mock Remote Machine Manager (daemon API functions)
const mockAssignWorkToDaemon = vi.fn();
const mockStopDaemon = vi.fn();
const mockGetDaemonStatus = vi.fn();
const mockCheckDaemonHealth = vi.fn();
const mockDeployDaemon = vi.fn();
const mockShutdownDaemon = vi.fn();

vi.mock('../../services/remote-machine-manager.js', () => ({
  assignWorkToDaemon: mockAssignWorkToDaemon,
  stopDaemon: mockStopDaemon,
  getDaemonStatus: mockGetDaemonStatus,
  checkDaemonHealth: mockCheckDaemonHealth,
  deployDaemon: mockDeployDaemon,
  shutdownDaemon: mockShutdownDaemon,
}));

// Mock fs for SSH key reading
vi.mock('fs', async () => {
  const actual = await vi.importActual('fs');
  return {
    ...actual,
    readFileSync: vi.fn(() => 'mock-ssh-key-content'),
  };
});

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
    daemonPort: 9999,
  });
  mockCrudModule.listRemoteMachines.mockReturnValue([
    {
      id: 1,
      name: 'test-server',
      host: '192.168.1.10',
      port: 22,
      username: 'root',
      daemonPort: 9999,
    },
  ]);

  // Default daemon API mocks
  mockAssignWorkToDaemon.mockResolvedValue({ success: true, message: 'Work assigned' });
  mockStopDaemon.mockResolvedValue({ success: true, message: 'Hard stop initiated' });
  mockGetDaemonStatus.mockResolvedValue(null);
  mockCheckDaemonHealth.mockResolvedValue(true);
  mockDeployDaemon.mockResolvedValue({ success: true, message: 'Deployed', port: 9999 });
  mockShutdownDaemon.mockResolvedValue({ success: true, message: 'Shutdown initiated' });
});

// =============================================================================
// Tests: POST /api/projects/:project_name/remote-agent/start
// =============================================================================

describe('POST /api/projects/:project_name/remote-agent/start', () => {
  it('starts a remote agent via daemon successfully', async () => {
    const res = await testRequest(app, 'POST', '/api/projects/test-project/remote-agent/start', {
      machine_id: 1,
    });

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; message: string; machine_name: string }>(res);
    expect(body.success).toBe(true);
    expect(body.message).toContain('Work assigned to daemon on test-server');
    expect(body.machine_name).toBe('test-server');

    expect(mockAssignWorkToDaemon).toHaveBeenCalledWith(
      1,
      'https://github.com/test/project.git',
      'test-project',
      'mock-ssh-key-content'
    );
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

  it('returns 500 when daemon fails to accept work', async () => {
    mockAssignWorkToDaemon.mockResolvedValue({ success: false, message: 'Daemon busy' });

    const res = await testRequest(app, 'POST', '/api/projects/test-project/remote-agent/start', {
      machine_id: 1,
    });

    expect(res.status).toBe(500);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('Daemon busy');
  });
});

// =============================================================================
// Tests: POST /api/projects/:project_name/remote-agent/stop
// =============================================================================

describe('POST /api/projects/:project_name/remote-agent/stop', () => {
  it('stops remote agents running on project', async () => {
    // Mock daemon running this project
    mockGetDaemonStatus.mockResolvedValue({
      status: 'running',
      current_repo: 'https://github.com/test/test-project.git',
      current_feature: 'feature-1',
      agent_type: 'coding',
      stats: null,
    });

    const res = await testRequest(app, 'POST', '/api/projects/test-project/remote-agent/stop');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; results: unknown[] }>(res);
    expect(body.success).toBe(true);
    expect(body.results).toHaveLength(1);
    expect(mockStopDaemon).toHaveBeenCalledWith(1, true);
  });

  it('returns 404 when no remote agents are running', async () => {
    mockGetDaemonStatus.mockResolvedValue({ status: 'idle', current_repo: null });

    const res = await testRequest(app, 'POST', '/api/projects/test-project/remote-agent/stop');

    expect(res.status).toBe(404);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('No remote agents running');
  });
});

// =============================================================================
// Tests: GET /api/projects/:project_name/remote-agent/status
// =============================================================================

describe('GET /api/projects/:project_name/remote-agent/status', () => {
  it('returns status of daemons working on the project', async () => {
    mockGetDaemonStatus.mockResolvedValue({
      status: 'running',
      current_repo: 'https://github.com/test/test-project.git',
      current_feature: 'feature-1',
      agent_type: 'coding',
      stats: { completed: 5, remaining: 10, total: 15 },
    });

    const res = await testRequest(app, 'GET', '/api/projects/test-project/remote-agent/status');

    expect(res.status).toBe(200);
    const body = await parseResponse<unknown[]>(res);
    expect(body).toHaveLength(1);
    expect(body[0]).toMatchObject({
      machine_id: 1,
      machine_name: 'test-server',
      status: 'running',
      current_feature: 'feature-1',
    });
  });

  it('returns empty array when no daemons working on project', async () => {
    mockGetDaemonStatus.mockResolvedValue({ status: 'idle', current_repo: null });

    const res = await testRequest(app, 'GET', '/api/projects/test-project/remote-agent/status');

    expect(res.status).toBe(200);
    const body = await parseResponse<unknown[]>(res);
    expect(body).toEqual([]);
  });
});
