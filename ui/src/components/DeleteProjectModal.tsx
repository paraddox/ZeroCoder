/**
 * Delete Project Modal Component
 *
 * Confirmation modal for deleting a project. User must type the project
 * name exactly to enable the delete button (GitHub-style confirmation).
 */

import { useState } from 'react'
import { X, AlertTriangle, Trash2, Loader2 } from 'lucide-react'
import { deleteProject } from '../lib/api'
import type { ProjectSummary } from '../lib/types'

interface DeleteProjectModalProps {
  isOpen: boolean
  project: ProjectSummary | null
  onClose: () => void
  onDeleted: () => void
}

export function DeleteProjectModal({
  isOpen,
  project,
  onClose,
  onDeleted,
}: DeleteProjectModalProps) {
  const [confirmName, setConfirmName] = useState('')
  const [isDeleting, setIsDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!isOpen || !project) return null

  const nameMatches = confirmName === project.name
  const canDelete = nameMatches && !isDeleting

  const handleDelete = async () => {
    if (!canDelete) return

    setIsDeleting(true)
    setError(null)

    try {
      await deleteProject(project.name, true) // true = delete files
      setConfirmName('')
      onDeleted()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete project')
      setIsDeleting(false)
    }
  }

  const handleClose = () => {
    if (isDeleting) return // Prevent closing during deletion
    setConfirmName('')
    setError(null)
    onClose()
  }

  return (
    <div className="modal-backdrop" onClick={handleClose}>
      <div
        className="modal w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
          <div className="flex items-center gap-2">
            <AlertTriangle size={20} className="text-[var(--color-danger)]" />
            <h2 className="font-medium text-lg text-[var(--color-text)]">
              Delete Project
            </h2>
          </div>
          <button
            onClick={handleClose}
            disabled={isDeleting}
            className="btn btn-ghost p-2"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          <p className="text-[var(--color-text-secondary)] mb-4">
            This action <span className="font-semibold text-[var(--color-danger)]">cannot be undone</span>. This will permanently delete:
          </p>

          <ul className="list-disc list-inside text-sm text-[var(--color-text-secondary)] mb-4 space-y-1">
            <li>Project folder and all files</li>
            <li>Feature tracking data</li>
            <li>All project configuration</li>
          </ul>

          <div className="mb-4 p-3 bg-[var(--color-bg-elevated)] rounded-lg border border-[var(--color-border)]">
            <p className="text-sm text-[var(--color-text-secondary)]">
              Project: <span className="font-medium text-[var(--color-text)]">{project.name}</span>
            </p>
            <p className="text-sm text-[var(--color-text-secondary)] mt-1 break-all">
              Path: <span className="font-mono text-xs">{project.path}</span>
            </p>
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium mb-2 text-[var(--color-text)]">
              Type <span className="font-mono bg-[var(--color-bg-elevated)] px-1.5 py-0.5 rounded">{project.name}</span> to confirm:
            </label>
            <input
              type="text"
              value={confirmName}
              onChange={(e) => setConfirmName(e.target.value)}
              placeholder={project.name}
              disabled={isDeleting}
              className="input"
              autoFocus
            />
          </div>

          {error && (
            <div className="mb-4 p-3 bg-[var(--color-danger)] text-[var(--color-text-inverse)] text-sm rounded-md">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-3">
            <button
              onClick={handleClose}
              disabled={isDeleting}
              className="btn btn-ghost"
            >
              Cancel
            </button>
            <button
              onClick={handleDelete}
              disabled={!canDelete}
              className="btn btn-danger"
            >
              {isDeleting ? (
                <>
                  <Loader2 size={16} className="animate-spin" />
                  Deleting...
                </>
              ) : (
                <>
                  <Trash2 size={16} />
                  Delete Project
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
