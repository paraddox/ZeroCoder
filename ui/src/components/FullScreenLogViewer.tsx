/**
 * Full-Screen Log Viewer
 *
 * A modal overlay for viewing agent logs with enhanced features:
 * - 500 log capacity (vs. 100 in dashboard)
 * - Search functionality with text highlighting
 * - Log level filtering (All, Error, Warning, Info)
 * - Container filtering
 * - Export to text file
 * - Copy log line on click
 */

import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { X, Search, Download, Copy, Check, ChevronDown, ArrowDown, Terminal } from 'lucide-react'
import type { LogEntry, ContainerInfo } from '../hooks/useWebSocket'

type LogLevel = 'all' | 'error' | 'warn' | 'info'

interface FullScreenLogViewerProps {
  isOpen: boolean
  onClose: () => void
  logs: LogEntry[]
  projectName: string | null
  registeredContainers?: ContainerInfo[]
}

/**
 * Parse log level from line content
 */
function getLogLevel(line: string): 'error' | 'warn' | 'info' {
  const lowerLine = line.toLowerCase()
  if (lowerLine.includes('error') || lowerLine.includes('exception') || lowerLine.includes('traceback')) {
    return 'error'
  }
  if (lowerLine.includes('warn') || lowerLine.includes('warning')) {
    return 'warn'
  }
  return 'info'
}

/**
 * Get color class for log level
 */
function getLogColor(level: 'error' | 'warn' | 'info'): string {
  switch (level) {
    case 'error':
      return 'text-rose-400'
    case 'warn':
      return 'text-amber-400'
    case 'info':
    default:
      return 'text-emerald-400'
  }
}

/**
 * Format timestamp to HH:MM:SS
 */
function formatTimestamp(timestamp: string): string {
  try {
    const date = new Date(timestamp)
    return date.toLocaleTimeString('en-US', {
      hour12: false,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  } catch {
    return ''
  }
}

/**
 * Highlight search matches in text
 */
function highlightText(text: string, search: string): React.ReactNode {
  if (!search.trim()) return text

  const parts = text.split(new RegExp(`(${search.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'))

  return parts.map((part, i) =>
    part.toLowerCase() === search.toLowerCase() ? (
      <mark key={i} className="bg-amber-500/40 text-white rounded px-0.5">
        {part}
      </mark>
    ) : (
      part
    )
  )
}

export function FullScreenLogViewer({
  isOpen,
  onClose,
  logs,
  projectName,
  registeredContainers,
}: FullScreenLogViewerProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [levelFilter, setLevelFilter] = useState<LogLevel>('all')
  const [containerFilter, setContainerFilter] = useState<number | null>(null)
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [showLevelDropdown, setShowLevelDropdown] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)
  const levelDropdownRef = useRef<HTMLDivElement>(null)

  // Get available containers
  const availableContainers = useMemo(() => {
    if (registeredContainers && registeredContainers.length > 0) {
      return registeredContainers.map(c => c.number).sort((a, b) => a - b)
    }
    const containers = new Set<number>()
    logs.forEach(log => {
      if (log.container_number !== undefined) {
        containers.add(log.container_number)
      }
    })
    return Array.from(containers).sort((a, b) => a - b)
  }, [registeredContainers, logs])

  // Filter logs
  const filteredLogs = useMemo(() => {
    return logs.filter(log => {
      // Container filter
      if (containerFilter !== null && log.container_number !== containerFilter) {
        return false
      }

      // Level filter
      if (levelFilter !== 'all') {
        const logLevel = getLogLevel(log.line)
        if (levelFilter === 'error' && logLevel !== 'error') return false
        if (levelFilter === 'warn' && logLevel !== 'warn') return false
        if (levelFilter === 'info' && logLevel === 'error') return false
        if (levelFilter === 'info' && logLevel === 'warn') return false
      }

      // Search filter
      if (searchQuery.trim()) {
        return log.line.toLowerCase().includes(searchQuery.toLowerCase())
      }

      return true
    })
  }, [logs, containerFilter, levelFilter, searchQuery])

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && scrollRef.current && isOpen) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [filteredLogs, autoScroll, isOpen])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (levelDropdownRef.current && !levelDropdownRef.current.contains(e.target as Node)) {
        setShowLevelDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Handle keyboard shortcuts
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      // Escape to close
      if (e.key === 'Escape') {
        onClose()
      }
      // Ctrl/Cmd + F to focus search
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        e.preventDefault()
        document.getElementById('fullscreen-log-search')?.focus()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  // Detect scroll position
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    const isAtBottom = el.scrollHeight - el.scrollTop <= el.clientHeight + 50
    setAutoScroll(isAtBottom)
  }

  // Scroll to bottom
  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
      setAutoScroll(true)
    }
  }, [])

  // Copy log line
  const copyLogLine = useCallback(async (line: string, index: number) => {
    try {
      await navigator.clipboard.writeText(line)
      setCopiedIndex(index)
      setTimeout(() => setCopiedIndex(null), 2000)
    } catch {
      console.error('Failed to copy to clipboard')
    }
  }, [])

  // Export logs
  const exportLogs = useCallback(() => {
    const content = filteredLogs
      .map(log => {
        const timestamp = formatTimestamp(log.timestamp)
        const container = log.container_number !== undefined ? `[#${log.container_number}]` : ''
        return `${timestamp} ${container} ${log.line}`
      })
      .join('\n')

    const blob = new Blob([content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${projectName || 'agent'}-logs-${new Date().toISOString().slice(0, 10)}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, [filteredLogs, projectName])

  if (!isOpen) return null

  const hasMultipleContainers = availableContainers.length > 1

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/95 backdrop-blur-sm animate-fade-in">
      <div className="h-full flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700 bg-slate-800/50">
          <div className="flex items-center gap-3">
            <Terminal size={20} className="text-emerald-400" />
            <h2 className="font-display text-lg font-medium text-white">
              Full Screen Logs
              {projectName && (
                <span className="text-slate-400 font-sans text-sm ml-2">
                  {projectName}
                </span>
              )}
            </h2>
            <span className="px-2 py-0.5 text-xs font-mono bg-slate-700 text-slate-300 rounded-full">
              {filteredLogs.length} / {logs.length}
            </span>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={exportLogs}
              className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-slate-300 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
            >
              <Download size={16} />
              Export
            </button>
            <button
              onClick={onClose}
              className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Filters Bar */}
        <div className="flex flex-wrap items-center gap-4 px-6 py-3 border-b border-slate-700/50 bg-slate-800/30">
          {/* Search */}
          <div className="relative flex-1 min-w-[200px] max-w-md">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              id="fullscreen-log-search"
              type="text"
              placeholder="Search logs... (Ctrl+F)"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm bg-slate-800 border border-slate-600 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
            />
          </div>

          {/* Level Filter Dropdown */}
          <div className="relative" ref={levelDropdownRef}>
            <button
              onClick={() => setShowLevelDropdown(!showLevelDropdown)}
              className="flex items-center gap-2 px-3 py-2 text-sm font-medium bg-slate-800 border border-slate-600 rounded-lg text-slate-300 hover:bg-slate-700 transition-colors"
            >
              <span className={`w-2 h-2 rounded-full ${
                levelFilter === 'all' ? 'bg-slate-400' :
                levelFilter === 'error' ? 'bg-rose-400' :
                levelFilter === 'warn' ? 'bg-amber-400' : 'bg-emerald-400'
              }`} />
              {levelFilter === 'all' ? 'All Levels' :
               levelFilter === 'error' ? 'Errors' :
               levelFilter === 'warn' ? 'Warnings' : 'Info'}
              <ChevronDown size={14} />
            </button>

            {showLevelDropdown && (
              <div className="absolute top-full left-0 mt-1 w-40 bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-10 overflow-hidden">
                {(['all', 'error', 'warn', 'info'] as LogLevel[]).map((level) => (
                  <button
                    key={level}
                    onClick={() => {
                      setLevelFilter(level)
                      setShowLevelDropdown(false)
                    }}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-sm text-left transition-colors ${
                      levelFilter === level ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-700'
                    }`}
                  >
                    <span className={`w-2 h-2 rounded-full ${
                      level === 'all' ? 'bg-slate-400' :
                      level === 'error' ? 'bg-rose-400' :
                      level === 'warn' ? 'bg-amber-400' : 'bg-emerald-400'
                    }`} />
                    {level === 'all' ? 'All Levels' :
                     level === 'error' ? 'Errors' :
                     level === 'warn' ? 'Warnings' : 'Info'}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Container Filter */}
          {hasMultipleContainers && (
            <div className="flex items-center gap-1">
              <span className="text-sm text-slate-500 mr-1">Container:</span>
              <button
                onClick={() => setContainerFilter(null)}
                className={`px-3 py-1.5 text-xs font-mono rounded-lg transition-colors ${
                  containerFilter === null
                    ? 'bg-emerald-600 text-white'
                    : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                }`}
              >
                All
              </button>
              {availableContainers.map((containerNum) => {
                const containerInfo = registeredContainers?.find(c => c.number === containerNum)
                const label = containerNum === -1 ? 'Hound' : containerInfo?.agent_type || `#${containerNum}`
                return (
                  <button
                    key={containerNum}
                    onClick={() => setContainerFilter(containerNum)}
                    className={`px-3 py-1.5 text-xs font-mono rounded-lg transition-colors ${
                      containerFilter === containerNum
                        ? 'bg-emerald-600 text-white'
                        : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                    }`}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Log Content */}
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto p-4 font-mono text-sm"
        >
          {filteredLogs.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-500">
              {searchQuery ? `No logs matching "${searchQuery}"` : 'No logs yet. Start the agent to see output.'}
            </div>
          ) : (
            <div className="space-y-0.5">
              {filteredLogs.map((log, index) => {
                const level = getLogLevel(log.line)
                const colorClass = getLogColor(level)
                const timestamp = formatTimestamp(log.timestamp)
                const showContainerBadge = hasMultipleContainers && containerFilter === null && log.container_number !== undefined

                return (
                  <div
                    key={`${log.timestamp}-${index}`}
                    className="group flex gap-3 hover:bg-slate-800/50 px-3 py-1 rounded cursor-pointer"
                    onClick={() => copyLogLine(log.line, index)}
                    title="Click to copy"
                  >
                    {/* Line number */}
                    <span className="text-slate-600 select-none shrink-0 text-xs w-10 text-right">
                      {index + 1}
                    </span>

                    {/* Timestamp */}
                    <span className="text-slate-500 select-none shrink-0 text-xs">
                      {timestamp}
                    </span>

                    {/* Container badge */}
                    {showContainerBadge && (
                      <span className="px-1.5 py-0.5 text-xs font-mono bg-slate-700 text-slate-400 rounded shrink-0">
                        {log.container_number === -1 ? 'Hound' : (() => {
                          const containerInfo = registeredContainers?.find(c => c.number === log.container_number)
                          return containerInfo?.agent_type || `#${log.container_number}`
                        })()}
                      </span>
                    )}

                    {/* Log content */}
                    <span className={`${colorClass} whitespace-pre-wrap break-all text-xs leading-relaxed flex-1`}>
                      {highlightText(log.line, searchQuery)}
                    </span>

                    {/* Copy indicator */}
                    <span className="opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                      {copiedIndex === index ? (
                        <Check size={14} className="text-emerald-400" />
                      ) : (
                        <Copy size={14} className="text-slate-500" />
                      )}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Jump to Bottom Button */}
        {!autoScroll && (
          <button
            onClick={scrollToBottom}
            className="absolute bottom-6 right-6 flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-full shadow-lg transition-all hover:scale-105"
          >
            <ArrowDown size={16} />
            Jump to Bottom
          </button>
        )}
      </div>
    </div>
  )
}
