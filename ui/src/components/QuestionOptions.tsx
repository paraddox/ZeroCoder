/**
 * Question Options Component
 *
 * Renders structured questions from AskUserQuestion tool.
 * Shows clickable option buttons with soft editorial styling.
 */

import { useState } from 'react'
import { Check } from 'lucide-react'
import type { SpecQuestion } from '../lib/types'

interface QuestionOptionsProps {
  questions: SpecQuestion[]
  onSubmit: (answers: Record<string, string | string[]>) => void
  disabled?: boolean
}

export function QuestionOptions({
  questions,
  onSubmit,
  disabled = false,
}: QuestionOptionsProps) {
  // Track selected answers for each question
  const [answers, setAnswers] = useState<Record<string, string | string[]>>({})
  const [customInputs, setCustomInputs] = useState<Record<string, string>>({})
  const [showCustomInput, setShowCustomInput] = useState<Record<string, boolean>>({})

  const handleOptionClick = (questionIdx: number, optionLabel: string, multiSelect: boolean) => {
    const key = String(questionIdx)

    if (optionLabel === 'Other') {
      setShowCustomInput((prev) => ({ ...prev, [key]: true }))
      return
    }

    setShowCustomInput((prev) => ({ ...prev, [key]: false }))

    setAnswers((prev) => {
      if (multiSelect) {
        const current = (prev[key] as string[]) || []
        if (current.includes(optionLabel)) {
          return { ...prev, [key]: current.filter((o) => o !== optionLabel) }
        } else {
          return { ...prev, [key]: [...current, optionLabel] }
        }
      } else {
        return { ...prev, [key]: optionLabel }
      }
    })
  }

  const handleCustomInputChange = (questionIdx: number, value: string) => {
    const key = String(questionIdx)
    setCustomInputs((prev) => ({ ...prev, [key]: value }))
    setAnswers((prev) => ({ ...prev, [key]: value }))
  }

  const handleSubmit = () => {
    // Ensure all questions have answers
    const finalAnswers: Record<string, string | string[]> = {}

    questions.forEach((_, idx) => {
      const key = String(idx)
      if (showCustomInput[key] && customInputs[key]) {
        finalAnswers[key] = customInputs[key]
      } else if (answers[key]) {
        finalAnswers[key] = answers[key]
      }
    })

    onSubmit(finalAnswers)
  }

  const isOptionSelected = (questionIdx: number, optionLabel: string, multiSelect: boolean) => {
    const key = String(questionIdx)
    const answer = answers[key]

    if (multiSelect) {
      return Array.isArray(answer) && answer.includes(optionLabel)
    }
    return answer === optionLabel
  }

  const hasAnswer = (questionIdx: number) => {
    const key = String(questionIdx)
    return !!(answers[key] || (showCustomInput[key] && customInputs[key]))
  }

  const allQuestionsAnswered = questions.every((_, idx) => hasAnswer(idx))

  return (
    <div className="space-y-6 p-4">
      {questions.map((q, questionIdx) => (
        <div
          key={questionIdx}
          className="card p-4 bg-[var(--color-bg)]"
        >
          {/* Question header */}
          <div className="flex items-center gap-3 mb-4">
            <span className="badge bg-[var(--color-accent)] text-[var(--color-text-inverse)]">
              {q.header}
            </span>
            <span className="font-medium text-[var(--color-text)]">
              {q.question}
            </span>
            {q.multiSelect && (
              <span className="text-xs text-[var(--color-text-secondary)] font-mono">
                (select multiple)
              </span>
            )}
          </div>

          {/* Options grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {q.options.map((opt, optIdx) => {
              const isSelected = isOptionSelected(questionIdx, opt.label, q.multiSelect)

              return (
                <button
                  key={optIdx}
                  onClick={() => handleOptionClick(questionIdx, opt.label, q.multiSelect)}
                  disabled={disabled}
                  className={`
                    text-left p-4
                    border border-[var(--color-border)] rounded-md
                    transition-all duration-150
                    ${
                      isSelected
                        ? 'bg-[var(--color-pending)] shadow-sm'
                        : 'bg-[var(--color-bg)] shadow-sm hover:shadow-md hover:border-[var(--color-accent)]'
                    }
                    disabled:opacity-50 disabled:cursor-not-allowed
                  `}
                >
                  <div className="flex items-start gap-2">
                    {/* Checkbox/Radio indicator */}
                    <div
                      className={`
                        w-5 h-5 flex-shrink-0 mt-0.5
                        border border-[var(--color-border)]
                        flex items-center justify-center
                        ${q.multiSelect ? 'rounded' : 'rounded-full'}
                        ${isSelected ? 'bg-[var(--color-done)] border-[var(--color-done)]' : 'bg-[var(--color-bg)]'}
                      `}
                    >
                      {isSelected && <Check size={12} strokeWidth={2} className="text-[var(--color-text-inverse)]" />}
                    </div>

                    <div className="flex-1">
                      <div className="font-medium text-[var(--color-text)]">
                        {opt.label}
                      </div>
                      <div className="text-sm text-[var(--color-text-secondary)] mt-1">
                        {opt.description}
                      </div>
                    </div>
                  </div>
                </button>
              )
            })}

            {/* "Other" option */}
            <button
              onClick={() => handleOptionClick(questionIdx, 'Other', q.multiSelect)}
              disabled={disabled}
              className={`
                text-left p-4
                border border-[var(--color-border)] rounded-md
                transition-all duration-150
                ${
                  showCustomInput[String(questionIdx)]
                    ? 'bg-[var(--color-pending)] shadow-sm'
                    : 'bg-[var(--color-bg)] shadow-sm hover:shadow-md hover:border-[var(--color-accent)]'
                }
                disabled:opacity-50 disabled:cursor-not-allowed
              `}
            >
              <div className="flex items-start gap-2">
                <div
                  className={`
                    w-5 h-5 flex-shrink-0 mt-0.5
                    border border-[var(--color-border)]
                    flex items-center justify-center
                    ${q.multiSelect ? 'rounded' : 'rounded-full'}
                    ${showCustomInput[String(questionIdx)] ? 'bg-[var(--color-done)] border-[var(--color-done)]' : 'bg-[var(--color-bg)]'}
                  `}
                >
                  {showCustomInput[String(questionIdx)] && <Check size={12} strokeWidth={2} className="text-[var(--color-text-inverse)]" />}
                </div>

                <div className="flex-1">
                  <div className="font-medium text-[var(--color-text)]">Other</div>
                  <div className="text-sm text-[var(--color-text-secondary)] mt-1">
                    Provide a custom answer
                  </div>
                </div>
              </div>
            </button>
          </div>

          {/* Custom input field */}
          {showCustomInput[String(questionIdx)] && (
            <div className="mt-4">
              <input
                type="text"
                value={customInputs[String(questionIdx)] || ''}
                onChange={(e) => handleCustomInputChange(questionIdx, e.target.value)}
                placeholder="Type your answer..."
                className="input"
                autoFocus
                disabled={disabled}
              />
            </div>
          )}
        </div>
      ))}

      {/* Submit button */}
      <div className="flex justify-end">
        <button
          onClick={handleSubmit}
          disabled={disabled || !allQuestionsAnswered}
          className="btn btn-primary"
        >
          Continue
        </button>
      </div>
    </div>
  )
}
