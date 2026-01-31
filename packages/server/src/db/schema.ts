/**
 * Database Schema (Drizzle ORM)
 * =============================
 *
 * SQLite database schema converted from registry.py SQLAlchemy models.
 * Tables:
 * - projects: Registered projects with git URLs
 * - containers: Docker container instances for projects
 * - featureCache: Cached feature data from container polling
 * - featureStatsCache: Aggregate feature statistics
 * - remoteMachines: Remote machines with daemon for agent execution
 * - projectVerificationState: Session-scoped verification tracking
 */

import { sqliteTable, text, integer, real, primaryKey, unique } from 'drizzle-orm/sqlite-core';
import { relations } from 'drizzle-orm';

// =============================================================================
// Projects Table
// =============================================================================

export const projects = sqliteTable('projects', {
  // Primary key is the project name (not auto-increment ID)
  name: text('name', { length: 50 }).primaryKey(),
  gitUrl: text('git_url').notNull(),
  targetContainerCount: integer('target_container_count').notNull().default(1),
  createdAt: text('created_at').notNull(), // ISO timestamp
});

export const projectsRelations = relations(projects, ({ many }) => ({
  containers: many(containers),
  featureCache: many(featureCache),
  featureStatsCache: many(featureStatsCache),
}));

export type Project = typeof projects.$inferSelect;
export type NewProject = typeof projects.$inferInsert;

// =============================================================================
// Containers Table
// =============================================================================

export const containers = sqliteTable(
  'containers',
  {
    id: integer('id').primaryKey({ autoIncrement: true }),
    projectName: text('project_name', { length: 50 })
      .notNull()
      .references(() => projects.name, { onDelete: 'cascade' }),
    containerNumber: integer('container_number').notNull(),
    containerType: text('container_type', { length: 20 }).notNull().default('coding'), // 'init' | 'coding'
    dockerContainerId: text('docker_container_id', { length: 100 }),
    status: text('status', { length: 20 }).notNull().default('created'), // 'created' | 'running' | 'stopping' | 'stopped'
    currentFeature: text('current_feature', { length: 50 }),
    createdAt: text('created_at').notNull(),

    // Session-scoped state (cleared on server restart)
    userStartedAt: text('user_started_at'), // ISO timestamp, non-null = user started
    gracefulStopRequested: integer('graceful_stop_requested', { mode: 'boolean' }).notNull().default(false),
    restarting: integer('restarting', { mode: 'boolean' }).notNull().default(false),
    lastAgentWasOverseer: integer('last_agent_was_overseer', { mode: 'boolean' }).notNull().default(false),
    isMilestoneOverseer: integer('is_milestone_overseer', { mode: 'boolean' }).notNull().default(false),
    lastActivityAt: text('last_activity_at'), // ISO timestamp
    lastClosedFeature: text('last_closed_feature', { length: 50 }),
  },
  (table) => [
    unique('uq_container_identity').on(table.projectName, table.containerNumber, table.containerType),
  ]
);

export const containersRelations = relations(containers, ({ one }) => ({
  project: one(projects, {
    fields: [containers.projectName],
    references: [projects.name],
  }),
}));

export type Container = typeof containers.$inferSelect;
export type NewContainer = typeof containers.$inferInsert;

// Valid container types and statuses (for validation)
export const CONTAINER_TYPES = ['init', 'coding'] as const;
export const CONTAINER_STATUSES = ['created', 'running', 'stopping', 'stopped'] as const;
export type ContainerType = (typeof CONTAINER_TYPES)[number];
export type ContainerStatus = (typeof CONTAINER_STATUSES)[number];

// =============================================================================
// Feature Cache Table
// =============================================================================

export const featureCache = sqliteTable(
  'feature_cache',
  {
    projectName: text('project_name', { length: 50 })
      .notNull()
      .references(() => projects.name, { onDelete: 'cascade' }),
    featureId: text('feature_id', { length: 50 }).notNull(),
    priority: integer('priority').notNull().default(999),
    category: text('category', { length: 100 }).notNull().default(''),
    name: text('name', { length: 255 }).notNull(),
    description: text('description').notNull().default(''),
    stepsJson: text('steps_json').notNull().default('[]'), // JSON array of steps
    status: text('status', { length: 20 }).notNull(), // 'open' | 'in_progress' | 'closed'
    updatedAt: text('updated_at').notNull(), // ISO timestamp
  },
  (table) => [primaryKey({ columns: [table.projectName, table.featureId] })]
);

export const featureCacheRelations = relations(featureCache, ({ one }) => ({
  project: one(projects, {
    fields: [featureCache.projectName],
    references: [projects.name],
  }),
}));

export type FeatureCache = typeof featureCache.$inferSelect;
export type NewFeatureCache = typeof featureCache.$inferInsert;

// Valid feature statuses
export const FEATURE_STATUSES = ['open', 'in_progress', 'closed'] as const;
export type FeatureStatus = (typeof FEATURE_STATUSES)[number];

// =============================================================================
// Feature Stats Cache Table
// =============================================================================

export const featureStatsCache = sqliteTable('feature_stats_cache', {
  projectName: text('project_name', { length: 50 })
    .primaryKey()
    .references(() => projects.name, { onDelete: 'cascade' }),
  pendingCount: integer('pending_count').notNull().default(0),
  inProgressCount: integer('in_progress_count').notNull().default(0),
  doneCount: integer('done_count').notNull().default(0),
  totalCount: integer('total_count').notNull().default(0),
  percentage: real('percentage').notNull().default(0.0),
  lastPolledAt: text('last_polled_at').notNull(), // ISO timestamp
  pollError: text('poll_error', { length: 500 }),
  lastOverseerMilestone: integer('last_overseer_milestone').notNull().default(0), // 0, 10, 20, ..., 90
});

export const featureStatsCacheRelations = relations(featureStatsCache, ({ one }) => ({
  project: one(projects, {
    fields: [featureStatsCache.projectName],
    references: [projects.name],
  }),
}));

export type FeatureStatsCache = typeof featureStatsCache.$inferSelect;
export type NewFeatureStatsCache = typeof featureStatsCache.$inferInsert;

// =============================================================================
// Remote Machines Table
// =============================================================================

export const remoteMachines = sqliteTable('remote_machines', {
  id: integer('id').primaryKey({ autoIncrement: true }),
  name: text('name', { length: 100 }).notNull().unique(),
  host: text('host', { length: 255 }).notNull(),
  port: integer('port').notNull().default(22),
  username: text('username', { length: 100 }).notNull().default('root'),
  sshKeyPath: text('ssh_key_path', { length: 500 }),
  gitSshKeyPath: text('git_ssh_key_path', { length: 500 }), // Path to SSH key for git clone on remote
  status: text('status', { length: 20 }).notNull().default('unknown'), // 'online' | 'offline' | 'unknown'
  lastCheckedAt: text('last_checked_at'), // ISO timestamp
  createdAt: text('created_at').notNull(), // ISO timestamp
  // Daemon fields (for daemon-based remote agents)
  daemonPort: integer('daemon_port').default(9999),
  daemonPid: integer('daemon_pid'),
  daemonLastSeen: text('daemon_last_seen'), // ISO timestamp
  daemonVersion: text('daemon_version', { length: 50 }), // Version of deployed daemon
});

export type RemoteMachine = typeof remoteMachines.$inferSelect;
export type NewRemoteMachine = typeof remoteMachines.$inferInsert;

// Valid machine statuses
export const MACHINE_STATUSES = ['online', 'offline', 'unknown'] as const;
export type MachineStatus = (typeof MACHINE_STATUSES)[number];

// =============================================================================
// Project Verification State Table (session-scoped)
// =============================================================================

export const projectVerificationState = sqliteTable('project_verification_state', {
  projectName: text('project_name', { length: 50 }).primaryKey(),
  verificationRunning: integer('verification_running', { mode: 'boolean' }).notNull().default(false),
  startedAt: text('started_at'), // ISO timestamp
});

export type ProjectVerificationState = typeof projectVerificationState.$inferSelect;
export type NewProjectVerificationState = typeof projectVerificationState.$inferInsert;
