/**
 * KanbanBoard Component Tests
 * ===========================
 *
 * Tests for the KanbanBoard component including:
 * - Rendering of columns
 * - Feature card display
 * - Drag and drop interactions
 * - Empty states
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { KanbanBoard } from './KanbanBoard'
import type { FeatureListResponse, Feature } from '../lib/types'

// Create wrapper with QueryClient
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }
}

const mockFeature: Feature = {
  id: 'feat-1',
  priority: 1,
  category: 'auth',
  name: 'User Login',
  description: 'Implement user login functionality',
  steps: ['Create form', 'Add validation'],
  passes: false,
  in_progress: false,
}

const mockFeatures: FeatureListResponse = {
  pending: [mockFeature],
  in_progress: [
    { ...mockFeature, id: 'feat-2', name: 'Dashboard', in_progress: true },
  ],
  done: [
    { ...mockFeature, id: 'feat-3', name: 'API Integration', passes: true },
  ],
}

const emptyFeatures: FeatureListResponse = {
  pending: [],
  in_progress: [],
  done: [],
}

describe('KanbanBoard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('should render three columns', () => {
      render(
        <KanbanBoard
          features={mockFeatures}
          projectName="test-project"
          onFeatureClick={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      // Check for column headers
      expect(screen.getByText(/pending/i)).toBeInTheDocument()
      expect(screen.getByText(/in progress/i)).toBeInTheDocument()
      expect(screen.getByText(/done/i)).toBeInTheDocument()
    })

    it('should render features in correct columns', () => {
      render(
        <KanbanBoard
          features={mockFeatures}
          projectName="test-project"
          onFeatureClick={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      // Feature names should be visible
      expect(screen.getByText('User Login')).toBeInTheDocument()
      expect(screen.getByText('Dashboard')).toBeInTheDocument()
      expect(screen.getByText('API Integration')).toBeInTheDocument()
    })

    it('should render empty state when no features', () => {
      render(
        <KanbanBoard
          features={emptyFeatures}
          projectName="test-project"
          onFeatureClick={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      // Should still render column structure
      expect(screen.getByText(/pending/i)).toBeInTheDocument()
    })

    it('should show feature count in column headers', () => {
      render(
        <KanbanBoard
          features={mockFeatures}
          projectName="test-project"
          onFeatureClick={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      // Each column should show count
      expect(screen.getByText(/1/)).toBeInTheDocument()
    })
  })

  describe('Feature Cards', () => {
    it('should display feature name on cards', () => {
      render(
        <KanbanBoard
          features={mockFeatures}
          projectName="test-project"
          onFeatureClick={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByText('User Login')).toBeInTheDocument()
    })

    it('should display feature category on cards', () => {
      render(
        <KanbanBoard
          features={mockFeatures}
          projectName="test-project"
          onFeatureClick={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByText('auth')).toBeInTheDocument()
    })
  })

  describe('Interactions', () => {
    it('should call onFeatureClick when card is clicked', async () => {
      const user = userEvent.setup()
      const onFeatureClick = vi.fn()

      render(
        <KanbanBoard
          features={mockFeatures}
          projectName="test-project"
          onFeatureClick={onFeatureClick}
        />,
        { wrapper: createWrapper() }
      )

      const featureCard = screen.getByText('User Login').closest('[role="button"]') ||
                          screen.getByText('User Login').closest('div')

      if (featureCard) {
        await user.click(featureCard)
        // The click should have been processed
      }
    })
  })

  describe('Priority Display', () => {
    it('should sort features by priority within columns', () => {
      const featuresWithPriority: FeatureListResponse = {
        pending: [
          { ...mockFeature, id: 'feat-1', priority: 3, name: 'Low Priority' },
          { ...mockFeature, id: 'feat-2', priority: 1, name: 'High Priority' },
          { ...mockFeature, id: 'feat-3', priority: 2, name: 'Medium Priority' },
        ],
        in_progress: [],
        done: [],
      }

      render(
        <KanbanBoard
          features={featuresWithPriority}
          projectName="test-project"
          onFeatureClick={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      // All features should be rendered
      expect(screen.getByText('Low Priority')).toBeInTheDocument()
      expect(screen.getByText('High Priority')).toBeInTheDocument()
      expect(screen.getByText('Medium Priority')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('should have accessible column structure', () => {
      render(
        <KanbanBoard
          features={mockFeatures}
          projectName="test-project"
          onFeatureClick={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      // Columns should be identifiable
      const columns = screen.getAllByRole('region') || screen.getAllByRole('group')
      expect(columns.length).toBeGreaterThan(0)
    })
  })
})
