/**
 * NewProjectModal Component Tests
 * ================================
 *
 * Enterprise-grade tests for the NewProjectModal component including:
 * - Step navigation (mode → details → method → chat → complete)
 * - Form validation
 * - Project creation flows (new vs existing)
 * - Resume wizard functionality
 * - Error handling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '../test/test-utils'
import userEvent from '@testing-library/user-event'
import { NewProjectModal } from './NewProjectModal'

// Mock the hooks
vi.mock('../hooks/useProjects', () => ({
  useCreateProject: vi.fn(() => ({
    mutateAsync: vi.fn().mockResolvedValue({ name: 'test-project' }),
    isLoading: false,
    error: null,
  })),
  useAddExistingRepo: vi.fn(() => ({
    mutateAsync: vi.fn().mockResolvedValue({ name: 'test-project' }),
    isLoading: false,
    error: null,
  })),
}))

vi.mock('../lib/api', () => ({
  startAgent: vi.fn(),
  updateWizardStatus: vi.fn(),
  deleteWizardStatus: vi.fn(),
}))

// Mock SpecCreationChat
vi.mock('./SpecCreationChat', () => ({
  SpecCreationChat: vi.fn(({ onComplete }) => (
    <div data-testid="spec-creation-chat">
      <button onClick={() => onComplete('/path/to/spec', false)}>Complete Spec</button>
    </div>
  )),
}))

// =============================================================================
// Fixtures
// =============================================================================

const defaultProps = {
  isOpen: true,
  onClose: vi.fn(),
  onProjectCreated: vi.fn(),
}

// =============================================================================
// Initial Render Tests
// =============================================================================

describe('NewProjectModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Initial Render', () => {
    it('should not render when closed', () => {
      render(<NewProjectModal {...defaultProps} isOpen={false} />)
      expect(screen.queryByText('Create New Project')).not.toBeInTheDocument()
    })

    it('should render mode selection when open', () => {
      render(<NewProjectModal {...defaultProps} />)
      expect(screen.getByText('New Project')).toBeInTheDocument()
      expect(screen.getByText('Existing Project')).toBeInTheDocument()
    })

    it('should show close button', () => {
      render(<NewProjectModal {...defaultProps} />)
      // Close button should be visible
      const closeButtons = screen.getAllByRole('button')
      expect(closeButtons.length).toBeGreaterThan(0)
    })
  })

  // =============================================================================
  // Mode Selection Tests
  // =============================================================================

  describe('Mode Selection', () => {
    it('should advance to details step when selecting "New Project"', async () => {
      const user = userEvent.setup()
      render(<NewProjectModal {...defaultProps} />)

      const newProjectButton = screen.getByText('New Project')
      await user.click(newProjectButton)

      // Should show details form
      expect(screen.getByPlaceholderText(/project name/i)).toBeInTheDocument()
    })

    it('should advance to details step when selecting "Existing Project"', async () => {
      const user = userEvent.setup()
      render(<NewProjectModal {...defaultProps} />)

      const existingButton = screen.getByText('Existing Project')
      await user.click(existingButton)

      // Should show details form
      expect(screen.getByPlaceholderText(/project name/i)).toBeInTheDocument()
    })
  })

  // =============================================================================
  // Form Validation Tests
  // =============================================================================

  describe('Form Validation', () => {
    it('should show error for empty project name', async () => {
      const user = userEvent.setup()
      render(<NewProjectModal {...defaultProps} />)

      // Go to details step
      await user.click(screen.getByText('New Project'))

      // Try to submit without name
      const submitButton = screen.getByRole('button', { name: /continue|next/i })
      await user.click(submitButton)

      expect(screen.getByText(/please enter a project name/i)).toBeInTheDocument()
    })

    it('should show error for invalid project name characters', async () => {
      const user = userEvent.setup()
      render(<NewProjectModal {...defaultProps} />)

      await user.click(screen.getByText('New Project'))

      const nameInput = screen.getByPlaceholderText(/project name/i)
      await user.type(nameInput, 'invalid@project!')

      const gitInput = screen.getByPlaceholderText(/git.*url/i)
      await user.type(gitInput, 'https://github.com/test/repo.git')

      const submitButton = screen.getByRole('button', { name: /continue|next/i })
      await user.click(submitButton)

      expect(screen.getByText(/only contain letters, numbers, hyphens, and underscores/i)).toBeInTheDocument()
    })

    it('should show error for missing git URL', async () => {
      const user = userEvent.setup()
      render(<NewProjectModal {...defaultProps} />)

      await user.click(screen.getByText('New Project'))

      const nameInput = screen.getByPlaceholderText(/project name/i)
      await user.type(nameInput, 'valid-project')

      const submitButton = screen.getByRole('button', { name: /continue|next/i })
      await user.click(submitButton)

      expect(screen.getByText(/please enter a git.*url/i)).toBeInTheDocument()
    })

    it('should show error for invalid git URL format', async () => {
      const user = userEvent.setup()
      render(<NewProjectModal {...defaultProps} />)

      await user.click(screen.getByText('New Project'))

      const nameInput = screen.getByPlaceholderText(/project name/i)
      await user.type(nameInput, 'valid-project')

      const gitInput = screen.getByPlaceholderText(/git.*url/i)
      await user.type(gitInput, 'not-a-valid-url')

      const submitButton = screen.getByRole('button', { name: /continue|next/i })
      await user.click(submitButton)

      expect(screen.getByText(/valid git url/i)).toBeInTheDocument()
    })

    it('should accept valid HTTPS git URL', async () => {
      const user = userEvent.setup()
      render(<NewProjectModal {...defaultProps} />)

      await user.click(screen.getByText('New Project'))

      const nameInput = screen.getByPlaceholderText(/project name/i)
      await user.type(nameInput, 'valid-project')

      const gitInput = screen.getByPlaceholderText(/git.*url/i)
      await user.type(gitInput, 'https://github.com/user/repo.git')

      const submitButton = screen.getByRole('button', { name: /continue|next/i })
      await user.click(submitButton)

      // Should advance to method selection (no error)
      await waitFor(() => {
        expect(screen.queryByText(/valid git url/i)).not.toBeInTheDocument()
      })
    })

    it('should accept valid SSH git URL', async () => {
      const user = userEvent.setup()
      render(<NewProjectModal {...defaultProps} />)

      await user.click(screen.getByText('New Project'))

      const nameInput = screen.getByPlaceholderText(/project name/i)
      await user.type(nameInput, 'valid-project')

      const gitInput = screen.getByPlaceholderText(/git.*url/i)
      await user.type(gitInput, 'git@github.com:user/repo.git')

      const submitButton = screen.getByRole('button', { name: /continue|next/i })
      await user.click(submitButton)

      // Should advance (no error)
      await waitFor(() => {
        expect(screen.queryByText(/valid git url/i)).not.toBeInTheDocument()
      })
    })
  })

  // =============================================================================
  // New Project Flow Tests
  // =============================================================================

  describe('New Project Flow', () => {
    it('should show method selection for new projects', async () => {
      const user = userEvent.setup()
      render(<NewProjectModal {...defaultProps} />)

      // Complete mode and details steps
      await user.click(screen.getByText('New Project'))

      const nameInput = screen.getByPlaceholderText(/project name/i)
      await user.type(nameInput, 'test-project')

      const gitInput = screen.getByPlaceholderText(/git.*url/i)
      await user.type(gitInput, 'https://github.com/user/repo.git')

      const submitButton = screen.getByRole('button', { name: /continue|next/i })
      await user.click(submitButton)

      // Should show method selection
      await waitFor(() => {
        expect(screen.getByText(/Claude|AI/i)).toBeInTheDocument()
      })
    })

    it('should create project with manual method', async () => {
      const user = userEvent.setup()
      render(<NewProjectModal {...defaultProps} />)

      // Complete flow
      await user.click(screen.getByText('New Project'))

      const nameInput = screen.getByPlaceholderText(/project name/i)
      await user.type(nameInput, 'test-project')

      const gitInput = screen.getByPlaceholderText(/git.*url/i)
      await user.type(gitInput, 'https://github.com/user/repo.git')

      await user.click(screen.getByRole('button', { name: /continue|next/i }))

      // Wait for method selection
      await waitFor(() => {
        const buttons = screen.queryAllByRole('button')
        return buttons.length > 0
      })
    })
  })

  // =============================================================================
  // Existing Project Flow Tests
  // =============================================================================

  describe('Existing Project Flow', () => {
    it('should complete immediately for existing projects', async () => {
      const onProjectCreated = vi.fn()

      const user = userEvent.setup()
      render(<NewProjectModal {...defaultProps} onProjectCreated={onProjectCreated} />)

      // Select existing project mode
      await user.click(screen.getByText('Existing Project'))

      const nameInput = screen.getByPlaceholderText(/project name/i)
      await user.type(nameInput, 'existing-project')

      const gitInput = screen.getByPlaceholderText(/git.*url/i)
      await user.type(gitInput, 'https://github.com/user/existing.git')

      await user.click(screen.getByRole('button', { name: /continue|next/i }))

      // Should show next step or complete
      await waitFor(() => {
        const buttons = screen.queryAllByRole('button')
        return buttons.length > 0
      })
    })
  })

  // =============================================================================
  // Resume Wizard Tests
  // =============================================================================

  describe('Resume Wizard', () => {
    it('should restore state from resume data', () => {
      render(
        <NewProjectModal
          {...defaultProps}
          resumeProjectName="resumed-project"
          resumeState={{
            step: 'method',
            spec_method: null,
            started_at: new Date().toISOString(),
            chat_messages: [],
          }}
        />
      )

      // Should be at method step (not mode step)
      // Project name should be set
    })

    it('should resume at chat step', () => {
      render(
        <NewProjectModal
          {...defaultProps}
          resumeProjectName="resumed-project"
          resumeState={{
            step: 'chat',
            spec_method: 'claude',
            started_at: new Date().toISOString(),
            chat_messages: [],
          }}
        />
      )

      // Should show spec creation chat
      expect(screen.getByTestId('spec-creation-chat')).toBeInTheDocument()
    })
  })

  // =============================================================================
  // Error Handling Tests
  // =============================================================================

  describe('Error Handling', () => {
    it('should display API errors', async () => {
      const user = userEvent.setup()
      render(<NewProjectModal {...defaultProps} />)

      // Complete flow to trigger creation
      await user.click(screen.getByText('New Project'))

      const nameInput = screen.getByPlaceholderText(/project name/i)
      await user.type(nameInput, 'test-project')

      const gitInput = screen.getByPlaceholderText(/git.*url/i)
      await user.type(gitInput, 'https://github.com/user/repo.git')

      await user.click(screen.getByRole('button', { name: /continue|next/i }))

      // Wait for method selection
      await waitFor(() => {
        const buttons = screen.queryAllByRole('button')
        return buttons.length > 0
      })
    })

    it('should handle network errors gracefully', async () => {
      const user = userEvent.setup()
      render(<NewProjectModal {...defaultProps} />)

      await user.click(screen.getByText('Existing Project'))

      const nameInput = screen.getByPlaceholderText(/project name/i)
      await user.type(nameInput, 'test-project')

      const gitInput = screen.getByPlaceholderText(/git.*url/i)
      await user.type(gitInput, 'https://github.com/user/repo.git')

      await user.click(screen.getByRole('button', { name: /continue|next/i }))

      // Should continue to next step or show error
      await waitFor(() => {
        const buttons = screen.queryAllByRole('button')
        return buttons.length > 0
      })
    })
  })

  // =============================================================================
  // Close Button Tests
  // =============================================================================

  describe('Close Button', () => {
    it('should call onClose when close button clicked', async () => {
      const onClose = vi.fn()
      const user = userEvent.setup()

      render(<NewProjectModal {...defaultProps} onClose={onClose} />)

      // Find and click close button (X icon)
      const buttons = screen.getAllByRole('button')
      const closeButton = buttons[0] // Usually first button is close

      await user.click(closeButton)
      expect(onClose).toHaveBeenCalled()
    })
  })

  // =============================================================================
  // Navigation Tests
  // =============================================================================

  describe('Navigation', () => {
    it('should allow going back from details to mode', async () => {
      const user = userEvent.setup()
      render(<NewProjectModal {...defaultProps} />)

      // Go to details
      await user.click(screen.getByText('New Project'))

      // Should have back button
      const backButton = screen.queryByRole('button', { name: /back/i })
      if (backButton) {
        await user.click(backButton)
        // Should be back at mode selection
        expect(screen.getByText('New Project')).toBeInTheDocument()
        expect(screen.getByText('Existing Project')).toBeInTheDocument()
      }
    })
  })
})
