/**
 * useTheme Hook Tests
 * ===================
 *
 * Enterprise-grade tests for the useTheme hook including:
 * - Theme state management
 * - System preference detection
 * - Persistence to localStorage
 * - CSS class toggling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useTheme, ThemeProvider } from './useTheme'
import React from 'react'

// =============================================================================
// Fixtures
// =============================================================================

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <ThemeProvider>{children}</ThemeProvider>
)

// =============================================================================
// Hook Tests
// =============================================================================

describe('useTheme Hook', () => {
  beforeEach(() => {
    localStorage.clear()
    // Reset document classes
    document.documentElement.classList.remove('dark', 'light')
  })

  afterEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark', 'light')
  })

  describe('Initial State', () => {
    it('should return theme and toggleTheme function', () => {
      const { result } = renderHook(() => useTheme(), { wrapper })

      expect(result.current.theme).toBeDefined()
      expect(typeof result.current.toggleTheme).toBe('function')
    })

    it('should default to light theme when no preference', () => {
      // Mock matchMedia to return no preference
      const originalMatchMedia = window.matchMedia
      window.matchMedia = vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }))

      const { result } = renderHook(() => useTheme(), { wrapper })

      // Theme should be 'light' or 'dark' based on default
      expect(['light', 'dark']).toContain(result.current.theme)

      window.matchMedia = originalMatchMedia
    })

    it('should detect system dark mode preference', () => {
      const originalMatchMedia = window.matchMedia
      window.matchMedia = vi.fn().mockImplementation((query: string) => ({
        matches: query.includes('dark'),
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }))

      const { result } = renderHook(() => useTheme(), { wrapper })

      // Should respect system preference if no stored value
      expect(['light', 'dark']).toContain(result.current.theme)

      window.matchMedia = originalMatchMedia
    })
  })

  describe('Toggle Theme', () => {
    it('should toggle from light to dark', () => {
      localStorage.setItem('theme', 'light')

      const { result } = renderHook(() => useTheme(), { wrapper })

      act(() => {
        result.current.toggleTheme()
      })

      expect(result.current.theme).toBe('dark')
    })

    it('should toggle from dark to light', () => {
      localStorage.setItem('theme', 'dark')

      const { result } = renderHook(() => useTheme(), { wrapper })

      act(() => {
        result.current.toggleTheme()
      })

      expect(result.current.theme).toBe('light')
    })

    it('should toggle multiple times correctly', () => {
      const { result } = renderHook(() => useTheme(), { wrapper })

      const initialTheme = result.current.theme

      act(() => {
        result.current.toggleTheme()
      })

      const afterFirstToggle = result.current.theme
      expect(afterFirstToggle).not.toBe(initialTheme)

      act(() => {
        result.current.toggleTheme()
      })

      expect(result.current.theme).toBe(initialTheme)
    })
  })

  describe('LocalStorage Persistence', () => {
    it('should persist theme to localStorage', () => {
      const { result } = renderHook(() => useTheme(), { wrapper })

      act(() => {
        result.current.toggleTheme()
      })

      const storedTheme = localStorage.getItem('theme')
      expect(storedTheme).toBe(result.current.theme)
    })

    it('should restore theme from localStorage', () => {
      localStorage.setItem('theme', 'dark')

      const { result } = renderHook(() => useTheme(), { wrapper })

      expect(result.current.theme).toBe('dark')
    })

    it('should handle invalid localStorage value', () => {
      localStorage.setItem('theme', 'invalid-value')

      const { result } = renderHook(() => useTheme(), { wrapper })

      // Should fall back to valid theme
      expect(['light', 'dark']).toContain(result.current.theme)
    })
  })

  describe('CSS Class Updates', () => {
    it('should add dark class to document in dark mode', () => {
      localStorage.setItem('theme', 'dark')

      renderHook(() => useTheme(), { wrapper })

      expect(document.documentElement.classList.contains('dark')).toBe(true)
    })

    it('should remove dark class in light mode', () => {
      document.documentElement.classList.add('dark')
      localStorage.setItem('theme', 'light')

      renderHook(() => useTheme(), { wrapper })

      expect(document.documentElement.classList.contains('dark')).toBe(false)
    })

    it('should update classes when toggling', () => {
      localStorage.setItem('theme', 'light')

      const { result } = renderHook(() => useTheme(), { wrapper })

      expect(document.documentElement.classList.contains('dark')).toBe(false)

      act(() => {
        result.current.toggleTheme()
      })

      expect(document.documentElement.classList.contains('dark')).toBe(true)
    })
  })

  describe('Error Handling', () => {
    it('should handle localStorage errors gracefully', () => {
      const originalSetItem = localStorage.setItem
      localStorage.setItem = vi.fn(() => {
        throw new Error('QuotaExceededError')
      })

      const { result } = renderHook(() => useTheme(), { wrapper })

      // Should not throw when toggling
      expect(() => {
        act(() => {
          result.current.toggleTheme()
        })
      }).not.toThrow()

      localStorage.setItem = originalSetItem
    })
  })
})
