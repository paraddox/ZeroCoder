// ZeroCoder Server
// TypeScript server using Hono framework and Drizzle ORM

import { serve } from '@hono/node-server';
import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { logger } from 'hono/logger';
import { VERSION } from '@zerocoder/shared';

const app = new Hono();

// Middleware
app.use('*', logger());
app.use('*', cors());

// Health check
app.get('/health', (c) => {
  return c.json({
    status: 'ok',
    version: VERSION,
    timestamp: new Date().toISOString(),
  });
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

console.log(`ZeroCoder Server v${VERSION}`);
console.log(`Starting server on port ${port}...`);

serve({
  fetch: app.fetch,
  port,
});

export { app };
