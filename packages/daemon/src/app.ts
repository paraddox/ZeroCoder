/**
 * Hono App Configuration
 * ======================
 *
 * Central Hono app instance for the daemon.
 */

import { Hono } from 'hono';
import { logger as honoLogger } from 'hono/logger';
import type { Context, Next } from 'hono';
import { HTTPException } from 'hono/http-exception';

import { getConfig } from './utils/config.js';
import { createLogger } from './utils/logger.js';

const log = createLogger('app');

/**
 * Authentication middleware.
 * Checks for DAEMON_SECRET if configured.
 */
async function authMiddleware(c: Context, next: Next) {
  const config = getConfig();

  // If no secret configured, allow all requests
  if (!config.secret) {
    return next();
  }

  // Check Authorization header
  const authHeader = c.req.header('Authorization');
  if (!authHeader?.startsWith('Bearer ')) {
    throw new HTTPException(401, { message: 'Missing or invalid Authorization header' });
  }

  const token = authHeader.substring(7);
  if (token !== config.secret) {
    throw new HTTPException(403, { message: 'Invalid daemon secret' });
  }

  return next();
}

/**
 * Global error handler middleware.
 */
async function errorHandler(c: Context, next: Next) {
  try {
    await next();
  } catch (err) {
    if (err instanceof HTTPException) {
      return c.json(
        {
          error: err.message,
          status: err.status,
        },
        err.status
      );
    }

    // Log unexpected errors
    log.error('Unhandled error', { error: err instanceof Error ? err.message : String(err) });

    const message = err instanceof Error ? err.message : 'Internal server error';
    return c.json(
      {
        error: message,
        status: 500,
      },
      500
    );
  }
}

// Create the Hono app
const app = new Hono();

// Apply middleware
app.use('*', errorHandler);
app.use('*', honoLogger());
app.use('*', authMiddleware);

export { app };
