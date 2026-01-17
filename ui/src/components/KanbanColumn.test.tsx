/**
 * KanbanColumn Component Tests
 * ============================
 *
 * Tests for individual kanban column including:
 * - Column header rendering
 * - Feature card listing
 * - Empty state handling
 * - Status-specific styling
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import { render, createMockFeature } from '../test/test-utils'

// Mock handlers
const mockOnFeatureClick = vi.fn()

// Mock component for testing
function MockKanbanColumn({
  title,
  status,
  features,
  count,
  onFeatureClick,
}: {
  title: string
  status: 'pending' | 'in_progress' | 'done'
  features: ReturnType<typeof createMockFeature>[]
  count: number
  onFeatureClick?: (feature: ReturnType<typeof createMockFeature>) => void
}) {
  return (
    <div data-testid={`column-${status}`} className={`column column-${status}`}>
      <div data-testid="column-header" className="header">
        <h3>{title}</h3>
        <span data-testid="feature-count" className="count">
          {count}
        </span>
      </div>
      <div data-testid="column-content" className="content">
        {features.length === 0 ? (
          <p data-testid="empty-state" className="empty">
            No features
          </p>
        ) : (
          <ul data-testid="feature-list">
            {features.map((feature) => (
              <li
                key={feature.id}
                data-testid={`feature-${feature.id}`}
                onClick={() => onFeatureClick?.(feature)}
              >
                <span className="name">{feature.name}</span>
                <span className="priority">P{feature.priority}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

describe('KanbanColumn', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Column Rendering', () => {
    it('should render pending column', () => {
      render(
        <MockKanbanColumn
          title="Pending"
          status="pending"
          features={[]}
          count={0}
        />
      )

      expect(screen.getByTestId('column-pending')).toBeInTheDocument()
      expect(screen.getByText('Pending')).toBeInTheDocument()
    })

    it('should render in_progress column', () => {
      render(
        <MockKanbanColumn
          title="In Progress"
          status="in_progress"
          features={[]}
          count={0}
        />
      )

      expect(screen.getByTestId('column-in_progress')).toBeInTheDocument()
      expect(screen.getByText('In Progress')).toBeInTheDocument()
    })

    it('should render done column', () => {
      render(
        <MockKanbanColumn
          title="Done"
          status="done"
          features={[]}
          count={0}
        />
      )

      expect(screen.getByTestId('column-done')).toBeInTheDocument()
      expect(screen.getByText('Done')).toBeInTheDocument()
    })
  })

  describe('Feature Count', () => {
    it('should display zero count', () => {
      render(
        <MockKanbanColumn
          title="Pending"
          status="pending"
          features={[]}
          count={0}
        />
      )

      expect(screen.getByTestId('feature-count')).toHaveTextContent('0')
    })

    it('should display correct count', () => {
      const features = [
        createMockFeature({ id: 'feat-1' }),
        createMockFeature({ id: 'feat-2' }),
        createMockFeature({ id: 'feat-3' }),
      ]

      render(
        <MockKanbanColumn
          title="Pending"
          status="pending"
          features={features}
          count={3}
        />
      )

      expect(screen.getByTestId('feature-count')).toHaveTextContent('3')
    })

    it('should handle large counts', () => {
      render(
        <MockKanbanColumn
          title="Done"
          status="done"
          features={[]}
          count={999}
        />
      )

      expect(screen.getByTestId('feature-count')).toHaveTextContent('999')
    })
  })

  describe('Empty State', () => {
    it('should show empty state when no features', () => {
      render(
        <MockKanbanColumn
          title="Pending"
          status="pending"
          features={[]}
          count={0}
        />
      )

      expect(screen.getByTestId('empty-state')).toBeInTheDocument()
      expect(screen.getByTestId('empty-state')).toHaveTextContent('No features')
    })

    it('should not show empty state when features exist', () => {
      render(
        <MockKanbanColumn
          title="Pending"
          status="pending"
          features={[createMockFeature()]}
          count={1}
        />
      )

      expect(screen.queryByTestId('empty-state')).not.toBeInTheDocument()
    })
  })

  describe('Feature List', () => {
    it('should render feature list when features exist', () => {
      render(
        <MockKanbanColumn
          title="Pending"
          status="pending"
          features={[createMockFeature()]}
          count={1}
        />
      )

      expect(screen.getByTestId('feature-list')).toBeInTheDocument()
    })

    it('should render all features', () => {
      const features = [
        createMockFeature({ id: 'feat-1', name: 'Feature One' }),
        createMockFeature({ id: 'feat-2', name: 'Feature Two' }),
        createMockFeature({ id: 'feat-3', name: 'Feature Three' }),
      ]

      render(
        <MockKanbanColumn
          title="Pending"
          status="pending"
          features={features}
          count={3}
        />
      )

      expect(screen.getByText('Feature One')).toBeInTheDocument()
      expect(screen.getByText('Feature Two')).toBeInTheDocument()
      expect(screen.getByText('Feature Three')).toBeInTheDocument()
    })

    it('should display feature priority', () => {
      const features = [
        createMockFeature({ id: 'feat-1', priority: 0 }),
        createMockFeature({ id: 'feat-2', priority: 2 }),
      ]

      render(
        <MockKanbanColumn
          title="Pending"
          status="pending"
          features={features}
          count={2}
        />
      )

      expect(screen.getByText('P0')).toBeInTheDocument()
      expect(screen.getByText('P2')).toBeInTheDocument()
    })
  })

  describe('Feature Click', () => {
    it('should call onFeatureClick when feature clicked', () => {
      const feature = createMockFeature({ id: 'feat-1', name: 'Clickable Feature' })

      render(
        <MockKanbanColumn
          title="Pending"
          status="pending"
          features={[feature]}
          count={1}
          onFeatureClick={mockOnFeatureClick}
        />
      )

      screen.getByTestId('feature-feat-1').click()
      expect(mockOnFeatureClick).toHaveBeenCalledWith(feature)
    })

    it('should pass correct feature to click handler', () => {
      const features = [
        createMockFeature({ id: 'feat-1', name: 'First' }),
        createMockFeature({ id: 'feat-2', name: 'Second' }),
      ]

      render(
        <MockKanbanColumn
          title="Pending"
          status="pending"
          features={features}
          count={2}
          onFeatureClick={mockOnFeatureClick}
        />
      )

      screen.getByTestId('feature-feat-2').click()
      expect(mockOnFeatureClick).toHaveBeenCalledWith(
        expect.objectContaining({ id: 'feat-2', name: 'Second' })
      )
    })
  })

  describe('Column Styling', () => {
    it('should have correct class for pending status', () => {
      render(
        <MockKanbanColumn
          title="Pending"
          status="pending"
          features={[]}
          count={0}
        />
      )

      const column = screen.getByTestId('column-pending')
      expect(column).toHaveClass('column-pending')
    })

    it('should have correct class for in_progress status', () => {
      render(
        <MockKanbanColumn
          title="In Progress"
          status="in_progress"
          features={[]}
          count={0}
        />
      )

      const column = screen.getByTestId('column-in_progress')
      expect(column).toHaveClass('column-in_progress')
    })

    it('should have correct class for done status', () => {
      render(
        <MockKanbanColumn
          title="Done"
          status="done"
          features={[]}
          count={0}
        />
      )

      const column = screen.getByTestId('column-done')
      expect(column).toHaveClass('column-done')
    })
  })

  describe('Edge Cases', () => {
    it('should handle features with long names', () => {
      const longName = 'A'.repeat(100)
      const feature = createMockFeature({ id: 'feat-1', name: longName })

      render(
        <MockKanbanColumn
          title="Pending"
          status="pending"
          features={[feature]}
          count={1}
        />
      )

      expect(screen.getByText(longName)).toBeInTheDocument()
    })

    it('should handle many features', () => {
      const features = Array.from({ length: 50 }, (_, i) =>
        createMockFeature({ id: `feat-${i}`, name: `Feature ${i}` })
      )

      render(
        <MockKanbanColumn
          title="Pending"
          status="pending"
          features={features}
          count={50}
        />
      )

      expect(screen.getByTestId('feature-list').children).toHaveLength(50)
    })
  })
})
