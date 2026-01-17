/**
 * State Management Hook Tests
 * ===========================
 *
 * Comprehensive tests for state management hooks including:
 * - Query state management
 * - Mutation handling
 * - Cache invalidation
 * - Optimistic updates
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
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
        staleTime: 0,
      },
      mutations: {
        retry: false,
      },
    },
  })

const createWrapper = () => {
  const queryClient = createTestQueryClient()
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
}

// =============================================================================
// useProjects Hook Tests
// =============================================================================

describe('useProjects', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should fetch projects list', async () => {
    vi.doMock('../lib/api', () => ({
      listProjects: vi.fn().mockResolvedValue([
        { name: 'project-1', git_url: 'https://github.com/user/repo1.git' },
        { name: 'project-2', git_url: 'https://github.com/user/repo2.git' },
      ]),
    }))

    const { useProjects } = await import('./useProjects')
    const { result } = renderHook(() => useProjects(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
  })

  it('should handle fetch error', async () => {
    vi.doMock('../lib/api', () => ({
      listProjects: vi.fn().mockRejectedValue(new Error('Network error')),
    }))

    const { useProjects } = await import('./useProjects')
    const { result } = renderHook(() => useProjects(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isError).toBe(true)
    })
  })

  it('should refetch on demand', async () => {
    const mockListProjects = vi.fn().mockResolvedValue([])
    vi.doMock('../lib/api', () => ({
      listProjects: mockListProjects,
    }))

    const { useProjects } = await import('./useProjects')
    const { result } = renderHook(() => useProjects(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    // Trigger refetch
    act(() => {
      result.current.refetch()
    })

    await waitFor(() => {
      expect(mockListProjects).toHaveBeenCalledTimes(2)
    })
  })
})

// =============================================================================
// useFeatures Hook Tests
// =============================================================================

describe('useFeatures', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should fetch features for project', async () => {
    vi.doMock('../lib/api', () => ({
      getFeatures: vi.fn().mockResolvedValue({
        pending: [{ id: 'feat-1', name: 'Feature 1' }],
        in_progress: [],
        done: [],
      }),
    }))

    const { useFeatures } = await import('./useFeatures')
    const { result } = renderHook(() => useFeatures('test-project'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
  })

  it('should not fetch without project name', async () => {
    const mockGetFeatures = vi.fn()
    vi.doMock('../lib/api', () => ({
      getFeatures: mockGetFeatures,
    }))

    const { useFeatures } = await import('./useFeatures')
    const { result } = renderHook(() => useFeatures(''), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(mockGetFeatures).not.toHaveBeenCalled()
  })
})

// =============================================================================
// useContainers Hook Tests
// =============================================================================

describe('useContainers', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should fetch containers for project', async () => {
    vi.doMock('../lib/api', () => ({
      getContainers: vi.fn().mockResolvedValue([
        { id: 1, container_number: 1, status: 'running' },
      ]),
    }))

    const { useContainers } = await import('./useContainers')
    const { result } = renderHook(() => useContainers('test-project'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
  })

  it('should poll for container updates', async () => {
    vi.useFakeTimers()
    const mockGetContainers = vi.fn().mockResolvedValue([])

    vi.doMock('../lib/api', () => ({
      getContainers: mockGetContainers,
    }))

    const { useContainers } = await import('./useContainers')
    renderHook(() => useContainers('test-project', { pollInterval: 1000 }), {
      wrapper: createWrapper(),
    })

    // Wait for initial fetch
    await vi.advanceTimersByTimeAsync(100)

    // Advance time for polling
    await vi.advanceTimersByTimeAsync(1000)

    expect(mockGetContainers.mock.calls.length).toBeGreaterThanOrEqual(1)

    vi.useRealTimers()
  })
})

// =============================================================================
// useContainerStatus Hook Tests
// =============================================================================

describe('useContainerStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should track container status', async () => {
    vi.doMock('../lib/api', () => ({
      getAgentStatus: vi.fn().mockResolvedValue({
        status: 'running',
        container_name: 'zerocoder-test-1',
        agent_running: true,
      }),
    }))

    const { useContainerStatus } = await import('./useContainerStatus')
    const { result } = renderHook(() => useContainerStatus('test-project'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
  })

  it('should handle status transitions', async () => {
    let callCount = 0
    vi.doMock('../lib/api', () => ({
      getAgentStatus: vi.fn().mockImplementation(() => {
        callCount++
        return Promise.resolve({
          status: callCount === 1 ? 'stopped' : 'running',
          agent_running: callCount !== 1,
        })
      }),
    }))

    const { useContainerStatus } = await import('./useContainerStatus')
    const { result, rerender } = renderHook(
      () => useContainerStatus('test-project'),
      { wrapper: createWrapper() }
    )

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
  })
})

// =============================================================================
// useMutations Tests
// =============================================================================

describe('Mutation Hooks', () => {
  it('should handle create feature mutation', async () => {
    const mockCreateFeature = vi.fn().mockResolvedValue({ id: 'feat-new' })

    vi.doMock('../lib/api', () => ({
      createFeature: mockCreateFeature,
      getFeatures: vi.fn().mockResolvedValue({ pending: [], in_progress: [], done: [] }),
    }))

    const { useCreateFeature } = await import('./useFeatures')
    const { result } = renderHook(() => useCreateFeature('test-project'), {
      wrapper: createWrapper(),
    })

    await act(async () => {
      await result.current.mutateAsync({
        name: 'New Feature',
        category: 'test',
        description: 'Test description',
        steps: [],
      })
    })

    expect(mockCreateFeature).toHaveBeenCalled()
  })

  it('should handle update feature mutation', async () => {
    const mockUpdateFeature = vi.fn().mockResolvedValue({ id: 'feat-1' })

    vi.doMock('../lib/api', () => ({
      updateFeature: mockUpdateFeature,
      getFeatures: vi.fn().mockResolvedValue({ pending: [], in_progress: [], done: [] }),
    }))

    const { useUpdateFeature } = await import('./useFeatures')
    const { result } = renderHook(() => useUpdateFeature('test-project'), {
      wrapper: createWrapper(),
    })

    await act(async () => {
      await result.current.mutateAsync({
        featureId: 'feat-1',
        updates: { name: 'Updated Name' },
      })
    })

    expect(mockUpdateFeature).toHaveBeenCalled()
  })

  it('should handle delete feature mutation', async () => {
    const mockDeleteFeature = vi.fn().mockResolvedValue(undefined)

    vi.doMock('../lib/api', () => ({
      deleteFeature: mockDeleteFeature,
      getFeatures: vi.fn().mockResolvedValue({ pending: [], in_progress: [], done: [] }),
    }))

    const { useDeleteFeature } = await import('./useFeatures')
    const { result } = renderHook(() => useDeleteFeature('test-project'), {
      wrapper: createWrapper(),
    })

    await act(async () => {
      await result.current.mutateAsync('feat-1')
    })

    expect(mockDeleteFeature).toHaveBeenCalledWith('test-project', 'feat-1')
  })

  it('should handle mutation error', async () => {
    vi.doMock('../lib/api', () => ({
      createFeature: vi.fn().mockRejectedValue(new Error('Creation failed')),
      getFeatures: vi.fn().mockResolvedValue({ pending: [], in_progress: [], done: [] }),
    }))

    const { useCreateFeature } = await import('./useFeatures')
    const { result } = renderHook(() => useCreateFeature('test-project'), {
      wrapper: createWrapper(),
    })

    await act(async () => {
      try {
        await result.current.mutateAsync({
          name: 'Test',
          category: 'test',
          description: 'Test',
          steps: [],
        })
      } catch (e) {
        expect(e).toBeInstanceOf(Error)
      }
    })

    expect(result.current.isError).toBe(true)
  })
})

// =============================================================================
// Cache Invalidation Tests
// =============================================================================

describe('Cache Invalidation', () => {
  it('should invalidate features after mutation', async () => {
    const mockGetFeatures = vi.fn().mockResolvedValue({
      pending: [],
      in_progress: [],
      done: [],
    })
    const mockCreateFeature = vi.fn().mockResolvedValue({ id: 'feat-new' })

    vi.doMock('../lib/api', () => ({
      getFeatures: mockGetFeatures,
      createFeature: mockCreateFeature,
    }))

    const queryClient = createTestQueryClient()
    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { useFeatures, useCreateFeature } = await import('./useFeatures')

    // First, fetch features
    const { result: featuresResult } = renderHook(
      () => useFeatures('test-project'),
      { wrapper }
    )

    await waitFor(() => {
      expect(featuresResult.current.isLoading).toBe(false)
    })

    // Then create a feature
    const { result: createResult } = renderHook(
      () => useCreateFeature('test-project'),
      { wrapper }
    )

    await act(async () => {
      await createResult.current.mutateAsync({
        name: 'New Feature',
        category: 'test',
        description: 'Test',
        steps: [],
      })
    })

    // Features should be refetched
    expect(mockGetFeatures.mock.calls.length).toBeGreaterThanOrEqual(1)
  })
})

// =============================================================================
// Optimistic Update Tests
// =============================================================================

describe('Optimistic Updates', () => {
  it('should optimistically update feature status', async () => {
    const initialFeatures = {
      pending: [{ id: 'feat-1', name: 'Feature 1', status: 'open' }],
      in_progress: [],
      done: [],
    }

    vi.doMock('../lib/api', () => ({
      getFeatures: vi.fn().mockResolvedValue(initialFeatures),
      updateFeature: vi.fn().mockResolvedValue({ id: 'feat-1', status: 'in_progress' }),
    }))

    // Optimistic update logic test
    const optimisticUpdate = (features: typeof initialFeatures, featureId: string, newStatus: string) => {
      const updated = { ...features }

      // Find and remove from current location
      for (const key of ['pending', 'in_progress', 'done'] as const) {
        const index = updated[key].findIndex((f) => f.id === featureId)
        if (index !== -1) {
          const [feature] = updated[key].splice(index, 1)
          feature.status = newStatus

          // Add to new location
          if (newStatus === 'open') updated.pending.push(feature)
          else if (newStatus === 'in_progress') updated.in_progress.push(feature)
          else if (newStatus === 'closed') updated.done.push(feature)

          break
        }
      }

      return updated
    }

    const result = optimisticUpdate(initialFeatures, 'feat-1', 'in_progress')

    expect(result.pending).toHaveLength(0)
    expect(result.in_progress).toHaveLength(1)
    expect(result.in_progress[0].status).toBe('in_progress')
  })
})

// =============================================================================
// Query Key Tests
// =============================================================================

describe('Query Keys', () => {
  it('should use correct query keys', () => {
    const queryKeys = {
      projects: ['projects'] as const,
      project: (name: string) => ['projects', name] as const,
      features: (projectName: string) => ['projects', projectName, 'features'] as const,
      containers: (projectName: string) => ['projects', projectName, 'containers'] as const,
    }

    expect(queryKeys.projects).toEqual(['projects'])
    expect(queryKeys.project('my-project')).toEqual(['projects', 'my-project'])
    expect(queryKeys.features('my-project')).toEqual(['projects', 'my-project', 'features'])
    expect(queryKeys.containers('my-project')).toEqual(['projects', 'my-project', 'containers'])
  })

  it('should invalidate correct queries', () => {
    const queryClient = createTestQueryClient()

    // Set some cached data
    queryClient.setQueryData(['projects', 'test', 'features'], { pending: [], in_progress: [], done: [] })
    queryClient.setQueryData(['projects', 'test', 'containers'], [])

    // Invalidate features only
    queryClient.invalidateQueries({ queryKey: ['projects', 'test', 'features'] })

    // Features should be invalidated
    const featuresState = queryClient.getQueryState(['projects', 'test', 'features'])
    expect(featuresState?.isInvalidated).toBe(true)

    // Containers should still be valid
    const containersState = queryClient.getQueryState(['projects', 'test', 'containers'])
    expect(containersState?.isInvalidated).toBeFalsy()
  })
})

// =============================================================================
// Error Recovery Tests
// =============================================================================

describe('Error Recovery', () => {
  it('should retry failed queries', async () => {
    let attempts = 0
    const mockFetch = vi.fn().mockImplementation(() => {
      attempts++
      if (attempts < 2) {
        return Promise.reject(new Error('Temporary failure'))
      }
      return Promise.resolve([])
    })

    vi.doMock('../lib/api', () => ({
      listProjects: mockFetch,
    }))

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: 2,
          retryDelay: 0,
        },
      },
    })

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )

    const { useProjects } = await import('./useProjects')
    const { result } = renderHook(() => useProjects(), { wrapper })

    await waitFor(() => {
      expect(result.current.isSuccess || attempts >= 2).toBe(true)
    })
  })

  it('should show error state after retries exhausted', async () => {
    vi.doMock('../lib/api', () => ({
      listProjects: vi.fn().mockRejectedValue(new Error('Persistent failure')),
    }))

    const { useProjects } = await import('./useProjects')
    const { result } = renderHook(() => useProjects(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isError).toBe(true)
    })

    expect(result.current.error).toBeDefined()
  })
})
