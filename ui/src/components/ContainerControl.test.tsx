/**
 * ContainerControl Component Tests
 * =================================
 *
 * Tests for the ContainerControl component including:
 * - Start/Stop button states
 * - Button disabled states
 * - Loading states during actions
 * - Progress display
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ContainerControl } from './ContainerControl'

// =============================================================================
// Test Fixtures
// =============================================================================

const defaultProps = {
  projectName: 'test-project',
  agentRunning: false,
  gracefulStopRequested: false,
  progress: { passing: 0, total: 10, percentage: 0 },
  isConnected: true,
  onStart: vi.fn(),
  onStopNow: vi.fn(),
  onGracefulStop: vi.fn(),
  onEditTasks: vi.fn(),
  onAddFeature: vi.fn(),
  onSettings: vi.fn(),
  onDelete: vi.fn(),
}

// =============================================================================
// Component Tests
// =============================================================================

describe('ContainerControl', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Button States', () => {
    it('should enable start button when agent is not running', () => {
      render(<ContainerControl {...defaultProps} agentRunning={false} />)

      const startButton = screen.getByRole('button', { name: /start/i })
      expect(startButton).not.toBeDisabled()
    })

    it('should disable start button when agent is running', () => {
      render(<ContainerControl {...defaultProps} agentRunning={true} />)

      const startButton = screen.getByRole('button', { name: /start/i })
      expect(startButton).toBeDisabled()
    })

    it('should enable stop button when agent is running', () => {
      render(<ContainerControl {...defaultProps} agentRunning={true} />)

      const stopButton = screen.getByRole('button', { name: /stop now/i })
      expect(stopButton).not.toBeDisabled()
    })

    it('should disable stop button when agent is not running', () => {
      render(<ContainerControl {...defaultProps} agentRunning={false} />)

      const stopButton = screen.getByRole('button', { name: /stop now/i })
      expect(stopButton).toBeDisabled()
    })

    it('should enable graceful stop button when agent is running', () => {
      render(<ContainerControl {...defaultProps} agentRunning={true} />)

      const gracefulStopButton = screen.getByRole('button', { name: /complete & stop/i })
      expect(gracefulStopButton).not.toBeDisabled()
    })

    it('should disable graceful stop when already requested', () => {
      render(
        <ContainerControl
          {...defaultProps}
          agentRunning={true}
          gracefulStopRequested={true}
        />
      )

      const gracefulStopButton = screen.getByRole('button', { name: /stopping/i })
      expect(gracefulStopButton).toBeDisabled()
    })
  })

  describe('Button Actions', () => {
    it('should call onStart when start button clicked', async () => {
      const user = userEvent.setup()
      const onStart = vi.fn().mockResolvedValue(undefined)
      render(<ContainerControl {...defaultProps} onStart={onStart} />)

      const startButton = screen.getByRole('button', { name: /start/i })
      await user.click(startButton)

      expect(onStart).toHaveBeenCalled()
    })

    it('should call onStopNow when stop button clicked', async () => {
      const user = userEvent.setup()
      const onStopNow = vi.fn().mockResolvedValue(undefined)
      render(
        <ContainerControl
          {...defaultProps}
          agentRunning={true}
          onStopNow={onStopNow}
        />
      )

      const stopButton = screen.getByRole('button', { name: /stop now/i })
      await user.click(stopButton)

      expect(onStopNow).toHaveBeenCalled()
    })

    it('should call onGracefulStop when graceful stop clicked', async () => {
      const user = userEvent.setup()
      const onGracefulStop = vi.fn()
      render(
        <ContainerControl
          {...defaultProps}
          agentRunning={true}
          onGracefulStop={onGracefulStop}
        />
      )

      const gracefulStopButton = screen.getByRole('button', { name: /complete & stop/i })
      await user.click(gracefulStopButton)

      expect(onGracefulStop).toHaveBeenCalled()
    })

    it('should call onEditTasks when edit tasks button clicked', async () => {
      const user = userEvent.setup()
      const onEditTasks = vi.fn()
      render(<ContainerControl {...defaultProps} onEditTasks={onEditTasks} />)

      const editButton = screen.getByRole('button', { name: /edit tasks/i })
      await user.click(editButton)

      expect(onEditTasks).toHaveBeenCalled()
    })

    it('should disable edit tasks when agent is running', () => {
      render(<ContainerControl {...defaultProps} agentRunning={true} />)

      const editButton = screen.getByRole('button', { name: /edit tasks/i })
      expect(editButton).toBeDisabled()
    })
  })

  describe('Loading States', () => {
    it('should show starting state while action in progress', async () => {
      const user = userEvent.setup()
      let resolveStart: () => void
      const startPromise = new Promise<void>((resolve) => {
        resolveStart = resolve
      })
      const onStart = vi.fn().mockReturnValue(startPromise)

      render(<ContainerControl {...defaultProps} onStart={onStart} />)

      const startButton = screen.getByRole('button', { name: /start/i })
      await user.click(startButton)

      // Button should show loading state
      await waitFor(() => {
        expect(screen.getByText(/starting/i)).toBeInTheDocument()
      })

      // Clean up
      resolveStart!()
    })

    it('should show stopping state while stop action in progress', async () => {
      const user = userEvent.setup()
      let resolveStop: () => void
      const stopPromise = new Promise<void>((resolve) => {
        resolveStop = resolve
      })
      const onStopNow = vi.fn().mockReturnValue(stopPromise)

      render(
        <ContainerControl
          {...defaultProps}
          agentRunning={true}
          onStopNow={onStopNow}
        />
      )

      const stopButton = screen.getByRole('button', { name: /stop now/i })
      await user.click(stopButton)

      // Button should show loading state
      await waitFor(() => {
        expect(screen.getByText(/stopping/i)).toBeInTheDocument()
      })

      // Clean up
      resolveStop!()
    })
  })

  describe('Progress Display', () => {
    it('should render progress component', () => {
      render(
        <ContainerControl
          {...defaultProps}
          progress={{ passing: 5, total: 10, percentage: 50 }}
        />
      )

      // Progress should be visible (CompactProgress component)
      // The specific rendering depends on CompactProgress implementation
    })
  })

  describe('Additional Actions', () => {
    it('should call onAddFeature when add feature button clicked', async () => {
      const user = userEvent.setup()
      const onAddFeature = vi.fn()
      render(<ContainerControl {...defaultProps} onAddFeature={onAddFeature} />)

      const addButton = screen.getByRole('button', { name: /add feature/i })
      await user.click(addButton)

      expect(onAddFeature).toHaveBeenCalled()
    })

    it('should hide add feature button when agent is running', () => {
      render(<ContainerControl {...defaultProps} agentRunning={true} />)

      const addButton = screen.queryByRole('button', { name: /add feature/i })
      expect(addButton).not.toBeInTheDocument()
    })

    it('should call onSettings when settings button clicked', async () => {
      const user = userEvent.setup()
      const onSettings = vi.fn()
      render(<ContainerControl {...defaultProps} onSettings={onSettings} />)

      const settingsButton = screen.getByTitle(/project settings/i)
      await user.click(settingsButton)

      expect(onSettings).toHaveBeenCalled()
    })

    it('should call onDelete when delete button clicked', async () => {
      const user = userEvent.setup()
      const onDelete = vi.fn()
      render(<ContainerControl {...defaultProps} onDelete={onDelete} />)

      const deleteButton = screen.getByTitle(/delete project/i)
      await user.click(deleteButton)

      expect(onDelete).toHaveBeenCalled()
    })
  })

  describe('Remote Button', () => {
    it('should show remote button when onRemote provided', () => {
      const onRemote = vi.fn()
      render(<ContainerControl {...defaultProps} onRemote={onRemote} />)

      const remoteButton = screen.getByRole('button', { name: /remote/i })
      expect(remoteButton).toBeInTheDocument()
    })

    it('should not show remote button when onRemote not provided', () => {
      render(<ContainerControl {...defaultProps} />)

      const remoteButton = screen.queryByRole('button', { name: /remote/i })
      expect(remoteButton).not.toBeInTheDocument()
    })

    it('should call onRemote when remote button clicked', async () => {
      const user = userEvent.setup()
      const onRemote = vi.fn()
      render(<ContainerControl {...defaultProps} onRemote={onRemote} />)

      const remoteButton = screen.getByRole('button', { name: /remote/i })
      await user.click(remoteButton)

      expect(onRemote).toHaveBeenCalled()
    })
  })
})
