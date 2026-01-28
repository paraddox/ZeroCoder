/**
 * Assistant Database
 * ==================
 *
 * Drizzle ORM functions for persisting assistant conversations.
 * Each project has its own assistant.db file in the project directory.
 *
 * TypeScript port of server/services/assistant_database.py
 */

import Database from 'better-sqlite3';
import { join } from 'node:path';

// =============================================================================
// Types
// =============================================================================

export interface Conversation {
  id: number;
  projectName: string;
  title: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface ConversationMessage {
  id: number;
  conversationId: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
}

export interface ConversationSummary {
  id: number;
  project_name: string;
  title: string | null;
  created_at: string | null;
  updated_at: string | null;
  message_count: number;
}

export interface ConversationDetail {
  id: number;
  project_name: string;
  title: string | null;
  created_at: string | null;
  updated_at: string | null;
  messages: ConversationMessageModel[];
}

export interface ConversationMessageModel {
  id: number;
  role: string;
  content: string;
  timestamp: string | null;
}

// =============================================================================
// Database Setup
// =============================================================================

function getDbPath(projectDir: string): string {
  return join(projectDir, 'assistant.db');
}

function getDb(projectDir: string): Database.Database {
  const dbPath = getDbPath(projectDir);
  const db = new Database(dbPath);

  // Create tables if they don't exist
  db.exec(`
    CREATE TABLE IF NOT EXISTS conversations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_name TEXT NOT NULL,
      title TEXT,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS conversation_messages (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      conversation_id INTEGER NOT NULL,
      role TEXT NOT NULL,
      content TEXT NOT NULL,
      timestamp TEXT NOT NULL DEFAULT (datetime('now')),
      FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_conversations_project ON conversations(project_name);
    CREATE INDEX IF NOT EXISTS idx_messages_conversation ON conversation_messages(conversation_id);
  `);

  return db;
}

// =============================================================================
// Conversation Operations
// =============================================================================

/**
 * Create a new conversation for a project.
 */
export function createConversation(projectDir: string, projectName: string, title?: string): Conversation {
  const db = getDb(projectDir);

  try {
    const stmt = db.prepare(`
      INSERT INTO conversations (project_name, title, created_at, updated_at)
      VALUES (?, ?, datetime('now'), datetime('now'))
    `);

    const result = stmt.run(projectName, title ?? null);
    const conversationId = Number(result.lastInsertRowid);

    console.log(`[AssistantDatabase] Created conversation ${conversationId} for project ${projectName}`);

    return {
      id: conversationId,
      projectName,
      title: title ?? null,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
  } finally {
    db.close();
  }
}

/**
 * Get all conversations for a project with message counts.
 */
export function getConversations(projectDir: string, projectName: string): ConversationSummary[] {
  const db = getDb(projectDir);

  try {
    const stmt = db.prepare(`
      SELECT
        c.id,
        c.project_name,
        c.title,
        c.created_at,
        c.updated_at,
        COUNT(m.id) as message_count
      FROM conversations c
      LEFT JOIN conversation_messages m ON m.conversation_id = c.id
      WHERE c.project_name = ?
      GROUP BY c.id
      ORDER BY c.updated_at DESC
    `);

    const rows = stmt.all(projectName) as Array<{
      id: number;
      project_name: string;
      title: string | null;
      created_at: string;
      updated_at: string;
      message_count: number;
    }>;

    return rows.map(row => ({
      id: row.id,
      project_name: row.project_name,
      title: row.title,
      created_at: row.created_at,
      updated_at: row.updated_at,
      message_count: row.message_count,
    }));
  } finally {
    db.close();
  }
}

/**
 * List all conversations across all projects in the database (for testing).
 */
export function listConversations(projectDir: string): ConversationSummary[] {
  const db = getDb(projectDir);

  try {
    const stmt = db.prepare(`
      SELECT
        c.id,
        c.project_name,
        c.title,
        c.created_at,
        c.updated_at,
        COUNT(m.id) as message_count
      FROM conversations c
      LEFT JOIN conversation_messages m ON m.conversation_id = c.id
      GROUP BY c.id
      ORDER BY c.updated_at DESC
    `);

    const rows = stmt.all() as Array<{
      id: number;
      project_name: string;
      title: string | null;
      created_at: string;
      updated_at: string;
      message_count: number;
    }>;

    return rows.map(row => ({
      id: row.id,
      project_name: row.project_name,
      title: row.title,
      created_at: row.created_at,
      updated_at: row.updated_at,
      message_count: row.message_count,
    }));
  } finally {
    db.close();
  }
}

/**
 * Get a conversation with all its messages.
 */
export function getConversation(projectDir: string, conversationId: number): ConversationDetail | null {
  const db = getDb(projectDir);

  try {
    // Get conversation
    const convStmt = db.prepare(`
      SELECT id, project_name, title, created_at, updated_at
      FROM conversations
      WHERE id = ?
    `);

    const conversation = convStmt.get(conversationId) as {
      id: number;
      project_name: string;
      title: string | null;
      created_at: string;
      updated_at: string;
    } | undefined;

    if (!conversation) {
      return null;
    }

    // Get messages
    const msgStmt = db.prepare(`
      SELECT id, role, content, timestamp
      FROM conversation_messages
      WHERE conversation_id = ?
      ORDER BY timestamp ASC
    `);

    const messages = msgStmt.all(conversationId) as Array<{
      id: number;
      role: string;
      content: string;
      timestamp: string;
    }>;

    return {
      id: conversation.id,
      project_name: conversation.project_name,
      title: conversation.title,
      created_at: conversation.created_at,
      updated_at: conversation.updated_at,
      messages: messages.map(m => ({
        id: m.id,
        role: m.role,
        content: m.content,
        timestamp: m.timestamp,
      })),
    };
  } finally {
    db.close();
  }
}

/**
 * Delete a conversation and all its messages.
 */
export function deleteConversation(projectDir: string, conversationId: number): boolean {
  const db = getDb(projectDir);

  try {
    const stmt = db.prepare('DELETE FROM conversations WHERE id = ?');
    const result = stmt.run(conversationId);

    console.log(`[AssistantDatabase] Deleted conversation ${conversationId}`);
    return result.changes > 0;
  } finally {
    db.close();
  }
}

// =============================================================================
// Message Operations
// =============================================================================

/**
 * Add a message to a conversation.
 */
export function addMessage(
  projectDir: string,
  conversationId: number,
  role: 'user' | 'assistant' | 'system',
  content: string
): ConversationMessageModel | null {
  const db = getDb(projectDir);

  try {
    // Check if conversation exists
    const convStmt = db.prepare('SELECT id, title FROM conversations WHERE id = ?');
    const conversation = convStmt.get(conversationId) as { id: number; title: string | null } | undefined;

    if (!conversation) {
      return null;
    }

    // Insert message
    const msgStmt = db.prepare(`
      INSERT INTO conversation_messages (conversation_id, role, content, timestamp)
      VALUES (?, ?, ?, datetime('now'))
    `);

    const result = msgStmt.run(conversationId, role, content);
    const messageId = Number(result.lastInsertRowid);

    // Update conversation's updated_at timestamp
    const updateStmt = db.prepare(`
      UPDATE conversations
      SET updated_at = datetime('now')
      WHERE id = ?
    `);
    updateStmt.run(conversationId);

    // Auto-generate title from first user message if not set
    if (!conversation.title && role === 'user') {
      const title = content.slice(0, 50) + (content.length > 50 ? '...' : '');
      const titleStmt = db.prepare('UPDATE conversations SET title = ? WHERE id = ?');
      titleStmt.run(title, conversationId);
    }

    console.log(`[AssistantDatabase] Added ${role} message to conversation ${conversationId}`);

    return {
      id: messageId,
      role,
      content,
      timestamp: new Date().toISOString(),
    };
  } finally {
    db.close();
  }
}

/**
 * Get all messages for a conversation.
 */
export function getMessages(projectDir: string, conversationId: number): ConversationMessageModel[] {
  const db = getDb(projectDir);

  try {
    const stmt = db.prepare(`
      SELECT id, role, content, timestamp
      FROM conversation_messages
      WHERE conversation_id = ?
      ORDER BY timestamp ASC
    `);

    const rows = stmt.all(conversationId) as Array<{
      id: number;
      role: string;
      content: string;
      timestamp: string;
    }>;

    return rows.map(row => ({
      id: row.id,
      role: row.role,
      content: row.content,
      timestamp: row.timestamp,
    }));
  } finally {
    db.close();
  }
}
