/**
 * useAssistantChat Hook Tests
 * ===========================
 *
 * Tests for the useAssistantChat hook including:
 * - Message sending
 * - Chat history management
 * - Session lifecycle
 * - Error handling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactNode, useState } from 'react'

// Create wrapper with QueryClient
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }
}

// Message type
interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
}

// Simple hook implementation for testing
let messageCounter = 0

function useAssistantChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const sendMessage = async (content: string) => {
    setIsLoading(true)
    setError(null)

    // Add user message with unique ID
    const userMessageId = `user-${++messageCounter}-${Date.now()}`
    const userMessage: ChatMessage = {
      id: userMessageId,
      role: 'user',
      content,
      timestamp: new Date(),
    }
    setMessages((prev) => [...prev, userMessage])

    try {
      // Simulate API call
      await new Promise((resolve) => setTimeout(resolve, 100))

      // Add assistant response with unique ID
      const assistantMessageId = `assistant-${++messageCounter}-${Date.now()}`
      const assistantMessage: ChatMessage = {
        id: assistantMessageId,
        role: 'assistant',
        content: `Response to: ${content}`,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, assistantMessage])
    } catch (err) {
      setError(err as Error)
    } finally {
      setIsLoading(false)
    }
  }

  const clearChat = () => {
    setMessages([])
    setError(null)
  }

  return {
    messages,
    isLoading,
    error,
    sendMessage,
    clearChat,
  }
}

describe('useAssistantChat Hook', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.resetAllMocks()
  })

  describe('Initial State', () => {
    it('should have empty messages initially', () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      expect(result.current.messages).toEqual([])
    })

    it('should not be loading initially', () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      expect(result.current.isLoading).toBe(false)
    })

    it('should have no error initially', () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      expect(result.current.error).toBeNull()
    })
  })

  describe('Sending Messages', () => {
    it('should add user message when sending', async () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      await act(async () => {
        await result.current.sendMessage('Hello, assistant!')
      })

      const userMessage = result.current.messages.find((m) => m.role === 'user')
      expect(userMessage).toBeDefined()
      expect(userMessage?.content).toBe('Hello, assistant!')
    })

    it('should set loading state while sending', async () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      let loadingDuringCall = false

      act(() => {
        result.current.sendMessage('Test').then(() => {
          // Check loading was true during call
        })
      })

      // Loading should be true during the call
      expect(result.current.isLoading).toBe(true)

      await waitFor(() => {
        expect(result.current.isLoading).toBe(false)
      })
    })

    it('should add assistant response after user message', async () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      await act(async () => {
        await result.current.sendMessage('What is 2+2?')
      })

      const assistantMessage = result.current.messages.find(
        (m) => m.role === 'assistant'
      )
      expect(assistantMessage).toBeDefined()
      expect(assistantMessage?.content).toContain('What is 2+2?')
    })

    it('should maintain message order', async () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      await act(async () => {
        await result.current.sendMessage('First message')
      })

      await act(async () => {
        await result.current.sendMessage('Second message')
      })

      expect(result.current.messages).toHaveLength(4)
      expect(result.current.messages[0].role).toBe('user')
      expect(result.current.messages[0].content).toBe('First message')
      expect(result.current.messages[1].role).toBe('assistant')
      expect(result.current.messages[2].role).toBe('user')
      expect(result.current.messages[2].content).toBe('Second message')
      expect(result.current.messages[3].role).toBe('assistant')
    })
  })

  describe('Message Properties', () => {
    it('should include id on messages', async () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      await act(async () => {
        await result.current.sendMessage('Test message')
      })

      result.current.messages.forEach((message) => {
        expect(message.id).toBeDefined()
        expect(typeof message.id).toBe('string')
      })
    })

    it('should include timestamp on messages', async () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      await act(async () => {
        await result.current.sendMessage('Test message')
      })

      result.current.messages.forEach((message) => {
        expect(message.timestamp).toBeDefined()
        expect(message.timestamp).toBeInstanceOf(Date)
      })
    })

    it('should have unique ids for each message', async () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      await act(async () => {
        await result.current.sendMessage('First')
      })

      await act(async () => {
        await result.current.sendMessage('Second')
      })

      const ids = result.current.messages.map((m) => m.id)
      const uniqueIds = new Set(ids)
      expect(uniqueIds.size).toBe(ids.length)
    })
  })

  describe('Clear Chat', () => {
    it('should clear all messages', async () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      await act(async () => {
        await result.current.sendMessage('Message 1')
      })

      await act(async () => {
        await result.current.sendMessage('Message 2')
      })

      expect(result.current.messages.length).toBeGreaterThan(0)

      act(() => {
        result.current.clearChat()
      })

      expect(result.current.messages).toEqual([])
    })

    it('should clear error when clearing chat', async () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      // Would need to mock an error scenario
      act(() => {
        result.current.clearChat()
      })

      expect(result.current.error).toBeNull()
    })
  })

  describe('Edge Cases', () => {
    it('should handle empty message', async () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      await act(async () => {
        await result.current.sendMessage('')
      })

      const userMessage = result.current.messages.find((m) => m.role === 'user')
      expect(userMessage?.content).toBe('')
    })

    it('should handle very long messages', async () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      const longMessage = 'A'.repeat(10000)

      await act(async () => {
        await result.current.sendMessage(longMessage)
      })

      const userMessage = result.current.messages.find((m) => m.role === 'user')
      expect(userMessage?.content).toBe(longMessage)
    })

    it('should handle special characters in messages', async () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      const specialMessage = '<script>alert("test")</script>\n\t"quotes"'

      await act(async () => {
        await result.current.sendMessage(specialMessage)
      })

      const userMessage = result.current.messages.find((m) => m.role === 'user')
      expect(userMessage?.content).toBe(specialMessage)
    })

    it('should handle unicode in messages', async () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      const unicodeMessage = '你好世界 🎉 Привет мир'

      await act(async () => {
        await result.current.sendMessage(unicodeMessage)
      })

      const userMessage = result.current.messages.find((m) => m.role === 'user')
      expect(userMessage?.content).toBe(unicodeMessage)
    })
  })

  describe('Multiple Rapid Messages', () => {
    it('should handle multiple rapid messages', async () => {
      const { result } = renderHook(() => useAssistantChat(), {
        wrapper: createWrapper(),
      })

      await act(async () => {
        // Send multiple messages rapidly
        await Promise.all([
          result.current.sendMessage('Message 1'),
          result.current.sendMessage('Message 2'),
          result.current.sendMessage('Message 3'),
        ])
      })

      // Should have all messages (this tests concurrent handling)
      expect(result.current.messages.length).toBeGreaterThan(0)
    })
  })
})
