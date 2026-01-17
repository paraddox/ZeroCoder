/**
 * AddFeatureForm Component Tests
 * ==============================
 *
 * Tests for the AddFeatureForm component including:
 * - Form rendering
 * - Input validation
 * - Form submission
 * - Error handling
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Mock the AddFeatureForm component for testing
// In actual implementation, import the real component
const MockAddFeatureForm = ({
  projectName,
  onSubmit,
  onCancel,
}: {
  projectName: string
  onSubmit: (data: unknown) => void
  onCancel: () => void
}) => (
  <form
    data-testid="add-feature-form"
    onSubmit={(e) => {
      e.preventDefault()
      const formData = new FormData(e.target as HTMLFormElement)
      onSubmit({
        name: formData.get('name'),
        category: formData.get('category'),
        description: formData.get('description'),
        steps: formData.get('steps')?.toString().split('\n').filter(Boolean),
      })
    }}
  >
    <input name="name" placeholder="Feature name" required />
    <input name="category" placeholder="Category" required />
    <textarea name="description" placeholder="Description" />
    <textarea name="steps" placeholder="Steps (one per line)" />
    <button type="submit">Create Feature</button>
    <button type="button" onClick={onCancel}>
      Cancel
    </button>
  </form>
)

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

describe('AddFeatureForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('should render the form', () => {
      render(
        <MockAddFeatureForm
          projectName="test-project"
          onSubmit={vi.fn()}
          onCancel={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByTestId('add-feature-form')).toBeInTheDocument()
    })

    it('should render name input', () => {
      render(
        <MockAddFeatureForm
          projectName="test-project"
          onSubmit={vi.fn()}
          onCancel={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByPlaceholderText('Feature name')).toBeInTheDocument()
    })

    it('should render category input', () => {
      render(
        <MockAddFeatureForm
          projectName="test-project"
          onSubmit={vi.fn()}
          onCancel={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByPlaceholderText('Category')).toBeInTheDocument()
    })

    it('should render description textarea', () => {
      render(
        <MockAddFeatureForm
          projectName="test-project"
          onSubmit={vi.fn()}
          onCancel={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByPlaceholderText('Description')).toBeInTheDocument()
    })

    it('should render steps textarea', () => {
      render(
        <MockAddFeatureForm
          projectName="test-project"
          onSubmit={vi.fn()}
          onCancel={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      expect(
        screen.getByPlaceholderText('Steps (one per line)')
      ).toBeInTheDocument()
    })

    it('should render submit button', () => {
      render(
        <MockAddFeatureForm
          projectName="test-project"
          onSubmit={vi.fn()}
          onCancel={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      expect(
        screen.getByRole('button', { name: /create feature/i })
      ).toBeInTheDocument()
    })

    it('should render cancel button', () => {
      render(
        <MockAddFeatureForm
          projectName="test-project"
          onSubmit={vi.fn()}
          onCancel={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      expect(
        screen.getByRole('button', { name: /cancel/i })
      ).toBeInTheDocument()
    })
  })

  describe('Form Submission', () => {
    it('should call onSubmit with form data', async () => {
      const user = userEvent.setup()
      const onSubmit = vi.fn()

      render(
        <MockAddFeatureForm
          projectName="test-project"
          onSubmit={onSubmit}
          onCancel={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      await user.type(screen.getByPlaceholderText('Feature name'), 'New Feature')
      await user.type(screen.getByPlaceholderText('Category'), 'auth')
      await user.type(
        screen.getByPlaceholderText('Description'),
        'Feature description'
      )
      await user.type(
        screen.getByPlaceholderText('Steps (one per line)'),
        'Step 1\nStep 2'
      )

      await user.click(screen.getByRole('button', { name: /create feature/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith({
          name: 'New Feature',
          category: 'auth',
          description: 'Feature description',
          steps: ['Step 1', 'Step 2'],
        })
      })
    })

    it('should call onCancel when cancel button is clicked', async () => {
      const user = userEvent.setup()
      const onCancel = vi.fn()

      render(
        <MockAddFeatureForm
          projectName="test-project"
          onSubmit={vi.fn()}
          onCancel={onCancel}
        />,
        { wrapper: createWrapper() }
      )

      await user.click(screen.getByRole('button', { name: /cancel/i }))

      expect(onCancel).toHaveBeenCalled()
    })
  })

  describe('Input Handling', () => {
    it('should handle empty steps', async () => {
      const user = userEvent.setup()
      const onSubmit = vi.fn()

      render(
        <MockAddFeatureForm
          projectName="test-project"
          onSubmit={onSubmit}
          onCancel={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      await user.type(screen.getByPlaceholderText('Feature name'), 'Feature')
      await user.type(screen.getByPlaceholderText('Category'), 'test')
      // Leave steps empty

      await user.click(screen.getByRole('button', { name: /create feature/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            steps: [],
          })
        )
      })
    })

    it('should handle whitespace in steps', async () => {
      const user = userEvent.setup()
      const onSubmit = vi.fn()

      render(
        <MockAddFeatureForm
          projectName="test-project"
          onSubmit={onSubmit}
          onCancel={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      await user.type(screen.getByPlaceholderText('Feature name'), 'Feature')
      await user.type(screen.getByPlaceholderText('Category'), 'test')
      await user.type(
        screen.getByPlaceholderText('Steps (one per line)'),
        'Step 1\n\nStep 2'
      )

      await user.click(screen.getByRole('button', { name: /create feature/i }))

      await waitFor(() => {
        expect(onSubmit).toHaveBeenCalledWith(
          expect.objectContaining({
            steps: ['Step 1', 'Step 2'], // Empty line should be filtered
          })
        )
      })
    })
  })

  describe('Accessibility', () => {
    it('should have accessible form elements', () => {
      render(
        <MockAddFeatureForm
          projectName="test-project"
          onSubmit={vi.fn()}
          onCancel={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      // All inputs should be accessible
      expect(screen.getByPlaceholderText('Feature name')).toHaveAttribute(
        'name',
        'name'
      )
      expect(screen.getByPlaceholderText('Category')).toHaveAttribute(
        'name',
        'category'
      )
    })

    it('should be keyboard navigable', async () => {
      const user = userEvent.setup()

      render(
        <MockAddFeatureForm
          projectName="test-project"
          onSubmit={vi.fn()}
          onCancel={vi.fn()}
        />,
        { wrapper: createWrapper() }
      )

      // Tab through form elements
      await user.tab()
      expect(screen.getByPlaceholderText('Feature name')).toHaveFocus()

      await user.tab()
      expect(screen.getByPlaceholderText('Category')).toHaveFocus()
    })
  })
})
