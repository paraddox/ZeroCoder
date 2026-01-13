/**
 * TypeScript types for the Autonomous Coding UI
 */

// Project types
export interface ProjectStats {
  passing: number
  in_progress: number
  total: number
  percentage: number
}

export interface ProjectSummary {
  name: string
  path: string
  has_spec: boolean
  wizard_incomplete: boolean
  stats: ProjectStats
  agent_status?: AgentStatus
  agent_running?: boolean
}

export interface ProjectDetail extends ProjectSummary {
  prompts_dir: string
}

// Filesystem types
export interface DriveInfo {
  letter: string
  label: string
  available?: boolean
}

export interface DirectoryEntry {
  name: string
  path: string
  is_directory: boolean
  has_children: boolean
}

export interface DirectoryListResponse {
  current_path: string
  parent_path: string | null
  entries: DirectoryEntry[]
  drives: DriveInfo[] | null
}

export interface PathValidationResponse {
  valid: boolean
  exists: boolean
  is_directory: boolean
  can_write: boolean
  message: string
}

export interface ProjectPrompts {
  app_spec: string
  initializer_prompt: string
  coding_prompt: string
}

// Wizard status types
export interface WizardStatusMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
}

export type WizardStep = 'name' | 'folder' | 'method' | 'chat'
export type SpecMethod = 'claude' | 'manual'

export interface WizardStatus {
  step: WizardStep
  spec_method: SpecMethod | null
  started_at: string
  chat_messages: WizardStatusMessage[]
}

// Feature types
export interface Feature {
  id: string  // beads uses string IDs like "feat-1"
  priority: number
  category: string
  name: string
  description: string
  steps: string[]
  passes: boolean
  in_progress: boolean
}

export interface FeatureListResponse {
  pending: Feature[]
  in_progress: Feature[]
  done: Feature[]
}

export interface FeatureCreate {
  category: string
  name: string
  description: string
  steps: string[]
  priority?: number
}

// Agent types
export type AgentStatus = 'not_created' | 'stopped' | 'running' | 'crashed'

export interface AgentStatusResponse {
  status: AgentStatus
  container_name: string | null
  pid: number | null
  started_at: string | null
  idle_seconds: number
  yolo_mode: boolean
  agent_running: boolean
}

export interface AgentActionResponse {
  success: boolean
  status: AgentStatus
  message: string
}

// Setup types
export interface SetupStatus {
  claude_cli: boolean
  credentials: boolean
  node: boolean
  npm: boolean
}

// WebSocket message types
export type WSMessageType = 'progress' | 'feature_update' | 'log' | 'agent_status' | 'pong'

export interface WSProgressMessage {
  type: 'progress'
  passing: number
  in_progress: number
  total: number
  percentage: number
}

export interface WSFeatureUpdateMessage {
  type: 'feature_update'
  feature_id: string  // beads uses string IDs
  passes: boolean
}

export interface WSLogMessage {
  type: 'log'
  line: string
  timestamp: string
}

export interface WSAgentStatusMessage {
  type: 'agent_status'
  status: AgentStatus
}

export interface WSPongMessage {
  type: 'pong'
}

export type WSMessage =
  | WSProgressMessage
  | WSFeatureUpdateMessage
  | WSLogMessage
  | WSAgentStatusMessage
  | WSPongMessage

// ============================================================================
// Spec Chat Types
// ============================================================================

export interface SpecQuestionOption {
  label: string
  description: string
}

export interface SpecQuestion {
  question: string
  header: string
  options: SpecQuestionOption[]
  multiSelect: boolean
}

export interface SpecChatTextMessage {
  type: 'text'
  content: string
}

export interface SpecChatQuestionMessage {
  type: 'question'
  questions: SpecQuestion[]
  tool_id?: string
}

export interface SpecChatCompleteMessage {
  type: 'spec_complete'
  path: string
}

export interface SpecChatFileWrittenMessage {
  type: 'file_written'
  path: string
}

export interface SpecChatSessionCompleteMessage {
  type: 'complete'
}

export interface SpecChatErrorMessage {
  type: 'error'
  content: string
}

export interface SpecChatPongMessage {
  type: 'pong'
}

export interface SpecChatResponseDoneMessage {
  type: 'response_done'
}

export type SpecChatServerMessage =
  | SpecChatTextMessage
  | SpecChatQuestionMessage
  | SpecChatCompleteMessage
  | SpecChatFileWrittenMessage
  | SpecChatSessionCompleteMessage
  | SpecChatErrorMessage
  | SpecChatPongMessage
  | SpecChatResponseDoneMessage

// File attachment types
export type ImageMimeType = 'image/jpeg' | 'image/png'
export type TextMimeType = 'text/plain' | 'text/markdown' | 'text/csv' | 'application/json' | 'text/html' | 'text/css' | 'text/javascript' | 'application/xml'
export type AttachmentMimeType = ImageMimeType | TextMimeType

// Image attachment for chat messages
export interface ImageAttachment {
  id: string
  filename: string
  mimeType: ImageMimeType
  base64Data: string    // Raw base64 (without data: prefix)
  previewUrl: string    // data: URL for display
  size: number          // File size in bytes
  isText?: false        // Type discriminator
}

// Text file attachment for chat messages
export interface TextAttachment {
  id: string
  filename: string
  mimeType: TextMimeType
  textContent: string   // Raw text content
  size: number          // File size in bytes
  isText: true          // Type discriminator
}

// Union type for any attachment
export type FileAttachment = ImageAttachment | TextAttachment

// UI chat message for display
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  attachments?: FileAttachment[]
  timestamp: Date
  questions?: SpecQuestion[]
  isStreaming?: boolean
}

// ============================================================================
// Assistant Chat Types
// ============================================================================

export interface AssistantConversation {
  id: number
  project_name: string
  title: string | null
  created_at: string | null
  updated_at: string | null
  message_count: number
}

export interface AssistantMessage {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string | null
}

export interface AssistantConversationDetail {
  id: number
  project_name: string
  title: string | null
  created_at: string | null
  updated_at: string | null
  messages: AssistantMessage[]
}

export interface AssistantChatTextMessage {
  type: 'text'
  content: string
}

export interface AssistantChatToolCallMessage {
  type: 'tool_call'
  tool: string
  input: Record<string, unknown>
}

export interface AssistantChatResponseDoneMessage {
  type: 'response_done'
}

export interface AssistantChatErrorMessage {
  type: 'error'
  content: string
}

export interface AssistantChatConversationCreatedMessage {
  type: 'conversation_created'
  conversation_id: number
}

export interface AssistantChatPongMessage {
  type: 'pong'
}

export interface AssistantChatIssueCreatedMessage {
  type: 'issue_created'
  id: string
  title: string
}

export type AssistantChatServerMessage =
  | AssistantChatTextMessage
  | AssistantChatToolCallMessage
  | AssistantChatResponseDoneMessage
  | AssistantChatErrorMessage
  | AssistantChatConversationCreatedMessage
  | AssistantChatPongMessage
  | AssistantChatIssueCreatedMessage
