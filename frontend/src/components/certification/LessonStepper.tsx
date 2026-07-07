import { useState, useEffect, useCallback, useRef } from 'react'
import { Check, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, Clock, Loader2, Target, Upload } from 'lucide-react'
import { cn } from '../../lib/cn'
import { useToast } from '../../contexts/ToastContext'
import { useAuth } from '../../hooks/useAuth'
import type { CertExercise, LessonSection } from '../../types/certification'
import { LessonContent } from './LessonContent'

function estimateReadTime(content: string): number {
  const words = content.split(/\s+/).length
  return Math.max(1, Math.round(words / 200))
}

export function LessonStepper({
  lessons,
  moduleId,
  exercise,
  onAllLessonsRead,
  onGoToChallenge,
  onStepChange,
  onProvision,
  provisioning,
  isProvisioned,
  hasDocuments,
}: {
  lessons: LessonSection[]
  moduleId: string
  exercise?: CertExercise | null
  onAllLessonsRead?: () => void
  onGoToChallenge: () => void
  onStepChange?: () => void
  onProvision?: () => void
  provisioning?: boolean
  isProvisioned?: boolean
  hasDocuments?: boolean
}) {
  const { user } = useAuth()
  // Resume from localStorage, scoped by user
  const storageKey = `cert-lesson:${user?.user_id || ''}:${moduleId}`
  const [currentIndex, setCurrentIndex] = useState(() => {
    const saved = localStorage.getItem(storageKey)
    const idx = saved ? parseInt(saved, 10) : 0
    return isNaN(idx) || idx < 0 || idx >= lessons.length ? 0 : idx
  })
  const [readLessons, setReadLessons] = useState<Set<number>>(() => new Set([0]))
  const { toast } = useToast()

  // Reset when moduleId changes (component reused for different module)
  useEffect(() => {
    const saved = localStorage.getItem(storageKey)
    const idx = saved ? parseInt(saved, 10) : 0
    setCurrentIndex(isNaN(idx) || idx < 0 || idx >= lessons.length ? 0 : idx)
    setReadLessons(new Set([0]))
  }, [moduleId, storageKey, lessons.length])

  // Clamp index if it ever goes out of bounds
  const safeIndex = currentIndex >= lessons.length ? 0 : currentIndex

  // Keep a stable ref to onStepChange so the scroll effect doesn't re-fire
  // every time the parent re-renders (inline arrow functions change every render)
  const onStepChangeRef = useRef(onStepChange)
  useEffect(() => { onStepChangeRef.current = onStepChange })

  // Scroll parent to top AFTER the new lesson content has rendered.
  // Using useEffect (post-render) instead of calling scroll synchronously in
  // the click handler — synchronous calls fire before React paints the new
  // content, so the browser can negate the scroll when it updates layout.
  const isFirstRender = useRef(true)
  useEffect(() => {
    if (isFirstRender.current) { isFirstRender.current = false; return }
    onStepChangeRef.current?.()
  }, [safeIndex]) // eslint-disable-line react-hooks/exhaustive-deps

  // Persist current lesson to localStorage
  useEffect(() => {
    localStorage.setItem(storageKey, String(safeIndex))
  }, [safeIndex, storageKey])

  // Mark current lesson as read
  useEffect(() => {
    setReadLessons(prev => {
      if (prev.has(safeIndex)) return prev
      return new Set([...prev, safeIndex])
    })
  }, [safeIndex])

  const allRead = readLessons.size >= lessons.length
  const [showChallengePreview, setShowChallengePreview] = useState(false)

  const goNext = useCallback(() => {
    if (safeIndex < lessons.length - 1) {
      const nextIdx = safeIndex + 1
      setCurrentIndex(nextIdx)
      setReadLessons(prev => {
        if (prev.has(nextIdx)) return new Set([...prev])
        toast(`Lesson ${safeIndex + 1} of ${lessons.length} complete!`, 'success')
        return new Set([...prev, nextIdx])
      })
    }
  }, [safeIndex, lessons.length, toast])

  const goPrev = useCallback(() => {
    if (safeIndex > 0) {
      setCurrentIndex(safeIndex - 1)
    }
  }, [safeIndex])

  // Notify when all lessons read
  useEffect(() => {
    if (allRead && onAllLessonsRead) {
      onAllLessonsRead()
    }
  }, [allRead, onAllLessonsRead])

  const isLastLesson = safeIndex === lessons.length - 1
  const readTime = estimateReadTime(lessons[safeIndex].content)
  const lessonMentionsLab = /set up lab/i.test(lessons[safeIndex].content)
  const showInlineLabCta = hasDocuments && lessonMentionsLab && onProvision

  return (
    <div className="space-y-4">
      {/* Progress bar with dots */}
      <div className="flex items-center gap-1.5 px-1">
        {lessons.map((_, i) => (
          <button
            key={i}
            type="button"
            onClick={() => setCurrentIndex(i)}
            aria-label={`Lesson ${i + 1}: ${lessons[i].title}`}
            className={cn(
              'h-2 flex-1 transition-all duration-300',
              i === safeIndex
                ? 'bg-highlight cert-dot-pulse'
                : readLessons.has(i)
                  ? 'bg-green-400'
                  : 'bg-gray-200',
            )}
            style={{
              borderRadius: 'var(--ui-radius, 12px)',
              ...(i === safeIndex ? { background: 'var(--highlight-color)' } : {}),
            }}
            title={`Lesson ${i + 1}: ${lessons[i].title}`}
          />
        ))}
      </div>

      {/* Lesson counter + read time */}
      <div className="flex items-center justify-between px-1">
        <span className="text-xs font-medium text-gray-500">
          Lesson {safeIndex + 1} of {lessons.length}
        </span>
        <span className="flex items-center gap-1 text-xs text-gray-500">
          <Clock size={10} aria-hidden="true" />
          ~{readTime} min read
        </span>
      </div>

      {/* Lesson content with transition */}
      <div className="cert-slide-in" key={safeIndex}>
        <LessonContent section={lessons[safeIndex]} />
      </div>

      {/* Inline Set Up Lab CTA — shown when the lesson references the button */}
      {showInlineLabCta && (
        <div
          className={cn(
            'p-3 border-2 flex items-center justify-between gap-3',
            isProvisioned ? 'border-green-200 bg-green-50/50' : 'border-blue-200 bg-blue-50/50',
          )}
          style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        >
          <div className="flex items-center gap-2 min-w-0">
            {isProvisioned ? (
              <CheckCircle2 size={16} className="text-green-600 shrink-0" />
            ) : (
              <Upload size={16} className="text-blue-600 shrink-0" />
            )}
            <span className={cn('text-sm font-semibold', isProvisioned ? 'text-green-800' : 'text-blue-800')}>
              {isProvisioned ? 'Lab documents are ready' : 'Set up your lab to load the sample document'}
            </span>
          </div>
          <button
            onClick={onProvision}
            disabled={provisioning || isProvisioned}
            className={cn(
              'flex items-center gap-2 px-3 py-1.5 text-sm font-semibold transition-all disabled:opacity-50 shrink-0',
              isProvisioned
                ? 'bg-green-100 text-green-700'
                : 'bg-blue-600 text-white hover:bg-blue-700',
            )}
            style={{ borderRadius: 'var(--ui-radius, 12px)' }}
          >
            {provisioning ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Setting up...
              </>
            ) : isProvisioned ? (
              <>
                <Check size={14} />
                Ready
              </>
            ) : (
              <>
                <Upload size={14} />
                Set Up Lab
              </>
            )}
          </button>
        </div>
      )}

      {/* Challenge preview — shown on last lesson when exercise exists */}
      {isLastLesson && exercise && (
        <div
          className="overflow-hidden border border-amber-200 bg-amber-50/50"
          style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        >
          <button
            onClick={() => setShowChallengePreview(p => !p)}
            className="flex w-full items-center justify-between px-3 py-2 text-left"
          >
            <span className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-amber-700">
              <Target size={12} />
              What you'll do next
            </span>
            <ChevronDown
              size={14}
              className={cn('text-amber-600 transition-transform duration-200', showChallengePreview && 'rotate-180')}
            />
          </button>
          {showChallengePreview && (
            <div className="px-3 pb-3 space-y-1.5">
              {exercise.overview && (
                <p className="text-xs text-amber-800 mb-2 leading-relaxed">{exercise.overview}</p>
              )}
              {exercise.instructions.slice(0, 3).map((step, i) => (
                <div key={i} className="flex items-start gap-2 text-xs text-amber-900">
                  <span className="shrink-0 font-bold">{i + 1}.</span>
                  <span>{step.replace(/\*\*(.+?)\*\*/g, '$1')}</span>
                </div>
              ))}
              {exercise.instructions.length > 3 && (
                <p className="text-xs text-amber-600 italic pl-4">...and {exercise.instructions.length - 3} more steps</p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Navigation buttons */}
      <div className="flex items-center justify-between pt-2">
        <button
          onClick={goPrev}
          disabled={safeIndex === 0}
          className={cn(
            'flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-all',
            'border border-gray-200 hover:border-gray-300 disabled:opacity-30 disabled:cursor-not-allowed',
          )}
          style={{ borderRadius: 'var(--ui-radius, 12px)' }}
        >
          <ChevronLeft size={14} />
          Previous
        </button>

        {isLastLesson ? (
          <button
            onClick={onGoToChallenge}
            className="flex items-center gap-1.5 px-4 py-2 bg-highlight text-highlight-text text-sm font-bold hover:brightness-90 transition-all"
            style={{ borderRadius: 'var(--ui-radius, 12px)' }}
          >
            Go to Challenge
            <ChevronRight size={14} />
          </button>
        ) : (
          <button
            onClick={goNext}
            className="flex items-center gap-1.5 px-4 py-2 bg-highlight text-highlight-text text-sm font-bold hover:brightness-90 transition-all"
            style={{ borderRadius: 'var(--ui-radius, 12px)' }}
          >
            Next
            <ChevronRight size={14} />
          </button>
        )}
      </div>
    </div>
  )
}
