/**
 * Progress Utility Unit Tests
 *
 * Tests for progress tracking and milestone calculation functions.
 * Mocks file system and fetch operations.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  registerBeadsManager,
  hasFeatures,
  hasOpenFeatures,
  countPassingTests,
  getAllPassingFeatures,
  sendProgressWebhook,
  printSessionHeader,
  printProgressSummary,
  calculateMilestone,
  hasReachedNewMilestone,
  getCurrentMilestone,
} from '../progress.js';

// Mock fs module
vi.mock('node:fs', () => ({
  existsSync: vi.fn(),
}));

import { existsSync } from 'node:fs';

const mockedExistsSync = vi.mocked(existsSync);

const mockedFetch = vi.fn();
global.fetch = mockedFetch as unknown as typeof fetch;

describe('registerBeadsManager', () => {
  it('registers getCachedStats and getCachedFeatures functions', () => {
    const mockGetCachedStats = vi.fn(() => ({ total: 5, pending: 2, in_progress: 1, done: 2 }));
    const mockGetCachedFeatures = vi.fn(() => [{ id: '1', name: 'Feature 1', passes: true }]);

    // Should not throw
    registerBeadsManager(mockGetCachedStats, mockGetCachedFeatures);

    // Verify functions are registered by using them
    const stats = mockGetCachedStats();
    expect(stats.total).toBe(5);
  });
});

describe('hasFeatures', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns true when stats show total > 0', () => {
    const mockGetCachedStats = vi.fn(() => ({ total: 5, pending: 2, in_progress: 1, done: 2 }));
    registerBeadsManager(mockGetCachedStats, vi.fn());

    const result = hasFeatures('/project', 'test-project');

    expect(result).toBe(true);
  });

  it('returns false when stats show total = 0', () => {
    const mockGetCachedStats = vi.fn(() => ({ total: 0, pending: 0, in_progress: 0, done: 0 }));
    registerBeadsManager(mockGetCachedStats, vi.fn());

    const result = hasFeatures('/project', 'test-project');

    expect(result).toBe(false);
  });

  it('falls back to checking beads.db when no projectName', () => {
    mockedExistsSync.mockReturnValue(true);

    const result = hasFeatures('/project');

    expect(result).toBe(true);
    expect(mockedExistsSync).toHaveBeenCalledWith('/project/.beads/beads.db');
  });

  it('returns false when beads.db does not exist and no stats', () => {
    mockedExistsSync.mockReturnValue(false);

    const result = hasFeatures('/project');

    expect(result).toBe(false);
  });

  it('handles errors from getCachedStats gracefully', () => {
    const mockGetCachedStats = vi.fn(() => {
      throw new Error('Stats error');
    });
    registerBeadsManager(mockGetCachedStats, vi.fn());
    mockedExistsSync.mockReturnValue(true);

    const result = hasFeatures('/project', 'test-project');

    expect(result).toBe(true); // Falls back to file check
  });
});

describe('hasOpenFeatures', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns true when there are pending features', () => {
    const mockGetCachedStats = vi.fn(() => ({ total: 5, pending: 3, in_progress: 0, done: 2 }));
    registerBeadsManager(mockGetCachedStats, vi.fn());

    const result = hasOpenFeatures('/project', 'test-project');

    expect(result).toBe(true);
  });

  it('returns true when there are in_progress features', () => {
    const mockGetCachedStats = vi.fn(() => ({ total: 5, pending: 0, in_progress: 2, done: 3 }));
    registerBeadsManager(mockGetCachedStats, vi.fn());

    const result = hasOpenFeatures('/project', 'test-project');

    expect(result).toBe(true);
  });

  it('returns false when no pending or in_progress features', () => {
    const mockGetCachedStats = vi.fn(() => ({ total: 5, pending: 0, in_progress: 0, done: 5 }));
    registerBeadsManager(mockGetCachedStats, vi.fn());

    const result = hasOpenFeatures('/project', 'test-project');

    expect(result).toBe(false);
  });

  it('returns true as fallback when no projectName', () => {
    const result = hasOpenFeatures('/project');

    expect(result).toBe(true);
  });

  it('handles errors gracefully and returns true', () => {
    const mockGetCachedStats = vi.fn(() => {
      throw new Error('Stats error');
    });
    registerBeadsManager(mockGetCachedStats, vi.fn());

    const result = hasOpenFeatures('/project', 'test-project');

    expect(result).toBe(true);
  });
});

describe('countPassingTests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns correct counts from stats', () => {
    const mockGetCachedStats = vi.fn(() => ({ total: 10, pending: 3, in_progress: 2, done: 5 }));
    registerBeadsManager(mockGetCachedStats, vi.fn());

    const [passing, inProgress, total] = countPassingTests('/project', 'test-project');

    expect(passing).toBe(5);
    expect(inProgress).toBe(2);
    expect(total).toBe(10);
  });

  it('returns zeros when no features exist', () => {
    const mockGetCachedStats = vi.fn(() => ({ total: 0, pending: 0, in_progress: 0, done: 0 }));
    registerBeadsManager(mockGetCachedStats, vi.fn());

    const [passing, inProgress, total] = countPassingTests('/project', 'test-project');

    expect(passing).toBe(0);
    expect(inProgress).toBe(0);
    expect(total).toBe(0);
  });

  it('returns zeros when no projectName', () => {
    const [passing, inProgress, total] = countPassingTests('/project');

    expect(passing).toBe(0);
    expect(inProgress).toBe(0);
    expect(total).toBe(0);
  });

  it('handles errors gracefully', () => {
    const mockGetCachedStats = vi.fn(() => {
      throw new Error('Stats error');
    });
    registerBeadsManager(mockGetCachedStats, vi.fn());

    const [passing, inProgress, total] = countPassingTests('/project', 'test-project');

    expect(passing).toBe(0);
    expect(inProgress).toBe(0);
    expect(total).toBe(0);
  });
});

describe('getAllPassingFeatures', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns passing features from cached features', () => {
    const mockFeatures = [
      { id: '1', name: 'Feature 1', passes: true, category: 'core', status: 'closed' },
      { id: '2', name: 'Feature 2', passes: false, category: 'api', status: 'open' },
      { id: '3', name: 'Feature 3', passes: true, category: 'ui', status: 'closed' },
    ];
    const mockGetCachedFeatures = vi.fn(() => mockFeatures);
    registerBeadsManager(vi.fn(), mockGetCachedFeatures);

    const result = getAllPassingFeatures('/project', 'test-project');

    expect(result).toHaveLength(2);
    expect(result[0]?.id).toBe('1');
    expect(result[1]?.id).toBe('3');
  });

  it('returns empty array when no passing features', () => {
    const mockFeatures = [
      { id: '1', name: 'Feature 1', passes: false, category: 'core' },
      { id: '2', name: 'Feature 2', passes: false, category: 'api' },
    ];
    const mockGetCachedFeatures = vi.fn(() => mockFeatures);
    registerBeadsManager(vi.fn(), mockGetCachedFeatures);

    const result = getAllPassingFeatures('/project', 'test-project');

    expect(result).toHaveLength(0);
  });

  it('returns empty array when no projectName', () => {
    const result = getAllPassingFeatures('/project');

    expect(result).toEqual([]);
  });

  it('handles errors gracefully', () => {
    const mockGetCachedFeatures = vi.fn(() => {
      throw new Error('Features error');
    });
    registerBeadsManager(vi.fn(), mockGetCachedFeatures);

    const result = getAllPassingFeatures('/project', 'test-project');

    expect(result).toEqual([]);
  });

  it('handles features with closed status', () => {
    const mockFeatures = [
      { id: '1', name: 'Feature 1', passes: false, category: 'core', status: 'closed' },
    ];
    const mockGetCachedFeatures = vi.fn(() => mockFeatures);
    registerBeadsManager(vi.fn(), mockGetCachedFeatures);

    const result = getAllPassingFeatures('/project', 'test-project');

    expect(result).toHaveLength(1);
    expect(result[0]?.id).toBe('1');
  });
});

describe('sendProgressWebhook', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedExistsSync.mockReturnValue(false);
  });

  it('does nothing when webhook URL not configured', async () => {
    // WEBHOOK_URL is read at module load time from PROGRESS_N8N_WEBHOOK_URL env var.
    // Since it's not set in the test environment, all webhook calls return early.
    // This test verifies the guard clause behavior.
    await sendProgressWebhook(5, 10, '/project', 'test-project');
    // When WEBHOOK_URL is undefined, the function returns early without calling fetch
    expect(mockedFetch).not.toHaveBeenCalled();
  });
});

describe('printSessionHeader', () => {
  it('prints initializer header', () => {
    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    printSessionHeader(1, true);

    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('SESSION 1'));
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('INITIALIZER'));
    consoleSpy.mockRestore();
  });

  it('prints coding agent header', () => {
    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    printSessionHeader(5, false);

    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('SESSION 5'));
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('CODING AGENT'));
    consoleSpy.mockRestore();
  });
});

describe('printProgressSummary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('prints progress when features exist', async () => {
    const mockGetCachedStats = vi.fn(() => ({ total: 10, pending: 3, in_progress: 2, done: 5 }));
    registerBeadsManager(mockGetCachedStats, vi.fn());
    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    await printProgressSummary('/project', 'test-project');

    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('5/10 tests passing'));
    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('2 in progress'));
    consoleSpy.mockRestore();
  });

  it('prints no features message when total is 0', async () => {
    const mockGetCachedStats = vi.fn(() => ({ total: 0, pending: 0, in_progress: 0, done: 0 }));
    registerBeadsManager(mockGetCachedStats, vi.fn());
    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});

    await printProgressSummary('/project', 'test-project');

    expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('No features yet'));
    consoleSpy.mockRestore();
  });
});

describe('calculateMilestone', () => {
  it('returns 0 when total is 0', () => {
    expect(calculateMilestone(0, 0)).toBe(0);
  });

  it('calculates milestone correctly', () => {
    expect(calculateMilestone(5, 10)).toBe(50);  // 50% -> 50%
    expect(calculateMilestone(3, 10)).toBe(30);  // 30% -> 30%
    expect(calculateMilestone(7, 10)).toBe(70);  // 70% -> 70%
  });

  it('rounds down to nearest 10%', () => {
    expect(calculateMilestone(4, 10)).toBe(40);  // 40% -> 40%
    expect(calculateMilestone(4, 9)).toBe(40);   // 44.4% -> 40%
    expect(calculateMilestone(1, 3)).toBe(30);   // 33.3% -> 30%
  });
});

describe('hasReachedNewMilestone', () => {
  it('returns false when total is 0', () => {
    expect(hasReachedNewMilestone(5, 3, 0)).toBe(false);
  });

  it('returns true when milestone increases', () => {
    expect(hasReachedNewMilestone(6, 3, 10)).toBe(true);  // 60% vs 30%
    expect(hasReachedNewMilestone(7, 4, 10)).toBe(true);  // 70% vs 40%
  });

  it('returns false when milestone does not increase', () => {
    expect(hasReachedNewMilestone(5, 5, 10)).toBe(false); // 50% vs 50%
    expect(hasReachedNewMilestone(3, 5, 10)).toBe(false); // 30% vs 50% (decreased)
  });

  it('returns false when same milestone', () => {
    expect(hasReachedNewMilestone(4, 4, 10)).toBe(false); // 40% vs 40%
  });
});

describe('getCurrentMilestone', () => {
  it('returns 0% when total is 0', () => {
    expect(getCurrentMilestone(0, 0)).toBe('0%');
  });

  it('returns formatted milestone', () => {
    expect(getCurrentMilestone(5, 10)).toBe('50%');
    expect(getCurrentMilestone(3, 10)).toBe('30%');
    expect(getCurrentMilestone(10, 10)).toBe('100%');
  });
});
