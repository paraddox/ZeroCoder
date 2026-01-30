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

// Run migrations to add new columns to existing tables
// These are idempotent - they check if column exists before adding
function runMigrations(): void {
  // Add daemon_version column to remote_machines table (added in checkup system feature)
  try {
    const tableInfo = sqlite.prepare("PRAGMA table_info('remote_machines')").all() as { name: string }[];
    const hasDaemonVersion = tableInfo.some((col) => col.name === 'daemon_version');
    if (!hasDaemonVersion) {
      sqlite.exec("ALTER TABLE remote_machines ADD COLUMN daemon_version TEXT");
      console.log('[Migration] Added daemon_version column to remote_machines table');
    }
  } catch (e) {
    // Table might not exist yet, that's fine - schema will create it
    console.debug('[Migration] remote_machines table does not exist yet, skipping migration');
  }
}

runMigrations();

export const db = drizzle(sqlite, { schema });

export * from './schema.js';
export * from './crud.js';
