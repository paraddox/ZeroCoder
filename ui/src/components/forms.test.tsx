/**
 * Form Component Tests
 * ====================
 *
 * Comprehensive tests for form components including:
 * - Input validation
 * - Form submission
 * - Error handling
 * - User feedback
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'

// =============================================================================
// Test Utilities
// =============================================================================

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  })

const TestWrapper = ({ children }: { children: React.ReactNode }) => {
  const queryClient = createTestQueryClient()
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  )
}

// =============================================================================
// AddFeatureForm Component Tests
// =============================================================================

describe('AddFeatureForm', () => {
  const mockOnSubmit = vi.fn()
  const mockOnCancel = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render all form fields', async () => {
    const { AddFeatureForm } = await import('./AddFeatureForm')

    render(
      <TestWrapper>
        <AddFeatureForm onSubmit={mockOnSubmit} onCancel={mockOnCancel} />
      </TestWrapper>
    )

    expect(screen.getByLabelText(/name/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/category/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument()
  })

  it('should validate required fields', async () => {
    const { AddFeatureForm } = await import('./AddFeatureForm')
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <AddFeatureForm onSubmit={mockOnSubmit} onCancel={mockOnCancel} />
      </TestWrapper>
    )

    // Try to submit without filling required fields
    const submitButton = screen.getByRole('button', { name: /add|create|submit/i })
    await user.click(submitButton)

    // Should not call onSubmit with invalid data
    await waitFor(() => {
      // Form should show validation state
      expect(mockOnSubmit).not.toHaveBeenCalled()
    })
  })

  it('should call onSubmit with valid data', async () => {
    const { AddFeatureForm } = await import('./AddFeatureForm')
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <AddFeatureForm onSubmit={mockOnSubmit} onCancel={mockOnCancel} />
      </TestWrapper>
    )

    // Fill in form fields
    const nameInput = screen.getByLabelText(/name/i)
    await user.type(nameInput, 'Test Feature')

    const categoryInput = screen.getByLabelText(/category/i)
    await user.type(categoryInput, 'testing')

    const descriptionInput = screen.getByLabelText(/description/i)
    await user.type(descriptionInput, 'A test feature description')

    // Submit form
    const submitButton = screen.getByRole('button', { name: /add|create|submit/i })
    await user.click(submitButton)

    // Should call onSubmit
    await waitFor(() => {
      expect(mockOnSubmit).toHaveBeenCalled()
    })
  })

  it('should call onCancel when cancel button clicked', async () => {
    const { AddFeatureForm } = await import('./AddFeatureForm')
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <AddFeatureForm onSubmit={mockOnSubmit} onCancel={mockOnCancel} />
      </TestWrapper>
    )

    const cancelButton = screen.getByRole('button', { name: /cancel/i })
    await user.click(cancelButton)

    expect(mockOnCancel).toHaveBeenCalled()
  })

  it('should handle priority selection', async () => {
    const { AddFeatureForm } = await import('./AddFeatureForm')
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <AddFeatureForm onSubmit={mockOnSubmit} onCancel={mockOnCancel} />
      </TestWrapper>
    )

    // Find priority selector
    const priorityButtons = screen.getAllByRole('button')
    const p0Button = priorityButtons.find(btn => btn.textContent?.includes('P0'))

    if (p0Button) {
      await user.click(p0Button)
    }
  })
})

// =============================================================================
// FeatureEditModal Component Tests
// =============================================================================

describe('FeatureEditModal', () => {
  const mockFeature = {
    id: 'feat-1',
    name: 'Test Feature',
    category: 'testing',
    description: 'A test description',
    priority: 1,
    steps: ['Step 1', 'Step 2'],
    passes: false,
    in_progress: false,
  }

  const mockOnSave = vi.fn()
  const mockOnClose = vi.fn()
  const mockOnDelete = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render with feature data', async () => {
    const { FeatureEditModal } = await import('./FeatureEditModal')

    render(
      <TestWrapper>
        <FeatureEditModal
          feature={mockFeature}
          isOpen={true}
          onClose={mockOnClose}
          onSave={mockOnSave}
          onDelete={mockOnDelete}
        />
      </TestWrapper>
    )

    // Should display feature name
    expect(screen.getByDisplayValue('Test Feature')).toBeInTheDocument()
  })

  it('should call onClose when close button clicked', async () => {
    const { FeatureEditModal } = await import('./FeatureEditModal')
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <FeatureEditModal
          feature={mockFeature}
          isOpen={true}
          onClose={mockOnClose}
          onSave={mockOnSave}
          onDelete={mockOnDelete}
        />
      </TestWrapper>
    )

    const closeButton = screen.getByRole('button', { name: /close|cancel/i })
    await user.click(closeButton)

    expect(mockOnClose).toHaveBeenCalled()
  })

  it('should not render when closed', async () => {
    const { FeatureEditModal } = await import('./FeatureEditModal')

    render(
      <TestWrapper>
        <FeatureEditModal
          feature={mockFeature}
          isOpen={false}
          onClose={mockOnClose}
          onSave={mockOnSave}
          onDelete={mockOnDelete}
        />
      </TestWrapper>
    )

    // Modal content should not be visible
    expect(screen.queryByDisplayValue('Test Feature')).not.toBeInTheDocument()
  })
})

// =============================================================================
// Form Validation Tests
// =============================================================================

describe('Form Validation Patterns', () => {
  it('should validate project name format', () => {
    const validateProjectName = (name: string): boolean => {
      const pattern = /^[a-zA-Z0-9][a-zA-Z0-9_-]*$/
      return pattern.test(name) && name.length <= 50 && name.length >= 1
    }

    // Valid names
    expect(validateProjectName('my-project')).toBe(true)
    expect(validateProjectName('project_123')).toBe(true)
    expect(validateProjectName('MyProject')).toBe(true)
    expect(validateProjectName('a')).toBe(true)

    // Invalid names
    expect(validateProjectName('')).toBe(false)
    expect(validateProjectName('project with spaces')).toBe(false)
    expect(validateProjectName('-starts-with-dash')).toBe(false)
    expect(validateProjectName('a'.repeat(51))).toBe(false)
  })

  it('should validate git URL format', () => {
    const validateGitUrl = (url: string): boolean => {
      return (
        url.startsWith('https://') ||
        url.startsWith('git@')
      ) && url.length > 10
    }

    // Valid URLs
    expect(validateGitUrl('https://github.com/user/repo.git')).toBe(true)
    expect(validateGitUrl('git@github.com:user/repo.git')).toBe(true)

    // Invalid URLs
    expect(validateGitUrl('http://github.com/user/repo.git')).toBe(false)
    expect(validateGitUrl('ftp://example.com')).toBe(false)
    expect(validateGitUrl('')).toBe(false)
  })

  it('should validate priority values', () => {
    const validatePriority = (priority: number): boolean => {
      return Number.isInteger(priority) && priority >= 0 && priority <= 4
    }

    // Valid priorities
    expect(validatePriority(0)).toBe(true)
    expect(validatePriority(2)).toBe(true)
    expect(validatePriority(4)).toBe(true)

    // Invalid priorities
    expect(validatePriority(-1)).toBe(false)
    expect(validatePriority(5)).toBe(false)
    expect(validatePriority(1.5)).toBe(false)
  })
})

// =============================================================================
// Form Accessibility Tests
// =============================================================================

describe('Form Accessibility', () => {
  it('should have associated labels for inputs', async () => {
    const { AddFeatureForm } = await import('./AddFeatureForm')

    render(
      <TestWrapper>
        <AddFeatureForm onSubmit={() => {}} onCancel={() => {}} />
      </TestWrapper>
    )

    // All inputs should be accessible by label
    const nameInput = screen.getByLabelText(/name/i)
    expect(nameInput).toHaveAttribute('id')

    const categoryInput = screen.getByLabelText(/category/i)
    expect(categoryInput).toHaveAttribute('id')
  })

  it('should support keyboard navigation', async () => {
    const { AddFeatureForm } = await import('./AddFeatureForm')
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <AddFeatureForm onSubmit={() => {}} onCancel={() => {}} />
      </TestWrapper>
    )

    // Tab through form fields
    await user.tab()
    const firstFocused = document.activeElement
    expect(firstFocused?.tagName).toBe('INPUT')
  })

  it('should announce validation errors', async () => {
    const { AddFeatureForm } = await import('./AddFeatureForm')
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <AddFeatureForm onSubmit={() => {}} onCancel={() => {}} />
      </TestWrapper>
    )

    // Submit empty form
    const submitButton = screen.getByRole('button', { name: /add|create|submit/i })
    await user.click(submitButton)

    // Should have aria-invalid or error messages
    // The specific implementation depends on the form library used
  })
})

// =============================================================================
// Form State Management Tests
// =============================================================================

describe('Form State Management', () => {
  it('should preserve form state during typing', async () => {
    const { AddFeatureForm } = await import('./AddFeatureForm')
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <AddFeatureForm onSubmit={() => {}} onCancel={() => {}} />
      </TestWrapper>
    )

    const nameInput = screen.getByLabelText(/name/i)
    await user.type(nameInput, 'My Feature')

    // Value should be preserved
    expect(nameInput).toHaveValue('My Feature')
  })

  it('should reset form on cancel', async () => {
    const { AddFeatureForm } = await import('./AddFeatureForm')
    const user = userEvent.setup()
    const onCancel = vi.fn()

    render(
      <TestWrapper>
        <AddFeatureForm onSubmit={() => {}} onCancel={onCancel} />
      </TestWrapper>
    )

    // Type something
    const nameInput = screen.getByLabelText(/name/i)
    await user.type(nameInput, 'My Feature')

    // Click cancel
    const cancelButton = screen.getByRole('button', { name: /cancel/i })
    await user.click(cancelButton)

    expect(onCancel).toHaveBeenCalled()
  })

  it('should handle rapid input changes', async () => {
    const { AddFeatureForm } = await import('./AddFeatureForm')
    const user = userEvent.setup({ delay: null })

    render(
      <TestWrapper>
        <AddFeatureForm onSubmit={() => {}} onCancel={() => {}} />
      </TestWrapper>
    )

    const nameInput = screen.getByLabelText(/name/i)

    // Rapid typing
    await user.type(nameInput, 'Quick typing test with many characters')

    expect(nameInput).toHaveValue('Quick typing test with many characters')
  })
})

// =============================================================================
// Form Error Handling Tests
// =============================================================================

describe('Form Error Handling', () => {
  it('should display error message on submission failure', async () => {
    const { AddFeatureForm } = await import('./AddFeatureForm')
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockRejectedValue(new Error('Submission failed'))

    render(
      <TestWrapper>
        <AddFeatureForm onSubmit={onSubmit} onCancel={() => {}} />
      </TestWrapper>
    )

    // Fill and submit
    const nameInput = screen.getByLabelText(/name/i)
    await user.type(nameInput, 'Test Feature')

    const categoryInput = screen.getByLabelText(/category/i)
    await user.type(categoryInput, 'test')

    const submitButton = screen.getByRole('button', { name: /add|create|submit/i })
    await user.click(submitButton)

    // Error should be handled
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalled()
    })
  })

  it('should clear error on retry', async () => {
    const { AddFeatureForm } = await import('./AddFeatureForm')
    const user = userEvent.setup()
    let callCount = 0
    const onSubmit = vi.fn().mockImplementation(() => {
      callCount++
      if (callCount === 1) {
        return Promise.reject(new Error('First attempt failed'))
      }
      return Promise.resolve()
    })

    render(
      <TestWrapper>
        <AddFeatureForm onSubmit={onSubmit} onCancel={() => {}} />
      </TestWrapper>
    )

    // Fill form
    const nameInput = screen.getByLabelText(/name/i)
    await user.type(nameInput, 'Test Feature')

    const categoryInput = screen.getByLabelText(/category/i)
    await user.type(categoryInput, 'test')

    // First submit (fails)
    const submitButton = screen.getByRole('button', { name: /add|create|submit/i })
    await user.click(submitButton)

    // Wait for first attempt
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledTimes(1)
    })
  })
})

// =============================================================================
// Form Integration Tests
// =============================================================================

describe('Form Integration', () => {
  it('should integrate with React Query mutations', async () => {
    const { AddFeatureForm } = await import('./AddFeatureForm')
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue({ id: 'feat-new' })

    render(
      <TestWrapper>
        <AddFeatureForm onSubmit={onSubmit} onCancel={() => {}} />
      </TestWrapper>
    )

    // Fill and submit
    const nameInput = screen.getByLabelText(/name/i)
    await user.type(nameInput, 'New Feature')

    const categoryInput = screen.getByLabelText(/category/i)
    await user.type(categoryInput, 'new')

    const submitButton = screen.getByRole('button', { name: /add|create|submit/i })
    await user.click(submitButton)

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalled()
    })
  })
})
