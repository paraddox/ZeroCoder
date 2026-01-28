/**
 * Assistant Chat Router
 * =====================
 *
 * WebSocket and REST endpoints for the read-only project assistant.
 * TypeScript port of server/routers/assistant_chat.py
 */

import { Hono } from 'hono';
import { HTTPException } from 'hono/http-exception';
import type { WSContext } from 'hono/ws';
import { existsSync } from 'node:fs';
import { z } from 'zod';

import {
  createSession,
  getSession,
  listSessions,
  removeSession,
  cleanupAllSessions,
} from '../services/assistant-chat-session.js';

import {
  createConversation,
  getConversation,
  getConversations,
  deleteConversation,
} from '../services/assistant-database.js';

import { getProjectPath, validateProjectName } from '../db/crud.js';

// =============================================================================
// Schemas
// =============================================================================

// WebSocket message schemas
const WSClientMessageSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('ping') }),
  z.object({
    type: z.literal('start'),
    conversation_id: z.number().optional(),
  }),
  z.object({
    type: z.literal('message'),
    content: z.string(),
  }),
]);

// =============================================================================
// Router Setup
// =============================================================================

const assistantRouter = new Hono();

// =============================================================================
// Validation Helpers
// =============================================================================

function validateProjectNameParam(name: string): string {
  const validation = validateProjectName(name);
  if (!validation.valid) {
    throw new HTTPException(400, { message: validation.error });
  }
  return name;
}

// =============================================================================
// REST Endpoints - Conversation Management
// =============================================================================

// GET /api/assistant/conversations/:project_name - List all conversations for a project
assistantRouter.get('/conversations/:project_name', (c) => {
  const projectName = validateProjectNameParam(c.req.param('project_name'));

  const projectDir = getProjectPath(projectName);
  if (!projectDir) {
    throw new HTTPException(404, { message: 'Project not found' });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  const conversations = getConversations(projectDir, projectName);
  return c.json(conversations);
});

// GET /api/assistant/conversations/:project_name/:conversation_id - Get a specific conversation
assistantRouter.get('/conversations/:project_name/:conversation_id', (c) => {
  const projectName = validateProjectNameParam(c.req.param('project_name'));
  const conversationId = parseInt(c.req.param('conversation_id'), 10);

  if (isNaN(conversationId)) {
    throw new HTTPException(400, { message: 'Invalid conversation ID' });
  }

  const projectDir = getProjectPath(projectName);
  if (!projectDir) {
    throw new HTTPException(404, { message: 'Project not found' });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  const conversation = getConversation(projectDir, conversationId);
  if (!conversation) {
    throw new HTTPException(404, { message: 'Conversation not found' });
  }

  return c.json(conversation);
});

// POST /api/assistant/conversations/:project_name - Create a new conversation
assistantRouter.post('/conversations/:project_name', (c) => {
  const projectName = validateProjectNameParam(c.req.param('project_name'));

  const projectDir = getProjectPath(projectName);
  if (!projectDir) {
    throw new HTTPException(404, { message: 'Project not found' });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  const conversation = createConversation(projectDir, projectName);
  return c.json({
    id: conversation.id,
    project_name: conversation.projectName,
    title: conversation.title,
    created_at: conversation.createdAt,
    updated_at: conversation.updatedAt,
    message_count: 0,
  });
});

// DELETE /api/assistant/conversations/:project_name/:conversation_id - Delete a conversation
assistantRouter.delete('/conversations/:project_name/:conversation_id', (c) => {
  const projectName = validateProjectNameParam(c.req.param('project_name'));
  const conversationId = parseInt(c.req.param('conversation_id'), 10);

  if (isNaN(conversationId)) {
    throw new HTTPException(400, { message: 'Invalid conversation ID' });
  }

  const projectDir = getProjectPath(projectName);
  if (!projectDir) {
    throw new HTTPException(404, { message: 'Project not found' });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  const success = deleteConversation(projectDir, conversationId);
  if (!success) {
    throw new HTTPException(404, { message: 'Conversation not found' });
  }

  return c.json({ success: true, message: 'Conversation deleted' });
});

// =============================================================================
// REST Endpoints - Session Management
// =============================================================================

// GET /api/assistant/sessions - List all active assistant sessions
assistantRouter.get('/sessions', (c) => {
  const sessions = listSessions();
  return c.json(sessions);
});

// GET /api/assistant/sessions/:project_name - Get information about an active session
assistantRouter.get('/sessions/:project_name', (c) => {
  const projectName = validateProjectNameParam(c.req.param('project_name'));

  const session = getSession(projectName);
  if (!session) {
    throw new HTTPException(404, { message: 'No active session for this project' });
  }

  return c.json({
    project_name: projectName,
    conversation_id: session.getConversationId(),
    is_active: true,
  });
});

// DELETE /api/assistant/sessions/:project_name - Close an active session
assistantRouter.delete('/sessions/:project_name', async (c) => {
  const projectName = validateProjectNameParam(c.req.param('project_name'));

  const session = getSession(projectName);
  if (!session) {
    throw new HTTPException(404, { message: 'No active session for this project' });
  }

  await removeSession(projectName);
  return c.json({ success: true, message: 'Session closed' });
});

// =============================================================================
// WebSocket Handler
// =============================================================================

/**
 * Handle WebSocket connections for assistant chat.
 * This is used by the Hono WS middleware.
 *
 * Message protocol:
 *
 * Client -> Server:
 * - {"type": "start", "conversation_id": number | null} - Start/resume session
 * - {"type": "message", "content": "..."} - Send user message
 * - {"type": "ping"} - Keep-alive ping
 *
 * Server -> Client:
 * - {"type": "conversation_created", "conversation_id": number} - New conversation created
 * - {"type": "text", "content": "..."} - Text chunk from Claude
 * - {"type": "tool_call", "tool": "...", "input": {...}} - Tool being called
 * - {"type": "issue_created", "id": "...", "title": "..."} - Issue was created
 * - {"type": "response_done"} - Response complete
 * - {"type": "error", "content": "..."} - Error message
 * - {"type": "pong"} - Keep-alive pong
 */
export async function handleAssistantWebSocket(
  ws: WSContext,
  projectName: string
): Promise<void> {
  // Validate project name
  const validation = validateProjectName(projectName);
  if (!validation.valid) {
    ws.close(4000, 'Invalid project name');
    return;
  }

  // Look up project directory from registry
  const projectDir = getProjectPath(projectName);
  if (!projectDir) {
    ws.close(4004, 'Project not found in registry');
    return;
  }

  if (!existsSync(projectDir)) {
    ws.close(4004, 'Project directory not found');
    return;
  }

  console.log(`[AssistantWebSocket] Connection opened for ${projectName}`);

  let session = getSession(projectName);

  // Store message handler reference for cleanup
  const messageHandler = async (data: unknown) => {
    if (typeof data !== 'string') {
      ws.send(JSON.stringify({
        type: 'error',
        content: 'Invalid message format: expected string',
      }));
      return;
    }

    let message: z.infer<typeof WSClientMessageSchema>;
    try {
      const parsed = JSON.parse(data);
      const result = WSClientMessageSchema.safeParse(parsed);
      if (!result.success) {
        ws.send(JSON.stringify({
          type: 'error',
          content: `Invalid message format: ${result.error.message}`,
        }));
        return;
      }
      message = result.data;
    } catch {
      ws.send(JSON.stringify({
        type: 'error',
        content: 'Invalid JSON',
      }));
      return;
    }

    // Handle different message types
    switch (message.type) {
      case 'ping':
        ws.send(JSON.stringify({ type: 'pong' }));
        break;

      case 'start': {
        // Get optional conversation_id to resume
        const conversationId = message.conversation_id;

        try {
          // Create a new session
          session = await createSession(projectName, projectDir, conversationId);

          // Stream the initial greeting
          for await (const chunk of session.start()) {
            ws.send(JSON.stringify(chunk));
          }
        } catch (e) {
          console.error(`[AssistantWebSocket] Error starting session for ${projectName}:`, e);
          ws.send(JSON.stringify({
            type: 'error',
            content: `Failed to start session: ${e instanceof Error ? e.message : String(e)}`,
          }));
        }
        break;
      }

      case 'message': {
        // User sent a message
        if (!session) {
          session = getSession(projectName);
          if (!session) {
            ws.send(JSON.stringify({
              type: 'error',
              content: 'No active session. Send \'start\' first.',
            }));
            return;
          }
        }

        const userContent = message.content.trim();
        if (!userContent) {
          ws.send(JSON.stringify({
            type: 'error',
            content: 'Empty message',
          }));
          return;
        }

        // Stream Claude's response
        for await (const chunk of session.sendMessage(userContent)) {
          ws.send(JSON.stringify(chunk));
        }
        break;
      }

      default:
        ws.send(JSON.stringify({
          type: 'error',
          content: 'Unknown message type',
        }));
    }
  };

  // Store reference for potential cleanup
  (ws as unknown as { _assistantMessageHandler?: (data: unknown) => void })._assistantMessageHandler = messageHandler;

  console.log(`[AssistantWebSocket] Handler registered for ${projectName}`);
}

export { assistantRouter };
export { cleanupAllSessions as cleanupAssistantSessions };
