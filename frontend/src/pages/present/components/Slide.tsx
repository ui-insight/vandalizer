import type { Slide as SlideData } from '../content'
import { Markdown } from '../markdown'
import { cn } from '../../../lib/cn'

interface SlideProps {
  slide: SlideData
  /** Compact rendering for the print handout (smaller type, dark-on-light). */
  variant?: 'deck' | 'print'
}

/**
 * Renders one slide's content. Shared by the presenter Deck and the print
 * handout so the two can never drift. Markdown body is rendered through the
 * sanitized pipeline; the `.deck-prose` class (index.css) sizes headings,
 * lists, tables and code for a projector.
 */
export function Slide({ slide, variant = 'deck' }: SlideProps) {
  const isPrint = variant === 'print'
  return (
    <div className={cn('w-full', isPrint ? 'max-w-3xl' : 'max-w-4xl mx-auto')}>
      <h2
        className={cn(
          'font-bold tracking-tight',
          isPrint ? 'text-2xl text-black mb-4' : 'text-3xl sm:text-5xl text-white mb-8',
        )}
      >
        {slide.title}
      </h2>
      <Markdown
        source={slide.body}
        className={cn('deck-prose', isPrint ? 'deck-prose--print' : 'text-gray-200')}
      />
      {slide.note && (
        <p
          className={cn(
            'no-print mt-8 text-sm italic',
            isPrint ? 'hidden' : 'text-gray-500',
          )}
        >
          <span className="font-semibold not-italic text-gray-400">Note: </span>
          {slide.note}
        </p>
      )}
    </div>
  )
}
