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
import { eq, desc, asc } from 'drizzle-orm';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import {
  conversations,
  conversationMessages,
  type Conversation,
  type NewConversation,
  type NewConversationMessage,
} from './assistant-schema.js';

// =============================================================================
// Types
// =============================================================================

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

function getDb(projectDir: string) {
  const dbPath = getDbPath(projectDir);
  const sqlite = new Database(dbPath);

  // Create tables if they don't exist using Drizzle migrations
  sqlite.exec(`
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

  return drizzle(sqlite, {
    schema: { conversations, conversationMessages },
  });
}

// =============================================================================
// Conversation Operations
// =============================================================================

/**
 * Create a new conversation for a project.
 */
export function createConversation(
  projectDir: string,
  projectName: string,
  title?: string
): Conversation {
  const db = getDb(projectDir);

  const now = new Date().toISOString();
  const result = db
    .insert(conversations)
    .values({
      projectName,
      title: title ?? null,
      createdAt: now,
      updatedAt: now,
    } as NewConversation)
    .returning()
    .all();

  const conversation = result[0]!;
  console.log(
    `[AssistantDatabase] Created conversation ${conversation.id} for project ${projectName}`
  );

  return conversation;
}

/**
 * Get all conversations for a project with message counts.
 */
export function getConversations(
  projectDir: string,
  projectName: string
): ConversationSummary[] {
  const db = getDb(projectDir);

  // Get conversations with message counts using Drizzle
  const convs = db
    .select()
    .from(conversations)
    .where(eq(conversations.projectName, projectName))
    .orderBy(desc(conversations.updatedAt))
    .all();

  // Get message counts for each conversation
  const result: ConversationSummary[] = [];
  for (const conv of convs) {
    const messageCount = db
      .select({ count: conversationMessages.id })
      .from(conversationMessages)
      .where(eq(conversationMessages.conversationId, conv.id))
      .all().length;

    result.push({
      id: conv.id,
      project_name: conv.projectName,
      title: conv.title,
      created_at: conv.createdAt,
      updated_at: conv.updatedAt,
      message_count: messageCount,
    });
  }

  return result;
}

/**
 * List all conversations across all projects in the database (for testing).
 */
export function listConversations(projectDir: string): ConversationSummary[] {
  const db = getDb(projectDir);

  // Get all conversations with message counts using Drizzle
  const convs = db
    .select()
    .from(conversations)
    .orderBy(desc(conversations.updatedAt))
    .all();

  // Get message counts for each conversation
  const result: ConversationSummary[] = [];
  for (const conv of convs) {
    const messageCount = db
      .select({ count: conversationMessages.id })
      .from(conversationMessages)
      .where(eq(conversationMessages.conversationId, conv.id))
      .all().length;

    result.push({
      id: conv.id,
      project_name: conv.projectName,
      title: conv.title,
      created_at: conv.createdAt,
      updated_at: conv.updatedAt,
      message_count: messageCount,
    });
  }

  return result;
}

/**
 * Get a conversation with all its messages.
 */
export function getConversation(
  projectDir: string,
  conversationId: number
): ConversationDetail | null {
  const db = getDb(projectDir);

  // Get conversation using Drizzle
  const conversation = db
    .select()
    .from(conversations)
    .where(eq(conversations.id, conversationId))
    .get();

  if (!conversation) {
    return null;
  }

  // Get messages using Drizzle
  const messages = db
    .select()
    .from(conversationMessages)
    .where(eq(conversationMessages.conversationId, conversationId))
    .orderBy(asc(conversationMessages.timestamp))
    .all();

  return {
    id: conversation.id,
    project_name: conversation.projectName,
    title: conversation.title,
    created_at: conversation.createdAt,
    updated_at: conversation.updatedAt,
    messages: messages.map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      timestamp: m.timestamp,
    })),
  };
}

/**
 * Delete a conversation and all its messages.
 */
export function deleteConversation(
  projectDir: string,
  conversationId: number
): boolean {
  const db = getDb(projectDir);

  const result = db
    .delete(conversations)
    .where(eq(conversations.id, conversationId))
    .run();

  console.log(`[AssistantDatabase] Deleted conversation ${conversationId}`);
  return result.changes > 0;
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

  // Check if conversation exists
  const conversation = db
    .select()
    .from(conversations)
    .where(eq(conversations.id, conversationId))
    .get();

  if (!conversation) {
    return null;
  }

  const now = new Date().toISOString();

  // Insert message using Drizzle
  const result = db
    .insert(conversationMessages)
    .values({
      conversationId,
      role,
      content,
      timestamp: now,
    } as NewConversationMessage)
    .returning()
    .all();

  const message = result[0]!;

  // Update conversation's updated_at timestamp
  db.update(conversations)
    .set({ updatedAt: now })
    .where(eq(conversations.id, conversationId))
    .run();

  // Auto-generate title from first user message if not set
  if (!conversation.title && role === 'user') {
    const title = content.slice(0, 50) + (content.length > 50 ? '...' : '');
    db.update(conversations)
      .set({ title })
      .where(eq(conversations.id, conversationId))
      .run();
  }

  console.log(
    `[AssistantDatabase] Added ${role} message to conversation ${conversationId}`
  );

  return {
    id: message.id,
    role: message.role,
    content: message.content,
    timestamp: message.timestamp,
  };
}

/**
 * Get all messages for a conversation.
 */
export function getMessages(
  projectDir: string,
  conversationId: number
): ConversationMessageModel[] {
  const db = getDb(projectDir);

  const messages = db
    .select()
    .from(conversationMessages)
    .where(eq(conversationMessages.conversationId, conversationId))
    .orderBy(asc(conversationMessages.timestamp))
    .all();

  return messages.map((row) => ({
    id: row.id,
    role: row.role,
    content: row.content,
    timestamp: row.timestamp,
  }));
}
