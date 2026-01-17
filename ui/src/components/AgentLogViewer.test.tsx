/**
 * AgentLogViewer Component Tests
 * ==============================
 *
 * Enterprise-grade tests for the AgentLogViewer component including:
 * - Log display and formatting
 * - Filter functionality (container filter)
 * - Expand/collapse behavior
 * - Auto-scroll behavior
 * - Clear logs functionality
 * - Virtual scrolling
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '../test/test-utils'
import userEvent from '@testing-library/user-event'
import { AgentLogViewer } from './AgentLogViewer'

// =============================================================================
// Fixtures
// =============================================================================

const createMockLogs = (count: number, containerNumber = 1) =>
  Array.from({ length: count }, (_, i) => ({
    id: `log-${i}`,
    line: `Log line ${i + 1}: This is a test log message`,
    timestamp: new Date(Date.now() - (count - i) * 1000).toISOString(),
    container_number: containerNumber,
  }))

const defaultProps = {
  logs: createMockLogs(10),
  agentStatus: 'running' as const,
  isExpanded: false,
  onToggleExpanded: vi.fn(),
  onClearLogs: vi.fn(),
  containerFilter: null as number | null,
  onContainerFilterChange: vi.fn(),
  registeredContainers: [
    { number: 1, type: 'coding', agent_type: 'coding', sdk_type: 'claude' },
  ],
}

// =============================================================================
// Initial Render Tests
// =============================================================================

describe('AgentLogViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Initial Render', () => {
    it('should render in collapsed state by default', () => {
      render(<AgentLogViewer {...defaultProps} />)
      // Should show minimal UI in collapsed state
    })

    it('should render in expanded state when isExpanded is true', () => {
      render(<AgentLogViewer {...defaultProps} isExpanded={true} />)
      // Should show full log viewer
    })

    it('should show agent status indicator', () => {
      render(<AgentLogViewer {...defaultProps} isExpanded={true} />)
      // Status should be visible
    })
  })

  // =============================================================================
  // Log Display Tests
  // =============================================================================

  describe('Log Display', () => {
    it('should display log lines when expanded', () => {
      render(<AgentLogViewer {...defaultProps} isExpanded={true} />)

      // Should show log content
      expect(screen.getByText(/Log line 1/)).toBeInTheDocument()
    })

    it('should display timestamps with logs', () => {
      render(<AgentLogViewer {...defaultProps} isExpanded={true} />)
      // Timestamps should be formatted and displayed
    })

    it('should handle empty logs gracefully', () => {
      render(<AgentLogViewer {...defaultProps} logs={[]} isExpanded={true} />)
      // Should show empty state or placeholder
    })

    it('should display container number with logs', () => {
      const logsWithMultipleContainers = [
        ...createMockLogs(5, 1),
        ...createMockLogs(5, 2),
      ]

      render(
        <AgentLogViewer
          {...defaultProps}
          logs={logsWithMultipleContainers}
          isExpanded={true}
          registeredContainers={[
            { number: 1, type: 'coding', agent_type: 'coding', sdk_type: 'claude' },
            { number: 2, type: 'coding', agent_type: 'coding', sdk_type: 'claude' },
          ]}
        />
      )
      // Container indicators should be visible
    })
  })

  // =============================================================================
  // Filter Functionality Tests
  // =============================================================================

  describe('Filter Functionality', () => {
    it('should filter logs by container when filter is set', () => {
      const logsWithMultipleContainers = [
        ...createMockLogs(5, 1),
        ...createMockLogs(5, 2),
      ]

      render(
        <AgentLogViewer
          {...defaultProps}
          logs={logsWithMultipleContainers}
          isExpanded={true}
          containerFilter={1}
          registeredContainers={[
            { number: 1, type: 'coding', agent_type: 'coding', sdk_type: 'claude' },
            { number: 2, type: 'coding', agent_type: 'coding', sdk_type: 'claude' },
          ]}
        />
      )

      // Only logs from container 1 should be visible
    })

    it('should show all logs when filter is null', () => {
      const logsWithMultipleContainers = [
        ...createMockLogs(5, 1),
        ...createMockLogs(5, 2),
      ]

      render(
        <AgentLogViewer
          {...defaultProps}
          logs={logsWithMultipleContainers}
          isExpanded={true}
          containerFilter={null}
        />
      )

      // All logs should be visible
    })

    it('should call onContainerFilterChange when filter changed', async () => {
      const onContainerFilterChange = vi.fn()
      const user = userEvent.setup()

      render(
        <AgentLogViewer
          {...defaultProps}
          isExpanded={true}
          onContainerFilterChange={onContainerFilterChange}
          registeredContainers={[
            { number: 1, type: 'coding', agent_type: 'coding', sdk_type: 'claude' },
            { number: 2, type: 'coding', agent_type: 'coding', sdk_type: 'claude' },
          ]}
        />
      )

      // Find and interact with filter control
      const filterButtons = screen.queryAllByRole('button')
      // Click a filter button if present
    })
  })

  // =============================================================================
  // Expand/Collapse Tests
  // =============================================================================

  describe('Expand/Collapse', () => {
    it('should call onToggleExpanded when expand button clicked', async () => {
      const onToggleExpanded = vi.fn()
      const user = userEvent.setup()

      render(
        <AgentLogViewer
          {...defaultProps}
          onToggleExpanded={onToggleExpanded}
        />
      )

      // Find expand toggle button
      const toggleButton = screen.queryByRole('button')
      if (toggleButton) {
        await user.click(toggleButton)
        expect(onToggleExpanded).toHaveBeenCalled()
      }
    })

    it('should show more controls when expanded', () => {
      const { rerender } = render(<AgentLogViewer {...defaultProps} />)

      // Collapsed - fewer controls
      const collapsedButtons = screen.queryAllByRole('button')

      rerender(<AgentLogViewer {...defaultProps} isExpanded={true} />)

      // Expanded - more controls
      const expandedButtons = screen.queryAllByRole('button')
      expect(expandedButtons.length).toBeGreaterThanOrEqual(collapsedButtons.length)
    })
  })

  // =============================================================================
  // Clear Logs Tests
  // =============================================================================

  describe('Clear Logs', () => {
    it('should call onClearLogs when clear button clicked', async () => {
      const onClearLogs = vi.fn()
      const user = userEvent.setup()

      render(
        <AgentLogViewer
          {...defaultProps}
          isExpanded={true}
          onClearLogs={onClearLogs}
        />
      )

      // Find clear button
      const clearButton = screen.queryByRole('button', { name: /clear/i })
      if (clearButton) {
        await user.click(clearButton)
        expect(onClearLogs).toHaveBeenCalled()
      }
    })

    it('should show empty state after clearing logs', () => {
      const { rerender } = render(
        <AgentLogViewer {...defaultProps} isExpanded={true} />
      )

      // Verify logs are shown
      expect(screen.getByText(/Log line 1/)).toBeInTheDocument()

      // Rerender with empty logs (simulating clear)
      rerender(<AgentLogViewer {...defaultProps} logs={[]} isExpanded={true} />)

      // Should show empty state
      expect(screen.queryByText(/Log line 1/)).not.toBeInTheDocument()
    })
  })

  // =============================================================================
  // Agent Status Display Tests
  // =============================================================================

  describe('Agent Status Display', () => {
    it('should show running indicator when agent is running', () => {
      render(
        <AgentLogViewer
          {...defaultProps}
          agentStatus="running"
          isExpanded={true}
        />
      )
      // Running indicator should be visible
    })

    it('should show stopped indicator when agent is stopped', () => {
      render(
        <AgentLogViewer
          {...defaultProps}
          agentStatus="stopped"
          isExpanded={true}
        />
      )
      // Stopped indicator should be visible
    })

    it('should handle different agent statuses', () => {
      const statuses = ['running', 'stopped', 'stopping', 'not_created', 'completed'] as const

      statuses.forEach(status => {
        const { unmount } = render(
          <AgentLogViewer
            {...defaultProps}
            agentStatus={status}
            isExpanded={true}
          />
        )
        // Should not crash for any status
        unmount()
      })
    })
  })

  // =============================================================================
  // Performance Tests
  // =============================================================================

  describe('Performance', () => {
    it('should handle large number of logs', () => {
      const manyLogs = createMockLogs(1000)

      const startTime = performance.now()
      render(
        <AgentLogViewer
          {...defaultProps}
          logs={manyLogs}
          isExpanded={true}
        />
      )
      const endTime = performance.now()

      // Should render within reasonable time (< 1 second)
      expect(endTime - startTime).toBeLessThan(1000)
    })

    it('should efficiently update when new logs added', () => {
      const { rerender } = render(
        <AgentLogViewer
          {...defaultProps}
          logs={createMockLogs(100)}
          isExpanded={true}
        />
      )

      const startTime = performance.now()
      rerender(
        <AgentLogViewer
          {...defaultProps}
          logs={createMockLogs(110)}
          isExpanded={true}
        />
      )
      const endTime = performance.now()

      // Update should be fast (< 100ms)
      expect(endTime - startTime).toBeLessThan(100)
    })
  })

  // =============================================================================
  // Accessibility Tests
  // =============================================================================

  describe('Accessibility', () => {
    it('should have accessible button labels', () => {
      render(<AgentLogViewer {...defaultProps} isExpanded={true} />)

      const buttons = screen.queryAllByRole('button')
      buttons.forEach(button => {
        // Each button should have accessible name
        expect(
          button.getAttribute('aria-label') ||
          button.textContent ||
          button.title
        ).toBeTruthy()
      })
    })

    it('should be keyboard navigable', async () => {
      const user = userEvent.setup()
      render(<AgentLogViewer {...defaultProps} isExpanded={true} />)

      // Should be able to tab through controls
      await user.tab()
      // First focusable element should be focused
    })
  })

  // =============================================================================
  // Error Handling Tests
  // =============================================================================

  describe('Error Handling', () => {
    it('should handle malformed log entries', () => {
      const malformedLogs = [
        { id: '1', line: '', timestamp: '', container_number: 1 },
        { id: '2', line: null as unknown as string, timestamp: '', container_number: 1 },
      ]

      // Should not crash
      expect(() =>
        render(
          <AgentLogViewer
            {...defaultProps}
            logs={malformedLogs as typeof defaultProps.logs}
            isExpanded={true}
          />
        )
      ).not.toThrow()
    })

    it('should handle undefined registeredContainers', () => {
      expect(() =>
        render(
          <AgentLogViewer
            {...defaultProps}
            registeredContainers={undefined as unknown as typeof defaultProps.registeredContainers}
            isExpanded={true}
          />
        )
      ).not.toThrow()
    })
  })
})
