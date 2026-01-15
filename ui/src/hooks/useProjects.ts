/**
 * React Query hooks for project data
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '../lib/api'
import type { FeatureCreate, AgentStatusResponse, AgentModel } from '../lib/types'

// ============================================================================
// Projects
// ============================================================================

export function useProjects() {
  return useQuery({
    queryKey: ['projects'],
    queryFn: api.listProjects,
  })
}

export function useProject(name: string | null) {
  return useQuery({
    queryKey: ['project', name],
    queryFn: () => api.getProject(name!),
    enabled: !!name,
  })
}

export function useCreateProject() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ name, gitUrl, isNew }: { name: string; gitUrl: string; isNew?: boolean }) =>
      api.createProject(name, gitUrl, isNew),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}

export function useAddExistingRepo() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ name, gitUrl }: { name: string; gitUrl: string }) =>
      api.addExistingRepo({ name, git_url: gitUrl }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}

export function useDeleteProject() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (name: string) => api.deleteProject(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}

export function useProjectSettings(name: string | null) {
  return useQuery({
    queryKey: ['project-settings', name],
    queryFn: () => api.getProjectSettings(name!),
    enabled: !!name,
  })
}

export function useUpdateProjectSettings(projectName: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (settings: { agent_model: AgentModel }) =>
      api.updateProjectSettings(projectName, settings),
    onSuccess: () => {
      // Invalidate both project list and settings
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      queryClient.invalidateQueries({ queryKey: ['project-settings', projectName] })
      queryClient.invalidateQueries({ queryKey: ['project', projectName] })
    },
  })
}

// ============================================================================
// Features
// ============================================================================

export function useFeatures(projectName: string | null) {
  return useQuery({
    queryKey: ['features', projectName],
    queryFn: () => api.listFeatures(projectName!),
    enabled: !!projectName,
    refetchInterval: 5000, // Refetch every 5 seconds for real-time updates
  })
}

export function useCreateFeature(projectName: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (feature: FeatureCreate) => api.createFeature(projectName, feature),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['features', projectName] })
    },
  })
}

export function useDeleteFeature(projectName: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (featureId: string) => api.deleteFeature(projectName, featureId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['features', projectName] })
    },
  })
}

export function useSkipFeature(projectName: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (featureId: string) => api.skipFeature(projectName, featureId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['features', projectName] })
    },
  })
}

export function useUpdateFeature(projectName: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ featureId, data }: { featureId: string; data: Parameters<typeof api.updateFeature>[2] }) =>
      api.updateFeature(projectName, featureId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['features', projectName] })
    },
  })
}

export function useReopenFeature(projectName: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (featureId: string) => api.reopenFeature(projectName, featureId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['features', projectName] })
    },
  })
}

// ============================================================================
// Agent
// ============================================================================

export function useAgentStatus(projectName: string | null) {
  return useQuery({
    queryKey: ['agent-status', projectName],
    queryFn: () => api.getAgentStatus(projectName!),
    enabled: !!projectName,
    refetchInterval: 3000, // Poll every 3 seconds
  })
}

export function useStartAgent(projectName: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (yoloMode: boolean = false) => api.startAgent(projectName, yoloMode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agent-status', projectName] })
    },
  })
}

export function useStopAgent(projectName: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => api.stopAgent(projectName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agent-status', projectName] })
    },
  })
}

export function useGracefulStopAgent(projectName: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => api.gracefulStopAgent(projectName),

    // Optimistic update: immediately set graceful_stop_requested = true
    onMutate: async () => {
      // Cancel outgoing refetches to avoid overwriting optimistic update
      await queryClient.cancelQueries({ queryKey: ['agent-status', projectName] })

      // Snapshot previous value for rollback
      const previousStatus = queryClient.getQueryData<AgentStatusResponse>(['agent-status', projectName])

      // Optimistically update the cache
      queryClient.setQueryData<AgentStatusResponse>(
        ['agent-status', projectName],
        (old) => old ? { ...old, graceful_stop_requested: true } : old
      )

      // Return context with previous state
      return { previousStatus }
    },

    // Rollback on error
    onError: (_err, _variables, context) => {
      if (context?.previousStatus) {
        queryClient.setQueryData(['agent-status', projectName], context.previousStatus)
      }
    },

    // Refetch to sync with server state
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agent-status', projectName] })
    },
  })
}

export function useStartContainerOnly(projectName: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => api.startContainerOnly(projectName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agent-status', projectName] })
    },
  })
}


// ============================================================================
// Setup
// ============================================================================

export function useSetupStatus() {
  return useQuery({
    queryKey: ['setup-status'],
    queryFn: api.getSetupStatus,
    staleTime: 60000, // Cache for 1 minute
  })
}

export function useHealthCheck() {
  return useQuery({
    queryKey: ['health'],
    queryFn: api.healthCheck,
    retry: false,
  })
}

// ============================================================================
// Filesystem
// ============================================================================

export function useListDirectory(path?: string) {
  return useQuery({
    queryKey: ['filesystem', 'list', path],
    queryFn: () => api.listDirectory(path),
  })
}

export function useCreateDirectory() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (path: string) => api.createDirectory(path),
    onSuccess: (_, path) => {
      // Invalidate parent directory listing
      const parentPath = path.split('/').slice(0, -1).join('/') || undefined
      queryClient.invalidateQueries({ queryKey: ['filesystem', 'list', parentPath] })
    },
  })
}

export function useValidatePath() {
  return useMutation({
    mutationFn: (path: string) => api.validatePath(path),
  })
}
