/**
 * Agent Router Integration Tests
 *
 * Tests for agent/container control API endpoints.
 * Mocks Docker operations and ContainerManager.
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

// Mock filesystem
const mockExistsSync = vi.fn();
const mockReadFileSync = vi.fn();
const mockReaddirSync = vi.fn();
const mockUnlinkSync = vi.fn();

vi.mock('node:fs', () => ({
  existsSync: (...args: unknown[]) => mockExistsSync(...args),
  readFileSync: (...args: unknown[]) => mockReadFileSync(...args),
  readdirSync: (...args: unknown[]) => mockReaddirSync(...args),
  unlinkSync: (...args: unknown[]) => mockUnlinkSync(...args),
}));

// Mock child_process for Docker CLI
const mockExecSync = vi.fn();
const mockSpawnSync = vi.fn();

vi.mock('node:child_process', () => ({
  execSync: (...args: unknown[]) => mockExecSync(...args),
  spawnSync: (...args: unknown[]) => mockSpawnSync(...args),
}));

// Mock crud module
const mockCrudModule = {
  getProjectPath: vi.fn(),
  getProjectGitUrl: vi.fn(),
  getProjectInfo: vi.fn(),
  validateProjectName: vi.fn((name: string) => {
    if (!/^[a-zA-Z0-9_-]{1,50}$/.test(name)) {
      return { valid: false, error: 'Invalid project name' };
    }
    return { valid: true };
  }),
  getContainer: vi.fn(),
  createContainer: vi.fn(),
  updateContainerStatus: vi.fn(),
  deleteContainer: vi.fn(),
  listProjectContainers: vi.fn(),
  isGracefulStopRequested: vi.fn(),
  setGracefulStop: vi.fn(),
  updateLastActivity: vi.fn(),
};

vi.mock('../../db/crud.js', () => mockCrudModule);

// Mock prompts utility
vi.mock('../../utils/prompts.js', () => ({
  getInitializerPrompt: vi.fn(() => '# Initializer Prompt'),
  getCodingPrompt: vi.fn(() => '# Coding Prompt'),
  getCodingPromptYolo: vi.fn(() => '# Coding Prompt YOLO'),
  getOverseerPrompt: vi.fn(() => '# Overseer Prompt'),
  isExistingRepoProject: vi.fn(() => false),
}));

// Mock progress utility
vi.mock('../../utils/progress.js', () => ({
  hasFeatures: vi.fn(() => true),
  hasOpenFeatures: vi.fn(() => true),
}));

// =============================================================================
// Test Setup
// =============================================================================

let testCtx: TestContext;
let app: Hono;

beforeAll(async () => {
  testCtx = createTestDatabase();

  // Dynamically import router after mocks are set up
  const { agentRouter } = await import('../agent.js');

  app = new Hono();
  app.onError((err, c) => {
    const status = 'status' in err ? (err.status as number) : 500;
    return c.json({ error: err.message, status }, status as 500);
  });
  // Mount with project name prefix to match actual routing
  app.route('/api/projects/:name/agent', agentRouter);
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
  mockReadFileSync.mockReturnValue('{}');
  mockReaddirSync.mockReturnValue([]);
  mockSpawnSync.mockReturnValue({ status: 0, stdout: '', stderr: '' });
  mockCrudModule.getProjectPath.mockReturnValue('/test/projects/my-project');
  mockCrudModule.getProjectGitUrl.mockReturnValue('https://github.com/test/repo');
  mockCrudModule.getProjectInfo.mockReturnValue({
    gitUrl: 'https://github.com/test/repo',
    localPath: '/test/projects/my-project',
    targetContainerCount: 1,
  });
  mockCrudModule.getContainer.mockReturnValue(null);
  mockCrudModule.createContainer.mockReturnValue(1);
  mockCrudModule.listProjectContainers.mockReturnValue([]);
  mockCrudModule.isGracefulStopRequested.mockReturnValue(false);
});

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Setup mock for Docker availability check.
 */
function setupDockerAvailable(available: boolean = true): void {
  mockExecSync.mockImplementation((cmd: string) => {
    if (cmd === 'docker info') {
      if (available) {
        return Buffer.from('Docker is running');
      }
      throw new Error('Docker not available');
    }
    if (cmd.includes('docker images')) {
      return Buffer.from('abc123\n'); // Image exists
    }
    if (cmd.includes('docker inspect')) {
      return Buffer.from('running\n');
    }
    if (cmd.includes('docker exec') && cmd.includes('pgrep')) {
      return Buffer.from('1234\n'); // Process running
    }
    if (cmd.includes('docker stop') || cmd.includes('docker rm')) {
      return Buffer.from('');
    }
    return Buffer.from('');
  });
}

// =============================================================================
// Tests: GET /api/projects/:name/agent/status - Get agent status
// =============================================================================

describe('GET /api/projects/:name/agent/status', () => {
  it('returns not_created status when no container exists', async () => {
    mockCrudModule.getContainer.mockReturnValue(null);

    const res = await testRequest(app, 'GET', '/api/projects/my-project/agent/status');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ status: string; agent_running: boolean }>(res);
    expect(body.status).toBe('not_created');
    expect(body.agent_running).toBe(false);
  });

  it('returns running status when container is running', async () => {
    setupDockerAvailable();
    mockCrudModule.getContainer.mockReturnValue({
      containerNumber: 1,
      status: 'running',
      createdAt: new Date().toISOString(),
    });

    const res = await testRequest(app, 'GET', '/api/projects/my-project/agent/status');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ status: string; agent_running: boolean }>(res);
    expect(body.status).toBe('running');
    expect(body.agent_running).toBe(true);
  });

  it('includes graceful_stop_requested flag', async () => {
    mockCrudModule.getContainer.mockReturnValue({
      containerNumber: 1,
      status: 'running',
      createdAt: new Date().toISOString(),
    });
    mockCrudModule.isGracefulStopRequested.mockReturnValue(true);
    setupDockerAvailable();

    const res = await testRequest(app, 'GET', '/api/projects/my-project/agent/status');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ graceful_stop_requested: boolean }>(res);
    expect(body.graceful_stop_requested).toBe(true);
  });
});

// =============================================================================
// Tests: POST /api/projects/:name/agent/start - Start agent
// =============================================================================

describe('POST /api/projects/:name/agent/start', () => {
  it('returns 503 when Docker is not available', async () => {
    mockExecSync.mockImplementation((cmd: string) => {
      if (cmd === 'docker info') {
        throw new Error('Docker not available');
      }
      return Buffer.from('');
    });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/start');

    expect(res.status).toBe(503);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('Docker');
  });

  it('returns 503 when container image is missing', async () => {
    mockExecSync.mockImplementation((cmd: string) => {
      if (cmd === 'docker info') {
        return Buffer.from('Docker running');
      }
      if (cmd.includes('docker images')) {
        return Buffer.from(''); // No image
      }
      return Buffer.from('');
    });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/start');

    expect(res.status).toBe(503);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('zerocoder-project');
  });

  it('returns 404 when project not found', async () => {
    setupDockerAvailable();
    mockCrudModule.getProjectPath.mockReturnValue(null);

    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/start');

    expect(res.status).toBe(404);
  });

  it('returns 404 when project has no git URL', async () => {
    setupDockerAvailable();
    mockCrudModule.getProjectGitUrl.mockReturnValue(null);

    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/start');

    expect(res.status).toBe(404);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('git URL');
  });

  it('starts agent successfully', async () => {
    setupDockerAvailable();

    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/start');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; status: string }>(res);
    expect(body.success).toBe(true);
    expect(body.status).toBe('running');
    expect(mockCrudModule.createContainer).toHaveBeenCalled();
    expect(mockCrudModule.updateContainerStatus).toHaveBeenCalled();
  });

  it('accepts custom instruction', async () => {
    setupDockerAvailable();

    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/start', {
      instruction: 'Custom instruction for the agent',
    });

    expect(res.status).toBe(200);
  });

  it('supports yolo_mode flag', async () => {
    setupDockerAvailable();

    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/start', {
      yolo_mode: true,
    });

    expect(res.status).toBe(200);
  });
});

// =============================================================================
// Tests: POST /api/projects/:name/agent/stop - Stop agent
// =============================================================================

describe('POST /api/projects/:name/agent/stop', () => {
  it('returns success when no containers exist', async () => {
    mockCrudModule.listProjectContainers.mockReturnValue([]);

    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/stop');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; message: string }>(res);
    expect(body.success).toBe(true);
    expect(body.message).toContain('No containers');
  });

  it('stops all running containers', async () => {
    setupDockerAvailable();
    mockCrudModule.listProjectContainers.mockReturnValue([
      { containerNumber: 1, containerType: 'coding' },
      { containerNumber: 2, containerType: 'coding' },
    ]);

    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/stop');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; message: string }>(res);
    expect(body.success).toBe(true);
    expect(body.message).toContain('2');
    expect(mockCrudModule.updateContainerStatus).toHaveBeenCalledTimes(2);
  });

  it('handles containers that fail to stop', async () => {
    mockCrudModule.listProjectContainers.mockReturnValue([
      { containerNumber: 1, containerType: 'coding' },
    ]);
    mockExecSync.mockImplementation(() => {
      throw new Error('Container not found');
    });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/stop');

    expect(res.status).toBe(200);
    // Status should still be updated even if docker stop fails
    expect(mockCrudModule.updateContainerStatus).toHaveBeenCalled();
  });
});

// =============================================================================
// Tests: POST /api/projects/:name/agent/graceful-stop - Request graceful stop
// =============================================================================

describe('POST /api/projects/:name/agent/graceful-stop', () => {
  it('sets graceful stop flag for all containers', async () => {
    mockCrudModule.listProjectContainers.mockReturnValue([
      { containerNumber: 1, containerType: 'coding' },
      { containerNumber: 2, containerType: 'coding' },
    ]);

    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/graceful-stop');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; status: string }>(res);
    expect(body.success).toBe(true);
    expect(body.status).toBe('stopping');
    expect(mockCrudModule.setGracefulStop).toHaveBeenCalledTimes(2);
  });

  it('returns success when no containers exist', async () => {
    mockCrudModule.listProjectContainers.mockReturnValue([]);

    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/graceful-stop');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ status: string }>(res);
    expect(body.status).toBe('stopped');
  });
});

// =============================================================================
// Tests: POST /api/projects/:name/agent/instruction - Send instruction
// =============================================================================

describe('POST /api/projects/:name/agent/instruction', () => {
  it('returns 400 when instruction is missing', async () => {
    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/instruction', {});

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('instruction');
  });

  it('returns 400 when container not found', async () => {
    mockCrudModule.getContainer.mockReturnValue(null);

    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/instruction', {
      instruction: 'Test instruction',
    });

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('not found');
  });

  it('returns 400 when container is not running', async () => {
    mockCrudModule.getContainer.mockReturnValue({
      containerNumber: 1,
      status: 'stopped',
    });
    mockExecSync.mockImplementation((cmd: string) => {
      if (cmd.includes('docker inspect')) {
        return Buffer.from('exited\n');
      }
      return Buffer.from('');
    });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/instruction', {
      instruction: 'Test instruction',
    });

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('not running');
  });

  it('sends instruction successfully', async () => {
    setupDockerAvailable();
    mockCrudModule.getContainer.mockReturnValue({
      containerNumber: 1,
      status: 'running',
    });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/instruction', {
      instruction: 'Continue working on the feature',
    });

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean }>(res);
    expect(body.success).toBe(true);
  });
});

// =============================================================================
// Tests: DELETE /api/projects/:name/agent/container - Remove container
// =============================================================================

describe('DELETE /api/projects/:name/agent/container', () => {
  it('removes container successfully', async () => {
    setupDockerAvailable();

    const res = await testRequest(app, 'DELETE', '/api/projects/my-project/agent/container');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean }>(res);
    expect(body.success).toBe(true);
    expect(mockCrudModule.deleteContainer).toHaveBeenCalledWith('my-project', 1, 'coding');
  });

  it('succeeds even when Docker container does not exist', async () => {
    mockExecSync.mockImplementation(() => {
      throw new Error('Container not found');
    });

    const res = await testRequest(app, 'DELETE', '/api/projects/my-project/agent/container');

    expect(res.status).toBe(200);
    expect(mockCrudModule.deleteContainer).toHaveBeenCalled();
  });
});

// =============================================================================
// Tests: Deprecated Endpoints
// =============================================================================

describe('Deprecated endpoints', () => {
  it('POST /agent/pause returns 400', async () => {
    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/pause');

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('not supported');
  });

  it('POST /agent/resume returns 400', async () => {
    const res = await testRequest(app, 'POST', '/api/projects/my-project/agent/resume');

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('not supported');
  });
});

// =============================================================================
// Tests: Container Session Endpoints (container-to-host communication)
// =============================================================================

describe('Container Session Endpoints', () => {
  describe('GET /agent/containers/:containerNumber/session', () => {
    it('returns session info for container', async () => {
      mockExistsSync.mockReturnValue(true);
      mockReadFileSync.mockReturnValue(JSON.stringify({ agent_model: 'glm-4-7' }));

      const res = await testRequest(
        app,
        'GET',
        '/api/projects/my-project/agent/containers/1/session'
      );

      expect(res.status).toBe(200);
      const body = await parseResponse<{
        should_continue: boolean;
        graceful_stop_requested: boolean;
        has_open_features: boolean;
      }>(res);
      expect(body.should_continue).toBe(true);
      expect(body.graceful_stop_requested).toBe(false);
      expect(body.has_open_features).toBe(true);
    });

    it('indicates should_continue=false when graceful stop requested', async () => {
      mockCrudModule.isGracefulStopRequested.mockReturnValue(true);

      const res = await testRequest(
        app,
        'GET',
        '/api/projects/my-project/agent/containers/1/session'
      );

      expect(res.status).toBe(200);
      const body = await parseResponse<{ should_continue: boolean }>(res);
      expect(body.should_continue).toBe(false);
    });
  });

  describe('POST /agent/containers/:containerNumber/heartbeat', () => {
    it('acknowledges heartbeat and updates activity', async () => {
      const res = await testRequest(
        app,
        'POST',
        '/api/projects/my-project/agent/containers/1/heartbeat'
      );

      expect(res.status).toBe(200);
      const body = await parseResponse<{
        acknowledged: boolean;
        graceful_stop_requested: boolean;
      }>(res);
      expect(body.acknowledged).toBe(true);
      expect(mockCrudModule.updateLastActivity).toHaveBeenCalledWith('my-project', 1, 'coding');
    });
  });

  describe('POST /agent/containers/:containerNumber/exit', () => {
    it('indicates restart needed when open features exist', async () => {
      const res = await testRequest(
        app,
        'POST',
        '/api/projects/my-project/agent/containers/1/exit'
      );

      expect(res.status).toBe(200);
      const body = await parseResponse<{
        restart: boolean;
        has_open_features: boolean;
      }>(res);
      expect(body.restart).toBe(true);
      expect(body.has_open_features).toBe(true);
    });

    it('indicates no restart when graceful stop requested', async () => {
      mockCrudModule.isGracefulStopRequested.mockReturnValue(true);

      const res = await testRequest(
        app,
        'POST',
        '/api/projects/my-project/agent/containers/1/exit'
      );

      expect(res.status).toBe(200);
      const body = await parseResponse<{ restart: boolean }>(res);
      expect(body.restart).toBe(false);
    });
  });
});

// =============================================================================
// Tests: Invalid Project Name
// =============================================================================

describe('Invalid project names', () => {
  it('returns 400 for project name with spaces', async () => {
    const res = await testRequest(app, 'GET', '/api/projects/invalid%20name/agent/status');
    expect(res.status).toBe(400);
  });

  it('returns 400 for project name with special characters', async () => {
    const res = await testRequest(app, 'GET', '/api/projects/invalid@name/agent/status');
    expect(res.status).toBe(400);
  });
});
