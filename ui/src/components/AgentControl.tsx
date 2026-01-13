import { useState } from 'react'
import { Play, Square, Loader2, Zap, Edit3 } from 'lucide-react'
import {
  useStartAgent,
  useStopAgent,
  useStartContainerOnly,
} from '../hooks/useProjects'
import type { AgentStatus } from '../lib/types'

interface AgentControlProps {
  projectName: string
  status: AgentStatus
  yoloMode?: boolean
  agentRunning?: boolean
}

export function AgentControl({ projectName, status, yoloMode = false, agentRunning = false }: AgentControlProps) {
  const [yoloEnabled, setYoloEnabled] = useState(false)

  const startAgent = useStartAgent(projectName)
  const stopAgent = useStopAgent(projectName)
  const startContainerOnly = useStartContainerOnly(projectName)

  const isLoading =
    startAgent.isPending ||
    stopAgent.isPending ||
    startContainerOnly.isPending

  const handleStart = () => startAgent.mutate(yoloEnabled)
  const handleStop = () => stopAgent.mutate()
  const handleStartContainer = () => startContainerOnly.mutate()

  // Container running but agent not running = "idle" mode
  const isIdleMode = status === 'running' && !agentRunning

  return (
    <div className="flex items-center gap-2">
      {/* Status Indicator */}
      <StatusIndicator status={status} isIdleMode={isIdleMode} />

      {/* YOLO Mode Indicator */}
      {status === 'running' && yoloMode && !isIdleMode && (
        <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-[var(--color-pending-bg)] border border-[var(--color-pending-border)] rounded-md">
          <Zap size={12} className="text-[var(--color-pending)]" />
          <span className="font-medium text-xs text-[#9A7B2E]">
            YOLO
          </span>
        </div>
      )}

      {/* Control Buttons */}
      <div className="flex gap-1.5">
        {status === 'not_created' || status === 'stopped' || status === 'crashed' ? (
          <>
            {/* Edit Mode Button - starts container without agent */}
            <button
              onClick={handleStartContainer}
              disabled={isLoading}
              className="btn btn-secondary btn-icon"
              title="Start container for editing tasks (no agent)"
            >
              {isLoading && startContainerOnly.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Edit3 size={16} />
              )}
            </button>
            {/* YOLO Toggle */}
            <button
              onClick={() => setYoloEnabled(!yoloEnabled)}
              className={`btn btn-icon ${
                yoloEnabled ? 'btn-warning' : 'btn-secondary'
              }`}
              title="YOLO Mode: Skip testing for rapid prototyping"
            >
              <Zap size={16} />
            </button>
            <button
              onClick={handleStart}
              disabled={isLoading}
              className="btn btn-success btn-icon"
              title={yoloEnabled ? "Start Agent (YOLO Mode)" : "Start Agent"}
            >
              {isLoading && startAgent.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Play size={16} />
              )}
            </button>
          </>
        ) : isIdleMode ? (
          <>
            {/* Container running but no agent - show Run and Stop */}
            <button
              onClick={() => setYoloEnabled(!yoloEnabled)}
              className={`btn btn-icon ${
                yoloEnabled ? 'btn-warning' : 'btn-secondary'
              }`}
              title="YOLO Mode: Skip testing for rapid prototyping"
            >
              <Zap size={16} />
            </button>
            <button
              onClick={handleStart}
              disabled={isLoading}
              className="btn btn-success btn-icon"
              title={yoloEnabled ? "Start Agent (YOLO Mode)" : "Start Agent"}
            >
              {isLoading && startAgent.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Play size={16} />
              )}
            </button>
            <button
              onClick={handleStop}
              disabled={isLoading}
              className="btn btn-danger btn-icon"
              title="Stop Container"
            >
              {isLoading && stopAgent.isPending ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Square size={16} />
              )}
            </button>
          </>
        ) : status === 'running' ? (
          <button
            onClick={handleStop}
            disabled={isLoading}
            className="btn btn-danger btn-icon"
            title="Stop Agent"
          >
            {isLoading ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Square size={16} />
            )}
          </button>
        ) : null}
      </div>
    </div>
  )
}

function StatusIndicator({ status, isIdleMode = false }: { status: AgentStatus; isIdleMode?: boolean }) {
  const statusConfig: Record<AgentStatus, { color: string; label: string; pulse: boolean }> = {
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
    crashed: {
      color: 'var(--color-danger)',
      label: 'Crashed',
      pulse: true,
    },
  }

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

  const config = statusConfig[status] || statusConfig.stopped

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
