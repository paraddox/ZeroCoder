/**
 * Assistant Router Tests
 * ======================
 *
 * Tests for the assistant chat API endpoints.
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

vi.mock('node:fs', () => ({
  existsSync: (...args: unknown[]) => mockExistsSync(...args),
}));

// Mock the assistant-chat-session module
const mockCreateSession = vi.fn();
const mockGetSession = vi.fn();
const mockListSessions = vi.fn();
const mockRemoveSession = vi.fn();

vi.mock('../../services/assistant-chat-session.js', () => ({
  AssistantChatSession: vi.fn(),
  createSession: mockCreateSession,
  getSession: mockGetSession,
  listSessions: mockListSessions,
  removeSession: mockRemoveSession,
  cleanupAllSessions: vi.fn(),
}));

// Mock the assistant-database module
const mockCreateConversation = vi.fn();
const mockGetConversation = vi.fn();
const mockGetConversations = vi.fn();
const mockDeleteConversation = vi.fn();

vi.mock('../../services/assistant-database.js', () => ({
  createConversation: mockCreateConversation,
  getConversation: mockGetConversation,
  getConversations: mockGetConversations,
  deleteConversation: mockDeleteConversation,
  addMessage: vi.fn(),
  getMessages: vi.fn(),
  listConversations: vi.fn(),
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
  mockListSessions.mockReturnValue([]);
  mockGetProjectPath.mockReturnValue('/test/projects/test-project');
  mockGetSession.mockReturnValue(null);
  mockGetConversations.mockReturnValue([]);
  mockGetConversation.mockReturnValue(null);

  // Dynamically import router after mocks are set up
  const { assistantRouter } = await import('../assistant.js');

  app = new Hono();
  app.onError((err, c) => {
    const status = 'status' in err ? (err.status as number) : 500;
    return c.json({ error: err.message, status }, status as 500);
  });
  app.route('/api/assistant', assistantRouter);
});

// =============================================================================
// Tests: GET /api/assistant/conversations/:project_name - List conversations
// =============================================================================

describe('GET /api/assistant/conversations/:project_name', () => {
  it('returns empty array when no conversations exist', async () => {
    mockGetConversations.mockReturnValue([]);

    const res = await testRequest(app, 'GET', '/api/assistant/conversations/test-project');

    expect(res.status).toBe(200);
    const body = await parseResponse<unknown[]>(res);
    expect(body).toEqual([]);
  });

  it('returns list of conversations for project', async () => {
    mockGetConversations.mockReturnValue([
      {
        id: 1,
        project_name: 'test-project',
        title: 'Test Conversation',
        created_at: '2024-01-01T00:00:00Z',
        updated_at: '2024-01-01T00:01:00Z',
        message_count: 5,
      },
    ]);

    const res = await testRequest(app, 'GET', '/api/assistant/conversations/test-project');

    expect(res.status).toBe(200);
    const body = await parseResponse<Array<{
      id: number;
      project_name: string;
      title: string;
      message_count: number;
    }>>(res);
    expect(body).toHaveLength(1);
    expect(body[0]!.id).toBe(1);
    expect(body[0]!.title).toBe('Test Conversation');
    expect(body[0]!.message_count).toBe(5);
  });

  it('returns 404 when project not found', async () => {
    mockGetProjectPath.mockReturnValue(null);

    const res = await testRequest(app, 'GET', '/api/assistant/conversations/nonexistent');

    expect(res.status).toBe(404);
  });

  it('returns 404 when project directory does not exist', async () => {
    mockExistsSync.mockReturnValue(false);

    const res = await testRequest(app, 'GET', '/api/assistant/conversations/test-project');

    expect(res.status).toBe(404);
  });

  it('returns 400 for invalid project name', async () => {
    const res = await testRequest(app, 'GET', '/api/assistant/conversations/invalid%20name');

    expect(res.status).toBe(400);
  });
});

// =============================================================================
// Tests: GET /api/assistant/conversations/:project_name/:conversation_id
// =============================================================================

describe('GET /api/assistant/conversations/:project_name/:conversation_id', () => {
  it('returns conversation with messages', async () => {
    mockGetConversation.mockReturnValue({
      id: 1,
      project_name: 'test-project',
      title: 'Test Conversation',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:01:00Z',
      messages: [
        { id: 1, role: 'user', content: 'Hello', timestamp: '2024-01-01T00:00:00Z' },
        { id: 2, role: 'assistant', content: 'Hi!', timestamp: '2024-01-01T00:00:01Z' },
      ],
    });

    const res = await testRequest(app, 'GET', '/api/assistant/conversations/test-project/1');

    expect(res.status).toBe(200);
    const body = await parseResponse<{
      id: number;
      project_name: string;
      title: string;
      messages: Array<{ id: number; role: string; content: string }>;
    }>(res);
    expect(body.id).toBe(1);
    expect(body.messages).toHaveLength(2);
    expect(body.messages[0]!.role).toBe('user');
    expect(body.messages[1]!.role).toBe('assistant');
  });

  it('returns 404 when conversation not found', async () => {
    mockGetConversation.mockReturnValue(null);

    const res = await testRequest(app, 'GET', '/api/assistant/conversations/test-project/999');

    expect(res.status).toBe(404);
  });

  it('returns 400 for invalid conversation ID', async () => {
    const res = await testRequest(app, 'GET', '/api/assistant/conversations/test-project/invalid');

    expect(res.status).toBe(400);
  });
});

// =============================================================================
// Tests: POST /api/assistant/conversations/:project_name
// =============================================================================

describe('POST /api/assistant/conversations/:project_name', () => {
  it('creates a new conversation', async () => {
    mockCreateConversation.mockReturnValue({
      id: 1,
      projectName: 'test-project',
      title: null,
      createdAt: '2024-01-01T00:00:00Z',
      updatedAt: '2024-01-01T00:00:00Z',
    });

    const res = await testRequest(app, 'POST', '/api/assistant/conversations/test-project');

    expect(res.status).toBe(200);
    const body = await parseResponse<{
      id: number;
      project_name: string;
      title: null;
      message_count: number;
    }>(res);
    expect(body.id).toBe(1);
    expect(body.project_name).toBe('test-project');
    expect(body.message_count).toBe(0);
    expect(mockCreateConversation).toHaveBeenCalledWith('/test/projects/test-project', 'test-project');
  });

  it('returns 404 when project not found', async () => {
    mockGetProjectPath.mockReturnValue(null);

    const res = await testRequest(app, 'POST', '/api/assistant/conversations/nonexistent');

    expect(res.status).toBe(404);
  });
});

// =============================================================================
// Tests: DELETE /api/assistant/conversations/:project_name/:conversation_id
// =============================================================================

describe('DELETE /api/assistant/conversations/:project_name/:conversation_id', () => {
  it('deletes a conversation', async () => {
    mockDeleteConversation.mockReturnValue(true);

    const res = await testRequest(app, 'DELETE', '/api/assistant/conversations/test-project/1');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; message: string }>(res);
    expect(body.success).toBe(true);
    expect(body.message).toContain('deleted');
    expect(mockDeleteConversation).toHaveBeenCalledWith('/test/projects/test-project', 1);
  });

  it('returns 404 when conversation not found', async () => {
    mockDeleteConversation.mockReturnValue(false);

    const res = await testRequest(app, 'DELETE', '/api/assistant/conversations/test-project/999');

    expect(res.status).toBe(404);
  });
});

// =============================================================================
// Tests: GET /api/assistant/sessions - List sessions
// =============================================================================

describe('GET /api/assistant/sessions', () => {
  it('returns empty array when no sessions exist', async () => {
    mockListSessions.mockReturnValue([]);

    const res = await testRequest(app, 'GET', '/api/assistant/sessions');

    expect(res.status).toBe(200);
    const body = await parseResponse<string[]>(res);
    expect(body).toEqual([]);
  });

  it('returns list of active session project names', async () => {
    mockListSessions.mockReturnValue(['project-1', 'project-2']);

    const res = await testRequest(app, 'GET', '/api/assistant/sessions');

    expect(res.status).toBe(200);
    const body = await parseResponse<string[]>(res);
    expect(body).toEqual(['project-1', 'project-2']);
  });
});

// =============================================================================
// Tests: GET /api/assistant/sessions/:project_name - Get session info
// =============================================================================

describe('GET /api/assistant/sessions/:project_name', () => {
  it('returns session info for active session', async () => {
    const mockSession = {
      getConversationId: () => 1,
    };
    mockGetSession.mockReturnValue(mockSession);

    const res = await testRequest(app, 'GET', '/api/assistant/sessions/test-project');

    expect(res.status).toBe(200);
    const body = await parseResponse<{
      project_name: string;
      conversation_id: number;
      is_active: boolean;
    }>(res);
    expect(body.project_name).toBe('test-project');
    expect(body.conversation_id).toBe(1);
    expect(body.is_active).toBe(true);
  });

  it('returns 404 when session does not exist', async () => {
    mockGetSession.mockReturnValue(null);

    const res = await testRequest(app, 'GET', '/api/assistant/sessions/nonexistent');

    expect(res.status).toBe(404);
    const body = await parseResponse<{ error: string }>(res);
    expect(body.error).toContain('No active session');
  });

  it('returns 400 for invalid project name', async () => {
    const res = await testRequest(app, 'GET', '/api/assistant/sessions/invalid%20name');

    expect(res.status).toBe(400);
  });
});

// =============================================================================
// Tests: DELETE /api/assistant/sessions/:project_name - Close session
// =============================================================================

describe('DELETE /api/assistant/sessions/:project_name', () => {
  it('closes active session', async () => {
    const mockSession = {
      getConversationId: () => 1,
    };
    mockGetSession.mockReturnValue(mockSession);
    mockRemoveSession.mockResolvedValue(undefined);

    const res = await testRequest(app, 'DELETE', '/api/assistant/sessions/test-project');

    expect(res.status).toBe(200);
    const body = await parseResponse<{ success: boolean; message: string }>(res);
    expect(body.success).toBe(true);
    expect(body.message).toContain('Session closed');
    expect(mockRemoveSession).toHaveBeenCalledWith('test-project');
  });

  it('returns 404 when session does not exist', async () => {
    mockGetSession.mockReturnValue(null);

    const res = await testRequest(app, 'DELETE', '/api/assistant/sessions/nonexistent');

    expect(res.status).toBe(404);
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

    const res1 = await testRequest(app, 'GET', '/api/assistant/sessions');
    expect(await parseResponse<string[]>(res1)).toEqual([]);

    // Simulate session creation (would happen via WebSocket)
    const res2 = await testRequest(app, 'GET', '/api/assistant/sessions');
    expect(await parseResponse<string[]>(res2)).toEqual(['test-project']);
  });

  it('validates project names correctly', async () => {
    // Valid names
    const validRes = await testRequest(app, 'GET', '/api/assistant/sessions/valid-project-123');
    expect(validRes.status).not.toBe(400);

    // Invalid names with spaces
    const invalidRes = await testRequest(app, 'GET', '/api/assistant/sessions/invalid name');
    expect(invalidRes.status).toBe(400);
  });
});

// =============================================================================
// Tests: Conversation Management Integration
// =============================================================================

describe('Conversation Management', () => {
  it('creates and retrieves a conversation', async () => {
    // Create conversation
    mockCreateConversation.mockReturnValue({
      id: 1,
      projectName: 'test-project',
      title: null,
      createdAt: '2024-01-01T00:00:00Z',
      updatedAt: '2024-01-01T00:00:00Z',
    });

    const createRes = await testRequest(app, 'POST', '/api/assistant/conversations/test-project');
    expect(createRes.status).toBe(200);

    // Get conversation
    mockGetConversation.mockReturnValue({
      id: 1,
      project_name: 'test-project',
      title: 'Test',
      created_at: '2024-01-01T00:00:00Z',
      updated_at: '2024-01-01T00:00:00Z',
      messages: [],
    });

    const getRes = await testRequest(app, 'GET', '/api/assistant/conversations/test-project/1');
    expect(getRes.status).toBe(200);
  });

  it('lists conversations for a project', async () => {
    mockGetConversations.mockReturnValue([
      { id: 1, project_name: 'test-project', title: 'Conv 1', created_at: '2024-01-01T00:00:00Z', updated_at: '2024-01-01T00:01:00Z', message_count: 2 },
      { id: 2, project_name: 'test-project', title: 'Conv 2', created_at: '2024-01-02T00:00:00Z', updated_at: '2024-01-02T00:01:00Z', message_count: 5 },
    ]);

    const res = await testRequest(app, 'GET', '/api/assistant/conversations/test-project');

    expect(res.status).toBe(200);
    const body = await parseResponse<unknown[]>(res);
    expect(body).toHaveLength(2);
  });
});
