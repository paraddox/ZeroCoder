// Shared types and utilities for ZeroCoder
// This package contains common types, constants, and utilities
// shared between the server and UI packages.

export const VERSION = '1.0.0';

// Re-export types and constants from types.ts (source of truth for types)
export * from './types.js';

// Re-export Zod schemas (for runtime validation)
// Only export schemas, not inferred types (to avoid conflicts with types.ts)
export {
  // Constants
  MAX_IMAGE_SIZE,
  MAX_TEXT_SIZE,
  // Project schemas
  ProjectCreateSchema,
  ProjectStatsSchema,
  ProjectSummarySchema,
  ProjectDetailSchema,
  ProjectSettingsUpdateSchema,
  ProjectPromptsSchema,
  ProjectPromptsUpdateSchema,
  WizardStatusMessageSchema,
  WizardStatusSchema,
  AddExistingRepoRequestSchema,
  ContainerCountUpdateSchema,
  // Container schemas
  ContainerTypeSchema,
  ContainerStatusTypeSchema,
  AgentTypeSchema,
  SdkTypeSchema,
  ContainerStatusSchema,
  // Feature schemas
  FeatureBaseSchema,
  FeatureCreateSchema,
  FeatureUpdateSchema,
  FeatureResponseSchema,
  FeatureListResponseSchema,
  // Agent schemas
  AgentStatusTypeSchema,
  AgentStartRequestSchema,
  AgentStatusSchema,
  AgentActionResponseSchema,
  // Setup schemas
  SetupStatusSchema,
  // WebSocket schemas
  WSProgressMessageSchema,
  WSFeatureUpdateMessageSchema,
  WSLogMessageSchema,
  WSAgentStatusMessageSchema,
  // Attachment schemas
  ImageMimeTypeSchema,
  TextMimeTypeSchema,
  ImageAttachmentSchema,
  TextAttachmentSchema,
  FileAttachmentSchema,
  // Task schemas
  TaskCreateSchema,
  TaskUpdateSchema,
  // Remote machine schemas
  RemoteMachineCreateSchema,
  RemoteMachineResponseSchema,
  RemoteAgentStartRequestSchema,
  RemoteAgentStatusResponseSchema,
  // Types only defined in schemas.ts (not in types.ts)
  type ProjectCreate,
  type ProjectSettingsUpdate,
  type ProjectPromptsUpdate,
  type AddExistingRepoRequest,
  type ContainerCountUpdate,
  type ContainerStatus,
  type FeatureBase,
  type FeatureUpdate,
  type FeatureResponse,
  type AgentStatusType,
  type AgentStartRequest,
  type TaskCreate,
  type TaskUpdate,
  type RemoteMachineResponse,
  type RemoteAgentStartRequest,
  type RemoteAgentStatusResponse,
} from './schemas.js';
