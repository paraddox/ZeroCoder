import { useState } from 'react'
import { Play, Square, PauseCircle, Edit3, Loader2, Plus, Trash2, Settings } from 'lucide-react'
import { CompactProgress } from './CompactProgress'

interface ContainerControlProps {
  projectName: string
  agentRunning: boolean
  gracefulStopRequested: boolean
  progress: {
    passing: number
    total: number
    percentage: number
  }
  isConnected: boolean
  onStart: () => Promise<void>
  onStopNow: () => Promise<void>
  onGracefulStop: () => Promise<void>
  onEditTasks: () => void
  onAddFeature: () => void
  onSettings: () => void
  onDelete: () => void
}

export function ContainerControl({
  projectName: _projectName,
  agentRunning,
  gracefulStopRequested,
  progress,
  isConnected,
  onStart,
  onStopNow,
  onGracefulStop,
  onEditTasks,
  onAddFeature,
  onSettings,
  onDelete,
}: ContainerControlProps) {
  const [isStarting, setIsStarting] = useState(false)
  const [isStopping, setIsStopping] = useState(false)

  const handleStart = async () => {
    setIsStarting(true)
    try {
      await onStart()
    } finally {
      setIsStarting(false)
    }
  }

  const handleStopNow = async () => {
    setIsStopping(true)
    try {
      await onStopNow()
    } finally {
      setIsStopping(false)
    }
  }

  return (
    <div className="flex items-center gap-4 p-4 bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-[var(--radius-lg)] flex-wrap">
      {/* Control Buttons */}
      <div className="flex items-center gap-2">
        {/* Start Button */}
        <button
          onClick={handleStart}
          disabled={agentRunning || isStarting}
          className="btn btn-success"
          title="Start containers"
        >
          {isStarting ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Play size={16} />
          )}
          <span>{isStarting ? 'Starting...' : 'Start'}</span>
        </button>

        {/* Stop Now Button */}
        <button
          onClick={handleStopNow}
          disabled={!agentRunning || isStopping}
          className="btn btn-danger"
          title="Force stop all containers immediately"
        >
          {isStopping ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Square size={16} />
          )}
          <span>{isStopping ? 'Stopping...' : 'Stop Now'}</span>
        </button>

        {/* Complete & Stop Button */}
        <button
          onClick={onGracefulStop}
          disabled={!agentRunning || gracefulStopRequested}
          className={`btn ${gracefulStopRequested ? 'btn-secondary' : 'btn-warning'}`}
          title={gracefulStopRequested ? "Stopping after current tasks complete..." : "Complete current tasks then stop"}
          aria-pressed={gracefulStopRequested}
        >
          <PauseCircle size={16} />
          <span>{gracefulStopRequested ? 'Stopping...' : 'Complete & Stop'}</span>
        </button>

        {/* Divider */}
        <div className="w-px h-8 bg-[var(--color-border)]" />

        {/* Edit Tasks Button */}
        <button
          onClick={onEditTasks}
          disabled={agentRunning}
          className="btn btn-secondary"
          title="Edit project tasks"
        >
          <Edit3 size={16} />
          <span>Edit Tasks</span>
        </button>
      </div>

      {/* Divider */}
      <div className="w-px h-8 bg-[var(--color-border)]" />

      {/* Right side: Add Feature, Progress, Settings, Delete */}
      <div className="flex items-center gap-3 ml-auto">
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
  )
}
