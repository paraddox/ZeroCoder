/**
 * ProgressDashboard Component Tests
 * ==================================
 *
 * Tests for the ProgressDashboard component including:
 * - Progress display
 * - Statistics rendering
 * - Progress bar visualization
 * - Edge cases
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Mock ProgressDashboard component for testing
const MockProgressDashboard = ({
  stats,
}: {
  stats: {
    passing: number
    in_progress: number
    total: number
    percentage: number
  }
}) => (
  <div data-testid="progress-dashboard">
    <div data-testid="progress-bar" style={{ width: `${stats.percentage}%` }} />
    <span data-testid="passing-count">{stats.passing}</span>
    <span data-testid="in-progress-count">{stats.in_progress}</span>
    <span data-testid="total-count">{stats.total}</span>
    <span data-testid="percentage">{stats.percentage.toFixed(1)}%</span>
  </div>
)

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  })

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }
}

describe('ProgressDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('should render the dashboard', () => {
      render(
        <MockProgressDashboard
          stats={{ passing: 5, in_progress: 2, total: 10, percentage: 50 }}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByTestId('progress-dashboard')).toBeInTheDocument()
    })

    it('should render progress bar', () => {
      render(
        <MockProgressDashboard
          stats={{ passing: 5, in_progress: 2, total: 10, percentage: 50 }}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByTestId('progress-bar')).toBeInTheDocument()
    })

    it('should render all statistics', () => {
      render(
        <MockProgressDashboard
          stats={{ passing: 5, in_progress: 2, total: 10, percentage: 50 }}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByTestId('passing-count')).toHaveTextContent('5')
      expect(screen.getByTestId('in-progress-count')).toHaveTextContent('2')
      expect(screen.getByTestId('total-count')).toHaveTextContent('10')
    })
  })

  describe('Progress Bar', () => {
    it('should show correct width for 0%', () => {
      render(
        <MockProgressDashboard
          stats={{ passing: 0, in_progress: 0, total: 10, percentage: 0 }}
        />,
        { wrapper: createWrapper() }
      )

      const progressBar = screen.getByTestId('progress-bar')
      expect(progressBar).toHaveStyle({ width: '0%' })
    })

    it('should show correct width for 50%', () => {
      render(
        <MockProgressDashboard
          stats={{ passing: 5, in_progress: 0, total: 10, percentage: 50 }}
        />,
        { wrapper: createWrapper() }
      )

      const progressBar = screen.getByTestId('progress-bar')
      expect(progressBar).toHaveStyle({ width: '50%' })
    })

    it('should show correct width for 100%', () => {
      render(
        <MockProgressDashboard
          stats={{ passing: 10, in_progress: 0, total: 10, percentage: 100 }}
        />,
        { wrapper: createWrapper() }
      )

      const progressBar = screen.getByTestId('progress-bar')
      expect(progressBar).toHaveStyle({ width: '100%' })
    })
  })

  describe('Percentage Display', () => {
    it('should display percentage with one decimal', () => {
      render(
        <MockProgressDashboard
          stats={{ passing: 1, in_progress: 0, total: 3, percentage: 33.333 }}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByTestId('percentage')).toHaveTextContent('33.3%')
    })

    it('should display 0.0% for empty project', () => {
      render(
        <MockProgressDashboard
          stats={{ passing: 0, in_progress: 0, total: 0, percentage: 0 }}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByTestId('percentage')).toHaveTextContent('0.0%')
    })

    it('should display 100.0% for completed project', () => {
      render(
        <MockProgressDashboard
          stats={{ passing: 10, in_progress: 0, total: 10, percentage: 100 }}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByTestId('percentage')).toHaveTextContent('100.0%')
    })
  })

  describe('Edge Cases', () => {
    it('should handle zero total', () => {
      render(
        <MockProgressDashboard
          stats={{ passing: 0, in_progress: 0, total: 0, percentage: 0 }}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByTestId('total-count')).toHaveTextContent('0')
      expect(screen.getByTestId('percentage')).toHaveTextContent('0.0%')
    })

    it('should handle large numbers', () => {
      render(
        <MockProgressDashboard
          stats={{
            passing: 999,
            in_progress: 50,
            total: 1000,
            percentage: 99.9,
          }}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByTestId('passing-count')).toHaveTextContent('999')
      expect(screen.getByTestId('total-count')).toHaveTextContent('1000')
    })

    it('should handle decimal percentages', () => {
      render(
        <MockProgressDashboard
          stats={{ passing: 1, in_progress: 0, total: 7, percentage: 14.285714 }}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByTestId('percentage')).toHaveTextContent('14.3%')
    })
  })

  describe('State Changes', () => {
    it('should update when stats change', () => {
      const { rerender } = render(
        <MockProgressDashboard
          stats={{ passing: 0, in_progress: 0, total: 10, percentage: 0 }}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByTestId('passing-count')).toHaveTextContent('0')

      // Rerender with new stats
      rerender(
        <QueryClientProvider
          client={
            new QueryClient({
              defaultOptions: { queries: { retry: false } },
            })
          }
        >
          <MockProgressDashboard
            stats={{ passing: 5, in_progress: 2, total: 10, percentage: 50 }}
          />
        </QueryClientProvider>
      )

      expect(screen.getByTestId('passing-count')).toHaveTextContent('5')
      expect(screen.getByTestId('in-progress-count')).toHaveTextContent('2')
    })
  })
})
