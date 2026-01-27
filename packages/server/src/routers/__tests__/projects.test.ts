/**
 * Projects Router Integration Tests
 *
 * Tests for project management API endpoints.
 * Uses in-memory database with mocked filesystem and Docker operations.
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
const mockReadFileSync = vi.fn();
const mockWriteFileSync = vi.fn();
const mockMkdirSync = vi.fn();
const mockUnlinkSync = vi.fn();
const mockRmSync = vi.fn();

vi.mock('node:fs', () => ({
  existsSync: (...args: unknown[]) => mockExistsSync(...args),
  readFileSync: (...args: unknown[]) => mockReadFileSync(...args),
  writeFileSync: (...args: unknown[]) => mockWriteFileSync(...args),
  mkdirSync: (...args: unknown[]) => mockMkdirSync(...args),
  unlinkSync: (...args: unknown[]) => mockUnlinkSync(...args),
  rmSync: (...args: unknown[]) => mockRmSync(...args),
}));

// Mock child_process
const mockExecSync = vi.fn();
vi.mock('node:child_process', () => ({
  execSync: (...args: unknown[]) => mockExecSync(...args),
}));

// Mock progress utility
vi.mock('../../utils/progress.js', () => ({
  countPassingTests: vi.fn(() => [3, 2, 10]), // [passing, in_progress, total]
  hasFeatures: vi.fn(() => true),
  hasOpenFeatures: vi.fn(() => true),
}));

// Mock prompts utility
vi.mock('../../utils/prompts.js', () => ({
  hasProjectPrompts: vi.fn(() => true),
  scaffoldProjectPrompts: vi.fn(),
  scaffoldExistingRepo: vi.fn(),
  getProjectPromptsDir: vi.fn((dir: string) => `${dir}/prompts`),
}));

// =============================================================================
// Test Setup
// =============================================================================

let testCtx: TestContext;
let app: Hono;

// We need to create mock CRUD functions that use our test database
const mockCrudModule = {
  registerProject: vi.fn(),
  unregisterProject: vi.fn(),
  getProjectPath: vi.fn(),
  getProjectInfo: vi.fn(),
  getProjectsDir: vi.fn(() => '/test/projects'),
  listRegisteredProjects: vi.fn(),
  validateProjectName: vi.fn((name: string) => {
    if (!/^[a-zA-Z0-9_-]{1,50}$/.test(name)) {
      return { valid: false, error: 'Invalid project name' };
    }
    return { valid: true };
  }),
  updateTargetContainerCount: vi.fn(() => true),
  listProjectContainers: vi.fn(() => []),
};

vi.mock('../../db/crud.js', () => mockCrudModule);

beforeAll(async () => {
  testCtx = createTestDatabase();

  // Dynamically import router after mocks are set up
  const { projectsRouter } = await import('../projects.js');

  app = new Hono();
  app.onError((err, c) => {
    const status = 'status' in err ? (err.status as number) : 500;
    return c.json({ error: err.message, status }, status as 500);
  });
  app.route('/api/projects', projectsRouter);
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
  mockCrudModule.listRegisteredProjects.mockReturnValue({});
  mockCrudModule.getProjectPath.mockReturnValue(null);
  mockCrudModule.getProjectInfo.mockReturnValue(null);
  mockCrudModule.listProjectContainers.mockReturnValue([]);
});

// =============================================================================
// Tests: GET /api/projects - List all projects
// =============================================================================

describe('GET /api/projects', () => {
  it('returns empty array when no projects exist', async () => {
    mockCrudModule.listRegisteredProjects.mockReturnValue({});

    const res = await testRequest(app, 'GET', '/api/projects');

    expect(res.status).toBe(200);
    const body = await parseResponse<unknown[]>(res);
    expect(body).toEqual([]);
  });

  it('returns projects with stats and status', async () => {
    mockCrudModule.listRegisteredProjects.mockReturnValue({
      'test-project': {
        gitUrl: 'https://github.com/test/repo',
        localPath: '/test/projects/test-project',
        isNew: true,
        targetContainerCount: 1,
      },
    });
    mockExistsSync.mockReturnValue(true);
    mockReadFileSync.mockReturnValue(JSON.stringify({ agent_model: 'claude-sonnet-4-5-20250514' }));

    const res = await testRequest(app, 'GET', '/api/projects');

    expect(res.status).toBe(200);
    const body = await parseResponse<Array<{ name: string; git_url: string; stats: object }>>(res);
    expect(body).toHaveLength(1);
    expect(body[0]?.name).toBe('test-project');
    expect(body[0]?.git_url).toBe('https://github.com/test/repo');
    expect(body[0]?.stats).toBeDefined();
  });

  it('skips projects with missing local directories', async () => {
    mockCrudModule.listRegisteredProjects.mockReturnValue({
      'test-project': {
        gitUrl: 'https://github.com/test/repo',
        localPath: '/nonexistent/path',
        isNew: true,
        targetContainerCount: 1,
      },
    });
    mockExistsSync.mockReturnValue(false);

    const res = await testRequest(app, 'GET', '/api/projects');

    expect(res.status).toBe(200);
    const body = await parseResponse<unknown[]>(res);
    expect(body).toEqual([]);
  });
});

// =============================================================================
// Tests: POST /api/projects - Create a new project
// =============================================================================

describe('POST /api/projects', () => {
  it('creates a new project successfully', async () => {
    mockCrudModule.getProjectPath.mockReturnValue(null);
    mockExistsSync.mockReturnValue(false);
    mockExecSync.mockReturnValue(Buffer.from(''));
    mockCrudModule.registerProject.mockResolvedValue(undefined);

    const res = await testRequest(app, 'POST', '/api/projects', {
      name: 'new-project',
      git_url: 'https://github.com/test/new-repo',
      is_new: true,
    });

    expect(res.status).toBe(200);
    const body = await parseResponse<{ name: string; git_url: string }>(res);
    expect(body.name).toBe('new-project');
    expect(body.git_url).toBe('https://github.com/test/new-repo');
  });

  it('rejects invalid project names', async () => {
    const res = await testRequest(app, 'POST', '/api/projects', {
      name: 'invalid name with spaces',
      git_url: 'https://github.com/test/repo',
      is_new: true,
    });

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('Invalid');
  });

  it('rejects duplicate project names', async () => {
    mockCrudModule.getProjectPath.mockReturnValue('/existing/path');
    mockExistsSync.mockReturnValue(true);

    const res = await testRequest(app, 'POST', '/api/projects', {
      name: 'existing-project',
      git_url: 'https://github.com/test/repo',
      is_new: true,
    });

    expect(res.status).toBe(409);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('already exists');
  });

  it('returns 500 when git clone fails', async () => {
    mockCrudModule.getProjectPath.mockReturnValue(null);
    mockExistsSync.mockReturnValue(false);
    mockExecSync.mockImplementation(() => {
      const error = new Error('Git clone failed') as Error & { stderr: Buffer };
      error.stderr = Buffer.from('fatal: repository not found');
      throw error;
    });

    const res = await testRequest(app, 'POST', '/api/projects', {
      name: 'fail-project',
      git_url: 'https://github.com/nonexistent/repo',
      is_new: true,
    });

    expect(res.status).toBe(500);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('Git clone failed');
  });
});

// =============================================================================
// Tests: GET /api/projects/:name - Get project details
// =============================================================================

describe('GET /api/projects/:name', () => {
  it('returns project details', async () => {
    mockCrudModule.getProjectInfo.mockReturnValue({
      gitUrl: 'https://github.com/test/repo',
      localPath: '/test/projects/my-project',
      isNew: true,
      targetContainerCount: 2,
    });
    mockExistsSync.mockReturnValue(true);
    mockReadFileSync.mockReturnValue(JSON.stringify({ agent_model: 'glm-4-7' }));

    const res = await testRequest(app, 'GET', '/api/projects/my-project');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ name: string; git_url: string; target_container_count: number }>(res);
    expect(body.name).toBe('my-project');
    expect(body.git_url).toBe('https://github.com/test/repo');
    expect(body.target_container_count).toBe(2);
  });

  it('returns 404 for non-existent project', async () => {
    mockCrudModule.getProjectInfo.mockReturnValue(null);

    const res = await testRequest(app, 'GET', '/api/projects/nonexistent');

    expect(res.status).toBe(404);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('not found');
  });

  it('returns 400 for invalid project name', async () => {
    const res = await testRequest(app, 'GET', '/api/projects/invalid%20name');

    expect(res.status).toBe(400);
  });
});

// =============================================================================
// Tests: DELETE /api/projects/:name - Delete a project
// =============================================================================

describe('DELETE /api/projects/:name', () => {
  it('deletes a project without removing files', async () => {
    mockCrudModule.getProjectPath.mockReturnValue('/test/projects/delete-me');
    mockExistsSync.mockImplementation((path: string) => {
      // Lock file doesn't exist
      if (path.includes('.agent.lock')) return false;
      return true;
    });
    mockCrudModule.unregisterProject.mockResolvedValue(undefined);

    const res = await testRequest(app, 'DELETE', '/api/projects/delete-me');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; message: string }>(res);
    expect(body.success).toBe(true);
    expect(body.message).toContain('files preserved');
    expect(mockRmSync).not.toHaveBeenCalled();
  });

  it('deletes a project with files when delete_files=true', async () => {
    mockCrudModule.getProjectPath.mockReturnValue('/test/projects/delete-me');
    mockExistsSync.mockImplementation((path: string) => {
      if (path.includes('.agent.lock')) return false;
      return true;
    });
    mockCrudModule.unregisterProject.mockResolvedValue(undefined);

    const res = await testRequest(app, 'DELETE', '/api/projects/delete-me?delete_files=true');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; message: string }>(res);
    expect(body.success).toBe(true);
    expect(body.message).toContain('files removed');
    expect(mockRmSync).toHaveBeenCalled();
  });

  it('returns 409 when agent is running', async () => {
    mockCrudModule.getProjectPath.mockReturnValue('/test/projects/running-project');
    mockExistsSync.mockReturnValue(true); // Lock file exists

    const res = await testRequest(app, 'DELETE', '/api/projects/running-project');

    expect(res.status).toBe(409);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('agent is running');
  });

  it('returns 404 for non-existent project', async () => {
    mockCrudModule.getProjectPath.mockReturnValue(null);

    const res = await testRequest(app, 'DELETE', '/api/projects/nonexistent');

    expect(res.status).toBe(404);
  });
});

// =============================================================================
// Tests: GET /api/projects/:name/prompts - Get project prompts
// =============================================================================

describe('GET /api/projects/:name/prompts', () => {
  it('returns project prompts', async () => {
    mockCrudModule.getProjectPath.mockReturnValue('/test/projects/my-project');
    mockExistsSync.mockReturnValue(true);
    mockReadFileSync.mockImplementation((path: string) => {
      if (path.includes('app_spec.txt')) return 'App specification';
      if (path.includes('initializer_prompt.md')) return '# Initializer';
      if (path.includes('coding_prompt.md')) return '# Coding';
      return '';
    });

    const res = await testRequest(app, 'GET', '/api/projects/my-project/prompts');

    expect(res.status).toBe(200);
    const body = await parseResponse<{
      app_spec: string;
      initializer_prompt: string;
      coding_prompt: string;
    }>(res);
    expect(body.app_spec).toBe('App specification');
    expect(body.initializer_prompt).toBe('# Initializer');
    expect(body.coding_prompt).toBe('# Coding');
  });

  it('returns 404 for non-existent project', async () => {
    mockCrudModule.getProjectPath.mockReturnValue(null);

    const res = await testRequest(app, 'GET', '/api/projects/nonexistent/prompts');

    expect(res.status).toBe(404);
  });
});

// =============================================================================
// Tests: PUT /api/projects/:name/prompts - Update project prompts
// =============================================================================

describe('PUT /api/projects/:name/prompts', () => {
  it('updates project prompts', async () => {
    mockCrudModule.getProjectPath.mockReturnValue('/test/projects/my-project');
    mockExistsSync.mockReturnValue(true);

    const res = await testRequest(app, 'PUT', '/api/projects/my-project/prompts', {
      app_spec: 'New spec',
      initializer_prompt: 'New initializer',
      coding_prompt: 'New coding',
    });

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean }>(res);
    expect(body.success).toBe(true);
    expect(mockWriteFileSync).toHaveBeenCalled();
  });
});

// =============================================================================
// Tests: GET /api/projects/:name/stats - Get project statistics
// =============================================================================

describe('GET /api/projects/:name/stats', () => {
  it('returns project statistics', async () => {
    mockCrudModule.getProjectPath.mockReturnValue('/test/projects/my-project');
    mockExistsSync.mockReturnValue(true);

    const res = await testRequest(app, 'GET', '/api/projects/my-project/stats');

    expect(res.status).toBe(200);
    const body = await parseResponse<{
      passing: number;
      in_progress: number;
      total: number;
      percentage: number;
    }>(res);
    expect(body.passing).toBe(3);
    expect(body.in_progress).toBe(2);
    expect(body.total).toBe(10);
    expect(body.percentage).toBe(30);
  });
});

// =============================================================================
// Tests: PATCH /api/projects/:name/settings - Update project settings
// =============================================================================

describe('PATCH /api/projects/:name/settings', () => {
  it('updates agent model setting', async () => {
    mockCrudModule.getProjectPath.mockReturnValue('/test/projects/my-project');
    mockExistsSync.mockReturnValue(true);
    mockReadFileSync.mockReturnValue('{}');

    const res = await testRequest(app, 'PATCH', '/api/projects/my-project/settings', {
      agent_model: 'claude-sonnet-4-5-20250514',
    });

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; agent_model: string }>(res);
    expect(body.success).toBe(true);
    expect(body.agent_model).toBe('claude-sonnet-4-5-20250514');
  });

  it('rejects invalid model', async () => {
    mockCrudModule.getProjectPath.mockReturnValue('/test/projects/my-project');
    mockExistsSync.mockReturnValue(true);

    const res = await testRequest(app, 'PATCH', '/api/projects/my-project/settings', {
      agent_model: 'invalid-model',
    });

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('Invalid model');
  });
});

// =============================================================================
// Tests: PUT /api/projects/:name/containers/count - Update container count
// =============================================================================

describe('PUT /api/projects/:name/containers/count', () => {
  it('updates target container count', async () => {
    mockCrudModule.getProjectPath.mockReturnValue('/test/projects/my-project');
    mockCrudModule.updateTargetContainerCount.mockReturnValue(true);

    const res = await testRequest(app, 'PUT', '/api/projects/my-project/containers/count', {
      target_count: 3,
    });

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; target_count: number }>(res);
    expect(body.success).toBe(true);
    expect(body.target_count).toBe(3);
    expect(mockCrudModule.updateTargetContainerCount).toHaveBeenCalledWith('my-project', 3);
  });
});

// =============================================================================
// Tests: GET /api/projects/:name/containers - List project containers
// =============================================================================

describe('GET /api/projects/:name/containers', () => {
  it('returns list of containers', async () => {
    mockCrudModule.getProjectPath.mockReturnValue('/test/projects/my-project');
    mockCrudModule.listProjectContainers.mockReturnValue([
      {
        containerNumber: 1,
        containerType: 'coding',
        status: 'running',
        currentFeature: 'feat-1',
        dockerContainerId: 'abc123',
      } as never,
      {
        containerNumber: 2,
        containerType: 'coding',
        status: 'stopped',
        currentFeature: null,
        dockerContainerId: 'def456',
      } as never,
    ]);
    mockExecSync.mockReturnValue(Buffer.from('running\n'));

    const res = await testRequest(app, 'GET', '/api/projects/my-project/containers');

    expect(res.status).toBe(200);
    const body = await parseResponse<
      Array<{ container_number: number; container_type: string; status: string }>
    >(res);
    expect(body).toHaveLength(2);
    expect(body[0]?.container_number).toBe(1);
    expect(body[0]?.status).toBe('running');
  });
});

// =============================================================================
// Tests: POST /api/projects/add-existing - Add existing repository
// =============================================================================

describe('POST /api/projects/add-existing', () => {
  it('adds an existing repository', async () => {
    mockCrudModule.getProjectPath.mockReturnValue(null);
    mockExistsSync.mockImplementation((path: string) => {
      // Local path doesn't exist yet, beads config doesn't exist
      if (path.includes('.beads')) return false;
      return false;
    });
    mockExecSync.mockReturnValue(Buffer.from(''));
    mockCrudModule.registerProject.mockResolvedValue(undefined);

    const res = await testRequest(app, 'POST', '/api/projects/add-existing', {
      name: 'existing-repo',
      git_url: 'https://github.com/test/existing',
    });

    expect(res.status).toBe(200);
    const body = await parseResponse<{ name: string; is_new: boolean; has_spec: boolean }>(res);
    expect(body.name).toBe('existing-repo');
    expect(body.is_new).toBe(false);
    expect(body.has_spec).toBe(false);
  });
});

// =============================================================================
// Tests: Edit Mode Endpoints
// =============================================================================

describe('Edit Mode', () => {
  describe('POST /api/projects/:name/edit/start', () => {
    it('starts edit mode', async () => {
      mockCrudModule.getProjectPath.mockReturnValue('/test/projects/my-project');

      const res = await testRequest(app, 'POST', '/api/projects/my-project/edit/start');

      expect(res.status).toBe(200);
      const body = await parseResponse<{ success: boolean; edit_mode: boolean }>(res);
      expect(body.success).toBe(true);
      expect(body.edit_mode).toBe(true);
    });

    it('returns success if already in edit mode', async () => {
      mockCrudModule.getProjectPath.mockReturnValue('/test/projects/my-project');

      // Start edit mode first
      await testRequest(app, 'POST', '/api/projects/my-project/edit/start');

      // Try to start again
      const res = await testRequest(app, 'POST', '/api/projects/my-project/edit/start');

      expect(res.status).toBe(200);
      const body = await parseResponse<{ message: string }>(res);
      expect(body.message).toContain('Already in edit mode');
    });
  });

  describe('POST /api/projects/:name/edit/save', () => {
    it('saves and exits edit mode', async () => {
      mockCrudModule.getProjectPath.mockReturnValue('/test/projects/my-project');

      // Start edit mode first
      await testRequest(app, 'POST', '/api/projects/my-project/edit/start');

      const res = await testRequest(app, 'POST', '/api/projects/my-project/edit/save');

      expect(res.status).toBe(200);
      const body = await parseResponse<{ success: boolean; edit_mode: boolean }>(res);
      expect(body.success).toBe(true);
      expect(body.edit_mode).toBe(false);
    });

    it('returns 400 if not in edit mode', async () => {
      mockCrudModule.getProjectPath.mockReturnValue('/test/projects/my-project');

      const res = await testRequest(app, 'POST', '/api/projects/my-project/edit/save');

      expect(res.status).toBe(400);
      const body = await parseResponse<{ error: string }>(res);
      expect(body.error).toContain('not in edit mode');
    });
  });
});
