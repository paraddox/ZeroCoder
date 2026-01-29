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
  requestGracefulStop,
  requestHardStop,
  gracefulShutdown,
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

  return c.json({
    success: true,
    message: 'Hard stop initiated',
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

  return c.json({
    success: true,
    message: 'Graceful stop requested - will stop after current session',
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
