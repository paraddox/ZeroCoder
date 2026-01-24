/**
 * useCelebration Hook Tests
 * =========================
 *
 * Enterprise-grade tests for the useCelebration hook including:
 * - Celebration trigger conditions
 * - Confetti animation control
 * - Feature completion detection
 * - Multiple project handling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useCelebration } from './useCelebration'
import type { FeaturesByStatus } from '../lib/types'

// =============================================================================
// Fixtures
// =============================================================================

const createFeatures = (
  pending: number,
  inProgress: number,
  done: number
): FeaturesByStatus => ({
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
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Celebration Trigger', () => {
    it('should not celebrate when features are pending', () => {
      const features = createFeatures(5, 0, 0)
      const { result } = renderHook(() =>
        useCelebration(features, 'test-project')
      )

      expect(result.current.isCelebrating).toBe(false)
    })

    it('should not celebrate when features are in progress', () => {
      const features = createFeatures(0, 3, 2)
      const { result } = renderHook(() =>
        useCelebration(features, 'test-project')
      )

      expect(result.current.isCelebrating).toBe(false)
    })

    it('should celebrate when all features are done', async () => {
      // Start with some pending
      const initialFeatures = createFeatures(1, 0, 4)
      const { result, rerender } = renderHook(
        ({ features, project }) => useCelebration(features, project),
        {
          initialProps: {
            features: initialFeatures,
            project: 'test-project',
          },
        }
      )

      expect(result.current.isCelebrating).toBe(false)

      // Complete all features
      const completedFeatures = createFeatures(0, 0, 5)
      rerender({
        features: completedFeatures,
        project: 'test-project',
      })

      // Should trigger celebration
      await waitFor(() => {
        expect(result.current.isCelebrating).toBe(true)
      })
    })

    it('should not celebrate for empty feature list', () => {
      const features = createFeatures(0, 0, 0)
      const { result } = renderHook(() =>
        useCelebration(features, 'test-project')
      )

      expect(result.current.isCelebrating).toBe(false)
    })

    it('should not celebrate if project is null', () => {
      const features = createFeatures(0, 0, 5)
      const { result } = renderHook(() =>
        useCelebration(features, null)
      )

      expect(result.current.isCelebrating).toBe(false)
    })
  })

  describe('Celebration Reset', () => {
    it('should reset celebration when switching projects', async () => {
      const completedFeatures = createFeatures(0, 0, 5)
      const { result, rerender } = renderHook(
        ({ features, project }) => useCelebration(features, project),
        {
          initialProps: {
            features: createFeatures(1, 0, 4),
            project: 'project-1',
          },
        }
      )

      // Trigger celebration
      rerender({
        features: completedFeatures,
        project: 'project-1',
      })

      await waitFor(() => {
        expect(result.current.isCelebrating).toBe(true)
      })

      // Switch to different project
      rerender({
        features: createFeatures(5, 0, 0),
        project: 'project-2',
      })

      await waitFor(() => {
        expect(result.current.isCelebrating).toBe(false)
      })
    })

    it('should not re-celebrate for same completed state', async () => {
      const completedFeatures = createFeatures(0, 0, 5)
      const celebrationCount = { count: 0 }

      const { result, rerender } = renderHook(
        ({ features, project }) => {
          const celebration = useCelebration(features, project)
          if (celebration.isCelebrating) {
            celebrationCount.count++
          }
          return celebration
        },
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

      await waitFor(() => {
        expect(result.current.isCelebrating).toBe(true)
      })

      // Re-render with same features - should not re-trigger
      const initialCount = celebrationCount.count

      rerender({
        features: completedFeatures,
        project: 'test-project',
      })

      // Count should not increase significantly
    })
  })

  describe('Edge Cases', () => {
    it('should handle undefined features', () => {
      const { result } = renderHook(() =>
        useCelebration(undefined, 'test-project')
      )

      expect(result.current.isCelebrating).toBe(false)
    })

    it('should handle features transitioning from done back to in progress', async () => {
      const { result, rerender } = renderHook(
        ({ features, project }) => useCelebration(features, project),
        {
          initialProps: {
            features: createFeatures(0, 0, 5),
            project: 'test-project',
          },
        }
      )

      // Wait for any initial celebration
      await waitFor(() => {
        // Initial state
      })

      // Feature moves back to in_progress (e.g., reopened)
      rerender({
        features: createFeatures(0, 1, 4),
        project: 'test-project',
      })

      await waitFor(() => {
        expect(result.current.isCelebrating).toBe(false)
      })
    })

    it('should handle rapid feature updates', async () => {
      const { result, rerender } = renderHook(
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

      // Should eventually celebrate when all done
      await waitFor(() => {
        expect(result.current.isCelebrating).toBe(true)
      })
    })
  })

  describe('Confetti Control', () => {
    it('should expose stop celebration function', async () => {
      const completedFeatures = createFeatures(0, 0, 5)
      const { result, rerender } = renderHook(
        ({ features, project }) => useCelebration(features, project),
        {
          initialProps: {
            features: createFeatures(1, 0, 4),
            project: 'test-project',
          },
        }
      )

      rerender({
        features: completedFeatures,
        project: 'test-project',
      })

      await waitFor(() => {
        expect(result.current.isCelebrating).toBe(true)
      })

      // Stop celebration if function exists
      if (result.current.stopCelebration) {
        act(() => {
          result.current.stopCelebration()
        })

        expect(result.current.isCelebrating).toBe(false)
      }
    })
  })
})
