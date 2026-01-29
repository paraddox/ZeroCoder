/**
 * ZeroCoder Remote Agent Daemon
 * =============================
 *
 * Persistent daemon that runs on remote machines, exposing a REST API
 * for work assignment and control. Manages Claude Code agent lifecycle.
 */

import { serve } from '@hono/node-server';

import { app } from './app.js';
import { getConfig } from './utils/config.js';
import { createLogger } from './utils/logger.js';
import { workRouter } from './routers/work.js';
import { controlRouter } from './routers/control.js';
import { gracefulShutdown } from './services/agent-orchestrator.js';

const log = createLogger('main');

// Register routers
app.route('/', workRouter);
app.route('/', controlRouter);

/**
 * Main entry point.
 */
async function main(): Promise<void> {
  const config = getConfig();

  log.info('Starting ZeroCoder daemon', {
    port: config.port,
    workspaceDir: config.workspaceDir,
    hasSecret: !!config.secret,
    hasApiKey: !!config.anthropicApiKey,
  });

  // Set up graceful shutdown handlers
  const shutdown = async (signal: string) => {
    log.info(`Received ${signal}, shutting down...`);
    await gracefulShutdown();
    process.exit(0);
  };

  process.on('SIGINT', () => shutdown('SIGINT'));
  process.on('SIGTERM', () => shutdown('SIGTERM'));

  // Start the server
  serve({
    fetch: app.fetch,
    port: config.port,
  });

  log.info(`Daemon listening on port ${config.port}`);
}

main().catch((err) => {
  log.error('Fatal error', { error: err instanceof Error ? err.message : String(err) });
  process.exit(1);
});
