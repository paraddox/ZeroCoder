/**
 * WebSocket Module
 * ================
 *
 * Exports WebSocket connection management, handlers, and callback system.
 */

export { ConnectionManager, manager, validateProjectName } from './connection-manager.js';
export {
  handleProjectWebSocket,
  extractProjectName,
  isProjectWebSocketRequest,
} from './project-socket.js';
export {
  CallbackManager,
  createContainerCallbackManager,
  createStatusFilter,
  createOutputFilter,
  type OutputCallback,
  type StatusCallback,
  type CallbackSupport,
  type QueuedMessage,
  type CallbackManagerOptions,
} from './callback-system.js';
