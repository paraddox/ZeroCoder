/**
 * Structured Logger
 * =================
 *
 * Simple structured logging for the daemon.
 */

import { getConfig } from './config.js';

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

/**
 * Get ISO timestamp for logging.
 */
function getTimestamp(): string {
  return new Date().toISOString();
}

/**
 * Format a log message.
 */
function formatMessage(level: LogLevel, component: string, message: string, data?: Record<string, unknown>): string {
  const timestamp = getTimestamp();
  const dataStr = data ? ` ${JSON.stringify(data)}` : '';
  return `[${timestamp}] [${level.toUpperCase()}] [${component}] ${message}${dataStr}`;
}

/**
 * Check if a log level should be output.
 */
function shouldLog(level: LogLevel): boolean {
  const config = getConfig();
  return LOG_LEVELS[level] >= LOG_LEVELS[config.logLevel];
}

/**
 * Create a logger for a specific component.
 */
export function createLogger(component: string) {
  return {
    debug(message: string, data?: Record<string, unknown>): void {
      if (shouldLog('debug')) {
        console.log(formatMessage('debug', component, message, data));
      }
    },

    info(message: string, data?: Record<string, unknown>): void {
      if (shouldLog('info')) {
        console.log(formatMessage('info', component, message, data));
      }
    },

    warn(message: string, data?: Record<string, unknown>): void {
      if (shouldLog('warn')) {
        console.warn(formatMessage('warn', component, message, data));
      }
    },

    error(message: string, data?: Record<string, unknown>): void {
      if (shouldLog('error')) {
        console.error(formatMessage('error', component, message, data));
      }
    },
  };
}

/** Default logger */
export const logger = createLogger('daemon');
