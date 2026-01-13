/**
 * Chat Message Component
 *
 * Displays a single message in the spec creation chat.
 * Supports user, assistant, and system messages with soft editorial styling.
 */

import { Bot, User, Info, FileText } from 'lucide-react'
import type { ChatMessage as ChatMessageType, ImageAttachment } from '../lib/types'

interface ChatMessageProps {
  message: ChatMessageType
}

export function ChatMessage({ message }: ChatMessageProps) {
  const { role, content, attachments, timestamp, isStreaming } = message

  // Format timestamp
  const timeString = timestamp.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })

  // Role-specific styling
  const roleConfig = {
    user: {
      icon: User,
      bgColor: 'bg-[var(--color-pending)]',
      borderColor: 'border-[var(--color-border)]',
      align: 'justify-end',
      bubbleAlign: 'items-end',
      iconBg: 'bg-[var(--color-pending)]',
    },
    assistant: {
      icon: Bot,
      bgColor: 'bg-[var(--color-bg-elevated)]',
      borderColor: 'border-[var(--color-border)]',
      align: 'justify-start',
      bubbleAlign: 'items-start',
      iconBg: 'bg-[var(--color-progress)]',
    },
    system: {
      icon: Info,
      bgColor: 'bg-[var(--color-done)]',
      borderColor: 'border-[var(--color-border)]',
      align: 'justify-center',
      bubbleAlign: 'items-center',
      iconBg: 'bg-[var(--color-done)]',
    },
  }

  const config = roleConfig[role]
  const Icon = config.icon

  // System messages are styled differently
  if (role === 'system') {
    return (
      <div className={`flex ${config.align} px-4 py-2`}>
        <div
          className={`
            ${config.bgColor}
            border ${config.borderColor}
            px-4 py-2
            rounded-md
            text-sm font-mono
            shadow-sm
          `}
        >
          <span className="flex items-center gap-2">
            <Icon size={14} />
            {content}
          </span>
        </div>
      </div>
    )
  }

  return (
    <div className={`flex ${config.align} px-4 py-2`}>
      <div className={`flex flex-col ${config.bubbleAlign} max-w-[80%] gap-1`}>
        {/* Message bubble */}
        <div className="flex items-start gap-2">
          {role === 'assistant' && (
            <div
              className={`
                ${config.iconBg}
                border border-[var(--color-border)]
                p-1.5
                rounded-full
                shadow-sm
                flex-shrink-0
              `}
            >
              <Icon size={16} className="text-[var(--color-text-inverse)]" />
            </div>
          )}

          <div
            className={`
              ${config.bgColor}
              border ${config.borderColor}
              px-4 py-3
              rounded-lg
              shadow-sm
              ${isStreaming ? 'opacity-90' : ''}
            `}
          >
            {/* Parse content for basic markdown-like formatting */}
            {content && (
              <div className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--color-text)]">
                {content.split('\n').map((line, i) => {
                  // Bold text
                  const boldRegex = /\*\*(.*?)\*\*/g
                  const parts = []
                  let lastIndex = 0
                  let match

                  while ((match = boldRegex.exec(line)) !== null) {
                    if (match.index > lastIndex) {
                      parts.push(line.slice(lastIndex, match.index))
                    }
                    parts.push(
                      <strong key={`bold-${i}-${match.index}`} className="font-medium">
                        {match[1]}
                      </strong>
                    )
                    lastIndex = match.index + match[0].length
                  }

                  if (lastIndex < line.length) {
                    parts.push(line.slice(lastIndex))
                  }

                  return (
                    <span key={i}>
                      {parts.length > 0 ? parts : line}
                      {i < content.split('\n').length - 1 && '\n'}
                    </span>
                  )
                })}
              </div>
            )}

            {/* Display attachments (images and text files) */}
            {attachments && attachments.length > 0 && (
              <div className={`flex flex-wrap gap-2 ${content ? 'mt-3' : ''}`}>
                {attachments.map((attachment) => (
                  <div
                    key={attachment.id}
                    className="border border-[var(--color-border)] p-1 bg-[var(--color-bg-elevated)] rounded-md shadow-sm"
                  >
                    {attachment.isText ? (
                      // Text file display
                      <div className="flex items-center gap-2 px-2 py-1">
                        <FileText size={16} className="text-[var(--color-text-secondary)]" />
                        <span className="text-xs text-[var(--color-text-secondary)]">
                          {attachment.filename}
                        </span>
                      </div>
                    ) : (
                      // Image display
                      <>
                        <img
                          src={(attachment as ImageAttachment).previewUrl}
                          alt={attachment.filename}
                          className="max-w-48 max-h-48 object-contain cursor-pointer hover:opacity-90 transition-opacity rounded"
                          onClick={() => window.open((attachment as ImageAttachment).previewUrl, '_blank')}
                          title={`${attachment.filename} (click to enlarge)`}
                        />
                        <span className="text-xs text-[var(--color-text-secondary)] block mt-1 text-center">
                          {attachment.filename}
                        </span>
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Streaming indicator */}
            {isStreaming && (
              <span className="inline-block w-2 h-4 bg-[var(--color-accent)] ml-1 animate-pulse rounded-sm" />
            )}
          </div>

          {role === 'user' && (
            <div
              className={`
                ${config.iconBg}
                border border-[var(--color-border)]
                p-1.5
                rounded-full
                shadow-sm
                flex-shrink-0
              `}
            >
              <Icon size={16} />
            </div>
          )}
        </div>

        {/* Timestamp */}
        <span className="text-xs text-[var(--color-text-secondary)] font-mono px-2">
          {timeString}
        </span>
      </div>
    </div>
  )
}
