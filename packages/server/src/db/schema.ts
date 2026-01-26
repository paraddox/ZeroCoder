// Database schema using Drizzle ORM
// This will be populated with tables from server/schemas.py

import { sqliteTable, text, integer } from 'drizzle-orm/sqlite-core';

// Placeholder schema - will be populated by ZeroCoder-awb.24
export const projects = sqliteTable('projects', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  name: text('name').notNull().unique(),
  path: text('path').notNull(),
  gitUrl: text('git_url'),
  status: text('status').notNull().default('active'),
  createdAt: text('created_at').notNull(),
  updatedAt: text('updated_at').notNull(),
});

export type Project = typeof projects.$inferSelect;
export type NewProject = typeof projects.$inferInsert;
