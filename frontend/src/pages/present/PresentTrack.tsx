import { Presentation, Printer } from 'lucide-react'
import type { Track } from './content'
import { Markdown } from './markdown'
import { ElevatorPitchCard } from './components/ElevatorPitchCard'

interface PresentTrackProps {
  track: Track
  /** Open the presenter deck (sets ?mode=deck). */
  onPresent: () => void
  /** Print the full handout. */
  onPrint: () => void
  /** Emphasize a pitch variant from ?pitch. */
  pitchHighlight?: 'spoken' | 'written'
}

export function PresentTrack({ track, onPresent, onPrint, pitchHighlight }: PresentTrackProps) {
  const Icon = track.icon
  return (
    <div id="main-content" tabIndex={-1} className="space-y-12">
      {/* Hero */}
      <header>
        <div className="flex items-center gap-3 mb-4">
          <span className="flex h-11 w-11 items-center justify-center rounded-lg bg-[#f1b300]/10 text-[#f1b300]">
            <Icon className="w-6 h-6" />
          </span>
          <div>
            <h1 className="text-3xl sm:text-4xl font-bold text-white tracking-tight">
              {track.label}
            </h1>
            <p className="text-gray-500">{track.tagline}</p>
          </div>
        </div>

        <ul className="grid gap-2 sm:grid-cols-2 mt-6">
          {track.valueProps.map((vp) => (
            <li key={vp} className="flex items-start gap-2 text-gray-300">
              <span className="text-[#f1b300] mt-1 leading-none">&#x2022;</span>
              <span>{vp}</span>
            </li>
          ))}
        </ul>

        <div className="flex flex-wrap items-center gap-3 mt-7">
          <button
            onClick={onPresent}
            className="inline-flex items-center gap-2 rounded-lg bg-[#f1b300] px-4 py-2.5 text-sm font-bold text-black hover:bg-[#d49e00] transition-colors"
          >
            <Presentation className="w-4 h-4" />
            Present ({track.slides.length} slides)
          </button>
          <button
            onClick={onPrint}
            className="inline-flex items-center gap-2 rounded-lg border border-white/15 px-4 py-2.5 text-sm font-medium text-gray-200 hover:bg-white/10 transition-colors"
          >
            <Printer className="w-4 h-4" />
            Print / PDF
          </button>
        </div>
      </header>

      {/* Elevator pitch */}
      <section>
        <h2 className="text-sm font-bold uppercase tracking-wider text-[#f1b300] mb-4">
          Elevator pitch
        </h2>
        <ElevatorPitchCard pitch={track.pitch} highlight={pitchHighlight} />
      </section>

      {/* Long-form sections */}
      <section className="space-y-10">
        {track.sections.map((s) => (
          <div key={s.id} className="border-t border-white/10 pt-8">
            <h2 className="text-2xl font-bold text-white mb-3">{s.heading}</h2>
            <Markdown source={s.body} className="deck-prose deck-prose--read text-gray-300" />
          </div>
        ))}
      </section>
    </div>
  )
}
