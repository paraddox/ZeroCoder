/**
 * Existing Repo Modal Component
 *
 * Modal for adding existing repositories by Git URL.
 * The repository will be cloned to the default projects directory.
 */

import { useState } from 'react'
import { X, GitBranch, ArrowLeft, Loader2, CheckCircle2, AlertCircle } from 'lucide-react'
import { addExistingRepo } from '../lib/api'

type Step = 'git_url' | 'name' | 'processing' | 'complete' | 'error'

interface ExistingRepoModalProps {
  isOpen: boolean
  onClose: () => void
  onProjectAdded: (projectName: string) => void
}

export function ExistingRepoModal({
  isOpen,
  onClose,
  onProjectAdded,
}: ExistingRepoModalProps) {
  const [step, setStep] = useState<Step>('git_url')
  const [gitUrl, setGitUrl] = useState('')
  const [projectName, setProjectName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [processingStatus, setProcessingStatus] = useState('')

  if (!isOpen) return null

  const extractRepoName = (url: string): string => {
    // Extract repo name from git URL
    // https://github.com/user/repo.git -> repo
    // git@github.com:user/repo.git -> repo
    const match = url.match(/\/([^/]+?)(\.git)?$/) || url.match(/:([^/]+?)(\.git)?$/)
    return match ? match[1].replace('.git', '') : ''
  }

  const handleGitUrlSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!gitUrl.trim()) {
      setError('Please enter a Git URL')
      return
    }
    if (!gitUrl.startsWith('https://') && !gitUrl.startsWith('git@')) {
      setError('Git URL must start with https:// or git@')
      return
    }
    setError(null)
    // Auto-suggest project name from URL
    const suggestedName = extractRepoName(gitUrl)
    setProjectName(suggestedName)
    setStep('name')
  }

  const handleNameSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = projectName.trim()

    if (!trimmed) {
      setError('Please enter a project name')
      return
    }

    if (!/^[a-zA-Z0-9_-]+$/.test(trimmed)) {
      setError('Project name can only contain letters, numbers, hyphens, and underscores')
      return
    }

    setError(null)
    setStep('processing')

    try {
      setProcessingStatus('Cloning repository...')

      // Call API - only git_url mode supported now
      await addExistingRepo({
        name: trimmed,
        git_url: gitUrl,
      })

      setProcessingStatus('Project added successfully!')
      setStep('complete')

      // Auto-close after success
      setTimeout(() => {
        onProjectAdded(trimmed)
        handleClose()
      }, 1500)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add project')
      setStep('error')
    }
  }

  const handleClose = () => {
    setStep('git_url')
    setGitUrl('')
    setProjectName('')
    setError(null)
    setProcessingStatus('')
    onClose()
  }

  const handleBack = () => {
    setError(null)
    if (step === 'name') {
      setStep('git_url')
      setProjectName('')
    } else if (step === 'error') {
      setStep('name')
    }
  }

  return (
    <div className="modal-backdrop" onClick={handleClose}>
      <div
        className="modal w-full max-w-lg"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
          <div className="flex items-center gap-2">
            <GitBranch size={20} className="text-[var(--color-accent)]" />
            <h2 className="font-medium text-xl text-[var(--color-text)]">
              {step === 'git_url' && 'Clone Existing Repository'}
              {step === 'name' && 'Project Name'}
              {step === 'processing' && 'Adding Project...'}
              {step === 'complete' && 'Project Added!'}
              {step === 'error' && 'Error'}
            </h2>
          </div>
          <button onClick={handleClose} className="btn btn-ghost p-2">
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Step 1: Git URL */}
          {step === 'git_url' && (
            <form onSubmit={handleGitUrlSubmit}>
              <p className="text-[var(--color-text-secondary)] mb-6">
                Enter the Git URL of an existing repository to clone.
              </p>

              <div className="mb-6">
                <label className="block font-medium mb-2 text-[var(--color-text)]">
                  Repository URL
                </label>
                <input
                  type="text"
                  value={gitUrl}
                  onChange={(e) => setGitUrl(e.target.value)}
                  placeholder="https://github.com/user/repo.git"
                  className="input"
                  autoFocus
                />
                <p className="text-sm text-[var(--color-text-secondary)] mt-2">
                  HTTPS or SSH URL (git@...)
                </p>
              </div>

              {error && (
                <div className="mb-4 p-3 bg-red-50 text-red-700 text-sm rounded-md border border-red-200">
                  {error}
                </div>
              )}

              <div className="flex justify-end">
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={!gitUrl.trim()}
                >
                  Next
                </button>
              </div>
            </form>
          )}

          {/* Step 2: Project Name */}
          {step === 'name' && (
            <form onSubmit={handleNameSubmit}>
              <div className="mb-4">
                <div className="text-sm text-[var(--color-text-secondary)] mb-4 p-3 bg-[var(--color-bg-elevated)] rounded-md">
                  <div className="font-medium text-[var(--color-text)]">Repository:</div>
                  <code className="text-xs break-all">{gitUrl}</code>
                </div>

                <label className="block font-medium mb-2 text-[var(--color-text)]">
                  Project Name
                </label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="my-project"
                  className="input"
                  pattern="^[a-zA-Z0-9_-]+$"
                  autoFocus
                />
                <p className="text-sm text-[var(--color-text-secondary)] mt-2">
                  Used to identify this project in the UI.
                </p>
              </div>

              {error && (
                <div className="mb-4 p-3 bg-red-50 text-red-700 text-sm rounded-md border border-red-200">
                  {error}
                </div>
              )}

              <div className="flex justify-between">
                <button
                  type="button"
                  onClick={handleBack}
                  className="btn btn-ghost"
                >
                  <ArrowLeft size={16} />
                  Back
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={!projectName.trim()}
                >
                  Add Project
                </button>
              </div>
            </form>
          )}

          {/* Step 3: Processing */}
          {step === 'processing' && (
            <div className="text-center py-8">
              <Loader2 size={48} className="animate-spin mx-auto mb-4 text-[var(--color-accent)]" />
              <p className="text-[var(--color-text)]">{processingStatus}</p>
            </div>
          )}

          {/* Step 4: Complete */}
          {step === 'complete' && (
            <div className="text-center py-8">
              <CheckCircle2 size={48} className="mx-auto mb-4 text-[var(--color-done)]" />
              <p className="text-[var(--color-text)] font-medium">Project added successfully!</p>
              <p className="text-sm text-[var(--color-text-secondary)] mt-2">
                Redirecting to project...
              </p>
            </div>
          )}

          {/* Error state */}
          {step === 'error' && (
            <div className="text-center py-6">
              <AlertCircle size={48} className="mx-auto mb-4 text-red-500" />
              <p className="text-red-600 font-medium mb-2">Failed to add project</p>
              <p className="text-sm text-[var(--color-text-secondary)] mb-6">{error}</p>
              <div className="flex justify-center gap-3">
                <button onClick={handleBack} className="btn btn-ghost">
                  <ArrowLeft size={16} />
                  Back
                </button>
                <button onClick={handleClose} className="btn btn-primary">
                  Close
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
