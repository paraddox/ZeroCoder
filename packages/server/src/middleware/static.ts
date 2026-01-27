/**
 * Static File Middleware
 * ======================
 *
 * Serves React production build from ui/dist/ directory.
 * Handles SPA fallback routing (serves index.html for non-API routes).
 */

import { Context, Hono } from 'hono';
import { serveStatic } from '@hono/node-server/serve-static';
import * as fs from 'node:fs';
import * as path from 'node:path';

/**
 * Find the project root by walking up from the current file location
 * until we find the ui/ directory (which only exists at project root).
 */
function findProjectRoot(): string {
  // Start from this file's directory
  let dir = import.meta.dirname ?? __dirname;

  // Walk up until we find ui/ directory or hit the filesystem root
  for (let i = 0; i < 10; i++) {
    const uiDir = path.join(dir, 'ui');
    if (fs.existsSync(uiDir) && fs.statSync(uiDir).isDirectory()) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) {
      // Reached filesystem root without finding ui/
      break;
    }
    dir = parent;
  }

  // Fallback: use current working directory (typical for server startup)
  return process.cwd();
}

const PROJECT_ROOT = findProjectRoot();
const UI_DIST_DIR = path.join(PROJECT_ROOT, 'ui', 'dist');
const INDEX_HTML = path.join(UI_DIST_DIR, 'index.html');

/**
 * Check if UI dist directory exists and is valid
 */
export function isUIBuildAvailable(): boolean {
  return fs.existsSync(UI_DIST_DIR) && fs.existsSync(INDEX_HTML);
}

/**
 * Get the UI dist directory path
 */
export function getUIDistPath(): string {
  return UI_DIST_DIR;
}

/**
 * Configure static file serving middleware on a Hono app.
 * Only configures if ui/dist exists.
 *
 * Order of routes matters:
 * 1. /assets/* - Serve bundled Vite assets with caching
 * 2. / - Serve index.html for root
 * 3. /*  - SPA fallback (serve file if exists, else index.html)
 */
export function configureStaticFiles(app: Hono): void {
  if (!isUIBuildAvailable()) {
    console.log('UI build not found at', UI_DIST_DIR, '- skipping static file serving');
    return;
  }

  console.log('Serving static files from', UI_DIST_DIR);

  // Serve /assets/* with caching headers (Vite's bundled assets have content hashes)
  app.use(
    '/assets/*',
    serveStatic({
      root: UI_DIST_DIR,
      rewriteRequestPath: (p: string) => p, // Keep /assets/* path as-is
      onFound: (_path, c) => {
        // Long-term caching for hashed assets
        c.header('Cache-Control', 'public, max-age=31536000, immutable');
      },
    })
  );

  // Serve other static files from ui/dist (e.g., vite.svg, favicon)
  app.use(
    '/vite.svg',
    serveStatic({
      root: UI_DIST_DIR,
      rewriteRequestPath: () => '/vite.svg',
    })
  );

  // Serve index.html for root route
  app.get('/', (c: Context) => {
    return serveIndexHtml(c);
  });

  // SPA fallback: serve file if exists, otherwise index.html
  // This catch-all must be registered AFTER API routes
  app.get('*', (c: Context) => {
    const reqPath = c.req.path;

    // Skip API and WebSocket routes (they should 404 if not matched)
    if (reqPath.startsWith('/api/') || reqPath.startsWith('/ws/')) {
      return c.json({ error: 'Not found' }, 404);
    }

    // Try to serve the file directly
    const filePath = path.join(UI_DIST_DIR, reqPath);
    const normalizedPath = path.normalize(filePath);

    // Security: ensure path is within UI_DIST_DIR (prevent directory traversal)
    if (!normalizedPath.startsWith(UI_DIST_DIR)) {
      return c.json({ error: 'Invalid path' }, 400);
    }

    // If file exists, let Hono serve it
    if (fs.existsSync(normalizedPath) && fs.statSync(normalizedPath).isFile()) {
      return c.newResponse(fs.readFileSync(normalizedPath), 200, {
        'Content-Type': getMimeType(normalizedPath),
      });
    }

    // Fall back to index.html for SPA routing
    return serveIndexHtml(c);
  });
}

/**
 * Serve the index.html file
 */
function serveIndexHtml(c: Context): Response {
  const content = fs.readFileSync(INDEX_HTML, 'utf-8');
  return c.html(content);
}

/**
 * Get MIME type for a file based on extension
 */
function getMimeType(filePath: string): string {
  const ext = path.extname(filePath).toLowerCase();
  const mimeTypes: Record<string, string> = {
    '.html': 'text/html',
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.mjs': 'application/javascript',
    '.json': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.ico': 'image/x-icon',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
    '.ttf': 'font/ttf',
    '.eot': 'application/vnd.ms-fontobject',
    '.txt': 'text/plain',
    '.map': 'application/json',
  };
  return mimeTypes[ext] ?? 'application/octet-stream';
}
