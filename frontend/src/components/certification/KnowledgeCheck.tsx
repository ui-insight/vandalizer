import { useState } from 'react'
import { CheckCircle2, HelpCircle, XCircle } from 'lucide-react'
import { cn } from '../../lib/cn'
import type { KnowledgeCheckData } from '../../types/certification'

export function KnowledgeCheck({ data }: { data: KnowledgeCheckData }) {
  const [selected, setSelected] = useState<number | null>(null)
  const answered = selected !== null

  return (
    <div
      className="my-4 p-4 border-2 border-indigo-200 bg-indigo-50/30"
      style={{ borderRadius: 'var(--ui-radius, 12px)' }}
    >
      <div className="flex items-center gap-2 mb-3">
        <HelpCircle size={16} className="text-indigo-500" />
        <span className="text-xs font-bold uppercase tracking-wider text-indigo-500">Knowledge Check</span>
      </div>
      <p className="text-sm font-medium text-gray-900 mb-3">{data.question}</p>
      <div className="space-y-2">
        {data.options.map((opt, i) => {
          const isSelected = selected === i
          const isCorrect = opt.correct
          const showResult = answered

          return (
            <button
              key={i}
              onClick={() => { if (!answered) setSelected(i) }}
              disabled={answered}
              className={cn(
                'w-full text-left flex items-start gap-2.5 p-3 border transition-all text-sm',
                !answered && 'cursor-pointer hover:border-indigo-300 hover:bg-indigo-50/50',
                answered && 'cursor-default',
                !showResult && 'border-gray-200 bg-white',
                showResult && isSelected && isCorrect && 'border-green-400 bg-green-50',
                showResult && isSelected && !isCorrect && 'border-amber-400 bg-amber-50',
                showResult && !isSelected && isCorrect && 'border-green-300 bg-green-50/50',
                showResult && !isSelected && !isCorrect && 'border-gray-200 bg-gray-50 opacity-60',
              )}
              style={{ borderRadius: 'var(--ui-radius, 12px)' }}
            >
              <div className="shrink-0 mt-0.5">
                {showResult && isCorrect ? (
                  <CheckCircle2 size={16} className="text-green-600" />
                ) : showResult && isSelected && !isCorrect ? (
                  <XCircle size={16} className="text-amber-600" />
                ) : (
                  <div className={cn(
                    'w-4 h-4 rounded-full border-2',
                    isSelected ? 'border-indigo-500 bg-indigo-500' : 'border-gray-300',
                  )} />
                )}
              </div>
              <div className="flex-1">
                <span className={cn(
                  showResult && isCorrect && 'font-medium text-green-800',
                  showResult && isSelected && !isCorrect && 'text-amber-800',
                  !showResult && 'text-gray-700',
                )}>
                  {opt.text}
                </span>
                {showResult && (isSelected || isCorrect) && (
                  <p className={cn(
                    'text-xs mt-1',
                    isCorrect ? 'text-green-600' : 'text-amber-600',
                  )}>
                    {isSelected && !isCorrect ? `Not quite \u2014 ${opt.explanation}` : opt.explanation}
                  </p>
                )}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
