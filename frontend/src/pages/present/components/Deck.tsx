import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, X, Maximize2, Printer } from 'lucide-react'
import type { Slide as SlideData } from '../content'
import { Slide } from './Slide'
import { usePresentNav } from '../usePresentNav'
import { cn } from '../../../lib/cn'

export interface DeckProps {
  slides: SlideData[]
  /** Zero-based starting slide. */
  initialIndex?: number
  /** Track label, shown in the deck chrome. */
  title?: string
  onClose: () => void
  /** Notified on every index change so the route can sync ?slide. */
  onIndexChange?: (index: number) => void
  /** Print the full handout (all slides). */
  onPrint?: () => void
}

/**
 * Full-screen presenter overlay. A fixed CSS overlay (not the Fullscreen API)
 * so it works in every browser without a user-gesture requirement; a Maximize
 * button offers true fullscreen on top. Keyboard nav via usePresentNav.
 */
export function Deck({
  slides,
  initialIndex = 0,
  title,
  onClose,
  onIndexChange,
  onPrint,
}: DeckProps) {
  const count = slides.length
  const clampedInitial = Math.min(Math.max(initialIndex, 0), count - 1)
  const [index, setIndex] = useState(clampedInitial)

  const goTo = (i: number) => {
    const next = Math.min(Math.max(i, 0), count - 1)
    setIndex(next)
    onIndexChange?.(next)
  }

  usePresentNav({ count, index, onIndex: goTo, onClose })

  // Lock body scroll while the overlay is open; restore + exit fullscreen on close.
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
      if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {})
    }
  }, [])

  const requestFullscreen = () => {
    try {
      if (document.fullscreenElement) document.exitFullscreen?.()
      else document.documentElement.requestFullscreen?.()
    } catch {
      /* fullscreen is best-effort; the CSS overlay already fills the screen */
    }
  }

  const slide = slides[index]

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title ? `${title} — presentation` : 'Presentation'}
      className="no-print fixed inset-0 z-[100] flex flex-col bg-[#0a0a0a] text-white"
    >
      {/* Top chrome */}
      <div className="no-print flex items-center justify-between px-4 sm:px-6 py-3 border-b border-white/10">
        <div className="flex items-center gap-3 text-sm">
          <span className="font-bold text-white">Vandalizer</span>
          {title && <span className="text-[#f1b300]">{title}</span>}
        </div>
        <div className="flex items-center gap-1">
          {onPrint && (
            <button
              onClick={onPrint}
              aria-label="Print handout"
              className="p-2 rounded-md text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
            >
              <Printer className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={requestFullscreen}
            aria-label="Toggle fullscreen"
            className="p-2 rounded-md text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
          >
            <Maximize2 className="w-4 h-4" />
          </button>
          <button
            onClick={onClose}
            aria-label="Exit presentation"
            className="p-2 rounded-md text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Slide stage */}
      <div className="relative flex-1 min-h-0 flex items-center justify-center px-6 sm:px-16 py-8 overflow-y-auto">
        {/* Prev / next click zones (chevrons) */}
        <button
          onClick={() => goTo(index - 1)}
          disabled={index === 0}
          aria-label="Previous slide"
          className="no-print absolute left-2 sm:left-4 top-1/2 -translate-y-1/2 p-2 rounded-full text-gray-500 hover:text-white hover:bg-white/10 disabled:opacity-20 disabled:hover:bg-transparent transition-colors"
        >
          <ChevronLeft className="w-7 h-7" />
        </button>
        <Slide slide={slide} />
        <button
          onClick={() => goTo(index + 1)}
          disabled={index === count - 1}
          aria-label="Next slide"
          className="no-print absolute right-2 sm:right-4 top-1/2 -translate-y-1/2 p-2 rounded-full text-gray-500 hover:text-white hover:bg-white/10 disabled:opacity-20 disabled:hover:bg-transparent transition-colors"
        >
          <ChevronRight className="w-7 h-7" />
        </button>
      </div>

      {/* Bottom chrome: dots + counter + hint */}
      <div className="no-print flex items-center justify-between px-4 sm:px-6 py-3 border-t border-white/10">
        <div className="flex items-center gap-1.5">
          {slides.map((s, i) => (
            <button
              key={s.id}
              onClick={() => goTo(i)}
              aria-label={`Go to slide ${i + 1}`}
              aria-current={i === index}
              className={cn(
                'h-2 rounded-full transition-all',
                i === index ? 'w-6 bg-[#f1b300]' : 'w-2 bg-white/20 hover:bg-white/40',
              )}
            />
          ))}
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <span className="hidden sm:inline">← → to navigate · Esc to exit</span>
          <span className="tabular-nums text-gray-400">
            {index + 1} / {count}
          </span>
        </div>
      </div>
    </div>
  )
}
