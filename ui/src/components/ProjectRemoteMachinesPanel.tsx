import { Server, Wifi, WifiOff, Loader2, Play, Square } from 'lucide-react'
import { useProjectRemoteMachines } from '../hooks/useProjectRemoteMachines'
import { useStartRemoteAgent, useStopRemoteAgent } from '../hooks/useRemoteMachines'
import type { ProjectMachineInfo } from '../hooks/useProjectRemoteMachines'

interface ProjectRemoteMachinesPanelProps {
  projectName: string
}

export function ProjectRemoteMachinesPanel({ projectName }: ProjectRemoteMachinesPanelProps) {
  const { machines, isLoading } = useProjectRemoteMachines(projectName)
  const startRemote = useStartRemoteAgent(projectName)
  const stopRemote = useStopRemoteAgent(projectName)

  const handleStart = async (machineId: number) => {
    try {
      await startRemote.mutateAsync(machineId)
    } catch {
      // Error handled by mutation state
    }
  }

  const handleStop = async () => {
    try {
      await stopRemote.mutateAsync()
    } catch {
      // Error handled by mutation state
    }
  }

  // Don't render if no machines are configured at all
  if (!isLoading && machines.length === 0) {
    return null
  }

  return (
    <div className="card overflow-hidden">
      {/* Header */}
      <div className="column-header bg-[var(--color-bg-subtle)]">
        <Server size={16} className="text-[var(--color-primary)]" />
        <h2 className="font-display text-base font-medium text-[var(--color-text)]">
          Remote Machines
        </h2>
        <span className="badge badge-progress">{machines.length}</span>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="p-6">
          <div className="flex items-center justify-center gap-2 text-[var(--color-text-secondary)]">
            <Loader2 size={16} className="animate-spin" />
            <span>Loading machines...</span>
          </div>
        </div>
      ) : (
        <div className="divide-y divide-[var(--color-border)]">
          {machines.map((info, index) => (
            <MachineRow
              key={info.machine.id}
              info={info}
              index={index}
              onStart={handleStart}
              onStop={handleStop}
              isStartPending={startRemote.isPending}
              isStopPending={stopRemote.isPending}
            />
          ))}
        </div>
      )}

      {/* Error display */}
      {(startRemote.error || stopRemote.error) && (
        <div className="px-4 pb-4">
          <p className="text-sm text-[var(--color-danger)]">
            {startRemote.error instanceof Error
              ? startRemote.error.message
              : stopRemote.error instanceof Error
                ? stopRemote.error.message
                : 'Operation failed'}
          </p>
        </div>
      )}
    </div>
  )
}

interface MachineRowProps {
  info: ProjectMachineInfo
  index: number
  onStart: (machineId: number) => void
  onStop: () => void
  isStartPending: boolean
  isStopPending: boolean
}

function MachineRow({
  info,
  index,
  onStart,
  onStop,
  isStartPending,
  isStopPending,
}: MachineRowProps) {
  const { machine, agentForThisProject } = info
  const isOnline = machine.status === 'online'
  const isWorking = !!agentForThisProject

  return (
    <div
      className="p-4 bg-[var(--color-bg)] hover:bg-[var(--color-bg-elevated)] transition-colors animate-slide-in"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      <div className="flex items-center justify-between gap-4">
        {/* Machine Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-1">
            {/* Online/Offline indicator */}
            {isOnline ? (
              <Wifi size={14} className="text-[var(--color-done)] flex-shrink-0" />
            ) : (
              <WifiOff size={14} className="text-[var(--color-text-muted)] flex-shrink-0" />
            )}

            {/* Machine Name */}
            <span className="font-display font-medium text-[var(--color-text)]">
              {machine.name}
            </span>

            {/* Host */}
            <span className="text-sm text-[var(--color-text-secondary)]">
              ({machine.host})
            </span>
          </div>

          {/* Status line */}
          {isWorking ? (
            <p className="text-sm text-[var(--color-progress)] ml-6">
              working: {agentForThisProject.current_feature || 'starting...'}
            </p>
          ) : (
            <p className="text-sm text-[var(--color-text-muted)] italic ml-6">
              {isOnline ? 'idle' : 'offline'}
            </p>
          )}
        </div>

        {/* Action Button */}
        <div className="flex-shrink-0">
          {isWorking ? (
            <button
              onClick={onStop}
              disabled={isStopPending}
              className="btn btn-danger btn-sm flex items-center gap-1.5"
              title="Stop agent on this machine"
            >
              {isStopPending ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Square size={12} />
              )}
              Stop
            </button>
          ) : (
            <button
              onClick={() => onStart(machine.id)}
              disabled={!isOnline || isStartPending}
              className="btn btn-success btn-sm flex items-center gap-1.5"
              title={isOnline ? 'Start agent on this machine' : 'Machine is offline'}
            >
              {isStartPending ? (
                <Loader2 size={12} className="animate-spin" />
              ) : (
                <Play size={12} />
              )}
              Start
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
