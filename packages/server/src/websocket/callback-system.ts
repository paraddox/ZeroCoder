/**
 * Callback System for Output/Status Streaming
 * ============================================
 *
 * Provides a reusable callback infrastructure for streaming agent output
 * and status changes to WebSocket clients.
 *
 * Features:
 * - Async callback registration and execution
 * - Message queuing for reliability
 * - Connection recovery support
 * - Broadcast filtering
 * - Error isolation (one failing callback doesn't affect others)
 *
 * Converted from server/services/container_manager.py callback system.
 */

import type { AgentStatus } from '@zerocoder/shared';

/**
 * Output callback function type.
 * Receives a line of output from the agent.
 */
export type OutputCallback = (line: string) => Promise<void>;

/**
 * Status callback function type.
 * Receives the new status when agent status changes.
 */
export type StatusCallback = (status: string) => Promise<void>;

/**
 * Generic callback function type.
 */
export type GenericCallback<T> = (data: T) => Promise<void>;

/**
 * Message types for the queue.
 */
export type QueuedMessageType = 'output' | 'status';

/**
 * Queued message structure.
 */
export interface QueuedMessage {
  type: QueuedMessageType;
  data: string;
  timestamp: number;
  id: number;
}

/**
 * Callback registration with optional filter.
 */
interface CallbackRegistration<T> {
  callback: GenericCallback<T>;
  filter?: (data: T) => boolean;
}

/**
 * Logger interface.
 */
const logger = {
  warning: (msg: string) => console.warn(`[CallbackSystem] ${msg}`),
  debug: (msg: string) => console.debug(`[CallbackSystem] ${msg}`),
};

/**
 * Configuration options for CallbackManager.
 */
export interface CallbackManagerOptions {
  /**
   * Maximum number of messages to keep in history for recovery.
   * Default: 1000
   */
  maxHistorySize?: number;

  /**
   * How long to keep messages in history (ms).
   * Default: 5 minutes (300000ms)
   */
  historyRetentionMs?: number;

  /**
   * Timeout for individual callback execution (ms).
   * Default: 5000ms
   */
  callbackTimeoutMs?: number;
}

/**
 * Manages callbacks for streaming output and status changes.
 *
 * This class provides a thread-safe way to register callbacks and
 * broadcast messages to them. It includes features for:
 * - Message queuing and history for connection recovery
 * - Broadcast filtering for selective notifications
 * - Error isolation between callbacks
 *
 * @example
 * ```typescript
 * const callbacks = new CallbackManager();
 *
 * // Register callbacks
 * callbacks.addOutputCallback(async (line) => {
 *   await ws.send(JSON.stringify({ type: 'log', line }));
 * });
 *
 * // Broadcast output
 * await callbacks.broadcastOutput('Agent started...');
 * ```
 */
export class CallbackManager {
  private outputCallbacks: Set<CallbackRegistration<string>> = new Set();
  private statusCallbacks: Set<CallbackRegistration<string>> = new Set();

  /**
   * Message history for connection recovery.
   * Stores recent messages that can be replayed to reconnecting clients.
   */
  private messageHistory: QueuedMessage[] = [];
  private messageIdCounter = 0;

  private readonly maxHistorySize: number;
  private readonly historyRetentionMs: number;
  private readonly callbackTimeoutMs: number;

  /**
   * Current status for new subscribers.
   */
  private currentStatus: string = 'not_created';

  constructor(options: CallbackManagerOptions = {}) {
    this.maxHistorySize = options.maxHistorySize ?? 1000;
    this.historyRetentionMs = options.historyRetentionMs ?? 300000; // 5 minutes
    this.callbackTimeoutMs = options.callbackTimeoutMs ?? 5000;
  }

  // ============================================================================
  // Output Callbacks
  // ============================================================================

  /**
   * Add a callback for output lines.
   *
   * @param callback - Function to call with each output line
   * @param filter - Optional filter function to selectively receive messages
   */
  addOutputCallback(
    callback: OutputCallback,
    filter?: (line: string) => boolean
  ): void {
    this.outputCallbacks.add({ callback, filter });
  }

  /**
   * Remove an output callback.
   *
   * @param callback - The callback function to remove
   */
  removeOutputCallback(callback: OutputCallback): void {
    for (const registration of this.outputCallbacks) {
      if (registration.callback === callback) {
        this.outputCallbacks.delete(registration);
        break;
      }
    }
  }

  /**
   * Broadcast an output line to all registered callbacks.
   * Errors in individual callbacks are caught and logged.
   *
   * @param line - The output line to broadcast
   */
  async broadcastOutput(line: string): Promise<void> {
    // Add to history
    this.addToHistory('output', line);

    // Get callbacks snapshot
    const callbacks = Array.from(this.outputCallbacks);

    // Execute all callbacks concurrently
    await Promise.allSettled(
      callbacks.map(async ({ callback, filter }) => {
        // Apply filter if present
        if (filter && !filter(line)) {
          return;
        }
        await this.safeCallback(callback, line);
      })
    );
  }

  // ============================================================================
  // Status Callbacks
  // ============================================================================

  /**
   * Add a callback for status changes.
   *
   * @param callback - Function to call when status changes
   * @param filter - Optional filter function to selectively receive status updates
   */
  addStatusCallback(
    callback: StatusCallback,
    filter?: (status: string) => boolean
  ): void {
    this.statusCallbacks.add({ callback, filter });
  }

  /**
   * Remove a status callback.
   *
   * @param callback - The callback function to remove
   */
  removeStatusCallback(callback: StatusCallback): void {
    for (const registration of this.statusCallbacks) {
      if (registration.callback === callback) {
        this.statusCallbacks.delete(registration);
        break;
      }
    }
  }

  /**
   * Notify all registered callbacks of a status change.
   * This method fires and forgets - it schedules callbacks but doesn't wait.
   *
   * @param status - The new status
   */
  notifyStatusChange(status: string): void {
    this.currentStatus = status;

    // Add to history
    this.addToHistory('status', status);

    // Get callbacks snapshot
    const callbacks = Array.from(this.statusCallbacks);

    // Fire callbacks without waiting
    for (const { callback, filter } of callbacks) {
      // Apply filter if present
      if (filter && !filter(status)) {
        continue;
      }
      // Schedule callback execution
      this.safeCallback(callback, status).catch(() => {
        // Error already logged in safeCallback
      });
    }
  }

  /**
   * Broadcast a status change and wait for all callbacks to complete.
   *
   * @param status - The new status
   */
  async broadcastStatus(status: string): Promise<void> {
    this.currentStatus = status;

    // Add to history
    this.addToHistory('status', status);

    // Get callbacks snapshot
    const callbacks = Array.from(this.statusCallbacks);

    // Execute all callbacks concurrently
    await Promise.allSettled(
      callbacks.map(async ({ callback, filter }) => {
        // Apply filter if present
        if (filter && !filter(status)) {
          return;
        }
        await this.safeCallback(callback, status);
      })
    );
  }

  // ============================================================================
  // Message History & Recovery
  // ============================================================================

  /**
   * Add a message to history.
   */
  private addToHistory(type: QueuedMessageType, data: string): void {
    const message: QueuedMessage = {
      type,
      data,
      timestamp: Date.now(),
      id: ++this.messageIdCounter,
    };

    this.messageHistory.push(message);

    // Trim history if needed
    this.pruneHistory();
  }

  /**
   * Remove old messages from history.
   */
  private pruneHistory(): void {
    const now = Date.now();
    const cutoff = now - this.historyRetentionMs;

    // Remove old messages
    let oldest = this.messageHistory[0];
    while (oldest && oldest.timestamp < cutoff) {
      this.messageHistory.shift();
      oldest = this.messageHistory[0];
    }

    // Trim to max size
    while (this.messageHistory.length > this.maxHistorySize) {
      this.messageHistory.shift();
    }
  }

  /**
   * Get messages since a given message ID for connection recovery.
   * Returns all messages if lastMessageId is 0 or not found.
   *
   * @param lastMessageId - The last message ID the client received
   * @returns Array of messages since that ID
   */
  getMessagesSince(lastMessageId: number): QueuedMessage[] {
    if (lastMessageId <= 0) {
      return [...this.messageHistory];
    }

    const index = this.messageHistory.findIndex((m) => m.id === lastMessageId);
    if (index === -1) {
      // Message not found - client too far behind, return all
      return [...this.messageHistory];
    }

    // Return messages after the found one
    return this.messageHistory.slice(index + 1);
  }

  /**
   * Get the current status.
   */
  getCurrentStatus(): string {
    return this.currentStatus;
  }

  /**
   * Set the current status without notifying callbacks.
   * Useful for initialization.
   */
  setCurrentStatus(status: string): void {
    this.currentStatus = status;
  }

  /**
   * Get the number of registered output callbacks.
   */
  getOutputCallbackCount(): number {
    return this.outputCallbacks.size;
  }

  /**
   * Get the number of registered status callbacks.
   */
  getStatusCallbackCount(): number {
    return this.statusCallbacks.size;
  }

  /**
   * Get the current history size.
   */
  getHistorySize(): number {
    return this.messageHistory.length;
  }

  /**
   * Clear all callbacks and history.
   */
  clear(): void {
    this.outputCallbacks.clear();
    this.statusCallbacks.clear();
    this.messageHistory = [];
  }

  // ============================================================================
  // Internal Helpers
  // ============================================================================

  /**
   * Safely execute a callback with timeout and error handling.
   */
  private async safeCallback<T>(
    callback: GenericCallback<T>,
    data: T
  ): Promise<void> {
    try {
      // Create timeout promise
      const timeoutPromise = new Promise<never>((_, reject) => {
        setTimeout(
          () => reject(new Error('Callback timeout')),
          this.callbackTimeoutMs
        );
      });

      // Race callback against timeout
      await Promise.race([callback(data), timeoutPromise]);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      logger.warning(`Callback error: ${message}`);
    }
  }
}

/**
 * Mixin interface for classes that support callbacks.
 * Implement this interface to provide callback functionality.
 */
export interface CallbackSupport {
  addOutputCallback(callback: OutputCallback): void;
  removeOutputCallback(callback: OutputCallback): void;
  addStatusCallback(callback: StatusCallback): void;
  removeStatusCallback(callback: StatusCallback): void;
}

/**
 * Create a CallbackManager with container-appropriate defaults.
 */
export function createContainerCallbackManager(): CallbackManager {
  return new CallbackManager({
    maxHistorySize: 500,
    historyRetentionMs: 60000, // 1 minute
    callbackTimeoutMs: 5000,
  });
}

/**
 * Broadcast filter that only passes certain status values.
 */
export function createStatusFilter(
  allowedStatuses: AgentStatus[]
): (status: string) => boolean {
  const statusSet = new Set(allowedStatuses);
  return (status: string) => statusSet.has(status as AgentStatus);
}

/**
 * Broadcast filter that filters output lines by pattern.
 */
export function createOutputFilter(
  pattern: RegExp
): (line: string) => boolean {
  return (line: string) => pattern.test(line);
}
