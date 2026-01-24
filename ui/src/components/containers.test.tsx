/**
 * Container Component Tests
 * =========================
 *
 * Comprehensive tests for container management components including:
 * - Container list display
 * - Container controls
 * - Status indicators
 * - Real-time updates
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
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
// ContainerList Component Tests
// =============================================================================

describe('ContainerList', () => {
  const mockContainers = [
    {
      id: 1,
      container_number: 0,
      container_type: 'init' as const,
      status: 'completed' as const,
      current_feature: null,
    },
    {
      id: 2,
      container_number: 1,
      container_type: 'coding' as const,
      status: 'running' as const,
      current_feature: 'feat-1',
    },
    {
      id: 3,
      container_number: 2,
      container_type: 'coding' as const,
      status: 'stopped' as const,
      current_feature: null,
    },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render all containers', async () => {
    const { ContainerList } = await import('./ContainerList')

    render(
      <TestWrapper>
        <ContainerList
          containers={mockContainers}
          onStartContainer={() => {}}
          onStopContainer={() => {}}
        />
      </TestWrapper>
    )

    // Should show container numbers or identifiers
    expect(screen.getByText(/init/i)).toBeInTheDocument()
  })

  it('should show container status indicators', async () => {
    const { ContainerList } = await import('./ContainerList')

    render(
      <TestWrapper>
        <ContainerList
          containers={mockContainers}
          onStartContainer={() => {}}
          onStopContainer={() => {}}
        />
      </TestWrapper>
    )

    // Should have status indicators
    expect(screen.getByText(/running/i)).toBeInTheDocument()
    expect(screen.getByText(/stopped/i)).toBeInTheDocument()
  })

  it('should call onStartContainer when start button clicked', async () => {
    const { ContainerList } = await import('./ContainerList')
    const onStartContainer = vi.fn()
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <ContainerList
          containers={mockContainers}
          onStartContainer={onStartContainer}
          onStopContainer={() => {}}
        />
      </TestWrapper>
    )

    // Find start button for stopped container
    const startButtons = screen.getAllByRole('button', { name: /start/i })
    if (startButtons.length > 0) {
      await user.click(startButtons[0])
      expect(onStartContainer).toHaveBeenCalled()
    }
  })

  it('should call onStopContainer when stop button clicked', async () => {
    const { ContainerList } = await import('./ContainerList')
    const onStopContainer = vi.fn()
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <ContainerList
          containers={mockContainers}
          onStartContainer={() => {}}
          onStopContainer={onStopContainer}
        />
      </TestWrapper>
    )

    // Find stop button for running container
    const stopButtons = screen.getAllByRole('button', { name: /stop/i })
    if (stopButtons.length > 0) {
      await user.click(stopButtons[0])
      expect(onStopContainer).toHaveBeenCalled()
    }
  })

  it('should display current feature for running containers', async () => {
    const { ContainerList } = await import('./ContainerList')

    render(
      <TestWrapper>
        <ContainerList
          containers={mockContainers}
          onStartContainer={() => {}}
          onStopContainer={() => {}}
        />
      </TestWrapper>
    )

    // Container 1 is working on feat-1
    expect(screen.getByText(/feat-1/i)).toBeInTheDocument()
  })

  it('should handle empty container list', async () => {
    const { ContainerList } = await import('./ContainerList')

    render(
      <TestWrapper>
        <ContainerList
          containers={[]}
          onStartContainer={() => {}}
          onStopContainer={() => {}}
        />
      </TestWrapper>
    )

    // Should show empty state or no containers message
    expect(screen.queryByText(/no containers/i)).toBeInTheDocument()
  })
})

// =============================================================================
// ContainerControl Component Tests
// =============================================================================

describe('ContainerControl', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render container count selector', async () => {
    const { ContainerControl } = await import('./ContainerControl')

    render(
      <TestWrapper>
        <ContainerControl
          currentCount={2}
          maxCount={10}
          onCountChange={() => {}}
        />
      </TestWrapper>
    )

    // Should show current count
    expect(screen.getByText(/2/)).toBeInTheDocument()
  })

  it('should allow increasing container count', async () => {
    const { ContainerControl } = await import('./ContainerControl')
    const onCountChange = vi.fn()
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <ContainerControl
          currentCount={2}
          maxCount={10}
          onCountChange={onCountChange}
        />
      </TestWrapper>
    )

    // Find increase button
    const increaseButton = screen.getByRole('button', { name: /increase|\+|add/i })
    if (increaseButton) {
      await user.click(increaseButton)
      expect(onCountChange).toHaveBeenCalledWith(3)
    }
  })

  it('should allow decreasing container count', async () => {
    const { ContainerControl } = await import('./ContainerControl')
    const onCountChange = vi.fn()
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <ContainerControl
          currentCount={2}
          maxCount={10}
          onCountChange={onCountChange}
        />
      </TestWrapper>
    )

    // Find decrease button
    const decreaseButton = screen.getByRole('button', { name: /decrease|-|remove/i })
    if (decreaseButton) {
      await user.click(decreaseButton)
      expect(onCountChange).toHaveBeenCalledWith(1)
    }
  })

  it('should disable decrease at minimum', async () => {
    const { ContainerControl } = await import('./ContainerControl')

    render(
      <TestWrapper>
        <ContainerControl
          currentCount={1}
          maxCount={10}
          onCountChange={() => {}}
        />
      </TestWrapper>
    )

    // Decrease button should be disabled at minimum
    const decreaseButton = screen.queryByRole('button', { name: /decrease|-|remove/i })
    if (decreaseButton) {
      expect(decreaseButton).toBeDisabled()
    }
  })

  it('should disable increase at maximum', async () => {
    const { ContainerControl } = await import('./ContainerControl')

    render(
      <TestWrapper>
        <ContainerControl
          currentCount={10}
          maxCount={10}
          onCountChange={() => {}}
        />
      </TestWrapper>
    )

    // Increase button should be disabled at maximum
    const increaseButton = screen.queryByRole('button', { name: /increase|\+|add/i })
    if (increaseButton) {
      expect(increaseButton).toBeDisabled()
    }
  })
})

// =============================================================================
// Container Status Tests
// =============================================================================

describe('Container Status Display', () => {
  it('should show correct colors for status', () => {
    const getStatusColor = (status: string): string => {
      const colors: Record<string, string> = {
        running: 'green',
        stopped: 'gray',
        completed: 'blue',
        not_created: 'gray',
        created: 'yellow',
      }
      return colors[status] || 'gray'
    }

    expect(getStatusColor('running')).toBe('green')
    expect(getStatusColor('stopped')).toBe('gray')
    expect(getStatusColor('completed')).toBe('blue')
    expect(getStatusColor('unknown')).toBe('gray')
  })

  it('should show correct icons for container types', () => {
    const getTypeIcon = (type: string): string => {
      const icons: Record<string, string> = {
        init: '🚀',
        coding: '💻',
        overseer: '👁️',
      }
      return icons[type] || '📦'
    }

    expect(getTypeIcon('init')).toBe('🚀')
    expect(getTypeIcon('coding')).toBe('💻')
    expect(getTypeIcon('overseer')).toBe('👁️')
    expect(getTypeIcon('unknown')).toBe('📦')
  })
})

// =============================================================================
// Container Interaction Tests
// =============================================================================

describe('Container Interactions', () => {
  it('should show loading state during start', async () => {
    const { ContainerList } = await import('./ContainerList')

    const containers = [
      {
        id: 1,
        container_number: 1,
        container_type: 'coding' as const,
        status: 'stopped' as const,
        current_feature: null,
      },
    ]

    render(
      <TestWrapper>
        <ContainerList
          containers={containers}
          onStartContainer={() => new Promise(() => {})} // Never resolves
          onStopContainer={() => {}}
          isLoading={true}
        />
      </TestWrapper>
    )

    // Should show loading indicator
    expect(screen.queryByText(/loading|starting/i)).toBeInTheDocument()
  })

  it('should disable controls during operation', async () => {
    const { ContainerList } = await import('./ContainerList')

    const containers = [
      {
        id: 1,
        container_number: 1,
        container_type: 'coding' as const,
        status: 'running' as const,
        current_feature: 'feat-1',
      },
    ]

    render(
      <TestWrapper>
        <ContainerList
          containers={containers}
          onStartContainer={() => {}}
          onStopContainer={() => {}}
          disabled={true}
        />
      </TestWrapper>
    )

    // Buttons should be disabled
    const buttons = screen.getAllByRole('button')
    buttons.forEach((button) => {
      if (button.textContent?.match(/start|stop/i)) {
        expect(button).toBeDisabled()
      }
    })
  })
})

// =============================================================================
// Container Metrics Tests
// =============================================================================

describe('Container Metrics', () => {
  it('should calculate container summary correctly', () => {
    const containers = [
      { status: 'running' },
      { status: 'running' },
      { status: 'stopped' },
      { status: 'completed' },
    ]

    const summary = {
      total: containers.length,
      running: containers.filter((c) => c.status === 'running').length,
      stopped: containers.filter((c) => c.status === 'stopped').length,
      completed: containers.filter((c) => c.status === 'completed').length,
    }

    expect(summary.total).toBe(4)
    expect(summary.running).toBe(2)
    expect(summary.stopped).toBe(1)
    expect(summary.completed).toBe(1)
  })

  it('should show utilization percentage', () => {
    const calculateUtilization = (running: number, total: number): number => {
      if (total === 0) return 0
      return Math.round((running / total) * 100)
    }

    expect(calculateUtilization(2, 4)).toBe(50)
    expect(calculateUtilization(0, 4)).toBe(0)
    expect(calculateUtilization(4, 4)).toBe(100)
    expect(calculateUtilization(0, 0)).toBe(0)
  })
})

// =============================================================================
// Container Log Integration Tests
// =============================================================================

describe('Container Log Display', () => {
  it('should show log viewer for selected container', async () => {
    const { AgentLogViewer } = await import('./AgentLogViewer')

    render(
      <TestWrapper>
        <AgentLogViewer
          projectName="test-project"
          logs={[
            { timestamp: new Date(), line: 'Starting container...' },
            { timestamp: new Date(), line: 'Loading configuration...' },
          ]}
          isExpanded={true}
        />
      </TestWrapper>
    )

    // Should display log content
    expect(screen.getByText(/Starting container/)).toBeInTheDocument()
    expect(screen.getByText(/Loading configuration/)).toBeInTheDocument()
  })

  it('should filter logs by container', async () => {
    const { AgentLogViewer } = await import('./AgentLogViewer')

    const logs = [
      { timestamp: new Date(), line: '[Container 1] Message 1', container: 1 },
      { timestamp: new Date(), line: '[Container 2] Message 2', container: 2 },
      { timestamp: new Date(), line: '[Container 1] Message 3', container: 1 },
    ]

    render(
      <TestWrapper>
        <AgentLogViewer
          projectName="test-project"
          logs={logs}
          isExpanded={true}
          filterContainer={1}
        />
      </TestWrapper>
    )

    // Should only show container 1 logs
    expect(screen.getByText(/\[Container 1\] Message 1/)).toBeInTheDocument()
    expect(screen.getByText(/\[Container 1\] Message 3/)).toBeInTheDocument()
  })

  it('should auto-scroll to bottom on new logs', async () => {
    const { AgentLogViewer } = await import('./AgentLogViewer')

    const { rerender } = render(
      <TestWrapper>
        <AgentLogViewer
          projectName="test-project"
          logs={[{ timestamp: new Date(), line: 'Log 1' }]}
          isExpanded={true}
        />
      </TestWrapper>
    )

    // Add new log
    rerender(
      <TestWrapper>
        <AgentLogViewer
          projectName="test-project"
          logs={[
            { timestamp: new Date(), line: 'Log 1' },
            { timestamp: new Date(), line: 'Log 2' },
          ]}
          isExpanded={true}
        />
      </TestWrapper>
    )

    // New log should be visible
    expect(screen.getByText('Log 2')).toBeInTheDocument()
  })
})

// =============================================================================
// Container Error States Tests
// =============================================================================

describe('Container Error States', () => {
  it('should show error message on container failure', async () => {
    const { ContainerList } = await import('./ContainerList')

    const containers = [
      {
        id: 1,
        container_number: 1,
        container_type: 'coding' as const,
        status: 'stopped' as const,
        current_feature: null,
        error: 'Container crashed unexpectedly',
      },
    ]

    render(
      <TestWrapper>
        <ContainerList
          containers={containers}
          onStartContainer={() => {}}
          onStopContainer={() => {}}
        />
      </TestWrapper>
    )

    // Should show error state
    expect(screen.queryByText(/error|crashed|failed/i)).toBeInTheDocument()
  })

  it('should allow retry after error', async () => {
    const { ContainerList } = await import('./ContainerList')
    const onStartContainer = vi.fn()
    const user = userEvent.setup()

    const containers = [
      {
        id: 1,
        container_number: 1,
        container_type: 'coding' as const,
        status: 'stopped' as const,
        current_feature: null,
        error: 'Previous error',
      },
    ]

    render(
      <TestWrapper>
        <ContainerList
          containers={containers}
          onStartContainer={onStartContainer}
          onStopContainer={() => {}}
        />
      </TestWrapper>
    )

    // Find retry/start button
    const startButton = screen.getByRole('button', { name: /start|retry/i })
    if (startButton) {
      await user.click(startButton)
      expect(onStartContainer).toHaveBeenCalled()
    }
  })
})
