/**
 * Services Index
 * ==============
 *
 * Re-exports all service modules for convenient imports.
 */

export * from './beads-manager.js';
export * from './container-manager.js';
export * from './agent-executor.js';
export * from './log-streamer.js';
export * from './local-project-manager.js';
export * from './task-cleanup.js';
export * from './branch-cleanup.js';
export {
  RemoteMachineManager,
  getOrCreateRemoteManager,
  getExistingRemoteManager,
  getAllRemoteManagers,
  clearRemoteManager,
  cleanupAllRemoteManagers,
  type RemoteAgentStatus,
  type RemoteOutputCallback,
  type RemoteStatusCallback,
} from './remote-machine-manager.js';
export {
  SpecChatSession,
  createSession,
  getSession,
  listSessions,
  removeSession,
  cleanupAllSessions,
  type MessageChunk,
} from './spec-chat-session.js';

// Assistant chat exports
export {
  AssistantChatSession,
  createSession as createAssistantSession,
  getSession as getAssistantSession,
  listSessions as listAssistantSessions,
  removeSession as removeAssistantSession,
  cleanupAllSessions as cleanupAllAssistantSessions,
  type MessageChunk as AssistantMessageChunk,
} from './assistant-chat-session.js';

// Assistant database exports
export {
  createConversation,
  getConversation,
  getConversations,
  deleteConversation,
  addMessage,
  getMessages,
  listConversations,
  type Conversation,
  type ConversationMessage,
  type ConversationSummary,
  type ConversationDetail,
  type ConversationMessageModel,
} from './assistant-database.js';
