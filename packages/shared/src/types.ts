// Shared TypeScript types for ZeroCoder
// These types will be extracted from ui/src/lib/types.ts in ZeroCoder-awb.18

// Placeholder types - will be populated with actual types

/** Project status values */
export type ProjectStatus = 'active' | 'paused' | 'completed' | 'error';

/** Agent/container status values */
export type AgentStatus = 'not_created' | 'running' | 'stopped' | 'completed';

/** Feature status values */
export type FeatureStatus = 'open' | 'in_progress' | 'closed';

/** Priority levels (P0=critical, P4=backlog) */
export type Priority = 0 | 1 | 2 | 3 | 4;
