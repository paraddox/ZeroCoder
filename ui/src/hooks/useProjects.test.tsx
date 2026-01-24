/**
 * useProjects Hook Unit Tests
 * ===========================
 *
 * Tests for React Query hooks including:
 * - Query execution
 * - Mutation handling
 * - Cache invalidation
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactNode } from 'react'
import * as api from '../lib/api'

// Mock the API module
vi.mock('../lib/api', () => ({
  listProjects: vi.fn(),
  createProject: vi.fn(),
  deleteProject: vi.fn(),
  listFeatures: vi.fn(),
  createFeature: vi.fn(),
  updateFeature: vi.fn(),
  deleteFeature: vi.fn(),
  reopenFeature: vi.fn(),
  getAgentStatus: vi.fn(),
  startAgent: vi.fn(),
  stopAgent: vi.fn(),
  gracefulStopAgent: vi.fn(),
  listContainers: vi.fn(),
  updateContainerCount: vi.fn(),
  updateProjectSettings: vi.fn(),
}))

// Import hooks after mocking
import {
  useProjects,
  useCreateProject,
  useDeleteProject,
  useFeatures,
  useCreateFeature,
  useAgentStatus,
  useStartAgent,
  useStopAgent,
  useUpdateProjectSettings,
} from './useProjects'

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

describe('useProjects Hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.resetAllMocks()
  })

  describe('useProjects', () => {
    it('should fetch projects on mount', async () => {
      const mockProjects = [
        {
          name: 'test-project',
          git_url: 'https://github.com/user/repo.git',
          local_path: '/path/to/project',
          is_new: false,
          has_spec: true,
          wizard_incomplete: false,
          stats: { passing: 5, in_progress: 2, total: 10, percentage: 50 },
          target_container_count: 1,
        },
      ]

      vi.mocked(api.listProjects).mockResolvedValue(mockProjects)

      const { result } = renderHook(() => useProjects(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.listProjects).toHaveBeenCalled()
      expect(result.current.data).toEqual(mockProjects)
    })

    it('should handle error state', async () => {
      vi.mocked(api.listProjects).mockRejectedValue(new Error('Network error'))

      const { result } = renderHook(() => useProjects(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })

      expect(result.current.error?.message).toBe('Network error')
    })
  })

  describe('useCreateProject', () => {
    it('should create a project', async () => {
      const newProject = {
        name: 'new-project',
        git_url: 'https://github.com/user/repo.git',
        local_path: '/path/to/project',
        is_new: true,
        has_spec: false,
        wizard_incomplete: false,
        stats: { passing: 0, in_progress: 0, total: 0, percentage: 0 },
        target_container_count: 1,
      }

      vi.mocked(api.createProject).mockResolvedValue(newProject)

      const { result } = renderHook(() => useCreateProject(), {
        wrapper: createWrapper(),
      })

      result.current.mutate({ name: 'new-project', gitUrl: 'https://github.com/user/repo.git' })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.createProject).toHaveBeenCalledWith(
        'new-project',
        'https://github.com/user/repo.git',
        undefined  // isNew is optional, defaults in the API
      )
    })
  })

  describe('useDeleteProject', () => {
    it('should delete a project', async () => {
      vi.mocked(api.deleteProject).mockResolvedValue(undefined)

      const { result } = renderHook(() => useDeleteProject(), {
        wrapper: createWrapper(),
      })

      // The hook's mutationFn takes just the project name
      result.current.mutate('test-project')

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.deleteProject).toHaveBeenCalledWith('test-project')
    })
  })

  describe('useFeatures', () => {
    it('should fetch features for a project', async () => {
      const mockFeatures = {
        pending: [{ id: 'feat-1', name: 'Test', passes: false, in_progress: false }],
        in_progress: [],
        done: [],
      }

      vi.mocked(api.listFeatures).mockResolvedValue(mockFeatures as any)

      const { result } = renderHook(() => useFeatures('test-project'), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.listFeatures).toHaveBeenCalledWith('test-project')
      expect(result.current.data).toEqual(mockFeatures)
    })
  })

  describe('useCreateFeature', () => {
    it('should create a feature', async () => {
      const newFeature = {
        id: 'feat-1',
        priority: 1,
        category: 'auth',
        name: 'Login',
        description: 'Login feature',
        steps: [],
        passes: false,
        in_progress: false,
      }

      vi.mocked(api.createFeature).mockResolvedValue(newFeature)

      const { result } = renderHook(() => useCreateFeature('test-project'), {
        wrapper: createWrapper(),
      })

      result.current.mutate({
        category: 'auth',
        name: 'Login',
        description: 'Login feature',
        steps: [],
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.createFeature).toHaveBeenCalled()
    })
  })

  describe('useAgentStatus', () => {
    it('should fetch agent status', async () => {
      const mockStatus = {
        status: 'running',
        container_name: 'zerocoder-test-1',
        pid: 12345,
        started_at: '2024-01-01T00:00:00Z',
        idle_seconds: 0,
        yolo_mode: false,
        agent_running: true,
      }

      vi.mocked(api.getAgentStatus).mockResolvedValue(mockStatus as any)

      const { result } = renderHook(() => useAgentStatus('test-project'), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.getAgentStatus).toHaveBeenCalledWith('test-project')
      expect(result.current.data).toEqual(mockStatus)
    })
  })

  describe('useStartAgent', () => {
    it('should start agent', async () => {
      const mockResponse = {
        success: true,
        status: 'running',
        message: 'Agent started',
      }

      vi.mocked(api.startAgent).mockResolvedValue(mockResponse as any)

      const { result } = renderHook(() => useStartAgent('test-project'), {
        wrapper: createWrapper(),
      })

      // The hook's mutationFn takes yoloMode boolean directly
      result.current.mutate(false)

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.startAgent).toHaveBeenCalledWith('test-project', false)
    })
  })

  describe('useStopAgent', () => {
    it('should stop agent', async () => {
      const mockResponse = {
        success: true,
        status: 'stopped',
        message: 'Agent stopped',
      }

      vi.mocked(api.stopAgent).mockResolvedValue(mockResponse as any)

      const { result } = renderHook(() => useStopAgent('test-project'), {
        wrapper: createWrapper(),
      })

      result.current.mutate()

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.stopAgent).toHaveBeenCalledWith('test-project')
    })
  })

  describe('useUpdateProjectSettings', () => {
    it('should update project settings', async () => {
      vi.mocked(api.updateProjectSettings).mockResolvedValue({
        success: true,
        message: 'Settings updated',
        agent_model: 'claude-opus-4-5-20251101',
      })

      const { result } = renderHook(() => useUpdateProjectSettings('test-project'), {
        wrapper: createWrapper(),
      })

      result.current.mutate({ agent_model: 'claude-opus-4-5-20251101' })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.updateProjectSettings).toHaveBeenCalledWith('test-project', {
        agent_model: 'claude-opus-4-5-20251101',
      })
    })
  })
})
