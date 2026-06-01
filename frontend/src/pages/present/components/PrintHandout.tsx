import type { Slide as SlideData } from '../content'
import { Slide } from './Slide'

/**
 * Hidden on screen (`print:block`), shown only when printing. Stacks every
 * slide one-per-page so Cmd/Ctrl-P always emits the full handout regardless of
 * which deck slide is showing. The @media print rules in index.css handle the
 * page breaks and force an ink-friendly light background.
 */
export function PrintHandout({
  slides,
  title,
}: {
  slides: SlideData[]
  title: string
}) {
  return (
    <div className="print-handout hidden print:block">
      <h1 className="text-3xl font-bold text-black mb-2">Vandalizer</h1>
      <p className="text-lg text-gray-700 mb-8">{title}</p>
      {slides.map((slide) => (
        <section key={slide.id} className="print-slide">
          <Slide slide={slide} variant="print" />
        </section>
      ))}
    </div>
  )
}
