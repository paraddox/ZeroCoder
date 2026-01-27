/**
 * Features Router Integration Tests
 *
 * Tests for feature/task management API endpoints.
 * Mocks beads CLI operations and filesystem.
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
vi.mock('node:fs', () => ({
  existsSync: (...args: unknown[]) => mockExistsSync(...args),
}));

// Mock child_process for beads CLI
const mockExecSync = vi.fn();
vi.mock('node:child_process', () => ({
  execSync: (...args: unknown[]) => mockExecSync(...args),
}));

// Mock crud module
const mockCrudModule = {
  getProjectPath: vi.fn(),
  getProjectGitUrl: vi.fn(),
  listProjectContainers: vi.fn(() => []),
};

vi.mock('../../db/crud.js', () => mockCrudModule);

// =============================================================================
// Test Data
// =============================================================================

const sampleTasks = [
  {
    id: 'feat-1',
    title: 'Add user authentication',
    status: 'open',
    priority: 1,
    labels: ['auth'],
    description: '1. Create login form\n2. Implement JWT\n3. Add session management',
  },
  {
    id: 'feat-2',
    title: 'Setup database schema',
    status: 'in_progress',
    priority: 2,
    labels: ['database'],
    description: 'Create initial database schema',
  },
  {
    id: 'feat-3',
    title: 'Write unit tests',
    status: 'closed',
    priority: 3,
    labels: ['testing'],
    description: 'Add comprehensive unit tests',
  },
];

// =============================================================================
// Test Setup
// =============================================================================

let testCtx: TestContext;
let app: Hono;

beforeAll(async () => {
  testCtx = createTestDatabase();

  // Dynamically import router after mocks are set up
  const { featuresRouter } = await import('../features.js');

  app = new Hono();
  app.onError((err, c) => {
    const status = 'status' in err ? (err.status as number) : 500;
    return c.json({ error: err.message, status }, status as 500);
  });
  app.route('/api/projects', featuresRouter);
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
  mockCrudModule.getProjectPath.mockReturnValue('/test/projects/my-project');
  mockCrudModule.getProjectGitUrl.mockReturnValue('https://github.com/test/repo');
  mockCrudModule.listProjectContainers.mockReturnValue([]);
});

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Setup mock for beads list command.
 */
function setupBeadsListMock(tasks: typeof sampleTasks): void {
  mockExecSync.mockImplementation((cmd: string) => {
    if (cmd.includes('bd') && cmd.includes('list')) {
      return Buffer.from(JSON.stringify(tasks));
    }
    return Buffer.from('');
  });
}

// =============================================================================
// Tests: GET /api/projects/:name/features - List features
// =============================================================================

describe('GET /api/projects/:name/features', () => {
  it('returns features grouped by status', async () => {
    setupBeadsListMock(sampleTasks);

    const res = await testRequest(app, 'GET', '/api/projects/my-project/features');

    expect(res.status).toBe(200);
    const body = await parseResponse<{
      pending: unknown[];
      in_progress: unknown[];
      done: unknown[];
    }>(res);

    expect(body.pending).toHaveLength(1);
    expect(body.in_progress).toHaveLength(1);
    expect(body.done).toHaveLength(1);
  });

  it('returns empty lists when no features exist', async () => {
    setupBeadsListMock([]);

    const res = await testRequest(app, 'GET', '/api/projects/my-project/features');

    expect(res.status).toBe(200);
    const body = await parseResponse<{
      pending: unknown[];
      in_progress: unknown[];
      done: unknown[];
    }>(res);

    expect(body.pending).toEqual([]);
    expect(body.in_progress).toEqual([]);
    expect(body.done).toEqual([]);
  });

  it('returns 404 for non-existent project', async () => {
    mockCrudModule.getProjectPath.mockReturnValue(null);

    const res = await testRequest(app, 'GET', '/api/projects/nonexistent/features');

    expect(res.status).toBe(404);
  });

  it('returns 404 when project directory is missing', async () => {
    mockExistsSync.mockReturnValue(false);

    const res = await testRequest(app, 'GET', '/api/projects/my-project/features');

    expect(res.status).toBe(404);
  });

  it('parses feature steps from description', async () => {
    setupBeadsListMock([sampleTasks[0]!]);

    const res = await testRequest(app, 'GET', '/api/projects/my-project/features');

    expect(res.status).toBe(200);
    const body = await parseResponse<{
      pending: Array<{ steps: string[] }>;
    }>(res);

    expect(body.pending[0]?.steps).toEqual([
      'Create login form',
      'Implement JWT',
      'Add session management',
    ]);
  });

  it('marks features being worked on by containers as in_progress', async () => {
    mockCrudModule.listProjectContainers.mockReturnValue([
      { currentFeature: 'feat-1' } as never,
    ]);
    setupBeadsListMock([{ ...sampleTasks[0]!, status: 'open' }]);

    const res = await testRequest(app, 'GET', '/api/projects/my-project/features');

    expect(res.status).toBe(200);
    const body = await parseResponse<{
      pending: unknown[];
      in_progress: unknown[];
    }>(res);

    expect(body.pending).toHaveLength(0);
    expect(body.in_progress).toHaveLength(1);
  });
});

// =============================================================================
// Tests: POST /api/projects/:name/features - Create feature
// =============================================================================

describe('POST /api/projects/:name/features', () => {
  it('creates a new feature', async () => {
    mockExecSync.mockImplementation((cmd: string) => {
      if (cmd.includes('create')) {
        return Buffer.from(JSON.stringify({ id: 'feat-4' }));
      }
      if (cmd.includes('list')) {
        return Buffer.from(
          JSON.stringify([
            {
              id: 'feat-4',
              title: 'New Feature',
              status: 'open',
              priority: 2,
              labels: [],
            },
          ])
        );
      }
      return Buffer.from('');
    });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/features', {
      name: 'New Feature',
      description: 'A new feature description',
      category: 'frontend',
      steps: [],
      priority: 2,
    });

    expect(res.status).toBe(200);
    const body = await parseResponse<{ id: string; name: string }>(res);
    expect(body.id).toBe('feat-4');
    expect(body.name).toBe('New Feature');
  });

  it('creates feature with steps in description', async () => {
    mockExecSync.mockImplementation((cmd: string) => {
      if (cmd.includes('create')) {
        // Verify description contains numbered steps
        expect(cmd).toContain('1. Step one');
        expect(cmd).toContain('2. Step two');
        return Buffer.from(JSON.stringify({ id: 'feat-5' }));
      }
      if (cmd.includes('list')) {
        return Buffer.from(
          JSON.stringify([{ id: 'feat-5', title: 'Test', status: 'open', priority: 2, labels: [] }])
        );
      }
      return Buffer.from('');
    });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/features', {
      name: 'Test',
      description: '',
      category: 'backend',
      steps: ['Step one', 'Step two'],
    });

    expect(res.status).toBe(200);
  });

  it('returns 404 for non-existent project', async () => {
    mockCrudModule.getProjectPath.mockReturnValue(null);

    const res = await testRequest(app, 'POST', '/api/projects/nonexistent/features', {
      name: 'Test',
      description: 'Test description',
      category: 'test',
      steps: [],
    });

    expect(res.status).toBe(404);
  });

  it('returns 400 for invalid request body', async () => {
    const res = await testRequest(app, 'POST', '/api/projects/my-project/features', {
      // Missing required fields
      description: 'No name provided',
    });

    expect(res.status).toBe(400);
  });

  it('returns 500 when beads command fails', async () => {
    mockExecSync.mockImplementation(() => {
      const error = new Error('beads error') as Error & { stderr: Buffer };
      error.stderr = Buffer.from('bd: command failed');
      throw error;
    });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/features', {
      name: 'Test Feature',
      description: 'Test description',
      category: 'test',
      steps: [],
    });

    expect(res.status).toBe(500);
  });
});

// =============================================================================
// Tests: GET /api/projects/:name/features/:featureId - Get feature
// =============================================================================

describe('GET /api/projects/:name/features/:featureId', () => {
  it('returns feature details', async () => {
    setupBeadsListMock(sampleTasks);

    const res = await testRequest(app, 'GET', '/api/projects/my-project/features/feat-1');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ id: string; name: string }>(res);
    expect(body.id).toBe('feat-1');
    expect(body.name).toBe('Add user authentication');
  });

  it('returns 404 for non-existent feature', async () => {
    setupBeadsListMock([]);

    const res = await testRequest(app, 'GET', '/api/projects/my-project/features/feat-999');

    expect(res.status).toBe(404);
  });
});

// =============================================================================
// Tests: DELETE /api/projects/:name/features/:featureId - Delete feature
// =============================================================================

describe('DELETE /api/projects/:name/features/:featureId', () => {
  it('deletes a feature', async () => {
    mockExecSync.mockImplementation((cmd: string) => {
      if (cmd.includes('list')) {
        return Buffer.from(JSON.stringify(sampleTasks));
      }
      if (cmd.includes('delete')) {
        return Buffer.from('');
      }
      return Buffer.from('');
    });

    const res = await testRequest(app, 'DELETE', '/api/projects/my-project/features/feat-1');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean }>(res);
    expect(body.success).toBe(true);
  });

  it('returns 404 for non-existent feature', async () => {
    setupBeadsListMock([]);

    const res = await testRequest(app, 'DELETE', '/api/projects/my-project/features/feat-999');

    expect(res.status).toBe(404);
  });
});

// =============================================================================
// Tests: PATCH /api/projects/:name/features/:featureId - Update feature
// =============================================================================

describe('PATCH /api/projects/:name/features/:featureId', () => {
  it('updates feature name', async () => {
    const updatedTask = { ...sampleTasks[0]!, title: 'Updated Name' };
    mockExecSync.mockImplementation((cmd: string) => {
      if (cmd.includes('list')) {
        return Buffer.from(JSON.stringify([updatedTask]));
      }
      if (cmd.includes('update')) {
        return Buffer.from('');
      }
      return Buffer.from('');
    });

    const res = await testRequest(app, 'PATCH', '/api/projects/my-project/features/feat-1', {
      name: 'Updated Name',
    });

    expect(res.status).toBe(200);
    const body = await parseResponse<{ name: string }>(res);
    expect(body.name).toBe('Updated Name');
  });

  it('updates feature priority', async () => {
    const updatedTask = { ...sampleTasks[0]!, priority: 0 };
    mockExecSync.mockImplementation((cmd: string) => {
      if (cmd.includes('list')) {
        return Buffer.from(JSON.stringify([updatedTask]));
      }
      if (cmd.includes('update')) {
        expect(cmd).toContain('P0');
        return Buffer.from('');
      }
      return Buffer.from('');
    });

    const res = await testRequest(app, 'PATCH', '/api/projects/my-project/features/feat-1', {
      priority: 0,
    });

    expect(res.status).toBe(200);
  });

  it('returns 400 when no update fields provided', async () => {
    setupBeadsListMock(sampleTasks);

    const res = await testRequest(app, 'PATCH', '/api/projects/my-project/features/feat-1', {});

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('No update fields');
  });

  it('returns 404 for non-existent feature', async () => {
    setupBeadsListMock([]);

    const res = await testRequest(app, 'PATCH', '/api/projects/my-project/features/feat-999', {
      name: 'New Name',
    });

    expect(res.status).toBe(404);
  });
});

// =============================================================================
// Tests: PATCH /api/projects/:name/features/:featureId/skip - Skip feature
// =============================================================================

describe('PATCH /api/projects/:name/features/:featureId/skip', () => {
  it('sets feature priority to P4 (backlog)', async () => {
    mockExecSync.mockImplementation((cmd: string) => {
      if (cmd.includes('list')) {
        return Buffer.from(JSON.stringify(sampleTasks));
      }
      if (cmd.includes('update') && cmd.includes('P4')) {
        return Buffer.from('');
      }
      return Buffer.from('');
    });

    const res = await testRequest(app, 'PATCH', '/api/projects/my-project/features/feat-1/skip');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean }>(res);
    expect(body.success).toBe(true);
  });
});

// =============================================================================
// Tests: PATCH /api/projects/:name/features/:featureId/reopen - Reopen feature
// =============================================================================

describe('PATCH /api/projects/:name/features/:featureId/reopen', () => {
  it('reopens a closed feature', async () => {
    mockExecSync.mockImplementation((cmd: string) => {
      if (cmd.includes('list')) {
        return Buffer.from(JSON.stringify([sampleTasks[2]])); // feat-3 is closed
      }
      if (cmd.includes('reopen')) {
        return Buffer.from('');
      }
      return Buffer.from('');
    });

    const res = await testRequest(app, 'PATCH', '/api/projects/my-project/features/feat-3/reopen');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean }>(res);
    expect(body.success).toBe(true);
  });

  it('returns 400 when trying to reopen a non-closed feature', async () => {
    mockExecSync.mockImplementation((cmd: string) => {
      if (cmd.includes('list')) {
        return Buffer.from(JSON.stringify([sampleTasks[0]])); // feat-1 is open
      }
      return Buffer.from('');
    });

    const res = await testRequest(app, 'PATCH', '/api/projects/my-project/features/feat-1/reopen');

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('not completed');
  });
});

// =============================================================================
// Tests: Invalid Project Name
// =============================================================================

describe('Invalid project names', () => {
  it('returns 400 for project name with spaces', async () => {
    const res = await testRequest(app, 'GET', '/api/projects/invalid%20name/features');
    expect(res.status).toBe(400);
  });

  it('returns 400 for project name with special characters', async () => {
    const res = await testRequest(app, 'GET', '/api/projects/invalid@name/features');
    expect(res.status).toBe(400);
  });
});
