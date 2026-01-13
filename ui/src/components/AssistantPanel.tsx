/**
 * Assistant Panel Component
 *
 * Slide-in panel container for the project assistant chat.
 * Slides in from the right side of the screen.
 */

import { X, Bot } from 'lucide-react'
import { AssistantChat } from './AssistantChat'

interface AssistantPanelProps {
  projectName: string
  isOpen: boolean
  onClose: () => void
}

export function AssistantPanel({ projectName, isOpen, onClose }: AssistantPanelProps) {
  return (
    <>
      {/* Backdrop - click to close */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/20 z-40 transition-opacity duration-300"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Panel */}
      <div
        className={`
          fixed right-0 top-0 bottom-0 z-50
          w-[400px] max-w-[90vw]
          bg-[var(--color-bg)]
          border-l border-[var(--color-border)]
          shadow-lg
          transform transition-transform duration-300 ease-out
          flex flex-col
          ${isOpen ? 'translate-x-0' : 'translate-x-full'}
        `}
        role="dialog"
        aria-label="Project Assistant"
        aria-hidden={!isOpen}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)] bg-[var(--color-accent)]">
          <div className="flex items-center gap-2">
            <div className="bg-[var(--color-bg-elevated)] border border-[var(--color-border)] p-1.5 rounded-md shadow-sm">
              <Bot size={18} className="text-[var(--color-text)]" />
            </div>
            <div>
              <h2 className="font-display font-medium text-[var(--color-text-inverse)]">Project Assistant</h2>
              <p className="text-xs text-[var(--color-text-inverse)]/80 font-mono">{projectName}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="
              btn btn-ghost
              p-2
              bg-[var(--color-text-inverse)]/20 border-[var(--color-text-inverse)]/40
              hover:bg-[var(--color-text-inverse)]/30
              text-[var(--color-text-inverse)]
            "
            title="Close Assistant (Press A)"
            aria-label="Close Assistant"
          >
            <X size={18} />
          </button>
        </div>

        {/* Chat area */}
        <div className="flex-1 overflow-hidden">
          {isOpen && <AssistantChat projectName={projectName} />}
        </div>
      </div>
    </>
  )
}
