/**
 * Control Router
 * ==============
 *
 * POST /stop/hard - Immediate stop
 * POST /stop/graceful - Stop after current session
 * GET /status - Current status
 * GET /health - Health check
 * POST /shutdown - Graceful daemon shutdown
 */

import { Hono } from 'hono';

import { createLogger } from '../utils/logger.js';
import {
  getStatus,
  getSessionStatus,
  requestGracefulStop,
  requestHardStop,
  gracefulShutdown,
  waitForStopped,
} from '../services/agent-orchestrator.js';

const log = createLogger('control-router');

const controlRouter = new Hono();

/**
 * POST /stop/hard
 *
 * Immediate stop of agent session.
 */
controlRouter.post('/stop/hard', async (c) => {
  log.info('Hard stop requested');
  requestHardStop();

  // Wait up to 5 seconds for status to transition
  const stopped = await waitForStopped(5000);

  return c.json({
    success: true,
    message: stopped ? 'Stopped' : 'Stop initiated (agent finishing current operation)',
    status: getSessionStatus(),
  });
});

/**
 * POST /stop/graceful
 *
 * Stop after completing current session.
 */
controlRouter.post('/stop/graceful', async (c) => {
  log.info('Graceful stop requested');
  requestGracefulStop();

  // Wait up to 5 seconds for status to transition
  const stopped = await waitForStopped(5000);

  return c.json({
    success: true,
    message: stopped ? 'Stopped' : 'Graceful stop initiated (will stop after current session)',
    status: getSessionStatus(),
  });
});

/**
 * GET /status
 *
 * Return current repo and task status.
 */
controlRouter.get('/status', async (c) => {
  const status = getStatus();

  return c.json({
    status: status.status,
    current_repo: status.currentRepo,
    current_feature: status.currentFeature,
    agent_type: status.agentType,
    stats: status.stats
      ? {
          completed: status.stats.closed,
          remaining: status.stats.open + status.stats.inProgress,
          total: status.stats.total,
        }
      : null,
  });
});

/**
 * GET /health
 *
 * Health check endpoint.
 */
controlRouter.get('/health', async (c) => {
  return c.json({
    healthy: true,
    timestamp: new Date().toISOString(),
  });
});

/**
 * GET /version
 *
 * Return daemon version from package.json.
 */
controlRouter.get('/version', async (c) => {
  // Read package.json version using fs
  const { readFileSync } = await import('fs');
  const { dirname, join } = await import('path');
  const { fileURLToPath } = await import('url');

  const __filename = fileURLToPath(import.meta.url);
  const __dirname = dirname(__filename);
  const pkgPath = join(__dirname, '../../package.json');

  try {
    const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8'));
    return c.json({
      version: pkg.version ?? '0.0.0',
      name: pkg.name ?? '@zerocoder/daemon',
    });
  } catch {
    return c.json({
      version: '0.0.0',
      name: '@zerocoder/daemon',
    });
  }
});

/**
 * POST /shutdown
 *
 * Graceful daemon shutdown.
 */
controlRouter.post('/shutdown', async (c) => {
  log.info('Shutdown requested');

  // Start graceful shutdown in background
  setTimeout(async () => {
    await gracefulShutdown();
    log.info('Daemon exiting');
    process.exit(0);
  }, 100);

  return c.json({
    success: true,
    message: 'Shutdown initiated',
  });
});

export { controlRouter };
