import { Wifi, WifiOff } from 'lucide-react'

interface CompactProgressProps {
  passing: number
  total: number
  percentage: number
  isConnected: boolean
}

export function CompactProgress({
  passing,
  total,
  percentage,
  isConnected,
}: CompactProgressProps) {
  // Color-code percentage based on completion
  const getPercentageColor = () => {
    if (percentage >= 75) return 'var(--color-done)'
    if (percentage >= 25) return 'var(--color-progress)'
    return 'var(--color-pending)'
  }

  return (
    <div className="compact-progress">
      {/* Connection Indicator */}
      <div className="compact-progress-connection">
        {isConnected ? (
          <>
            <Wifi size={12} className="text-[var(--color-done)]" />
            <span className="text-[var(--color-done)]">Live</span>
          </>
        ) : (
          <>
            <WifiOff size={12} className="text-[var(--color-danger)]" />
            <span className="text-[var(--color-danger)]">Offline</span>
          </>
        )}
      </div>

      {/* Progress Stats */}
      <div>
        <span
          className="compact-progress-percentage"
          style={{ color: getPercentageColor() }}
        >
          {percentage.toFixed(1)}%
        </span>
        <span className="compact-progress-fraction">
          {' '}({passing}/{total})
        </span>
      </div>
    </div>
  )
}
