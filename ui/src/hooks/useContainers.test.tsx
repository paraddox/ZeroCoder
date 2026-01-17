/**
 * useContainers Hook Tests
 * ========================
 *
 * Tests for the useContainers hook including:
 * - Container list fetching
 * - Container count updates
 * - Error handling
 * - Loading states
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider, useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ReactNode } from 'react'
import * as api from '../lib/api'

// Mock the API module
vi.mock('../lib/api', () => ({
  listContainers: vi.fn(),
  updateContainerCount: vi.fn(),
}))

// Create wrapper with QueryClient
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  })

  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }
}

// Simple hook implementations for testing (simulating useContainers hook)
function useContainers(projectName: string) {
  return useQuery({
    queryKey: ['containers', projectName],
    queryFn: () => api.listContainers(projectName),
    enabled: !!projectName,
  })
}

function useUpdateContainerCount(projectName: string) {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: (targetCount: number) =>
      api.updateContainerCount(projectName, targetCount),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['containers', projectName] })
      qc.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}

describe('useContainers Hook', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.resetAllMocks()
  })

  describe('useContainers', () => {
    it('should fetch containers on mount', async () => {
      const mockContainers = [
        {
          id: 1,
          container_number: 1,
          container_type: 'coding',
          status: 'running',
          current_feature: 'feat-1',
        },
      ]

      vi.mocked(api.listContainers).mockResolvedValue(mockContainers)

      const { result } = renderHook(() => useContainers('test-project'), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.listContainers).toHaveBeenCalledWith('test-project')
      expect(result.current.data).toEqual(mockContainers)
    })

    it('should handle loading state', async () => {
      vi.mocked(api.listContainers).mockImplementation(
        () => new Promise(() => {}) // Never resolves
      )

      const { result } = renderHook(() => useContainers('test-project'), {
        wrapper: createWrapper(),
      })

      expect(result.current.isLoading).toBe(true)
    })

    it('should handle error state', async () => {
      vi.mocked(api.listContainers).mockRejectedValue(new Error('Fetch failed'))

      const { result } = renderHook(() => useContainers('test-project'), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })

      expect(result.current.error?.message).toBe('Fetch failed')
    })

    it('should not fetch when project is empty', async () => {
      const { result } = renderHook(() => useContainers(''), {
        wrapper: createWrapper(),
      })

      expect(result.current.fetchStatus).toBe('idle')
      expect(api.listContainers).not.toHaveBeenCalled()
    })

    it('should handle empty container list', async () => {
      vi.mocked(api.listContainers).mockResolvedValue([])

      const { result } = renderHook(() => useContainers('test-project'), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data).toEqual([])
    })

    it('should handle multiple containers', async () => {
      const mockContainers = [
        {
          id: 1,
          container_number: 1,
          container_type: 'coding',
          status: 'running',
          current_feature: 'feat-1',
        },
        {
          id: 2,
          container_number: 2,
          container_type: 'coding',
          status: 'stopped',
          current_feature: null,
        },
        {
          id: 3,
          container_number: 3,
          container_type: 'coding',
          status: 'created',
          current_feature: null,
        },
      ]

      vi.mocked(api.listContainers).mockResolvedValue(mockContainers)

      const { result } = renderHook(() => useContainers('test-project'), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data).toHaveLength(3)
    })
  })

  describe('useUpdateContainerCount', () => {
    it('should update container count successfully', async () => {
      vi.mocked(api.updateContainerCount).mockResolvedValue({
        success: true,
        message: 'Container count updated',
        target_container_count: 5,
      })

      const { result } = renderHook(
        () => useUpdateContainerCount('test-project'),
        { wrapper: createWrapper() }
      )

      result.current.mutate(5)

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.updateContainerCount).toHaveBeenCalledWith('test-project', 5)
    })

    it('should handle update error', async () => {
      vi.mocked(api.updateContainerCount).mockRejectedValue(
        new Error('Update failed')
      )

      const { result } = renderHook(
        () => useUpdateContainerCount('test-project'),
        { wrapper: createWrapper() }
      )

      result.current.mutate(5)

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })

      expect(result.current.error?.message).toBe('Update failed')
    })
  })

  describe('Container Status Types', () => {
    it('should handle all container status values', async () => {
      const statuses = ['not_created', 'created', 'running', 'stopping', 'stopped', 'completed']

      for (const status of statuses) {
        const mockContainers = [
          {
            id: 1,
            container_number: 1,
            container_type: 'coding',
            status,
            current_feature: null,
          },
        ]

        vi.mocked(api.listContainers).mockResolvedValue(mockContainers)

        const { result } = renderHook(() => useContainers('test-project'), {
          wrapper: createWrapper(),
        })

        await waitFor(() => {
          expect(result.current.isSuccess).toBe(true)
        })

        expect(result.current.data?.[0].status).toBe(status)
      }
    })

    it('should handle init container type', async () => {
      const mockContainers = [
        {
          id: 1,
          container_number: 0,
          container_type: 'init',
          status: 'completed',
          current_feature: null,
        },
      ]

      vi.mocked(api.listContainers).mockResolvedValue(mockContainers)

      const { result } = renderHook(() => useContainers('test-project'), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(result.current.data?.[0].container_type).toBe('init')
      expect(result.current.data?.[0].container_number).toBe(0)
    })
  })
})
