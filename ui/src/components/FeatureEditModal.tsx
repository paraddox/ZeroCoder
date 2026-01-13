/**
 * Feature Edit Modal Component
 *
 * Modal for editing a feature's JSON data directly.
 */

import { useState, useEffect } from 'react'
import { X, Save, Loader2, AlertCircle } from 'lucide-react'
import { useUpdateFeature } from '../hooks/useProjects'
import type { Feature } from '../lib/types'

interface FeatureEditModalProps {
  feature: Feature
  projectName: string
  onClose: () => void
  onSaved?: () => void
}

// Fields that can be edited
interface EditableFeatureData {
  name: string
  description: string
  category: string
  priority: number
  steps: string[]
}

export function FeatureEditModal({ feature, projectName, onClose, onSaved }: FeatureEditModalProps) {
  const [jsonText, setJsonText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [parseError, setParseError] = useState<string | null>(null)

  const updateFeature = useUpdateFeature(projectName)

  // Initialize JSON text from feature
  useEffect(() => {
    const editableData: EditableFeatureData = {
      name: feature.name,
      description: feature.description,
      category: feature.category,
      priority: feature.priority,
      steps: feature.steps,
    }
    setJsonText(JSON.stringify(editableData, null, 2))
  }, [feature])

  // Validate JSON as user types
  useEffect(() => {
    try {
      JSON.parse(jsonText)
      setParseError(null)
    } catch {
      setParseError('Invalid JSON syntax')
    }
  }, [jsonText])

  const handleSave = async () => {
    setError(null)

    // Parse and validate JSON
    let parsed: EditableFeatureData
    try {
      parsed = JSON.parse(jsonText)
    } catch {
      setError('Invalid JSON syntax')
      return
    }

    // Validate required fields
    if (!parsed.name?.trim()) {
      setError('Name is required')
      return
    }
    if (typeof parsed.priority !== 'number' || parsed.priority < 0) {
      setError('Priority must be a non-negative number')
      return
    }
    if (!Array.isArray(parsed.steps)) {
      setError('Steps must be an array')
      return
    }

    try {
      await updateFeature.mutateAsync({
        featureId: feature.id,
        data: {
          name: parsed.name,
          description: parsed.description || '',
          category: parsed.category || '',
          priority: parsed.priority,
          steps: parsed.steps,
        },
      })
      onSaved?.()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update feature')
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal w-full max-w-2xl p-0"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
          <div>
            <h2 className="font-display text-lg font-medium">
              Edit Feature
            </h2>
            <span className="text-sm text-[var(--color-text-secondary)] font-mono">
              {feature.id}
            </span>
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

          {/* JSON Editor */}
          <div>
            <label className="block text-sm font-medium mb-2">
              Feature Data (JSON)
            </label>
            <textarea
              value={jsonText}
              onChange={(e) => setJsonText(e.target.value)}
              className={`input font-mono text-sm w-full h-80 resize-none ${
                parseError ? 'border-[var(--color-danger)]' : ''
              }`}
              spellCheck={false}
            />
            {parseError && (
              <p className="text-xs text-[var(--color-danger)] mt-1">
                {parseError}
              </p>
            )}
          </div>

          {/* Help text */}
          <p className="text-xs text-[var(--color-text-secondary)]">
            Edit the JSON to modify the feature's name, description, category, priority, or steps.
          </p>
        </div>

        {/* Actions */}
        <div className="p-4 border-t border-[var(--color-border)] bg-[var(--color-bg)] flex gap-3">
          <button
            onClick={handleSave}
            disabled={updateFeature.isPending || !!parseError}
            className="btn btn-primary flex-1"
          >
            {updateFeature.isPending ? (
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
            disabled={updateFeature.isPending}
            className="btn btn-ghost"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
