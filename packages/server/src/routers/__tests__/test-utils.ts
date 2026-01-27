/**
 * Router Integration Test Utilities
 *
 * Provides test helpers for API integration tests:
 * - In-memory database setup
 * - Mock external dependencies (Docker, beads CLI, filesystem)
 * - Test app factory with routers
 */

import { Hono } from 'hono';
import Database from 'better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import { vi } from 'vitest';
import * as schema from '../../db/schema.js';

// =============================================================================
// Types
// =============================================================================

export type TestDb = ReturnType<typeof drizzle<typeof schema>>;
export type TestSqlite = ReturnType<typeof Database>;

export interface TestContext {
  sqlite: TestSqlite;
  db: TestDb;
  cleanup: () => void;
}

// =============================================================================
// Database Setup
// =============================================================================

/**
 * Create an in-memory test database with all tables.
 */
export function createTestDatabase(): TestContext {
  const sqlite = new Database(':memory:');
  const db = drizzle(sqlite, { schema });

  // Create all tables
  sqlite.exec(`
    CREATE TABLE IF NOT EXISTS projects (
      name TEXT PRIMARY KEY NOT NULL,
      git_url TEXT NOT NULL,
      target_container_count INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS containers (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_name TEXT NOT NULL REFERENCES projects(name) ON DELETE CASCADE,
      container_number INTEGER NOT NULL,
      container_type TEXT NOT NULL DEFAULT 'coding',
      docker_container_id TEXT,
      status TEXT NOT NULL DEFAULT 'created',
      current_feature TEXT,
      created_at TEXT NOT NULL,
      user_started_at TEXT,
      graceful_stop_requested INTEGER NOT NULL DEFAULT 0,
      restarting INTEGER NOT NULL DEFAULT 0,
      last_agent_was_overseer INTEGER NOT NULL DEFAULT 0,
      is_milestone_overseer INTEGER NOT NULL DEFAULT 0,
      last_activity_at TEXT,
      last_closed_feature TEXT,
      UNIQUE(project_name, container_number, container_type)
    );

    CREATE TABLE IF NOT EXISTS feature_cache (
      project_name TEXT NOT NULL REFERENCES projects(name) ON DELETE CASCADE,
      feature_id TEXT NOT NULL,
      priority INTEGER NOT NULL DEFAULT 999,
      category TEXT NOT NULL DEFAULT '',
      name TEXT NOT NULL,
      description TEXT NOT NULL DEFAULT '',
      steps_json TEXT NOT NULL DEFAULT '[]',
      status TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY (project_name, feature_id)
    );

    CREATE TABLE IF NOT EXISTS feature_stats_cache (
      project_name TEXT PRIMARY KEY REFERENCES projects(name) ON DELETE CASCADE,
      pending_count INTEGER NOT NULL DEFAULT 0,
      in_progress_count INTEGER NOT NULL DEFAULT 0,
      done_count INTEGER NOT NULL DEFAULT 0,
      total_count INTEGER NOT NULL DEFAULT 0,
      percentage REAL NOT NULL DEFAULT 0.0,
      last_polled_at TEXT NOT NULL,
      poll_error TEXT,
      last_overseer_milestone INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS remote_machines (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL UNIQUE,
      host TEXT NOT NULL,
      port INTEGER NOT NULL DEFAULT 22,
      username TEXT NOT NULL DEFAULT 'root',
      ssh_key_path TEXT,
      status TEXT NOT NULL DEFAULT 'unknown',
      last_checked_at TEXT,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS remote_agents (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      project_name TEXT NOT NULL REFERENCES projects(name) ON DELETE CASCADE,
      machine_id INTEGER NOT NULL REFERENCES remote_machines(id) ON DELETE CASCADE,
      agent_number INTEGER NOT NULL DEFAULT 1,
      status TEXT NOT NULL DEFAULT 'created',
      current_feature TEXT,
      pid INTEGER,
      user_started_at TEXT,
      graceful_stop_requested INTEGER NOT NULL DEFAULT 0,
      restarting INTEGER NOT NULL DEFAULT 0,
      last_activity_at TEXT,
      created_at TEXT NOT NULL,
      UNIQUE(project_name, machine_id, agent_number)
    );

    CREATE TABLE IF NOT EXISTS project_verification_state (
      project_name TEXT PRIMARY KEY,
      verification_running INTEGER NOT NULL DEFAULT 0,
      started_at TEXT
    );
  `);

  return {
    sqlite,
    db,
    cleanup: () => sqlite.close(),
  };
}

/**
 * Clear all data from test database tables.
 */
export function clearTestDatabase(sqlite: TestSqlite): void {
  sqlite.exec(`
    DELETE FROM remote_agents;
    DELETE FROM remote_machines;
    DELETE FROM feature_cache;
    DELETE FROM feature_stats_cache;
    DELETE FROM project_verification_state;
    DELETE FROM containers;
    DELETE FROM projects;
  `);
}

// =============================================================================
// Test Data Helpers
// =============================================================================

/**
 * Insert a test project directly into the database.
 */
export function insertTestProject(
  sqlite: TestSqlite,
  name: string,
  gitUrl: string = 'https://github.com/test/repo',
  targetContainerCount: number = 1
): void {
  sqlite.exec(`
    INSERT INTO projects (name, git_url, target_container_count, created_at)
    VALUES ('${name}', '${gitUrl}', ${targetContainerCount}, '${new Date().toISOString()}')
  `);
}

/**
 * Insert a test container directly into the database.
 */
export function insertTestContainer(
  sqlite: TestSqlite,
  projectName: string,
  containerNumber: number,
  containerType: string = 'coding',
  status: string = 'created'
): void {
  sqlite.exec(`
    INSERT INTO containers (project_name, container_number, container_type, status, created_at)
    VALUES ('${projectName}', ${containerNumber}, '${containerType}', '${status}', '${new Date().toISOString()}')
  `);
}

/**
 * Insert feature stats cache for a project.
 */
export function insertTestFeatureStats(
  sqlite: TestSqlite,
  projectName: string,
  stats: {
    pending?: number;
    inProgress?: number;
    done?: number;
    total?: number;
    percentage?: number;
  } = {}
): void {
  const pending = stats.pending ?? 5;
  const inProgress = stats.inProgress ?? 2;
  const done = stats.done ?? 3;
  const total = stats.total ?? 10;
  const percentage = stats.percentage ?? 30.0;

  sqlite.exec(`
    INSERT INTO feature_stats_cache
    (project_name, pending_count, in_progress_count, done_count, total_count, percentage, last_polled_at, last_overseer_milestone)
    VALUES ('${projectName}', ${pending}, ${inProgress}, ${done}, ${total}, ${percentage}, '${new Date().toISOString()}', 0)
  `);
}

// =============================================================================
// Mock Factories
// =============================================================================

/**
 * Create mock functions for filesystem operations.
 */
export function createFsMocks() {
  return {
    existsSync: vi.fn(() => true),
    readFileSync: vi.fn(() => ''),
    writeFileSync: vi.fn(),
    mkdirSync: vi.fn(),
    unlinkSync: vi.fn(),
    rmSync: vi.fn(),
    readdirSync: vi.fn(() => []),
    accessSync: vi.fn(),
  };
}

/**
 * Create mock functions for child_process operations.
 */
export function createChildProcessMocks() {
  return {
    execSync: vi.fn(() => Buffer.from('')),
    spawnSync: vi.fn(() => ({ status: 0, stdout: '', stderr: '' })),
  };
}

/**
 * Create mock for beads CLI commands.
 */
export function createBeadsMocks() {
  return {
    runBeadsCommand: vi.fn(() => ({ success: true, output: '[]' })),
    getBeadsTasks: vi.fn(() => []),
  };
}

// =============================================================================
// Test App Factory
// =============================================================================

/**
 * Create a test Hono app with error handling middleware.
 */
export function createTestApp(): Hono {
  const app = new Hono();

  // Simple error handler for tests
  app.onError((err, c) => {
    const status = 'status' in err ? (err.status as number) : 500;
    const message = err.message || 'Internal server error';
    return c.json({ error: message, status }, status as 500);
  });

  return app;
}

// =============================================================================
// Request Helpers
// =============================================================================

/**
 * Helper to make test requests to a Hono app.
 */
export async function testRequest(
  app: Hono,
  method: string,
  path: string,
  body?: unknown,
  headers: Record<string, string> = {}
): Promise<Response> {
  const url = new URL(path, 'http://localhost');

  const init: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...headers,
    },
  };

  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }

  return app.request(url.toString(), init);
}

/**
 * Parse JSON response with type safety.
 */
export async function parseResponse<T>(response: Response): Promise<T> {
  return (await response.json()) as T;
}
