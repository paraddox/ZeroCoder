/**
 * WebSocket Hook for Real-time Updates
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import type { WSMessage, AgentStatus } from '../lib/types'

export interface LogEntry {
  line: string
  timestamp: string
  container_number?: number
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
  isConnected: boolean
  gracefulStopRequested: boolean
}

const MAX_LOGS = 100 // Keep last 100 log lines

export function useProjectWebSocket(projectName: string | null) {
  const [state, setState] = useState<WebSocketState>({
    progress: { passing: 0, in_progress: 0, total: 0, percentage: 0 },
    agentStatus: 'stopped',
    logs: [],
    isConnected: false,
    gracefulStopRequested: false,
  })

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const reconnectAttempts = useRef(0)
  const hasConnectedRef = useRef(false) // Track if we've ever successfully connected
  const shouldReconnectRef = useRef(true) // Whether to auto-reconnect
  const logCacheRef = useRef<Record<string, Array<{ line: string; timestamp: string }>>>({}) // Cache logs per project

  const connect = useCallback(() => {
    if (!projectName || !shouldReconnectRef.current) return

    // Build WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${protocol}//${host}/ws/projects/${encodeURIComponent(projectName)}`

    try {
      const ws = new WebSocket(wsUrl)
      wsRef.current = ws

      ws.onopen = () => {
        setState(prev => ({ ...prev, isConnected: true }))
        reconnectAttempts.current = 0
        hasConnectedRef.current = true
      }

      ws.onmessage = (event) => {
        try {
          const message: WSMessage = JSON.parse(event.data)

          switch (message.type) {
            case 'progress':
              setState(prev => ({
                ...prev,
                progress: {
                  passing: message.passing,
                  in_progress: message.in_progress,
                  total: message.total,
                  percentage: message.percentage,
                },
              }))
              break

            case 'agent_status':
              setState(prev => ({
                ...prev,
                agentStatus: message.status,
                // Reset gracefulStopRequested when agent stops
                gracefulStopRequested: message.status === 'running' ? prev.gracefulStopRequested : false,
              }))
              break

            case 'log': {
              const logEntry: LogEntry = {
                line: message.line,
                timestamp: message.timestamp,
                container_number: message.container_number,
              }
              setState(prev => {
                const newLogs = [...prev.logs, logEntry]
                // Keep last 100 logs
                const trimmedLogs = newLogs.slice(-MAX_LOGS)

                // Update cache for current project
                if (projectName) {
                  logCacheRef.current[projectName] = trimmedLogs
                }

                return { ...prev, logs: trimmedLogs }
              })
              break
            }

            case 'graceful_stop_requested':
              setState(prev => ({
                ...prev,
                gracefulStopRequested: message.graceful_stop_requested,
              }))
              break

            case 'feature_update':
              // Feature updates will trigger a refetch via React Query
              break

            case 'pong':
              // Heartbeat response
              break
          }
        } catch {
          console.error('Failed to parse WebSocket message')
        }
      }

      ws.onclose = () => {
        setState(prev => ({ ...prev, isConnected: false }))
        wsRef.current = null

        // Only reconnect if we've successfully connected before
        // This prevents infinite reconnect loops for deleted/invalid projects
        if (!hasConnectedRef.current) {
          console.log(`WebSocket: Initial connection to ${projectName} failed, not reconnecting`)
          shouldReconnectRef.current = false
          return
        }

        if (!shouldReconnectRef.current) return

        // Exponential backoff reconnection (max 5 attempts)
        if (reconnectAttempts.current >= 5) {
          console.log(`WebSocket: Max reconnection attempts reached for ${projectName}`)
          return
        }

        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts.current), 30000)
        reconnectAttempts.current++

        reconnectTimeoutRef.current = window.setTimeout(() => {
          connect()
        }, delay)
      }

      ws.onerror = () => {
        ws.close()
      }
    } catch {
      // Failed to connect, will retry via onclose
    }
  }, [projectName])

  // Send ping to keep connection alive
  const sendPing = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'ping' }))
    }
  }, [])

  // Connect when project changes
  useEffect(() => {
    // Reset refs for new project
    hasConnectedRef.current = false
    shouldReconnectRef.current = true
    reconnectAttempts.current = 0

    if (!projectName) {
      // No project selected - clear logs
      setState(prev => ({ ...prev, logs: [] }))
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      return
    }

    // Restore cached logs for this project (or empty array)
    setState(prev => ({
      ...prev,
      logs: logCacheRef.current[projectName] || [],
    }))

    connect()

    // Ping every 30 seconds
    const pingInterval = setInterval(sendPing, 30000)

    return () => {
      clearInterval(pingInterval)
      shouldReconnectRef.current = false // Prevent reconnect on cleanup
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [projectName, connect, sendPing])

  // Clear logs function
  const clearLogs = useCallback(() => {
    setState(prev => ({ ...prev, logs: [] }))
    // Also clear from cache
    if (projectName) {
      logCacheRef.current[projectName] = []
    }
  }, [projectName])

  return {
    ...state,
    clearLogs,
  }
}
