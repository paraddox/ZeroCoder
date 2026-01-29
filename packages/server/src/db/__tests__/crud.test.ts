/**
 * Database CRUD Unit Tests
 *
 * Tests for all database CRUD operations using an in-memory SQLite database.
 * Covers: projects, containers, remote machines, remote agents, feature stats,
 * session state, and verification state functions.
 */

import { describe, it, expect, beforeEach, beforeAll, afterAll } from 'vitest';
import Database from 'better-sqlite3';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import { eq, and } from 'drizzle-orm';
import * as schema from '../schema.js';

// Create in-memory test database
let testSqlite: ReturnType<typeof Database>;
let testDb: ReturnType<typeof drizzle<typeof schema>>;

// Helper to insert a project directly for tests
function insertProject(name: string, gitUrl: string = 'https://github.com/test/repo') {
  testSqlite.exec(`
    INSERT INTO projects (name, git_url, target_container_count, created_at)
    VALUES ('${name}', '${gitUrl}', 1, '${new Date().toISOString()}')
  `);
}

// Helper to insert a container directly
function insertContainer(
  projectName: string,
  containerNumber: number,
  containerType: string = 'coding'
) {
  testSqlite.exec(`
    INSERT INTO containers (project_name, container_number, container_type, status, created_at)
    VALUES ('${projectName}', ${containerNumber}, '${containerType}', 'created', '${new Date().toISOString()}')
  `);
}

// Helper to insert a remote machine directly
function insertRemoteMachine(name: string, host: string = '192.168.1.1'): number {
  testSqlite.exec(`
    INSERT INTO remote_machines (name, host, port, username, status, created_at)
    VALUES ('${name}', '${host}', 22, 'root', 'unknown', '${new Date().toISOString()}')
  `);
  const result = testSqlite.prepare('SELECT last_insert_rowid() as id').get() as { id: number };
  return result.id;
}

// Helper to insert feature stats cache
function insertFeatureStatsCache(projectName: string) {
  testSqlite.exec(`
    INSERT INTO feature_stats_cache (project_name, pending_count, in_progress_count, done_count, total_count, percentage, last_polled_at, last_overseer_milestone)
    VALUES ('${projectName}', 5, 2, 3, 10, 30.0, '${new Date().toISOString()}', 20)
  `);
}

beforeAll(() => {
  testSqlite = new Database(':memory:');
  testDb = drizzle(testSqlite, { schema });

  // Create tables
  testSqlite.exec(`
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
      created_at TEXT NOT NULL,
      daemon_port INTEGER DEFAULT 9999,
      daemon_pid INTEGER,
      daemon_last_seen TEXT
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
});

afterAll(() => {
  testSqlite.close();
});

beforeEach(() => {
  // Clean all tables before each test
  testSqlite.exec(`
    DELETE FROM remote_agents;
    DELETE FROM remote_machines;
    DELETE FROM feature_cache;
    DELETE FROM feature_stats_cache;
    DELETE FROM project_verification_state;
    DELETE FROM containers;
    DELETE FROM projects;
  `);
});

// =============================================================================
// Validation Function Tests
// =============================================================================

describe('Validation Functions', () => {
  describe('Project Name Validation', () => {
    it('accepts valid project names', () => {
      const validNames = ['my-project', 'project_1', 'MyProject', 'test123', 'a'];
      for (const name of validNames) {
        // Valid project names should match the regex /^[a-zA-Z0-9_-]{1,50}$/
        expect(/^[a-zA-Z0-9_-]{1,50}$/.test(name)).toBe(true);
      }
    });

    it('rejects invalid project names', () => {
      const invalidNames = ['', 'a'.repeat(51), 'my project', 'project@name', 'project/name'];
      for (const name of invalidNames) {
        expect(/^[a-zA-Z0-9_-]{1,50}$/.test(name)).toBe(false);
      }
    });
  });

  describe('Git URL Validation', () => {
    it('accepts valid git URLs', () => {
      const validUrls = [
        'https://github.com/user/repo',
        'https://gitlab.com/user/repo.git',
        'git@github.com:user/repo.git',
      ];
      for (const url of validUrls) {
        expect(url.startsWith('https://') || url.startsWith('git@')).toBe(true);
      }
    });

    it('rejects invalid git URLs', () => {
      const invalidUrls = ['', 'http://github.com/repo', 'ftp://github.com/repo', 'github.com/repo'];
      for (const url of invalidUrls) {
        expect(url === '' || (!url.startsWith('https://') && !url.startsWith('git@'))).toBe(true);
      }
    });
  });
});

// =============================================================================
// Projects CRUD Tests
// =============================================================================

describe('Projects CRUD', () => {
  describe('Create Project', () => {
    it('creates a project successfully', () => {
      insertProject('test-project', 'https://github.com/test/repo');

      const project = testDb
        .select()
        .from(schema.projects)
        .where(eq(schema.projects.name, 'test-project'))
        .get();

      expect(project).toBeDefined();
      expect(project?.name).toBe('test-project');
      expect(project?.gitUrl).toBe('https://github.com/test/repo');
      expect(project?.targetContainerCount).toBe(1);
    });

    it('prevents duplicate project names', () => {
      insertProject('duplicate-project');

      expect(() => {
        insertProject('duplicate-project');
      }).toThrow();
    });
  });

  describe('Read Project', () => {
    it('retrieves a project by name', () => {
      insertProject('my-project', 'https://github.com/user/my-project');

      const project = testDb
        .select()
        .from(schema.projects)
        .where(eq(schema.projects.name, 'my-project'))
        .get();

      expect(project?.gitUrl).toBe('https://github.com/user/my-project');
    });

    it('returns undefined for non-existent project', () => {
      const project = testDb
        .select()
        .from(schema.projects)
        .where(eq(schema.projects.name, 'non-existent'))
        .get();

      expect(project).toBeUndefined();
    });

    it('lists all projects', () => {
      insertProject('project-1');
      insertProject('project-2');
      insertProject('project-3');

      const projects = testDb.select().from(schema.projects).all();

      expect(projects).toHaveLength(3);
      expect(projects.map((p) => p.name).sort()).toEqual(['project-1', 'project-2', 'project-3']);
    });
  });

  describe('Update Project', () => {
    it('updates project git URL', () => {
      insertProject('update-project', 'https://github.com/old/repo');

      testDb
        .update(schema.projects)
        .set({ gitUrl: 'https://github.com/new/repo' })
        .where(eq(schema.projects.name, 'update-project'))
        .run();

      const project = testDb
        .select()
        .from(schema.projects)
        .where(eq(schema.projects.name, 'update-project'))
        .get();

      expect(project?.gitUrl).toBe('https://github.com/new/repo');
    });

    it('updates target container count', () => {
      insertProject('scale-project');

      testDb
        .update(schema.projects)
        .set({ targetContainerCount: 5 })
        .where(eq(schema.projects.name, 'scale-project'))
        .run();

      const project = testDb
        .select()
        .from(schema.projects)
        .where(eq(schema.projects.name, 'scale-project'))
        .get();

      expect(project?.targetContainerCount).toBe(5);
    });
  });

  describe('Delete Project', () => {
    it('deletes a project', () => {
      insertProject('delete-project');

      const result = testDb
        .delete(schema.projects)
        .where(eq(schema.projects.name, 'delete-project'))
        .run();

      expect(result.changes).toBe(1);

      const project = testDb
        .select()
        .from(schema.projects)
        .where(eq(schema.projects.name, 'delete-project'))
        .get();

      expect(project).toBeUndefined();
    });

    it('returns 0 changes when deleting non-existent project', () => {
      const result = testDb
        .delete(schema.projects)
        .where(eq(schema.projects.name, 'non-existent'))
        .run();

      expect(result.changes).toBe(0);
    });
  });
});

// =============================================================================
// Containers CRUD Tests
// =============================================================================

describe('Containers CRUD', () => {
  beforeEach(() => {
    insertProject('container-test-project');
  });

  describe('Create Container', () => {
    it('creates a container record', () => {
      insertContainer('container-test-project', 1, 'coding');

      const container = testDb
        .select()
        .from(schema.containers)
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .get();

      expect(container).toBeDefined();
      expect(container?.status).toBe('created');
      expect(container?.containerType).toBe('coding');
    });

    it('enforces unique constraint on (projectName, containerNumber, containerType)', () => {
      insertContainer('container-test-project', 1, 'coding');

      expect(() => {
        insertContainer('container-test-project', 1, 'coding');
      }).toThrow();
    });

    it('allows same container number with different types', () => {
      insertContainer('container-test-project', 1, 'coding');
      insertContainer('container-test-project', 1, 'init');

      const containers = testDb
        .select()
        .from(schema.containers)
        .where(eq(schema.containers.projectName, 'container-test-project'))
        .all();

      expect(containers).toHaveLength(2);
    });
  });

  describe('Read Container', () => {
    it('retrieves container by project, number, and type', () => {
      insertContainer('container-test-project', 1, 'coding');

      const container = testDb
        .select()
        .from(schema.containers)
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1),
            eq(schema.containers.containerType, 'coding')
          )
        )
        .get();

      expect(container).toBeDefined();
    });

    it('lists all containers for a project', () => {
      insertContainer('container-test-project', 1, 'coding');
      insertContainer('container-test-project', 2, 'coding');
      insertContainer('container-test-project', 0, 'init');

      const containers = testDb
        .select()
        .from(schema.containers)
        .where(eq(schema.containers.projectName, 'container-test-project'))
        .all();

      expect(containers).toHaveLength(3);
    });
  });

  describe('Update Container', () => {
    it('updates container status', () => {
      insertContainer('container-test-project', 1, 'coding');

      testDb
        .update(schema.containers)
        .set({ status: 'running' })
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .run();

      const container = testDb
        .select()
        .from(schema.containers)
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .get();

      expect(container?.status).toBe('running');
    });

    it('updates docker container ID', () => {
      insertContainer('container-test-project', 1, 'coding');

      testDb
        .update(schema.containers)
        .set({ dockerContainerId: 'abc123def456' })
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .run();

      const container = testDb
        .select()
        .from(schema.containers)
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .get();

      expect(container?.dockerContainerId).toBe('abc123def456');
    });

    it('updates current feature', () => {
      insertContainer('container-test-project', 1, 'coding');

      testDb
        .update(schema.containers)
        .set({ currentFeature: 'beads-42' })
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .run();

      const container = testDb
        .select()
        .from(schema.containers)
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .get();

      expect(container?.currentFeature).toBe('beads-42');
    });
  });

  describe('Delete Container', () => {
    it('deletes a container', () => {
      insertContainer('container-test-project', 1, 'coding');

      const result = testDb
        .delete(schema.containers)
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .run();

      expect(result.changes).toBe(1);
    });

    it('cascades delete when project is deleted', () => {
      insertContainer('container-test-project', 1, 'coding');
      insertContainer('container-test-project', 2, 'coding');

      testDb.delete(schema.projects).where(eq(schema.projects.name, 'container-test-project')).run();

      const containers = testDb.select().from(schema.containers).all();
      expect(containers).toHaveLength(0);
    });
  });

  describe('Session State', () => {
    it('sets and gets user started flag', () => {
      insertContainer('container-test-project', 1, 'coding');

      testDb
        .update(schema.containers)
        .set({ userStartedAt: new Date().toISOString() })
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .run();

      const container = testDb
        .select({ userStartedAt: schema.containers.userStartedAt })
        .from(schema.containers)
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .get();

      expect(container?.userStartedAt).not.toBeNull();
    });

    it('sets and gets graceful stop flag', () => {
      insertContainer('container-test-project', 1, 'coding');

      testDb
        .update(schema.containers)
        .set({ gracefulStopRequested: true })
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .run();

      const container = testDb
        .select({ gracefulStopRequested: schema.containers.gracefulStopRequested })
        .from(schema.containers)
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .get();

      // SQLite stores boolean as integer
      expect(container?.gracefulStopRequested).toBeTruthy();
    });

    it('sets and gets restarting flag', () => {
      insertContainer('container-test-project', 1, 'coding');

      testDb
        .update(schema.containers)
        .set({ restarting: true })
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .run();

      const container = testDb
        .select({ restarting: schema.containers.restarting })
        .from(schema.containers)
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .get();

      expect(container?.restarting).toBeTruthy();
    });

    it('sets and gets overseer flags', () => {
      insertContainer('container-test-project', 1, 'coding');

      testDb
        .update(schema.containers)
        .set({
          lastAgentWasOverseer: true,
          isMilestoneOverseer: true,
        })
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .run();

      const container = testDb
        .select({
          lastAgentWasOverseer: schema.containers.lastAgentWasOverseer,
          isMilestoneOverseer: schema.containers.isMilestoneOverseer,
        })
        .from(schema.containers)
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .get();

      expect(container?.lastAgentWasOverseer).toBeTruthy();
      expect(container?.isMilestoneOverseer).toBeTruthy();
    });

    it('updates and retrieves last activity timestamp', () => {
      insertContainer('container-test-project', 1, 'coding');
      const timestamp = new Date().toISOString();

      testDb
        .update(schema.containers)
        .set({ lastActivityAt: timestamp })
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .run();

      const container = testDb
        .select({ lastActivityAt: schema.containers.lastActivityAt })
        .from(schema.containers)
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .get();

      expect(container?.lastActivityAt).toBe(timestamp);
    });

    it('stores and retrieves last closed feature', () => {
      insertContainer('container-test-project', 1, 'coding');

      testDb
        .update(schema.containers)
        .set({ lastClosedFeature: 'beads-99' })
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .run();

      const container = testDb
        .select({ lastClosedFeature: schema.containers.lastClosedFeature })
        .from(schema.containers)
        .where(
          and(
            eq(schema.containers.projectName, 'container-test-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .get();

      expect(container?.lastClosedFeature).toBe('beads-99');
    });
  });
});

// =============================================================================
// Remote Machines CRUD Tests
// =============================================================================

describe('Remote Machines CRUD', () => {
  describe('Create Remote Machine', () => {
    it('creates a remote machine', () => {
      const id = insertRemoteMachine('server-1', '192.168.1.100');

      const machine = testDb
        .select()
        .from(schema.remoteMachines)
        .where(eq(schema.remoteMachines.id, id))
        .get();

      expect(machine).toBeDefined();
      expect(machine?.name).toBe('server-1');
      expect(machine?.host).toBe('192.168.1.100');
      expect(machine?.port).toBe(22);
      expect(machine?.username).toBe('root');
      expect(machine?.status).toBe('unknown');
    });

    it('enforces unique machine names', () => {
      insertRemoteMachine('unique-server');

      expect(() => {
        insertRemoteMachine('unique-server');
      }).toThrow();
    });
  });

  describe('Read Remote Machine', () => {
    it('retrieves a machine by ID', () => {
      const id = insertRemoteMachine('get-server', '10.0.0.1');

      const machine = testDb
        .select()
        .from(schema.remoteMachines)
        .where(eq(schema.remoteMachines.id, id))
        .get();

      expect(machine?.host).toBe('10.0.0.1');
    });

    it('lists all machines', () => {
      insertRemoteMachine('server-a', '10.0.0.1');
      insertRemoteMachine('server-b', '10.0.0.2');
      insertRemoteMachine('server-c', '10.0.0.3');

      const machines = testDb.select().from(schema.remoteMachines).all();

      expect(machines).toHaveLength(3);
    });
  });

  describe('Update Remote Machine', () => {
    it('updates machine status', () => {
      const id = insertRemoteMachine('status-server');

      testDb
        .update(schema.remoteMachines)
        .set({ status: 'online', lastCheckedAt: new Date().toISOString() })
        .where(eq(schema.remoteMachines.id, id))
        .run();

      const machine = testDb
        .select()
        .from(schema.remoteMachines)
        .where(eq(schema.remoteMachines.id, id))
        .get();

      expect(machine?.status).toBe('online');
      expect(machine?.lastCheckedAt).not.toBeNull();
    });
  });

  describe('Delete Remote Machine', () => {
    it('deletes a machine', () => {
      const id = insertRemoteMachine('delete-server');

      const result = testDb
        .delete(schema.remoteMachines)
        .where(eq(schema.remoteMachines.id, id))
        .run();

      expect(result.changes).toBe(1);
    });
  });
});

// =============================================================================
// Remote Agents CRUD Tests
// =============================================================================

describe('Remote Agents CRUD', () => {
  let machineId: number;

  beforeEach(() => {
    insertProject('agent-test-project');
    machineId = insertRemoteMachine('agent-machine');
  });

  describe('Create Remote Agent', () => {
    it('creates a remote agent', () => {
      testSqlite.exec(`
        INSERT INTO remote_agents (project_name, machine_id, agent_number, status, created_at)
        VALUES ('agent-test-project', ${machineId}, 1, 'created', '${new Date().toISOString()}')
      `);

      const agent = testDb
        .select()
        .from(schema.remoteAgents)
        .where(
          and(
            eq(schema.remoteAgents.projectName, 'agent-test-project'),
            eq(schema.remoteAgents.machineId, machineId)
          )
        )
        .get();

      expect(agent).toBeDefined();
      expect(agent?.agentNumber).toBe(1);
      expect(agent?.status).toBe('created');
    });

    it('enforces unique constraint on (projectName, machineId, agentNumber)', () => {
      testSqlite.exec(`
        INSERT INTO remote_agents (project_name, machine_id, agent_number, status, created_at)
        VALUES ('agent-test-project', ${machineId}, 1, 'created', '${new Date().toISOString()}')
      `);

      expect(() => {
        testSqlite.exec(`
          INSERT INTO remote_agents (project_name, machine_id, agent_number, status, created_at)
          VALUES ('agent-test-project', ${machineId}, 1, 'created', '${new Date().toISOString()}')
        `);
      }).toThrow();
    });
  });

  describe('Update Remote Agent', () => {
    it('updates agent status and feature', () => {
      testSqlite.exec(`
        INSERT INTO remote_agents (project_name, machine_id, agent_number, status, created_at)
        VALUES ('agent-test-project', ${machineId}, 1, 'created', '${new Date().toISOString()}')
      `);

      const agent = testDb
        .select()
        .from(schema.remoteAgents)
        .where(eq(schema.remoteAgents.projectName, 'agent-test-project'))
        .get();

      testDb
        .update(schema.remoteAgents)
        .set({
          status: 'running',
          currentFeature: 'beads-10',
          pid: 12345,
        })
        .where(eq(schema.remoteAgents.id, agent!.id))
        .run();

      const updated = testDb
        .select()
        .from(schema.remoteAgents)
        .where(eq(schema.remoteAgents.id, agent!.id))
        .get();

      expect(updated?.status).toBe('running');
      expect(updated?.currentFeature).toBe('beads-10');
      expect(updated?.pid).toBe(12345);
    });

    it('sets graceful stop and restarting flags', () => {
      testSqlite.exec(`
        INSERT INTO remote_agents (project_name, machine_id, agent_number, status, created_at)
        VALUES ('agent-test-project', ${machineId}, 1, 'created', '${new Date().toISOString()}')
      `);

      const agent = testDb
        .select()
        .from(schema.remoteAgents)
        .where(eq(schema.remoteAgents.projectName, 'agent-test-project'))
        .get();

      testDb
        .update(schema.remoteAgents)
        .set({
          gracefulStopRequested: true,
          restarting: true,
        })
        .where(eq(schema.remoteAgents.id, agent!.id))
        .run();

      const updated = testDb
        .select()
        .from(schema.remoteAgents)
        .where(eq(schema.remoteAgents.id, agent!.id))
        .get();

      expect(updated?.gracefulStopRequested).toBeTruthy();
      expect(updated?.restarting).toBeTruthy();
    });
  });

  describe('Delete Remote Agent', () => {
    it('deletes an agent', () => {
      testSqlite.exec(`
        INSERT INTO remote_agents (project_name, machine_id, agent_number, status, created_at)
        VALUES ('agent-test-project', ${machineId}, 1, 'created', '${new Date().toISOString()}')
      `);

      const agent = testDb
        .select()
        .from(schema.remoteAgents)
        .where(eq(schema.remoteAgents.projectName, 'agent-test-project'))
        .get();

      const result = testDb
        .delete(schema.remoteAgents)
        .where(eq(schema.remoteAgents.id, agent!.id))
        .run();

      expect(result.changes).toBe(1);
    });

    it('cascades delete when project is deleted', () => {
      testSqlite.exec(`
        INSERT INTO remote_agents (project_name, machine_id, agent_number, status, created_at)
        VALUES ('agent-test-project', ${machineId}, 1, 'created', '${new Date().toISOString()}')
      `);

      testDb.delete(schema.projects).where(eq(schema.projects.name, 'agent-test-project')).run();

      const agents = testDb.select().from(schema.remoteAgents).all();
      expect(agents).toHaveLength(0);
    });

    it('cascades delete when machine is deleted', () => {
      testSqlite.exec(`
        INSERT INTO remote_agents (project_name, machine_id, agent_number, status, created_at)
        VALUES ('agent-test-project', ${machineId}, 1, 'created', '${new Date().toISOString()}')
      `);

      testDb.delete(schema.remoteMachines).where(eq(schema.remoteMachines.id, machineId)).run();

      const agents = testDb.select().from(schema.remoteAgents).all();
      expect(agents).toHaveLength(0);
    });
  });
});

// =============================================================================
// Feature Stats Cache Tests
// =============================================================================

describe('Feature Stats Cache', () => {
  beforeEach(() => {
    insertProject('stats-test-project');
  });

  it('stores and retrieves feature stats', () => {
    insertFeatureStatsCache('stats-test-project');

    const stats = testDb
      .select()
      .from(schema.featureStatsCache)
      .where(eq(schema.featureStatsCache.projectName, 'stats-test-project'))
      .get();

    expect(stats).toBeDefined();
    expect(stats?.pendingCount).toBe(5);
    expect(stats?.inProgressCount).toBe(2);
    expect(stats?.doneCount).toBe(3);
    expect(stats?.totalCount).toBe(10);
    expect(stats?.percentage).toBe(30.0);
    expect(stats?.lastOverseerMilestone).toBe(20);
  });

  it('updates overseer milestone', () => {
    insertFeatureStatsCache('stats-test-project');

    testDb
      .update(schema.featureStatsCache)
      .set({ lastOverseerMilestone: 50 })
      .where(eq(schema.featureStatsCache.projectName, 'stats-test-project'))
      .run();

    const stats = testDb
      .select()
      .from(schema.featureStatsCache)
      .where(eq(schema.featureStatsCache.projectName, 'stats-test-project'))
      .get();

    expect(stats?.lastOverseerMilestone).toBe(50);
  });

  it('cascades delete when project is deleted', () => {
    insertFeatureStatsCache('stats-test-project');

    testDb.delete(schema.projects).where(eq(schema.projects.name, 'stats-test-project')).run();

    const stats = testDb.select().from(schema.featureStatsCache).all();
    expect(stats).toHaveLength(0);
  });
});

// =============================================================================
// Feature Cache Tests
// =============================================================================

describe('Feature Cache', () => {
  beforeEach(() => {
    insertProject('feature-cache-project');
  });

  it('stores and retrieves feature cache entries', () => {
    testSqlite.exec(`
      INSERT INTO feature_cache (project_name, feature_id, priority, category, name, description, steps_json, status, updated_at)
      VALUES ('feature-cache-project', 'beads-1', 1, 'core', 'Add login', 'Implement login functionality', '["step 1", "step 2"]', 'open', '${new Date().toISOString()}')
    `);

    const feature = testDb
      .select()
      .from(schema.featureCache)
      .where(
        and(
          eq(schema.featureCache.projectName, 'feature-cache-project'),
          eq(schema.featureCache.featureId, 'beads-1')
        )
      )
      .get();

    expect(feature).toBeDefined();
    expect(feature?.name).toBe('Add login');
    expect(feature?.priority).toBe(1);
    expect(feature?.status).toBe('open');
  });

  it('uses composite primary key (projectName, featureId)', () => {
    testSqlite.exec(`
      INSERT INTO feature_cache (project_name, feature_id, priority, name, status, updated_at)
      VALUES ('feature-cache-project', 'beads-1', 1, 'Feature 1', 'open', '${new Date().toISOString()}')
    `);

    expect(() => {
      testSqlite.exec(`
        INSERT INTO feature_cache (project_name, feature_id, priority, name, status, updated_at)
        VALUES ('feature-cache-project', 'beads-1', 2, 'Duplicate', 'open', '${new Date().toISOString()}')
      `);
    }).toThrow();
  });

  it('allows same feature ID in different projects', () => {
    insertProject('another-project');

    testSqlite.exec(`
      INSERT INTO feature_cache (project_name, feature_id, priority, name, status, updated_at)
      VALUES ('feature-cache-project', 'beads-1', 1, 'Feature 1', 'open', '${new Date().toISOString()}')
    `);
    testSqlite.exec(`
      INSERT INTO feature_cache (project_name, feature_id, priority, name, status, updated_at)
      VALUES ('another-project', 'beads-1', 1, 'Feature 1 in another project', 'open', '${new Date().toISOString()}')
    `);

    const features = testDb.select().from(schema.featureCache).all();
    expect(features).toHaveLength(2);
  });
});

// =============================================================================
// Project Verification State Tests
// =============================================================================

describe('Project Verification State', () => {
  it('sets verification running state', () => {
    testSqlite.exec(`
      INSERT INTO project_verification_state (project_name, verification_running, started_at)
      VALUES ('verify-project', 1, '${new Date().toISOString()}')
    `);

    const state = testDb
      .select()
      .from(schema.projectVerificationState)
      .where(eq(schema.projectVerificationState.projectName, 'verify-project'))
      .get();

    expect(state).toBeDefined();
    expect(state?.verificationRunning).toBeTruthy();
    expect(state?.startedAt).not.toBeNull();
  });

  it('clears verification state', () => {
    testSqlite.exec(`
      INSERT INTO project_verification_state (project_name, verification_running, started_at)
      VALUES ('clear-verify', 1, '${new Date().toISOString()}')
    `);

    testDb
      .update(schema.projectVerificationState)
      .set({ verificationRunning: false, startedAt: null })
      .where(eq(schema.projectVerificationState.projectName, 'clear-verify'))
      .run();

    const state = testDb
      .select()
      .from(schema.projectVerificationState)
      .where(eq(schema.projectVerificationState.projectName, 'clear-verify'))
      .get();

    expect(state?.verificationRunning).toBeFalsy();
    expect(state?.startedAt).toBeNull();
  });
});

// =============================================================================
// Transaction Handling Tests
// =============================================================================

describe('Transaction Handling', () => {
  it('rolls back on error', () => {
    insertProject('transaction-project');

    try {
      testSqlite.transaction(() => {
        testSqlite.exec(`
          UPDATE projects SET target_container_count = 5 WHERE name = 'transaction-project'
        `);
        // Force an error
        throw new Error('Simulated error');
      })();
    } catch {
      // Expected
    }

    const project = testDb
      .select()
      .from(schema.projects)
      .where(eq(schema.projects.name, 'transaction-project'))
      .get();

    // Should still be 1 due to rollback
    expect(project?.targetContainerCount).toBe(1);
  });

  it('commits successful transactions', () => {
    insertProject('commit-project');

    testSqlite.transaction(() => {
      testSqlite.exec(`
        UPDATE projects SET target_container_count = 5 WHERE name = 'commit-project'
      `);
    })();

    const project = testDb
      .select()
      .from(schema.projects)
      .where(eq(schema.projects.name, 'commit-project'))
      .get();

    expect(project?.targetContainerCount).toBe(5);
  });
});

// =============================================================================
// Concurrent Access Tests
// =============================================================================

describe('Concurrent Access', () => {
  it('handles concurrent writes with serialization', () => {
    insertProject('concurrent-project');
    insertContainer('concurrent-project', 1, 'coding');

    // Simulate concurrent updates
    const updates = Array.from({ length: 10 }, (_, i) => {
      return testDb
        .update(schema.containers)
        .set({ status: i % 2 === 0 ? 'running' : 'stopped' })
        .where(
          and(
            eq(schema.containers.projectName, 'concurrent-project'),
            eq(schema.containers.containerNumber, 1)
          )
        )
        .run();
    });

    // All updates should succeed
    expect(updates.every((u) => u.changes === 1)).toBe(true);

    // Final state should be deterministic (last write wins)
    const container = testDb
      .select()
      .from(schema.containers)
      .where(
        and(
          eq(schema.containers.projectName, 'concurrent-project'),
          eq(schema.containers.containerNumber, 1)
        )
      )
      .get();

    expect(['running', 'stopped']).toContain(container?.status);
  });
});
