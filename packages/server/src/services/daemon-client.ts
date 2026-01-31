/**
 * Daemon Client
 * =============
 *
 * Unified client for communicating with ZeroCoder daemons.
 * Works with both container daemons and remote machine daemons.
 */

/** Simple logger for daemon client */
const log = {
  info: (msg: string, data?: Record<string, unknown>) => console.log(`[DaemonClient] ${msg}`, data ?? ''),
  warn: (msg: string, data?: Record<string, unknown>) => console.warn(`[DaemonClient] ${msg}`, data ?? ''),
  debug: (msg: string, data?: Record<string, unknown>) => console.debug(`[DaemonClient] ${msg}`, data ?? ''),
  error: (msg: string, data?: Record<string, unknown>) => console.error(`[DaemonClient] ${msg}`, data ?? ''),
};

/** Daemon status response */
export interface DaemonStatus {
  status: 'idle' | 'running' | 'stopping' | 'stopped';
  current_repo: string | null;
  current_feature: string | null;
  agent_type: string | null;
  stats: {
    completed: number;
    remaining: number;
    total: number;
  } | null;
}

/** Health check response */
export interface HealthResponse {
  healthy: boolean;
  timestamp: string;
}

/** Work request response */
export interface WorkResponse {
  success: boolean;
  message: string;
  project_name?: string;
  project_path?: string;
}

/** Stop response */
export interface StopResponse {
  success: boolean;
  message: string;
}

/**
 * Client for communicating with a ZeroCoder daemon via HTTP API.
 */
export class DaemonClient {
  private baseUrl: string;
  private authToken?: string;
  private timeoutMs: number;

  constructor(baseUrl: string, authToken?: string, timeoutMs: number = 30000) {
    this.baseUrl = baseUrl.replace(/\/$/, ''); // Remove trailing slash
    this.authToken = authToken;
    this.timeoutMs = timeoutMs;
  }

  /**
   * Get the base URL of this daemon.
   */
  getBaseUrl(): string {
    return this.baseUrl;
  }

  /**
   * Build headers for requests.
   */
  private getHeaders(): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (this.authToken) {
      headers['Authorization'] = `Bearer ${this.authToken}`;
    }
    return headers;
  }

  /**
   * Make a GET request.
   */
  private async get<T>(path: string): Promise<T> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        method: 'GET',
        headers: this.getHeaders(),
        signal: controller.signal,
      });

      if (!response.ok) {
        const error = await response.text();
        throw new Error(`HTTP ${response.status}: ${error}`);
      }

      return response.json() as Promise<T>;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  /**
   * Make a POST request.
   */
  private async post<T>(path: string, body?: unknown): Promise<T> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        method: 'POST',
        headers: this.getHeaders(),
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });

      if (!response.ok) {
        const error = await response.text();
        throw new Error(`HTTP ${response.status}: ${error}`);
      }

      return response.json() as Promise<T>;
    } finally {
      clearTimeout(timeoutId);
    }
  }

  /**
   * Check if daemon is healthy.
   */
  async isHealthy(): Promise<boolean> {
    try {
      const response = await this.get<HealthResponse>('/health');
      return response.healthy === true;
    } catch (err) {
      log.debug('Health check failed', { error: err instanceof Error ? err.message : String(err) });
      return false;
    }
  }

  /**
   * Wait for daemon to become healthy.
   * @param maxAttempts - Maximum number of attempts
   * @param intervalMs - Interval between attempts in milliseconds
   */
  async waitForHealthy(maxAttempts: number = 30, intervalMs: number = 1000): Promise<boolean> {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      if (await this.isHealthy()) {
        log.info('Daemon is healthy', { baseUrl: this.baseUrl, attempt: attempt + 1 });
        return true;
      }
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
    log.warn('Daemon health check timed out', { baseUrl: this.baseUrl, maxAttempts });
    return false;
  }

  /**
   * Get current daemon status.
   */
  async getStatus(): Promise<DaemonStatus> {
    return this.get<DaemonStatus>('/status');
  }

  /**
   * Start work on a repository.
   * @param repoUrl - Git SSH URL to clone
   * @param projectName - Project identifier
   * @param sshKey - Optional SSH key (uses default if not provided)
   */
  async startWork(repoUrl: string, projectName: string, sshKey?: string): Promise<WorkResponse> {
    const body: Record<string, string> = {
      repo_url: repoUrl,
      project_name: projectName,
    };
    if (sshKey) {
      body['ssh_key'] = sshKey;
    }
    return this.post<WorkResponse>('/work', body);
  }

  /**
   * Request graceful stop (finish current session, then stop).
   */
  async stopGraceful(): Promise<StopResponse> {
    return this.post<StopResponse>('/stop/graceful');
  }

  /**
   * Request hard stop (immediate).
   */
  async stopHard(): Promise<StopResponse> {
    return this.post<StopResponse>('/stop/hard');
  }

  /**
   * Request daemon shutdown.
   */
  async shutdown(): Promise<StopResponse> {
    return this.post<StopResponse>('/shutdown');
  }
}

// =============================================================================
// Factory Functions
// =============================================================================

/** Base port for container daemons (container N uses port 19000 + N) */
const CONTAINER_DAEMON_BASE_PORT = 19000;

/**
 * Get the host port for a container's daemon.
 */
export function getContainerDaemonPort(containerNumber: number): number {
  return CONTAINER_DAEMON_BASE_PORT + containerNumber;
}

/**
 * Create a daemon client for a container.
 * @param containerNumber - The container number (1, 2, 3, etc.)
 */
export function createContainerDaemonClient(containerNumber: number): DaemonClient {
  const port = getContainerDaemonPort(containerNumber);
  return new DaemonClient(`http://localhost:${port}`);
}

/**
 * Create a daemon client for a remote machine.
 * @param host - Remote machine hostname or IP
 * @param port - Daemon port (default 9999)
 * @param token - Optional auth token
 */
export function createRemoteDaemonClient(
  host: string,
  port: number = 9999,
  token?: string
): DaemonClient {
  return new DaemonClient(`http://${host}:${port}`, token);
}
