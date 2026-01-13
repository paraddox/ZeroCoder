/**
 * New Project Modal Component
 *
 * Multi-step modal for creating new projects:
 * 1. Enter project name
 * 2. Select project folder
 * 3. Choose spec method (Claude or manual)
 * 4a. If Claude: Show SpecCreationChat
 * 4b. If manual: Create project and close
 *
 * Also supports resuming an interrupted wizard via resumeState prop.
 */

import { useState, useEffect, useCallback } from 'react'
import { X, Bot, FileEdit, ArrowRight, ArrowLeft, Loader2, CheckCircle2, Folder } from 'lucide-react'
import { useCreateProject } from '../hooks/useProjects'
import { SpecCreationChat } from './SpecCreationChat'
import { FolderBrowser } from './FolderBrowser'
import { startAgent, updateWizardStatus, deleteWizardStatus } from '../lib/api'
import type { WizardStatus, WizardStep, SpecMethod as SpecMethodType } from '../lib/types'

type InitializerStatus = 'idle' | 'starting' | 'error'

type Step = 'name' | 'folder' | 'method' | 'chat' | 'complete'
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
  const [step, setStep] = useState<Step>('name')
  const [projectName, setProjectName] = useState('')
  const [projectPath, setProjectPath] = useState<string | null>(null)
  const [specMethod, setSpecMethod] = useState<SpecMethod | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [initializerStatus, setInitializerStatus] = useState<InitializerStatus>('idle')
  const [initializerError, setInitializerError] = useState<string | null>(null)
  const [yoloModeSelected, setYoloModeSelected] = useState(false)
  const [isResuming, setIsResuming] = useState(false)

  const createProject = useCreateProject()

  // Initialize state from resume data
  useEffect(() => {
    if (isOpen && resumeProjectName && resumeState) {
      setIsResuming(true)
      setProjectName(resumeProjectName)
      // Map wizard step to modal step
      const stepMap: Record<WizardStep, Step> = {
        'name': 'name',
        'folder': 'folder',
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
      const wizardStep: WizardStep = newStep === 'chat' ? 'chat' : newStep
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
    setStep('folder')
    await persistWizardState('folder')
  }

  const handleFolderSelect = async (path: string) => {
    // Append project name to the selected path
    const fullPath = path.endsWith('/') ? `${path}${projectName.trim()}` : `${path}/${projectName.trim()}`
    setProjectPath(fullPath)
    setStep('method')
    await persistWizardState('method')
  }

  const handleFolderCancel = () => {
    setStep('name')
  }

  const handleMethodSelect = async (method: SpecMethod) => {
    setSpecMethod(method)

    // For resuming, we may not have projectPath but the project already exists
    if (!projectPath && !isResuming) {
      setError('Please select a project folder first')
      setStep('folder')
      return
    }

    if (method === 'manual') {
      // Create project immediately with manual method (skip if resuming)
      try {
        if (!isResuming && projectPath) {
          const project = await createProject.mutateAsync({
            name: projectName.trim(),
            path: projectPath,
            specMethod: 'manual',
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
        if (!isResuming && projectPath) {
          await createProject.mutateAsync({
            name: projectName.trim(),
            path: projectPath,
            specMethod: 'claude',
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
    setStep('name')
    setProjectName('')
    setProjectPath(null)
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
      setStep('folder')
      setSpecMethod(null)
    } else if (step === 'folder') {
      setStep('name')
      setProjectPath(null)
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

  // Folder step uses larger modal
  if (step === 'folder') {
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
                  Select Project Location
                </h2>
                <p className="text-sm text-[var(--color-text-secondary)]">
                  A folder named <span className="font-medium font-mono">{projectName}</span> will be created inside the selected directory
                </p>
              </div>
            </div>
            <button
              onClick={handleClose}
              className="btn btn-ghost p-2"
            >
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
          <h2 className="font-medium text-xl text-[var(--color-text)]">
            {step === 'name' && 'Create New Project'}
            {step === 'method' && 'Choose Setup Method'}
            {step === 'complete' && 'Project Created!'}
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
          {/* Step 1: Project Name */}
          {step === 'name' && (
            <form onSubmit={handleNameSubmit}>
              <div className="mb-6">
                <label className="block font-medium mb-2 text-[var(--color-text)]">
                  Project Name
                </label>
                <input
                  type="text"
                  value={projectName}
                  onChange={(e) => setProjectName(e.target.value)}
                  placeholder="my-awesome-app"
                  className="input"
                  pattern="^[a-zA-Z0-9_-]+$"
                  autoFocus
                />
                <p className="text-sm text-[var(--color-text-secondary)] mt-2">
                  Use letters, numbers, hyphens, and underscores only.
                </p>
              </div>

              {error && (
                <div className="mb-4 p-3 bg-[var(--color-danger)] text-[var(--color-text-inverse)] text-sm rounded-md border border-[var(--color-border)]">
                  {error}
                </div>
              )}

              <div className="flex justify-end">
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={!projectName.trim()}
                >
                  Next
                  <ArrowRight size={16} />
                </button>
              </div>
            </form>
          )}

          {/* Step 2: Spec Method */}
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

          {/* Step 3: Complete */}
          {step === 'complete' && (
            <div className="text-center py-8">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-[var(--color-done)] rounded-full mb-4">
                <CheckCircle2 size={32} className="text-[var(--color-text-inverse)]" />
              </div>
              <h3 className="font-medium text-xl mb-2 text-[var(--color-text)]">
                {projectName}
              </h3>
              <p className="text-[var(--color-text-secondary)]">
                Your project has been created successfully!
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
