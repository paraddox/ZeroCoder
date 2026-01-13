import { useState } from 'react'
import { KanbanColumn } from './KanbanColumn'
import type { Feature, FeatureListResponse } from '../lib/types'

interface KanbanBoardProps {
  features: FeatureListResponse | undefined
  onFeatureClick: (feature: Feature) => void
  agentRunning?: boolean
  onEditFeature?: (feature: Feature) => void
  onReopenFeature?: (feature: Feature) => void
}

export function KanbanBoard({
  features,
  onFeatureClick,
  agentRunning = false,
  onEditFeature,
  onReopenFeature,
}: KanbanBoardProps) {
  const [pendingSearch, setPendingSearch] = useState('')
  const [doneSearch, setDoneSearch] = useState('')

  if (!features) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {['Pending', 'In Progress', 'Done'].map(title => (
          <div key={title} className="card p-4">
            <div className="h-8 bg-[var(--color-bg-muted)] animate-pulse rounded mb-4" />
            <div className="space-y-3">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-24 bg-[var(--color-bg-muted)] animate-pulse rounded" />
              ))}
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      <KanbanColumn
        title="Pending"
        count={features.pending.length}
        features={features.pending}
        color="pending"
        onFeatureClick={onFeatureClick}
        showSearch={features.pending.length > 3}
        searchQuery={pendingSearch}
        onSearchChange={setPendingSearch}
        agentRunning={agentRunning}
        onEdit={onEditFeature}
      />
      <KanbanColumn
        title="In Progress"
        count={features.in_progress.length}
        features={features.in_progress}
        color="progress"
        onFeatureClick={onFeatureClick}
        agentRunning={agentRunning}
      />
      <KanbanColumn
        title="Done"
        count={features.done.length}
        features={features.done}
        color="done"
        onFeatureClick={onFeatureClick}
        showSearch={features.done.length > 3}
        searchQuery={doneSearch}
        onSearchChange={setDoneSearch}
        agentRunning={agentRunning}
        onReopen={onReopenFeature}
      />
    </div>
  )
}
