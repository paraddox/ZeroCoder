/**
 * Spec Creation Router Tests
 * ==========================
 *
 * Tests for the spec creation API endpoints.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { Hono } from 'hono';
import {
  testRequest,
  parseResponse,
} from './test-utils.js';

// =============================================================================
// Mock Setup
// =============================================================================

const mockExistsSync = vi.fn();
const mockReadFileSync = vi.fn();
const mockWriteFileSync = vi.fn();
const mockMkdirSync = vi.fn();
const mockUnlinkSync = vi.fn();

vi.mock('node:fs', () => ({
  existsSync: (...args: unknown[]) => mockExistsSync(...args),
  readFileSync: (...args: unknown[]) => mockReadFileSync(...args),
  writeFileSync: (...args: unknown[]) => mockWriteFileSync(...args),
  mkdirSync: (...args: unknown[]) => mockMkdirSync(...args),
  unlinkSync: (...args: unknown[]) => mockUnlinkSync(...args),
}));

// Mock the spec-chat-session module
const mockCreateSession = vi.fn();
const mockGetSession = vi.fn();
const mockListSessions = vi.fn();
const mockRemoveSession = vi.fn();

vi.mock('../../services/spec-chat-session.js', () => ({
  createSession: mockCreateSession,
  getSession: mockGetSession,
  listSessions: mockListSessions,
  removeSession: mockRemoveSession,
  cleanupAllSessions: vi.fn(),
}));

// Mock CRUD module
const mockGetProjectPath = vi.fn();
const mockValidateProjectName = vi.fn((name: string) => {
  if (!/^[a-zA-Z0-9_-]{1,50}$/.test(name)) {
    return { valid: false, error: 'Invalid project name' };
  }
  return { valid: true };
});

vi.mock('../../db/crud.js', () => ({
  getProjectPath: mockGetProjectPath,
  validateProjectName: mockValidateProjectName,
}));

// =============================================================================
// Test Setup
// =============================================================================

let app: Hono;

beforeEach(async () => {
  vi.clearAllMocks();

  // Reset default mock behaviors
  mockExistsSync.mockReturnValue(true);
  mockReadFileSync.mockReturnValue('{}');
  mockListSessions.mockReturnValue([]);
  mockGetProjectPath.mockReturnValue('/test/projects/test-project');
  mockGetSession.mockReturnValue(null);

  // Dynamically import router after mocks are set up
  const { specCreationRouter } = await import('../spec-creation.js');

  app = new Hono();
  app.onError((err, c) => {
    const status = 'status' in err ? (err.status as number) : 500;
    return c.json({ error: err.message, status }, status as 500);
  });
  app.route('/api/spec', specCreationRouter);
});

// =============================================================================
// Tests: GET /api/spec/sessions - List sessions
// =============================================================================

describe('GET /api/spec/sessions', () => {
  it('returns empty array when no sessions exist', async () => {
    mockListSessions.mockReturnValue([]);

    const res = await testRequest(app, 'GET', '/api/spec/sessions');

    expect(res.status).toBe(200);
    const body = await parseResponse<string[]>(res);
    expect(body).toEqual([]);
  });

  it('returns list of active session project names', async () => {
    mockListSessions.mockReturnValue(['project-1', 'project-2']);

    const res = await testRequest(app, 'GET', '/api/spec/sessions');

    expect(res.status).toBe(200);
    const body = await parseResponse<string[]>(res);
    expect(body).toEqual(['project-1', 'project-2']);
  });
});

// =============================================================================
// Tests: GET /api/spec/sessions/:project_name - Get session status
// =============================================================================

describe('GET /api/spec/sessions/:project_name', () => {
  it('returns session status for active session', async () => {
    const mockSession = {
      isComplete: () => false,
      getMessages: () => [
        { role: 'user', content: 'Hello', timestamp: '2024-01-01T00:00:00Z' },
        { role: 'assistant', content: 'Hi!', timestamp: '2024-01-01T00:00:01Z' },
      ],
    };
    mockGetSession.mockReturnValue(mockSession);

    const res = await testRequest(app, 'GET', '/api/spec/sessions/test-project');

    expect(res.status).toBe(200);
    const body = await parseResponse<{
      project_name: string;
      is_active: boolean;
      is_complete: boolean;
      message_count: number;
    }>(res);
    expect(body.project_name).toBe('test-project');
    expect(body.is_active).toBe(true);
    expect(body.is_complete).toBe(false);
    expect(body.message_count).toBe(2);
  });

  it('returns 404 when session does not exist', async () => {
    mockGetSession.mockReturnValue(null);

    const res = await testRequest(app, 'GET', '/api/spec/sessions/nonexistent');

    expect(res.status).toBe(404);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('No active session');
  });

  it('returns 400 for invalid project name', async () => {
    const res = await testRequest(app, 'GET', '/api/spec/sessions/invalid%20name');

    expect(res.status).toBe(400);
  });
});

// =============================================================================
// Tests: DELETE /api/spec/sessions/:project_name - Cancel session
// =============================================================================

describe('DELETE /api/spec/sessions/:project_name', () => {
  it('cancels active session', async () => {
    const mockSession = {
      isComplete: () => false,
      getMessages: () => [],
    };
    mockGetSession.mockReturnValue(mockSession);
    mockRemoveSession.mockResolvedValue(undefined);

    const res = await testRequest(app, 'DELETE', '/api/spec/sessions/test-project');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; message: string }>(res);
    expect(body.success).toBe(true);
    expect(body.message).toContain('Session cancelled');
    expect(mockRemoveSession).toHaveBeenCalledWith('test-project');
  });

  it('returns 404 when session does not exist', async () => {
    mockGetSession.mockReturnValue(null);

    const res = await testRequest(app, 'DELETE', '/api/spec/sessions/nonexistent');

    expect(res.status).toBe(404);
  });
});

// =============================================================================
// Tests: GET /api/spec/status/:project_name - Get spec file status
// =============================================================================

describe('GET /api/spec/status/:project_name', () => {
  it('returns not_started when status file does not exist', async () => {
    mockGetProjectPath.mockReturnValue('/test/projects/test-project');
    mockExistsSync.mockImplementation((path: string) => {
      if (path.includes('.spec_status.json')) return false;
      return true;
    });

    const res = await testRequest(app, 'GET', '/api/spec/status/test-project');

    expect(res.status).toBe(200);
    const body = await parseResponse<{
      exists: boolean;
      status: string;
      feature_count: null;
      timestamp: null;
      files_written: string[];
    }>(res);
    expect(body.exists).toBe(false);
    expect(body.status).toBe('not_started');
    expect(body.feature_count).toBeNull();
    expect(body.files_written).toEqual([]);
  });

  it('returns status from existing status file', async () => {
    mockGetProjectPath.mockReturnValue('/test/projects/test-project');
    mockExistsSync.mockReturnValue(true);
    mockReadFileSync.mockReturnValue(
      JSON.stringify({
        status: 'complete',
        feature_count: 5,
        timestamp: '2024-01-01T00:00:00Z',
        files_written: ['app_spec.txt', 'initializer_prompt.md'],
      })
    );

    const res = await testRequest(app, 'GET', '/api/spec/status/test-project');

    expect(res.status).toBe(200);
    const body = await parseResponse<{
      exists: boolean;
      status: string;
      feature_count: number;
      timestamp: string;
      files_written: string[];
    }>(res);
    expect(body.exists).toBe(true);
    expect(body.status).toBe('complete');
    expect(body.feature_count).toBe(5);
    expect(body.timestamp).toBe('2024-01-01T00:00:00Z');
    expect(body.files_written).toEqual(['app_spec.txt', 'initializer_prompt.md']);
  });

  it('returns error status for invalid JSON', async () => {
    mockGetProjectPath.mockReturnValue('/test/projects/test-project');
    mockExistsSync.mockReturnValue(true);
    mockReadFileSync.mockReturnValue('invalid json');

    const res = await testRequest(app, 'GET', '/api/spec/status/test-project');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ exists: boolean; status: string }>(res);
    expect(body.exists).toBe(true);
    expect(body.status).toBe('error');
  });

  it('returns 404 when project not found in registry', async () => {
    mockGetProjectPath.mockReturnValue(null);

    const res = await testRequest(app, 'GET', '/api/spec/status/nonexistent');

    expect(res.status).toBe(404);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('not found in registry');
  });

  it('returns 404 when project directory does not exist', async () => {
    mockGetProjectPath.mockReturnValue('/test/projects/test-project');
    mockExistsSync.mockReturnValue(false);

    const res = await testRequest(app, 'GET', '/api/spec/status/test-project');

    expect(res.status).toBe(404);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('Project directory not found');
  });
});

// =============================================================================
// Tests: Session Management Integration
// =============================================================================

describe('Session Management', () => {
  it('lists sessions after creating one', async () => {
    mockListSessions
      .mockReturnValueOnce([])
      .mockReturnValueOnce(['test-project']);

    const res1 = await testRequest(app, 'GET', '/api/spec/sessions');
    expect(await parseResponse<string[]>(res1)).toEqual([]);

    // Simulate session creation (would happen via WebSocket)
    const res2 = await testRequest(app, 'GET', '/api/spec/sessions');
    expect(await parseResponse<string[]>(res2)).toEqual(['test-project']);
  });

  it('validates project names correctly', async () => {
    // Valid names
    const validRes = await testRequest(app, 'GET', '/api/spec/sessions/valid-project-123');
    expect(validRes.status).not.toBe(400);

    // Invalid names with spaces
    const invalidRes = await testRequest(app, 'GET', '/api/spec/sessions/invalid name');
    expect(invalidRes.status).toBe(400);
  });
});
