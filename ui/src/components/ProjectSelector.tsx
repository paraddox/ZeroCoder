import { useState } from 'react'
import { ChevronDown, Plus, FolderOpen, Loader2, AlertCircle, GitBranch } from 'lucide-react'
import type { ProjectSummary } from '../lib/types'
import { NewProjectModal } from './NewProjectModal'
import { ExistingRepoModal } from './ExistingRepoModal'

interface ProjectSelectorProps {
  projects: ProjectSummary[]
  selectedProject: string | null
  onSelectProject: (name: string | null) => void
  onIncompleteProjectClick?: (project: ProjectSummary) => void
  isLoading: boolean
}

export function ProjectSelector({
  projects,
  selectedProject,
  onSelectProject,
  onIncompleteProjectClick,
  isLoading,
}: ProjectSelectorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [showNewProjectModal, setShowNewProjectModal] = useState(false)
  const [showExistingRepoModal, setShowExistingRepoModal] = useState(false)

  const handleProjectCreated = (projectName: string) => {
    onSelectProject(projectName)
    setIsOpen(false)
  }

  const selectedProjectData = projects.find(p => p.name === selectedProject)

  return (
    <div className="relative">
      {/* Dropdown Trigger */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="btn btn-secondary min-w-[200px] justify-between"
        disabled={isLoading}
      >
        {isLoading ? (
          <Loader2 size={16} className="animate-spin" />
        ) : selectedProject ? (
          <>
            <span className="flex items-center gap-2">
              <FolderOpen size={16} className="text-[var(--color-text-secondary)]" />
              {selectedProject}
            </span>
            {selectedProjectData && selectedProjectData.stats.total > 0 && (
              <span className="badge badge-done ml-2">
                {selectedProjectData.stats.percentage}%
              </span>
            )}
          </>
        ) : (
          <span className="text-[var(--color-text-muted)]">
            Select Project
          </span>
        )}
        <ChevronDown
          size={16}
          className={`text-[var(--color-text-muted)] transition-transform ${isOpen ? 'rotate-180' : ''}`}
        />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />

          {/* Menu */}
          <div className="absolute top-full left-0 mt-2 w-full dropdown z-50 min-w-[280px]">
            {projects.length > 0 ? (
              <div className="max-h-[300px] overflow-auto">
                {projects.map(project => (
                  <button
                    key={project.name}
                    onClick={() => {
                      if (project.wizard_incomplete && onIncompleteProjectClick) {
                        onIncompleteProjectClick(project)
                        setIsOpen(false)
                      } else {
                        onSelectProject(project.name)
                        setIsOpen(false)
                      }
                    }}
                    className={`dropdown-item flex items-center justify-between ${
                      project.name === selectedProject ? 'active' : ''
                    }`}
                  >
                    <span className="flex items-center gap-2">
                      <FolderOpen size={14} className="text-[var(--color-text-secondary)]" />
                      {project.name}
                      {project.wizard_incomplete && (
                        <span title="Setup incomplete">
                          <AlertCircle size={14} className="text-[var(--color-warning)]" />
                        </span>
                      )}
                    </span>
                    {project.stats.total > 0 && (
                      <span className="text-sm font-mono text-[var(--color-text-muted)]">
                        {project.stats.passing}/{project.stats.total}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            ) : (
              <div className="p-4 text-center text-[var(--color-text-muted)] text-sm">
                No projects yet
              </div>
            )}

            {/* Divider */}
            <div className="divider" />

            {/* Create New */}
            <button
              onClick={() => {
                setShowNewProjectModal(true)
                setIsOpen(false)
              }}
              className="dropdown-item flex items-center gap-2 font-medium text-[var(--color-accent)]"
            >
              <Plus size={14} />
              New Project
            </button>

            {/* Add Existing Repo */}
            <button
              onClick={() => {
                setShowExistingRepoModal(true)
                setIsOpen(false)
              }}
              className="dropdown-item flex items-center gap-2 text-[var(--color-text-secondary)]"
            >
              <GitBranch size={14} />
              Add Existing Repo
            </button>
          </div>
        </>
      )}

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
    </div>
  )
}
