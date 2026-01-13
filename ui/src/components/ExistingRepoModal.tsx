/**
 * Existing Repo Modal Component
 *
 * Multi-step modal for adding existing repositories:
 * 1. Choose source type (Git URL or Local Folder)
 * 2a. If Git URL: Enter URL + select destination folder
 * 2b. If Local Folder: Select the folder
 * 3. Enter project name (auto-suggested)
 * 4. Processing (clone, init beads, scaffold)
 * 5. Complete
 */

import { useState } from 'react'
import { X, GitBranch, Folder, ArrowRight, ArrowLeft, Loader2, CheckCircle2, AlertCircle } from 'lucide-react'
import { FolderBrowser } from './FolderBrowser'
import { addExistingRepo } from '../lib/api'

type Step = 'source' | 'git_url' | 'local_folder' | 'name' | 'processing' | 'complete' | 'error'
type SourceType = 'git_url' | 'local_folder'

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
  const [step, setStep] = useState<Step>('source')
  const [sourceType, setSourceType] = useState<SourceType | null>(null)
  const [gitUrl, setGitUrl] = useState('')
  const [selectedPath, setSelectedPath] = useState<string | null>(null)
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

  const extractFolderName = (path: string): string => {
    // Extract folder name from path
    const parts = path.split(/[/\\]/).filter(Boolean)
    return parts[parts.length - 1] || ''
  }

  const handleSourceSelect = (type: SourceType) => {
    setSourceType(type)
    setError(null)
    if (type === 'git_url') {
      setStep('git_url')
    } else {
      setStep('local_folder')
    }
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
    // Now need to select destination folder
    setStep('local_folder')
  }

  const handleFolderSelect = (path: string) => {
    setSelectedPath(path)
    // Auto-suggest project name
    if (sourceType === 'git_url') {
      // For git clone, the repo will be cloned into this folder
      // Suggest name from git URL
      const suggestedName = extractRepoName(gitUrl)
      setProjectName(suggestedName)
      // Full path will be path + repo name
      setSelectedPath(`${path}/${suggestedName}`)
    } else {
      // For local folder, suggest name from folder
      const suggestedName = extractFolderName(path)
      setProjectName(suggestedName)
    }
    setStep('name')
  }

  const handleFolderCancel = () => {
    if (sourceType === 'git_url') {
      setStep('git_url')
    } else {
      setStep('source')
    }
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
      if (sourceType === 'git_url') {
        setProcessingStatus('Cloning repository...')
      } else {
        setProcessingStatus('Checking folder...')
      }

      // Call API
      await addExistingRepo({
        name: trimmed,
        source_type: sourceType!,
        git_url: sourceType === 'git_url' ? gitUrl : undefined,
        path: selectedPath!,
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
    setStep('source')
    setSourceType(null)
    setGitUrl('')
    setSelectedPath(null)
    setProjectName('')
    setError(null)
    setProcessingStatus('')
    onClose()
  }

  const handleBack = () => {
    setError(null)
    if (step === 'git_url') {
      setStep('source')
      setGitUrl('')
    } else if (step === 'local_folder') {
      if (sourceType === 'git_url') {
        setStep('git_url')
      } else {
        setStep('source')
      }
      setSelectedPath(null)
    } else if (step === 'name') {
      setStep('local_folder')
      setProjectName('')
    } else if (step === 'error') {
      setStep('name')
    }
  }

  // Folder browser step uses larger modal
  if (step === 'local_folder') {
    return (
      <div className="modal-backdrop" onClick={handleClose}>
        <div
          className="modal w-full max-w-3xl max-h-[85vh] flex flex-col"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
            <div className="flex items-center gap-3">
              <Folder size={24} className="text-[var(--color-accent)]" />
              <div>
                <h2 className="font-medium text-xl text-[var(--color-text)]">
                  {sourceType === 'git_url' ? 'Select Clone Destination' : 'Select Repository Folder'}
                </h2>
                <p className="text-sm text-[var(--color-text-secondary)]">
                  {sourceType === 'git_url'
                    ? 'Choose where to clone the repository'
                    : 'Select the folder containing your existing repository'}
                </p>
              </div>
            </div>
            <button onClick={handleClose} className="btn btn-ghost p-2">
              <X size={20} />
            </button>
          </div>

          {/* Folder Browser */}
          <div className="flex-1 overflow-hidden">
            <FolderBrowser
              onSelect={handleFolderSelect}
              onCancel={handleFolderCancel}
            />
          </div>
        </div>
      </div>
    )
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
              {step === 'source' && 'Add Existing Repository'}
              {step === 'git_url' && 'Enter Git URL'}
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
          {/* Step 1: Source Type */}
          {step === 'source' && (
            <div>
              <p className="text-[var(--color-text-secondary)] mb-6">
                How would you like to add your repository?
              </p>

              <div className="space-y-4">
                {/* Git URL option */}
                <button
                  onClick={() => handleSourceSelect('git_url')}
                  className={`
                    w-full text-left p-4
                    border border-[var(--color-border)]
                    bg-[var(--color-bg)]
                    rounded-lg
                    hover:bg-[var(--color-bg-elevated)]
                    hover:border-[var(--color-accent)]
                    transition-all duration-150
                  `}
                >
                  <div className="flex items-start gap-4">
                    <div className="p-2 bg-[var(--color-accent)] rounded-md">
                      <GitBranch size={24} className="text-[var(--color-text-inverse)]" />
                    </div>
                    <div className="flex-1">
                      <span className="font-medium text-lg text-[var(--color-text)]">
                        Clone from Git URL
                      </span>
                      <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                        Clone a repository from GitHub, GitLab, or any Git remote.
                      </p>
                    </div>
                  </div>
                </button>

                {/* Local folder option */}
                <button
                  onClick={() => handleSourceSelect('local_folder')}
                  className={`
                    w-full text-left p-4
                    border border-[var(--color-border)]
                    bg-[var(--color-bg)]
                    rounded-lg
                    hover:bg-[var(--color-bg-elevated)]
                    hover:border-[var(--color-accent)]
                    transition-all duration-150
                  `}
                >
                  <div className="flex items-start gap-4">
                    <div className="p-2 bg-[var(--color-text-secondary)] rounded-md">
                      <Folder size={24} className="text-[var(--color-text-inverse)]" />
                    </div>
                    <div className="flex-1">
                      <span className="font-medium text-lg text-[var(--color-text)]">
                        Select Local Folder
                      </span>
                      <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                        Add a repository that's already on your machine.
                      </p>
                    </div>
                  </div>
                </button>
              </div>
            </div>
          )}

          {/* Step 2a: Git URL */}
          {step === 'git_url' && (
            <form onSubmit={handleGitUrlSubmit}>
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
                  disabled={!gitUrl.trim()}
                >
                  Next
                  <ArrowRight size={16} />
                </button>
              </div>
            </form>
          )}

          {/* Step 3: Project Name */}
          {step === 'name' && (
            <form onSubmit={handleNameSubmit}>
              <div className="mb-4">
                <div className="text-sm text-[var(--color-text-secondary)] mb-4 p-3 bg-[var(--color-bg-elevated)] rounded-md">
                  <div className="font-medium text-[var(--color-text)]">Selected:</div>
                  <code className="text-xs">{selectedPath}</code>
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
                  <ArrowRight size={16} />
                </button>
              </div>
            </form>
          )}

          {/* Step 4: Processing */}
          {step === 'processing' && (
            <div className="text-center py-8">
              <Loader2 size={48} className="animate-spin mx-auto mb-4 text-[var(--color-accent)]" />
              <p className="text-[var(--color-text)]">{processingStatus}</p>
            </div>
          )}

          {/* Step 5: Complete */}
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
