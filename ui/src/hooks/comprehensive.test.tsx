/**
 * Comprehensive Hook Tests
 * ========================
 *
 * Enterprise-grade tests for all React hooks including:
 * - Query hooks (data fetching)
 * - Mutation hooks (data modification)
 * - WebSocket hooks
 * - State management hooks
 * - Side effect hooks
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
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
  skipFeature: vi.fn(),
  getAgentStatus: vi.fn(),
  startAgent: vi.fn(),
  stopAgent: vi.fn(),
  gracefulStopAgent: vi.fn(),
  listContainers: vi.fn(),
  updateContainerCount: vi.fn(),
  updateProjectSettings: vi.fn(),
  getProjectSettings: vi.fn(),
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

// =============================================================================
// useProjects Hook Tests
// =============================================================================

import {
  useProjects,
  useProject,
  useCreateProject,
  useDeleteProject,
  useFeatures,
  useCreateFeature,
  useUpdateFeature,
  useDeleteFeature,
  useReopenFeature,
  useAgentStatus,
  useStartAgent,
  useStopAgent,
  useGracefulStopAgent,
  useUpdateProjectSettings,
  useSkipFeature,
} from './useProjects'

describe('useProjects Hook', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.resetAllMocks()
  })

  describe('Query Hooks', () => {
    it('should fetch projects list', async () => {
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

    it('should handle projects fetch error', async () => {
      const error = new Error('Network error')
      vi.mocked(api.listProjects).mockRejectedValue(error)

      const { result } = renderHook(() => useProjects(), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })

      expect(result.current.error?.message).toBe('Network error')
    })

    it('should fetch single project features', async () => {
      const mockFeatures = {
        pending: [
          {
            id: 'feat-1',
            priority: 1,
            category: 'auth',
            name: 'Login',
            description: 'User login',
            steps: [],
            passes: false,
            in_progress: false,
          },
        ],
        in_progress: [],
        done: [],
      }

      vi.mocked(api.listFeatures).mockResolvedValue(mockFeatures)

      const { result } = renderHook(() => useFeatures('test-project'), {
        wrapper: createWrapper(),
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.listFeatures).toHaveBeenCalledWith('test-project')
      expect(result.current.data).toEqual(mockFeatures)
    })

    it('should fetch agent status', async () => {
      const mockStatus = {
        status: 'running',
        container_name: 'zerocoder-test-1',
        pid: 12345,
        started_at: '2024-01-01T00:00:00Z',
        idle_seconds: 30,
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
      expect(result.current.data?.status).toBe('running')
    })
  })

  describe('Mutation Hooks', () => {
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

      act(() => {
        result.current.mutate({
          name: 'new-project',
          gitUrl: 'https://github.com/user/repo.git',
        })
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.createProject).toHaveBeenCalledWith(
        'new-project',
        'https://github.com/user/repo.git',
        undefined
      )
    })

    it('should delete a project', async () => {
      vi.mocked(api.deleteProject).mockResolvedValue(undefined)

      const { result } = renderHook(() => useDeleteProject(), {
        wrapper: createWrapper(),
      })

      act(() => {
        result.current.mutate('test-project')
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.deleteProject).toHaveBeenCalledWith('test-project')
    })

    it('should create a feature', async () => {
      const newFeature = {
        id: 'feat-1',
        priority: 1,
        category: 'auth',
        name: 'Login',
        description: 'User login',
        steps: ['Step 1'],
        passes: false,
        in_progress: false,
      }

      vi.mocked(api.createFeature).mockResolvedValue(newFeature)

      const { result } = renderHook(() => useCreateFeature('test-project'), {
        wrapper: createWrapper(),
      })

      act(() => {
        result.current.mutate({
          category: 'auth',
          name: 'Login',
          description: 'User login',
          steps: ['Step 1'],
        })
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.createFeature).toHaveBeenCalled()
    })

    it('should update a feature', async () => {
      const updatedFeature = {
        id: 'feat-1',
        priority: 2,
        category: 'auth',
        name: 'Updated Login',
        description: 'Updated description',
        steps: [],
        passes: false,
        in_progress: false,
      }

      vi.mocked(api.updateFeature).mockResolvedValue(updatedFeature)

      const { result } = renderHook(() => useUpdateFeature('test-project'), {
        wrapper: createWrapper(),
      })

      act(() => {
        result.current.mutate({
          featureId: 'feat-1',
          update: { name: 'Updated Login' },
        })
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.updateFeature).toHaveBeenCalled()
    })

    it('should delete a feature', async () => {
      vi.mocked(api.deleteFeature).mockResolvedValue(undefined)

      const { result } = renderHook(() => useDeleteFeature('test-project'), {
        wrapper: createWrapper(),
      })

      act(() => {
        result.current.mutate('feat-1')
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.deleteFeature).toHaveBeenCalledWith('test-project', 'feat-1')
    })

    it('should reopen a feature', async () => {
      vi.mocked(api.reopenFeature).mockResolvedValue(undefined)

      const { result } = renderHook(() => useReopenFeature('test-project'), {
        wrapper: createWrapper(),
      })

      act(() => {
        result.current.mutate('feat-1')
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.reopenFeature).toHaveBeenCalledWith('test-project', 'feat-1')
    })

    it('should skip a feature', async () => {
      vi.mocked(api.skipFeature).mockResolvedValue(undefined)

      const { result } = renderHook(() => useSkipFeature('test-project'), {
        wrapper: createWrapper(),
      })

      act(() => {
        result.current.mutate('feat-1')
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.skipFeature).toHaveBeenCalledWith('test-project', 'feat-1')
    })

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

      act(() => {
        result.current.mutate(false)
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.startAgent).toHaveBeenCalledWith('test-project', false)
    })

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

      act(() => {
        result.current.mutate()
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.stopAgent).toHaveBeenCalledWith('test-project')
    })

    it('should graceful stop agent', async () => {
      const mockResponse = {
        success: true,
        status: 'stopping',
        message: 'Graceful stop initiated',
      }

      vi.mocked(api.gracefulStopAgent).mockResolvedValue(mockResponse as any)

      const { result } = renderHook(() => useGracefulStopAgent('test-project'), {
        wrapper: createWrapper(),
      })

      act(() => {
        result.current.mutate()
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.gracefulStopAgent).toHaveBeenCalledWith('test-project')
    })

    it('should update project settings', async () => {
      vi.mocked(api.updateProjectSettings).mockResolvedValue({
        success: true,
        message: 'Settings updated',
        agent_model: 'claude-opus-4-5-20251101',
      })

      const { result } = renderHook(() => useUpdateProjectSettings('test-project'), {
        wrapper: createWrapper(),
      })

      act(() => {
        result.current.mutate({ agent_model: 'claude-opus-4-5-20251101' })
      })

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true)
      })

      expect(api.updateProjectSettings).toHaveBeenCalledWith('test-project', {
        agent_model: 'claude-opus-4-5-20251101',
      })
    })
  })

  describe('Error Handling', () => {
    it('should handle create project error', async () => {
      const error = new Error('Failed to create project')
      vi.mocked(api.createProject).mockRejectedValue(error)

      const { result } = renderHook(() => useCreateProject(), {
        wrapper: createWrapper(),
      })

      act(() => {
        result.current.mutate({
          name: 'test',
          gitUrl: 'https://github.com/user/repo.git',
        })
      })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })

      expect(result.current.error?.message).toBe('Failed to create project')
    })

    it('should handle start agent error', async () => {
      const error = new Error('Container not found')
      vi.mocked(api.startAgent).mockRejectedValue(error)

      const { result } = renderHook(() => useStartAgent('test-project'), {
        wrapper: createWrapper(),
      })

      act(() => {
        result.current.mutate(false)
      })

      await waitFor(() => {
        expect(result.current.isError).toBe(true)
      })

      expect(result.current.error?.message).toBe('Container not found')
    })
  })
})

// =============================================================================
// useContainers Hook Tests
// =============================================================================

import { useContainers, useUpdateContainerCount } from './useContainers'

describe('useContainers Hook', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should fetch container list', async () => {
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
    ]

    vi.mocked(api.listContainers).mockResolvedValue(mockContainers as any)

    const { result } = renderHook(() => useContainers('test-project'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(api.listContainers).toHaveBeenCalledWith('test-project')
    expect(result.current.data).toEqual(mockContainers)
  })

  it('should update container count', async () => {
    vi.mocked(api.updateContainerCount).mockResolvedValue({ success: true })

    const { result } = renderHook(() => useUpdateContainerCount('test-project'), {
      wrapper: createWrapper(),
    })

    act(() => {
      result.current.mutate(5)
    })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(api.updateContainerCount).toHaveBeenCalledWith('test-project', 5)
  })
})

// =============================================================================
// useWebSocket Hook Tests
// =============================================================================

import { useProjectWebSocket } from './useWebSocket'

describe('useWebSocket Hook', () => {
  let mockWebSocket: any

  beforeEach(() => {
    vi.clearAllMocks()
    mockWebSocket = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: 1, // OPEN
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }

    // @ts-ignore - Mock WebSocket constructor
    global.WebSocket = vi.fn(() => mockWebSocket)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('should connect to WebSocket', async () => {
    const { result } = renderHook(() => useProjectWebSocket('test-project'), {
      wrapper: createWrapper(),
    })

    // Simulate open event
    const openHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'open'
    )?.[1]
    if (openHandler) openHandler()

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })
  })

  it('should handle WebSocket messages', async () => {
    const { result } = renderHook(() => useProjectWebSocket('test-project'), {
      wrapper: createWrapper(),
    })

    // Simulate open event
    const openHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'open'
    )?.[1]
    if (openHandler) openHandler()

    // Simulate message event
    const messageHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'message'
    )?.[1]
    if (messageHandler) {
      messageHandler({
        data: JSON.stringify({ type: 'progress', passing: 5, total: 10 }),
      })
    }

    await waitFor(() => {
      expect(result.current.wsState.stats.passing).toBe(5)
    })
  })

  it('should handle WebSocket close', async () => {
    const { result } = renderHook(() => useProjectWebSocket('test-project'), {
      wrapper: createWrapper(),
    })

    // Simulate open event
    const openHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'open'
    )?.[1]
    if (openHandler) openHandler()

    // Simulate close event
    const closeHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'close'
    )?.[1]
    if (closeHandler) closeHandler()

    await waitFor(() => {
      expect(result.current.isConnected).toBe(false)
    })
  })

  it('should handle agent_status message', async () => {
    const { result } = renderHook(() => useProjectWebSocket('test-project'), {
      wrapper: createWrapper(),
    })

    // Simulate open event
    const openHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'open'
    )?.[1]
    if (openHandler) openHandler()

    // Simulate agent_status message
    const messageHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'message'
    )?.[1]
    if (messageHandler) {
      messageHandler({
        data: JSON.stringify({ type: 'agent_status', status: 'running' }),
      })
    }

    await waitFor(() => {
      expect(result.current.wsState.agentStatus).toBe('running')
    })
  })

  it('should handle log message', async () => {
    const { result } = renderHook(() => useProjectWebSocket('test-project'), {
      wrapper: createWrapper(),
    })

    // Simulate open event
    const openHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'open'
    )?.[1]
    if (openHandler) openHandler()

    // Simulate log message
    const messageHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'message'
    )?.[1]
    if (messageHandler) {
      messageHandler({
        data: JSON.stringify({
          type: 'log',
          line: 'Processing feature...',
          timestamp: new Date().toISOString(),
        }),
      })
    }

    await waitFor(() => {
      expect(result.current.wsState.logs.length).toBe(1)
    })
  })
})

// =============================================================================
// useTheme Hook Tests
// =============================================================================

import { useTheme, ThemeProvider } from './useTheme'

describe('useTheme Hook', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
  })

  it('should return default theme', () => {
    const { result } = renderHook(() => useTheme(), {
      wrapper: ({ children }) => <ThemeProvider>{children}</ThemeProvider>,
    })

    expect(result.current.theme).toBe('light')
  })

  it('should toggle theme', () => {
    const { result } = renderHook(() => useTheme(), {
      wrapper: ({ children }) => <ThemeProvider>{children}</ThemeProvider>,
    })

    act(() => {
      result.current.toggleTheme()
    })

    expect(result.current.theme).toBe('dark')
  })

  it('should persist theme to localStorage', () => {
    const { result } = renderHook(() => useTheme(), {
      wrapper: ({ children }) => <ThemeProvider>{children}</ThemeProvider>,
    })

    act(() => {
      result.current.toggleTheme()
    })

    expect(localStorage.getItem('theme')).toBe('dark')
  })

  it('should load theme from localStorage', () => {
    localStorage.setItem('theme', 'dark')

    const { result } = renderHook(() => useTheme(), {
      wrapper: ({ children }) => <ThemeProvider>{children}</ThemeProvider>,
    })

    expect(result.current.theme).toBe('dark')
  })
})

// =============================================================================
// useCelebration Hook Tests
// =============================================================================

import { useCelebration } from './useCelebration'

describe('useCelebration Hook', () => {
  it('should not trigger on mount', () => {
    const { result } = renderHook(() =>
      useCelebration({ passing: 0, total: 0, percentage: 0, in_progress: 0 })
    )

    expect(result.current.showCelebration).toBe(false)
  })

  it('should trigger when all features complete', async () => {
    const { result, rerender } = renderHook(
      ({ stats }) => useCelebration(stats),
      {
        initialProps: {
          stats: { passing: 5, total: 10, percentage: 50, in_progress: 0 },
        },
      }
    )

    // Update to 100%
    rerender({
      stats: { passing: 10, total: 10, percentage: 100, in_progress: 0 },
    })

    await waitFor(() => {
      expect(result.current.showCelebration).toBe(true)
    })
  })

  it('should reset celebration state', async () => {
    const { result, rerender } = renderHook(
      ({ stats }) => useCelebration(stats),
      {
        initialProps: {
          stats: { passing: 5, total: 10, percentage: 50, in_progress: 0 },
        },
      }
    )

    // Trigger celebration
    rerender({
      stats: { passing: 10, total: 10, percentage: 100, in_progress: 0 },
    })

    await waitFor(() => {
      expect(result.current.showCelebration).toBe(true)
    })

    // Reset
    act(() => {
      result.current.hideCelebration()
    })

    expect(result.current.showCelebration).toBe(false)
  })
})

// =============================================================================
// useSpecChat Hook Tests
// =============================================================================

import { useSpecChat } from './useSpecChat'

describe('useSpecChat Hook', () => {
  let mockWebSocket: any

  beforeEach(() => {
    vi.clearAllMocks()
    mockWebSocket = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: 1,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }

    // @ts-ignore
    global.WebSocket = vi.fn(() => mockWebSocket)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('should connect to spec chat WebSocket', async () => {
    const { result } = renderHook(() => useSpecChat('test-project'))

    // Simulate open event
    const openHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'open'
    )?.[1]
    if (openHandler) openHandler()

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })
  })

  it('should send message', async () => {
    const { result } = renderHook(() => useSpecChat('test-project'))

    // Simulate open event
    const openHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'open'
    )?.[1]
    if (openHandler) openHandler()

    act(() => {
      result.current.sendMessage('Hello')
    })

    expect(mockWebSocket.send).toHaveBeenCalled()
  })

  it('should handle incoming messages', async () => {
    const { result } = renderHook(() => useSpecChat('test-project'))

    // Simulate open event
    const openHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'open'
    )?.[1]
    if (openHandler) openHandler()

    // Simulate message event
    const messageHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'message'
    )?.[1]
    if (messageHandler) {
      messageHandler({
        data: JSON.stringify({
          type: 'text',
          content: 'Response from Claude',
        }),
      })
    }

    await waitFor(() => {
      expect(result.current.messages.length).toBeGreaterThan(0)
    })
  })
})

// =============================================================================
// useAssistantChat Hook Tests
// =============================================================================

import { useAssistantChat } from './useAssistantChat'

describe('useAssistantChat Hook', () => {
  let mockWebSocket: any

  beforeEach(() => {
    vi.clearAllMocks()
    mockWebSocket = {
      send: vi.fn(),
      close: vi.fn(),
      readyState: 1,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }

    // @ts-ignore
    global.WebSocket = vi.fn(() => mockWebSocket)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('should connect to assistant WebSocket', async () => {
    const { result } = renderHook(() =>
      useAssistantChat('test-project', 'conv-1')
    )

    // Simulate open event
    const openHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'open'
    )?.[1]
    if (openHandler) openHandler()

    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
    })
  })

  it('should send message to assistant', async () => {
    const { result } = renderHook(() =>
      useAssistantChat('test-project', 'conv-1')
    )

    // Simulate open event
    const openHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'open'
    )?.[1]
    if (openHandler) openHandler()

    act(() => {
      result.current.sendMessage('Help me with this feature')
    })

    expect(mockWebSocket.send).toHaveBeenCalled()
  })

  it('should handle tool_call message', async () => {
    const { result } = renderHook(() =>
      useAssistantChat('test-project', 'conv-1')
    )

    // Simulate open event
    const openHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'open'
    )?.[1]
    if (openHandler) openHandler()

    // Simulate tool_call message
    const messageHandler = mockWebSocket.addEventListener.mock.calls.find(
      ([event]: [string, Function]) => event === 'message'
    )?.[1]
    if (messageHandler) {
      messageHandler({
        data: JSON.stringify({
          type: 'tool_call',
          tool_name: 'create_feature',
          arguments: { name: 'New Feature' },
        }),
      })
    }

    await waitFor(() => {
      expect(result.current.messages.length).toBeGreaterThan(0)
    })
  })
})

// =============================================================================
// Edge Cases and Error Handling
// =============================================================================

describe('Hook Edge Cases', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should handle empty project list', async () => {
    vi.mocked(api.listProjects).mockResolvedValue([])

    const { result } = renderHook(() => useProjects(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data).toEqual([])
  })

  it('should handle empty features', async () => {
    vi.mocked(api.listFeatures).mockResolvedValue({
      pending: [],
      in_progress: [],
      done: [],
    })

    const { result } = renderHook(() => useFeatures('test-project'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true)
    })

    expect(result.current.data?.pending.length).toBe(0)
  })

  it('should handle container list error', async () => {
    const error = new Error('Failed to fetch containers')
    vi.mocked(api.listContainers).mockRejectedValue(error)

    const { result } = renderHook(() => useContainers('test-project'), {
      wrapper: createWrapper(),
    })

    await waitFor(() => {
      expect(result.current.isError).toBe(true)
    })

    expect(result.current.error?.message).toBe('Failed to fetch containers')
  })

  it('should handle mutation failure gracefully', async () => {
    const error = new Error('Delete failed')
    vi.mocked(api.deleteFeature).mockRejectedValue(error)

    const { result } = renderHook(() => useDeleteFeature('test-project'), {
      wrapper: createWrapper(),
    })

    act(() => {
      result.current.mutate('feat-1')
    })

    await waitFor(() => {
      expect(result.current.isError).toBe(true)
    })

    expect(result.current.error?.message).toBe('Delete failed')
  })
})
