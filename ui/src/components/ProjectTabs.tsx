import { useState, useRef, useEffect } from 'react'
import { Plus, FolderOpen, Loader2, AlertCircle, GitBranch } from 'lucide-react'
import type { ProjectSummary } from '../lib/types'
import { NewProjectModal } from './NewProjectModal'
import { ExistingRepoModal } from './ExistingRepoModal'

interface ProjectTabsProps {
  projects: ProjectSummary[]
  selectedProject: string | null
  onSelectProject: (name: string | null) => void
  onIncompleteProjectClick?: (project: ProjectSummary) => void
  isLoading: boolean
}

// Helper function to determine status dot configuration
function getStatusDotConfig(project: ProjectSummary): { color: string; pulse: boolean } | null {
  if (project.agent_status === 'running') {
    if (project.agent_running) {
      // Agent is running - green with pulse
      return { color: 'var(--color-done)', pulse: true }
    } else {
      // Container running but no agent (Edit Mode) - blue
      return { color: 'var(--color-progress)', pulse: false }
    }
  }
  return null // No dot for other states
}

export function ProjectTabs({
  projects,
  selectedProject,
  onSelectProject,
  onIncompleteProjectClick,
  isLoading,
}: ProjectTabsProps) {
  const [showNewProjectModal, setShowNewProjectModal] = useState(false)
  const [showExistingRepoModal, setShowExistingRepoModal] = useState(false)
  const [showAddMenu, setShowAddMenu] = useState(false)
  const tabsRef = useRef<HTMLDivElement>(null)

  const handleProjectCreated = (projectName: string) => {
    onSelectProject(projectName)
  }

  const handleTabClick = (project: ProjectSummary) => {
    if (project.wizard_incomplete && onIncompleteProjectClick) {
      onIncompleteProjectClick(project)
    } else {
      onSelectProject(project.name)
    }
  }

  // Auto-scroll active tab into view
  useEffect(() => {
    if (selectedProject && tabsRef.current) {
      const activeTab = tabsRef.current.querySelector('.tab-button.active')
      if (activeTab) {
        activeTab.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
      }
    }
  }, [selectedProject])

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-4 py-2">
        <Loader2 size={16} className="animate-spin text-[var(--color-text-secondary)]" />
        <span className="text-sm text-[var(--color-text-secondary)]">Loading projects...</span>
      </div>
    )
  }

  return (
    <>
      <div className="flex items-center gap-2">
        {/* Project Tabs */}
        <div ref={tabsRef} className="project-tabs">
          {projects.length === 0 ? (
            <button
              onClick={() => setShowNewProjectModal(true)}
              className="tab-button text-[var(--color-text-muted)]"
              title="Create your first project"
            >
              <FolderOpen size={16} />
              Get Started
            </button>
          ) : (
            projects.map(project => {
              const dotConfig = getStatusDotConfig(project)

              return (
                <button
                  key={project.name}
                  onClick={() => handleTabClick(project)}
                  className={`tab-button ${project.name === selectedProject ? 'active' : ''}`}
                  title={project.name}
                >
                  {dotConfig && (
                    <span
                      className={`status-dot ${dotConfig.pulse ? 'status-dot-pulse' : ''}`}
                      style={{ backgroundColor: dotConfig.color }}
                    />
                  )}
                  <span className="truncate max-w-[150px]">{project.name}</span>
                  {project.wizard_incomplete && (
                    <AlertCircle
                      size={12}
                      className="text-[var(--color-warning)]"
                    />
                  )}
                  {!project.wizard_incomplete && project.stats.total > 0 && (
                    <span className="badge badge-sm">
                      {project.stats.percentage}%
                    </span>
                  )}
                </button>
              )
            })
          )}
        </div>

        {/* Add Project Button with Dropdown */}
        <div className="relative">
          <button
            onClick={() => setShowAddMenu(!showAddMenu)}
            className="tab-add-button"
            title="Add project"
          >
            <Plus size={14} />
          </button>

          {/* Add Menu Dropdown */}
          {showAddMenu && (
            <>
              {/* Backdrop */}
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowAddMenu(false)}
              />

              {/* Menu */}
              <div className="absolute top-full right-0 mt-2 dropdown z-50 min-w-[200px]">
                <button
                  onClick={() => {
                    setShowNewProjectModal(true)
                    setShowAddMenu(false)
                  }}
                  className="dropdown-item flex items-center gap-2 font-medium text-[var(--color-accent)]"
                >
                  <Plus size={14} />
                  New Project
                </button>

                <button
                  onClick={() => {
                    setShowExistingRepoModal(true)
                    setShowAddMenu(false)
                  }}
                  className="dropdown-item flex items-center gap-2 text-[var(--color-text-secondary)]"
                >
                  <GitBranch size={14} />
                  Add Existing Repo
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* New Project Modal */}
      <NewProjectModal
        isOpen={showNewProjectModal}
        onClose={() => setShowNewProjectModal(false)}
        onProjectCreated={handleProjectCreated}
      />

      {/* Existing Repo Modal */}
      <ExistingRepoModal
        isOpen={showExistingRepoModal}
        onClose={() => setShowExistingRepoModal(false)}
        onProjectAdded={handleProjectCreated}
      />
    </>
  )
}
