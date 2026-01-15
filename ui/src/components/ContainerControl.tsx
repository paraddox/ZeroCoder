import { Play, Square, PauseCircle, Edit3, Settings2 } from 'lucide-react'

interface ContainerControlProps {
  projectName: string
  targetCount: number
  runningCount: number
  agentRunning: boolean
  gracefulStopRequested: boolean
  onTargetChange: (count: number) => Promise<void>
  onStart: () => Promise<void>
  onStopNow: () => Promise<void>
  onGracefulStop: () => Promise<void>
  onEditTasks: () => void
}

export function ContainerControl({
  projectName: _projectName,
  targetCount,
  runningCount,
  agentRunning,
  gracefulStopRequested,
  onTargetChange,
  onStart,
  onStopNow,
  onGracefulStop,
  onEditTasks,
}: ContainerControlProps) {
  const handleSliderChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const newCount = parseInt(e.target.value, 10)
    await onTargetChange(newCount)
  }

  return (
    <div className="flex items-center gap-4 p-4 bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-[var(--radius-lg)]">
      {/* Container Count Slider */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <Settings2 size={16} className="text-[var(--color-text-secondary)]" />
          <span className="text-sm font-medium text-[var(--color-text)]">Containers</span>
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
            className="w-32 h-2 rounded-full appearance-none cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              background: agentRunning
                ? 'var(--color-bg-muted)'
                : `linear-gradient(to right, var(--color-progress) 0%, var(--color-progress) ${((targetCount - 1) / 9) * 100}%, var(--color-bg-muted) ${((targetCount - 1) / 9) * 100}%, var(--color-bg-muted) 100%)`,
            }}
          />
          <div className="flex items-center gap-1.5 min-w-[4rem]">
            <span
              className="font-mono text-lg font-semibold"
              style={{ color: 'var(--color-progress)' }}
            >
              {targetCount}
            </span>
            {runningCount > 0 && (
              <span className="text-xs text-[var(--color-text-muted)]">
                ({runningCount} active)
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Divider */}
      <div className="w-px h-8 bg-[var(--color-border)]" />

      {/* Control Buttons */}
      <div className="flex items-center gap-2">
        {/* Start Button */}
        <button
          onClick={onStart}
          disabled={agentRunning}
          className="btn btn-success"
          title="Start containers"
        >
          <Play size={16} />
          <span>Start</span>
        </button>

        {/* Stop Now Button */}
        <button
          onClick={onStopNow}
          disabled={!agentRunning}
          className="btn btn-danger"
          title="Force stop all containers immediately"
        >
          <Square size={16} />
          <span>Stop Now</span>
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
    </div>
  )
}
