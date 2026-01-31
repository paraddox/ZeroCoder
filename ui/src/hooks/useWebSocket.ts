/**
 * WebSocket Hook for Real-time Updates
 *
 * NOTE: WebSocket functionality is disabled. This hook returns static state.
 * Real-time updates are handled via API polling instead.
 */

import { useState, useCallback } from 'react'
import type { AgentStatus } from '@zerocoder/shared'

export interface LogEntry {
  line: string
  timestamp: string
  container_number?: number
}

export interface ContainerInfo {
  number: number
  type: 'init' | 'coding'
  agent_type?: 'coder' | 'initializer' | 'overseer'
  sdk_type?: 'claude' | 'opencode'
}

interface WebSocketState {
  progress: {
    passing: number
    in_progress: number
    total: number
    percentage: number
  }
  agentStatus: AgentStatus
  logs: LogEntry[]
  containers: ContainerInfo[]
  isConnected: boolean
  gracefulStopRequested: boolean
  containerUpdateCounter: number
}

/**
 * Hook that provides WebSocket-like state interface.
 * WebSocket is disabled - returns static state.
 * Real-time updates are handled via API polling in React Query hooks.
 */
export function useWebSocket(_projectName: string | null) {
  const [state] = useState<WebSocketState>({
    progress: { passing: 0, in_progress: 0, total: 0, percentage: 0 },
    agentStatus: 'stopped',
    logs: [],
    containers: [],
    isConnected: false,
    gracefulStopRequested: false,
    containerUpdateCounter: 0,
  })

  const clearLogs = useCallback(() => {
    // No-op - logs are not managed by this hook
  }, [])

  return {
    ...state,
    clearLogs,
  }
}

export const useProjectWebSocket = useWebSocket
