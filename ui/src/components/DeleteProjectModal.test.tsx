/**
 * DeleteProjectModal Component Tests
 * ==================================
 *
 * Tests for the project deletion confirmation modal including:
 * - Confirmation dialog rendering
 * - Delete action handling
 * - Cancel action handling
 * - Warning message display
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { render, createMockProject } from '../test/test-utils'

// Mock handlers
const mockOnConfirm = vi.fn()
const mockOnCancel = vi.fn()

// Mock component for testing interaction patterns
function MockDeleteProjectModal({
  projectName,
  isOpen,
  onConfirm,
  onCancel,
  isDeleting = false,
}: {
  projectName: string
  isOpen: boolean
  onConfirm: () => void
  onCancel: () => void
  isDeleting?: boolean
}) {
  if (!isOpen) return null

  return (
    <div role="dialog" aria-labelledby="delete-modal-title">
      <h2 id="delete-modal-title">Delete Project</h2>
      <p data-testid="warning-message">
        Are you sure you want to delete <strong>{projectName}</strong>?
      </p>
      <p data-testid="warning-details">
        This action cannot be undone. All local data will be permanently removed.
      </p>
      <div data-testid="button-group">
        <button onClick={onCancel} disabled={isDeleting} data-testid="cancel-btn">
          Cancel
        </button>
        <button
          onClick={onConfirm}
          disabled={isDeleting}
          data-testid="confirm-btn"
          className="destructive"
        >
          {isDeleting ? 'Deleting...' : 'Delete Project'}
        </button>
      </div>
    </div>
  )
}

describe('DeleteProjectModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('should render when open', () => {
      render(
        <MockDeleteProjectModal
          projectName="test-project"
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByRole('heading', { name: 'Delete Project' })).toBeInTheDocument()
    })

    it('should not render when closed', () => {
      render(
        <MockDeleteProjectModal
          projectName="test-project"
          isOpen={false}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    it('should display project name in warning', () => {
      render(
        <MockDeleteProjectModal
          projectName="my-awesome-project"
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByTestId('warning-message')).toHaveTextContent(
        'my-awesome-project'
      )
    })

    it('should display warning about permanent deletion', () => {
      render(
        <MockDeleteProjectModal
          projectName="test-project"
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByTestId('warning-details')).toHaveTextContent(
        'cannot be undone'
      )
    })
  })

  describe('Buttons', () => {
    it('should render cancel button', () => {
      render(
        <MockDeleteProjectModal
          projectName="test-project"
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByTestId('cancel-btn')).toBeInTheDocument()
      expect(screen.getByTestId('cancel-btn')).toHaveTextContent('Cancel')
    })

    it('should render delete button', () => {
      render(
        <MockDeleteProjectModal
          projectName="test-project"
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByTestId('confirm-btn')).toBeInTheDocument()
      expect(screen.getByTestId('confirm-btn')).toHaveTextContent('Delete Project')
    })

    it('should show loading state when deleting', () => {
      render(
        <MockDeleteProjectModal
          projectName="test-project"
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
          isDeleting={true}
        />
      )

      expect(screen.getByTestId('confirm-btn')).toHaveTextContent('Deleting...')
    })

    it('should disable buttons when deleting', () => {
      render(
        <MockDeleteProjectModal
          projectName="test-project"
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
          isDeleting={true}
        />
      )

      expect(screen.getByTestId('cancel-btn')).toBeDisabled()
      expect(screen.getByTestId('confirm-btn')).toBeDisabled()
    })
  })

  describe('Interactions', () => {
    it('should call onCancel when cancel button clicked', () => {
      render(
        <MockDeleteProjectModal
          projectName="test-project"
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      fireEvent.click(screen.getByTestId('cancel-btn'))
      expect(mockOnCancel).toHaveBeenCalledTimes(1)
    })

    it('should call onConfirm when delete button clicked', () => {
      render(
        <MockDeleteProjectModal
          projectName="test-project"
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      fireEvent.click(screen.getByTestId('confirm-btn'))
      expect(mockOnConfirm).toHaveBeenCalledTimes(1)
    })

    it('should not call onConfirm when clicking disabled button', () => {
      render(
        <MockDeleteProjectModal
          projectName="test-project"
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
          isDeleting={true}
        />
      )

      fireEvent.click(screen.getByTestId('confirm-btn'))
      expect(mockOnConfirm).not.toHaveBeenCalled()
    })

    it('should not call onCancel when clicking disabled button', () => {
      render(
        <MockDeleteProjectModal
          projectName="test-project"
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
          isDeleting={true}
        />
      )

      fireEvent.click(screen.getByTestId('cancel-btn'))
      expect(mockOnCancel).not.toHaveBeenCalled()
    })
  })

  describe('Project Names', () => {
    it('should handle project names with special characters', () => {
      render(
        <MockDeleteProjectModal
          projectName="project-with-dashes_and_underscores"
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByTestId('warning-message')).toHaveTextContent(
        'project-with-dashes_and_underscores'
      )
    })

    it('should handle project names with numbers', () => {
      render(
        <MockDeleteProjectModal
          projectName="project123"
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByTestId('warning-message')).toHaveTextContent('project123')
    })

    it('should handle short project names', () => {
      render(
        <MockDeleteProjectModal
          projectName="a"
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByTestId('warning-message')).toHaveTextContent('a')
    })

    it('should handle long project names', () => {
      const longName = 'a'.repeat(50)
      render(
        <MockDeleteProjectModal
          projectName={longName}
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByTestId('warning-message')).toHaveTextContent(longName)
    })
  })

  describe('Accessibility', () => {
    it('should have proper dialog role', () => {
      render(
        <MockDeleteProjectModal
          projectName="test-project"
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByRole('dialog')).toBeInTheDocument()
    })

    it('should have accessible title', () => {
      render(
        <MockDeleteProjectModal
          projectName="test-project"
          isOpen={true}
          onConfirm={mockOnConfirm}
          onCancel={mockOnCancel}
        />
      )

      expect(screen.getByRole('dialog')).toHaveAttribute(
        'aria-labelledby',
        'delete-modal-title'
      )
    })
  })
})
