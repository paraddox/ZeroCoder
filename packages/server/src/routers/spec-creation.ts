/**
 * Spec Creation Router
 * ====================
 *
 * WebSocket and REST endpoints for interactive spec creation with Claude.
 * TypeScript port of server/routers/spec_creation.py
 */

import { Hono } from 'hono';
import { HTTPException } from 'hono/http-exception';
import type { WSContext } from 'hono/ws';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { z } from 'zod';
import type { FileAttachment, ImageMimeType, TextMimeType } from '@zerocoder/shared';

import {
  createSession,
  getSession,
  listSessions,
  removeSession,
  cleanupAllSessions,
} from '../services/spec-chat-session.js';

import { getProjectPath, validateProjectName } from '../db/crud.js';

// =============================================================================
// Schemas
// =============================================================================

// WebSocket message schemas
const WSClientMessageSchema = z.discriminatedUnion('type', [
  z.object({ type: z.literal('ping') }),
  z.object({ type: z.literal('start') }),
  z.object({
    type: z.literal('message'),
    content: z.string(),
    attachments: z.array(z.unknown()).optional(),
  }),
  z.object({
    type: z.literal('answer'),
    answers: z.record(z.string(), z.unknown()),
    tool_id: z.string(),
  }),
]);

// =============================================================================
// Router Setup
// =============================================================================

const specCreationRouter = new Hono();

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
// REST Endpoints
// =============================================================================

// GET /api/spec/sessions - List all active spec creation sessions
specCreationRouter.get('/sessions', (c) => {
  const sessions = listSessions();
  return c.json(sessions);
});

// GET /api/spec/sessions/:project_name - Get status of a spec creation session
specCreationRouter.get('/sessions/:project_name', (c) => {
  const projectName = validateProjectNameParam(c.req.param('project_name'));

  const session = getSession(projectName);
  if (!session) {
    throw new HTTPException(404, { message: 'No active session for this project' });
  }

  return c.json({
    project_name: projectName,
    is_active: true,
    is_complete: session.isComplete(),
    message_count: session.getMessages().length,
  });
});

// DELETE /api/spec/sessions/:project_name - Cancel and remove a session
specCreationRouter.delete('/sessions/:project_name', async (c) => {
  const projectName = validateProjectNameParam(c.req.param('project_name'));

  const session = getSession(projectName);
  if (!session) {
    throw new HTTPException(404, { message: 'No active session for this project' });
  }

  await removeSession(projectName);
  return c.json({ success: true, message: 'Session cancelled' });
});

// GET /api/spec/status/:project_name - Get spec file status from disk
specCreationRouter.get('/status/:project_name', (c) => {
  const projectName = validateProjectNameParam(c.req.param('project_name'));

  const projectDir = getProjectPath(projectName);
  if (!projectDir) {
    throw new HTTPException(404, { message: 'Project not found in registry' });
  }

  if (!existsSync(projectDir)) {
    throw new HTTPException(404, { message: 'Project directory not found' });
  }

  const statusFile = join(projectDir, 'prompts', '.spec_status.json');

  if (!existsSync(statusFile)) {
    return c.json({
      exists: false,
      status: 'not_started',
      feature_count: null,
      timestamp: null,
      files_written: [],
    });
  }

  try {
    const data = JSON.parse(readFileSync(statusFile, 'utf-8')) as {
      status?: string;
      feature_count?: number;
      timestamp?: string;
      files_written?: string[];
    };
    return c.json({
      exists: true,
      status: data.status || 'unknown',
      feature_count: data.feature_count ?? null,
      timestamp: data.timestamp ?? null,
      files_written: data.files_written || [],
    });
  } catch (e) {
    console.warn(`[SpecCreation] Invalid JSON in spec status file: ${e}`);
    return c.json({
      exists: true,
      status: 'error',
      feature_count: null,
      timestamp: null,
      files_written: [],
    });
  }
});

// =============================================================================
// WebSocket Handler
// =============================================================================

/**
 * Handle WebSocket connections for spec creation chat.
 * This is used by the Hono WS middleware.
 *
 * Note: This handler expects to be called from a Hono WS route handler
 * where the WSContext has the socket methods available.
 */
export async function handleSpecWebSocket(
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

  console.log(`[SpecWebSocket] Connection opened for ${projectName}`);

  let session = getSession(projectName);

  // Handle incoming messages - using Hono's WSContext methods
  // The ws object in Hono has send/close methods and we use the subscribe pattern

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
        // Create and start a new session
        session = await createSession(projectName, projectDir);

        let specCompleteReceived = false;
        let specPath: string | null = null;

        // Stream the initial greeting
        for await (const chunk of session.start()) {
          // Track spec_complete but don't send complete yet
          if (chunk.type === 'spec_complete') {
            specCompleteReceived = true;
            specPath = chunk.path || null;
            ws.send(JSON.stringify(chunk));
            continue;
          }

          // When response_done arrives, send complete if spec was done
          if (chunk.type === 'response_done') {
            ws.send(JSON.stringify(chunk));
            if (specCompleteReceived) {
              ws.send(JSON.stringify({ type: 'complete', path: specPath }));
            }
            continue;
          }

          ws.send(JSON.stringify(chunk));
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

        // Parse attachments if present
        const attachments: FileAttachment[] = [];
        const rawAttachments = message.attachments || [];
        if (rawAttachments.length > 0) {
          for (const rawAtt of rawAttachments) {
            try {
              const att = rawAtt as {
                isText?: boolean;
                textContent?: string;
                filename?: string;
                mimeType?: string;
                base64Data?: string;
                id?: string;
                previewUrl?: string;
                size?: number;
              };

              const id = att.id || crypto.randomUUID();
              const filename = att.filename || 'unknown';
              const size = att.size || 0;

              if (att.isText || att.textContent !== undefined) {
                attachments.push({
                  id,
                  filename,
                  mimeType: (att.mimeType as TextMimeType) || 'text/plain',
                  textContent: att.textContent || '',
                  size,
                  isText: true,
                });
              } else {
                attachments.push({
                  id,
                  filename,
                  mimeType: (att.mimeType as ImageMimeType) || 'image/png',
                  base64Data: att.base64Data || '',
                  previewUrl: att.previewUrl || '',
                  size,
                  isText: false,
                });
              }
            } catch (e) {
              console.warn(`[SpecWebSocket] Invalid attachment data: ${e}`);
              ws.send(JSON.stringify({
                type: 'error',
                content: `Invalid attachment: ${e}`,
              }));
              return;
            }
          }
        }

        // Allow empty content if attachments are present
        if (!userContent && attachments.length === 0) {
          ws.send(JSON.stringify({
            type: 'error',
            content: 'Empty message',
          }));
          return;
        }

        let specCompleteReceived = false;
        let specPath: string | null = null;

        // Stream Claude's response
        for await (const chunk of session.sendMessage(userContent, attachments)) {
          // Track spec_complete but don't send complete yet
          if (chunk.type === 'spec_complete') {
            specCompleteReceived = true;
            specPath = chunk.path || null;
            ws.send(JSON.stringify(chunk));
            continue;
          }

          // When response_done arrives, send complete if spec was done
          if (chunk.type === 'response_done') {
            ws.send(JSON.stringify(chunk));
            if (specCompleteReceived) {
              ws.send(JSON.stringify({ type: 'complete', path: specPath }));
            }
            continue;
          }

          ws.send(JSON.stringify(chunk));
        }
        break;
      }

      case 'answer': {
        // User answered a structured question
        if (!session) {
          session = getSession(projectName);
          if (!session) {
            ws.send(JSON.stringify({
              type: 'error',
              content: 'No active session',
            }));
            return;
          }
        }

        // Format the answers as a natural response
        const answers = message.answers;
        let userResponse: string;
        if (typeof answers === 'object' && answers !== null) {
          // Convert structured answers to a message
          const responseParts: string[] = [];
          for (const [, answerValue] of Object.entries(answers)) {
            if (Array.isArray(answerValue)) {
              responseParts.push(answerValue.join(', '));
            } else {
              responseParts.push(String(answerValue));
            }
          }
          userResponse = responseParts.length > 0 ? responseParts.join('; ') : 'OK';
        } else {
          userResponse = String(answers);
        }

        let specCompleteReceived = false;
        let specPath: string | null = null;

        // Stream Claude's response
        for await (const chunk of session.sendMessage(userResponse)) {
          // Track spec_complete but don't send complete yet
          if (chunk.type === 'spec_complete') {
            specCompleteReceived = true;
            specPath = chunk.path || null;
            ws.send(JSON.stringify(chunk));
            continue;
          }

          // When response_done arrives, send complete if spec was done
          if (chunk.type === 'response_done') {
            ws.send(JSON.stringify(chunk));
            if (specCompleteReceived) {
              ws.send(JSON.stringify({ type: 'complete', path: specPath }));
            }
            continue;
          }

          ws.send(JSON.stringify(chunk));
        }
        break;
      }

      default:
        ws.send(JSON.stringify({
          type: 'error',
          content: `Unknown message type`,
        }));
    }
  };

  // For Hono WS, we need to return a handler or use the socket directly
  // The WSContext in Hono typically wraps the underlying WebSocket
  // We'll use the socket property if available, otherwise assume the caller
  // will handle message routing

  // Store reference for potential cleanup
  (ws as unknown as { _specMessageHandler?: (data: unknown) => void })._specMessageHandler = messageHandler;

  console.log(`[SpecWebSocket] Handler registered for ${projectName}`);

  // Note: The actual WebSocket event binding should be done by the caller
  // using ws.on('message', ...) or similar, depending on the WS library being used
}

export { specCreationRouter };
export { cleanupAllSessions as cleanupSpecSessions };
