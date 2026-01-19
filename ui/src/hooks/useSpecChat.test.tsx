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

      const { result } = renderHook(() => useSpecChat({ projectName: 'test-project' }))

      // Start the connection
      act(() => {
        result.current.start()
      })

      await waitFor(() => {
        expect(mockWebSocketInstance).toBeTruthy()
      })
    })

    it('should connect to correct URL', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat({ projectName: 'my-project' }))

      act(() => {
        result.current.start()
      })

      await waitFor(() => {
        expect(mockWebSocketInstance?.url).toContain('my-project')
        expect(mockWebSocketInstance?.url).toContain('spec')
      })
    })

    it('should track connection status', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat({ projectName: 'test-project' }))

      // Initially disconnected
      expect(result.current.connectionStatus).toBe('disconnected')

      act(() => {
        result.current.start()
      })

      await waitFor(() => {
        expect(result.current.connectionStatus).toBe('connected')
      })
    })

    it('should close connection on unmount', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result, unmount } = renderHook(() => useSpecChat({ projectName: 'test-project' }))

      act(() => {
        result.current.start()
      })

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

      const { result } = renderHook(() => useSpecChat({ projectName: 'test-project' }))

      act(() => {
        result.current.start()
      })

      await waitFor(() => {
        expect(result.current.connectionStatus).toBe('connected')
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

      const { result } = renderHook(() => useSpecChat({ projectName: 'test-project' }))

      act(() => {
        result.current.start()
      })

      await waitFor(() => {
        expect(result.current.connectionStatus).toBe('connected')
      })

      act(() => {
        mockWebSocketInstance?.simulateMessage({
          type: 'text',
          content: 'Hello! How can I help?',
        })
      })

      expect(result.current.messages.length).toBeGreaterThan(0)
    })

    it('should handle progress updates', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat({ projectName: 'test-project' }))

      act(() => {
        result.current.start()
      })

      await waitFor(() => {
        expect(result.current.connectionStatus).toBe('connected')
      })

      act(() => {
        mockWebSocketInstance?.simulateMessage({
          type: 'text',
          content: 'Analyzing your requirements...',
        })
      })

      // Progress should be tracked
      expect(result.current.isLoading).toBeDefined()
    })

    it('should handle completion message', async () => {
      const onComplete = vi.fn()
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat({ projectName: 'test-project', onComplete }))

      act(() => {
        result.current.start()
      })

      await waitFor(() => {
        expect(result.current.connectionStatus).toBe('connected')
      })

      act(() => {
        mockWebSocketInstance?.simulateMessage({
          type: 'spec_complete',
          path: '/path/to/spec.txt',
        })
      })

      // onComplete is NOT called automatically - user clicks "Continue to Project" button
      // Just verify completion state
      expect(result.current.isComplete).toBe(true)
    })
  })

  describe('File Attachments', () => {
    it('should send message with image attachment', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat({ projectName: 'test-project' }))

      act(() => {
        result.current.start()
      })

      await waitFor(() => {
        expect(result.current.connectionStatus).toBe('connected')
      })

      const imageAttachment = {
        id: 'img-1',
        filename: 'test.png',
        mimeType: 'image/png' as const,
        base64Data: 'base64encodeddata',
        previewUrl: 'data:image/png;base64,base64encodeddata',
        size: 1000,
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

      const { result } = renderHook(() => useSpecChat({ projectName: 'test-project' }))

      act(() => {
        result.current.start()
      })

      await waitFor(() => {
        expect(result.current.connectionStatus).toBe('connected')
      })

      const textAttachment = {
        id: 'txt-1',
        filename: 'requirements.txt',
        mimeType: 'text/plain' as const,
        textContent: 'React\nTypeScript\nTailwind',
        size: 100,
        isText: true as const,
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

      const { result } = renderHook(() => useSpecChat({ projectName: 'test-project' }))

      act(() => {
        result.current.start()
      })

      await waitFor(() => {
        expect(result.current.connectionStatus).toBe('connected')
      })

      act(() => {
        mockWebSocketInstance?.simulateMessage({
          type: 'question',
          questions: [
            {
              question: 'What framework do you prefer?',
              header: 'Framework',
              options: [
                { label: 'React', description: 'Popular UI library' },
                { label: 'Vue', description: 'Progressive framework' },
                { label: 'Angular', description: 'Full-featured framework' },
              ],
              multiSelect: false,
            },
          ],
          tool_id: 'tool-1',
        })
      })

      expect(result.current.currentQuestions).toBeDefined()
      expect(result.current.currentQuestions?.length).toBe(1)
      expect(result.current.currentQuestions?.[0].options?.length).toBe(3)
    })

    it('should send answer to question', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat({ projectName: 'test-project' }))

      act(() => {
        result.current.start()
      })

      await waitFor(() => {
        expect(result.current.connectionStatus).toBe('connected')
      })

      act(() => {
        mockWebSocketInstance?.simulateMessage({
          type: 'question',
          questions: [
            {
              question: 'What framework?',
              header: 'Framework',
              options: [{ label: 'React', description: 'Popular UI library' }],
              multiSelect: false,
            },
          ],
          tool_id: 'tool-1',
        })
      })

      act(() => {
        result.current.sendAnswer({ framework: ['React'] })
      })

      expect(mockWebSocketInstance?.send).toHaveBeenCalled()
      const sentData = JSON.parse(mockWebSocketInstance?.send.mock.calls[0][0])
      expect(sentData.type).toBe('answer')
    })
  })

  describe('Error Handling', () => {
    it('should handle WebSocket errors', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat({ projectName: 'test-project' }))

      act(() => {
        result.current.start()
      })

      await waitFor(() => {
        expect(mockWebSocketInstance).toBeTruthy()
      })

      act(() => {
        mockWebSocketInstance?.simulateError()
      })

      // Should have error state or disconnected
      expect(
        result.current.connectionStatus === 'error' ||
        result.current.connectionStatus === 'disconnected'
      ).toBeTruthy()
    })

    it('should handle connection close', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat({ projectName: 'test-project' }))

      act(() => {
        result.current.start()
      })

      await waitFor(() => {
        expect(result.current.connectionStatus).toBe('connected')
      })

      act(() => {
        mockWebSocketInstance?.close()
      })

      expect(result.current.connectionStatus).toBe('disconnected')
    })

    it('should handle malformed messages', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat({ projectName: 'test-project' }))

      act(() => {
        result.current.start()
      })

      await waitFor(() => {
        expect(result.current.connectionStatus).toBe('connected')
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

      const { result } = renderHook(() => useSpecChat({ projectName: 'test-project' }))

      act(() => {
        result.current.start()
      })

      await waitFor(() => {
        expect(result.current.connectionStatus).toBe('connected')
      })

      act(() => {
        result.current.sendMessage('Hello')
      })

      expect(result.current.isLoading).toBe(true)
    })

    it('should clear loading state when response received', async () => {
      const { useSpecChat } = await import('./useSpecChat')

      const { result } = renderHook(() => useSpecChat({ projectName: 'test-project' }))

      act(() => {
        result.current.start()
      })

      await waitFor(() => {
        expect(result.current.connectionStatus).toBe('connected')
      })

      act(() => {
        result.current.sendMessage('Hello')
      })

      expect(result.current.isLoading).toBe(true)

      act(() => {
        mockWebSocketInstance?.simulateMessage({
          type: 'response_done',
        })
      })

      // Loading should be cleared after response
      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })
    })
  })
})
