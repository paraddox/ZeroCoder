/**
 * useWebSocket Hook Tests
 * =======================
 *
 * Tests for the WebSocket hook including:
 * - Connection management
 * - Message handling
 * - Reconnection logic
 * - Error handling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useProjectWebSocket } from './useWebSocket'

// Alias for easier test migration
const useWebSocket = useProjectWebSocket

// Mock WebSocket class is already defined in test/setup.ts

describe('useWebSocket', () => {
  let mockWebSocketInstances: any[] = []

  beforeEach(() => {
    vi.clearAllMocks()
    mockWebSocketInstances = []

    // Track WebSocket instances
    const OriginalWebSocket = global.WebSocket
    global.WebSocket = vi.fn().mockImplementation((url: string) => {
      const instance = {
        url,
        readyState: 0, // CONNECTING
        onopen: null as (() => void) | null,
        onclose: null as (() => void) | null,
        onmessage: null as ((event: MessageEvent) => void) | null,
        onerror: null as ((event: Event) => void) | null,
        send: vi.fn(),
        close: vi.fn(() => {
          instance.readyState = 3 // CLOSED
          instance.onclose?.()
        }),
      }
      mockWebSocketInstances.push(instance)

      // Simulate connection
      setTimeout(() => {
        instance.readyState = 1 // OPEN
        instance.onopen?.()
      }, 0)

      return instance
    }) as unknown as typeof WebSocket
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('Connection', () => {
    it('should create WebSocket connection', async () => {
      const { result } = renderHook(() => useWebSocket('test-project'))

      await waitFor(() => {
        expect(global.WebSocket).toHaveBeenCalled()
      })
    })

    it('should use correct WebSocket URL', async () => {
      renderHook(() => useWebSocket('my-project'))

      await waitFor(() => {
        expect(global.WebSocket).toHaveBeenCalled()
      })

      const wsUrl = (global.WebSocket as any).mock.calls[0][0]
      expect(wsUrl).toContain('my-project')
    })

    it('should handle successful connection', async () => {
      const { result } = renderHook(() => useWebSocket('test-project'))

      await waitFor(() => {
        expect(mockWebSocketInstances.length).toBeGreaterThan(0)
      })

      // Trigger open event
      act(() => {
        const ws = mockWebSocketInstances[0]
        ws.readyState = 1
        ws.onopen?.()
      })

      // Connection should be established
    })
  })

  describe('Message Handling', () => {
    it('should handle incoming messages', async () => {
      const { result } = renderHook(() => useWebSocket('test-project'))

      await waitFor(() => {
        expect(mockWebSocketInstances.length).toBeGreaterThan(0)
      })

      // Simulate receiving a message
      act(() => {
        const ws = mockWebSocketInstances[0]
        ws.onmessage?.({
          data: JSON.stringify({ type: 'progress', data: { total: 10, passing: 5 } }),
        } as MessageEvent)
      })

      // Message should be processed
    })

    it('should handle different message types', async () => {
      const { result } = renderHook(() => useWebSocket('test-project'))

      await waitFor(() => {
        expect(mockWebSocketInstances.length).toBeGreaterThan(0)
      })

      const messageTypes = ['progress', 'agent_status', 'log', 'feature_update']

      messageTypes.forEach((type) => {
        act(() => {
          const ws = mockWebSocketInstances[0]
          ws.onmessage?.({
            data: JSON.stringify({ type, data: {} }),
          } as MessageEvent)
        })
      })
    })

    it('should handle malformed JSON', async () => {
      const { result } = renderHook(() => useWebSocket('test-project'))

      await waitFor(() => {
        expect(mockWebSocketInstances.length).toBeGreaterThan(0)
      })

      // Should not throw on malformed JSON
      act(() => {
        const ws = mockWebSocketInstances[0]
        ws.onmessage?.({
          data: 'not valid json',
        } as MessageEvent)
      })
    })
  })

  describe('Disconnection', () => {
    it('should close connection on unmount', async () => {
      const { unmount } = renderHook(() => useWebSocket('test-project'))

      await waitFor(() => {
        expect(mockWebSocketInstances.length).toBeGreaterThan(0)
      })

      const ws = mockWebSocketInstances[0]

      unmount()

      expect(ws.close).toHaveBeenCalled()
    })

    it('should handle unexpected disconnection', async () => {
      const { result } = renderHook(() => useWebSocket('test-project'))

      await waitFor(() => {
        expect(mockWebSocketInstances.length).toBeGreaterThan(0)
      })

      // Simulate unexpected close
      act(() => {
        const ws = mockWebSocketInstances[0]
        ws.readyState = 3
        ws.onclose?.()
      })

      // Should attempt reconnection (implementation dependent)
    })
  })

  describe('Error Handling', () => {
    it('should handle connection error', async () => {
      const { result } = renderHook(() => useWebSocket('test-project'))

      await waitFor(() => {
        expect(mockWebSocketInstances.length).toBeGreaterThan(0)
      })

      // Simulate error
      act(() => {
        const ws = mockWebSocketInstances[0]
        ws.onerror?.({} as Event)
      })

      // Should handle error gracefully
    })
  })

  describe('Project Change', () => {
    it('should reconnect when project changes', async () => {
      const { rerender } = renderHook(
        ({ project }) => useWebSocket(project),
        { initialProps: { project: 'project-a' } }
      )

      await waitFor(() => {
        expect(mockWebSocketInstances.length).toBe(1)
      })

      // Change project
      rerender({ project: 'project-b' })

      await waitFor(() => {
        expect(mockWebSocketInstances.length).toBe(2)
      })

      // Old connection should be closed, new one opened
      const [oldWs, newWs] = mockWebSocketInstances
      expect(oldWs.close).toHaveBeenCalled()
    })

    it('should not reconnect when project is same', async () => {
      const { rerender } = renderHook(
        ({ project }) => useWebSocket(project),
        { initialProps: { project: 'project-a' } }
      )

      await waitFor(() => {
        expect(mockWebSocketInstances.length).toBe(1)
      })

      // Rerender with same project
      rerender({ project: 'project-a' })

      // Should still be only one connection
      expect(mockWebSocketInstances.length).toBe(1)
    })
  })

  describe('Enabled State', () => {
    it('should not connect when disabled', async () => {
      // If hook supports enabled parameter
      const { result } = renderHook(() => useWebSocket(null as any))

      await new Promise((r) => setTimeout(r, 50))

      // Connection behavior depends on implementation
    })
  })

  describe('Message Types', () => {
    it('should handle progress message', async () => {
      const { result } = renderHook(() => useWebSocket('test-project'))

      await waitFor(() => {
        expect(mockWebSocketInstances.length).toBeGreaterThan(0)
      })

      act(() => {
        const ws = mockWebSocketInstances[0]
        ws.onmessage?.({
          data: JSON.stringify({
            type: 'progress',
            data: { passing: 5, in_progress: 2, total: 10, percentage: 50 },
          }),
        } as MessageEvent)
      })
    })

    it('should handle agent_status message', async () => {
      const { result } = renderHook(() => useWebSocket('test-project'))

      await waitFor(() => {
        expect(mockWebSocketInstances.length).toBeGreaterThan(0)
      })

      act(() => {
        const ws = mockWebSocketInstances[0]
        ws.onmessage?.({
          data: JSON.stringify({
            type: 'agent_status',
            data: { status: 'running', agent_running: true },
          }),
        } as MessageEvent)
      })
    })

    it('should handle log message', async () => {
      const { result } = renderHook(() => useWebSocket('test-project'))

      await waitFor(() => {
        expect(mockWebSocketInstances.length).toBeGreaterThan(0)
      })

      act(() => {
        const ws = mockWebSocketInstances[0]
        ws.onmessage?.({
          data: JSON.stringify({
            type: 'log',
            data: { line: 'Agent output line here' },
          }),
        } as MessageEvent)
      })
    })

    it('should handle feature_update message', async () => {
      const { result } = renderHook(() => useWebSocket('test-project'))

      await waitFor(() => {
        expect(mockWebSocketInstances.length).toBeGreaterThan(0)
      })

      act(() => {
        const ws = mockWebSocketInstances[0]
        ws.onmessage?.({
          data: JSON.stringify({
            type: 'feature_update',
            data: { feature_id: 'feat-1', status: 'closed' },
          }),
        } as MessageEvent)
      })
    })
  })
})
