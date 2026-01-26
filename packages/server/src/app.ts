/**
 * Hono App Configuration
 * ======================
 *
 * Central Hono app instance with middleware configuration.
 * - CORS middleware (configurable via CORS_ORIGINS env var)
 * - Localhost-only auth middleware (bypass with ALLOW_EXTERNAL_ACCESS)
 * - Request logging
 * - Global error handling
 */

import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { logger } from 'hono/logger';
import { HTTPException } from 'hono/http-exception';
import type { Context, Next } from 'hono';

// Environment configuration
const ALLOW_EXTERNAL_ACCESS = process.env['ALLOW_EXTERNAL_ACCESS']?.toLowerCase() === 'true';
const CORS_ORIGINS_ENV = process.env['CORS_ORIGINS'] ?? '';

// Determine CORS origins
function getCorsOrigins(): string[] {
  if (CORS_ORIGINS_ENV === '*') {
    return ['*'];
  }
  if (CORS_ORIGINS_ENV) {
    return CORS_ORIGINS_ENV.split(',').map((origin) => origin.trim());
  }
  // Default localhost origins
  return [
    'http://localhost:5173', // Vite dev server
    'http://127.0.0.1:5173',
    'http://localhost:8888', // Production
    'http://127.0.0.1:8888',
  ];
}

/**
 * Localhost-only authentication middleware.
 * Only allows requests from localhost unless ALLOW_EXTERNAL_ACCESS is set.
 * Also allows Docker network IPs (172.17.x.x) for beads API endpoints.
 */
async function requireLocalhost(c: Context, next: Next) {
  // Skip localhost check if external access is enabled (for Docker)
  if (ALLOW_EXTERNAL_ACCESS) {
    return next();
  }

  // Get client IP from various headers (reverse proxy support)
  const forwarded = c.req.header('x-forwarded-for');
  const realIp = c.req.header('x-real-ip');
  // Note: In Node.js with @hono/node-server, we can't directly access socket info
  // We rely on headers or the incoming connection info
  const clientHost = forwarded?.split(',')[0]?.trim() ?? realIp ?? '127.0.0.1';

  // Allow localhost connections
  const localhostAddresses = ['127.0.0.1', '::1', 'localhost', '::ffff:127.0.0.1'];
  if (localhostAddresses.includes(clientHost)) {
    return next();
  }

  // Allow Docker network IPs (172.17.0.0/16) for beads API endpoints only
  // Containers need to call host beads API
  if (clientHost.startsWith('172.17.')) {
    const path = c.req.path;
    if (path.startsWith('/api/projects/') && path.includes('/beads/')) {
      return next();
    }
  }

  throw new HTTPException(403, { message: 'Localhost access only' });
}

/**
 * Global error handler middleware.
 * Catches all errors and returns consistent JSON responses.
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
    console.error('Unhandled error:', err);

    // Return generic error for unexpected errors
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

// Apply middleware in order
// 1. Error handler (outermost - catches all errors)
app.use('*', errorHandler);

// 2. Request logging
app.use('*', logger());

// 3. CORS
const corsOrigins = getCorsOrigins();
app.use(
  '*',
  cors({
    origin: corsOrigins.includes('*') ? '*' : corsOrigins,
    credentials: true,
    allowMethods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
    allowHeaders: ['Content-Type', 'Authorization'],
  })
);

// 4. Localhost-only auth (innermost security layer)
app.use('*', requireLocalhost);

export { app, ALLOW_EXTERNAL_ACCESS };
