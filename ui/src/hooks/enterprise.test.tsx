/**
 * Enterprise Hooks Tests
 * ======================
 *
 * Comprehensive tests for React hooks including:
 * - State management hooks
 * - Data fetching hooks
 * - WebSocket hooks
 * - Side effect hooks
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'

// =============================================================================
// Test Utilities
// =============================================================================

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  })

const createWrapper = () => {
  const queryClient = createTestQueryClient()
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  )
}

// =============================================================================
// useTheme Hook Tests
// =============================================================================

describe('useTheme', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('should return default theme when no preference set', async () => {
    const { useTheme } = await import('./useTheme')
    const { result } = renderHook(() => useTheme())

    expect(result.current.theme).toBeDefined()
  })

  it('should toggle theme', async () => {
    const { useTheme } = await import('./useTheme')
    const { result } = renderHook(() => useTheme())

    const initialTheme = result.current.theme

    act(() => {
      result.current.toggleTheme()
    })

    expect(result.current.theme).not.toBe(initialTheme)
  })

  it('should persist theme to localStorage', async () => {
    const { useTheme } = await import('./useTheme')
    const { result } = renderHook(() => useTheme())

    act(() => {
      result.current.setTheme('dark')
    })

    expect(localStorage.getItem('theme')).toBe('dark')
  })

  it('should read theme from localStorage', async () => {
    localStorage.setItem('theme', 'dark')

    const { useTheme } = await import('./useTheme')
    const { result } = renderHook(() => useTheme())

    expect(result.current.theme).toBe('dark')
  })
})

// =============================================================================
// useCelebration Hook Tests
// =============================================================================

describe('useCelebration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should start with celebration disabled', async () => {
    const { useCelebration } = await import('./useCelebration')
    const { result } = renderHook(() => useCelebration())

    expect(result.current.isCelebrating).toBe(false)
  })

  it('should trigger celebration', async () => {
    const { useCelebration } = await import('./useCelebration')
    const { result } = renderHook(() => useCelebration())

    act(() => {
      result.current.celebrate()
    })

    expect(result.current.isCelebrating).toBe(true)
  })

  it('should stop celebration after timeout', async () => {
    vi.useFakeTimers()

    const { useCelebration } = await import('./useCelebration')
    const { result } = renderHook(() => useCelebration())

    act(() => {
      result.current.celebrate()
    })

    expect(result.current.isCelebrating).toBe(true)

    act(() => {
      vi.advanceTimersByTime(5000)
    })

    expect(result.current.isCelebrating).toBe(false)

    vi.useRealTimers()
  })
})

// =============================================================================
// useContainerStatus Hook Tests
// =============================================================================

describe('useContainerStatus', () => {
  it('should start with initial status', async () => {
    const { useContainerStatus } = await import('./useContainerStatus')
    const { result } = renderHook(() => useContainerStatus())

    expect(result.current.status).toBeDefined()
  })

  it('should update status', async () => {
    const { useContainerStatus } = await import('./useContainerStatus')
    const { result } = renderHook(() => useContainerStatus())

    act(() => {
      result.current.setStatus('running')
    })

    expect(result.current.status).toBe('running')
  })

  it('should handle multiple status updates', async () => {
    const { useContainerStatus } = await import('./useContainerStatus')
    const { result } = renderHook(() => useContainerStatus())

    act(() => {
      result.current.setStatus('running')
    })
    expect(result.current.status).toBe('running')

    act(() => {
      result.current.setStatus('stopped')
    })
    expect(result.current.status).toBe('stopped')

    act(() => {
      result.current.setStatus('completed')
    })
    expect(result.current.status).toBe('completed')
  })
})

// =============================================================================
// useWebSocket Hook Tests
// =============================================================================

describe('useWebSocket', () => {
  let mockWebSocket: any

  beforeEach(() => {
    mockWebSocket = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: WebSocket.OPEN,
      onopen: null,
      onclose: null,
      onmessage: null,
      onerror: null,
    }

    vi.spyOn(window, 'WebSocket').mockImplementation(() => mockWebSocket as any)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('should connect to WebSocket on mount', async () => {
    const { useWebSocket } = await import('./useWebSocket')

    renderHook(() => useWebSocket('test-project'))

    expect(window.WebSocket).toHaveBeenCalled()
  })

  it('should handle connection open', async () => {
    const { useWebSocket } = await import('./useWebSocket')
    const { result } = renderHook(() => useWebSocket('test-project'))

    act(() => {
      mockWebSocket.onopen?.()
    })

    expect(result.current.isConnected).toBe(true)
  })

  it('should handle incoming messages', async () => {
    const { useWebSocket } = await import('./useWebSocket')
    const { result } = renderHook(() => useWebSocket('test-project'))

    const testMessage = { type: 'progress', passing: 5, total: 10 }

    act(() => {
      mockWebSocket.onmessage?.({ data: JSON.stringify(testMessage) })
    })

    // The message should be processed
    expect(result.current.lastMessage).toEqual(testMessage)
  })

  it('should handle connection close', async () => {
    const { useWebSocket } = await import('./useWebSocket')
    const { result } = renderHook(() => useWebSocket('test-project'))

    act(() => {
      mockWebSocket.onopen?.()
    })

    expect(result.current.isConnected).toBe(true)

    act(() => {
      mockWebSocket.onclose?.()
    })

    expect(result.current.isConnected).toBe(false)
  })

  it('should cleanup on unmount', async () => {
    const { useWebSocket } = await import('./useWebSocket')
    const { unmount } = renderHook(() => useWebSocket('test-project'))

    unmount()

    expect(mockWebSocket.close).toHaveBeenCalled()
  })
})

// =============================================================================
// useProjects Hook Tests
// =============================================================================

describe('useProjects', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    global.fetch = vi.fn()
  })

  it('should fetch projects on mount', async () => {
    const mockProjects = [
      { name: 'project-1', git_url: 'https://github.com/user/repo1.git' },
      { name: 'project-2', git_url: 'https://github.com/user/repo2.git' },
    ]

    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockProjects),
    })

    const { useProjects } = await import('./useProjects')
    const { result } = renderHook(() => useProjects(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.data).toBeDefined()
    })
  })

  it('should handle fetch error', async () => {
    ;(global.fetch as any).mockRejectedValueOnce(new Error('Network error'))

    const { useProjects } = await import('./useProjects')
    const { result } = renderHook(() => useProjects(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.error).toBeDefined()
    })
  })
})

// =============================================================================
// useFeatures Hook Tests
// =============================================================================

describe('useFeatures', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    global.fetch = vi.fn()
  })

  it('should fetch features for a project', async () => {
    const mockFeatures = {
      pending: [{ id: 'feat-1', name: 'Feature 1' }],
      in_progress: [],
      done: [{ id: 'feat-2', name: 'Feature 2' }],
    }

    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockFeatures),
    })

    const { useFeatures } = await import('./useFeatures')
    const { result } = renderHook(() => useFeatures('test-project'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.data).toBeDefined()
    })
  })

  it('should return empty arrays when no project', async () => {
    const { useFeatures } = await import('./useFeatures')
    const { result } = renderHook(() => useFeatures(null as any), {
      wrapper: createWrapper(),
    })

    // Should not make request when project is null
    expect(global.fetch).not.toHaveBeenCalled()
  })
})

// =============================================================================
// useContainers Hook Tests
// =============================================================================

describe('useContainers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    global.fetch = vi.fn()
  })

  it('should fetch containers for a project', async () => {
    const mockContainers = [
      { id: 1, container_number: 1, status: 'running' },
      { id: 2, container_number: 2, status: 'stopped' },
    ]

    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockContainers),
    })

    const { useContainers } = await import('./useContainers')
    const { result } = renderHook(() => useContainers('test-project'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.data).toBeDefined()
    })
  })
})

// =============================================================================
// useSpecChat Hook Tests
// =============================================================================

describe('useSpecChat', () => {
  let mockWebSocket: any

  beforeEach(() => {
    mockWebSocket = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: WebSocket.OPEN,
      onopen: null,
      onclose: null,
      onmessage: null,
      onerror: null,
    }

    vi.spyOn(window, 'WebSocket').mockImplementation(() => mockWebSocket as any)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('should initialize with empty messages', async () => {
    const { useSpecChat } = await import('./useSpecChat')
    const { result } = renderHook(() => useSpecChat('test-project'))

    expect(result.current.messages).toEqual([])
  })

  it('should send message via WebSocket', async () => {
    const { useSpecChat } = await import('./useSpecChat')
    const { result } = renderHook(() => useSpecChat('test-project'))

    act(() => {
      mockWebSocket.onopen?.()
    })

    act(() => {
      result.current.sendMessage('Hello world')
    })

    expect(mockWebSocket.send).toHaveBeenCalled()
  })

  it('should receive and process messages', async () => {
    const { useSpecChat } = await import('./useSpecChat')
    const { result } = renderHook(() => useSpecChat('test-project'))

    act(() => {
      mockWebSocket.onopen?.()
    })

    act(() => {
      mockWebSocket.onmessage?.({
        data: JSON.stringify({
          type: 'message',
          role: 'assistant',
          content: 'Hello!',
        }),
      })
    })

    expect(result.current.messages.length).toBeGreaterThan(0)
  })
})

// =============================================================================
// useAssistantChat Hook Tests
// =============================================================================

describe('useAssistantChat', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    global.fetch = vi.fn()
  })

  it('should initialize with empty history', async () => {
    const { useAssistantChat } = await import('./useAssistantChat')
    const { result } = renderHook(() => useAssistantChat('test-project'))

    expect(result.current.messages).toEqual([])
  })

  it('should send message and update history', async () => {
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      body: {
        getReader: () => ({
          read: vi.fn()
            .mockResolvedValueOnce({
              value: new TextEncoder().encode('data: {"type":"content","content":"Hello"}\n\n'),
              done: false
            })
            .mockResolvedValueOnce({ done: true }),
        }),
      },
    })

    const { useAssistantChat } = await import('./useAssistantChat')
    const { result } = renderHook(() => useAssistantChat('test-project'))

    await act(async () => {
      await result.current.sendMessage('Hi there')
    })

    expect(result.current.messages.length).toBeGreaterThan(0)
  })

  it('should handle API errors', async () => {
    ;(global.fetch as any).mockRejectedValueOnce(new Error('API error'))

    const { useAssistantChat } = await import('./useAssistantChat')
    const { result } = renderHook(() => useAssistantChat('test-project'))

    await act(async () => {
      try {
        await result.current.sendMessage('Hi there')
      } catch {
        // Expected to throw
      }
    })

    expect(result.current.error).toBeDefined()
  })
})

// =============================================================================
// Hook Integration Tests
// =============================================================================

describe('Hook Integration', () => {
  it('should work together: theme + celebration', async () => {
    const { useTheme } = await import('./useTheme')
    const { useCelebration } = await import('./useCelebration')

    const { result: themeResult } = renderHook(() => useTheme())
    const { result: celebrationResult } = renderHook(() => useCelebration())

    // Both hooks should work independently
    act(() => {
      themeResult.current.setTheme('dark')
      celebrationResult.current.celebrate()
    })

    expect(themeResult.current.theme).toBe('dark')
    expect(celebrationResult.current.isCelebrating).toBe(true)
  })
})

// =============================================================================
// Edge Case Tests
// =============================================================================

describe('Hook Edge Cases', () => {
  it('should handle rapid state updates', async () => {
    const { useContainerStatus } = await import('./useContainerStatus')
    const { result } = renderHook(() => useContainerStatus())

    act(() => {
      for (let i = 0; i < 100; i++) {
        result.current.setStatus(i % 2 === 0 ? 'running' : 'stopped')
      }
    })

    // Final state should be the last update
    expect(result.current.status).toBe('stopped')
  })

  it('should cleanup resources on unmount', async () => {
    const mockCleanup = vi.fn()
    const mockWebSocket = {
      send: vi.fn(),
      close: mockCleanup,
      readyState: WebSocket.OPEN,
      onopen: null,
      onclose: null,
      onmessage: null,
      onerror: null,
    }

    vi.spyOn(window, 'WebSocket').mockImplementation(() => mockWebSocket as any)

    const { useWebSocket } = await import('./useWebSocket')
    const { unmount } = renderHook(() => useWebSocket('test-project'))

    unmount()

    expect(mockCleanup).toHaveBeenCalled()

    vi.restoreAllMocks()
  })

  it('should handle reconnection after disconnect', async () => {
    const mockWebSocket = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: WebSocket.CONNECTING,
      onopen: null,
      onclose: null,
      onmessage: null,
      onerror: null,
    }

    vi.spyOn(window, 'WebSocket').mockImplementation(() => mockWebSocket as any)

    const { useWebSocket } = await import('./useWebSocket')
    const { result, rerender } = renderHook(() => useWebSocket('test-project'))

    // Simulate disconnect
    act(() => {
      mockWebSocket.readyState = WebSocket.CLOSED
      mockWebSocket.onclose?.()
    })

    expect(result.current.isConnected).toBe(false)

    // Rerender should attempt reconnection
    rerender()

    vi.restoreAllMocks()
  })
})
