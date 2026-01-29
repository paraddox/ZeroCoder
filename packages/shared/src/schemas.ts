/**
 * Shared Zod schemas for ZeroCoder
 * Matches server/schemas.py Pydantic models
 */

import { z } from 'zod';

// ============================================================================
// Constants
// ============================================================================

export const MAX_IMAGE_SIZE = 5 * 1024 * 1024; // 5 MB for images
export const MAX_TEXT_SIZE = 1 * 1024 * 1024; // 1 MB for text files

// ============================================================================
// Project Schemas
// ============================================================================

export const ProjectCreateSchema = z.object({
  name: z
    .string()
    .min(1)
    .max(50)
    .regex(/^[a-zA-Z0-9_-]+$/),
  git_url: z.string().min(1).describe('Git repository URL (https:// or git@)'),
  is_new: z.boolean().default(true).describe('True if this is a new project needing wizard setup'),
  spec_method: z.enum(['claude', 'manual']).default('claude'),
});

export const ProjectStatsSchema = z.object({
  passing: z.number().int().default(0),
  in_progress: z.number().int().default(0),
  total: z.number().int().default(0),
  percentage: z.number().default(0.0),
});

export const ProjectSummarySchema = z.object({
  name: z.string(),
  git_url: z.string(),
  local_path: z.string(),
  is_new: z.boolean().default(true),
  has_spec: z.boolean(),
  wizard_incomplete: z.boolean().default(false),
  stats: ProjectStatsSchema,
  target_container_count: z.number().int().default(1),
  agent_status: z.string().nullable().optional(),
  agent_running: z.boolean().nullable().optional(),
  agent_model: z.string().nullable().optional(),
});

export const ProjectDetailSchema = z.object({
  name: z.string(),
  git_url: z.string(),
  local_path: z.string(),
  is_new: z.boolean().default(true),
  has_spec: z.boolean(),
  stats: ProjectStatsSchema,
  prompts_dir: z.string(),
  target_container_count: z.number().int().default(1),
  agent_model: z.string().nullable().optional(),
});

export const ProjectSettingsUpdateSchema = z.object({
  agent_model: z.string().describe('Model ID for coder/overseer agents'),
});

export const ProjectPromptsSchema = z.object({
  app_spec: z.string().default(''),
  initializer_prompt: z.string().default(''),
  coding_prompt: z.string().default(''),
});

export const ProjectPromptsUpdateSchema = z.object({
  app_spec: z.string().nullable().optional(),
  initializer_prompt: z.string().nullable().optional(),
  coding_prompt: z.string().nullable().optional(),
});

export const WizardStatusMessageSchema = z.object({
  role: z.enum(['user', 'assistant']),
  content: z.string(),
  timestamp: z.string(), // ISO datetime string
});

export const WizardStatusSchema = z.object({
  step: z.enum(['mode', 'details', 'method', 'chat']),
  spec_method: z.enum(['claude', 'manual']).nullable().optional(),
  started_at: z.string(), // ISO datetime string
  chat_messages: z.array(WizardStatusMessageSchema).default([]),
});

export const AddExistingRepoRequestSchema = z.object({
  name: z
    .string()
    .min(1)
    .max(50)
    .regex(/^[a-zA-Z0-9_-]+$/),
  git_url: z.string().min(1).describe('Git repository URL (https:// or git@)'),
});

export const ContainerCountUpdateSchema = z.object({
  target_count: z.number().int().min(1).max(10),
});

// ============================================================================
// Container Schemas
// ============================================================================

export const ContainerTypeSchema = z.enum(['init', 'coding']);
export const ContainerStatusTypeSchema = z.enum([
  'not_created',
  'created',
  'running',
  'stopping',
  'stopped',
  'completed',
]);
export const AgentTypeSchema = z.enum(['coder', 'overseer', 'initializer', 'reviewer']);
export const SdkTypeSchema = z.enum(['claude', 'opencode']);

export const ContainerStatusSchema = z.object({
  id: z.number().int(),
  container_number: z.number().int(),
  container_type: ContainerTypeSchema,
  status: ContainerStatusTypeSchema,
  current_feature: z.string().nullable().optional(),
  docker_container_id: z.string().nullable().optional(),
  agent_type: AgentTypeSchema.nullable().optional(),
  sdk_type: SdkTypeSchema.nullable().optional(),
});

// ============================================================================
// Feature Schemas
// ============================================================================

export const FeatureBaseSchema = z.object({
  category: z.string(),
  name: z.string(),
  description: z.string(),
  steps: z.array(z.string()),
});

export const FeatureCreateSchema = FeatureBaseSchema.extend({
  priority: z.number().int().nullable().optional(),
});

export const FeatureUpdateSchema = z.object({
  name: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
  category: z.string().nullable().optional(),
  priority: z.number().int().nullable().optional(),
  steps: z.array(z.string()).nullable().optional(),
});

export const FeatureResponseSchema = FeatureBaseSchema.extend({
  id: z.string(), // beads uses string IDs like "feat-1"
  priority: z.number().int(),
  passes: z.boolean(),
  in_progress: z.boolean(),
});

export const FeatureListResponseSchema = z.object({
  pending: z.array(FeatureResponseSchema),
  in_progress: z.array(FeatureResponseSchema),
  done: z.array(FeatureResponseSchema),
});

// ============================================================================
// Agent Schemas
// ============================================================================

export const AgentStatusTypeSchema = z.enum([
  'not_created',
  'stopped',
  'running',
  'paused',
  'crashed',
  'completed',
]);

export const AgentStartRequestSchema = z.object({
  instruction: z.string().nullable().optional(),
  yolo_mode: z.boolean().default(false), // Kept for backwards compatibility
});

export const AgentStatusSchema = z.object({
  status: AgentStatusTypeSchema,
  container_name: z.string().nullable().optional(),
  started_at: z.string().nullable().optional(), // ISO datetime string
  idle_seconds: z.number().int().default(0),
  agent_running: z.boolean().default(false),
  graceful_stop_requested: z.boolean().default(false),
  current_feature: z.string().nullable().optional(),
  agent_type: AgentTypeSchema.nullable().optional(),
  sdk_type: SdkTypeSchema.nullable().optional(),
  // Legacy fields for backwards compatibility
  pid: z.number().int().nullable().optional(),
  yolo_mode: z.boolean().default(false),
});

export const AgentActionResponseSchema = z.object({
  success: z.boolean(),
  status: z.string(),
  message: z.string().default(''),
});

// ============================================================================
// Setup Schemas
// ============================================================================

export const SetupStatusSchema = z.object({
  claude_cli: z.boolean(),
  credentials: z.boolean(),
  node: z.boolean(),
  npm: z.boolean(),
});

// ============================================================================
// WebSocket Message Schemas
// ============================================================================

export const WSProgressMessageSchema = z.object({
  type: z.literal('progress'),
  passing: z.number().int(),
  total: z.number().int(),
  percentage: z.number(),
});

export const WSFeatureUpdateMessageSchema = z.object({
  type: z.literal('feature_update'),
  feature_id: z.string(), // beads uses string IDs
  passes: z.boolean(),
});

export const WSLogMessageSchema = z.object({
  type: z.literal('log'),
  line: z.string(),
  timestamp: z.string(), // ISO datetime string
});

export const WSAgentStatusMessageSchema = z.object({
  type: z.literal('agent_status'),
  status: z.string(),
});

// ============================================================================
// Spec Chat / Attachment Schemas
// ============================================================================

export const ImageMimeTypeSchema = z.enum(['image/jpeg', 'image/png']);
export const TextMimeTypeSchema = z.enum([
  'text/plain',
  'text/markdown',
  'text/csv',
  'application/json',
  'text/html',
  'text/css',
  'text/javascript',
  'application/xml',
]);

export const ImageAttachmentSchema = z.object({
  filename: z.string().min(1).max(255),
  mimeType: ImageMimeTypeSchema,
  base64Data: z.string().refine(
    (data) => {
      try {
        const decoded = atob(data);
        return decoded.length <= MAX_IMAGE_SIZE;
      } catch {
        return false;
      }
    },
    { message: `Image must be valid base64 and under ${MAX_IMAGE_SIZE / (1024 * 1024)} MB` }
  ),
  isText: z.literal(false).default(false),
});

export const TextAttachmentSchema = z.object({
  filename: z.string().min(1).max(255),
  mimeType: TextMimeTypeSchema,
  textContent: z.string().refine((text) => Buffer.byteLength(text, 'utf8') <= MAX_TEXT_SIZE, {
    message: `Text file must be under ${MAX_TEXT_SIZE / (1024 * 1024)} MB`,
  }),
  isText: z.literal(true).default(true),
});

export const FileAttachmentSchema = z.discriminatedUnion('isText', [
  ImageAttachmentSchema.extend({ isText: z.literal(false) }),
  TextAttachmentSchema.extend({ isText: z.literal(true) }),
]);

// ============================================================================
// Task Schemas (Edit Mode)
// ============================================================================

export const TaskCreateSchema = z.object({
  title: z.string().min(1).max(200),
  description: z.string().max(5000).default(''),
  priority: z.number().int().min(0).max(4).default(2),
  task_type: z.enum(['feature', 'task', 'bug']).default('feature'),
});

export const TaskUpdateSchema = z.object({
  status: z.enum(['open', 'in_progress', 'closed']).nullable().optional(),
  priority: z.number().int().min(0).max(4).nullable().optional(),
  title: z.string().min(1).max(200).nullable().optional(),
});

// ============================================================================
// Remote Machine Schemas
// ============================================================================

export const RemoteMachineCreateSchema = z.object({
  name: z.string().min(1).max(100),
  host: z.string().min(1).max(255),
  port: z.number().int().min(1).max(65535).default(22),
  username: z.string().min(1).max(100).default('root'),
  ssh_key_path: z.string().max(500).nullable().optional(),
  git_ssh_key_path: z.string().max(500).nullable().optional(), // Path to SSH key for git clone on remote
});

export const RemoteMachineResponseSchema = z.object({
  id: z.number().int(),
  name: z.string(),
  host: z.string(),
  port: z.number().int(),
  username: z.string(),
  ssh_key_path: z.string().nullable().optional(),
  git_ssh_key_path: z.string().nullable().optional(),
  status: z.string(),
  last_checked_at: z.string().nullable().optional(),
  created_at: z.string().nullable().optional(),
  // Daemon fields
  daemon_port: z.number().int().nullable().optional(),
  daemon_pid: z.number().int().nullable().optional(),
  daemon_last_seen: z.string().nullable().optional(),
});

export const RemoteAgentStartRequestSchema = z.object({
  machine_id: z.number().int(),
});

export const RemoteAgentStatusResponseSchema = z.object({
  id: z.number().int(),
  project_name: z.string(),
  machine_id: z.number().int(),
  machine_name: z.string(),
  agent_number: z.number().int(),
  status: z.string(),
  current_feature: z.string().nullable().optional(),
  pid: z.number().int().nullable().optional(),
  graceful_stop_requested: z.boolean(),
  restarting: z.boolean(),
  last_activity_at: z.string().nullable().optional(),
});

// ============================================================================
// Inferred Types (types not defined in types.ts)
// ============================================================================

// These types are only exported from schemas because they're not in types.ts
export type ProjectCreate = z.infer<typeof ProjectCreateSchema>;
export type ProjectSettingsUpdate = z.infer<typeof ProjectSettingsUpdateSchema>;
export type ProjectPromptsUpdate = z.infer<typeof ProjectPromptsUpdateSchema>;
export type AddExistingRepoRequest = z.infer<typeof AddExistingRepoRequestSchema>;
export type ContainerCountUpdate = z.infer<typeof ContainerCountUpdateSchema>;
export type ContainerStatus = z.infer<typeof ContainerStatusSchema>;
export type FeatureBase = z.infer<typeof FeatureBaseSchema>;
export type FeatureUpdate = z.infer<typeof FeatureUpdateSchema>;
export type FeatureResponse = z.infer<typeof FeatureResponseSchema>;
export type AgentStatusType = z.infer<typeof AgentStatusTypeSchema>;
export type AgentStartRequest = z.infer<typeof AgentStartRequestSchema>;
export type TaskCreate = z.infer<typeof TaskCreateSchema>;
export type TaskUpdate = z.infer<typeof TaskUpdateSchema>;
export type RemoteMachineResponse = z.infer<typeof RemoteMachineResponseSchema>;
export type RemoteAgentStartRequest = z.infer<typeof RemoteAgentStartRequestSchema>;
export type RemoteAgentStatusResponse = z.infer<typeof RemoteAgentStatusResponseSchema>;
