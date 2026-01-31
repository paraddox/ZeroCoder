/**
 * Daemon Configuration
 * ====================
 *
 * Environment-based configuration for the remote agent daemon.
 */

export interface DaemonConfig {
  /** Port to listen on */
  port: number;

  /** Shared secret for authentication */
  secret: string;

  /** Anthropic API key for Claude SDK */
  anthropicApiKey: string;

  /** Base workspace directory */
  workspaceDir: string;

  /** Log level */
  logLevel: 'debug' | 'info' | 'warn' | 'error';
}

/**
 * Load configuration from environment variables.
 */
export function loadConfig(): DaemonConfig {
  const port = parseInt(process.env['DAEMON_PORT'] ?? '9999', 10);
  const secret = process.env['DAEMON_SECRET'] ?? '';
  const anthropicApiKey = process.env['ANTHROPIC_API_KEY'] ?? '';
  const workspaceDir = process.env['DAEMON_WORKSPACE'] ?? process.env['WORKSPACE_DIR'] ?? `${process.env['HOME']}/zerocoder`;
  const logLevel = (process.env['LOG_LEVEL'] ?? 'info') as DaemonConfig['logLevel'];

  if (!anthropicApiKey) {
    console.error('[CONFIG] WARNING: ANTHROPIC_API_KEY not set');
  }

  return {
    port,
    secret,
    anthropicApiKey,
    workspaceDir,
    logLevel,
  };
}

/** Global config instance */
let _config: DaemonConfig | null = null;

/**
 * Get the global configuration (lazy-loaded).
 */
export function getConfig(): DaemonConfig {
  if (!_config) {
    _config = loadConfig();
  }
  return _config;
}
