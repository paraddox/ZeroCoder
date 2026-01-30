import { useQuery } from '@tanstack/react-query'
import { listRemoteMachines, getAllRemoteAgents } from '../lib/api'
import type { RemoteMachine, RemoteAgentInfo } from '@zerocoder/shared'

export interface ProjectMachineInfo {
  machine: RemoteMachine
  /** Agent working on this project (if any) */
  agentForThisProject: RemoteAgentInfo | null
  /** Whether machine is idle (no agent on any project) */
  isIdle: boolean
  /** Whether machine is working on a different project */
  isWorkingOnOther: boolean
}

/**
 * Hook that combines remote machines with agent status filtered for a specific project.
 *
 * Returns machines in two categories:
 * 1. Idle machines (online, no active agent) - can start work on this project
 * 2. Machines working on this project - can stop
 *
 * Machines working on other projects are excluded.
 */
export function useProjectRemoteMachines(projectName: string | null) {
  // Fetch all machines
  const machinesQuery = useQuery({
    queryKey: ['remote-machines'],
    queryFn: listRemoteMachines,
    refetchInterval: 30000,
  })

  // Fetch all active agents across all projects
  const allAgentsQuery = useQuery({
    queryKey: ['remote-agents-all'],
    queryFn: getAllRemoteAgents,
    refetchInterval: 10000,
    enabled: !!projectName,
  })

  const machines = machinesQuery.data ?? []
  const allAgents = allAgentsQuery.data ?? []

  // Build machine info array
  const machineInfoList: ProjectMachineInfo[] = machines.map((machine) => {
    // Find any agent using this machine
    const agentOnMachine = allAgents.find((a) => a.machine_id === machine.id)

    // Find agent for this specific project
    const agentForThisProject = agentOnMachine?.project_name === projectName
      ? agentOnMachine
      : null

    return {
      machine,
      agentForThisProject,
      isIdle: !agentOnMachine,
      isWorkingOnOther: !!agentOnMachine && agentOnMachine.project_name !== projectName,
    }
  })

  // Filter: show idle machines and machines working on this project
  // Hide machines working on other projects
  const relevantMachines = machineInfoList.filter(
    (info) => !info.isWorkingOnOther
  )

  return {
    machines: relevantMachines,
    isLoading: machinesQuery.isLoading || allAgentsQuery.isLoading,
    isError: machinesQuery.isError || allAgentsQuery.isError,
    refetch: () => {
      machinesQuery.refetch()
      allAgentsQuery.refetch()
    },
  }
}
