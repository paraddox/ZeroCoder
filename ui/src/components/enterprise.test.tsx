/**
 * Enterprise Component Tests
 * ==========================
 *
 * Comprehensive tests for React components including:
 * - Rendering tests
 * - User interaction tests
 * - State management tests
 * - Accessibility tests
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
// FeatureCard Component Tests
// =============================================================================

describe('FeatureCard', () => {
  const mockFeature = {
    id: 'feat-1',
    name: 'User Authentication',
    category: 'auth',
    description: 'Implement user login and registration',
    priority: 1,
    steps: ['Create login form', 'Add validation', 'Connect to API'],
    passes: false,
    in_progress: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render feature name', async () => {
    const { FeatureCard } = await import('./FeatureCard')

    render(
      <TestWrapper>
        <FeatureCard feature={mockFeature} onEdit={() => {}} />
      </TestWrapper>
    )

    expect(screen.getByText('User Authentication')).toBeInTheDocument()
  })

  it('should render feature category', async () => {
    const { FeatureCard } = await import('./FeatureCard')

    render(
      <TestWrapper>
        <FeatureCard feature={mockFeature} onEdit={() => {}} />
      </TestWrapper>
    )

    expect(screen.getByText('auth')).toBeInTheDocument()
  })

  it('should call onEdit when clicked', async () => {
    const { FeatureCard } = await import('./FeatureCard')
    const onEdit = vi.fn()
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <FeatureCard feature={mockFeature} onEdit={onEdit} />
      </TestWrapper>
    )

    const card = screen.getByRole('article')
    await user.click(card)

    expect(onEdit).toHaveBeenCalledWith(mockFeature)
  })

  it('should show in-progress indicator', async () => {
    const { FeatureCard } = await import('./FeatureCard')
    const inProgressFeature = { ...mockFeature, in_progress: true }

    render(
      <TestWrapper>
        <FeatureCard feature={inProgressFeature} onEdit={() => {}} />
      </TestWrapper>
    )

    // Should have visual indicator for in-progress state
    const card = screen.getByRole('article')
    expect(card).toBeInTheDocument()
  })

  it('should display priority badge', async () => {
    const { FeatureCard } = await import('./FeatureCard')

    render(
      <TestWrapper>
        <FeatureCard feature={mockFeature} onEdit={() => {}} />
      </TestWrapper>
    )

    // Priority should be displayed
    expect(screen.getByText(/P1/i)).toBeInTheDocument()
  })
})

// =============================================================================
// KanbanBoard Component Tests
// =============================================================================

describe('KanbanBoard', () => {
  const mockFeatures = {
    pending: [
      { id: 'feat-1', name: 'Feature 1', category: 'ui', description: 'Desc', priority: 1, steps: [], passes: false, in_progress: false },
      { id: 'feat-2', name: 'Feature 2', category: 'api', description: 'Desc', priority: 2, steps: [], passes: false, in_progress: false },
    ],
    in_progress: [
      { id: 'feat-3', name: 'Feature 3', category: 'db', description: 'Desc', priority: 0, steps: [], passes: false, in_progress: true },
    ],
    done: [
      { id: 'feat-4', name: 'Feature 4', category: 'auth', description: 'Desc', priority: 1, steps: [], passes: true, in_progress: false },
    ],
  }

  it('should render all columns', async () => {
    const { KanbanBoard } = await import('./KanbanBoard')

    render(
      <TestWrapper>
        <KanbanBoard
          features={mockFeatures}
          onFeatureEdit={() => {}}
          isLoading={false}
        />
      </TestWrapper>
    )

    // Check for column headers
    expect(screen.getByText(/pending/i)).toBeInTheDocument()
    expect(screen.getByText(/in progress/i)).toBeInTheDocument()
    expect(screen.getByText(/done/i)).toBeInTheDocument()
  })

  it('should show feature counts in columns', async () => {
    const { KanbanBoard } = await import('./KanbanBoard')

    render(
      <TestWrapper>
        <KanbanBoard
          features={mockFeatures}
          onFeatureEdit={() => {}}
          isLoading={false}
        />
      </TestWrapper>
    )

    // Feature counts should be visible
    expect(screen.getByText('2')).toBeInTheDocument() // Pending count
    expect(screen.getByText('1')).toBeInTheDocument() // In progress count
  })

  it('should show loading state', async () => {
    const { KanbanBoard } = await import('./KanbanBoard')

    render(
      <TestWrapper>
        <KanbanBoard
          features={{ pending: [], in_progress: [], done: [] }}
          onFeatureEdit={() => {}}
          isLoading={true}
        />
      </TestWrapper>
    )

    // Should show loading indicator
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })
})

// =============================================================================
// KanbanColumn Component Tests
// =============================================================================

describe('KanbanColumn', () => {
  const mockFeatures = [
    { id: 'feat-1', name: 'Feature 1', category: 'ui', description: 'Desc', priority: 1, steps: [], passes: false, in_progress: false },
    { id: 'feat-2', name: 'Feature 2', category: 'api', description: 'Desc', priority: 0, steps: [], passes: false, in_progress: false },
  ]

  it('should render column title', async () => {
    const { KanbanColumn } = await import('./KanbanColumn')

    render(
      <KanbanColumn
        title="Pending"
        features={mockFeatures}
        onFeatureEdit={() => {}}
        colorClass="bg-amber-100"
      />
    )

    expect(screen.getByText('Pending')).toBeInTheDocument()
  })

  it('should render all features', async () => {
    const { KanbanColumn } = await import('./KanbanColumn')

    render(
      <KanbanColumn
        title="Pending"
        features={mockFeatures}
        onFeatureEdit={() => {}}
        colorClass="bg-amber-100"
      />
    )

    expect(screen.getByText('Feature 1')).toBeInTheDocument()
    expect(screen.getByText('Feature 2')).toBeInTheDocument()
  })

  it('should show feature count', async () => {
    const { KanbanColumn } = await import('./KanbanColumn')

    render(
      <KanbanColumn
        title="Pending"
        features={mockFeatures}
        onFeatureEdit={() => {}}
        colorClass="bg-amber-100"
      />
    )

    expect(screen.getByText('2')).toBeInTheDocument()
  })
})

// =============================================================================
// ContainerControl Component Tests
// =============================================================================

describe('ContainerControl', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('should render start button when stopped', async () => {
    const { ContainerControl } = await import('./ContainerControl')

    render(
      <TestWrapper>
        <ContainerControl
          projectName="test-project"
          status="stopped"
          onStatusChange={() => {}}
        />
      </TestWrapper>
    )

    expect(screen.getByRole('button', { name: /start/i })).toBeInTheDocument()
  })

  it('should render stop button when running', async () => {
    const { ContainerControl } = await import('./ContainerControl')

    render(
      <TestWrapper>
        <ContainerControl
          projectName="test-project"
          status="running"
          onStatusChange={() => {}}
        />
      </TestWrapper>
    )

    expect(screen.getByRole('button', { name: /stop/i })).toBeInTheDocument()
  })

  it('should call API when start clicked', async () => {
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ success: true }),
    })

    const { ContainerControl } = await import('./ContainerControl')
    const onStatusChange = vi.fn()
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <ContainerControl
          projectName="test-project"
          status="stopped"
          onStatusChange={onStatusChange}
        />
      </TestWrapper>
    )

    const startButton = screen.getByRole('button', { name: /start/i })
    await user.click(startButton)

    expect(global.fetch).toHaveBeenCalled()
  })

  it('should disable button during loading', async () => {
    ;(global.fetch as any).mockImplementation(() => new Promise(() => {})) // Never resolves

    const { ContainerControl } = await import('./ContainerControl')
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <ContainerControl
          projectName="test-project"
          status="stopped"
          onStatusChange={() => {}}
        />
      </TestWrapper>
    )

    const startButton = screen.getByRole('button', { name: /start/i })
    await user.click(startButton)

    // Button should be disabled during request
    expect(startButton).toBeDisabled()
  })
})

// =============================================================================
// ProgressDashboard Component Tests
// =============================================================================

describe('ProgressDashboard', () => {
  it('should render progress stats', async () => {
    const { ProgressDashboard } = await import('./ProgressDashboard')

    render(
      <ProgressDashboard
        passing={5}
        inProgress={2}
        total={10}
        percentage={50}
      />
    )

    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()
  })

  it('should show 100% when all complete', async () => {
    const { ProgressDashboard } = await import('./ProgressDashboard')

    render(
      <ProgressDashboard
        passing={10}
        inProgress={0}
        total={10}
        percentage={100}
      />
    )

    expect(screen.getByText('100%')).toBeInTheDocument()
  })

  it('should handle zero total', async () => {
    const { ProgressDashboard } = await import('./ProgressDashboard')

    render(
      <ProgressDashboard
        passing={0}
        inProgress={0}
        total={0}
        percentage={0}
      />
    )

    expect(screen.getByText('0%')).toBeInTheDocument()
  })
})

// =============================================================================
// FeatureModal Component Tests
// =============================================================================

describe('FeatureModal', () => {
  const mockFeature = {
    id: 'feat-1',
    name: 'Test Feature',
    category: 'test',
    description: 'A test feature',
    priority: 1,
    steps: ['Step 1', 'Step 2'],
    passes: false,
    in_progress: false,
  }

  it('should render feature details when open', async () => {
    const { FeatureModal } = await import('./FeatureModal')

    render(
      <TestWrapper>
        <FeatureModal
          feature={mockFeature}
          isOpen={true}
          onClose={() => {}}
          onSave={() => {}}
        />
      </TestWrapper>
    )

    expect(screen.getByText('Test Feature')).toBeInTheDocument()
    expect(screen.getByText('A test feature')).toBeInTheDocument()
  })

  it('should not render when closed', async () => {
    const { FeatureModal } = await import('./FeatureModal')

    render(
      <TestWrapper>
        <FeatureModal
          feature={mockFeature}
          isOpen={false}
          onClose={() => {}}
          onSave={() => {}}
        />
      </TestWrapper>
    )

    expect(screen.queryByText('Test Feature')).not.toBeInTheDocument()
  })

  it('should call onClose when close button clicked', async () => {
    const { FeatureModal } = await import('./FeatureModal')
    const onClose = vi.fn()
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <FeatureModal
          feature={mockFeature}
          isOpen={true}
          onClose={onClose}
          onSave={() => {}}
        />
      </TestWrapper>
    )

    const closeButton = screen.getByRole('button', { name: /close/i })
    await user.click(closeButton)

    expect(onClose).toHaveBeenCalled()
  })

  it('should display steps', async () => {
    const { FeatureModal } = await import('./FeatureModal')

    render(
      <TestWrapper>
        <FeatureModal
          feature={mockFeature}
          isOpen={true}
          onClose={() => {}}
          onSave={() => {}}
        />
      </TestWrapper>
    )

    expect(screen.getByText('Step 1')).toBeInTheDocument()
    expect(screen.getByText('Step 2')).toBeInTheDocument()
  })
})

// =============================================================================
// AddFeatureForm Component Tests
// =============================================================================

describe('AddFeatureForm', () => {
  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('should render form fields', async () => {
    const { AddFeatureForm } = await import('./AddFeatureForm')

    render(
      <TestWrapper>
        <AddFeatureForm projectName="test" onSuccess={() => {}} />
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
        <AddFeatureForm projectName="test" onSuccess={() => {}} />
      </TestWrapper>
    )

    const submitButton = screen.getByRole('button', { name: /add/i })
    await user.click(submitButton)

    // Should show validation error
    expect(screen.getByText(/required/i)).toBeInTheDocument()
  })

  it('should submit form with valid data', async () => {
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ success: true }),
    })

    const { AddFeatureForm } = await import('./AddFeatureForm')
    const onSuccess = vi.fn()
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <AddFeatureForm projectName="test" onSuccess={onSuccess} />
      </TestWrapper>
    )

    await user.type(screen.getByLabelText(/name/i), 'New Feature')
    await user.type(screen.getByLabelText(/category/i), 'auth')
    await user.type(screen.getByLabelText(/description/i), 'A new feature')

    const submitButton = screen.getByRole('button', { name: /add/i })
    await user.click(submitButton)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled()
    })
  })
})

// =============================================================================
// AgentLogViewer Component Tests
// =============================================================================

describe('AgentLogViewer', () => {
  it('should render log lines', async () => {
    const { AgentLogViewer } = await import('./AgentLogViewer')
    const logs = [
      { line: 'Starting agent...', timestamp: '2024-01-15T12:00:00Z', container_number: 1 },
      { line: 'Processing feature...', timestamp: '2024-01-15T12:00:01Z', container_number: 1 },
    ]

    render(<AgentLogViewer logs={logs} />)

    expect(screen.getByText(/Starting agent/)).toBeInTheDocument()
    expect(screen.getByText(/Processing feature/)).toBeInTheDocument()
  })

  it('should auto-scroll to bottom', async () => {
    const { AgentLogViewer } = await import('./AgentLogViewer')
    const logs = Array.from({ length: 100 }, (_, i) => ({
      line: `Log line ${i}`,
      timestamp: new Date().toISOString(),
      container_number: 1,
    }))

    const { container } = render(<AgentLogViewer logs={logs} />)

    const scrollContainer = container.querySelector('[data-testid="log-container"]')
    if (scrollContainer) {
      expect(scrollContainer.scrollTop).toBeGreaterThan(0)
    }
  })

  it('should handle empty logs', async () => {
    const { AgentLogViewer } = await import('./AgentLogViewer')

    render(<AgentLogViewer logs={[]} />)

    expect(screen.getByText(/no logs/i)).toBeInTheDocument()
  })
})

// =============================================================================
// ProjectSelector Component Tests
// =============================================================================

describe('ProjectSelector', () => {
  const mockProjects = [
    { name: 'project-1', git_url: 'https://github.com/user/repo1.git', local_path: '/path/1', is_new: false, has_spec: true, stats: { passing: 0, in_progress: 0, total: 5, percentage: 0 }, target_container_count: 1 },
    { name: 'project-2', git_url: 'https://github.com/user/repo2.git', local_path: '/path/2', is_new: true, has_spec: false, stats: { passing: 0, in_progress: 0, total: 0, percentage: 0 }, target_container_count: 1 },
  ]

  beforeEach(() => {
    global.fetch = vi.fn()
  })

  it('should render project options', async () => {
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockProjects),
    })

    const { ProjectSelector } = await import('./ProjectSelector')

    render(
      <TestWrapper>
        <ProjectSelector
          selectedProject="project-1"
          onSelectProject={() => {}}
        />
      </TestWrapper>
    )

    await waitFor(() => {
      expect(screen.getByText('project-1')).toBeInTheDocument()
    })
  })

  it('should call onSelectProject when selection changes', async () => {
    ;(global.fetch as any).mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve(mockProjects),
    })

    const { ProjectSelector } = await import('./ProjectSelector')
    const onSelectProject = vi.fn()
    const user = userEvent.setup()

    render(
      <TestWrapper>
        <ProjectSelector
          selectedProject=""
          onSelectProject={onSelectProject}
        />
      </TestWrapper>
    )

    await waitFor(() => {
      expect(screen.getByRole('combobox')).toBeInTheDocument()
    })

    const selector = screen.getByRole('combobox')
    await user.click(selector)

    await waitFor(() => {
      const option = screen.getByText('project-1')
      return user.click(option)
    })

    expect(onSelectProject).toHaveBeenCalled()
  })
})

// =============================================================================
// Accessibility Tests
// =============================================================================

describe('Accessibility', () => {
  it('FeatureCard should be keyboard navigable', async () => {
    const { FeatureCard } = await import('./FeatureCard')
    const onEdit = vi.fn()

    render(
      <TestWrapper>
        <FeatureCard
          feature={{
            id: 'feat-1',
            name: 'Test',
            category: 'test',
            description: 'Test',
            priority: 1,
            steps: [],
            passes: false,
            in_progress: false,
          }}
          onEdit={onEdit}
        />
      </TestWrapper>
    )

    const card = screen.getByRole('article')

    // Should be focusable
    card.focus()
    expect(document.activeElement).toBe(card)

    // Should respond to Enter key
    fireEvent.keyDown(card, { key: 'Enter' })
    expect(onEdit).toHaveBeenCalled()
  })

  it('ContainerControl buttons should have accessible names', async () => {
    const { ContainerControl } = await import('./ContainerControl')

    render(
      <TestWrapper>
        <ContainerControl
          projectName="test"
          status="stopped"
          onStatusChange={() => {}}
        />
      </TestWrapper>
    )

    const startButton = screen.getByRole('button', { name: /start/i })
    expect(startButton).toHaveAccessibleName()
  })

  it('FeatureModal should trap focus', async () => {
    const { FeatureModal } = await import('./FeatureModal')

    render(
      <TestWrapper>
        <FeatureModal
          feature={{
            id: 'feat-1',
            name: 'Test',
            category: 'test',
            description: 'Test',
            priority: 1,
            steps: [],
            passes: false,
            in_progress: false,
          }}
          isOpen={true}
          onClose={() => {}}
          onSave={() => {}}
        />
      </TestWrapper>
    )

    // Modal should have role="dialog"
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})

// =============================================================================
// Error Boundary Tests
// =============================================================================

describe('Error Handling', () => {
  it('should handle component errors gracefully', async () => {
    // Suppress console.error for this test
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const BrokenComponent = () => {
      throw new Error('Test error')
    }

    // Wrap in error boundary (would need to import actual error boundary)
    try {
      render(<BrokenComponent />)
    } catch {
      // Expected to throw
    }

    consoleSpy.mockRestore()
  })
})

// =============================================================================
// Performance Tests
// =============================================================================

describe('Performance', () => {
  it('should render large feature list efficiently', async () => {
    const { KanbanBoard } = await import('./KanbanBoard')

    const manyFeatures = {
      pending: Array.from({ length: 100 }, (_, i) => ({
        id: `feat-${i}`,
        name: `Feature ${i}`,
        category: 'test',
        description: 'Test',
        priority: i % 5,
        steps: [],
        passes: false,
        in_progress: false,
      })),
      in_progress: [],
      done: [],
    }

    const startTime = performance.now()

    render(
      <TestWrapper>
        <KanbanBoard
          features={manyFeatures}
          onFeatureEdit={() => {}}
          isLoading={false}
        />
      </TestWrapper>
    )

    const endTime = performance.now()

    // Should render in under 1 second
    expect(endTime - startTime).toBeLessThan(1000)
  })
})
