/**
 * Log Streamer Service
 * ====================
 *
 * Docker log streaming using dockerode with output sanitization,
 * log parsing, and WebSocket streaming integration.
 *
 * Features:
 * - Real-time Docker log streaming via dockerode
 * - Sensitive data sanitization (API keys, tokens, passwords)
 * - Log format parsing (timestamps, levels, sources)
 * - Feature detection (claim/close patterns)
 * - Callback-based output for WebSocket integration
 * - Automatic reconnection on stream failure
 */

import Docker from 'dockerode';
import { EventEmitter } from 'node:events';
import type { Readable } from 'node:stream';

// =============================================================================
// Types
// =============================================================================

/** Log entry with parsed metadata */
export interface LogEntry {
  /** Raw log line (sanitized) */
  line: string;
  /** ISO timestamp */
  timestamp: string;
  /** Log source: stdout or stderr */
  source: 'stdout' | 'stderr';
  /** Container name */
  containerName: string;
  /** Parsed log level if detected */
  level?: 'debug' | 'info' | 'warn' | 'error';
  /** Feature ID if detected in line */
  featureId?: string;
  /** Feature action if detected */
  featureAction?: 'claim' | 'close' | 'update';
}

/** Log streaming options */
export interface LogStreamOptions {
  /** Follow logs in real-time (default: true) */
  follow?: boolean;
  /** Include timestamps in log output (default: true) */
  timestamps?: boolean;
  /** Number of lines to tail from end (default: 0 = all) */
  tail?: number | 'all';
  /** Start streaming from this timestamp */
  since?: number;
  /** Stop streaming at this timestamp */
  until?: number;
  /** Stream stdout (default: true) */
  stdout?: boolean;
  /** Stream stderr (default: true) */
  stderr?: boolean;
}

/** Log callback type */
export type LogCallback = (entry: LogEntry) => void | Promise<void>;

/** Feature callback type */
export type FeatureCallback = (
  action: 'claim' | 'close' | 'update',
  featureId: string,
  line: string
) => void | Promise<void>;

/** Error callback type */
export type ErrorCallback = (error: Error) => void | Promise<void>;

// =============================================================================
// Sensitive Data Patterns
// =============================================================================

const SENSITIVE_PATTERNS: RegExp[] = [
  // Anthropic API keys
  /sk-ant[a-zA-Z0-9_-]*/gi,
  // Generic sk- prefixed keys (OpenAI, etc.)
  /sk-[a-zA-Z0-9]{20,}/gi,
  // Environment variable patterns
  /ANTHROPIC_API_KEY=[^\s]+/gi,
  /OPENAI_API_KEY=[^\s]+/gi,
  /CLAUDE_CODE_OAUTH_TOKEN=[^\s]+/gi,
  /ZHIPU_API_KEY=[^\s]+/gi,
  /MINIMAX_API_KEY=[^\s]+/gi,
  // Generic sensitive patterns
  /api[_-]?key[=:]\s*["']?[^\s"']+["']?/gi,
  /token[=:]\s*["']?[^\s"']+["']?/gi,
  /password[=:]\s*["']?[^\s"']+["']?/gi,
  /secret[=:]\s*["']?[^\s"']+["']?/gi,
  /credential[s]?[=:]\s*["']?[^\s"']+["']?/gi,
  // Bearer tokens
  /Bearer\s+[a-zA-Z0-9_.-]+/gi,
  // Base64 encoded secrets (common patterns)
  /eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+/g, // JWT tokens
];

// =============================================================================
// Feature Detection Patterns
// =============================================================================

const FEATURE_PATTERNS = {
  claim: [
    /Claimed ([\w]+-[\w.]+),/i,
    /Working on feature:\s*([\w]+-[\w.]+)/i,
    /Starting work on\s*([\w]+-[\w.]+)/i,
    /bd update\s+([\w]+-[\w.]+)\s+--status=in_progress/i,
  ],
  close: [
    /bd close\s+([\w]+-[\w.]+)/i,
    /Completed feature:\s*([\w]+-[\w.]+)/i,
    /Closed\s+([\w]+-[\w.]+)/i,
    /✓ Closed\s+([\w]+-[\w.]+)/i,
  ],
  update: [
    /bd update\s+([\w]+-[\w.]+)/i,
    /Updated issue:\s*([\w]+-[\w.]+)/i,
  ],
};

// =============================================================================
// Log Level Detection
// =============================================================================

const LOG_LEVEL_PATTERNS: Record<LogEntry['level'] & string, RegExp[]> = {
  error: [/\berror\b/i, /\bfatal\b/i, /\bexception\b/i, /\bfailed\b/i],
  warn: [/\bwarn(?:ing)?\b/i, /\bcaution\b/i],
  info: [/\binfo\b/i, /\bnotice\b/i],
  debug: [/\bdebug\b/i, /\btrace\b/i, /\bverbose\b/i],
};

// =============================================================================
// Helper Functions
// =============================================================================

/**
 * Sanitize log output to remove sensitive information.
 * This is a more comprehensive version that includes additional patterns
 * for log-specific sensitive data.
 */
function sanitizeLogOutput(line: string): string {
  let result = line;
  for (const pattern of SENSITIVE_PATTERNS) {
    // Reset lastIndex for global patterns
    pattern.lastIndex = 0;
    result = result.replace(pattern, '[REDACTED]');
  }
  return result;
}

/**
 * Detect log level from line content.
 */
function detectLogLevel(line: string): LogEntry['level'] | undefined {
  for (const [level, patterns] of Object.entries(LOG_LEVEL_PATTERNS)) {
    for (const pattern of patterns) {
      if (pattern.test(line)) {
        return level as LogEntry['level'];
      }
    }
  }
  return undefined;
}

/**
 * Detect feature action and ID from line content.
 */
function detectFeature(
  line: string
): { action: 'claim' | 'close' | 'update'; featureId: string } | null {
  for (const [action, patterns] of Object.entries(FEATURE_PATTERNS)) {
    for (const pattern of patterns) {
      const match = line.match(pattern);
      if (match?.[1]) {
        return {
          action: action as 'claim' | 'close' | 'update',
          featureId: match[1],
        };
      }
    }
  }
  return null;
}

/**
 * Parse Docker log stream header.
 * Docker multiplexes stdout/stderr with an 8-byte header:
 * [stream_type(1)][0(3)][size(4)][payload(size)]
 */
function parseDockerLogHeader(buffer: Buffer): {
  source: 'stdout' | 'stderr';
  size: number;
} | null {
  if (buffer.length < 8) return null;

  const streamType = buffer[0];
  const size = buffer.readUInt32BE(4);

  return {
    source: streamType === 1 ? 'stdout' : 'stderr',
    size,
  };
}

// =============================================================================
// LogStreamer Class
// =============================================================================

/**
 * Streams Docker container logs with sanitization and parsing.
 *
 * @example
 * ```typescript
 * const streamer = new LogStreamer('my-container');
 *
 * streamer.onLog((entry) => {
 *   console.log(`[${entry.source}] ${entry.line}`);
 * });
 *
 * streamer.onFeature((action, featureId) => {
 *   console.log(`Feature ${action}: ${featureId}`);
 * });
 *
 * await streamer.start();
 * ```
 */
export class LogStreamer extends EventEmitter {
  private readonly docker: Docker;
  private readonly containerName: string;
  private _isStreaming = false;
  private _stream: Readable | null = null;
  private _abortController: AbortController | null = null;
  private _reconnectAttempts = 0;
  private _maxReconnectAttempts = 5;
  private _reconnectDelay = 1000;

  // Callbacks
  private _logCallbacks: LogCallback[] = [];
  private _featureCallbacks: FeatureCallback[] = [];
  private _errorCallbacks: ErrorCallback[] = [];

  // Line buffer for handling partial lines
  private _lineBuffer = '';

  constructor(containerName: string, docker?: Docker) {
    super();
    this.containerName = containerName;
    this.docker = docker || new Docker();
  }

  // ===========================================================================
  // Public Properties
  // ===========================================================================

  get isStreaming(): boolean {
    return this._isStreaming;
  }

  // ===========================================================================
  // Callback Management
  // ===========================================================================

  /**
   * Register a callback for log entries.
   */
  onLog(callback: LogCallback): void {
    this._logCallbacks.push(callback);
  }

  /**
   * Remove a log callback.
   */
  offLog(callback: LogCallback): void {
    const index = this._logCallbacks.indexOf(callback);
    if (index !== -1) {
      this._logCallbacks.splice(index, 1);
    }
  }

  /**
   * Register a callback for feature detection.
   */
  onFeature(callback: FeatureCallback): void {
    this._featureCallbacks.push(callback);
  }

  /**
   * Remove a feature callback.
   */
  offFeature(callback: FeatureCallback): void {
    const index = this._featureCallbacks.indexOf(callback);
    if (index !== -1) {
      this._featureCallbacks.splice(index, 1);
    }
  }

  /**
   * Register a callback for errors.
   */
  onError(callback: ErrorCallback): void {
    this._errorCallbacks.push(callback);
  }

  /**
   * Remove an error callback.
   */
  offError(callback: ErrorCallback): void {
    const index = this._errorCallbacks.indexOf(callback);
    if (index !== -1) {
      this._errorCallbacks.splice(index, 1);
    }
  }

  // ===========================================================================
  // Streaming Control
  // ===========================================================================

  /**
   * Start streaming logs from the container.
   */
  async start(options: LogStreamOptions = {}): Promise<void> {
    if (this._isStreaming) {
      return;
    }

    const {
      follow = true,
      timestamps = true,
      tail = 0,
      since,
      until,
      stdout = true,
      stderr = true,
    } = options;

    this._isStreaming = true;
    this._abortController = new AbortController();
    this._reconnectAttempts = 0;

    try {
      const container = this.docker.getContainer(this.containerName);

      // Get log stream - use follow: true to get a ReadableStream
      const logOptions = {
        follow: true as const,
        timestamps,
        tail: tail === 'all' ? undefined : tail,
        since,
        until,
        stdout,
        stderr,
      };

      // When follow is true, dockerode returns a ReadableStream
      const stream = follow
        ? await container.logs(logOptions)
        : await container.logs({ ...logOptions, follow: false as const });

      this._stream = stream as unknown as Readable;
      this._setupStreamHandlers();

      this.emit('started');
    } catch (error) {
      this._isStreaming = false;
      const err = error instanceof Error ? error : new Error(String(error));
      await this._broadcastError(err);
      throw err;
    }
  }

  /**
   * Stop streaming logs.
   */
  async stop(): Promise<void> {
    if (!this._isStreaming) {
      return;
    }

    this._isStreaming = false;
    this._abortController?.abort();
    this._abortController = null;

    if (this._stream) {
      this._stream.destroy();
      this._stream = null;
    }

    this._lineBuffer = '';
    this.emit('stopped');
  }

  // ===========================================================================
  // Private Methods
  // ===========================================================================

  private _setupStreamHandlers(): void {
    if (!this._stream) return;

    // Handle the dockerode stream which may or may not be multiplexed
    this._stream.on('data', (chunk: Buffer) => {
      this._processChunk(chunk);
    });

    this._stream.on('end', () => {
      // Process any remaining data in buffer
      if (this._lineBuffer) {
        this._processLine(this._lineBuffer, 'stdout');
        this._lineBuffer = '';
      }

      if (this._isStreaming) {
        // Stream ended unexpectedly, try to reconnect
        this._handleReconnect();
      }
    });

    this._stream.on('error', async (error: Error) => {
      await this._broadcastError(error);

      if (this._isStreaming) {
        this._handleReconnect();
      }
    });

    // Handle abort
    this._abortController?.signal.addEventListener('abort', () => {
      this._stream?.destroy();
    });
  }

  private _processChunk(chunk: Buffer): void {
    // Docker logs can be either:
    // 1. Raw text (when TTY is enabled)
    // 2. Multiplexed with 8-byte headers (when TTY is disabled)

    let offset = 0;

    while (offset < chunk.length) {
      // Try to parse as multiplexed stream
      const header = parseDockerLogHeader(chunk.subarray(offset));

      if (header && offset + 8 + header.size <= chunk.length) {
        // Multiplexed format
        const payload = chunk.subarray(offset + 8, offset + 8 + header.size);
        this._processPayload(payload.toString('utf-8'), header.source);
        offset += 8 + header.size;
      } else {
        // Raw format or incomplete header - treat as raw text
        const text = chunk.subarray(offset).toString('utf-8');
        this._processPayload(text, 'stdout');
        break;
      }
    }
  }

  private _processPayload(text: string, source: 'stdout' | 'stderr'): void {
    // Add to buffer and process complete lines
    this._lineBuffer += text;

    const lines = this._lineBuffer.split('\n');

    // Keep the last incomplete line in buffer
    this._lineBuffer = lines.pop() || '';

    // Process complete lines
    for (const line of lines) {
      if (line.trim()) {
        this._processLine(line, source);
      }
    }
  }

  private _processLine(line: string, source: 'stdout' | 'stderr'): void {
    // Sanitize the line
    const sanitizedLine = sanitizeLogOutput(line);

    // Parse timestamp if present (Docker format: 2024-01-15T10:30:00.000000000Z)
    let timestamp = new Date().toISOString();
    let content = sanitizedLine;

    const timestampMatch = sanitizedLine.match(
      /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s+(.*)$/
    );
    if (timestampMatch) {
      timestamp = timestampMatch[1] || timestamp;
      content = timestampMatch[2] || sanitizedLine;
    }

    // Detect log level
    const level = detectLogLevel(content);

    // Detect feature action
    const feature = detectFeature(content);

    // Create log entry
    const entry: LogEntry = {
      line: content,
      timestamp,
      source,
      containerName: this.containerName,
      level,
      featureId: feature?.featureId,
      featureAction: feature?.action,
    };

    // Broadcast to callbacks
    this._broadcastLog(entry);

    // Broadcast feature action if detected
    if (feature) {
      this._broadcastFeature(feature.action, feature.featureId, content);
    }
  }

  private async _broadcastLog(entry: LogEntry): Promise<void> {
    this.emit('log', entry);

    for (const callback of this._logCallbacks) {
      try {
        await callback(entry);
      } catch (error) {
        console.error('Log callback error:', error);
      }
    }
  }

  private async _broadcastFeature(
    action: 'claim' | 'close' | 'update',
    featureId: string,
    line: string
  ): Promise<void> {
    this.emit('feature', action, featureId, line);

    for (const callback of this._featureCallbacks) {
      try {
        await callback(action, featureId, line);
      } catch (error) {
        console.error('Feature callback error:', error);
      }
    }
  }

  private async _broadcastError(error: Error): Promise<void> {
    this.emit('error', error);

    for (const callback of this._errorCallbacks) {
      try {
        await callback(error);
      } catch (e) {
        console.error('Error callback error:', e);
      }
    }
  }

  private async _handleReconnect(): Promise<void> {
    if (!this._isStreaming) return;
    if (this._reconnectAttempts >= this._maxReconnectAttempts) {
      console.error(
        `Max reconnect attempts (${this._maxReconnectAttempts}) reached for ${this.containerName}`
      );
      await this.stop();
      return;
    }

    this._reconnectAttempts++;
    const delay = this._reconnectDelay * Math.pow(2, this._reconnectAttempts - 1);

    console.log(
      `Reconnecting to ${this.containerName} in ${delay}ms (attempt ${this._reconnectAttempts}/${this._maxReconnectAttempts})`
    );

    await new Promise((resolve) => setTimeout(resolve, delay));

    if (!this._isStreaming) return;

    try {
      // Clean up old stream
      if (this._stream) {
        this._stream.destroy();
        this._stream = null;
      }

      // Restart from current time
      await this.start({ since: Math.floor(Date.now() / 1000) });
      this._reconnectAttempts = 0;
    } catch (error) {
      console.error(`Reconnect failed for ${this.containerName}:`, error);
      this._handleReconnect();
    }
  }
}

// =============================================================================
// Singleton Docker Instance
// =============================================================================

let _dockerInstance: Docker | null = null;

/**
 * Get or create the shared Docker instance.
 */
export function getDockerInstance(): Docker {
  if (!_dockerInstance) {
    _dockerInstance = new Docker();
  }
  return _dockerInstance;
}

// =============================================================================
// Factory Function
// =============================================================================

/**
 * Create a log streamer for a container.
 */
export function createLogStreamer(containerName: string): LogStreamer {
  return new LogStreamer(containerName, getDockerInstance());
}

// =============================================================================
// Utility Functions
// =============================================================================

/**
 * Check if a Docker container exists.
 */
export async function containerExists(containerName: string): Promise<boolean> {
  const docker = getDockerInstance();
  try {
    const container = docker.getContainer(containerName);
    await container.inspect();
    return true;
  } catch {
    return false;
  }
}

/**
 * Check if a Docker container is running.
 */
export async function isContainerRunning(containerName: string): Promise<boolean> {
  const docker = getDockerInstance();
  try {
    const container = docker.getContainer(containerName);
    const info = await container.inspect();
    return info.State.Running;
  } catch {
    return false;
  }
}

/**
 * Get recent logs from a container (non-streaming).
 */
export async function getRecentLogs(
  containerName: string,
  lines: number = 100
): Promise<LogEntry[]> {
  const docker = getDockerInstance();
  const container = docker.getContainer(containerName);

  const logs = await container.logs({
    follow: false,
    timestamps: true,
    tail: lines,
    stdout: true,
    stderr: true,
  });

  const entries: LogEntry[] = [];
  const text = logs.toString('utf-8');
  const logLines = text.split('\n');

  for (const line of logLines) {
    if (!line.trim()) continue;

    const sanitizedLine = sanitizeLogOutput(line);
    let timestamp = new Date().toISOString();
    let content = sanitizedLine;

    const timestampMatch = sanitizedLine.match(
      /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s+(.*)$/
    );
    if (timestampMatch) {
      timestamp = timestampMatch[1] || timestamp;
      content = timestampMatch[2] || sanitizedLine;
    }

    entries.push({
      line: content,
      timestamp,
      source: 'stdout',
      containerName,
      level: detectLogLevel(content),
    });
  }

  return entries;
}
