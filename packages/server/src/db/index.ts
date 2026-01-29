// Database connection and client
// Uses better-sqlite3 with Drizzle ORM

import Database from 'better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import { mkdirSync } from 'fs';
import { dirname } from 'path';
import * as schema from './schema.js';

const dbPath = process.env['DATABASE_URL'] ?? './data/zerocoder.db';

// Ensure the database directory exists
mkdirSync(dirname(dbPath), { recursive: true });

const sqlite = new Database(dbPath);
export const db = drizzle(sqlite, { schema });

export * from './schema.js';
export * from './crud.js';
