/**
 * Callback System Tests
 *
 * Tests for message queuing, callback registration, history tracking,
 * and connection recovery support.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  CallbackManager,
  createContainerCallbackManager,
  createStatusFilter,
  createOutputFilter,
  type OutputCallback,
  type StatusCallback,
} from '../callback-system.js';

// =============================================================================
// Tests: CallbackManager - Output Callbacks
// =============================================================================

describe('CallbackManager - Output Callbacks', () => {
  let manager: CallbackManager;

  beforeEach(() => {
    manager = new CallbackManager();
  });

  afterEach(() => {
    manager.clear();
  });

  it('adds and removes output callbacks', () => {
    const callback: OutputCallback = vi.fn(async () => {});

    manager.addOutputCallback(callback);
    expect(manager.getOutputCallbackCount()).toBe(1);

    manager.removeOutputCallback(callback);
    expect(manager.getOutputCallbackCount()).toBe(0);
  });

  it('broadcasts output to all registered callbacks', async () => {
    const callback1: OutputCallback = vi.fn(async () => {});
    const callback2: OutputCallback = vi.fn(async () => {});

    manager.addOutputCallback(callback1);
    manager.addOutputCallback(callback2);

    await manager.broadcastOutput('Hello, world!');

    expect(callback1).toHaveBeenCalledWith('Hello, world!');
    expect(callback2).toHaveBeenCalledWith('Hello, world!');
  });

  it('supports filters for selective output callbacks', async () => {
    const errorCallback: OutputCallback = vi.fn(async () => {});
    const allCallback: OutputCallback = vi.fn(async () => {});

    manager.addOutputCallback(errorCallback, (line) => line.includes('ERROR'));
    manager.addOutputCallback(allCallback);

    await manager.broadcastOutput('INFO: Starting up');
    await manager.broadcastOutput('ERROR: Something failed');

    expect(allCallback).toHaveBeenCalledTimes(2);
    expect(errorCallback).toHaveBeenCalledTimes(1);
    expect(errorCallback).toHaveBeenCalledWith('ERROR: Something failed');
  });

  it('isolates errors between callbacks', async () => {
    const badCallback: OutputCallback = vi.fn(async () => {
      throw new Error('Callback failed');
    });
    const goodCallback: OutputCallback = vi.fn(async () => {});

    manager.addOutputCallback(badCallback);
    manager.addOutputCallback(goodCallback);

    // Should not throw
    await manager.broadcastOutput('test');

    expect(goodCallback).toHaveBeenCalled();
  });

  it('handles callback timeout', async () => {
    const slowCallback: OutputCallback = vi.fn(async () => {
      // This callback takes too long
      await new Promise((resolve) => setTimeout(resolve, 10000));
    });
    const fastCallback: OutputCallback = vi.fn(async () => {});

    const shortTimeoutManager = new CallbackManager({
      callbackTimeoutMs: 100,
    });

    shortTimeoutManager.addOutputCallback(slowCallback);
    shortTimeoutManager.addOutputCallback(fastCallback);

    // Should complete without hanging
    await shortTimeoutManager.broadcastOutput('test');

    expect(fastCallback).toHaveBeenCalled();
  });
});

// =============================================================================
// Tests: CallbackManager - Status Callbacks
// =============================================================================

describe('CallbackManager - Status Callbacks', () => {
  let manager: CallbackManager;

  beforeEach(() => {
    manager = new CallbackManager();
  });

  afterEach(() => {
    manager.clear();
  });

  it('adds and removes status callbacks', () => {
    const callback: StatusCallback = vi.fn(async () => {});

    manager.addStatusCallback(callback);
    expect(manager.getStatusCallbackCount()).toBe(1);

    manager.removeStatusCallback(callback);
    expect(manager.getStatusCallbackCount()).toBe(0);
  });

  it('notifyStatusChange fires callbacks without waiting', () => {
    const callback: StatusCallback = vi.fn(async () => {});

    manager.addStatusCallback(callback);
    manager.notifyStatusChange('running');

    // Callback should be scheduled (may not have executed yet)
    expect(manager.getCurrentStatus()).toBe('running');
  });

  it('broadcastStatus waits for all callbacks', async () => {
    const results: string[] = [];
    const callback1: StatusCallback = vi.fn(async (status) => {
      results.push(`cb1:${status}`);
    });
    const callback2: StatusCallback = vi.fn(async (status) => {
      results.push(`cb2:${status}`);
    });

    manager.addStatusCallback(callback1);
    manager.addStatusCallback(callback2);

    await manager.broadcastStatus('running');

    expect(results).toContain('cb1:running');
    expect(results).toContain('cb2:running');
  });

  it('supports filters for selective status callbacks', async () => {
    const runningCallback: StatusCallback = vi.fn(async () => {});
    const allCallback: StatusCallback = vi.fn(async () => {});

    manager.addStatusCallback(runningCallback, (s) => s === 'running');
    manager.addStatusCallback(allCallback);

    await manager.broadcastStatus('starting');
    await manager.broadcastStatus('running');
    await manager.broadcastStatus('stopped');

    expect(allCallback).toHaveBeenCalledTimes(3);
    expect(runningCallback).toHaveBeenCalledTimes(1);
  });

  it('updates currentStatus on notifyStatusChange', () => {
    expect(manager.getCurrentStatus()).toBe('not_created');

    manager.notifyStatusChange('running');
    expect(manager.getCurrentStatus()).toBe('running');

    manager.notifyStatusChange('stopped');
    expect(manager.getCurrentStatus()).toBe('stopped');
  });

  it('setCurrentStatus updates without notifying', () => {
    const callback: StatusCallback = vi.fn(async () => {});
    manager.addStatusCallback(callback);

    manager.setCurrentStatus('running');

    expect(manager.getCurrentStatus()).toBe('running');
    expect(callback).not.toHaveBeenCalled();
  });
});

// =============================================================================
// Tests: CallbackManager - Message History
// =============================================================================

describe('CallbackManager - Message History', () => {
  let manager: CallbackManager;

  beforeEach(() => {
    manager = new CallbackManager({
      maxHistorySize: 10,
      historyRetentionMs: 60000,
    });
  });

  afterEach(() => {
    manager.clear();
  });

  it('stores output messages in history', async () => {
    await manager.broadcastOutput('line 1');
    await manager.broadcastOutput('line 2');

    expect(manager.getHistorySize()).toBe(2);
  });

  it('stores status messages in history', async () => {
    await manager.broadcastStatus('running');
    await manager.broadcastStatus('stopped');

    expect(manager.getHistorySize()).toBe(2);
  });

  it('getMessagesSince returns all messages when lastMessageId is 0', async () => {
    await manager.broadcastOutput('line 1');
    await manager.broadcastOutput('line 2');
    await manager.broadcastOutput('line 3');

    const messages = manager.getMessagesSince(0);

    expect(messages).toHaveLength(3);
    expect(messages[0]!.data).toBe('line 1');
    expect(messages[1]!.data).toBe('line 2');
    expect(messages[2]!.data).toBe('line 3');
  });

  it('getMessagesSince returns messages after given ID', async () => {
    await manager.broadcastOutput('line 1');
    await manager.broadcastOutput('line 2');
    await manager.broadcastOutput('line 3');

    const allMessages = manager.getMessagesSince(0);
    const firstMessageId = allMessages[0]!.id;

    const messagesAfterFirst = manager.getMessagesSince(firstMessageId);

    expect(messagesAfterFirst).toHaveLength(2);
    expect(messagesAfterFirst[0]!.data).toBe('line 2');
    expect(messagesAfterFirst[1]!.data).toBe('line 3');
  });

  it('getMessagesSince returns all messages when ID not found', async () => {
    await manager.broadcastOutput('line 1');
    await manager.broadcastOutput('line 2');

    const messages = manager.getMessagesSince(99999);

    expect(messages).toHaveLength(2);
  });

  it('prunes history when exceeding maxHistorySize', async () => {
    const smallManager = new CallbackManager({
      maxHistorySize: 3,
      historyRetentionMs: 60000,
    });

    await smallManager.broadcastOutput('line 1');
    await smallManager.broadcastOutput('line 2');
    await smallManager.broadcastOutput('line 3');
    await smallManager.broadcastOutput('line 4');
    await smallManager.broadcastOutput('line 5');

    expect(smallManager.getHistorySize()).toBe(3);

    const messages = smallManager.getMessagesSince(0);
    expect(messages[0]!.data).toBe('line 3');
    expect(messages[2]!.data).toBe('line 5');
  });

  it('messages have correct type field', async () => {
    await manager.broadcastOutput('output line');
    await manager.broadcastStatus('running');

    const messages = manager.getMessagesSince(0);

    expect(messages[0]!.type).toBe('output');
    expect(messages[1]!.type).toBe('status');
  });

  it('messages have incrementing IDs', async () => {
    await manager.broadcastOutput('line 1');
    await manager.broadcastOutput('line 2');
    await manager.broadcastOutput('line 3');

    const messages = manager.getMessagesSince(0);

    expect(messages[1]!.id).toBeGreaterThan(messages[0]!.id);
    expect(messages[2]!.id).toBeGreaterThan(messages[1]!.id);
  });

  it('messages have timestamp', async () => {
    const before = Date.now();
    await manager.broadcastOutput('test');
    const after = Date.now();

    const messages = manager.getMessagesSince(0);

    expect(messages[0]!.timestamp).toBeGreaterThanOrEqual(before);
    expect(messages[0]!.timestamp).toBeLessThanOrEqual(after);
  });
});

// =============================================================================
// Tests: CallbackManager - History Retention
// =============================================================================

describe('CallbackManager - History Retention', () => {
  it('prunes old messages based on retention time', async () => {
    vi.useFakeTimers();

    const manager = new CallbackManager({
      maxHistorySize: 100,
      historyRetentionMs: 1000, // 1 second retention
    });

    await manager.broadcastOutput('old message');

    // Advance time past retention period
    vi.advanceTimersByTime(2000);

    await manager.broadcastOutput('new message');

    const messages = manager.getMessagesSince(0);
    expect(messages).toHaveLength(1);
    expect(messages[0]!.data).toBe('new message');

    vi.useRealTimers();
  });
});

// =============================================================================
// Tests: CallbackManager - Clear
// =============================================================================

describe('CallbackManager - Clear', () => {
  it('clears all callbacks and history', async () => {
    const manager = new CallbackManager();

    manager.addOutputCallback(vi.fn(async () => {}));
    manager.addStatusCallback(vi.fn(async () => {}));
    await manager.broadcastOutput('test');
    await manager.broadcastStatus('running');

    manager.clear();

    expect(manager.getOutputCallbackCount()).toBe(0);
    expect(manager.getStatusCallbackCount()).toBe(0);
    expect(manager.getHistorySize()).toBe(0);
  });
});

// =============================================================================
// Tests: Factory Functions
// =============================================================================

describe('Factory Functions', () => {
  describe('createContainerCallbackManager', () => {
    it('creates manager with container-appropriate defaults', () => {
      const manager = createContainerCallbackManager();

      // Should be able to add callbacks
      manager.addOutputCallback(vi.fn(async () => {}));
      expect(manager.getOutputCallbackCount()).toBe(1);
    });
  });

  describe('createStatusFilter', () => {
    it('creates filter that only passes allowed statuses', () => {
      const filter = createStatusFilter(['running', 'completed']);

      expect(filter('running')).toBe(true);
      expect(filter('completed')).toBe(true);
      expect(filter('stopped')).toBe(false);
      expect(filter('not_created')).toBe(false);
    });
  });

  describe('createOutputFilter', () => {
    it('creates filter that matches pattern', () => {
      const errorFilter = createOutputFilter(/ERROR|WARN/);

      expect(errorFilter('ERROR: Something bad')).toBe(true);
      expect(errorFilter('WARN: Caution')).toBe(true);
      expect(errorFilter('INFO: All good')).toBe(false);
    });
  });
});

// =============================================================================
// Tests: Integration - Connection Recovery Scenario
// =============================================================================

describe('Integration - Connection Recovery', () => {
  it('supports reconnection recovery flow', async () => {
    const manager = new CallbackManager();

    // Initial connection broadcasts some messages
    await manager.broadcastOutput('Starting agent...');
    await manager.broadcastStatus('running');
    await manager.broadcastOutput('Processing feature-1');
    await manager.broadcastOutput('Feature complete');
    await manager.broadcastStatus('completed');

    // Get all messages (simulating new connection)
    const allMessages = manager.getMessagesSince(0);
    expect(allMessages).toHaveLength(5);

    // Client reconnects with last known message ID
    const lastKnownId = allMessages[2]!.id; // After "Processing feature-1"

    const missedMessages = manager.getMessagesSince(lastKnownId);

    expect(missedMessages).toHaveLength(2);
    expect(missedMessages[0]!.data).toBe('Feature complete');
    expect(missedMessages[1]!.data).toBe('completed');
    expect(missedMessages[1]!.type).toBe('status');
  });

  it('provides current status to new connections', () => {
    const manager = new CallbackManager();

    manager.notifyStatusChange('running');

    // New connection can immediately get current status
    expect(manager.getCurrentStatus()).toBe('running');
  });
});

// =============================================================================
// Tests: Edge Cases
// =============================================================================

describe('Edge Cases', () => {
  it('handles removing non-existent callback gracefully', () => {
    const manager = new CallbackManager();
    const callback: OutputCallback = vi.fn(async () => {});

    // Should not throw
    expect(() => manager.removeOutputCallback(callback)).not.toThrow();
    expect(() => manager.removeStatusCallback(callback)).not.toThrow();
  });

  it('handles empty broadcast gracefully', async () => {
    const manager = new CallbackManager();

    // No callbacks registered
    await expect(manager.broadcastOutput('test')).resolves.not.toThrow();
    await expect(manager.broadcastStatus('running')).resolves.not.toThrow();
  });

  it('handles concurrent broadcasts', async () => {
    const manager = new CallbackManager();
    const results: string[] = [];
    const callback: OutputCallback = vi.fn(async (line) => {
      results.push(line);
    });

    manager.addOutputCallback(callback);

    // Fire many broadcasts concurrently
    await Promise.all([
      manager.broadcastOutput('1'),
      manager.broadcastOutput('2'),
      manager.broadcastOutput('3'),
      manager.broadcastOutput('4'),
      manager.broadcastOutput('5'),
    ]);

    expect(results).toHaveLength(5);
  });

  it('handles duplicate callback registration', () => {
    const manager = new CallbackManager();
    const callback: OutputCallback = vi.fn(async () => {});

    manager.addOutputCallback(callback);
    manager.addOutputCallback(callback);

    // Set semantics - should still be 2 separate registrations
    expect(manager.getOutputCallbackCount()).toBe(2);
  });
});
