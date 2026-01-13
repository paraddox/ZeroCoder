/**
 * Spec Creation Chat Component
 *
 * Full chat interface for interactive spec creation with Claude.
 * Handles the 7-phase conversation flow for creating app specifications.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { Send, X, CheckCircle2, AlertCircle, Wifi, WifiOff, RotateCcw, Loader2, ArrowRight, Zap, Paperclip, ExternalLink } from 'lucide-react'
import { useSpecChat } from '../hooks/useSpecChat'
import { ChatMessage } from './ChatMessage'
import { QuestionOptions } from './QuestionOptions'
import { TypingIndicator } from './TypingIndicator'
import type { ImageAttachment, TextAttachment, FileAttachment, ImageMimeType, TextMimeType } from '../lib/types'

// File upload validation constants
const MAX_IMAGE_SIZE = 5 * 1024 * 1024 // 5 MB for images
const MAX_TEXT_SIZE = 1 * 1024 * 1024  // 1 MB for text files

const IMAGE_TYPES: ImageMimeType[] = ['image/jpeg', 'image/png']
const TEXT_TYPES: TextMimeType[] = [
  'text/plain', 'text/markdown', 'text/csv', 'application/json',
  'text/html', 'text/css', 'text/javascript', 'application/xml'
]

// File extensions that should be treated as text
const TEXT_EXTENSIONS = ['.txt', '.md', '.csv', '.json', '.html', '.css', '.js', '.jsx', '.ts', '.tsx', '.xml', '.yaml', '.yml', '.env', '.sh', '.py', '.rb', '.go', '.rs', '.java', '.c', '.cpp', '.h', '.hpp']

function isTextFile(file: File): boolean {
  // Check by MIME type
  if (TEXT_TYPES.includes(file.type as TextMimeType)) return true
  // Check by extension for files with generic MIME types
  const ext = '.' + file.name.split('.').pop()?.toLowerCase()
  return TEXT_EXTENSIONS.includes(ext)
}

function getTextMimeType(file: File): TextMimeType {
  if (TEXT_TYPES.includes(file.type as TextMimeType)) {
    return file.type as TextMimeType
  }
  // Default to text/plain for unknown text files
  return 'text/plain'
}

type InitializerStatus = 'idle' | 'starting' | 'error'

interface SpecCreationChatProps {
  projectName: string
  onComplete: (specPath: string, yoloMode?: boolean) => void
  onCancel: () => void
  onExitToProject: () => void  // Exit to project without starting agent
  initializerStatus?: InitializerStatus
  initializerError?: string | null
  onRetryInitializer?: () => void
}

export function SpecCreationChat({
  projectName,
  onComplete,
  onCancel,
  onExitToProject,
  initializerStatus = 'idle',
  initializerError = null,
  onRetryInitializer,
}: SpecCreationChatProps) {
  const [input, setInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [yoloEnabled, setYoloEnabled] = useState(false)
  const [pendingAttachments, setPendingAttachments] = useState<FileAttachment[]>([])
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const {
    messages,
    isLoading,
    isComplete,
    connectionStatus,
    currentQuestions,
    start,
    sendMessage,
    sendAnswer,
    disconnect,
  } = useSpecChat({
    projectName,
    onComplete,
    onError: (err) => setError(err),
  })

  // Start the chat session when component mounts
  useEffect(() => {
    start()

    return () => {
      disconnect()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, currentQuestions, isLoading])

  // Focus input when not loading and no questions
  useEffect(() => {
    if (!isLoading && !currentQuestions && inputRef.current) {
      inputRef.current.focus()
    }
  }, [isLoading, currentQuestions])

  const handleSendMessage = () => {
    const trimmed = input.trim()
    // Allow sending if there's text OR attachments
    if ((!trimmed && pendingAttachments.length === 0) || isLoading) return

    // Detect /exit command - exit to project without sending to Claude
    if (/^\s*\/exit\s*$/i.test(trimmed)) {
      setInput('')
      onExitToProject()
      return
    }

    sendMessage(trimmed, pendingAttachments.length > 0 ? pendingAttachments : undefined)
    setInput('')
    setPendingAttachments([]) // Clear attachments after sending
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  const handleAnswerSubmit = (answers: Record<string, string | string[]>) => {
    sendAnswer(answers)
  }

  // File handling for image and text attachments
  const handleFileSelect = useCallback((files: FileList | null) => {
    if (!files) return

    Array.from(files).forEach((file) => {
      const isText = isTextFile(file)

      // Validate file type for images (text files are more permissive via extension)
      if (!isText && !IMAGE_TYPES.includes(file.type as ImageMimeType)) {
        setError(`Invalid file type: ${file.name}. Supported: images (JPEG, PNG) and text files (.txt, .md, .json, etc.)`)
        return
      }

      // Validate file size
      const maxSize = isText ? MAX_TEXT_SIZE : MAX_IMAGE_SIZE
      const maxSizeMB = maxSize / (1024 * 1024)
      if (file.size > maxSize) {
        setError(`File too large: ${file.name}. Maximum size is ${maxSizeMB} MB for ${isText ? 'text files' : 'images'}.`)
        return
      }

      if (isText) {
        // Read text file as text
        const reader = new FileReader()
        reader.onload = (e) => {
          const textContent = e.target?.result as string

          const attachment: TextAttachment = {
            id: `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
            filename: file.name,
            mimeType: getTextMimeType(file),
            textContent,
            size: file.size,
            isText: true,
          }

          setPendingAttachments((prev) => [...prev, attachment])
        }
        reader.readAsText(file)
      } else {
        // Read image file as base64
        const reader = new FileReader()
        reader.onload = (e) => {
          const dataUrl = e.target?.result as string
          // dataUrl is "data:image/png;base64,XXXXXX"
          const base64Data = dataUrl.split(',')[1]

          const attachment: ImageAttachment = {
            id: `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`,
            filename: file.name,
            mimeType: file.type as ImageMimeType,
            base64Data,
            previewUrl: dataUrl,
            size: file.size,
          }

          setPendingAttachments((prev) => [...prev, attachment])
        }
        reader.readAsDataURL(file)
      }
    })
  }, [])

  const handleRemoveAttachment = useCallback((id: string) => {
    setPendingAttachments((prev) => prev.filter((a) => a.id !== id))
  }, [])

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      handleFileSelect(e.dataTransfer.files)
    },
    [handleFileSelect]
  )

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
  }, [])

  // Connection status indicator
  const ConnectionIndicator = () => {
    switch (connectionStatus) {
      case 'connected':
        return (
          <span className="flex items-center gap-1 text-xs text-[var(--color-success)]">
            <Wifi size={12} />
            Connected
          </span>
        )
      case 'connecting':
        return (
          <span className="flex items-center gap-1 text-xs text-[var(--color-warning)]">
            <Wifi size={12} className="animate-pulse" />
            Connecting...
          </span>
        )
      case 'error':
        return (
          <span className="flex items-center gap-1 text-xs text-[var(--color-danger)]">
            <WifiOff size={12} />
            Error
          </span>
        )
      default:
        return (
          <span className="flex items-center gap-1 text-xs text-[var(--color-text-secondary)]">
            <WifiOff size={12} />
            Disconnected
          </span>
        )
    }
  }

  return (
    <div className="flex flex-col h-full bg-[var(--color-bg)]">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)] bg-[var(--color-bg-elevated)]">
        <div className="flex items-center gap-3">
          <h2 className="font-display font-medium text-lg text-[var(--color-text)]">
            Create Spec: {projectName}
          </h2>
          <ConnectionIndicator />
        </div>

        <div className="flex items-center gap-2">
          {isComplete && (
            <span className="flex items-center gap-1 text-sm text-[var(--color-success)] font-medium">
              <CheckCircle2 size={16} />
              Complete
            </span>
          )}

          {/* Exit to Project - always visible escape hatch */}
          <button
            onClick={onExitToProject}
            className="btn btn-ghost text-sm py-2"
            title="Exit chat and go to project (you can start the agent manually)"
          >
            <ExternalLink size={16} />
            Exit to Project
          </button>

          <button
            onClick={onCancel}
            className="btn btn-ghost p-2"
            title="Cancel"
          >
            <X size={20} />
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-2 p-3 bg-[var(--color-danger)] text-[var(--color-text-inverse)] border-b border-[var(--color-border)]">
          <AlertCircle size={16} />
          <span className="flex-1 text-sm">{error}</span>
          <button
            onClick={() => setError(null)}
            className="p-1 hover:bg-[var(--color-text-inverse)]/20 rounded"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto py-4">
        {messages.length === 0 && !isLoading && (
          <div className="flex flex-col items-center justify-center h-full text-center p-8">
            <div className="card p-6 max-w-md">
              <h3 className="font-display font-medium text-lg mb-2">
                Starting Spec Creation
              </h3>
              <p className="text-sm text-[var(--color-text-secondary)]">
                Connecting to Claude to help you create your app specification...
              </p>
              {connectionStatus === 'error' && (
                <button
                  onClick={start}
                  className="btn btn-primary mt-4 text-sm"
                >
                  <RotateCcw size={14} />
                  Retry Connection
                </button>
              )}
            </div>
          </div>
        )}

        {messages.map((message) => (
          <ChatMessage key={message.id} message={message} />
        ))}

        {/* Structured questions */}
        {currentQuestions && currentQuestions.length > 0 && (
          <QuestionOptions
            questions={currentQuestions}
            onSubmit={handleAnswerSubmit}
            disabled={isLoading}
          />
        )}

        {/* Typing indicator - don't show when we have questions (waiting for user) */}
        {isLoading && !currentQuestions && <TypingIndicator />}

        {/* Scroll anchor */}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      {!isComplete && (
        <div
          className="p-4 border-t border-[var(--color-border)] bg-[var(--color-bg-elevated)]"
          onDrop={handleDrop}
          onDragOver={handleDragOver}
        >
          {/* Attachment previews */}
          {pendingAttachments.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-3">
              {pendingAttachments.map((attachment) => (
                <div
                  key={attachment.id}
                  className="relative group border border-[var(--color-border)] p-1 bg-[var(--color-bg)] rounded-md shadow-sm"
                >
                  {attachment.isText ? (
                    // Text file preview - show file icon and first few chars
                    <div className="w-16 h-16 flex flex-col items-center justify-center bg-[var(--color-bg-elevated)] rounded text-[var(--color-text-secondary)]">
                      <Paperclip size={20} />
                      <span className="text-[8px] mt-1 uppercase">{attachment.filename.split('.').pop()}</span>
                    </div>
                  ) : (
                    // Image preview
                    <img
                      src={(attachment as ImageAttachment).previewUrl}
                      alt={attachment.filename}
                      className="w-16 h-16 object-cover rounded"
                    />
                  )}
                  <button
                    onClick={() => handleRemoveAttachment(attachment.id)}
                    className="absolute -top-2 -right-2 bg-[var(--color-danger)] text-[var(--color-text-inverse)] rounded-full p-0.5 border border-[var(--color-border)] hover:scale-110 transition-transform"
                    title="Remove attachment"
                  >
                    <X size={12} />
                  </button>
                  <span className="text-xs truncate block max-w-16 mt-1 text-center">
                    {attachment.filename.length > 10
                      ? `${attachment.filename.substring(0, 7)}...`
                      : attachment.filename}
                  </span>
                </div>
              ))}
            </div>
          )}

          <div className="flex gap-3">
            {/* Hidden file input */}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,.txt,.md,.csv,.json,.html,.css,.js,.jsx,.ts,.tsx,.xml,.yaml,.yml,.env,.sh,.py,.rb,.go,.rs,.java,.c,.cpp,.h,.hpp"
              multiple
              onChange={(e) => handleFileSelect(e.target.files)}
              className="hidden"
            />

            {/* Attach button */}
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={connectionStatus !== 'connected'}
              className="btn btn-ghost p-3"
              title="Attach files (images: JPEG/PNG up to 5MB, text files: .txt/.md/.json/etc up to 1MB)"
            >
              <Paperclip size={18} />
            </button>

            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                currentQuestions
                  ? 'Or type a custom response...'
                  : pendingAttachments.length > 0
                    ? 'Add a message with your image(s)...'
                    : 'Type your response... (or /exit to go to project)'
              }
              className="input flex-1"
              disabled={(isLoading && !currentQuestions) || connectionStatus !== 'connected'}
            />
            <button
              onClick={handleSendMessage}
              disabled={
                (!input.trim() && pendingAttachments.length === 0) ||
                (isLoading && !currentQuestions) ||
                connectionStatus !== 'connected'
              }
              className="btn btn-primary px-6"
            >
              <Send size={18} />
            </button>
          </div>

          {/* Help text */}
          <p className="text-xs text-[var(--color-text-secondary)] mt-2">
            Press Enter to send. Drag & drop or click <Paperclip size={12} className="inline" /> to attach files (images or text files like .txt, .md, .json).
          </p>
        </div>
      )}

      {/* Completion footer */}
      {isComplete && (
        <div className={`p-4 border-t border-[var(--color-border)] ${
          initializerStatus === 'error' ? 'bg-[var(--color-danger)]' : 'bg-[var(--color-success)]'
        }`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {initializerStatus === 'starting' ? (
                <>
                  <Loader2 size={20} className="animate-spin" />
                  <span className="font-medium">
                    Starting agent{yoloEnabled ? ' (YOLO mode)' : ''}...
                  </span>
                </>
              ) : initializerStatus === 'error' ? (
                <>
                  <AlertCircle size={20} className="text-[var(--color-text-inverse)]" />
                  <span className="font-medium text-[var(--color-text-inverse)]">
                    {initializerError || 'Failed to start agent'}
                  </span>
                </>
              ) : (
                <>
                  <CheckCircle2 size={20} />
                  <span className="font-medium">Specification created successfully!</span>
                </>
              )}
            </div>
            <div className="flex items-center gap-2">
              {initializerStatus === 'error' && onRetryInitializer && (
                <button
                  onClick={onRetryInitializer}
                  className="btn bg-[var(--color-bg-elevated)] text-[var(--color-text)]"
                >
                  <RotateCcw size={14} />
                  Retry
                </button>
              )}
              {initializerStatus === 'idle' && (
                <>
                  {/* YOLO Mode Toggle */}
                  <button
                    onClick={() => setYoloEnabled(!yoloEnabled)}
                    className={`btn text-sm py-2 px-3 ${
                      yoloEnabled ? 'btn-warning' : 'bg-[var(--color-bg-elevated)] text-[var(--color-text)]'
                    }`}
                    title="YOLO Mode: Skip testing for rapid prototyping"
                  >
                    <Zap size={16} className={yoloEnabled ? 'text-yellow-900' : ''} />
                    <span className={yoloEnabled ? 'text-yellow-900 font-medium' : ''}>
                      YOLO
                    </span>
                  </button>
                  <button
                    onClick={() => onComplete('', yoloEnabled)}
                    className="btn btn-primary"
                  >
                    Continue to Project
                    <ArrowRight size={16} />
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
