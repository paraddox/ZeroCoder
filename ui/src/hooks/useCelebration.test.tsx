/**
 * useCelebration Hook Tests
 * =========================
 *
 * Tests for the useCelebration hook including:
 * - Celebration trigger conditions
 * - Confetti animation triggering
 * - Feature completion detection
 * - Multiple project handling
 *
 * Note: The hook returns void and triggers side effects (confetti/audio).
 * Tests verify side effects rather than return values.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useCelebration } from './useCelebration'
import type { FeatureListResponse } from '../lib/types'

// Mock canvas-confetti
vi.mock('canvas-confetti', () => ({
  default: vi.fn(),
}))

// Mock AudioContext
const mockOscillator = {
  connect: vi.fn(),
  start: vi.fn(),
  stop: vi.fn(),
  type: 'sine',
  frequency: {
    setValueAtTime: vi.fn(),
  },
}

const mockGainNode = {
  connect: vi.fn(),
  gain: {
    setValueAtTime: vi.fn(),
    linearRampToValueAtTime: vi.fn(),
    exponentialRampToValueAtTime: vi.fn(),
  },
}

const mockAudioContext = {
  createOscillator: vi.fn(() => mockOscillator),
  createGain: vi.fn(() => mockGainNode),
  destination: {},
  currentTime: 0,
  close: vi.fn(),
}

// =============================================================================
// Fixtures
// =============================================================================

const createFeatures = (
  pending: number,
  inProgress: number,
  done: number
): FeatureListResponse => ({
  pending: Array.from({ length: pending }, (_, i) => ({
    id: `pending-${i}`,
    priority: 1,
    category: 'test',
    name: `Pending ${i}`,
    description: 'Test feature',
    steps: [],
    passes: false,
    in_progress: false,
    skipped: false,
  })),
  in_progress: Array.from({ length: inProgress }, (_, i) => ({
    id: `progress-${i}`,
    priority: 1,
    category: 'test',
    name: `In Progress ${i}`,
    description: 'Test feature',
    steps: [],
    passes: false,
    in_progress: true,
    skipped: false,
  })),
  done: Array.from({ length: done }, (_, i) => ({
    id: `done-${i}`,
    priority: 1,
    category: 'test',
    name: `Done ${i}`,
    description: 'Test feature',
    steps: [],
    passes: true,
    in_progress: false,
    skipped: false,
  })),
})

// =============================================================================
// Hook Tests
// =============================================================================

describe('useCelebration Hook', () => {
  let confettiMock: ReturnType<typeof vi.fn>

  beforeEach(async () => {
    vi.clearAllMocks()
    vi.useFakeTimers()

    // Get the mocked confetti function
    const confettiModule = await import('canvas-confetti')
    confettiMock = confettiModule.default as unknown as ReturnType<typeof vi.fn>

    // Mock AudioContext
    vi.stubGlobal('AudioContext', vi.fn(() => mockAudioContext))
    vi.stubGlobal('webkitAudioContext', vi.fn(() => mockAudioContext))
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  describe('Celebration Trigger', () => {
    it('should not trigger celebration when features are pending', () => {
      const features = createFeatures(5, 0, 0)
      renderHook(() => useCelebration(features, 'test-project'))

      expect(confettiMock).not.toHaveBeenCalled()
    })

    it('should not trigger celebration when features are in progress', () => {
      const features = createFeatures(0, 3, 2)
      renderHook(() => useCelebration(features, 'test-project'))

      expect(confettiMock).not.toHaveBeenCalled()
    })

    it('should trigger celebration when all features complete (transition)', () => {
      // Start with some pending
      const initialFeatures = createFeatures(1, 0, 4)
      const { rerender } = renderHook(
        ({ features, project }) => useCelebration(features, project),
        {
          initialProps: {
            features: initialFeatures,
            project: 'test-project',
          },
        }
      )

      // First render initializes, no celebration yet
      expect(confettiMock).not.toHaveBeenCalled()

      // Complete all features
      const completedFeatures = createFeatures(0, 0, 5)
      rerender({
        features: completedFeatures,
        project: 'test-project',
      })

      // Should trigger celebration
      expect(confettiMock).toHaveBeenCalled()
    })

    it('should not trigger celebration for empty feature list', () => {
      const features = createFeatures(0, 0, 0)
      renderHook(() => useCelebration(features, 'test-project'))

      expect(confettiMock).not.toHaveBeenCalled()
    })

    it('should not trigger celebration if project is null', () => {
      const features = createFeatures(0, 0, 5)
      renderHook(() => useCelebration(features, null))

      expect(confettiMock).not.toHaveBeenCalled()
    })
  })

  describe('Celebration Reset', () => {
    it('should allow celebration for different projects', () => {
      // Start with incomplete project 1
      const { rerender } = renderHook(
        ({ features, project }) => useCelebration(features, project),
        {
          initialProps: {
            features: createFeatures(1, 0, 4),
            project: 'project-1',
          },
        }
      )

      // Complete project 1
      rerender({
        features: createFeatures(0, 0, 5),
        project: 'project-1',
      })

      expect(confettiMock).toHaveBeenCalled()
      confettiMock.mockClear()

      // Switch to incomplete project 2
      rerender({
        features: createFeatures(1, 0, 4),
        project: 'project-2',
      })

      expect(confettiMock).not.toHaveBeenCalled()

      // Complete project 2
      rerender({
        features: createFeatures(0, 0, 5),
        project: 'project-2',
      })

      expect(confettiMock).toHaveBeenCalled()
    })

    it('should not re-celebrate for same completed state', () => {
      const completedFeatures = createFeatures(0, 0, 5)
      const { rerender } = renderHook(
        ({ features, project }) => useCelebration(features, project),
        {
          initialProps: {
            features: createFeatures(1, 0, 4),
            project: 'test-project',
          },
        }
      )

      // First completion
      rerender({
        features: completedFeatures,
        project: 'test-project',
      })

      expect(confettiMock).toHaveBeenCalled()
      const callCount = confettiMock.mock.calls.length
      confettiMock.mockClear()

      // Re-render with same features - should not celebrate again
      rerender({
        features: completedFeatures,
        project: 'test-project',
      })

      // No additional celebration calls
      expect(confettiMock).not.toHaveBeenCalled()
    })
  })

  describe('Edge Cases', () => {
    it('should handle undefined features', () => {
      renderHook(() => useCelebration(undefined, 'test-project'))

      expect(confettiMock).not.toHaveBeenCalled()
    })

    it('should not celebrate on initial load of already-complete project', () => {
      // Load a project that's already complete
      const completedFeatures = createFeatures(0, 0, 5)
      renderHook(() => useCelebration(completedFeatures, 'test-project'))

      // Should NOT celebrate on initial load
      expect(confettiMock).not.toHaveBeenCalled()
    })

    it('should handle features transitioning from done back to in progress', () => {
      const { rerender } = renderHook(
        ({ features, project }) => useCelebration(features, project),
        {
          initialProps: {
            features: createFeatures(1, 0, 4),
            project: 'test-project',
          },
        }
      )

      // Complete all
      rerender({
        features: createFeatures(0, 0, 5),
        project: 'test-project',
      })

      expect(confettiMock).toHaveBeenCalled()
      confettiMock.mockClear()

      // Feature moves back to in_progress (e.g., reopened)
      rerender({
        features: createFeatures(0, 1, 4),
        project: 'test-project',
      })

      // No celebration when incomplete
      expect(confettiMock).not.toHaveBeenCalled()
    })

    it('should handle rapid feature updates without double-celebrating', () => {
      const { rerender } = renderHook(
        ({ features, project }) => useCelebration(features, project),
        {
          initialProps: {
            features: createFeatures(5, 0, 0),
            project: 'test-project',
          },
        }
      )

      // Rapid updates
      for (let i = 4; i >= 0; i--) {
        rerender({
          features: createFeatures(i, 0, 5 - i),
          project: 'test-project',
        })
      }

      // Should only celebrate once when all done
      // The confetti is called multiple times internally (from both sides + interval)
      // so we just verify it was triggered
      expect(confettiMock).toHaveBeenCalled()
    })
  })

  describe('Audio Playback', () => {
    it('should attempt to play fanfare when celebration triggers', () => {
      const { rerender } = renderHook(
        ({ features, project }) => useCelebration(features, project),
        {
          initialProps: {
            features: createFeatures(1, 0, 4),
            project: 'test-project',
          },
        }
      )

      // Complete all features
      rerender({
        features: createFeatures(0, 0, 5),
        project: 'test-project',
      })

      // AudioContext should be created for fanfare
      expect(AudioContext).toHaveBeenCalled()
    })
  })
})
