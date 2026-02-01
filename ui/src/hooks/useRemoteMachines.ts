import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listRemoteMachines,
  addRemoteMachine,
  removeRemoteMachine,
  testRemoteMachine,
  startRemoteAgent,
  stopRemoteAgent,
  gracefulStopRemoteAgent,
  getRemoteAgentStatus,
} from '../lib/api'
import type { RemoteMachineCreate } from '@zerocoder/shared'

export function useRemoteMachines() {
  return useQuery({
    queryKey: ['remote-machines'],
    queryFn: listRemoteMachines,
    refetchInterval: 30000,
  })
}

export function useAddRemoteMachine() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (machine: RemoteMachineCreate) => addRemoteMachine(machine),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['remote-machines'] })
    },
  })
}

export function useRemoveRemoteMachine() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (machineId: number) => removeRemoteMachine(machineId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['remote-machines'] })
    },
  })
}

export function useTestRemoteMachine() {
  return useMutation({
    mutationFn: (machineId: number) => testRemoteMachine(machineId),
  })
}

export function useStartRemoteAgent(projectName: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (machineId: number) => startRemoteAgent(projectName, machineId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['remote-agent-status', projectName] })
    },
  })
}

export function useStopRemoteAgent(projectName: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => stopRemoteAgent(projectName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['remote-agent-status', projectName] })
      queryClient.invalidateQueries({ queryKey: ['remote-agents-all'] })
    },
  })
}

export function useGracefulStopRemoteAgent(projectName: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => gracefulStopRemoteAgent(projectName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['remote-agent-status', projectName] })
      queryClient.invalidateQueries({ queryKey: ['remote-agents-all'] })
    },
  })
}

export function useRemoteAgentStatus(projectName: string | null) {
  return useQuery({
    queryKey: ['remote-agent-status', projectName],
    queryFn: () => getRemoteAgentStatus(projectName!),
    enabled: !!projectName,
    refetchInterval: 10000,
  })
}
