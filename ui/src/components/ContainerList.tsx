import { FileText, Loader2 } from 'lucide-react'
import type { ContainerInfo, ContainerStatusType } from '../lib/types'

interface ContainerListProps {
  containers: ContainerInfo[]
  onViewLogs: (containerNumber: number) => void
  isLoading?: boolean
}

const statusConfig: Record<ContainerStatusType, { color: string; label: string; pulse: boolean }> = {
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
}

export function ContainerList({ containers, onViewLogs, isLoading = false }: ContainerListProps) {
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
      {/* Header */}
      <div className="column-header bg-[var(--color-bg-subtle)]">
        <h2 className="font-display text-base font-medium text-[var(--color-text)]">
          Containers
        </h2>
        <span className="badge badge-progress">{containers.length}</span>
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
                    {/* Container Name */}
                    <span className="font-display font-medium text-[var(--color-text)]">
                      Agent {container.container_number}
                    </span>

                    {/* Type Badge */}
                    <span className="badge text-xs bg-[var(--color-bg-subtle)] text-[var(--color-text-secondary)] border border-[var(--color-border)]">
                      {container.container_type}
                    </span>
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
