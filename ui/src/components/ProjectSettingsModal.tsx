/**
 * Project Settings Modal Component
 *
 * Modal for configuring project settings like agent model selection.
 */

import { useState, useEffect } from 'react'
import { X, Save, Loader2, AlertCircle, Settings } from 'lucide-react'
import { useUpdateProjectSettings } from '../hooks/useProjects'
import { AGENT_MODELS, type AgentModel, type ProjectSummary } from '../lib/types'

interface ProjectSettingsModalProps {
  project: ProjectSummary
  onClose: () => void
  onSaved?: () => void
}

export function ProjectSettingsModal({ project, onClose, onSaved }: ProjectSettingsModalProps) {
  const [selectedModel, setSelectedModel] = useState<AgentModel>(
    project.agent_model || 'claude-sonnet-4-5-20250514'
  )
  const [error, setError] = useState<string | null>(null)

  const updateSettings = useUpdateProjectSettings(project.name)

  // Update selected model when project changes
  useEffect(() => {
    setSelectedModel(project.agent_model || 'claude-sonnet-4-5-20250514')
  }, [project.agent_model])

  const handleSave = async () => {
    setError(null)

    try {
      await updateSettings.mutateAsync({ agent_model: selectedModel })
      onSaved?.()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update settings')
    }
  }

  const hasChanges = selectedModel !== (project.agent_model || 'claude-sonnet-4-5-20250514')

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal w-full max-w-md p-0"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
          <div className="flex items-center gap-3">
            <Settings size={20} className="text-[var(--color-text-secondary)]" />
            <div>
              <h2 className="font-display text-lg font-medium">
                Project Settings
              </h2>
              <span className="text-sm text-[var(--color-text-secondary)]">
                {project.name}
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="btn btn-ghost p-2"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-4">
          {/* Error Message */}
          {error && (
            <div className="flex items-center gap-3 p-3 bg-[var(--color-danger)] text-[var(--color-text-inverse)] border border-[var(--color-border)] rounded-lg text-sm">
              <AlertCircle size={16} />
              <span className="flex-1">{error}</span>
              <button onClick={() => setError(null)}>
                <X size={14} />
              </button>
            </div>
          )}

          {/* Model Selection */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Agent Model
            </label>
            <p className="text-xs text-[var(--color-text-secondary)] mb-3">
              Select the model for coder and overseer agents. Changes apply to the next agent session.
            </p>
            <div className="space-y-2">
              {AGENT_MODELS.map((model) => (
                <label
                  key={model.id}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    selectedModel === model.id
                      ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/5'
                      : 'border-[var(--color-border)] hover:border-[var(--color-text-secondary)]'
                  }`}
                >
                  <input
                    type="radio"
                    name="agent-model"
                    value={model.id}
                    checked={selectedModel === model.id}
                    onChange={() => setSelectedModel(model.id)}
                    className="w-4 h-4 text-[var(--color-primary)]"
                  />
                  <div className="flex-1">
                    <span className="font-medium">{model.name}</span>
                    {model.id === 'claude-opus-4-5-20251101' && (
                      <span className="ml-2 text-xs px-2 py-0.5 rounded bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
                        Most capable
                      </span>
                    )}
                    {model.id === 'claude-sonnet-4-5-20250514' && (
                      <span className="ml-2 text-xs px-2 py-0.5 rounded bg-[var(--color-success)]/10 text-[var(--color-success)]">
                        Cost effective
                      </span>
                    )}
                    {model.badge && (
                      <span className={`ml-2 text-xs px-2 py-0.5 rounded bg-[var(--color-${model.badgeColor || 'primary'})]/10 text-[var(--color-${model.badgeColor || 'primary'})]`}>
                        {model.badge}
                      </span>
                    )}
                  </div>
                </label>
              ))}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="p-4 border-t border-[var(--color-border)] bg-[var(--color-bg)] flex gap-3">
          <button
            onClick={handleSave}
            disabled={updateSettings.isPending || !hasChanges}
            className="btn btn-primary flex-1"
          >
            {updateSettings.isPending ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <>
                <Save size={18} />
                Save Changes
              </>
            )}
          </button>
          <button
            onClick={onClose}
            disabled={updateSettings.isPending}
            className="btn btn-ghost"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
