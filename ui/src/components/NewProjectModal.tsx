/**
 * New Project Modal Component
 *
 * Two flows:
 * 1. New Project: mode → details (name + git URL) → method (Claude/manual) → wizard
 * 2. Existing Project: mode → details (name + git URL) → done
 */

import { useState, useEffect, useCallback } from 'react'
import { X, Bot, FileEdit, ArrowRight, ArrowLeft, Loader2, CheckCircle2, GitBranch, Plus, FolderGit2 } from 'lucide-react'
import { useCreateProject, useAddExistingRepo } from '../hooks/useProjects'
import { SpecCreationChat } from './SpecCreationChat'
import { startAgent, updateWizardStatus, deleteWizardStatus } from '../lib/api'
import type { WizardStatus, WizardStep, SpecMethod as SpecMethodType } from '../lib/types'

type InitializerStatus = 'idle' | 'starting' | 'error'
type ProjectMode = 'new' | 'existing'
type Step = 'mode' | 'details' | 'method' | 'chat' | 'complete'
type SpecMethod = 'claude' | 'manual'

interface NewProjectModalProps {
  isOpen: boolean
  onClose: () => void
  onProjectCreated: (projectName: string) => void
  // For resuming an interrupted wizard
  resumeProjectName?: string
  resumeState?: WizardStatus
}

export function NewProjectModal({
  isOpen,
  onClose,
  onProjectCreated,
  resumeProjectName,
  resumeState,
}: NewProjectModalProps) {
  const [step, setStep] = useState<Step>('mode')
  const [mode, setMode] = useState<ProjectMode>('new')
  const [projectName, setProjectName] = useState('')
  const [gitUrl, setGitUrl] = useState('')
  const [specMethod, setSpecMethod] = useState<SpecMethod | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [initializerStatus, setInitializerStatus] = useState<InitializerStatus>('idle')
  const [initializerError, setInitializerError] = useState<string | null>(null)
  const [yoloModeSelected, setYoloModeSelected] = useState(false)
  const [isResuming, setIsResuming] = useState(false)

  const createProject = useCreateProject()
  const addExistingRepo = useAddExistingRepo()

  // Initialize state from resume data
  useEffect(() => {
    if (isOpen && resumeProjectName && resumeState) {
      setIsResuming(true)
      setProjectName(resumeProjectName)
      // Map wizard step to modal step
      const stepMap: Record<WizardStep, Step> = {
        'mode': 'mode',
        'details': 'details',
        'method': 'method',
        'chat': 'chat',
      }
      setStep(stepMap[resumeState.step] || 'method')
      if (resumeState.spec_method) {
        setSpecMethod(resumeState.spec_method)
      }
    } else if (isOpen && !resumeProjectName) {
      setIsResuming(false)
    }
  }, [isOpen, resumeProjectName, resumeState])

  // Persist wizard state when step changes
  const persistWizardState = useCallback(async (newStep: Step, method?: SpecMethod | null) => {
    if (!projectName.trim()) return
    // Don't persist 'complete' step
    if (newStep === 'complete') return

    try {
      const wizardStep: WizardStep = newStep === 'chat' ? 'chat' : newStep as WizardStep
      await updateWizardStatus(projectName.trim(), {
        step: wizardStep,
        spec_method: (method ?? specMethod) as SpecMethodType | null,
        started_at: new Date().toISOString(),
        chat_messages: [], // Chat messages are handled separately by SpecCreationChat
      })
    } catch (err) {
      // Silently fail - don't block the UI for persistence errors
      console.error('Failed to persist wizard state:', err)
    }
  }, [projectName, specMethod])

  if (!isOpen) return null

  const handleModeSelect = (selectedMode: ProjectMode) => {
    setMode(selectedMode)
    setStep('details')
  }

  const handleDetailsSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const trimmedName = projectName.trim()
    const trimmedUrl = gitUrl.trim()

    if (!trimmedName) {
      setError('Please enter a project name')
      return
    }

    if (!/^[a-zA-Z0-9_-]+$/.test(trimmedName)) {
      setError('Project name can only contain letters, numbers, hyphens, and underscores')
      return
    }

    if (!trimmedUrl) {
      setError('Please enter a git repository URL')
      return
    }

    // Basic git URL validation
    if (!trimmedUrl.startsWith('git@') && !trimmedUrl.startsWith('https://') && !trimmedUrl.startsWith('http://')) {
      setError('Please enter a valid git URL (SSH or HTTPS)')
      return
    }

    setError(null)

    if (mode === 'existing') {
      // Create project with existing repo (is_new = false)
      try {
        await addExistingRepo.mutateAsync({
          name: trimmedName,
          gitUrl: trimmedUrl,
        })
        setStep('complete')
        setTimeout(() => {
          onProjectCreated(trimmedName)
          handleClose()
        }, 1500)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to add project')
      }
    } else {
      // New project - go to method selection
      setStep('method')
      await persistWizardState('method')
    }
  }

  const handleMethodSelect = async (method: SpecMethod) => {
    setSpecMethod(method)

    // For resuming, we may not have gitUrl but the project already exists
    if (!gitUrl.trim() && !isResuming) {
      setError('Please enter a git repository URL')
      setStep('details')
      return
    }

    if (method === 'manual') {
      // Create project immediately with manual method (skip if resuming)
      try {
        if (!isResuming) {
          const project = await createProject.mutateAsync({
            name: projectName.trim(),
            gitUrl: gitUrl.trim(),
            isNew: true,
          })
          // Clean up wizard status on completion
          await deleteWizardStatus(project.name).catch(() => {})
        }
        setStep('complete')
        setTimeout(() => {
          onProjectCreated(projectName.trim())
          handleClose()
        }, 1500)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to create project')
      }
    } else {
      // Create project then show chat (skip creation if resuming)
      try {
        if (!isResuming) {
          await createProject.mutateAsync({
            name: projectName.trim(),
            gitUrl: gitUrl.trim(),
            isNew: true,
          })
        }
        setStep('chat')
        await persistWizardState('chat', 'claude')
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to create project')
      }
    }
  }

  const handleSpecComplete = async (_specPath: string, yoloMode: boolean = false) => {
    // Save yoloMode for retry
    setYoloModeSelected(yoloMode)
    // Auto-start the initializer agent
    setInitializerStatus('starting')
    try {
      await startAgent(projectName.trim(), yoloMode)
      // Clean up wizard status on successful completion
      await deleteWizardStatus(projectName.trim()).catch(() => {})
      // Success - navigate to project
      setStep('complete')
      setTimeout(() => {
        onProjectCreated(projectName.trim())
        handleClose()
      }, 1500)
    } catch (err) {
      setInitializerStatus('error')
      setInitializerError(err instanceof Error ? err.message : 'Failed to start agent')
    }
  }

  const handleRetryInitializer = () => {
    setInitializerError(null)
    setInitializerStatus('idle')
    handleSpecComplete('', yoloModeSelected)
  }

  const handleChatCancel = () => {
    // Go back to method selection but keep the project
    setStep('method')
    setSpecMethod(null)
  }

  const handleExitToProject = async () => {
    // Exit chat and go directly to project - user can start agent manually
    // Clean up wizard status since user is exiting
    await deleteWizardStatus(projectName.trim()).catch(() => {})
    onProjectCreated(projectName.trim())
    handleClose()
  }

  const handleClose = () => {
    setStep('mode')
    setMode('new')
    setProjectName('')
    setGitUrl('')
    setSpecMethod(null)
    setError(null)
    setInitializerStatus('idle')
    setInitializerError(null)
    setYoloModeSelected(false)
    setIsResuming(false)
    onClose()
  }

  const handleBack = () => {
    if (step === 'method') {
      setStep('details')
      setSpecMethod(null)
    } else if (step === 'details') {
      setStep('mode')
      setProjectName('')
      setGitUrl('')
    }
  }

  // Full-screen chat view
  if (step === 'chat') {
    return (
      <div className="fixed inset-0 z-50 bg-[var(--color-bg)]">
        <SpecCreationChat
          projectName={projectName.trim()}
          onComplete={handleSpecComplete}
          onCancel={handleChatCancel}
          onExitToProject={handleExitToProject}
          initializerStatus={initializerStatus}
          initializerError={initializerError}
          onRetryInitializer={handleRetryInitializer}
        />
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
          <h2 className="font-medium text-xl text-[var(--color-text)]">
            {step === 'mode' && 'Add Project'}
            {step === 'details' && (mode === 'new' ? 'New Project' : 'Add Existing Project')}
            {step === 'method' && 'Choose Setup Method'}
            {step === 'complete' && 'Project Added!'}
          </h2>
          <button
            onClick={handleClose}
            className="btn btn-ghost p-2"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Step 1: Mode Selection */}
          {step === 'mode' && (
            <div>
              <p className="text-[var(--color-text-secondary)] mb-6">
                What would you like to do?
              </p>

              <div className="space-y-4">
                {/* New Project option */}
                <button
                  onClick={() => handleModeSelect('new')}
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
                      <Plus size={24} className="text-[var(--color-text-inverse)]" />
                    </div>
                    <div className="flex-1">
                      <span className="font-medium text-lg text-[var(--color-text)]">New Project</span>
                      <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                        Create a new application from scratch with AI-assisted specification.
                      </p>
                    </div>
                  </div>
                </button>

                {/* Existing Project option */}
                <button
                  onClick={() => handleModeSelect('existing')}
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
                    <div className="p-2 bg-[var(--color-warning)] rounded-md">
                      <FolderGit2 size={24} className="text-[var(--color-text)]" />
                    </div>
                    <div className="flex-1">
                      <span className="font-medium text-lg text-[var(--color-text)]">Existing Project</span>
                      <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                        Add an existing repository that already has beads issues configured.
                      </p>
                    </div>
                  </div>
                </button>
              </div>
            </div>
          )}

          {/* Step 2: Project Details (Name + Git URL) */}
          {step === 'details' && (
            <form onSubmit={handleDetailsSubmit}>
              <div className="mb-4">
                <label className="block font-medium mb-2 text-[var(--color-text)]">
                  Project Name
                </label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="my-awesome-app"
                  className="input"
                  autoFocus
                />
                <p className="text-sm text-[var(--color-text-secondary)] mt-2">
                  Use letters, numbers, hyphens, and underscores only.
                </p>
              </div>

              <div className="mb-6">
                <label className="block font-medium mb-2 text-[var(--color-text)]">
                  <span className="flex items-center gap-2">
                    <GitBranch size={16} />
                    Git Repository URL
                  </span>
                </label>
                <input
                  type="text"
                  value={gitUrl}
                  onChange={(e) => setGitUrl(e.target.value)}
                  placeholder="git@github.com:user/repo.git"
                  className="input"
                />
                <p className="text-sm text-[var(--color-text-secondary)] mt-2">
                  SSH (git@) or HTTPS URL to your repository
                </p>
              </div>

              {error && (
                <div className="mb-4 p-3 bg-[var(--color-danger)] text-[var(--color-text-inverse)] text-sm rounded-md border border-[var(--color-border)]">
                  {error}
                </div>
              )}

              {(createProject.isPending || addExistingRepo.isPending) && (
                <div className="mb-4 flex items-center justify-center gap-2 text-[var(--color-text-secondary)]">
                  <Loader2 size={16} className="animate-spin" />
                  <span>{mode === 'existing' ? 'Adding project...' : 'Creating project...'}</span>
                </div>
              )}

              <div className="flex justify-between">
                <button
                  type="button"
                  onClick={handleBack}
                  className="btn btn-ghost"
                  disabled={createProject.isPending || addExistingRepo.isPending}
                >
                  <ArrowLeft size={16} />
                  Back
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={!projectName.trim() || !gitUrl.trim() || createProject.isPending || addExistingRepo.isPending}
                >
                  {mode === 'new' ? 'Next' : 'Add Project'}
                  <ArrowRight size={16} />
                </button>
              </div>
            </form>
          )}

          {/* Step 3: Spec Method (New projects only) */}
          {step === 'method' && (
            <div>
              <p className="text-[var(--color-text-secondary)] mb-6">
                How would you like to define your project?
              </p>

              <div className="space-y-4">
                {/* Claude option */}
                <button
                  onClick={() => handleMethodSelect('claude')}
                  disabled={createProject.isPending}
                  className={`
                    w-full text-left p-4
                    border border-[var(--color-border)]
                    bg-[var(--color-bg)]
                    rounded-lg
                    hover:bg-[var(--color-bg-elevated)]
                    hover:border-[var(--color-accent)]
                    transition-all duration-150
                    disabled:opacity-50 disabled:cursor-not-allowed
                  `}
                >
                  <div className="flex items-start gap-4">
                    <div className="p-2 bg-[var(--color-accent)] rounded-md">
                      <Bot size={24} className="text-[var(--color-text-inverse)]" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-lg text-[var(--color-text)]">Create with Claude</span>
                        <span className="badge bg-[var(--color-done)] text-[var(--color-text-inverse)] text-xs">
                          Recommended
                        </span>
                      </div>
                      <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                        Interactive conversation to define features and generate your app specification automatically.
                      </p>
                    </div>
                  </div>
                </button>

                {/* Manual option */}
                <button
                  onClick={() => handleMethodSelect('manual')}
                  disabled={createProject.isPending}
                  className={`
                    w-full text-left p-4
                    border border-[var(--color-border)]
                    bg-[var(--color-bg)]
                    rounded-lg
                    hover:bg-[var(--color-bg-elevated)]
                    hover:border-[var(--color-accent)]
                    transition-all duration-150
                    disabled:opacity-50 disabled:cursor-not-allowed
                  `}
                >
                  <div className="flex items-start gap-4">
                    <div className="p-2 bg-[var(--color-warning)] rounded-md">
                      <FileEdit size={24} className="text-[var(--color-text)]" />
                    </div>
                    <div className="flex-1">
                      <span className="font-medium text-lg text-[var(--color-text)]">Edit Templates Manually</span>
                      <p className="text-sm text-[var(--color-text-secondary)] mt-1">
                        Edit the template files directly. Best for developers who want full control.
                      </p>
                    </div>
                  </div>
                </button>
              </div>

              {error && (
                <div className="mt-4 p-3 bg-[var(--color-danger)] text-[var(--color-text-inverse)] text-sm rounded-md border border-[var(--color-border)]">
                  {error}
                </div>
              )}

              {createProject.isPending && (
                <div className="mt-4 flex items-center justify-center gap-2 text-[var(--color-text-secondary)]">
                  <Loader2 size={16} className="animate-spin" />
                  <span>Creating project...</span>
                </div>
              )}

              <div className="flex justify-start mt-6">
                <button
                  onClick={handleBack}
                  className="btn btn-ghost"
                  disabled={createProject.isPending}
                >
                  <ArrowLeft size={16} />
                  Back
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Complete */}
          {step === 'complete' && (
            <div className="text-center py-8">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-[var(--color-done)] rounded-full mb-4">
                <CheckCircle2 size={32} className="text-[var(--color-text-inverse)]" />
              </div>
              <h3 className="font-medium text-xl mb-2 text-[var(--color-text)]">
                {projectName}
              </h3>
              <p className="text-[var(--color-text-secondary)]">
                {mode === 'existing'
                  ? 'Your project has been added successfully!'
                  : 'Your project has been created successfully!'}
              </p>
              <div className="mt-4 flex items-center justify-center gap-2">
                <Loader2 size={16} className="animate-spin" />
                <span className="text-sm text-[var(--color-text-secondary)]">Redirecting...</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
