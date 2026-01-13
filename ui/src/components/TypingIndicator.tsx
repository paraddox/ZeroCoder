/**
 * Typing Indicator Component
 *
 * Shows animated dots to indicate Claude is typing/thinking.
 * Styled with soft editorial aesthetic.
 */

export function TypingIndicator() {
  return (
    <div className="flex items-center gap-2 p-4">
      <div className="flex items-center gap-1">
        <span
          className="w-2 h-2 bg-[var(--color-progress)] rounded-full animate-bounce"
          style={{ animationDelay: '0ms' }}
        />
        <span
          className="w-2 h-2 bg-[var(--color-progress)] rounded-full animate-bounce"
          style={{ animationDelay: '150ms' }}
        />
        <span
          className="w-2 h-2 bg-[var(--color-progress)] rounded-full animate-bounce"
          style={{ animationDelay: '300ms' }}
        />
      </div>
      <span className="text-sm font-mono text-[var(--color-text-muted)] animate-pulse">
        Claude is thinking...
      </span>
    </div>
  )
}
