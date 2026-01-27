/**
 * Beads API Router Integration Tests
 *
 * Tests for the host-based beads API wrapper endpoints.
 * Mocks BeadsManager service for beads CLI operations.
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

// Mock BeadsManager service
const mockBeadsManager = {
  getTasks: vi.fn(),
  getTasksByStatus: vi.fn(),
  getStats: vi.fn(),
  runReadCommand: vi.fn(),
  createIssue: vi.fn(),
  updateIssue: vi.fn(),
  closeIssue: vi.fn(),
  reopenIssue: vi.fn(),
  sync: vi.fn(),
  addDependency: vi.fn(),
  addComment: vi.fn(),
};

vi.mock('../../services/beads-manager.js', () => ({
  getBeadsManager: vi.fn(() => Promise.resolve(mockBeadsManager)),
  BeadsTask: {},
}));

// Mock crud module
const mockCrudModule = {
  getContainer: vi.fn(),
  updateContainerStatus: vi.fn(),
  setLastClosedFeature: vi.fn(),
};

vi.mock('../../db/crud.js', () => mockCrudModule);

// =============================================================================
// Test Data
// =============================================================================

const sampleTasks = [
  {
    id: 'feat-1',
    title: 'Feature 1',
    status: 'open',
    priority: 1,
    labels: ['frontend'],
  },
  {
    id: 'feat-2',
    title: 'Feature 2',
    status: 'in_progress',
    priority: 2,
    labels: [],
  },
  {
    id: 'feat-3',
    title: 'Feature 3',
    status: 'closed',
    priority: 3,
    labels: ['backend'],
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
  const { beadsApiRouter } = await import('../beads-api.js');

  app = new Hono();
  app.onError((err, c) => {
    const status = 'status' in err ? (err.status as number) : 500;
    return c.json({ error: err.message, status }, status as 500);
  });
  app.route('/api/projects', beadsApiRouter);
});

afterAll(() => {
  testCtx.cleanup();
  vi.clearAllMocks();
});

beforeEach(() => {
  clearTestDatabase(testCtx.sqlite);
  vi.clearAllMocks();

  // Reset default mock behaviors
  mockBeadsManager.getTasks.mockReturnValue(sampleTasks);
  mockBeadsManager.getTasksByStatus.mockImplementation((status: string) =>
    sampleTasks.filter((t) => t.status === status)
  );
  mockBeadsManager.getStats.mockReturnValue({
    open: 1,
    in_progress: 1,
    closed: 1,
    total: 3,
  });
  mockBeadsManager.runReadCommand.mockResolvedValue({ data: [], error: null });
  mockCrudModule.getContainer.mockReturnValue(null);
});

// =============================================================================
// Tests: GET /api/projects/:name/beads/list - List issues
// =============================================================================

describe('GET /api/projects/:name/beads/list', () => {
  it('returns all issues', async () => {
    const res = await testRequest(app, 'GET', '/api/projects/my-project/beads/list');

    expect(res.status).toBe(200);
    const body = await parseResponse<typeof sampleTasks>(res);
    expect(body).toHaveLength(3);
    expect(mockBeadsManager.getTasks).toHaveBeenCalled();
  });

  it('filters by status when query param provided', async () => {
    mockBeadsManager.getTasksByStatus.mockReturnValue([sampleTasks[0]]);

    const res = await testRequest(app, 'GET', '/api/projects/my-project/beads/list?status=open');

    expect(res.status).toBe(200);
    const body = await parseResponse<typeof sampleTasks>(res);
    expect(body).toHaveLength(1);
    expect(mockBeadsManager.getTasksByStatus).toHaveBeenCalledWith('open');
  });

  it('returns 400 for invalid project name', async () => {
    const res = await testRequest(app, 'GET', '/api/projects/invalid%20name/beads/list');

    expect(res.status).toBe(400);
  });
});

// =============================================================================
// Tests: GET /api/projects/:name/beads/ready - List ready issues
// =============================================================================

describe('GET /api/projects/:name/beads/ready', () => {
  it('returns issues ready for work', async () => {
    mockBeadsManager.runReadCommand.mockResolvedValue({
      data: [sampleTasks[0]],
      error: null,
    });

    const res = await testRequest(app, 'GET', '/api/projects/my-project/beads/ready');

    expect(res.status).toBe(200);
    const body = await parseResponse<typeof sampleTasks>(res);
    expect(body).toHaveLength(1);
    expect(mockBeadsManager.runReadCommand).toHaveBeenCalledWith(['ready', '--json']);
  });

  it('returns 500 on error', async () => {
    mockBeadsManager.runReadCommand.mockResolvedValue({
      data: null,
      error: 'bd command failed',
    });

    const res = await testRequest(app, 'GET', '/api/projects/my-project/beads/ready');

    expect(res.status).toBe(500);
  });
});

// =============================================================================
// Tests: GET /api/projects/:name/beads/show/:issueId - Get issue details
// =============================================================================

describe('GET /api/projects/:name/beads/show/:issueId', () => {
  it('returns issue details', async () => {
    mockBeadsManager.runReadCommand.mockResolvedValue({
      data: [sampleTasks[0]],
      error: null,
    });

    const res = await testRequest(app, 'GET', '/api/projects/my-project/beads/show/feat-1');

    expect(res.status).toBe(200);
    expect(mockBeadsManager.runReadCommand).toHaveBeenCalledWith(['show', 'feat-1', '--json']);
  });

  it('returns 404 when issue not found', async () => {
    mockBeadsManager.runReadCommand.mockResolvedValue({
      data: null,
      error: 'Issue not found',
    });

    const res = await testRequest(app, 'GET', '/api/projects/my-project/beads/show/feat-999');

    expect(res.status).toBe(404);
  });

  it('returns 400 for invalid issue ID format', async () => {
    const res = await testRequest(app, 'GET', '/api/projects/my-project/beads/show/invalid');

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('Invalid issue ID');
  });
});

// =============================================================================
// Tests: GET /api/projects/:name/beads/stats - Get project statistics
// =============================================================================

describe('GET /api/projects/:name/beads/stats', () => {
  it('returns project statistics', async () => {
    const res = await testRequest(app, 'GET', '/api/projects/my-project/beads/stats');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ open: number; in_progress: number; closed: number }>(res);
    expect(body.open).toBe(1);
    expect(body.in_progress).toBe(1);
    expect(body.closed).toBe(1);
  });
});

// =============================================================================
// Tests: POST /api/projects/:name/beads/create - Create issue
// =============================================================================

describe('POST /api/projects/:name/beads/create', () => {
  it('creates a new issue', async () => {
    mockBeadsManager.createIssue.mockResolvedValue({
      data: { id: 'feat-4' },
      error: null,
    });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/create', {
      title: 'New Issue',
      description: 'Issue description',
      type: 'task',
      priority: 2,
    });

    expect(res.status).toBe(200);
    expect(mockBeadsManager.createIssue).toHaveBeenCalledWith(
      'New Issue',
      'task',
      2,
      'Issue description',
      undefined
    );
  });

  it('creates issue with labels', async () => {
    mockBeadsManager.createIssue.mockResolvedValue({
      data: { id: 'feat-4' },
      error: null,
    });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/create', {
      title: 'Labeled Issue',
      type: 'feature',
      priority: 1,
      labels: ['frontend', 'urgent'],
    });

    expect(res.status).toBe(200);
    expect(mockBeadsManager.createIssue).toHaveBeenCalledWith(
      'Labeled Issue',
      'feature',
      1,
      '',
      ['frontend', 'urgent']
    );
  });

  it('returns 400 for invalid request', async () => {
    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/create', {
      // Missing required title
      description: 'No title',
    });

    expect(res.status).toBe(400);
  });

  it('returns 500 on creation error', async () => {
    mockBeadsManager.createIssue.mockResolvedValue({
      data: null,
      error: 'Failed to create issue',
    });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/create', {
      title: 'Test',
    });

    expect(res.status).toBe(500);
  });
});

// =============================================================================
// Tests: POST /api/projects/:name/beads/claim - Claim next issue
// =============================================================================

describe('POST /api/projects/:name/beads/claim', () => {
  it('claims the next available open issue', async () => {
    mockBeadsManager.runReadCommand.mockResolvedValue({
      data: [{ ...sampleTasks[0], status: 'open' }],
      error: null,
    });
    mockBeadsManager.updateIssue.mockResolvedValue({ error: null });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/claim');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; issue: { id: string } }>(res);
    expect(body.success).toBe(true);
    expect(body.issue.id).toBe('feat-1');
    expect(mockBeadsManager.updateIssue).toHaveBeenCalledWith('feat-1', { status: 'in_progress' });
  });

  it('updates container current_feature when X-Container-Number header provided', async () => {
    mockBeadsManager.runReadCommand.mockResolvedValue({
      data: [{ ...sampleTasks[0], status: 'open' }],
      error: null,
    });
    mockBeadsManager.updateIssue.mockResolvedValue({ error: null });

    const res = await testRequest(
      app,
      'POST',
      '/api/projects/my-project/beads/claim',
      undefined,
      { 'X-Container-Number': '1' }
    );

    expect(res.status).toBe(200);
    expect(mockCrudModule.updateContainerStatus).toHaveBeenCalledWith(
      'my-project',
      1,
      'coding',
      { currentFeature: 'feat-1' }
    );
  });

  it('returns no issues available when all claimed', async () => {
    mockBeadsManager.runReadCommand.mockResolvedValue({
      data: [{ ...sampleTasks[1], status: 'in_progress' }], // Only in_progress
      error: null,
    });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/claim');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; message: string }>(res);
    expect(body.success).toBe(false);
    expect(body.message).toContain('No issues available');
  });

  it('returns 500 on ready command error', async () => {
    mockBeadsManager.runReadCommand.mockResolvedValue({
      data: null,
      error: 'Failed to get ready issues',
    });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/claim');

    expect(res.status).toBe(500);
  });
});

// =============================================================================
// Tests: PATCH /api/projects/:name/beads/update/:issueId - Update issue
// =============================================================================

describe('PATCH /api/projects/:name/beads/update/:issueId', () => {
  it('updates issue status', async () => {
    mockBeadsManager.updateIssue.mockResolvedValue({ error: null });

    const res = await testRequest(app, 'PATCH', '/api/projects/my-project/beads/update/feat-1', {
      status: 'in_progress',
    });

    expect(res.status).toBe(200);
    expect(mockBeadsManager.updateIssue).toHaveBeenCalledWith('feat-1', { status: 'in_progress' });
  });

  it('updates multiple fields', async () => {
    mockBeadsManager.updateIssue.mockResolvedValue({ error: null });

    const res = await testRequest(app, 'PATCH', '/api/projects/my-project/beads/update/feat-1', {
      title: 'Updated Title',
      priority: 0,
      assignee: 'dev1',
    });

    expect(res.status).toBe(200);
    expect(mockBeadsManager.updateIssue).toHaveBeenCalledWith('feat-1', {
      title: 'Updated Title',
      priority: 0,
      assignee: 'dev1',
    });
  });

  it('returns 400 when no update fields provided', async () => {
    const res = await testRequest(app, 'PATCH', '/api/projects/my-project/beads/update/feat-1', {});

    expect(res.status).toBe(400);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('No update fields');
  });

  it('returns 404 when issue not found', async () => {
    mockBeadsManager.updateIssue.mockResolvedValue({
      error: 'Issue not found',
    });

    const res = await testRequest(app, 'PATCH', '/api/projects/my-project/beads/update/feat-999', {
      status: 'closed',
    });

    expect(res.status).toBe(404);
  });
});

// =============================================================================
// Tests: POST /api/projects/:name/beads/close/:issueId - Close issue
// =============================================================================

describe('POST /api/projects/:name/beads/close/:issueId', () => {
  it('closes an issue', async () => {
    mockBeadsManager.closeIssue.mockResolvedValue({ error: null });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/close/feat-1');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean }>(res);
    expect(body.success).toBe(true);
    expect(mockBeadsManager.closeIssue).toHaveBeenCalledWith('feat-1', undefined);
  });

  it('closes with reason', async () => {
    mockBeadsManager.closeIssue.mockResolvedValue({ error: null });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/close/feat-1', {
      reason: 'Completed implementation',
    });

    expect(res.status).toBe(200);
    expect(mockBeadsManager.closeIssue).toHaveBeenCalledWith('feat-1', 'Completed implementation');
  });

  it('tracks closed feature for container', async () => {
    mockBeadsManager.closeIssue.mockResolvedValue({ error: null });
    mockCrudModule.getContainer.mockReturnValue({ currentFeature: 'feat-1' });

    const res = await testRequest(
      app,
      'POST',
      '/api/projects/my-project/beads/close/feat-1',
      undefined,
      { 'X-Container-Number': '1' }
    );

    expect(res.status).toBe(200);
    expect(mockCrudModule.setLastClosedFeature).toHaveBeenCalledWith('my-project', 1, 'feat-1');
    expect(mockCrudModule.updateContainerStatus).toHaveBeenCalledWith(
      'my-project',
      1,
      'coding',
      { currentFeature: '' }
    );
  });

  it('returns 404 when issue not found', async () => {
    mockBeadsManager.closeIssue.mockResolvedValue({
      error: 'Issue not found',
    });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/close/feat-999');

    expect(res.status).toBe(404);
  });
});

// =============================================================================
// Tests: POST /api/projects/:name/beads/reopen/:issueId - Reopen issue
// =============================================================================

describe('POST /api/projects/:name/beads/reopen/:issueId', () => {
  it('reopens an issue', async () => {
    mockBeadsManager.reopenIssue.mockResolvedValue({ error: null });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/reopen/feat-3');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean }>(res);
    expect(body.success).toBe(true);
  });

  it('returns 404 when issue not found', async () => {
    mockBeadsManager.reopenIssue.mockResolvedValue({
      error: 'Issue not found',
    });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/reopen/feat-999');

    expect(res.status).toBe(404);
  });
});

// =============================================================================
// Tests: POST /api/projects/:name/beads/sync - Sync with remote
// =============================================================================

describe('POST /api/projects/:name/beads/sync', () => {
  it('syncs beads with remote', async () => {
    mockBeadsManager.sync.mockResolvedValue([true, 'Synced successfully']);

    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/sync');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean }>(res);
    expect(body.success).toBe(true);
  });

  it('returns 500 on sync failure', async () => {
    mockBeadsManager.sync.mockResolvedValue([false, 'Sync failed: merge conflict']);

    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/sync');

    expect(res.status).toBe(500);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('merge conflict');
  });
});

// =============================================================================
// Tests: POST /api/projects/:name/beads/dep/add - Add dependency
// =============================================================================

describe('POST /api/projects/:name/beads/dep/add', () => {
  it('adds a dependency between issues', async () => {
    mockBeadsManager.addDependency.mockResolvedValue({ error: null });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/dep/add', {
      issue_id: 'feat-2',
      depends_on: 'feat-1',
    });

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean }>(res);
    expect(body.success).toBe(true);
    expect(mockBeadsManager.addDependency).toHaveBeenCalledWith('feat-2', 'feat-1');
  });

  it('returns 400 for invalid issue IDs', async () => {
    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/dep/add', {
      issue_id: 'invalid',
      depends_on: 'also-invalid',
    });

    expect(res.status).toBe(400);
  });
});

// =============================================================================
// Tests: POST /api/projects/:name/beads/comments/:issueId - Add comment
// =============================================================================

describe('POST /api/projects/:name/beads/comments/:issueId', () => {
  it('adds a comment to an issue', async () => {
    mockBeadsManager.addComment.mockResolvedValue({ error: null });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/comments/feat-1', {
      comment: 'This is a comment',
    });

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean }>(res);
    expect(body.success).toBe(true);
    expect(mockBeadsManager.addComment).toHaveBeenCalledWith('feat-1', 'This is a comment');
  });

  it('returns 400 for empty comment', async () => {
    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/comments/feat-1', {
      comment: '',
    });

    expect(res.status).toBe(400);
  });

  it('returns 404 when issue not found', async () => {
    mockBeadsManager.addComment.mockResolvedValue({
      error: 'Issue not found',
    });

    const res = await testRequest(app, 'POST', '/api/projects/my-project/beads/comments/feat-999', {
      comment: 'A comment',
    });

    expect(res.status).toBe(404);
  });
});
