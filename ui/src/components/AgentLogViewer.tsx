/**
 * Unified Agent Log Viewer
 *
 * Combines AgentThought and DebugLogViewer into a single expandable component.
 * - Collapsed: Shows latest agent "thought" (filtered narrative text)
 * - Expanded: Shows all logs with timestamps, resizable height, and color coding
 */

import { useMemo, useState, useEffect, useRef, useCallback } from 'react'
import { Brain, Sparkles, ChevronUp, ChevronDown, Trash2, GripHorizontal } from 'lucide-react'
import type { AgentStatus } from '../lib/types'
import type { LogEntry } from '../hooks/useWebSocket'

const IDLE_TIMEOUT = 30000 // 30 seconds
const MIN_HEIGHT = 150
const MAX_HEIGHT = 600
const DEFAULT_HEIGHT = 288
const STORAGE_KEY = 'unified-log-viewer-height'

interface AgentLogViewerProps {
  logs: LogEntry[]
  agentStatus: AgentStatus
  isExpanded: boolean
  onToggleExpanded: () => void
  onClearLogs: () => void
  onHeightChange?: (height: number) => void
  containerFilter?: number | null
  onContainerFilterChange?: (container: number | null) => void
}

type LogLevel = 'error' | 'warn' | 'debug' | 'info'

/**
 * Determines if a log line is an agent "thought" (narrative text)
 * vs. tool mechanics that should be hidden
 */
function isAgentThought(line: string): boolean {
  const trimmed = line.trim()

  // Skip tool mechanics
  if (/^\[Tool:/.test(trimmed)) return false
  if (/^\s*Input:\s*\{/.test(trimmed)) return false
  if (/^\[(Done|Error)\]/.test(trimmed)) return false
  if (/^\[Error\]/.test(trimmed)) return false
  if (/^Output:/.test(trimmed)) return false

  // Skip JSON and very short lines
  if (/^[\[\{]/.test(trimmed)) return false
  if (trimmed.length < 15) return false

  // Skip lines that are just paths or technical output
  if (/^[A-Za-z]:\\/.test(trimmed)) return false
  if (/^\/[a-z]/.test(trimmed)) return false

  // Keep narrative text (starts with capital, looks like a sentence)
  return /^[A-Z]/.test(trimmed) && trimmed.length > 20
}

/**
 * Extracts the latest agent thought from logs
 */
function getLatestThought(logs: Array<{ line: string; timestamp: string }>): string | null {
  // Search from most recent
  for (let i = logs.length - 1; i >= 0; i--) {
    if (isAgentThought(logs[i].line)) {
      return logs[i].line.trim()
    }
  }
  return null
}

/**
 * Parse log level from line content
 */
function getLogLevel(line: string): LogLevel {
  const lowerLine = line.toLowerCase()
  if (lowerLine.includes('error') || lowerLine.includes('exception') || lowerLine.includes('traceback')) {
    return 'error'
  }
  if (lowerLine.includes('warn') || lowerLine.includes('warning')) {
    return 'warn'
  }
  if (lowerLine.includes('debug')) {
    return 'debug'
  }
  return 'info'
}

/**
 * Get color class for log level
 */
function getLogColor(level: LogLevel): string {
  switch (level) {
    case 'error':
      return 'text-rose-400'
    case 'warn':
      return 'text-amber-400'
    case 'debug':
      return 'text-slate-500'
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

export function AgentLogViewer({
  logs,
  agentStatus,
  isExpanded,
  onToggleExpanded,
  onClearLogs,
  onHeightChange,
  containerFilter,
  onContainerFilterChange,
}: AgentLogViewerProps) {
  // Get unique container numbers from logs
  const availableContainers = useMemo(() => {
    const containers = new Set<number>()
    logs.forEach(log => {
      if (log.container_number !== undefined) {
        containers.add(log.container_number)
      }
    })
    return Array.from(containers).sort((a, b) => a - b)
  }, [logs])

  // Filter logs by container if filter is set
  const filteredLogs = useMemo(() => {
    if (containerFilter === null || containerFilter === undefined) {
      return logs
    }
    return logs.filter(log => log.container_number === containerFilter)
  }, [logs, containerFilter])

  // From AgentThought - use filtered logs
  const thought = useMemo(() => getLatestThought(filteredLogs), [filteredLogs])
  const [displayedThought, setDisplayedThought] = useState<string | null>(null)
  const [textVisible, setTextVisible] = useState(true)
  const [isVisible, setIsVisible] = useState(false)

  // From DebugLogViewer
  const scrollRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [isResizing, setIsResizing] = useState(false)
  const [panelHeight, setPanelHeight] = useState(() => {
    const saved = localStorage.getItem(STORAGE_KEY)
    return saved ? Math.min(Math.max(parseInt(saved, 10), MIN_HEIGHT), MAX_HEIGHT) : DEFAULT_HEIGHT
  })

  // Get last log timestamp for idle detection (use all logs, not filtered)
  const lastLogTimestamp = logs.length > 0
    ? new Date(logs[logs.length - 1].timestamp).getTime()
    : 0

  // Determine if component should be visible (use all logs, not filtered)
  const shouldShow = useMemo(() => {
    if (!logs.length && agentStatus !== 'running') return false
    if (isExpanded) return true // Always show when expanded
    if (agentStatus === 'running') return true
    // Show briefly after stop if recent logs exist (collapsed only)
    return Date.now() - lastLogTimestamp < IDLE_TIMEOUT
  }, [logs, agentStatus, lastLogTimestamp, isExpanded])

  // Animate text changes using CSS transitions
  useEffect(() => {
    if (thought !== displayedThought && thought) {
      // Fade out
      setTextVisible(false)
      // After fade out, update text and fade in
      const timeout = setTimeout(() => {
        setDisplayedThought(thought)
        setTextVisible(true)
      }, 150)
      return () => clearTimeout(timeout)
    }
  }, [thought, displayedThought])

  // Handle visibility transitions
  useEffect(() => {
    if (shouldShow) {
      setIsVisible(true)
    } else {
      // Delay hiding to allow exit animation
      const timeout = setTimeout(() => setIsVisible(false), 300)
      return () => clearTimeout(timeout)
    }
  }, [shouldShow])

  // Auto-scroll to bottom when new logs arrive (if user hasn't scrolled up)
  useEffect(() => {
    if (autoScroll && scrollRef.current && isExpanded) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [filteredLogs, autoScroll, isExpanded])

  // Scroll to bottom when expanding
  useEffect(() => {
    if (isExpanded && scrollRef.current && autoScroll) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [isExpanded, autoScroll])

  // Notify parent of height changes
  useEffect(() => {
    if (onHeightChange && isExpanded) {
      onHeightChange(panelHeight)
    }
  }, [panelHeight, isExpanded, onHeightChange])

  // Handle mouse move during resize
  const handleMouseMove = useCallback((e: MouseEvent) => {
    const containerTop = window.innerHeight - e.clientY
    const newHeight = containerTop
    const clampedHeight = Math.min(Math.max(newHeight, MIN_HEIGHT), MAX_HEIGHT)
    setPanelHeight(clampedHeight)
  }, [])

  // Handle mouse up to stop resizing
  const handleMouseUp = useCallback(() => {
    setIsResizing(false)
    localStorage.setItem(STORAGE_KEY, panelHeight.toString())
  }, [panelHeight])

  // Set up global mouse event listeners during resize
  useEffect(() => {
    if (isResizing) {
      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = 'ns-resize'
      document.body.style.userSelect = 'none'
    }
    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }
  }, [isResizing, handleMouseMove, handleMouseUp])

  // Start resizing
  const handleResizeStart = (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsResizing(true)
  }

  // Detect if user scrolled up
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    const isAtBottom = el.scrollHeight - el.scrollTop <= el.clientHeight + 50
    setAutoScroll(isAtBottom)
  }

  // Handle toggle with resize cancellation
  const handleToggle = () => {
    if (isResizing) {
      setIsResizing(false)
    }
    onToggleExpanded()
  }

  if (!isVisible) return null

  const isRunning = agentStatus === 'running'
  const displayText = displayedThought || (filteredLogs.length > 0 ? 'Agent working...' : 'Waiting for agent...')
  const hasMultipleContainers = availableContainers.length > 1

  // Collapsed state: AgentThought style
  if (!isExpanded) {
    return (
      <div
        className={`
          transition-all duration-300 ease-out overflow-hidden
          ${shouldShow ? 'opacity-100' : 'opacity-0'}
        `}
      >
        <div
          onClick={handleToggle}
          className={`
            relative
            bg-[var(--color-bg-elevated)]
            border border-[var(--color-border)]
            rounded-lg
            shadow-sm
            px-4 py-3
            flex items-center gap-3
            cursor-pointer
            hover:shadow-md hover:-translate-y-0.5
            transition-all duration-200
            ${isRunning ? 'animate-pulse-soft' : ''}
          `}
        >
          {/* Brain Icon with sparkle */}
          <div className="relative shrink-0">
            <Brain
              size={20}
              className="text-[var(--color-progress)]"
              strokeWidth={2}
            />
            {isRunning && (
              <Sparkles
                size={10}
                className="absolute -top-1 -right-1 text-[var(--color-pending)] animate-pulse"
              />
            )}
          </div>

          {/* Thought text with fade transition */}
          <p
            className={`
              flex-1 font-sans text-sm truncate transition-all duration-150 ease-out
              ${isRunning ? 'text-[var(--color-text)]' : 'text-[var(--color-text-secondary)]'}
            `}
            style={{
              opacity: textVisible ? 1 : 0,
              transform: textVisible ? 'translateY(0)' : 'translateY(-4px)',
            }}
          >
            {displayText.replace(/:$/, '')}
          </p>

          {/* Chevron Icon */}
          <ChevronDown
            size={16}
            className="text-[var(--color-text-muted)] shrink-0"
          />

          {/* Subtle running indicator bar */}
          {isRunning && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-[var(--color-progress)] opacity-30 rounded-b-lg" />
          )}
        </div>
      </div>
    )
  }

  // Expanded state: DebugLogViewer style
  return (
    <div
      className={`
        relative
        bg-slate-900
        border border-slate-700
        rounded-lg
        shadow-lg
        overflow-hidden
        log-viewer-transition
        ${isResizing ? 'resizing' : ''}
      `}
      style={{ height: panelHeight }}
    >
      {/* Resize handle */}
      <div
        className="absolute top-0 left-0 right-0 h-3 cursor-ns-resize group flex items-center justify-center -translate-y-1/2 z-10"
        onMouseDown={handleResizeStart}
      >
        <div className="w-12 h-1 bg-slate-600 rounded-full group-hover:bg-slate-500 transition-colors flex items-center justify-center">
          <GripHorizontal size={10} className="text-slate-400 group-hover:text-slate-300" />
        </div>
      </div>

      {/* Header bar */}
      <div
        className="flex items-center justify-between h-9 px-4 bg-slate-800 border-b border-slate-700 cursor-pointer"
        onClick={handleToggle}
      >
        <div className="flex items-center gap-2">
          <Brain size={14} className="text-emerald-400" />
          <span className="font-mono text-sm text-slate-200 font-medium">
            Agent Logs
          </span>
          <kbd className="px-1.5 py-0.5 text-xs font-mono bg-slate-900 text-slate-500 rounded">
            D
          </kbd>
          {filteredLogs.length > 0 && (
            <span className="px-2 py-0.5 text-xs font-mono bg-slate-900 text-slate-400 rounded-full">
              {filteredLogs.length}
            </span>
          )}
          {!autoScroll && (
            <span className="px-2 py-0.5 text-xs font-medium bg-amber-900/50 text-amber-400 rounded-full">
              Paused
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Container filter tabs (only show when multiple containers) */}
          {hasMultipleContainers && (
            <div
              className="flex items-center gap-1 mr-2"
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={() => onContainerFilterChange?.(null)}
                className={`px-2 py-0.5 text-xs font-mono rounded transition-colors ${
                  containerFilter === null || containerFilter === undefined
                    ? 'bg-emerald-600 text-white'
                    : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                }`}
              >
                All
              </button>
              {availableContainers.map((containerNum) => (
                <button
                  key={containerNum}
                  onClick={() => onContainerFilterChange?.(containerNum)}
                  className={`px-2 py-0.5 text-xs font-mono rounded transition-colors ${
                    containerFilter === containerNum
                      ? 'bg-emerald-600 text-white'
                      : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
                  }`}
                >
                  #{containerNum}
                </button>
              ))}
            </div>
          )}
          <button
            onClick={(e) => {
              e.stopPropagation()
              onClearLogs()
            }}
            className="p-1.5 hover:bg-slate-700 rounded transition-colors"
            title="Clear logs"
          >
            <Trash2 size={14} className="text-slate-500 hover:text-slate-400" />
          </button>
          <div className="p-1">
            <ChevronUp size={14} className="text-slate-500" />
          </div>
        </div>
      </div>

      {/* Log content area */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="h-[calc(100%-2.25rem)] overflow-y-auto bg-slate-900 p-3 font-mono text-sm"
      >
        {filteredLogs.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-600">
            {containerFilter !== null && containerFilter !== undefined
              ? `No logs for container #${containerFilter}. Try selecting "All".`
              : 'No logs yet. Start the agent to see output.'}
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
                  className="flex gap-3 hover:bg-slate-800/50 px-2 py-0.5 rounded"
                >
                  <span className="text-slate-600 select-none shrink-0 text-xs">
                    {timestamp}
                  </span>
                  {showContainerBadge && (
                    <span className="px-1.5 py-0.5 text-xs font-mono bg-slate-700 text-slate-400 rounded shrink-0">
                      #{log.container_number}
                    </span>
                  )}
                  <span className={`${colorClass} whitespace-pre-wrap break-all text-xs leading-relaxed`}>
                    {log.line}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
