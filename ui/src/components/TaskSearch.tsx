/**
 * Task Search Component
 *
 * A simple search input for filtering tasks in the Kanban columns.
 */

import { useState, useCallback, useEffect } from 'react'
import { Search, X } from 'lucide-react'

interface TaskSearchProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
}

export function TaskSearch({ value, onChange, placeholder = 'Search tasks...' }: TaskSearchProps) {
  const [localValue, setLocalValue] = useState(value)

  // Debounce the onChange callback
  useEffect(() => {
    const timer = setTimeout(() => {
      onChange(localValue)
    }, 200)

    return () => clearTimeout(timer)
  }, [localValue, onChange])

  // Sync external value changes
  useEffect(() => {
    setLocalValue(value)
  }, [value])

  const handleClear = useCallback(() => {
    setLocalValue('')
    onChange('')
  }, [onChange])

  return (
    <div className="relative">
      <Search
        size={14}
        className="absolute left-2 top-1/2 -translate-y-1/2 text-[var(--color-text-secondary)]"
      />
      <input
        type="text"
        value={localValue}
        onChange={(e) => setLocalValue(e.target.value)}
        placeholder={placeholder}
        className="input pl-7 pr-7 py-1.5 text-xs w-full"
      />
      {localValue && (
        <button
          onClick={handleClear}
          className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--color-text-secondary)] hover:text-[var(--color-text)] transition-colors"
          title="Clear search"
        >
          <X size={14} />
        </button>
      )}
    </div>
  )
}
