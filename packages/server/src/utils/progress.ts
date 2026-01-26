/**
 * Progress Tracking Utilities
 * ===========================
 *
 * Functions for tracking and displaying progress of the autonomous coding agent.
 * Uses live bd commands via BeadsManager for feature data.
 */

import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const WEBHOOK_URL = process.env['PROGRESS_N8N_WEBHOOK_URL'];
const PROGRESS_CACHE_FILE = '.progress_cache';

// Type definitions for stats and features
interface BeadsStats {
  total?: number;
  pending?: number;
  in_progress?: number;
  done?: number;
}

interface Feature {
  id?: string;
  category?: string;
  name?: string;
  passes?: boolean;
  status?: string;
}

interface ProgressCache {
  count: number;
  passing_ids: string[];
}

// These functions will be provided by the beads manager service
// For now, we define the interface and allow injection
type GetCachedStats = (projectName: string) => BeadsStats;
type GetCachedFeatures = (projectName: string) => Feature[];

let _getCachedStats: GetCachedStats | null = null;
let _getCachedFeatures: GetCachedFeatures | null = null;

/**
 * Register the beads manager functions for progress tracking.
 * This allows the progress module to work without circular imports.
 */
export function registerBeadsManager(
  getCachedStats: GetCachedStats,
  getCachedFeatures: GetCachedFeatures
): void {
  _getCachedStats = getCachedStats;
  _getCachedFeatures = getCachedFeatures;
}

/**
 * Check if the project has features in beads using live bd commands.
 *
 * This is used to determine if the initializer agent needs to run.
 *
 * @returns True if beads has issues, False if no features exist (initializer needs to run)
 */
export function hasFeatures(projectDir: string, projectName?: string): boolean {
  if (projectName && _getCachedStats) {
    try {
      const stats = _getCachedStats(projectName);
      return (stats.total ?? 0) > 0;
    } catch {
      // Stats not available
    }
  }

  // Fallback: check if .beads directory exists
  return existsSync(join(projectDir, '.beads', 'beads.db'));
}

/**
 * Check for open/in_progress features using live bd commands.
 *
 * This is used to determine if the overseer agent should run.
 *
 * @returns True if there are pending or in_progress features, False if all features are closed
 */
export function hasOpenFeatures(_projectDir: string, projectName?: string): boolean {
  if (projectName && _getCachedStats) {
    try {
      const stats = _getCachedStats(projectName);
      return (stats.pending ?? 0) + (stats.in_progress ?? 0) > 0;
    } catch {
      // Stats not available
    }
  }

  // Fallback: assume features exist (safer)
  return true;
}

/**
 * Count passing, in_progress, and total tests using live bd commands.
 *
 * @returns Tuple of [passing_count, in_progress_count, total_count]
 */
export function countPassingTests(
  _projectDir: string,
  projectName?: string
): [number, number, number] {
  if (projectName && _getCachedStats) {
    try {
      const stats = _getCachedStats(projectName);
      if ((stats.total ?? 0) > 0) {
        return [stats.done ?? 0, stats.in_progress ?? 0, stats.total ?? 0];
      }
    } catch {
      // Stats not available
    }
  }

  return [0, 0, 0];
}

/**
 * Get all passing features using live bd commands.
 *
 * @returns List of objects with id, category, name for each passing feature
 */
export function getAllPassingFeatures(
  _projectDir: string,
  projectName?: string
): Array<{ id: string; category: string; name: string }> {
  if (projectName && _getCachedFeatures) {
    try {
      const features = _getCachedFeatures(projectName);
      return features
        .filter((f) => f.passes || f.status === 'closed')
        .map((f) => ({
          id: f.id ?? '',
          category: f.category ?? '',
          name: f.name ?? '',
        }));
    } catch {
      // Features not available
    }
  }

  return [];
}

/**
 * Send webhook notification when progress increases.
 */
export async function sendProgressWebhook(
  passing: number,
  total: number,
  projectDir: string,
  projectName?: string
): Promise<void> {
  if (!WEBHOOK_URL) {
    return; // Webhook not configured
  }

  const cacheFile = join(projectDir, PROGRESS_CACHE_FILE);
  let previous = 0;
  let previousPassingIds = new Set<string>();

  // Read previous progress and passing feature IDs
  if (existsSync(cacheFile)) {
    try {
      const cacheData: ProgressCache = JSON.parse(readFileSync(cacheFile, 'utf-8'));
      previous = cacheData.count ?? 0;
      previousPassingIds = new Set(cacheData.passing_ids?.map(String) ?? []);
    } catch {
      previous = 0;
    }
  }

  // Only notify if progress increased
  if (passing > previous) {
    // Find which features are now passing
    const completedTests: string[] = [];
    const currentPassingIds: string[] = [];

    // Get all passing features
    const allPassing = getAllPassingFeatures(projectDir, projectName);
    for (const feature of allPassing) {
      const featureId = String(feature.id);
      currentPassingIds.push(featureId);
      if (!previousPassingIds.has(featureId)) {
        // This feature is newly passing
        const name = feature.name || `Feature #${featureId}`;
        const category = feature.category || '';
        if (category) {
          completedTests.push(`${category} ${name}`);
        } else {
          completedTests.push(name);
        }
      }
    }

    const projectDirName = projectDir.split('/').pop() ?? projectDir;
    const payload = {
      event: 'test_progress',
      passing,
      total,
      percentage: total > 0 ? Math.round((passing / total) * 1000) / 10 : 0,
      previous_passing: previous,
      tests_completed_this_session: passing - previous,
      completed_tests: completedTests,
      project: projectDirName,
      timestamp: new Date().toISOString(),
    };

    try {
      const response = await fetch(WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify([payload]), // n8n expects array
        signal: AbortSignal.timeout(5000),
      });

      if (!response.ok) {
        console.log(`[Webhook notification failed: HTTP ${response.status}]`);
      }
    } catch (e) {
      console.log(`[Webhook notification failed: ${e}]`);
    }

    // Update cache with count and passing IDs
    writeFileSync(
      cacheFile,
      JSON.stringify({ count: passing, passing_ids: currentPassingIds }),
      'utf-8'
    );
  } else {
    // Update cache even if no change (for initial state)
    if (!existsSync(cacheFile)) {
      const allPassing = getAllPassingFeatures(projectDir, projectName);
      const currentPassingIds = allPassing.map((f) => String(f.id));
      writeFileSync(
        cacheFile,
        JSON.stringify({ count: passing, passing_ids: currentPassingIds }),
        'utf-8'
      );
    }
  }
}

/**
 * Print a formatted header for the session.
 */
export function printSessionHeader(sessionNum: number, isInitializer: boolean): void {
  const sessionType = isInitializer ? 'INITIALIZER' : 'CODING AGENT';

  console.log('\n' + '='.repeat(70));
  console.log(`  SESSION ${sessionNum}: ${sessionType}`);
  console.log('='.repeat(70));
  console.log();
}

/**
 * Print a summary of current progress.
 */
export async function printProgressSummary(
  projectDir: string,
  projectName?: string
): Promise<void> {
  const [passing, inProgress, total] = countPassingTests(projectDir, projectName);

  if (total > 0) {
    const percentage = (passing / total) * 100;
    const statusParts = [`${passing}/${total} tests passing (${percentage.toFixed(1)}%)`];
    if (inProgress > 0) {
      statusParts.push(`${inProgress} in progress`);
    }
    console.log(`\nProgress: ${statusParts.join(', ')}`);
    await sendProgressWebhook(passing, total, projectDir, projectName);
  } else {
    console.log('\nProgress: No features yet');
  }
}

/**
 * Calculate milestone percentage (rounds to nearest 10%).
 */
export function calculateMilestone(passing: number, total: number): number {
  if (total === 0) return 0;
  const percentage = (passing / total) * 100;
  return Math.floor(percentage / 10) * 10;
}

/**
 * Check if a new milestone has been reached.
 */
export function hasReachedNewMilestone(
  currentPassing: number,
  previousPassing: number,
  total: number
): boolean {
  if (total === 0) return false;
  const currentMilestone = calculateMilestone(currentPassing, total);
  const previousMilestone = calculateMilestone(previousPassing, total);
  return currentMilestone > previousMilestone;
}

/**
 * Get the current milestone for display purposes.
 */
export function getCurrentMilestone(passing: number, total: number): string {
  if (total === 0) return '0%';
  const milestone = calculateMilestone(passing, total);
  return `${milestone}%`;
}
