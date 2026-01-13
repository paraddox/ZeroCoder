import { Wifi, WifiOff } from 'lucide-react'

interface ProgressDashboardProps {
  passing: number
  total: number
  percentage: number
  isConnected: boolean
}

export function ProgressDashboard({
  passing,
  total,
  percentage,
  isConnected,
}: ProgressDashboardProps) {
  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="font-display text-lg font-medium text-[var(--color-text)]">
          Progress
        </h2>
        <div className="flex items-center gap-2">
          {isConnected ? (
            <>
              <Wifi size={14} className="text-[var(--color-done)]" />
              <span className="text-sm text-[var(--color-done)] font-medium">Live</span>
            </>
          ) : (
            <>
              <WifiOff size={14} className="text-[var(--color-danger)]" />
              <span className="text-sm text-[var(--color-danger)] font-medium">Offline</span>
            </>
          )}
        </div>
      </div>

      {/* Large Percentage */}
      <div className="text-center mb-6">
        <span className="font-display text-5xl font-medium text-[var(--color-text)]">
          {percentage.toFixed(1)}
        </span>
        <span className="font-display text-2xl font-medium text-[var(--color-text-muted)] ml-1">
          %
        </span>
      </div>

      {/* Progress Bar */}
      <div className="progress-bar mb-6">
        <div
          className="progress-fill"
          style={{ width: `${percentage}%` }}
        />
      </div>

      {/* Stats */}
      <div className="flex justify-center gap-8 text-center">
        <div>
          <span className="font-mono text-2xl font-medium text-[var(--color-done)]">
            {passing}
          </span>
          <span className="block text-sm text-[var(--color-text-muted)] mt-1">
            Passing
          </span>
        </div>
        <div className="text-2xl text-[var(--color-border)]">/</div>
        <div>
          <span className="font-mono text-2xl font-medium text-[var(--color-text)]">
            {total}
          </span>
          <span className="block text-sm text-[var(--color-text-muted)] mt-1">
            Total
          </span>
        </div>
      </div>
    </div>
  )
}
