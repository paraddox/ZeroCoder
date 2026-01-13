import { useState, useEffect, useCallback } from 'react'
import { useProjects, useFeatures, useAgentStatus, useReopenFeature } from './hooks/useProjects'
import { useProjectWebSocket } from './hooks/useWebSocket'
import { useFeatureSound } from './hooks/useFeatureSound'
import { useCelebration } from './hooks/useCelebration'
import { useTheme } from './hooks/useTheme'

const STORAGE_KEY = 'zerocoder-selected-project'
import { ProjectSelector } from './components/ProjectSelector'
import { KanbanBoard } from './components/KanbanBoard'
import { AgentControl } from './components/AgentControl'
import { ProgressDashboard } from './components/ProgressDashboard'
import { SetupWizard } from './components/SetupWizard'
import { AddFeatureForm } from './components/AddFeatureForm'
import { FeatureModal } from './components/FeatureModal'
import { FeatureEditModal } from './components/FeatureEditModal'
import { DebugLogViewer } from './components/DebugLogViewer'
import { AgentThought } from './components/AgentThought'
import { AssistantFAB } from './components/AssistantFAB'
import { AssistantPanel } from './components/AssistantPanel'
import { IncompleteProjectModal } from './components/IncompleteProjectModal'
import { NewProjectModal } from './components/NewProjectModal'
import { DeleteProjectModal } from './components/DeleteProjectModal'
import { Plus, Loader2, Trash2, Sun, Moon } from 'lucide-react'
import type { Feature, ProjectSummary, WizardStatus } from './lib/types'

function App() {
  // Initialize selected project from localStorage
  const [selectedProject, setSelectedProject] = useState<string | null>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY)
    } catch {
      return null
    }
  })
  const [showAddFeature, setShowAddFeature] = useState(false)
  const [selectedFeature, setSelectedFeature] = useState<Feature | null>(null)
  const [setupComplete, setSetupComplete] = useState(true) // Start optimistic
  const [debugOpen, setDebugOpen] = useState(false)
  const [debugPanelHeight, setDebugPanelHeight] = useState(288) // Default height
  const [assistantOpen, setAssistantOpen] = useState(false)

  // Incomplete project wizard resume state
  const [incompleteProject, setIncompleteProject] = useState<ProjectSummary | null>(null)
  const [showResumeWizard, setShowResumeWizard] = useState(false)
  const [resumeWizardState, setResumeWizardState] = useState<{
    projectName: string
    wizardStatus: WizardStatus
  } | null>(null)

  // Delete project modal state
  const [showDeleteModal, setShowDeleteModal] = useState(false)

  // Edit feature modal state
  const [editingFeature, setEditingFeature] = useState<Feature | null>(null)

  const { data: projects, isLoading: projectsLoading, refetch: refetchProjects } = useProjects()
  const { data: features } = useFeatures(selectedProject)
  const { data: agentStatusData } = useAgentStatus(selectedProject)
  const reopenFeature = useReopenFeature(selectedProject ?? '')
  const wsState = useProjectWebSocket(selectedProject)
  const { theme, toggleTheme } = useTheme()

  // Play sounds when features move between columns
  useFeatureSound(features)

  // Celebrate when all features are complete
  useCelebration(features, selectedProject)

  // Persist selected project to localStorage
  const handleSelectProject = useCallback((project: string | null) => {
    setSelectedProject(project)
    try {
      if (project) {
        localStorage.setItem(STORAGE_KEY, project)
      } else {
        localStorage.removeItem(STORAGE_KEY)
      }
    } catch {
      // localStorage not available
    }
  }, [])

  // Handle click on incomplete project in selector
  const handleIncompleteProjectClick = useCallback((project: ProjectSummary) => {
    setIncompleteProject(project)
  }, [])

  // Handle resume from incomplete project modal
  const handleResumeWizard = useCallback((projectName: string, wizardStatus: WizardStatus) => {
    setIncompleteProject(null)
    setResumeWizardState({ projectName, wizardStatus })
    setShowResumeWizard(true)
  }, [])

  // Handle start fresh from incomplete project modal
  const handleStartFresh = useCallback((projectName: string) => {
    setIncompleteProject(null)
    setResumeWizardState({ projectName, wizardStatus: { step: 'method', spec_method: null, started_at: new Date().toISOString(), chat_messages: [] } })
    setShowResumeWizard(true)
  }, [])

  // Handle resume wizard completion
  const handleResumeWizardComplete = useCallback((projectName: string) => {
    setShowResumeWizard(false)
    setResumeWizardState(null)
    handleSelectProject(projectName)
  }, [handleSelectProject])

  // Handle resume wizard close (without completing)
  const handleResumeWizardClose = useCallback(() => {
    setShowResumeWizard(false)
    setResumeWizardState(null)
  }, [])

  // Handle project deletion
  const handleProjectDeleted = useCallback(() => {
    setShowDeleteModal(false)
    handleSelectProject(null)
    refetchProjects()
  }, [handleSelectProject, refetchProjects])

  // Handle edit feature
  const handleEditFeature = useCallback((feature: Feature) => {
    setEditingFeature(feature)
  }, [])

  // Handle reopen feature
  const handleReopenFeature = useCallback((feature: Feature) => {
    reopenFeature.mutate(feature.id)
  }, [reopenFeature])

  // Validate stored project exists (clear if project was deleted)
  useEffect(() => {
    if (selectedProject && projects && !projects.some(p => p.name === selectedProject)) {
      handleSelectProject(null)
    }
  }, [selectedProject, projects, handleSelectProject])

  // Close assistant panel when agent starts running
  useEffect(() => {
    if (agentStatusData?.agent_running && assistantOpen) {
      setAssistantOpen(false)
    }
  }, [agentStatusData?.agent_running, assistantOpen])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if user is typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return
      }

      // D : Toggle debug window
      if (e.key === 'd' || e.key === 'D') {
        e.preventDefault()
        setDebugOpen(prev => !prev)
      }

      // N : Add new feature (when project selected)
      if ((e.key === 'n' || e.key === 'N') && selectedProject) {
        e.preventDefault()
        setShowAddFeature(true)
      }

      // A : Toggle assistant panel (when project selected)
      if ((e.key === 'a' || e.key === 'A') && selectedProject) {
        e.preventDefault()
        setAssistantOpen(prev => !prev)
      }

      // Escape : Close modals
      if (e.key === 'Escape') {
        if (assistantOpen) {
          setAssistantOpen(false)
        } else if (editingFeature) {
          setEditingFeature(null)
        } else if (showAddFeature) {
          setShowAddFeature(false)
        } else if (selectedFeature) {
          setSelectedFeature(null)
        } else if (debugOpen) {
          setDebugOpen(false)
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [selectedProject, showAddFeature, selectedFeature, editingFeature, debugOpen, assistantOpen])

  // Combine WebSocket progress with feature data
  const progress = wsState.progress.total > 0 ? wsState.progress : {
    passing: features?.done.length ?? 0,
    total: (features?.pending.length ?? 0) + (features?.in_progress.length ?? 0) + (features?.done.length ?? 0),
    percentage: 0,
  }

  if (progress.total > 0 && progress.percentage === 0) {
    progress.percentage = Math.round((progress.passing / progress.total) * 100 * 10) / 10
  }

  if (!setupComplete) {
    return <SetupWizard onComplete={() => setSetupComplete(true)} />
  }

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      {/* Header */}
      <header className="bg-[var(--color-bg-elevated)] border-b border-[var(--color-border)]">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            {/* Logo and Title */}
            <div className="flex items-center gap-3">
              <h1 className="font-display text-xl font-medium tracking-tight text-[var(--color-text)]">
                ZeroCoder
              </h1>
              <button
                onClick={toggleTheme}
                className="btn btn-ghost p-2"
                title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
              >
                {theme === 'dark' ? (
                  <Sun size={18} className="text-[var(--color-text-secondary)]" />
                ) : (
                  <Moon size={18} className="text-[var(--color-text-secondary)]" />
                )}
              </button>
            </div>

            {/* Controls */}
            <div className="flex items-center gap-3">
              <ProjectSelector
                projects={projects ?? []}
                selectedProject={selectedProject}
                onSelectProject={handleSelectProject}
                onIncompleteProjectClick={handleIncompleteProjectClick}
                isLoading={projectsLoading}
              />

              {selectedProject && (
                <>
                  {/* Only show Add Feature when agent not running */}
                  {!agentStatusData?.agent_running && (
                    <button
                      onClick={() => setShowAddFeature(true)}
                      className="btn btn-primary text-sm"
                      title="Press N"
                    >
                      <Plus size={16} />
                      Add Feature
                      <kbd className="ml-1.5 px-1.5 py-0.5 text-xs bg-white/20 rounded-sm font-mono">
                        N
                      </kbd>
                    </button>
                  )}

                  <AgentControl
                    projectName={selectedProject}
                    status={wsState.agentStatus}
                    yoloMode={agentStatusData?.yolo_mode ?? false}
                    agentRunning={agentStatusData?.agent_running ?? false}
                  />

                  <button
                    onClick={() => setShowDeleteModal(true)}
                    className="btn btn-ghost text-[var(--color-text-secondary)] hover:text-[var(--color-danger)] hover:bg-[var(--color-danger-bg)]"
                    title="Delete project"
                  >
                    <Trash2 size={16} />
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main
        className="max-w-7xl mx-auto px-6 py-8"
        style={{ paddingBottom: debugOpen ? debugPanelHeight + 32 : undefined }}
      >
        {!selectedProject ? (
          <div className="empty-state mt-12">
            <h2 className="font-display text-2xl font-medium mb-3 text-[var(--color-text)]">
              Welcome to ZeroCoder
            </h2>
            <p className="text-[var(--color-text-secondary)]">
              Select a project from the dropdown above or create a new one to get started.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Progress Dashboard */}
            <ProgressDashboard
              passing={progress.passing}
              total={progress.total}
              percentage={progress.percentage}
              isConnected={wsState.isConnected}
            />

            {/* Agent Thought - shows latest agent narrative */}
            <AgentThought
              logs={wsState.logs}
              agentStatus={wsState.agentStatus}
            />

            {/* Initializing Features State - show when agent is running but no features yet */}
            {features &&
             features.pending.length === 0 &&
             features.in_progress.length === 0 &&
             features.done.length === 0 &&
             agentStatusData?.agent_running && (
              <div className="card p-8 text-center">
                <Loader2 size={28} className="animate-spin mx-auto mb-4 text-[var(--color-progress)]" />
                <h3 className="font-display font-medium text-lg mb-2 text-[var(--color-text)]">
                  Initializing Features...
                </h3>
                <p className="text-[var(--color-text-secondary)] text-sm">
                  The agent is reading your spec and creating features. This may take a moment.
                </p>
              </div>
            )}

            {/* Kanban Board */}
            <KanbanBoard
              features={features}
              onFeatureClick={setSelectedFeature}
              agentRunning={agentStatusData?.agent_running ?? false}
              onEditFeature={handleEditFeature}
              onReopenFeature={handleReopenFeature}
            />
          </div>
        )}
      </main>

      {/* Add Feature Modal */}
      {showAddFeature && selectedProject && (
        <AddFeatureForm
          projectName={selectedProject}
          onClose={() => setShowAddFeature(false)}
        />
      )}

      {/* Feature Detail Modal */}
      {selectedFeature && selectedProject && (
        <FeatureModal
          feature={selectedFeature}
          projectName={selectedProject}
          onClose={() => setSelectedFeature(null)}
        />
      )}

      {/* Feature Edit Modal */}
      {editingFeature && selectedProject && (
        <FeatureEditModal
          feature={editingFeature}
          projectName={selectedProject}
          onClose={() => setEditingFeature(null)}
        />
      )}

      {/* Debug Log Viewer - fixed to bottom */}
      {selectedProject && (
        <DebugLogViewer
          logs={wsState.logs}
          isOpen={debugOpen}
          onToggle={() => setDebugOpen(!debugOpen)}
          onClear={wsState.clearLogs}
          onHeightChange={setDebugPanelHeight}
        />
      )}

      {/* Assistant FAB and Panel - only show when agent not running */}
      {selectedProject && !agentStatusData?.agent_running && (
        <>
          <AssistantFAB
            onClick={() => setAssistantOpen(!assistantOpen)}
            isOpen={assistantOpen}
          />
          <AssistantPanel
            projectName={selectedProject}
            isOpen={assistantOpen}
            onClose={() => setAssistantOpen(false)}
          />
        </>
      )}

      {/* Incomplete Project Modal */}
      <IncompleteProjectModal
        isOpen={incompleteProject !== null}
        project={incompleteProject}
        onClose={() => setIncompleteProject(null)}
        onResume={handleResumeWizard}
        onStartFresh={handleStartFresh}
      />

      {/* Resume Wizard Modal */}
      <NewProjectModal
        isOpen={showResumeWizard}
        onClose={handleResumeWizardClose}
        onProjectCreated={handleResumeWizardComplete}
        resumeProjectName={resumeWizardState?.projectName}
        resumeState={resumeWizardState?.wizardStatus}
      />

      {/* Delete Project Modal */}
      <DeleteProjectModal
        isOpen={showDeleteModal}
        project={projects?.find(p => p.name === selectedProject) ?? null}
        onClose={() => setShowDeleteModal(false)}
        onDeleted={handleProjectDeleted}
      />
    </div>
  )
}

export default App
