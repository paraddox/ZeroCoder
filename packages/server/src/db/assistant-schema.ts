/**
 * Assistant Database Schema (Drizzle ORM)
 * ======================================
 *
 * SQLite database schema for assistant conversations.
 * Each project has its own assistant.db file in the project directory.
 *
 * Tables:
 * - conversations: Chat conversations for a project
 * - conversation_messages: Individual messages within conversations
 */

import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';

// =============================================================================
// Conversations Table
// =============================================================================

export const conversations = sqliteTable('conversations', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  projectName: text('project_name', { length: 100 }).notNull(),
  title: text('title', { length: 200 }),
  createdAt: text('created_at').notNull(), // ISO timestamp
  updatedAt: text('updated_at').notNull(), // ISO timestamp
});

export type Conversation = typeof conversations.$inferSelect;
export type NewConversation = typeof conversations.$inferInsert;

// =============================================================================
// Conversation Messages Table
// =============================================================================

export const conversationMessages = sqliteTable('conversation_messages', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  conversationId: integer('conversation_id')
    .notNull()
    .references(() => conversations.id, { onDelete: 'cascade' }),
  role: text('role', { length: 20 }).notNull(), // 'user' | 'assistant' | 'system'
  content: text('content').notNull(),
  timestamp: text('timestamp').notNull(), // ISO timestamp
});

export type ConversationMessage = typeof conversationMessages.$inferSelect;
export type NewConversationMessage = typeof conversationMessages.$inferInsert;
