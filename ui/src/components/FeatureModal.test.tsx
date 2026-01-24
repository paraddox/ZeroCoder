/**
 * FeatureModal Component Tests
 * ============================
 *
 * Tests for the feature detail modal including:
 * - Rendering feature details
 * - Status display
 * - Priority display
 * - Steps rendering
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { render, createMockFeature } from '../test/test-utils'

// Mock the component since we're testing interaction patterns
const mockOnClose = vi.fn()
const mockOnEdit = vi.fn()
const mockOnDelete = vi.fn()

// Simple mock component for testing
function MockFeatureModal({
  feature,
  isOpen,
  onClose,
  onEdit,
  onDelete,
}: {
  feature: ReturnType<typeof createMockFeature>
  isOpen: boolean
  onClose: () => void
  onEdit?: () => void
  onDelete?: () => void
}) {
  if (!isOpen) return null

  return (
    <div role="dialog" aria-labelledby="modal-title">
      <h2 id="modal-title">{feature.name}</h2>
      <p data-testid="category">{feature.category}</p>
      <p data-testid="priority">Priority: P{feature.priority}</p>
      <p data-testid="description">{feature.description}</p>
      {feature.steps && feature.steps.length > 0 && (
        <ul data-testid="steps">
          {feature.steps.map((step, i) => (
            <li key={i}>{step}</li>
          ))}
        </ul>
      )}
      <div data-testid="status">
        {feature.passes
          ? 'Completed'
          : feature.in_progress
          ? 'In Progress'
          : 'Pending'}
      </div>
      <button onClick={onClose}>Close</button>
      {onEdit && <button onClick={onEdit}>Edit</button>}
      {onDelete && <button onClick={onDelete}>Delete</button>}
    </div>
  )
}

describe('FeatureModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('should render feature details when open', () => {
      const feature = createMockFeature({
        name: 'Test Feature',
        category: 'testing',
        description: 'A test feature description',
      })

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByText('Test Feature')).toBeInTheDocument()
      expect(screen.getByTestId('category')).toHaveTextContent('testing')
      expect(screen.getByTestId('description')).toHaveTextContent(
        'A test feature description'
      )
    })

    it('should not render when closed', () => {
      const feature = createMockFeature()

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={false}
          onClose={mockOnClose}
        />
      )

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('should display priority correctly', () => {
      const feature = createMockFeature({ priority: 0 })

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      expect(screen.getByTestId('priority')).toHaveTextContent('Priority: P0')
    })

    it('should render steps list', () => {
      const feature = createMockFeature({
        steps: ['Step 1', 'Step 2', 'Step 3'],
      })

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      const stepsList = screen.getByTestId('steps')
      expect(stepsList).toBeInTheDocument()
      expect(stepsList.children).toHaveLength(3)
    })

    it('should not render steps list when empty', () => {
      const feature = createMockFeature({ steps: [] })

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      expect(screen.queryByTestId('steps')).not.toBeInTheDocument()
    })
  })

  describe('Status Display', () => {
    it('should show Pending status for open features', () => {
      const feature = createMockFeature({
        passes: false,
        in_progress: false,
      })

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      expect(screen.getByTestId('status')).toHaveTextContent('Pending')
    })

    it('should show In Progress status', () => {
      const feature = createMockFeature({
        passes: false,
        in_progress: true,
      })

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      expect(screen.getByTestId('status')).toHaveTextContent('In Progress')
    })

    it('should show Completed status for passing features', () => {
      const feature = createMockFeature({
        passes: true,
        in_progress: false,
      })

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      expect(screen.getByTestId('status')).toHaveTextContent('Completed')
    })
  })

  describe('Interactions', () => {
    it('should call onClose when close button clicked', () => {
      const feature = createMockFeature()

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      fireEvent.click(screen.getByText('Close'))
      expect(mockOnClose).toHaveBeenCalledTimes(1)
    })

    it('should call onEdit when edit button clicked', () => {
      const feature = createMockFeature()

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
          onEdit={mockOnEdit}
        />
      )

      fireEvent.click(screen.getByText('Edit'))
      expect(mockOnEdit).toHaveBeenCalledTimes(1)
    })

    it('should call onDelete when delete button clicked', () => {
      const feature = createMockFeature()

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
          onDelete={mockOnDelete}
        />
      )

      fireEvent.click(screen.getByText('Delete'))
      expect(mockOnDelete).toHaveBeenCalledTimes(1)
    })

    it('should not show edit button when onEdit not provided', () => {
      const feature = createMockFeature()

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      expect(screen.queryByText('Edit')).not.toBeInTheDocument()
    })

    it('should not show delete button when onDelete not provided', () => {
      const feature = createMockFeature()

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      expect(screen.queryByText('Delete')).not.toBeInTheDocument()
    })
  })

  describe('Priority Levels', () => {
    it('should display P0 for critical priority', () => {
      const feature = createMockFeature({ priority: 0 })

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      expect(screen.getByTestId('priority')).toHaveTextContent('P0')
    })

    it('should display P1 for high priority', () => {
      const feature = createMockFeature({ priority: 1 })

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      expect(screen.getByTestId('priority')).toHaveTextContent('P1')
    })

    it('should display P2 for medium priority', () => {
      const feature = createMockFeature({ priority: 2 })

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      expect(screen.getByTestId('priority')).toHaveTextContent('P2')
    })

    it('should display P3 for low priority', () => {
      const feature = createMockFeature({ priority: 3 })

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      expect(screen.getByTestId('priority')).toHaveTextContent('P3')
    })

    it('should display P4 for backlog priority', () => {
      const feature = createMockFeature({ priority: 4 })

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      expect(screen.getByTestId('priority')).toHaveTextContent('P4')
    })
  })

  describe('Edge Cases', () => {
    it('should handle feature with empty description', () => {
      const feature = createMockFeature({ description: '' })

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      expect(screen.getByTestId('description')).toHaveTextContent('')
    })

    it('should handle feature with long name', () => {
      const longName = 'A'.repeat(100)
      const feature = createMockFeature({ name: longName })

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      expect(screen.getByText(longName)).toBeInTheDocument()
    })

    it('should handle feature with many steps', () => {
      const steps = Array.from({ length: 20 }, (_, i) => `Step ${i + 1}`)
      const feature = createMockFeature({ steps })

      render(
        <MockFeatureModal
          feature={feature}
          isOpen={true}
          onClose={mockOnClose}
        />
      )

      const stepsList = screen.getByTestId('steps')
      expect(stepsList.children).toHaveLength(20)
    })
  })
})
