import { Plus, Trash2, Settings } from 'lucide-react'
import { AgentControl } from './AgentControl'
import { CompactProgress } from './CompactProgress'
import type { AgentStatus } from '../lib/types'

interface ControlBarProps {
  projectName: string
  agentStatus: AgentStatus
  yoloMode: boolean
  agentRunning: boolean
  gracefulStopRequested?: boolean
  progress: {
    passing: number
    total: number
    percentage: number
  }
  isConnected: boolean
  onAddFeature: () => void
  onSettings: () => void
  onDelete: () => void
}

export function ControlBar({
  projectName,
  agentStatus,
  yoloMode,
  agentRunning,
  gracefulStopRequested = false,
  progress,
  isConnected,
  onAddFeature,
  onSettings,
  onDelete,
}: ControlBarProps) {
  return (
    <div className="bg-[var(--color-bg-elevated)] border-b border-[var(--color-border)]">
      <div className="max-w-7xl mx-auto px-6 py-3">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          {/* Left: Agent Controls */}
          <AgentControl
            projectName={projectName}
            status={agentStatus}
            yoloMode={yoloMode}
            agentRunning={agentRunning}
            gracefulStopRequested={gracefulStopRequested}
          />

          {/* Right: Actions + Progress */}
          <div className="flex items-center gap-3">
            {!agentRunning && (
              <button
                onClick={onAddFeature}
                className="btn btn-primary btn-sm"
                title="Add a new feature (Press N)"
              >
                <Plus size={14} />
                Add Feature
                <kbd className="ml-1.5 px-1.5 py-0.5 text-xs bg-white/20 rounded-sm font-mono">
                  N
                </kbd>
              </button>
            )}
            <CompactProgress
              passing={progress.passing}
              total={progress.total}
              percentage={progress.percentage}
              isConnected={isConnected}
            />
            <button
              onClick={onSettings}
              className="btn btn-ghost btn-icon text-[var(--color-text-secondary)] hover:text-[var(--color-primary)]"
              title="Project settings"
            >
              <Settings size={16} />
            </button>
            <button
              onClick={onDelete}
              className="btn btn-ghost btn-icon text-[var(--color-text-secondary)] hover:text-[var(--color-danger)] hover:bg-[var(--color-danger-bg)]"
              title="Delete project"
            >
              <Trash2 size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
