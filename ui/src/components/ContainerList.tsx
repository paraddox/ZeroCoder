import { FileText, Loader2, Settings2 } from 'lucide-react'
import type { ContainerInfo, ContainerStatusType, AgentStatus } from '../lib/types'

interface ContainerListProps {
  containers: ContainerInfo[]
  onViewLogs: (containerNumber: number) => void
  isLoading?: boolean
  // New props for status badge and slider
  agentStatus: AgentStatus
  agentRunning: boolean
  gracefulStopRequested: boolean
  targetCount: number
  runningCount: number
  onTargetChange: (count: number) => Promise<void>
}

const statusConfig: Record<ContainerStatusType, { color: string; label: string; pulse: boolean }> = {
  not_created: {
    color: 'var(--color-text-muted)',
    label: 'Not Created',
    pulse: false,
  },
  created: {
    color: 'var(--color-text-muted)',
    label: 'Created',
    pulse: false,
  },
  running: {
    color: 'var(--color-done)',
    label: 'Running',
    pulse: true,
  },
  stopping: {
    color: 'var(--color-pending)',
    label: 'Stopping',
    pulse: true,
  },
  stopped: {
    color: 'var(--color-text-muted)',
    label: 'Stopped',
    pulse: false,
  },
  completed: {
    color: 'var(--color-done)',
    label: 'Completed',
    pulse: false,
  },
}

export function ContainerList({
  containers,
  onViewLogs,
  isLoading = false,
  agentStatus,
  agentRunning,
  gracefulStopRequested,
  targetCount,
  runningCount,
  onTargetChange,
}: ContainerListProps) {
  // Container running but agent not running = "idle" mode
  const isIdleMode = agentStatus === 'running' && !agentRunning

  const handleSliderChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const newCount = parseInt(e.target.value, 10)
    await onTargetChange(newCount)
  }

  if (isLoading) {
    return (
      <div className="card p-6">
        <div className="flex items-center justify-center gap-2 text-[var(--color-text-secondary)]">
          <Loader2 size={16} className="animate-spin" />
          <span>Loading containers...</span>
        </div>
      </div>
    )
  }

  if (containers.length === 0) {
    return (
      <div className="card p-6">
        <div className="text-center text-[var(--color-text-muted)] text-sm">
          No containers available
        </div>
      </div>
    )
  }

  return (
    <div className="card overflow-hidden">
      {/* Header with Status Badge and Slider */}
      <div className="column-header bg-[var(--color-bg-subtle)] flex-wrap gap-y-2">
        {/* Status Badge */}
        <StatusBadge status={agentStatus} isIdleMode={isIdleMode} gracefulStopRequested={gracefulStopRequested} />

        {/* Divider */}
        <div className="w-px h-6 bg-[var(--color-border)]" />

        {/* Title and Count */}
        <h2 className="font-display text-base font-medium text-[var(--color-text)]">
          Containers
        </h2>
        <span className="badge badge-progress">{containers.length}</span>

        {/* Divider */}
        <div className="w-px h-6 bg-[var(--color-border)]" />

        {/* Container Count Slider */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Settings2 size={16} className="text-[var(--color-text-secondary)]" />
            <span className="text-sm font-medium text-[var(--color-text)]">Target</span>
          </div>

          <div className="flex items-center gap-3">
            <input
              type="range"
              min={1}
              max={10}
              value={targetCount}
              onChange={handleSliderChange}
              disabled={agentRunning}
              aria-label="Number of containers"
              aria-valuemin={1}
              aria-valuemax={10}
              aria-valuenow={targetCount}
              aria-valuetext={`${targetCount} container${targetCount > 1 ? 's' : ''}`}
              className="w-24 h-2 rounded-full appearance-none cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: agentRunning
                  ? 'var(--color-bg-muted)'
                  : `linear-gradient(to right, var(--color-progress) 0%, var(--color-progress) ${((targetCount - 1) / 9) * 100}%, var(--color-bg-muted) ${((targetCount - 1) / 9) * 100}%, var(--color-bg-muted) 100%)`,
              }}
            />
            <div className="flex items-center gap-1.5 min-w-[3.5rem]">
              <span
                className="font-mono text-lg font-semibold"
                style={{ color: 'var(--color-progress)' }}
              >
                {targetCount}
              </span>
              {runningCount > 0 && (
                <span className="text-xs text-[var(--color-text-muted)]">
                  ({runningCount})
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Container List */}
      <div className="divide-y divide-[var(--color-border)]">
        {containers.map((container, index) => {
          const config = statusConfig[container.status]

          return (
            <div
              key={container.id}
              className="p-4 bg-[var(--color-bg)] hover:bg-[var(--color-bg-elevated)] transition-colors animate-slide-in"
              style={{ animationDelay: `${index * 50}ms` }}
            >
              <div className="flex items-center justify-between gap-4">
                {/* Container Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-1">
                    {/* Container Name - special handling for Hound (container_number -1) */}
                    <span className="font-display font-medium text-[var(--color-text)]">
                      {container.container_number === -1 ? 'Hound' : `Agent ${container.container_number}`}
                    </span>

                    {/* Agent Type Badge */}
                    <span className="badge text-xs bg-[var(--color-bg-subtle)] text-[var(--color-text-secondary)] border border-[var(--color-border)]">
                      {container.agent_type || container.container_type}
                    </span>

                    {/* SDK Badge */}
                    {container.sdk_type && (
                      <span className={`badge text-xs border ${
                        container.sdk_type === 'claude'
                          ? 'bg-orange-500/10 text-orange-400 border-orange-500/30'
                          : 'bg-blue-500/10 text-blue-400 border-blue-500/30'
                      }`}>
                        {container.sdk_type}
                      </span>
                    )}
                  </div>

                  {/* Current Feature */}
                  {container.current_feature ? (
                    <p className="text-sm text-[var(--color-text-secondary)] truncate">
                      {container.current_feature}
                    </p>
                  ) : (
                    <p className="text-sm text-[var(--color-text-muted)] italic">
                      No active feature
                    </p>
                  )}
                </div>

                {/* Status and Actions */}
                <div className="flex items-center gap-3 flex-shrink-0">
                  {/* Status Indicator */}
                  <div className="flex items-center gap-2 px-3 py-1.5 bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-md">
                    <span
                      className={`status-dot ${config.pulse ? 'status-dot-pulse' : ''}`}
                      style={{ backgroundColor: config.color }}
                    />
                    <span
                      className="font-medium text-sm"
                      style={{ color: config.color }}
                    >
                      {config.label}
                    </span>
                  </div>

                  {/* View Logs Button */}
                  <button
                    onClick={() => onViewLogs(container.container_number)}
                    className="btn btn-secondary btn-icon"
                    title="View Logs"
                  >
                    <FileText size={16} />
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// Status Badge component for overall agent status
const agentStatusConfig: Record<AgentStatus, { color: string; label: string; pulse: boolean }> = {
  not_created: {
    color: 'var(--color-text-muted)',
    label: 'Not Created',
    pulse: false,
  },
  stopped: {
    color: 'var(--color-text-muted)',
    label: 'Stopped',
    pulse: false,
  },
  running: {
    color: 'var(--color-done)',
    label: 'Running',
    pulse: true,
  },
  paused: {
    color: 'var(--color-progress)',
    label: 'Paused',
    pulse: false,
  },
  crashed: {
    color: 'var(--color-danger)',
    label: 'Crashed',
    pulse: true,
  },
  completed: {
    color: 'var(--color-done)',
    label: 'Completed',
    pulse: false,
  },
}

function StatusBadge({ status, isIdleMode = false, gracefulStopRequested = false }: { status: AgentStatus; isIdleMode?: boolean; gracefulStopRequested?: boolean }) {
  // Override for idle mode (container running, no agent)
  if (isIdleMode) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-md">
        <span
          className="status-dot"
          style={{ backgroundColor: 'var(--color-progress)' }}
        />
        <span
          className="font-medium text-sm"
          style={{ color: 'var(--color-progress)' }}
        >
          Edit Mode
        </span>
      </div>
    )
  }

  // Override for graceful stop (running, but stopping after current session)
  if (status === 'running' && gracefulStopRequested) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-md">
        <span
          className="status-dot status-dot-pulse"
          style={{ backgroundColor: 'var(--color-progress)' }}
        />
        <span
          className="font-medium text-sm"
          style={{ color: 'var(--color-progress)' }}
        >
          Running current session only
        </span>
      </div>
    )
  }

  const config = agentStatusConfig[status] || agentStatusConfig.stopped

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-md">
      <span
        className={`status-dot ${config.pulse ? 'status-dot-pulse' : ''}`}
        style={{ backgroundColor: config.color }}
      />
      <span
        className="font-medium text-sm"
        style={{ color: config.color }}
      >
        {config.label}
      </span>
    </div>
  )
}
