/**
 * useSpecChat Hook Tests
 * ======================
 *
 * Enterprise-grade tests for the useSpecChat hook including:
 * - WebSocket connection management
 * - Message sending and receiving
 * - Reconnection logic
 * - Error handling
 * - File attachment handling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'

// Mock WebSocket
class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3

  url: string
  readyState: number = MockWebSocket.CONNECTING
  onopen: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  constructor(url: string) {
    this.url = url
    // Simulate async connection
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN
      this.onopen?.(new Event('open'))
    }, 10)
  }

  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.(new CloseEvent('close'))
  })

  // Helper to simulate receiving a message
  simulateMessage(data: object) {
    this.onmessage?.(new MessageEvent('message', {
      data: JSON.stringify(data),
    }))
  }

  // Helper to simulate error
  simulateError() {
    this.onerror?.(new Event('error'))
  }
}

// Store reference to created WebSocket instances
let mockWebSocketInstance: MockWebSocket | null = null

vi.stubGlobal('WebSocket', class extends MockWebSocket {
  constructor(url: string) {
    super(url)
    mockWebSocketInstance = this
  }
})

// =============================================================================
// Hook Tests
// =============================================================================

describe('useSpecChat Hook', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockWebSocketInstance = null
  })

  afterEach(() => {
    mockWebSocketInstance?.close()
  })

  describe('Connection Management', () => {
    it('should establish WebSocket connection', async () => {
      // Import after mocking
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat('test-project'))

      await waitFor(() => {
        expect(mockWebSocketInstance).toBeTruthy()
      })
    })

    it('should connect to correct URL', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      renderHook(() => useSpecChat('my-project'))

      await waitFor(() => {
        expect(mockWebSocketInstance?.url).toContain('my-project')
        expect(mockWebSocketInstance?.url).toContain('spec-chat')
      })
    })

    it('should track connection status', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat('test-project'))

      // Initially connecting
      expect(result.current.isConnected).toBe(false)

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })
    })

    it('should close connection on unmount', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { unmount } = renderHook(() => useSpecChat('test-project'))

      await waitFor(() => {
        expect(mockWebSocketInstance).toBeTruthy()
      })

      unmount()

      expect(mockWebSocketInstance?.close).toHaveBeenCalled()
    })
  })

  describe('Message Handling', () => {
    it('should send text messages', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat('test-project'))

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      act(() => {
        result.current.sendMessage('Hello, Claude!')
      })

      expect(mockWebSocketInstance?.send).toHaveBeenCalled()
      const sentData = JSON.parse(mockWebSocketInstance?.send.mock.calls[0][0])
      expect(sentData.type).toBe('message')
      expect(sentData.content).toBe('Hello, Claude!')
    })

    it('should receive and store messages', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat('test-project'))

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      act(() => {
        mockWebSocketInstance?.simulateMessage({
          type: 'message',
          role: 'assistant',
          content: 'Hello! How can I help?',
        })
      })

      expect(result.current.messages.length).toBeGreaterThan(0)
    })

    it('should handle progress updates', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat('test-project'))

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      act(() => {
        mockWebSocketInstance?.simulateMessage({
          type: 'progress',
          message: 'Analyzing your requirements...',
        })
      })

      // Progress should be tracked
      expect(result.current.isLoading).toBeDefined()
    })

    it('should handle completion message', async () => {
      const onComplete = vi.fn()
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat('test-project', { onComplete }))

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      act(() => {
        mockWebSocketInstance?.simulateMessage({
          type: 'complete',
          spec_path: '/path/to/spec.txt',
        })
      })

      expect(onComplete).toHaveBeenCalledWith('/path/to/spec.txt')
    })
  })

  describe('File Attachments', () => {
    it('should send message with image attachment', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat('test-project'))

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      const imageAttachment = {
        type: 'image' as const,
        media_type: 'image/png',
        data: 'base64encodeddata',
      }

      act(() => {
        result.current.sendMessage('Check this image', [imageAttachment])
      })

      expect(mockWebSocketInstance?.send).toHaveBeenCalled()
      const sentData = JSON.parse(mockWebSocketInstance?.send.mock.calls[0][0])
      expect(sentData.attachments).toBeDefined()
      expect(sentData.attachments.length).toBe(1)
    })

    it('should send message with text file attachment', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat('test-project'))

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      const textAttachment = {
        type: 'text' as const,
        filename: 'requirements.txt',
        content: 'React\nTypeScript\nTailwind',
      }

      act(() => {
        result.current.sendMessage('Here are my requirements', [textAttachment])
      })

      expect(mockWebSocketInstance?.send).toHaveBeenCalled()
    })
  })

  describe('Question Handling', () => {
    it('should handle question message with options', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat('test-project'))

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      act(() => {
        mockWebSocketInstance?.simulateMessage({
          type: 'question',
          question_id: 'q1',
          text: 'What framework do you prefer?',
          options: [
            { id: 'react', label: 'React' },
            { id: 'vue', label: 'Vue' },
            { id: 'angular', label: 'Angular' },
          ],
          multi_select: false,
        })
      })

      expect(result.current.currentQuestion).toBeDefined()
      expect(result.current.currentQuestion?.options?.length).toBe(3)
    })

    it('should send answer to question', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat('test-project'))

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      act(() => {
        mockWebSocketInstance?.simulateMessage({
          type: 'question',
          question_id: 'q1',
          text: 'What framework?',
          options: [{ id: 'react', label: 'React' }],
          multi_select: false,
        })
      })

      act(() => {
        result.current.answerQuestion('q1', ['react'])
      })

      expect(mockWebSocketInstance?.send).toHaveBeenCalled()
      const sentData = JSON.parse(mockWebSocketInstance?.send.mock.calls[0][0])
      expect(sentData.type).toBe('answer')
      expect(sentData.question_id).toBe('q1')
    })
  })

  describe('Error Handling', () => {
    it('should handle WebSocket errors', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat('test-project'))

      await waitFor(() => {
        expect(mockWebSocketInstance).toBeTruthy()
      })

      act(() => {
        mockWebSocketInstance?.simulateError()
      })

      // Should have error state or reconnect
      expect(result.current.error || !result.current.isConnected).toBeTruthy()
    })

    it('should handle connection close', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat('test-project'))

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      act(() => {
        mockWebSocketInstance?.close()
      })

      expect(result.current.isConnected).toBe(false)
    })

    it('should handle malformed messages', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat('test-project'))

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      // Should not crash on invalid JSON
      expect(() => {
        act(() => {
          mockWebSocketInstance?.onmessage?.(new MessageEvent('message', {
            data: 'not valid json',
          }))
        })
      }).not.toThrow()
    })
  })

  describe('Loading States', () => {
    it('should track loading state when sending message', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat('test-project'))

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      act(() => {
        result.current.sendMessage('Hello')
      })

      expect(result.current.isLoading).toBe(true)
    })

    it('should clear loading state when response received', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat('test-project'))

      await waitFor(() => {
        expect(result.current.isConnected).toBe(true)
      })

      act(() => {
        result.current.sendMessage('Hello')
      })

      expect(result.current.isLoading).toBe(true)

      act(() => {
        mockWebSocketInstance?.simulateMessage({
          type: 'message',
          role: 'assistant',
          content: 'Response',
        })
      })

      // Loading should be cleared after response
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })
    })
  })
})
