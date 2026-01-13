/**
 * Incomplete Project Modal Component
 *
 * Shows when selecting a project with an incomplete setup wizard.
 * Offers options to resume, start fresh, or cancel.
 */

import { useState, useEffect } from 'react'
import { X, AlertCircle, Play, RefreshCw, Loader2 } from 'lucide-react'
import { getWizardStatus, deleteWizardStatus } from '../lib/api'
import type { WizardStatus, ProjectSummary } from '../lib/types'

interface IncompleteProjectModalProps {
  isOpen: boolean
  project: ProjectSummary | null
  onClose: () => void
  onResume: (projectName: string, wizardStatus: WizardStatus) => void
  onStartFresh: (projectName: string) => void
}

export function IncompleteProjectModal({
  isOpen,
  project,
  onClose,
  onResume,
  onStartFresh,
}: IncompleteProjectModalProps) {
  const [wizardStatus, setWizardStatus] = useState<WizardStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    if (isOpen && project) {
      setLoading(true)
      setError(null)
      getWizardStatus(project.name)
        .then((status) => {
          setWizardStatus(status)
          setLoading(false)
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : 'Failed to load wizard status')
          setLoading(false)
        })
    } else {
      setWizardStatus(null)
      setError(null)
    }
  }, [isOpen, project])

  if (!isOpen || !project) return null

  const handleResume = () => {
    if (wizardStatus) {
      onResume(project.name, wizardStatus)
    }
  }

  const handleStartFresh = async () => {
    setDeleting(true)
    try {
      await deleteWizardStatus(project.name)
      onStartFresh(project.name)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to clear wizard status')
      setDeleting(false)
    }
  }

  const getStepDescription = (step: string): string => {
    switch (step) {
      case 'name':
        return 'entering project name'
      case 'folder':
        return 'selecting project folder'
      case 'method':
        return 'choosing setup method'
      case 'chat':
        return 'creating spec with Claude'
      default:
        return step
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
          <div className="flex items-center gap-2">
            <AlertCircle size={20} className="text-[var(--color-warning)]" />
            <h2 className="font-medium text-lg text-[var(--color-text)]">
              Incomplete Setup
            </h2>
          </div>
          <button
            onClick={onClose}
            className="btn btn-ghost p-2"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {loading ? (
            <div className="flex items-center justify-center gap-2 py-8 text-[var(--color-text-secondary)]">
              <Loader2 size={20} className="animate-spin" />
              <span>Loading wizard status...</span>
            </div>
          ) : error ? (
            <div className="text-center py-4">
              <p className="text-[var(--color-danger)] mb-4">{error}</p>
              <button onClick={onClose} className="btn btn-secondary">
                Close
              </button>
            </div>
          ) : (
            <>
              <p className="text-[var(--color-text-secondary)] mb-4">
                The project <span className="font-medium text-[var(--color-text)]">{project.name}</span> has an incomplete setup.
              </p>

              {wizardStatus && (
                <div className="mb-6 p-3 bg-[var(--color-bg-elevated)] rounded-lg border border-[var(--color-border)]">
                  <p className="text-sm text-[var(--color-text-secondary)]">
                    Last step: <span className="font-medium text-[var(--color-text)]">{getStepDescription(wizardStatus.step)}</span>
                  </p>
                  {wizardStatus.spec_method && (
                    <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                      Method: <span className="font-medium text-[var(--color-text)]">{wizardStatus.spec_method === 'claude' ? 'Create with Claude' : 'Manual'}</span>
                    </p>
                  )}
                  {wizardStatus.chat_messages.length > 0 && (
                    <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                      Chat messages: <span className="font-medium text-[var(--color-text)]">{wizardStatus.chat_messages.length}</span>
                    </p>
                  )}
                </div>
              )}

              <div className="space-y-3">
                <button
                  onClick={handleResume}
                  disabled={!wizardStatus || deleting}
                  className="w-full btn btn-primary justify-center"
                >
                  <Play size={16} />
                  Resume Setup
                </button>

                <button
                  onClick={handleStartFresh}
                  disabled={deleting}
                  className="w-full btn btn-secondary justify-center"
                >
                  {deleting ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <RefreshCw size={16} />
                  )}
                  Start Fresh
                </button>

                <button
                  onClick={onClose}
                  disabled={deleting}
                  className="w-full btn btn-ghost justify-center"
                >
                  Cancel
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
