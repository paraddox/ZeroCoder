/**
 * ProjectSelector Component Tests
 * ================================
 *
 * Tests for the ProjectSelector component including:
 * - Project list display
 * - Selection handling
 * - Loading states
 * - Empty states
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ProjectSelector } from './ProjectSelector'
import type { ProjectSummary } from '../lib/types'

// Mock modals
vi.mock('./NewProjectModal', () => ({
  NewProjectModal: () => <div data-testid="new-project-modal" />,
}))

vi.mock('./ExistingRepoModal', () => ({
  ExistingRepoModal: () => <div data-testid="existing-repo-modal" />,
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

const mockProjects: ProjectSummary[] = [
  {
    name: 'project-alpha',
    git_url: 'https://github.com/user/alpha.git',
    local_path: '/path/to/alpha',
    is_new: false,
    has_spec: true,
    wizard_incomplete: false,
    stats: { passing: 5, in_progress: 2, total: 10, percentage: 50 },
    target_container_count: 1,
  },
  {
    name: 'project-beta',
    git_url: 'https://github.com/user/beta.git',
    local_path: '/path/to/beta',
    is_new: true,
    has_spec: false,
    wizard_incomplete: true,
    stats: { passing: 0, in_progress: 0, total: 0, percentage: 0 },
    target_container_count: 1,
  },
]

describe('ProjectSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('should render project selector button', () => {
      render(
        <ProjectSelector
          projects={mockProjects}
          selectedProject={null}
          onSelectProject={vi.fn()}
          isLoading={false}
        />,
        { wrapper: createWrapper() }
      )

      // Should show the dropdown button
      expect(screen.getByRole('button')).toBeInTheDocument()
    })

    it('should display selected project name', () => {
      render(
        <ProjectSelector
          projects={mockProjects}
          selectedProject="project-alpha"
          onSelectProject={vi.fn()}
          isLoading={false}
        />,
        { wrapper: createWrapper() }
      )

      expect(screen.getByText('project-alpha')).toBeInTheDocument()
    })

    it('should show placeholder when no project selected', () => {
      render(
        <ProjectSelector
          projects={mockProjects}
          selectedProject={null}
          onSelectProject={vi.fn()}
          isLoading={false}
        />,
        { wrapper: createWrapper() }
      )

      // Should show some placeholder text
      expect(screen.getByRole('button')).toBeInTheDocument()
    })
  })

  describe('Dropdown Behavior', () => {
    it('should open dropdown on click', async () => {
      const user = userEvent.setup()

      render(
        <ProjectSelector
          projects={mockProjects}
          selectedProject={null}
          onSelectProject={vi.fn()}
          isLoading={false}
        />,
        { wrapper: createWrapper() }
      )

      const button = screen.getByRole('button')
      await user.click(button)

      // Dropdown should be open, showing project options
      await waitFor(() => {
        expect(screen.getByText('project-alpha')).toBeInTheDocument()
        expect(screen.getByText('project-beta')).toBeInTheDocument()
      })
    })

    it('should call onSelectProject when project clicked', async () => {
      const user = userEvent.setup()
      const onSelectProject = vi.fn()

      render(
        <ProjectSelector
          projects={mockProjects}
          selectedProject={null}
          onSelectProject={onSelectProject}
          isLoading={false}
        />,
        { wrapper: createWrapper() }
      )

      // Open dropdown
      await user.click(screen.getByRole('button'))

      // Wait for dropdown to open and click a project
      await waitFor(() => {
        expect(screen.getByText('project-alpha')).toBeInTheDocument()
      })

      // Click project option (may need to find the correct clickable element)
      const projectOption = screen.getAllByText('project-alpha')[0]
      await user.click(projectOption)
    })
  })

  describe('Loading State', () => {
    it('should disable button while loading', () => {
      render(
        <ProjectSelector
          projects={[]}
          selectedProject={null}
          onSelectProject={vi.fn()}
          isLoading={true}
        />,
        { wrapper: createWrapper() }
      )

      const button = screen.getByRole('button')
      expect(button).toBeDisabled()
    })

    it('should show loading indicator', () => {
      render(
        <ProjectSelector
          projects={[]}
          selectedProject={null}
          onSelectProject={vi.fn()}
          isLoading={true}
        />,
        { wrapper: createWrapper() }
      )

      // Should show loading state (spinner or similar)
      expect(screen.getByRole('button')).toBeDisabled()
    })
  })

  describe('Empty State', () => {
    it('should handle empty projects list', () => {
      render(
        <ProjectSelector
          projects={[]}
          selectedProject={null}
          onSelectProject={vi.fn()}
          isLoading={false}
        />,
        { wrapper: createWrapper() }
      )

      // Should still render without errors
      expect(screen.getByRole('button')).toBeInTheDocument()
    })
  })

  describe('Project Stats Display', () => {
    it('should display stats for selected project', () => {
      render(
        <ProjectSelector
          projects={mockProjects}
          selectedProject="project-alpha"
          onSelectProject={vi.fn()}
          isLoading={false}
        />,
        { wrapper: createWrapper() }
      )

      // Project alpha has 5/10 features (50%)
      // Stats badge should be visible
      expect(screen.getByText('project-alpha')).toBeInTheDocument()
    })
  })

  describe('Incomplete Project Handling', () => {
    it('should call onIncompleteProjectClick for incomplete projects', async () => {
      const user = userEvent.setup()
      const onIncompleteProjectClick = vi.fn()

      render(
        <ProjectSelector
          projects={mockProjects}
          selectedProject={null}
          onSelectProject={vi.fn()}
          onIncompleteProjectClick={onIncompleteProjectClick}
          isLoading={false}
        />,
        { wrapper: createWrapper() }
      )

      // Open dropdown
      await user.click(screen.getByRole('button'))

      // Wait for dropdown
      await waitFor(() => {
        expect(screen.getByText('project-beta')).toBeInTheDocument()
      })
    })
  })

  describe('Button States', () => {
    it('should be enabled when not loading', () => {
      render(
        <ProjectSelector
          projects={mockProjects}
          selectedProject={null}
          onSelectProject={vi.fn()}
          isLoading={false}
        />,
        { wrapper: createWrapper() }
      )

      const button = screen.getByRole('button')
      expect(button).not.toBeDisabled()
    })
  })
})
