/**
 * React Query hooks for container management
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listContainers, updateContainerCount, stopAllContainers, startAgent, stopAgent, gracefulStopAgent } from '../lib/api'
import type { ContainerInfo } from '../lib/types'

/**
 * Hook to fetch containers for a project
 */
export function useContainers(projectName: string | null) {
  return useQuery<ContainerInfo[]>({
    queryKey: ['containers', projectName],
    queryFn: () => listContainers(projectName!),
    enabled: !!projectName,
    refetchInterval: 5000, // Poll every 5 seconds
  })
}

/**
 * Hook to update container count
 */
export function useUpdateContainerCount(projectName: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (targetCount: number) => updateContainerCount(projectName, targetCount),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['containers', projectName] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}

/**
 * Hook to start agent/containers
 */
export function useStartAgent(projectName: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (yoloMode: boolean = false) => startAgent(projectName, yoloMode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['containers', projectName] })
      queryClient.invalidateQueries({ queryKey: ['agentStatus', projectName] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}

/**
 * Hook to stop agent immediately
 */
export function useStopAgent(projectName: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => stopAgent(projectName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['containers', projectName] })
      queryClient.invalidateQueries({ queryKey: ['agentStatus', projectName] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}

/**
 * Hook to stop agent gracefully
 */
export function useGracefulStopAgent(projectName: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => gracefulStopAgent(projectName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agentStatus', projectName] })
    },
  })
}

/**
 * Hook to stop all containers
 */
export function useStopAllContainers(projectName: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (graceful: boolean = true) => stopAllContainers(projectName, graceful),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['containers', projectName] })
      queryClient.invalidateQueries({ queryKey: ['agentStatus', projectName] })
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })
}
