/**
 * Test Utilities
 * ==============
 *
 * Custom render functions and test utilities for React Testing Library.
 */

import React, { ReactElement, ReactNode } from 'react'
import { render, RenderOptions, RenderResult } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// Create a fresh QueryClient for each test
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: Infinity,
      },
      mutations: {
        retry: false,
      },
    },
  })
}

// Test wrapper with all providers
interface WrapperProps {
  children: ReactNode
}

function AllTheProviders({ children }: WrapperProps) {
  const queryClient = createTestQueryClient()
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  )
}

// Custom render function with providers
function customRender(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
): RenderResult {
  return render(ui, { wrapper: AllTheProviders, ...options })
}

// Re-export everything
export * from '@testing-library/react'
export { customRender as render }

// Helper to create mock project data
export function createMockProject(overrides = {}) {
  return {
    name: 'test-project',
    git_url: 'https://github.com/user/repo.git',
    local_path: '/path/to/project',
    is_new: false,
    has_spec: true,
    wizard_incomplete: false,
    stats: {
      passing: 5,
      in_progress: 2,
      total: 10,
      percentage: 50,
    },
    target_container_count: 1,
    agent_status: 'stopped',
    agent_running: false,
    ...overrides,
  }
}

// Helper to create mock feature data
export function createMockFeature(overrides = {}) {
  return {
    id: 'feat-1',
    priority: 1,
    category: 'auth',
    name: 'User Authentication',
    description: 'Implement user login',
    steps: ['Create form', 'Add validation'],
    passes: false,
    in_progress: false,
    ...overrides,
  }
}

// Helper to create mock container data
export function createMockContainer(overrides = {}) {
  return {
    id: 1,
    container_number: 1,
    container_type: 'coding' as const,
    status: 'running' as const,
    current_feature: 'feat-1',
    ...overrides,
  }
}

// Helper to wait for all pending promises
export async function flushPromises() {
  await new Promise((resolve) => setTimeout(resolve, 0))
}
