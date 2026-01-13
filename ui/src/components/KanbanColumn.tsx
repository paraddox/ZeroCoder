import { useMemo } from 'react'
import { FeatureCard } from './FeatureCard'
import { TaskSearch } from './TaskSearch'
import type { Feature } from '../lib/types'

interface KanbanColumnProps {
  title: string
  count: number
  features: Feature[]
  color: 'pending' | 'progress' | 'done'
  onFeatureClick: (feature: Feature) => void
  // Search props
  showSearch?: boolean
  searchQuery?: string
  onSearchChange?: (query: string) => void
  // Agent status for action visibility
  agentRunning?: boolean
  // Edit/Reopen callbacks
  onEdit?: (feature: Feature) => void
  onReopen?: (feature: Feature) => void
}

const colorConfig = {
  pending: {
    dot: 'var(--color-pending)',
    badge: 'badge-pending',
  },
  progress: {
    dot: 'var(--color-progress)',
    badge: 'badge-progress',
  },
  done: {
    dot: 'var(--color-done)',
    badge: 'badge-done',
  },
}

export function KanbanColumn({
  title,
  count,
  features,
  color,
  onFeatureClick,
  showSearch = false,
  searchQuery = '',
  onSearchChange,
  agentRunning = false,
  onEdit,
  onReopen,
}: KanbanColumnProps) {
  const config = colorConfig[color]

  // Filter features by search query
  const filteredFeatures = useMemo(() => {
    if (!searchQuery.trim()) return features

    const query = searchQuery.toLowerCase()
    return features.filter(
      (f) =>
        f.name.toLowerCase().includes(query) ||
        f.description.toLowerCase().includes(query) ||
        f.category.toLowerCase().includes(query)
    )
  }, [features, searchQuery])

  return (
    <div className="card overflow-hidden">
      {/* Header */}
      <div className="column-header bg-[var(--color-bg-subtle)]">
        <span
          className="column-dot"
          style={{ backgroundColor: config.dot }}
        />
        <h2 className="font-display text-base font-medium text-[var(--color-text)] flex-1">
          {title}
        </h2>
        <span className={`badge ${config.badge}`}>
          {searchQuery ? `${filteredFeatures.length}/${count}` : count}
        </span>
      </div>

      {/* Search */}
      {showSearch && onSearchChange && (
        <div className="px-3 pt-3 bg-[var(--color-bg)]">
          <TaskSearch
            value={searchQuery}
            onChange={onSearchChange}
            placeholder={`Search ${title.toLowerCase()}...`}
          />
        </div>
      )}

      {/* Cards */}
      <div className="p-3 space-y-3 max-h-[600px] overflow-y-auto bg-[var(--color-bg)]">
        {filteredFeatures.length === 0 ? (
          <div className="text-center py-8 text-[var(--color-text-muted)] text-sm">
            {searchQuery ? 'No matching features' : 'No features'}
          </div>
        ) : (
          filteredFeatures.map((feature, index) => (
            <div
              key={feature.id}
              className="animate-slide-in"
              style={{ animationDelay: `${index * 50}ms` }}
            >
              <FeatureCard
                feature={feature}
                onClick={() => onFeatureClick(feature)}
                isInProgress={color === 'progress'}
                agentRunning={agentRunning}
                showEdit={color === 'pending' && !agentRunning && !!onEdit}
                showReopen={color === 'done' && !agentRunning && !!onReopen}
                onEdit={onEdit ? () => onEdit(feature) : undefined}
                onReopen={onReopen ? () => onReopen(feature) : undefined}
              />
            </div>
          ))
        )}
      </div>
    </div>
  )
}
