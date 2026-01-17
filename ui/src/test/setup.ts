/**
 * Vitest Test Setup
 * =================
 *
 * Global test setup and configuration for React component tests.
 */

import '@testing-library/jest-dom'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

// Cleanup after each test case
afterEach(() => {
  cleanup()
})

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

// Mock ResizeObserver
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}))

// Mock IntersectionObserver
global.IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}))

// Mock fetch globally
global.fetch = vi.fn()

// Mock WebSocket
class MockWebSocket {
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  readyState = WebSocket.CONNECTING

  constructor(public url: string) {
    setTimeout(() => {
      this.readyState = WebSocket.OPEN
      this.onopen?.()
    }, 0)
  }

  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = WebSocket.CLOSED
    this.onclose?.()
  })
}

global.WebSocket = MockWebSocket as unknown as typeof WebSocket

// Suppress console errors in tests (optional)
// console.error = vi.fn()
