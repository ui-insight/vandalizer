import { useState, useEffect, useCallback } from 'react'
import { ChevronLeft, ChevronRight, Clock } from 'lucide-react'
import { cn } from '../../lib/cn'
import { useToast } from '../../contexts/ToastContext'
import type { LessonSection } from '../../types/certification'
import { LessonContent } from './LessonContent'

function estimateReadTime(content: string): number {
  const words = content.split(/\s+/).length
  return Math.max(1, Math.round(words / 200))
}

export function LessonStepper({
  lessons,
  moduleId,
  onAllLessonsRead,
  onGoToChallenge,
}: {
  lessons: LessonSection[]
  moduleId: string
  onAllLessonsRead?: () => void
  onGoToChallenge: () => void
}) {
  // Resume from localStorage
  const storageKey = `cert-lesson-${moduleId}`
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

  const goNext = useCallback(() => {
    if (safeIndex < lessons.length - 1) {
      const nextIdx = safeIndex + 1
      setCurrentIndex(nextIdx)
      setReadLessons(prev => new Set([...prev, nextIdx]))
      toast(`Lesson ${safeIndex + 1} of ${lessons.length} complete!`, 'success')
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

  return (
    <div className="space-y-4">
      {/* Progress bar with dots */}
      <div className="flex items-center gap-1.5 px-1">
        {lessons.map((_, i) => (
          <button
            key={i}
            onClick={() => setCurrentIndex(i)}
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
        <span className="flex items-center gap-1 text-xs text-gray-400">
          <Clock size={10} />
          ~{readTime} min read
        </span>
      </div>

      {/* Lesson content with transition */}
      <div className="cert-slide-in" key={safeIndex}>
        <LessonContent section={lessons[safeIndex]} />
      </div>

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
