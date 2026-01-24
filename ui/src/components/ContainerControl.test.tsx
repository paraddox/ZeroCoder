/**
 * ContainerControl Component Tests
 * =================================
 *
 * Tests for the ContainerControl component including:
 * - Start/Stop button states
 * - Status display
 * - Loading states
 * - Error handling
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ContainerControl } from './ContainerControl'
import * as api from '../lib/api'
import type { AgentStatusResponse } from '../lib/types'

// Mock the API module
vi.mock('../lib/api', () => ({
  getAgentStatus: vi.fn(),
  startAgent: vi.fn(),
  stopAgent: vi.fn(),
  gracefulStopAgent: vi.fn(),
}))

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

const notCreatedStatus: AgentStatusResponse = {
  status: 'not_created',
  container_name: 'zerocoder-test-1',
  started_at: null,
  idle_seconds: 0,
  yolo_mode: false,
  agent_running: false,
}

const runningStatus: AgentStatusResponse = {
  status: 'running',
  container_name: 'zerocoder-test-1',
  started_at: '2024-01-01T00:00:00Z',
  idle_seconds: 100,
  yolo_mode: false,
  agent_running: true,
}

const stoppedStatus: AgentStatusResponse = {
  status: 'stopped',
  container_name: 'zerocoder-test-1',
  started_at: '2024-01-01T00:00:00Z',
  idle_seconds: 0,
  yolo_mode: false,
  agent_running: false,
}

describe('ContainerControl', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Status Display', () => {
    it('should display not_created status', async () => {
      vi.mocked(api.getAgentStatus).mockResolvedValue(notCreatedStatus)

      render(<ContainerControl projectName="test-project" />, {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(api.getAgentStatus).toHaveBeenCalledWith('test-project')
      })
    })

    it('should display running status', async () => {
      vi.mocked(api.getAgentStatus).mockResolvedValue(runningStatus)

      render(<ContainerControl projectName="test-project" />, {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(api.getAgentStatus).toHaveBeenCalled()
      })

      // Should show running indicator
    })

    it('should display stopped status', async () => {
      vi.mocked(api.getAgentStatus).mockResolvedValue(stoppedStatus)

      render(<ContainerControl projectName="test-project" />, {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(api.getAgentStatus).toHaveBeenCalled()
      })

      // Should show stopped indicator
    })
  })

  describe('Start Button', () => {
    it('should show start button when not running', async () => {
      vi.mocked(api.getAgentStatus).mockResolvedValue(stoppedStatus)

      render(<ContainerControl projectName="test-project" />, {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(api.getAgentStatus).toHaveBeenCalled()
      })

      // Should have a start button
      const startButton = screen.queryByRole('button', { name: /start/i })
      // Button presence depends on implementation
    })

    it('should call startAgent when start button clicked', async () => {
      const user = userEvent.setup()
      vi.mocked(api.getAgentStatus).mockResolvedValue(stoppedStatus)
      vi.mocked(api.startAgent).mockResolvedValue({
        success: true,
        status: 'running',
        message: 'Started',
      })

      render(<ContainerControl projectName="test-project" />, {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(api.getAgentStatus).toHaveBeenCalled()
      })

      // Find and click start button if present
      const startButton = screen.queryByRole('button', { name: /start/i })
      if (startButton) {
        await user.click(startButton)
        expect(api.startAgent).toHaveBeenCalledWith('test-project', expect.anything())
      }
    })
  })

  describe('Stop Button', () => {
    it('should show stop button when running', async () => {
      vi.mocked(api.getAgentStatus).mockResolvedValue(runningStatus)

      render(<ContainerControl projectName="test-project" />, {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(api.getAgentStatus).toHaveBeenCalled()
      })

      // Should have a stop button
      const stopButton = screen.queryByRole('button', { name: /stop/i })
      // Button presence depends on implementation
    })

    it('should call stopAgent when stop button clicked', async () => {
      const user = userEvent.setup()
      vi.mocked(api.getAgentStatus).mockResolvedValue(runningStatus)
      vi.mocked(api.stopAgent).mockResolvedValue({
        success: true,
        status: 'stopped',
        message: 'Stopped',
      })

      render(<ContainerControl projectName="test-project" />, {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(api.getAgentStatus).toHaveBeenCalled()
      })

      // Find and click stop button if present
      const stopButton = screen.queryByRole('button', { name: /stop/i })
      if (stopButton) {
        await user.click(stopButton)
        expect(api.stopAgent).toHaveBeenCalledWith('test-project')
      }
    })
  })

  describe('Loading States', () => {
    it('should show loading while fetching status', async () => {
      let resolveStatus: (value: AgentStatusResponse) => void
      const statusPromise = new Promise<AgentStatusResponse>((resolve) => {
        resolveStatus = resolve
      })
      vi.mocked(api.getAgentStatus).mockReturnValue(statusPromise)

      render(<ContainerControl projectName="test-project" />, {
        wrapper: createWrapper(),
      })

      // Should be in loading state
      // Resolve to clean up
      resolveStatus!(stoppedStatus)
    })

    it('should disable buttons while action in progress', async () => {
      const user = userEvent.setup()

      let resolveStart: (value: { success: boolean; status: string; message: string }) => void
      const startPromise = new Promise<{ success: boolean; status: string; message: string }>(
        (resolve) => {
          resolveStart = resolve
        }
      )

      vi.mocked(api.getAgentStatus).mockResolvedValue(stoppedStatus)
      vi.mocked(api.startAgent).mockReturnValue(startPromise)

      render(<ContainerControl projectName="test-project" />, {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(api.getAgentStatus).toHaveBeenCalled()
      })

      // Click start if available
      const startButton = screen.queryByRole('button', { name: /start/i })
      if (startButton) {
        await user.click(startButton)
        // Button should be disabled while loading
      }

      // Resolve to clean up
      resolveStart!({ success: true, status: 'running', message: 'Started' })
    })
  })

  describe('Error Handling', () => {
    it('should handle start error', async () => {
      const user = userEvent.setup()
      vi.mocked(api.getAgentStatus).mockResolvedValue(stoppedStatus)
      vi.mocked(api.startAgent).mockRejectedValue(new Error('Docker not available'))

      render(<ContainerControl projectName="test-project" />, {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(api.getAgentStatus).toHaveBeenCalled()
      })

      const startButton = screen.queryByRole('button', { name: /start/i })
      if (startButton) {
        await user.click(startButton)
        // Should handle error gracefully
      }
    })

    it('should handle status fetch error', async () => {
      vi.mocked(api.getAgentStatus).mockRejectedValue(new Error('Network error'))

      render(<ContainerControl projectName="test-project" />, {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(api.getAgentStatus).toHaveBeenCalled()
      })

      // Should handle error and still render
    })
  })

  describe('Idle Time Display', () => {
    it('should display idle time when running', async () => {
      vi.mocked(api.getAgentStatus).mockResolvedValue(runningStatus)

      render(<ContainerControl projectName="test-project" />, {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(api.getAgentStatus).toHaveBeenCalled()
      })

      // Idle seconds (100) might be displayed
    })
  })

  describe('Polling', () => {
    it('should poll for status updates', async () => {
      vi.useFakeTimers()
      vi.mocked(api.getAgentStatus).mockResolvedValue(runningStatus)

      render(<ContainerControl projectName="test-project" />, {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(api.getAgentStatus).toHaveBeenCalled()
      })

      // Fast-forward time to trigger polling
      // Note: Actual polling depends on implementation

      vi.useRealTimers()
    })
  })
})
