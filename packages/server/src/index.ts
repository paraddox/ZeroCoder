/**
 * ZeroCoder Server Entry Point
 * ============================
 *
 * Main entry point for the TypeScript server.
 * Uses Hono framework with Drizzle ORM.
 */

import { serve } from '@hono/node-server';
import { VERSION } from '@zerocoder/shared';
import { app } from './app.js';

// Health check endpoint
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

// Root route
app.get('/', (c) => {
  return c.json({
    name: 'ZeroCoder Server',
    version: VERSION,
  });
});

// Start server
const port = parseInt(process.env['PORT'] ?? '8000', 10);
const host = process.env['HOST'] ?? '127.0.0.1';

console.log(`ZeroCoder Server v${VERSION}`);
console.log(`Starting server on http://${host}:${port}...`);

serve({
  fetch: app.fetch,
  port,
  hostname: host,
});

export { app };
