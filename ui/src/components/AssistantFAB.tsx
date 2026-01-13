/**
 * Floating Action Button for toggling the Assistant panel
 */

import { MessageCircle, X } from 'lucide-react'

interface AssistantFABProps {
  onClick: () => void
  isOpen: boolean
}

export function AssistantFAB({ onClick, isOpen }: AssistantFABProps) {
  return (
    <button
      onClick={onClick}
      className={`
        fixed bottom-6 right-6 z-50
        w-14 h-14
        flex items-center justify-center
        bg-[var(--color-accent)] text-[var(--color-text-inverse)]
        border border-[var(--color-border)]
        rounded-lg
        shadow-md
        transition-all duration-200
        hover:shadow-lg hover:-translate-y-0.5
        active:shadow-sm active:translate-y-0.5
        ${isOpen ? 'rotate-0' : ''}
      `}
      title={isOpen ? 'Close Assistant (Press A)' : 'Open Assistant (Press A)'}
      aria-label={isOpen ? 'Close Assistant' : 'Open Assistant'}
    >
      {isOpen ? <X size={24} /> : <MessageCircle size={24} />}
    </button>
  )
}
