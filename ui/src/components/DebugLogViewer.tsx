/**
 * Debug Log Viewer Component
 *
 * Collapsible panel at the bottom of the screen showing real-time
 * agent output (tool calls, results, steps). Similar to browser DevTools.
 * Features a resizable height via drag handle.
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { ChevronUp, ChevronDown, Trash2, Terminal, GripHorizontal } from 'lucide-react'

const MIN_HEIGHT = 150
const MAX_HEIGHT = 600
const DEFAULT_HEIGHT = 288
const STORAGE_KEY = 'debug-panel-height'

interface DebugLogViewerProps {
  logs: Array<{ line: string; timestamp: string }>
  isOpen: boolean
  onToggle: () => void
  onClear: () => void
  onHeightChange?: (height: number) => void
}

type LogLevel = 'error' | 'warn' | 'debug' | 'info'

export function DebugLogViewer({
  logs,
  isOpen,
  onToggle,
  onClear,
  onHeightChange,
}: DebugLogViewerProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [isResizing, setIsResizing] = useState(false)
  const [panelHeight, setPanelHeight] = useState(() => {
    // Load saved height from localStorage
    const saved = localStorage.getItem(STORAGE_KEY)
    return saved ? Math.min(Math.max(parseInt(saved, 10), MIN_HEIGHT), MAX_HEIGHT) : DEFAULT_HEIGHT
  })

  // Auto-scroll to bottom when new logs arrive (if user hasn't scrolled up)
  useEffect(() => {
    if (autoScroll && scrollRef.current && isOpen) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [logs, autoScroll, isOpen])

  // Notify parent of height changes
  useEffect(() => {
    if (onHeightChange && isOpen) {
      onHeightChange(panelHeight)
    }
  }, [panelHeight, isOpen, onHeightChange])

  // Handle mouse move during resize
  const handleMouseMove = useCallback((e: MouseEvent) => {
    const newHeight = window.innerHeight - e.clientY
    const clampedHeight = Math.min(Math.max(newHeight, MIN_HEIGHT), MAX_HEIGHT)
    setPanelHeight(clampedHeight)
  }, [])

  // Handle mouse up to stop resizing
  const handleMouseUp = useCallback(() => {
    setIsResizing(false)
    // Save to localStorage
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

  // Parse log level from line content
  const getLogLevel = (line: string): LogLevel => {
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

  // Get color class for log level - softer colors
  const getLogColor = (level: LogLevel): string => {
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

  // Format timestamp to HH:MM:SS
  const formatTimestamp = (timestamp: string): string => {
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

  return (
    <div
      className={`fixed bottom-0 left-0 right-0 z-40 ${
        isResizing ? '' : 'transition-all duration-200'
      }`}
      style={{ height: isOpen ? panelHeight : 36 }}
    >
      {/* Resize handle - only visible when open */}
      {isOpen && (
        <div
          className="absolute top-0 left-0 right-0 h-3 cursor-ns-resize group flex items-center justify-center -translate-y-1/2 z-50"
          onMouseDown={handleResizeStart}
        >
          <div className="w-12 h-1 bg-slate-600 rounded-full group-hover:bg-slate-500 transition-colors flex items-center justify-center">
            <GripHorizontal size={10} className="text-slate-400 group-hover:text-slate-300" />
          </div>
        </div>
      )}

      {/* Header bar */}
      <div
        className="flex items-center justify-between h-9 px-4 bg-slate-900 border-t border-slate-700 cursor-pointer"
        onClick={onToggle}
      >
        <div className="flex items-center gap-2">
          <Terminal size={14} className="text-emerald-400" />
          <span className="font-mono text-sm text-slate-200 font-medium">
            Debug
          </span>
          <kbd className="px-1.5 py-0.5 text-xs font-mono bg-slate-800 text-slate-500 rounded">
            D
          </kbd>
          {logs.length > 0 && (
            <span className="px-2 py-0.5 text-xs font-mono bg-slate-800 text-slate-400 rounded-full">
              {logs.length}
            </span>
          )}
          {!autoScroll && isOpen && (
            <span className="px-2 py-0.5 text-xs font-medium bg-amber-900/50 text-amber-400 rounded-full">
              Paused
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          {isOpen && (
            <button
              onClick={(e) => {
                e.stopPropagation()
                onClear()
              }}
              className="p-1.5 hover:bg-slate-800 rounded transition-colors"
              title="Clear logs"
            >
              <Trash2 size={14} className="text-slate-500 hover:text-slate-400" />
            </button>
          )}
          <div className="p-1">
            {isOpen ? (
              <ChevronDown size={14} className="text-slate-500" />
            ) : (
              <ChevronUp size={14} className="text-slate-500" />
            )}
          </div>
        </div>
      </div>

      {/* Log content area */}
      {isOpen && (
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="h-[calc(100%-2.25rem)] overflow-y-auto bg-slate-900 p-3 font-mono text-sm"
        >
          {logs.length === 0 ? (
            <div className="flex items-center justify-center h-full text-slate-600">
              No logs yet. Start the agent to see output.
            </div>
          ) : (
            <div className="space-y-0.5">
              {logs.map((log, index) => {
                const level = getLogLevel(log.line)
                const colorClass = getLogColor(level)
                const timestamp = formatTimestamp(log.timestamp)

                return (
                  <div
                    key={`${log.timestamp}-${index}`}
                    className="flex gap-3 hover:bg-slate-800/50 px-2 py-0.5 rounded"
                  >
                    <span className="text-slate-600 select-none shrink-0 text-xs">
                      {timestamp}
                    </span>
                    <span className={`${colorClass} whitespace-pre-wrap break-all text-xs leading-relaxed`}>
                      {log.line}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
