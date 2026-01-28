/**
 * Beads Manager Unit Tests
 *
 * Tests for the BeadsManager class and related functions.
 * Mocks file system and child process operations.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import {
  BeadsManager,
  getBeadsManager,
  getBeadsManagerSync,
  clearBeadsManager,
  getCachedStats,
  getCachedFeatures,
  type BeadsTask,
} from '../beads-manager.js';

// Mock dependencies
vi.mock('child_process', () => ({
  exec: vi.fn(),
  execSync: vi.fn(),
}));

vi.mock('fs', () => ({
  existsSync: vi.fn(),
  mkdirSync: vi.fn(),
}));

vi.mock('fs/promises', () => ({
  writeFile: vi.fn(),
}));

vi.mock('proper-lockfile', () => ({
  lock: vi.fn(),
}));

vi.mock('../../db/crud.js', () => ({
  getProjectsDir: vi.fn(() => '/test/projects'),
  getProjectGitUrl: vi.fn(),
  listValidProjects: vi.fn(() => []),
}));

import { exec, execSync } from 'child_process';
import { existsSync } from 'fs';
import * as lockfile from 'proper-lockfile';
import { getProjectsDir, getProjectGitUrl } from '../../db/crud.js';

const mockedExec = vi.mocked(exec);
const mockedExecSync = vi.mocked(execSync);
const mockedExistsSync = vi.mocked(existsSync);
const mockedLockfileLock = vi.mocked(lockfile.lock);
const mockedGetProjectsDir = vi.mocked(getProjectsDir);
const mockedGetProjectGitUrl = vi.mocked(getProjectGitUrl);

describe('BeadsManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Ensure getProjectsDir returns a valid path
    mockedGetProjectsDir.mockReturnValue('/test/projects');
    // Clear the managers cache
    clearBeadsManager('test-project');
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  describe('Constructor', () => {
    it('creates a BeadsManager with correct properties', () => {
      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');

      expect(manager.projectName).toBe('test-project');
      expect(manager.gitRemoteUrl).toBe('https://github.com/test/repo');
      expect(manager.localPath).toBe('/test/projects/test-project');
      expect(manager.lastPull).toBeNull();
    });
  });

  describe('ensureProjectExists', () => {
    it('returns success when project exists with git', async () => {
      mockedExistsSync.mockReturnValue(true);

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const [success, message] = await manager.ensureProjectExists();

      expect(success).toBe(true);
      expect(message).toBe('Project exists');
    });

    it('returns failure when project directory does not exist', async () => {
      mockedExistsSync.mockReturnValue(false);

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const [success, message] = await manager.ensureProjectExists();

      expect(success).toBe(false);
      expect(message).toContain('Project directory not found');
    });

    it('returns failure when git directory does not exist', async () => {
      mockedExistsSync.mockImplementation((path: unknown) => {
        if (typeof path === 'string' && path.includes('.git')) return false;
        return true;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const [success, message] = await manager.ensureProjectExists();

      expect(success).toBe(false);
      expect(message).toContain('Project directory not found');
    });
  });

  describe('getTasks', () => {
    it('returns empty array when project directory does not exist', () => {
      mockedExistsSync.mockReturnValue(false);

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const tasks = manager.getTasks();

      expect(tasks).toEqual([]);
    });

    it('returns empty array when beads directory does not exist', () => {
      mockedExistsSync.mockImplementation((path: unknown) => {
        if (typeof path === 'string' && path.includes('.beads')) return false;
        return true;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const tasks = manager.getTasks();

      expect(tasks).toEqual([]);
    });

    it('returns tasks from bd CLI output', () => {
      const mockTasks: BeadsTask[] = [
        { id: '1', title: 'Task 1', status: 'open', priority: 1, labels: [] },
        { id: '2', title: 'Task 2', status: 'in_progress', priority: 2, labels: ['bug'] },
      ];

      mockedExistsSync.mockReturnValue(true);
      mockedExecSync.mockReturnValue(JSON.stringify(mockTasks));

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const tasks = manager.getTasks();

      expect(tasks).toHaveLength(2);
      expect(tasks[0]?.id).toBe('1');
      expect(tasks[1]?.status).toBe('in_progress');
    });

    it('returns empty array when bd CLI returns empty output', () => {
      mockedExistsSync.mockReturnValue(true);
      mockedExecSync.mockReturnValue('');

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const tasks = manager.getTasks();

      expect(tasks).toEqual([]);
    });

    it('handles out of sync error and recovers', () => {
      const mockTasks: BeadsTask[] = [{ id: '1', title: 'Task 1', status: 'open', priority: 1, labels: [] }];

      mockedExistsSync.mockReturnValue(true);
      // First call throws out of sync error, second call succeeds
      mockedExecSync
        .mockImplementationOnce(() => {
          const error = new Error('out of sync') as Error & { stderr?: string };
          error.stderr = 'out of sync';
          throw error;
        })
        .mockReturnValueOnce('') // sync --import-only
        .mockReturnValueOnce(JSON.stringify(mockTasks)); // retry

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const tasks = manager.getTasks();

      expect(tasks).toHaveLength(1);
      expect(tasks[0]?.id).toBe('1');
    });

    it('returns empty array on bd CLI error', () => {
      mockedExistsSync.mockReturnValue(true);
      mockedExecSync.mockImplementation(() => {
        throw new Error('Command failed');
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const tasks = manager.getTasks();

      expect(tasks).toEqual([]);
    });
  });

  describe('getStats', () => {
    it('calculates correct stats from tasks', () => {
      const mockTasks: BeadsTask[] = [
        { id: '1', title: 'Task 1', status: 'open', priority: 1, labels: [] },
        { id: '2', title: 'Task 2', status: 'in_progress', priority: 2, labels: [] },
        { id: '3', title: 'Task 3', status: 'closed', priority: 3, labels: [] },
        { id: '4', title: 'Task 4', status: 'closed', priority: 4, labels: [] },
      ];

      mockedExistsSync.mockReturnValue(true);
      mockedExecSync.mockReturnValue(JSON.stringify(mockTasks));

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const stats = manager.getStats();

      expect(stats.total).toBe(4);
      expect(stats.open).toBe(1);
      expect(stats.in_progress).toBe(1);
      expect(stats.closed).toBe(2);
      expect(stats.percentage).toBe(50);
    });

    it('returns zero stats when no tasks', () => {
      mockedExistsSync.mockReturnValue(true);
      mockedExecSync.mockReturnValue('[]');

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const stats = manager.getStats();

      expect(stats.total).toBe(0);
      expect(stats.percentage).toBe(0);
    });

    it('handles tasks with missing status', () => {
      const mockTasks: unknown[] = [
        { id: '1', title: 'Task 1', priority: 1, labels: [] },
      ];

      mockedExistsSync.mockReturnValue(true);
      mockedExecSync.mockReturnValue(JSON.stringify(mockTasks));

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const stats = manager.getStats();

      expect(stats.open).toBe(1);
      expect(stats.in_progress).toBe(0);
      expect(stats.closed).toBe(0);
    });
  });

  describe('getFeatures', () => {
    it('converts tasks to features correctly', () => {
      const mockTasks: BeadsTask[] = [
        {
          id: '1',
          title: 'Feature 1',
          description: 'Description\n\n1. Step one\n2. Step two',
          status: 'in_progress',
          priority: 1,
          labels: ['category1'],
        },
      ];

      mockedExistsSync.mockReturnValue(true);
      mockedExecSync.mockReturnValue(JSON.stringify(mockTasks));

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const features = manager.getFeatures();

      expect(features).toHaveLength(1);
      expect(features[0]?.id).toBe('1');
      expect(features[0]?.name).toBe('Feature 1');
      expect(features[0]?.category).toBe('category1');
      expect(features[0]?.steps).toEqual(['Step one', 'Step two']);
      expect(features[0]?.in_progress).toBe(true);
      expect(features[0]?.passes).toBe(false);
    });

    it('marks closed tasks as passing', () => {
      const mockTasks: BeadsTask[] = [
        { id: '1', title: 'Done Feature', status: 'closed', priority: 1, labels: [] },
      ];

      mockedExistsSync.mockReturnValue(true);
      mockedExecSync.mockReturnValue(JSON.stringify(mockTasks));

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const features = manager.getFeatures();

      expect(features[0]?.passes).toBe(true);
      expect(features[0]?.in_progress).toBe(false);
    });

    it('extracts category from first label', () => {
      const mockTasks: BeadsTask[] = [
        { id: '1', title: 'Feature', status: 'open', priority: 1, labels: ['backend', 'api'] },
      ];

      mockedExistsSync.mockReturnValue(true);
      mockedExecSync.mockReturnValue(JSON.stringify(mockTasks));

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const features = manager.getFeatures();

      expect(features[0]?.category).toBe('backend');
    });
  });

  describe('getFeature', () => {
    it('returns feature by ID', () => {
      const mockTasks: BeadsTask[] = [
        { id: '1', title: 'Feature 1', status: 'open', priority: 1, labels: [] },
        { id: '2', title: 'Feature 2', status: 'open', priority: 2, labels: [] },
      ];

      mockedExistsSync.mockReturnValue(true);
      mockedExecSync.mockReturnValue(JSON.stringify(mockTasks));

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const feature = manager.getFeature('2');

      expect(feature).not.toBeNull();
      expect(feature?.id).toBe('2');
      expect(feature?.name).toBe('Feature 2');
    });

    it('returns null for non-existent feature', () => {
      const mockTasks: BeadsTask[] = [
        { id: '1', title: 'Feature 1', status: 'open', priority: 1, labels: [] },
      ];

      mockedExistsSync.mockReturnValue(true);
      mockedExecSync.mockReturnValue(JSON.stringify(mockTasks));

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const feature = manager.getFeature('999');

      expect(feature).toBeNull();
    });
  });

  describe('getTasksByStatus', () => {
    it('filters tasks by status', () => {
      const mockTasks: BeadsTask[] = [
        { id: '1', title: 'Open Task', status: 'open', priority: 1, labels: [] },
        { id: '2', title: 'In Progress Task', status: 'in_progress', priority: 2, labels: [] },
        { id: '3', title: 'Another Open', status: 'open', priority: 3, labels: [] },
      ];

      mockedExistsSync.mockReturnValue(true);
      mockedExecSync.mockReturnValue(JSON.stringify(mockTasks));

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const openTasks = manager.getTasksByStatus('open');

      expect(openTasks).toHaveLength(2);
      expect(openTasks.map(t => t.id)).toEqual(['1', '3']);
    });
  });

  describe('createIssue', () => {
    it('creates an issue with basic fields', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());

      const mockResponse = { success: true, data: { id: '42' } };
      mockedExec.mockImplementation((_cmd, _opts, callback) => {
        if (callback) {
          (callback as unknown as (error: null, result: { stdout: string }) => void)(null, { stdout: JSON.stringify(mockResponse) });
        }
        return {} as ReturnType<typeof exec>;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const result = await manager.createIssue('Test Issue');

      expect(result.success).toBe(true);
    });

    it('escapes quotes in title', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());

      let capturedCmd = '';
      mockedExec.mockImplementation((cmd, _opts, callback) => {
        capturedCmd = cmd as string;
        if (callback) {
          (callback as unknown as (error: null, result: { stdout: string }) => void)(null, { stdout: '{}' });
        }
        return {} as ReturnType<typeof exec>;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      await manager.createIssue('Issue with "quotes"');

      expect(capturedCmd).toContain('\\"quotes\\"');
    });

    it('includes description when provided', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());

      let capturedCmd = '';
      mockedExec.mockImplementation((cmd, _opts, callback) => {
        capturedCmd = cmd as string;
        if (callback) {
          (callback as unknown as (error: null, result: { stdout: string }) => void)(null, { stdout: '{}' });
        }
        return {} as ReturnType<typeof exec>;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      await manager.createIssue('Test', 'task', 2, 'Description');

      expect(capturedCmd).toContain('--description');
    });

    it('includes labels when provided', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());

      let capturedCmd = '';
      mockedExec.mockImplementation((cmd, _opts, callback) => {
        capturedCmd = cmd as string;
        if (callback) {
          (callback as unknown as (error: null, result: { stdout: string }) => void)(null, { stdout: '{}' });
        }
        return {} as ReturnType<typeof exec>;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      await manager.createIssue('Test', 'task', 2, '', ['bug', 'urgent']);

      expect(capturedCmd).toContain('--labels');
      expect(capturedCmd).toContain('bug,urgent');
    });
  });

  describe('updateIssue', () => {
    it('updates issue with provided fields', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());

      let capturedCmd = '';
      mockedExec.mockImplementation((cmd, _opts, callback) => {
        capturedCmd = cmd as string;
        if (callback) {
          (callback as unknown as (error: null, result: { stdout: string }) => void)(null, { stdout: '{}' });
        }
        return {} as ReturnType<typeof exec>;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      await manager.updateIssue('42', { title: 'New Title', status: 'closed' });

      expect(capturedCmd).toContain('update 42');
      expect(capturedCmd).toContain('--title');
      expect(capturedCmd).toContain('--status');
    });

    it('returns error when no fields provided', async () => {
      mockedExistsSync.mockReturnValue(true);

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const result = await manager.updateIssue('42', {});

      expect(result.error).toBe('No update fields provided');
    });

    it('formats priority correctly', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());

      let capturedCmd = '';
      mockedExec.mockImplementation((cmd, _opts, callback) => {
        capturedCmd = cmd as string;
        if (callback) {
          (callback as unknown as (error: null, result: { stdout: string }) => void)(null, { stdout: '{}' });
        }
        return {} as ReturnType<typeof exec>;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      await manager.updateIssue('42', { priority: 1 });

      expect(capturedCmd).toContain('--priority P1');
    });
  });

  describe('closeIssue', () => {
    it('closes an issue', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());

      let capturedCmd = '';
      mockedExec.mockImplementation((cmd, _opts, callback) => {
        capturedCmd = cmd as string;
        if (callback) {
          (callback as unknown as (error: null, result: { stdout: string }) => void)(null, { stdout: '{}' });
        }
        return {} as ReturnType<typeof exec>;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      await manager.closeIssue('42');

      expect(capturedCmd).toContain('close 42');
    });

    it('includes reason when provided', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());

      let capturedCmd = '';
      mockedExec.mockImplementation((cmd, _opts, callback) => {
        capturedCmd = cmd as string;
        if (callback) {
          (callback as unknown as (error: null, result: { stdout: string }) => void)(null, { stdout: '{}' });
        }
        return {} as ReturnType<typeof exec>;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      await manager.closeIssue('42', 'Done');

      expect(capturedCmd).toContain('--reason');
      expect(capturedCmd).toContain('Done');
    });
  });

  describe('reopenIssue', () => {
    it('reopens an issue', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());

      let capturedCmd = '';
      mockedExec.mockImplementation((cmd, _opts, callback) => {
        capturedCmd = cmd as string;
        if (callback) {
          (callback as unknown as (error: null, result: { stdout: string }) => void)(null, { stdout: '{}' });
        }
        return {} as ReturnType<typeof exec>;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      await manager.reopenIssue('42');

      expect(capturedCmd).toContain('reopen 42');
    });
  });

  describe('addDependency', () => {
    it('adds a dependency', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());

      let capturedCmd = '';
      mockedExec.mockImplementation((cmd, _opts, callback) => {
        capturedCmd = cmd as string;
        if (callback) {
          (callback as unknown as (error: null, result: { stdout: string }) => void)(null, { stdout: '{}' });
        }
        return {} as ReturnType<typeof exec>;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      await manager.addDependency('42', '10');

      expect(capturedCmd).toContain('dep add 42 10');
    });
  });

  describe('addComment', () => {
    it('adds a comment', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());

      let capturedCmd = '';
      mockedExec.mockImplementation((cmd, _opts, callback) => {
        capturedCmd = cmd as string;
        if (callback) {
          (callback as unknown as (error: null, result: { stdout: string }) => void)(null, { stdout: '{}' });
        }
        return {} as ReturnType<typeof exec>;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      await manager.addComment('42', 'This is a comment');

      expect(capturedCmd).toContain('comments add 42');
    });
  });

  describe('deleteIssue', () => {
    it('deletes an issue with force flag', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());

      let capturedCmd = '';
      mockedExec.mockImplementation((cmd, _opts, callback) => {
        capturedCmd = cmd as string;
        if (callback) {
          (callback as unknown as (error: null, result: { stdout: string }) => void)(null, { stdout: '{}' });
        }
        return {} as ReturnType<typeof exec>;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      await manager.deleteIssue('42');

      expect(capturedCmd).toContain('delete 42 --force');
    });
  });

  describe('createFeature', () => {
    it('creates a feature with steps', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());

      const mockResponse = { success: true, data: { id: '42' } };
      mockedExec.mockImplementation((_cmd, _opts, callback) => {
        if (callback) {
          (callback as unknown as (error: null, result: { stdout: string }) => void)(null, { stdout: JSON.stringify(mockResponse) });
        }
        return {} as ReturnType<typeof exec>;
      });

      // Mock getTasks to return the created feature
      const mockTasks: BeadsTask[] = [
        { id: '42', title: 'New Feature', description: '1. Step one\n2. Step two', status: 'open', priority: 5, labels: ['core'] },
      ];
      mockedExecSync.mockReturnValue(JSON.stringify(mockTasks));

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const feature = await manager.createFeature('New Feature', 'core', 'Description', ['Step one', 'Step two'], 5);

      expect(feature).not.toBeNull();
      expect(feature?.name).toBe('New Feature');
      expect(feature?.steps).toEqual(['Step one', 'Step two']);
    });

    it('returns null on creation failure', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());

      mockedExec.mockImplementation((_cmd, _opts, callback) => {
        if (callback) {
          (callback as unknown as (error: Error) => void)(new Error('Failed'));
        }
        return {} as ReturnType<typeof exec>;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const feature = await manager.createFeature('New Feature');

      expect(feature).toBeNull();
    });
  });

  describe('updateFeature', () => {
    it('returns null when feature does not exist', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedExecSync.mockReturnValue('[]');

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const result = await manager.updateFeature('999', { name: 'New Name' });

      expect(result).toBeNull();
    });
  });

  describe('deleteFeature', () => {
    it('returns true on successful deletion', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());

      mockedExec.mockImplementation((_cmd, _opts, callback) => {
        if (callback) {
          (callback as unknown as (error: null, result: { stdout: string }) => void)(null, { stdout: '{}' });
        }
        return {} as ReturnType<typeof exec>;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const result = await manager.deleteFeature('42');

      expect(result).toBe(true);
    });
  });

  describe('skipFeature', () => {
    it('returns null when feature does not exist', async () => {
      mockedExistsSync.mockReturnValue(true);
      mockedExecSync.mockReturnValue('[]');

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const result = await manager.skipFeature('999');

      expect(result).toBeNull();
    });

    it('sets priority to P4 when feature exists', async () => {
      const mockTasks: BeadsTask[] = [
        { id: '42', title: 'Feature', status: 'open', priority: 1, labels: [] },
      ];

      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());
      mockedExecSync.mockReturnValue(JSON.stringify(mockTasks));

      let capturedCmd = '';
      mockedExec.mockImplementation((cmd, _opts, callback) => {
        capturedCmd = cmd as string;
        if (callback) {
          (callback as unknown as (error: null, result: { stdout: string }) => void)(null, { stdout: '{}' });
        }
        return {} as ReturnType<typeof exec>;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const result = await manager.skipFeature('42');

      expect(result?.success).toBe(true);
      expect(capturedCmd).toContain('--priority P4');
    });
  });

  describe('reopenFeature', () => {
    it('reopens a closed feature', async () => {
      const mockTasks: BeadsTask[] = [
        { id: '42', title: 'Feature', status: 'open', priority: 1, labels: [] },
      ];

      mockedExistsSync.mockReturnValue(true);
      mockedLockfileLock.mockResolvedValue(vi.fn());
      mockedExecSync.mockReturnValue(JSON.stringify(mockTasks));

      mockedExec.mockImplementation((_cmd, _opts, callback) => {
        if (callback) {
          (callback as unknown as (error: null, result: { stdout: string }) => void)(null, { stdout: '{}' });
        }
        return {} as ReturnType<typeof exec>;
      });

      const manager = new BeadsManager('test-project', 'https://github.com/test/repo');
      const result = await manager.reopenFeature('42');

      expect(result).not.toBeNull();
    });
  });
});

describe('getBeadsManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearBeadsManager('cached-project');
    mockedGetProjectsDir.mockReturnValue('/test/projects');
  });

  it('creates new manager when not cached', async () => {
    mockedGetProjectGitUrl.mockReturnValue('https://github.com/test/repo');

    const manager = await getBeadsManager('cached-project');

    expect(manager).toBeInstanceOf(BeadsManager);
    expect(manager.projectName).toBe('cached-project');
  });

  it('returns cached manager on subsequent calls', async () => {
    mockedGetProjectGitUrl.mockReturnValue('https://github.com/test/repo');

    const manager1 = await getBeadsManager('cached-project');
    const manager2 = await getBeadsManager('cached-project');

    expect(manager1).toBe(manager2);
  });

  it('uses provided git URL', async () => {
    const manager = await getBeadsManager('new-project', 'https://github.com/custom/repo');

    expect(manager.gitRemoteUrl).toBe('https://github.com/custom/repo');
  });

  it('throws error when no git URL available', async () => {
    mockedGetProjectGitUrl.mockReturnValue(null);

    await expect(getBeadsManager('no-url-project')).rejects.toThrow('No git URL available');
  });
});

describe('getBeadsManagerSync', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearBeadsManager('sync-project');
    mockedGetProjectsDir.mockReturnValue('/test/projects');
  });

  it('returns null when manager not cached', () => {
    const manager = getBeadsManagerSync('sync-project');

    expect(manager).toBeNull();
  });

  it('returns cached manager', async () => {
    mockedGetProjectGitUrl.mockReturnValue('https://github.com/test/repo');

    await getBeadsManager('sync-project');
    const manager = getBeadsManagerSync('sync-project');

    expect(manager).toBeInstanceOf(BeadsManager);
  });
});

describe('clearBeadsManager', () => {
  beforeEach(() => {
    mockedGetProjectsDir.mockReturnValue('/test/projects');
  });

  it('removes cached manager', async () => {
    mockedGetProjectGitUrl.mockReturnValue('https://github.com/test/repo');

    await getBeadsManager('clear-test');
    expect(getBeadsManagerSync('clear-test')).not.toBeNull();

    clearBeadsManager('clear-test');
    expect(getBeadsManagerSync('clear-test')).toBeNull();
  });
});

describe('getCachedStats', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearBeadsManager('stats-project');
    mockedGetProjectsDir.mockReturnValue('/test/projects');
  });

  it('returns stats from cached manager', () => {
    const mockTasks: BeadsTask[] = [
      { id: '1', title: 'Task 1', status: 'open', priority: 1, labels: [] },
      { id: '2', title: 'Task 2', status: 'closed', priority: 2, labels: [] },
    ];

    mockedExistsSync.mockReturnValue(true);
    mockedExecSync.mockReturnValue(JSON.stringify(mockTasks));
    mockedGetProjectGitUrl.mockReturnValue('https://github.com/test/repo');

    // Mock the managers map directly by creating a manager through getBeadsManagerSync
    // Then we need to set it in the map - we'll use getCachedStats which creates if needed
    const stats = getCachedStats('stats-project');

    expect(stats.total).toBe(2);
    expect(stats.pending).toBe(1);
    expect(stats.done).toBe(1);
  });

  it('returns zero stats when no manager available', () => {
    mockedGetProjectGitUrl.mockReturnValue(null);

    const stats = getCachedStats('no-stats-project');

    expect(stats.total).toBe(0);
    expect(stats.percentage).toBe(0);
  });
});

describe('getCachedFeatures', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearBeadsManager('features-project');
    mockedGetProjectsDir.mockReturnValue('/test/projects');
  });

  it('returns features from cached manager', () => {
    const mockTasks: BeadsTask[] = [
      { id: '1', title: 'Feature 1', status: 'open', priority: 1, labels: ['core'] },
    ];

    mockedExistsSync.mockReturnValue(true);
    mockedExecSync.mockReturnValue(JSON.stringify(mockTasks));
    mockedGetProjectGitUrl.mockReturnValue('https://github.com/test/repo');

    const features = getCachedFeatures('features-project');

    expect(features).toHaveLength(1);
    expect(features[0]?.name).toBe('Feature 1');
  });

  it('returns empty array when no manager available', () => {
    mockedGetProjectGitUrl.mockReturnValue(null);

    const features = getCachedFeatures('no-features-project');

    expect(features).toEqual([]);
  });
});
