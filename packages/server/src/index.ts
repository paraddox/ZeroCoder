/**
 * ZeroCoder Server Entry Point
 * ============================
 *
 * Main entry point for the TypeScript server.
 * Uses Hono framework with Drizzle ORM.
 *
 * Route order:
 * 1. Health check endpoints (/health, /api/health)
 * 2. API routes (to be added: /api/projects, /api/features, etc.)
 * 3. Static file serving with SPA fallback (must be LAST)
 */

import { serve } from '@hono/node-server';
import { VERSION } from '@zerocoder/shared';
import { app } from './app.js';
import { configureStaticFiles, isUIBuildAvailable } from './middleware/static.js';
import { projectsRouter, featuresRouter, specCreationRouter } from './routers/index.js';
import {
  initializeBackgroundMonitors,
  shutdownBackgroundMonitors,
} from './services/container-manager.js';

// ============================================================================
// Health Check Endpoints
// ============================================================================

// Basic health check
app.get('/health', (c) => {
  return c.json({
    status: 'ok',
    version: VERSION,
    timestamp: new Date().toISOString(),
  });
});

// API health check (matches Python server)
app.get('/api/health', (c) => {
  return c.json({ status: 'healthy' });
});

// ============================================================================
// API Routes
// ============================================================================

// Mount project routes
app.route('/api/projects', projectsRouter);

// Mount feature routes (nested under projects)
// Features are accessed via /api/projects/:name/features/*
app.route('/api/projects', featuresRouter);

// Mount spec creation routes
app.route('/api/spec', specCreationRouter);

// Future routes will be mounted here:
// - /api/agent/* - Agent control
// - /ws/projects/:project_name - WebSocket connections

// ============================================================================
// Static File Serving (must be LAST)
// ============================================================================

// Configure static file serving for React UI build
// This registers a catch-all route, so it MUST come after all API routes
configureStaticFiles(app);

// If no UI build, provide a fallback root route
if (!isUIBuildAvailable()) {
  app.get('/', (c) => {
    return c.json({
      name: 'ZeroCoder Server',
      version: VERSION,
      message: 'UI not built. Run "npm run build" in ui/ directory.',
    });
  });
}

// ============================================================================
// Start Server
// ============================================================================

const port = parseInt(process.env['PORT'] ?? '8000', 10);
const host = process.env['HOST'] ?? '127.0.0.1';

console.log(`ZeroCoder Server v${VERSION}`);
console.log(`Starting server on http://${host}:${port}...`);

// Start background health monitors
initializeBackgroundMonitors();

const server = serve({
  fetch: app.fetch,
  port,
  hostname: host,
});

// ============================================================================
// Graceful Shutdown
// ============================================================================

let isShuttingDown = false;

async function gracefulShutdown(signal: string): Promise<void> {
  if (isShuttingDown) return;
  isShuttingDown = true;

  console.log(`\nReceived ${signal}, shutting down gracefully...`);

  // Shutdown background monitors and cleanup containers
  await shutdownBackgroundMonitors();

  // Close the HTTP server
  server.close();

  console.log('Server shut down.');
  process.exit(0);
}

process.on('SIGINT', () => gracefulShutdown('SIGINT'));
process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));

export { app };
