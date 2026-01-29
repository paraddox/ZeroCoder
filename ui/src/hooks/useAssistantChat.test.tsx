/**
 * useAssistantChat Hook Tests
 * ===========================
 *
 * Tests for the useAssistantChat hook including:
 * - Initial state
 * - Connection lifecycle
 * - Message handling
 * - Session management
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useAssistantChat } from './useAssistantChat'

// Mock WebSocket
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  readyState = MockWebSocket.CONNECTING
  url: string
  onopen: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null

  private sentMessages: string[] = []

  constructor(url: string) {
    this.url = url
    // Simulate async connection
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN
      this.onopen?.(new Event('open'))
    }, 10)
  }

  send(data: string) {
    this.sentMessages.push(data)
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.(new CloseEvent('close'))
  }

  getSentMessages() {
    return this.sentMessages
  }

  // Helper to simulate server messages
  simulateMessage(data: object) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }))
  }
}

// Store mock instances for test access
let mockWebSocketInstances: MockWebSocket[] = []

describe('useAssistantChat Hook', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockWebSocketInstances = []

    // Mock WebSocket constructor
    vi.stubGlobal('WebSocket', class extends MockWebSocket {
      constructor(url: string) {
        super(url)
        mockWebSocketInstances.push(this)
      }
    })

    // Mock window.location
    vi.stubGlobal('location', {
      protocol: 'http:',
      host: 'localhost:3000',
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    mockWebSocketInstances = []
  })

  describe('Initial State', () => {
    it('should have empty messages initially', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      expect(result.current.messages).toEqual([])
    })

    it('should not be loading initially', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      expect(result.current.isLoading).toBe(false)
    })

    it('should be disconnected initially', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      expect(result.current.connectionStatus).toBe('disconnected')
    })

    it('should have null conversationId initially', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      expect(result.current.conversationId).toBeNull()
    })
  })

  describe('Connection Lifecycle', () => {
    it('should set connecting status when start is called', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      expect(result.current.connectionStatus).toBe('connecting')
    })

    it('should set connected status after WebSocket opens', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      // Advance timers to trigger connection
      act(() => {
        vi.advanceTimersByTime(50)
      })

      expect(result.current.connectionStatus).toBe('connected')
    })

    it('should set disconnected status after disconnect is called', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      act(() => {
        vi.advanceTimersByTime(50)
      })

      act(() => {
        result.current.disconnect()
      })

      expect(result.current.connectionStatus).toBe('disconnected')
    })
  })

  describe('Message Handling', () => {
    it('should add user message when sendMessage is called', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      act(() => {
        vi.advanceTimersByTime(200)
      })

      act(() => {
        result.current.sendMessage('Hello!')
      })

      const userMessage = result.current.messages.find((m) => m.role === 'user')
      expect(userMessage).toBeDefined()
      expect(userMessage?.content).toBe('Hello!')
    })

    it('should set loading when message is sent', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      act(() => {
        vi.advanceTimersByTime(200)
      })

      act(() => {
        result.current.sendMessage('Test message')
      })

      expect(result.current.isLoading).toBe(true)
    })

    it('should add assistant message when text is received', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      act(() => {
        vi.advanceTimersByTime(200)
      })

      // Simulate server sending text
      act(() => {
        mockWebSocketInstances[0].simulateMessage({
          type: 'text',
          content: 'Hello from assistant!',
        })
      })

      const assistantMessage = result.current.messages.find(
        (m) => m.role === 'assistant'
      )
      expect(assistantMessage).toBeDefined()
      expect(assistantMessage?.content).toBe('Hello from assistant!')
    })

    it('should append text to streaming message', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      act(() => {
        vi.advanceTimersByTime(200)
      })

      act(() => {
        mockWebSocketInstances[0].simulateMessage({
          type: 'text',
          content: 'Part 1',
        })
      })

      act(() => {
        mockWebSocketInstances[0].simulateMessage({
          type: 'text',
          content: ' Part 2',
        })
      })

      const assistantMessage = result.current.messages.find(
        (m) => m.role === 'assistant'
      )
      expect(assistantMessage?.content).toBe('Part 1 Part 2')
    })
  })

  describe('Clear Messages', () => {
    it('should clear all messages', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      act(() => {
        vi.advanceTimersByTime(200)
      })

      act(() => {
        result.current.sendMessage('Test message')
      })

      expect(result.current.messages.length).toBeGreaterThan(0)

      act(() => {
        result.current.clearMessages()
      })

      expect(result.current.messages).toEqual([])
    })

    it('should clear conversationId when clearing messages', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      act(() => {
        vi.advanceTimersByTime(200)
      })

      // Simulate conversation created
      act(() => {
        mockWebSocketInstances[0].simulateMessage({
          type: 'conversation_created',
          conversation_id: 123,
        })
      })

      expect(result.current.conversationId).toBe(123)

      act(() => {
        result.current.clearMessages()
      })

      expect(result.current.conversationId).toBeNull()
    })
  })

  describe('Error Handling', () => {
    it('should call onError when not connected and trying to send', () => {
      const onError = vi.fn()
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project', onError })
      )

      act(() => {
        result.current.sendMessage('Test message')
      })

      expect(onError).toHaveBeenCalledWith('Not connected')
    })

    it('should call onError when WebSocket errors', () => {
      const onError = vi.fn()
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project', onError })
      )

      act(() => {
        result.current.start()
      })

      act(() => {
        vi.advanceTimersByTime(50)
      })

      // Simulate error
      act(() => {
        mockWebSocketInstances[0].onerror?.(new Event('error'))
      })

      expect(onError).toHaveBeenCalledWith('WebSocket connection error')
    })
  })

  describe('Cleanup', () => {
    it('should cleanup WebSocket on unmount', () => {
      const { result, unmount } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      act(() => {
        vi.advanceTimersByTime(50)
      })

      const ws = mockWebSocketInstances[0]
      expect(ws.readyState).toBe(MockWebSocket.OPEN)

      unmount()

      expect(ws.readyState).toBe(MockWebSocket.CLOSED)
    })

    it('should cleanup timers on unmount', () => {
      const { result, unmount } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      // Unmount while checkAndSend timer is still pending
      unmount()

      // Advance timers - should not throw
      act(() => {
        vi.advanceTimersByTime(1000)
      })

      // If we get here without errors, cleanup worked
      expect(true).toBe(true)
    })
  })

  describe('Message Properties', () => {
    it('should include id on messages', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      act(() => {
        vi.advanceTimersByTime(200)
      })

      act(() => {
        result.current.sendMessage('Test message')
      })

      result.current.messages.forEach((message) => {
        expect(message.id).toBeDefined()
        expect(typeof message.id).toBe('string')
      })
    })

    it('should include timestamp on messages', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      act(() => {
        vi.advanceTimersByTime(200)
      })

      act(() => {
        result.current.sendMessage('Test message')
      })

      result.current.messages.forEach((message) => {
        expect(message.timestamp).toBeDefined()
        expect(message.timestamp).toBeInstanceOf(Date)
      })
    })

    it('should have unique ids for each message', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      act(() => {
        vi.advanceTimersByTime(200)
      })

      act(() => {
        result.current.sendMessage('First')
      })

      act(() => {
        result.current.sendMessage('Second')
      })

      const ids = result.current.messages.map((m) => m.id)
      const uniqueIds = new Set(ids)
      expect(uniqueIds.size).toBe(ids.length)
    })
  })

  describe('Edge Cases', () => {
    it('should handle empty message', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      act(() => {
        vi.advanceTimersByTime(200)
      })

      act(() => {
        result.current.sendMessage('')
      })

      const userMessage = result.current.messages.find((m) => m.role === 'user')
      expect(userMessage?.content).toBe('')
    })

    it('should handle special characters in messages', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      act(() => {
        vi.advanceTimersByTime(200)
      })

      const specialMessage = '<script>alert("test")</script>\n\t"quotes"'

      act(() => {
        result.current.sendMessage(specialMessage)
      })

      const userMessage = result.current.messages.find((m) => m.role === 'user')
      expect(userMessage?.content).toBe(specialMessage)
    })

    it('should handle unicode in messages', () => {
      const { result } = renderHook(() =>
        useAssistantChat({ projectName: 'test-project' })
      )

      act(() => {
        result.current.start()
      })

      act(() => {
        vi.advanceTimersByTime(200)
      })

      const unicodeMessage = '你好世界 Привет мир'

      act(() => {
        result.current.sendMessage(unicodeMessage)
      })

      const userMessage = result.current.messages.find((m) => m.role === 'user')
      expect(userMessage?.content).toBe(unicodeMessage)
    })
  })
})
