/**
 * API Client Unit Tests
 * =====================
 *
 * Tests for API client functions including:
 * - HTTP method usage
 * - URL construction
 * - Error handling
 * - Request/response transformations
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
  listProjects,
  createProject,
  getProject,
  deleteProject,
  listFeatures,
  createFeature,
  getAgentStatus,
  startAgent,
  stopAgent,
  healthCheck,
  listContainers,
  updateContainerCount,
} from './api'
import type { ProjectSummary, FeatureListResponse, AgentStatusResponse } from './types'

// Mock fetch globally
const mockFetch = vi.fn()
global.fetch = mockFetch

describe('API Client', () => {
  beforeEach(() => {
    mockFetch.mockReset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  describe('Project API', () => {
    it('should list projects', async () => {
      const mockProjects: ProjectSummary[] = [
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

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockProjects),
      })

      const result = await listProjects()

      expect(mockFetch).toHaveBeenCalledWith('/api/projects', expect.any(Object))
      expect(result).toEqual(mockProjects)
    })

    it('should create a project', async () => {
      const newProject: ProjectSummary = {
        name: 'new-project',
        git_url: 'https://github.com/user/repo.git',
        local_path: '/path/to/project',
        is_new: true,
        has_spec: false,
        wizard_incomplete: false,
        stats: { passing: 0, in_progress: 0, total: 0, percentage: 0 },
        target_container_count: 1,
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(newProject),
      })

      const result = await createProject('new-project', 'https://github.com/user/repo.git')

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/projects',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            name: 'new-project',
            git_url: 'https://github.com/user/repo.git',
            is_new: true,
          }),
        })
      )
      expect(result).toEqual(newProject)
    })

    it('should get a project by name', async () => {
      const mockProject = {
        name: 'test-project',
        git_url: 'https://github.com/user/repo.git',
        local_path: '/path/to/project',
        is_new: false,
        has_spec: true,
        stats: { passing: 5, in_progress: 2, total: 10, percentage: 50 },
        prompts_dir: '/path/to/prompts',
        target_container_count: 1,
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockProject),
      })

      const result = await getProject('test-project')

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/projects/test-project',
        expect.any(Object)
      )
      expect(result).toEqual(mockProject)
    })

    it('should URL-encode project names', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({}),
      })

      await getProject('project with spaces')

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/projects/project%20with%20spaces',
        expect.any(Object)
      )
    })

    it('should delete a project', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true }),
      })

      await deleteProject('test-project')

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/projects/test-project',
        expect.objectContaining({ method: 'DELETE' })
      )
    })

    it('should delete a project with files', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true }),
      })

      await deleteProject('test-project', true)

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/projects/test-project?delete_files=true',
        expect.objectContaining({ method: 'DELETE' })
      )
    })
  })

  describe('Features API', () => {
    it('should list features', async () => {
      const mockFeatures: FeatureListResponse = {
        pending: [
          {
            id: 'feat-1',
            priority: 1,
            category: 'auth',
            name: 'Login',
            description: 'Login feature',
            steps: [],
            passes: false,
            in_progress: false,
          },
        ],
        in_progress: [],
        done: [],
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockFeatures),
      })

      const result = await listFeatures('test-project')

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/projects/test-project/features',
        expect.any(Object)
      )
      expect(result).toEqual(mockFeatures)
    })

    it('should create a feature', async () => {
      const newFeature = {
        id: 'feat-1',
        priority: 1,
        category: 'auth',
        name: 'Login',
        description: 'Login feature',
        steps: ['Step 1'],
        passes: false,
        in_progress: false,
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(newFeature),
      })

      const result = await createFeature('test-project', {
        category: 'auth',
        name: 'Login',
        description: 'Login feature',
        steps: ['Step 1'],
      })

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/projects/test-project/features',
        expect.objectContaining({ method: 'POST' })
      )
      expect(result).toEqual(newFeature)
    })
  })

  describe('Agent API', () => {
    it('should get agent status', async () => {
      const mockStatus: AgentStatusResponse = {
        status: 'running',
        container_name: 'zerocoder-test-1',
        pid: 12345,
        started_at: '2024-01-01T00:00:00Z',
        idle_seconds: 0,
        yolo_mode: false,
        agent_running: true,
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockStatus),
      })

      const result = await getAgentStatus('test-project')

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/projects/test-project/agent/status',
        expect.any(Object)
      )
      expect(result).toEqual(mockStatus)
    })

    it('should start agent', async () => {
      const mockResponse = {
        success: true,
        status: 'running',
        message: 'Agent started',
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResponse),
      })

      const result = await startAgent('test-project')

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/projects/test-project/agent/start-all',
        expect.objectContaining({ method: 'POST' })
      )
      expect(result).toEqual(mockResponse)
    })

    it('should stop agent', async () => {
      const mockResponse = {
        success: true,
        status: 'stopped',
        message: 'Agent stopped',
      }

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockResponse),
      })

      const result = await stopAgent('test-project')

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/projects/test-project/agent/stop',
        expect.objectContaining({ method: 'POST' })
      )
      expect(result).toEqual(mockResponse)
    })
  })

  describe('Container API', () => {
    it('should list containers', async () => {
      const mockContainers = [
        {
          id: 1,
          container_number: 1,
          container_type: 'coding',
          status: 'running',
          current_feature: 'feat-1',
          docker_container_id: 'abc123',
        },
      ]

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockContainers),
      })

      const result = await listContainers('test-project')

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/projects/test-project/containers',
        expect.any(Object)
      )
      expect(result).toEqual(mockContainers)
    })

    it('should update container count', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ success: true, target_count: 3 }),
      })

      const result = await updateContainerCount('test-project', 3)

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/projects/test-project/containers/count',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ target_count: 3 }),
        })
      )
      expect(result).toEqual({ success: true, target_count: 3 })
    })
  })

  describe('Health Check', () => {
    it('should return healthy status', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ status: 'healthy' }),
      })

      const result = await healthCheck()

      expect(mockFetch).toHaveBeenCalledWith('/api/health', expect.any(Object))
      expect(result).toEqual({ status: 'healthy' })
    })
  })

  describe('Error Handling', () => {
    it('should throw error on non-ok response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: () => Promise.resolve({ detail: 'Project not found' }),
      })

      await expect(getProject('nonexistent')).rejects.toThrow('Project not found')
    })

    it('should handle unknown error response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.reject(new Error('Invalid JSON')),
      })

      await expect(getProject('test')).rejects.toThrow('Unknown error')
    })

    it('should include HTTP status in error message when no detail', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve({}),
      })

      await expect(getProject('test')).rejects.toThrow('HTTP 500')
    })
  })

  describe('Request Headers', () => {
    it('should include Content-Type header', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve([]),
      })

      await listProjects()

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/projects',
        expect.objectContaining({
          headers: expect.objectContaining({
            'Content-Type': 'application/json',
          }),
        })
      )
    })
  })
})
