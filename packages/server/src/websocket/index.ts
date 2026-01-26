/**
 * WebSocket Module
 * ================
 *
 * Exports WebSocket connection management and handlers.
 */

export { ConnectionManager, manager, validateProjectName } from './connection-manager.js';
export {
  handleProjectWebSocket,
  extractProjectName,
  isProjectWebSocketRequest,
} from './project-socket.js';
