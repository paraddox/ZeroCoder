import { useState } from 'react'
import { X, Plus, Trash2, Wifi, WifiOff, Loader2, Server } from 'lucide-react'
import { useRemoteMachines, useAddRemoteMachine, useRemoveRemoteMachine, useTestRemoteMachine } from '../hooks/useRemoteMachines'

interface AppSettingsModalProps {
  isOpen: boolean
  onClose: () => void
}

export function AppSettingsModal({ isOpen, onClose }: AppSettingsModalProps) {
  const { data: machines, isLoading } = useRemoteMachines()
  const addMachine = useAddRemoteMachine()
  const removeMachine = useRemoveRemoteMachine()
  const testMachine = useTestRemoteMachine()

  const [showAddForm, setShowAddForm] = useState(false)
  const [formName, setFormName] = useState('')
  const [formHost, setFormHost] = useState('')
  const [formPort, setFormPort] = useState('22')
  const [formUsername, setFormUsername] = useState('root')
  const [formKeyPath, setFormKeyPath] = useState('')
  const [addError, setAddError] = useState<string | null>(null)

  if (!isOpen) return null

  const resetForm = () => {
    setFormName('')
    setFormHost('')
    setFormPort('22')
    setFormUsername('root')
    setFormKeyPath('')
    setAddError(null)
    setShowAddForm(false)
  }

  const handleAdd = async () => {
    setAddError(null)
    try {
      await addMachine.mutateAsync({
        name: formName,
        host: formHost,
        port: parseInt(formPort, 10) || 22,
        username: formUsername || 'root',
        ssh_key_path: formKeyPath || null,
      })
      resetForm()
    } catch (err: unknown) {
      setAddError(err instanceof Error ? err.message : 'Failed to add machine')
    }
  }

  const handleRemove = async (machineId: number) => {
    if (!confirm('Remove this machine?')) return
    await removeMachine.mutateAsync(machineId)
  }

  const handleTest = async (machineId: number) => {
    testMachine.mutate(machineId)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-[var(--color-bg)] border border-[var(--color-border)] rounded-[var(--radius-lg)] shadow-xl w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
          <div className="flex items-center gap-2">
            <Server size={18} className="text-[var(--color-primary)]" />
            <h2 className="font-display text-lg font-semibold text-[var(--color-text)]">
              App Settings
            </h2>
          </div>
          <button onClick={onClose} className="btn btn-ghost btn-icon">
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {/* Remote Machines Section */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-display text-base font-medium text-[var(--color-text)]">
                Remote Machines
              </h3>
              {!showAddForm && (
                <button
                  onClick={() => setShowAddForm(true)}
                  className="btn btn-primary btn-sm"
                >
                  <Plus size={14} />
                  Add Machine
                </button>
              )}
            </div>

            {/* Machine List */}
            {isLoading ? (
              <div className="flex items-center gap-2 text-[var(--color-text-secondary)] py-4">
                <Loader2 size={16} className="animate-spin" />
                Loading...
              </div>
            ) : machines && machines.length > 0 ? (
              <div className="space-y-2 mb-4">
                {machines.map((machine) => (
                  <div
                    key={machine.id}
                    className="flex items-center justify-between p-3 bg-[var(--color-bg-subtle)] border border-[var(--color-border)] rounded-md"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex items-center gap-1.5">
                        {machine.status === 'online' ? (
                          <Wifi size={14} className="text-[var(--color-done)]" />
                        ) : (
                          <WifiOff size={14} className="text-[var(--color-text-muted)]" />
                        )}
                        <span className="font-medium text-[var(--color-text)]">
                          {machine.name}
                        </span>
                      </div>
                      <span className="text-sm text-[var(--color-text-secondary)]">
                        {machine.username}@{machine.host}:{machine.port}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleTest(machine.id)}
                        className="btn btn-secondary btn-sm"
                        disabled={testMachine.isPending}
                      >
                        {testMachine.isPending ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          'Test'
                        )}
                      </button>
                      <button
                        onClick={() => handleRemove(machine.id)}
                        className="btn btn-ghost btn-icon text-[var(--color-danger)]"
                        title="Remove machine"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-[var(--color-text-muted)] py-4">
                No remote machines configured. Add one to run agents on remote servers.
              </p>
            )}

            {/* Test Result */}
            {testMachine.data && (
              <div className={`p-3 rounded-md mb-4 text-sm ${
                testMachine.data.connected
                  ? 'bg-green-500/10 border border-green-500/30 text-green-400'
                  : 'bg-red-500/10 border border-red-500/30 text-red-400'
              }`}>
                {testMachine.data.connected ? (
                  <div>
                    <p>Connected as: {testMachine.data.user}</p>
                    <p>Git: {testMachine.data.git_installed ? 'installed' : 'not found'}</p>
                    <p>Claude: {testMachine.data.claude_installed ? 'installed' : 'not found'}</p>
                  </div>
                ) : (
                  <p>Connection failed: {testMachine.data.error}</p>
                )}
              </div>
            )}

            {/* Add Machine Form */}
            {showAddForm && (
              <div className="p-4 bg-[var(--color-bg-elevated)] border border-[var(--color-border)] rounded-md space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs text-[var(--color-text-secondary)] mb-1">Name</label>
                    <input
                      type="text"
                      value={formName}
                      onChange={(e) => setFormName(e.target.value)}
                      placeholder="my-server"
                      className="input w-full"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-[var(--color-text-secondary)] mb-1">Host / IP</label>
                    <input
                      type="text"
                      value={formHost}
                      onChange={(e) => setFormHost(e.target.value)}
                      placeholder="192.168.1.100"
                      className="input w-full"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-[var(--color-text-secondary)] mb-1">Port</label>
                    <input
                      type="number"
                      value={formPort}
                      onChange={(e) => setFormPort(e.target.value)}
                      className="input w-full"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-[var(--color-text-secondary)] mb-1">Username</label>
                    <input
                      type="text"
                      value={formUsername}
                      onChange={(e) => setFormUsername(e.target.value)}
                      placeholder="root"
                      className="input w-full"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-[var(--color-text-secondary)] mb-1">SSH Key Path (optional)</label>
                  <input
                    type="text"
                    value={formKeyPath}
                    onChange={(e) => setFormKeyPath(e.target.value)}
                    placeholder="~/.ssh/id_ed25519"
                    className="input w-full"
                  />
                </div>

                {addError && (
                  <p className="text-sm text-[var(--color-danger)]">{addError}</p>
                )}

                <div className="flex items-center gap-2 pt-1">
                  <button
                    onClick={handleAdd}
                    disabled={!formName || !formHost || addMachine.isPending}
                    className="btn btn-primary btn-sm"
                  >
                    {addMachine.isPending ? (
                      <Loader2 size={14} className="animate-spin" />
                    ) : (
                      <Plus size={14} />
                    )}
                    {addMachine.isPending ? 'Connecting...' : 'Add & Test'}
                  </button>
                  <button onClick={resetForm} className="btn btn-secondary btn-sm">
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
