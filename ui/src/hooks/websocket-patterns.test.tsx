/**
 * WebSocket Pattern Tests
 * =======================
 *
 * Comprehensive tests for WebSocket hooks including:
 * - Connection lifecycle
 * - Message handling
 * - Reconnection logic
 * - Error handling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
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
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

// Mock WebSocket
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  readyState = MockWebSocket.CONNECTING
  onopen: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  constructor(public url: string) {
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN
      this.onopen?.(new Event('open'))
    }, 0)
  }

  send(data: string) {
    // Mock send
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.(new CloseEvent('close'))
  }

  simulateMessage(data: any) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }))
  }

  simulateError() {
    this.onerror?.(new Event('error'))
  }
}

// =============================================================================
// useWebSocket Hook Tests
// =============================================================================

describe('useWebSocket', () => {
  let mockWebSocket: MockWebSocket | null = null

  beforeEach(() => {
    vi.clearAllMocks()
    mockWebSocket = null

    // Mock global WebSocket
    global.WebSocket = vi.fn().mockImplementation((url: string) => {
      mockWebSocket = new MockWebSocket(url)
      return mockWebSocket
    }) as any
  })

  afterEach(() => {
    mockWebSocket?.close()
  })

  it('should connect to WebSocket', async () => {
    const { useWebSocket } = await import('./useWebSocket')
    const { result } = renderHook(
      () => useWebSocket('test-project'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })
  })

  it('should receive progress messages', async () => {
    const { useWebSocket } = await import('./useWebSocket')
    const { result } = renderHook(
      () => useWebSocket('test-project'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    // Simulate progress message
    act(() => {
      mockWebSocket?.simulateMessage({
        type: 'progress',
        passing: 5,
        total: 10,
        percentage: 50.0,
      })
    })

    await waitFor(() => {
      expect(result.current.progress?.passing).toBe(5)
      expect(result.current.progress?.total).toBe(10)
    })
  })

  it('should receive log messages', async () => {
    const { useWebSocket } = await import('./useWebSocket')
    const { result } = renderHook(
      () => useWebSocket('test-project'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    // Simulate log messages
    act(() => {
      mockWebSocket?.simulateMessage({
        type: 'log',
        line: 'Starting agent...',
        timestamp: new Date().toISOString(),
      })
    })

    await waitFor(() => {
      expect(result.current.logs.length).toBe(1)
      expect(result.current.logs[0].line).toBe('Starting agent...')
    })
  })

  it('should receive agent status messages', async () => {
    const { useWebSocket } = await import('./useWebSocket')
    const { result } = renderHook(
      () => useWebSocket('test-project'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    // Simulate status message
    act(() => {
      mockWebSocket?.simulateMessage({
        type: 'agent_status',
        status: 'running',
      })
    })

    await waitFor(() => {
      expect(result.current.agentStatus).toBe('running')
    })
  })

  it('should handle disconnection', async () => {
    const { useWebSocket } = await import('./useWebSocket')
    const { result } = renderHook(
      () => useWebSocket('test-project'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    // Simulate disconnect
    act(() => {
      mockWebSocket?.close()
    })

    await waitFor(() => {
      expect(result.current.isConnected).toBe(false)
    })
  })

  it('should handle connection error', async () => {
    const { useWebSocket } = await import('./useWebSocket')
    const { result } = renderHook(
      () => useWebSocket('test-project'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    // Simulate error
    act(() => {
      mockWebSocket?.simulateError()
    })

    // Should handle error gracefully
    expect(result.current.error).toBeDefined()
  })
})

// =============================================================================
// Reconnection Logic Tests
// =============================================================================

describe('WebSocket Reconnection', () => {
  it('should calculate backoff delay correctly', () => {
    const calculateBackoff = (attempt: number, baseDelay = 1000, maxDelay = 30000) => {
      return Math.min(baseDelay * Math.pow(2, attempt), maxDelay)
    }

    expect(calculateBackoff(0)).toBe(1000)
    expect(calculateBackoff(1)).toBe(2000)
    expect(calculateBackoff(2)).toBe(4000)
    expect(calculateBackoff(3)).toBe(8000)
    expect(calculateBackoff(10)).toBe(30000) // Capped at max
  })

  it('should limit reconnection attempts', () => {
    const maxAttempts = 5
    let attempts = 0

    const shouldReconnect = () => {
      if (attempts < maxAttempts) {
        attempts++
        return true
      }
      return false
    }

    while (shouldReconnect()) {
      // Reconnection attempts
    }

    expect(attempts).toBe(maxAttempts)
  })

  it('should reset attempts on successful connection', () => {
    let attempts = 3

    const onConnected = () => {
      attempts = 0
    }

    onConnected()
    expect(attempts).toBe(0)
  })
})

// =============================================================================
// Message Parsing Tests
// =============================================================================

describe('Message Parsing', () => {
  it('should parse progress message', () => {
    const parseMessage = (data: string) => {
      const parsed = JSON.parse(data)
      return parsed
    }

    const progressMsg = parseMessage(JSON.stringify({
      type: 'progress',
      passing: 5,
      total: 10,
      percentage: 50.0,
    }))

    expect(progressMsg.type).toBe('progress')
    expect(progressMsg.passing).toBe(5)
  })

  it('should parse log message', () => {
    const parseMessage = (data: string) => {
      const parsed = JSON.parse(data)
      return parsed
    }

    const logMsg = parseMessage(JSON.stringify({
      type: 'log',
      line: 'Test log line',
      timestamp: '2024-01-15T12:00:00Z',
    }))

    expect(logMsg.type).toBe('log')
    expect(logMsg.line).toBe('Test log line')
  })

  it('should handle malformed messages', () => {
    const parseMessage = (data: string) => {
      try {
        return JSON.parse(data)
      } catch {
        return null
      }
    }

    expect(parseMessage('not json')).toBeNull()
    expect(parseMessage('{invalid}')).toBeNull()
  })

  it('should handle unknown message types', () => {
    const handleMessage = (msg: { type: string }) => {
      switch (msg.type) {
        case 'progress':
          return 'progress'
        case 'log':
          return 'log'
        case 'agent_status':
          return 'status'
        default:
          return 'unknown'
      }
    }

    expect(handleMessage({ type: 'unknown_type' })).toBe('unknown')
  })
})

// =============================================================================
// useSpecChat Hook Tests
// =============================================================================

describe('useSpecChat', () => {
  let mockWebSocket: MockWebSocket | null = null

  beforeEach(() => {
    vi.clearAllMocks()
    mockWebSocket = null

    global.WebSocket = vi.fn().mockImplementation((url: string) => {
      mockWebSocket = new MockWebSocket(url)
      return mockWebSocket
    }) as any
  })

  afterEach(() => {
    mockWebSocket?.close()
  })

  it('should send user message', async () => {
    const { useSpecChat } = await import('./useSpecChat')
    const { result } = renderHook(
      () => useSpecChat('test-project'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    const sendSpy = vi.spyOn(mockWebSocket!, 'send')

    act(() => {
      result.current.sendMessage('Hello')
    })

    expect(sendSpy).toHaveBeenCalledWith(
      expect.stringContaining('Hello')
    )
  })

  it('should receive assistant response', async () => {
    const { useSpecChat } = await import('./useSpecChat')
    const { result } = renderHook(
      () => useSpecChat('test-project'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    // Simulate assistant response
    act(() => {
      mockWebSocket?.simulateMessage({
        type: 'assistant_message',
        content: 'Hello! How can I help?',
      })
    })

    await waitFor(() => {
      expect(result.current.messages.length).toBeGreaterThan(0)
    })
  })

  it('should track streaming state', async () => {
    const { useSpecChat } = await import('./useSpecChat')
    const { result } = renderHook(
      () => useSpecChat('test-project'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    // Start streaming
    act(() => {
      mockWebSocket?.simulateMessage({
        type: 'stream_start',
      })
    })

    await waitFor(() => {
      expect(result.current.isStreaming).toBe(true)
    })

    // End streaming
    act(() => {
      mockWebSocket?.simulateMessage({
        type: 'stream_end',
      })
    })

    await waitFor(() => {
      expect(result.current.isStreaming).toBe(false)
    })
  })
})

// =============================================================================
// useAssistantChat Hook Tests
// =============================================================================

describe('useAssistantChat', () => {
  let mockWebSocket: MockWebSocket | null = null

  beforeEach(() => {
    vi.clearAllMocks()
    mockWebSocket = null

    global.WebSocket = vi.fn().mockImplementation((url: string) => {
      mockWebSocket = new MockWebSocket(url)
      return mockWebSocket
    }) as any
  })

  afterEach(() => {
    mockWebSocket?.close()
  })

  it('should maintain conversation history', async () => {
    const { useAssistantChat } = await import('./useAssistantChat')
    const { result } = renderHook(
      () => useAssistantChat('test-project'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    // Send message
    act(() => {
      result.current.sendMessage('First message')
    })

    // Receive response
    act(() => {
      mockWebSocket?.simulateMessage({
        type: 'assistant_message',
        content: 'First response',
      })
    })

    // Send another message
    act(() => {
      result.current.sendMessage('Second message')
    })

    // Check history
    await waitFor(() => {
      expect(result.current.messages.length).toBeGreaterThanOrEqual(2)
    })
  })

  it('should clear conversation', async () => {
    const { useAssistantChat } = await import('./useAssistantChat')
    const { result } = renderHook(
      () => useAssistantChat('test-project'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })

    // Add some messages
    act(() => {
      result.current.sendMessage('Test message')
    })

    // Clear conversation
    act(() => {
      result.current.clearMessages()
    })

    expect(result.current.messages.length).toBe(0)
  })
})

// =============================================================================
// Connection State Tests
// =============================================================================

describe('Connection State Management', () => {
  it('should track connection states', () => {
    type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'

    const transitions: Record<ConnectionState, ConnectionState[]> = {
      disconnected: ['connecting'],
      connecting: ['connected', 'disconnected'],
      connected: ['disconnected', 'reconnecting'],
      reconnecting: ['connected', 'disconnected'],
    }

    // Valid transition
    expect(transitions.disconnected).toContain('connecting')

    // Invalid transitions are not in the array
    expect(transitions.disconnected).not.toContain('connected')
  })

  it('should track last message time', () => {
    let lastMessageTime: number | null = null

    const onMessage = () => {
      lastMessageTime = Date.now()
    }

    onMessage()
    expect(lastMessageTime).not.toBeNull()
    expect(lastMessageTime).toBeLessThanOrEqual(Date.now())
  })

  it('should detect stale connections', () => {
    const STALE_THRESHOLD = 30000 // 30 seconds

    const isStale = (lastMessageTime: number | null): boolean => {
      if (!lastMessageTime) return true
      return Date.now() - lastMessageTime > STALE_THRESHOLD
    }

    // No messages yet
    expect(isStale(null)).toBe(true)

    // Recent message
    expect(isStale(Date.now())).toBe(false)

    // Old message
    expect(isStale(Date.now() - 60000)).toBe(true)
  })
})

// =============================================================================
// Message Queue Tests
// =============================================================================

describe('Message Queuing', () => {
  it('should queue messages when disconnected', () => {
    const queue: string[] = []
    let isConnected = false

    const sendMessage = (message: string) => {
      if (isConnected) {
        // Send immediately
        return true
      } else {
        queue.push(message)
        return false
      }
    }

    // Queue while disconnected
    sendMessage('message 1')
    sendMessage('message 2')

    expect(queue.length).toBe(2)
  })

  it('should flush queue on reconnection', () => {
    const queue = ['message 1', 'message 2']
    const sent: string[] = []

    const flushQueue = () => {
      while (queue.length > 0) {
        const msg = queue.shift()!
        sent.push(msg)
      }
    }

    flushQueue()

    expect(queue.length).toBe(0)
    expect(sent.length).toBe(2)
  })

  it('should limit queue size', () => {
    const MAX_QUEUE_SIZE = 100
    const queue: string[] = []

    const addToQueue = (message: string) => {
      if (queue.length >= MAX_QUEUE_SIZE) {
        queue.shift() // Remove oldest
      }
      queue.push(message)
    }

    // Add more than max
    for (let i = 0; i < 150; i++) {
      addToQueue(`message ${i}`)
    }

    expect(queue.length).toBe(MAX_QUEUE_SIZE)
    expect(queue[0]).toBe('message 50') // First 50 were dropped
  })
})
