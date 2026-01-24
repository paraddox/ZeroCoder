import { X, Server, Wifi, WifiOff, Loader2 } from 'lucide-react'
import { useRemoteMachines, useStartRemoteAgent } from '../hooks/useRemoteMachines'

interface RemoteMachineModalProps {
  isOpen: boolean
  onClose: () => void
  projectName: string
}

export function RemoteMachineModal({ isOpen, onClose, projectName }: RemoteMachineModalProps) {
  const { data: machines, isLoading } = useRemoteMachines()
  const startRemote = useStartRemoteAgent(projectName)

  if (!isOpen) return null

  const handleStart = async (machineId: number) => {
    try {
      await startRemote.mutateAsync(machineId)
      onClose()
    } catch {
      // Error handled by mutation state
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-[var(--color-bg)] border border-[var(--color-border)] rounded-[var(--radius-lg)] shadow-xl w-full max-w-lg overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
          <div className="flex items-center gap-2">
            <Server size={18} className="text-[var(--color-primary)]" />
            <h2 className="font-display text-lg font-semibold text-[var(--color-text)]">
              Start on Remote Machine
            </h2>
          </div>
          <button onClick={onClose} className="btn btn-ghost btn-icon">
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="p-4">
          {isLoading ? (
            <div className="flex items-center justify-center gap-2 py-8 text-[var(--color-text-secondary)]">
              <Loader2 size={16} className="animate-spin" />
              Loading machines...
            </div>
          ) : machines && machines.length > 0 ? (
            <div className="space-y-2">
              {machines.map((machine) => {
                const isOnline = machine.status === 'online'
                return (
                  <div
                    key={machine.id}
                    className="flex items-center justify-between p-3 bg-[var(--color-bg-subtle)] border border-[var(--color-border)] rounded-md"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-1.5">
                        {isOnline ? (
                          <Wifi size={14} className="text-[var(--color-done)]" />
                        ) : (
                          <WifiOff size={14} className="text-[var(--color-text-muted)]" />
                        )}
                        <span className="font-medium text-[var(--color-text)]">
                          {machine.name}
                        </span>
                      </div>
                      <span className="text-sm text-[var(--color-text-secondary)]">
                        {machine.host}
                      </span>
                    </div>
                    <button
                      onClick={() => handleStart(machine.id)}
                      disabled={!isOnline || startRemote.isPending}
                      className="btn btn-success btn-sm"
                      title={isOnline ? 'Start agent on this machine' : 'Machine is offline'}
                    >
                      {startRemote.isPending ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        'Start'
                      )}
                    </button>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="text-center py-8">
              <p className="text-[var(--color-text-muted)] mb-2">
                No remote machines configured.
              </p>
              <p className="text-sm text-[var(--color-text-secondary)]">
                Add machines in App Settings (gear icon in the header).
              </p>
            </div>
          )}

          {startRemote.error && (
            <p className="mt-3 text-sm text-[var(--color-danger)]">
              {startRemote.error instanceof Error ? startRemote.error.message : 'Failed to start agent'}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
