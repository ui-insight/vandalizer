import { useState, useEffect, useCallback, useRef } from 'react'
import { Check, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, Clock, Loader2, Target, Upload } from 'lucide-react'
import { cn } from '../../lib/cn'
import { useToast } from '../../contexts/ToastContext'
import { useAuth } from '../../hooks/useAuth'
import type { CertExercise, LessonSection } from '../../types/certification'
import { LessonContent } from './LessonContent'
import { observeCertificationJourney } from '../../api/certificationJourney'

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
  enrollmentId,
  savedLessonId,
  onSavePosition,
  onReloadPosition,
  manifestSha256,
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
  enrollmentId?: string
  savedLessonId?: string
  onSavePosition?: (lessonId: string) => Promise<void>
  onReloadPosition?: () => Promise<void>
  manifestSha256?: string
}) {
  const { user } = useAuth()
  // Keep legacy numeric positions intact. Versioned positions belong to one
  // enrollment and use authored identities, so other courses cannot reuse them.
  const storageKey = enrollmentId ? `cert-lesson:${user?.user_id || ''}:${enrollmentId}:${moduleId}` : `cert-lesson:${user?.user_id || ''}:${moduleId}`
  const usesServerPosition = Boolean(enrollmentId && onSavePosition)
  const restorePosition = useCallback((): string | number => {
    try {
      if (usesServerPosition) return lessons.some(lesson => lesson.id === savedLessonId) ? savedLessonId! : (lessons[0]?.id ?? 0)
      const saved = localStorage.getItem(storageKey)
      if (enrollmentId) return saved && lessons.some(lesson => lesson.id === saved) ? saved : (lessons[0]?.id ?? 0)
      const idx = saved ? parseInt(saved, 10) : 0
      return Number.isInteger(idx) && idx >= 0 && idx < lessons.length ? idx : 0
    } catch { return lessons[0]?.id ?? 0 }
  }, [storageKey, enrollmentId, lessons, savedLessonId, usesServerPosition])
  const [currentPosition, setCurrentPosition] = useState<string | number>(restorePosition)
  const [positionStatus, setPositionStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const savingPosition = useRef(false)
  const savePlace = useCallback(async (lessonId: string) => {
    if (!onSavePosition || savingPosition.current) return
    savingPosition.current = true
    setPositionStatus('saving')
    try {
      await onSavePosition(lessonId)
      setPositionStatus('saved')
    } catch { setPositionStatus('error') }
    finally { savingPosition.current = false }
  }, [onSavePosition])
  const setCurrentIndex = useCallback((index: number) => {
    if (savingPosition.current) return
    setCurrentPosition(enrollmentId ? (lessons[index]?.id ?? index) : index)
    if (enrollmentId && lessons[index]?.id) void savePlace(lessons[index].id!)
  }, [enrollmentId, lessons, savePlace])
  const [readLessons, setReadLessons] = useState<Set<number>>(() => new Set())
  const { toast } = useToast()

  // Reset when moduleId changes (component reused for different module)
  useEffect(() => {
    setCurrentPosition(restorePosition())
  }, [restorePosition])
  useEffect(() => {
    setReadLessons(new Set())
    setPositionStatus('idle')
  }, [moduleId, enrollmentId])

  // Clamp index if it ever goes out of bounds
  const currentIndex = typeof currentPosition === 'string' ? lessons.findIndex(lesson => lesson.id === currentPosition) : currentPosition
  const safeIndex = currentIndex < 0 || currentIndex >= lessons.length ? 0 : currentIndex
  const observedRestoration = useRef<{ key: string; lessonId?: string; reported: boolean } | null>(null)
  useEffect(() => {
    const key = `${enrollmentId}:${moduleId}`
    if (observedRestoration.current?.key !== key) observedRestoration.current = { key, lessonId: savedLessonId, reported: false }
    const restored = observedRestoration.current
    if (!usesServerPosition || !restored.lessonId || lessons[safeIndex]?.id !== restored.lessonId
      || restored.reported || !manifestSha256) return
    restored.reported = true
    observeCertificationJourney('saved_lesson_displayed', { enrollment_id: enrollmentId, manifest_sha256: manifestSha256 })
  }, [enrollmentId, moduleId, usesServerPosition, savedLessonId, lessons, safeIndex, manifestSha256])

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
  }, [safeIndex])

  // Persist current lesson to localStorage
  useEffect(() => {
    try { localStorage.setItem(storageKey, enrollmentId ? (lessons[safeIndex]?.id ?? '') : String(safeIndex)) } catch { /* Reading still works without local storage. */ }
  }, [safeIndex, storageKey, enrollmentId, lessons])

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
        toast(`Lesson ${safeIndex + 1} of ${lessons.length} viewed`, 'success')
        return new Set([...prev, nextIdx])
      })
    }
  }, [safeIndex, lessons.length, toast, setCurrentIndex])

  const goPrev = useCallback(() => {
    if (safeIndex > 0) {
      setCurrentIndex(safeIndex - 1)
    }
  }, [safeIndex, setCurrentIndex])

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
      {/* Numbered lesson navigation wraps within narrow and docked panels. */}
      <nav aria-label="Lessons in this module" className="grid grid-cols-[repeat(auto-fit,minmax(2.75rem,1fr))] gap-1.5 px-1">
        {lessons.map((_, i) => (
          <button
            key={i}
            type="button"
            disabled={positionStatus === 'saving'}
            onClick={() => setCurrentIndex(i)}
            aria-label={`Lesson ${i + 1}: ${lessons[i].title}${readLessons.has(i) ? ", viewed" : ""}`}
            aria-current={i === safeIndex ? "step" : undefined}
            className={cn(
              'min-h-11 min-w-0 text-sm font-semibold transition-colors duration-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gray-900',
              i === safeIndex
                ? 'bg-highlight text-highlight-text ring-2 ring-inset ring-highlight-text'
                : readLessons.has(i)
                  ? 'bg-green-400 text-gray-900'
                  : 'bg-gray-200 text-gray-900',
            )}
            style={{
              borderRadius: 'var(--ui-radius, 12px)',
              ...(i === safeIndex ? { background: 'var(--highlight-color)' } : {}),
            }}
            title={`Lesson ${i + 1}: ${lessons[i].title}`}
          ><span aria-hidden="true">{i + 1}</span></button>
        ))}
      </nav>

      {enrollmentId && onSavePosition && (
        <div className="flex flex-wrap items-center gap-2 px-1 text-xs text-gray-600">
          <span role="status">{positionStatus === 'saving' ? 'Saving your place…' : positionStatus === 'saved' ? 'Place saved across devices.' : positionStatus === 'error' ? 'Your place could not be saved. Reload the saved place before trying again.' : 'Lesson navigation saves your place across devices.'}</span>
          {positionStatus === 'error' && <button type="button" className="underline font-medium" onClick={() => { void onReloadPosition?.() }}>Refresh progress</button>}
          <button type="button" className="underline font-medium disabled:opacity-50" disabled={positionStatus === 'saving'} onClick={() => { if (lessons[safeIndex].id) void savePlace(lessons[safeIndex].id!) }}>Save this place</button>
        </div>
      )}

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
        <LessonContent section={lessons[safeIndex]} manifestSha256={manifestSha256} practiceScope={lessons[safeIndex].id && lessons[safeIndex].revision ? {
          userId: user?.user_id || '', enrollmentId, moduleId, lessonId: lessons[safeIndex].id!, revision: lessons[safeIndex].revision!,
        } : undefined} />
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
              {isProvisioned ? 'Sample files are assigned; check their status above' : 'Set up your lab to load the sample document'}
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
                Assigned
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
          disabled={safeIndex === 0 || positionStatus === 'saving'}
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
            disabled={positionStatus === 'saving'}
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
