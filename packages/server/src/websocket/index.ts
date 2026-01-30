/**
 * WebSocket Module
 * ================
 *
 * Exports callback system for container output/status streaming.
 * Note: WebSocket endpoint handlers are not yet implemented.
 */

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
