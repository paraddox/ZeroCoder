// Database connection and client
// Uses better-sqlite3 with Drizzle ORM

import Database from 'better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import * as schema from './schema.js';

const dbPath = process.env['DATABASE_URL'] ?? './data/zerocoder.db';
const sqlite = new Database(dbPath);
export const db = drizzle(sqlite, { schema });

export * from './schema.js';
