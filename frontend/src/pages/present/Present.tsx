import { Navigate, useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { PresentShell } from './components/PresentShell'
import { PresentHub } from './PresentHub'
import { PresentTrack } from './PresentTrack'
import { Deck } from './components/Deck'
import { PrintHandout } from './components/PrintHandout'
import { getTrack } from './content'

type PresentSearch = {
  mode?: 'deck'
  slide?: number
  pitch?: 'spoken' | 'written'
}

/**
 * Route component for /docs/present and /docs/present/$audience.
 * - no audience  → hub (audience picker + pitch strip)
 * - audience     → read page, with ?mode=deck opening the presenter overlay,
 *                  ?slide=N selecting a slide, ?pitch=spoken|written highlighting.
 */
export default function Present() {
  const params = useParams({ strict: false }) as { audience?: string }
  const search = useSearch({ strict: false }) as PresentSearch
  const navigate = useNavigate()

  const track = getTrack(params.audience)

  // Hub
  if (!params.audience) {
    return (
      <>
        <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-[1000] focus:rounded-md focus:bg-white focus:px-4 focus:py-2 focus:shadow-lg focus:ring-2 focus:ring-highlight">Skip to main content</a>
        <PresentShell showSidebar={false}>
          <PresentHub />
        </PresentShell>
      </>
    )
  }

  // Unknown audience → back to the hub
  if (!track) {
    return <Navigate to="/docs/present" />
  }

  const audience = track.id
  const deckOpen = search.mode === 'deck'
  const initialIndex = Math.max(0, (search.slide ?? 1) - 1)

  const openDeck = () =>
    navigate({
      to: '/docs/present/$audience',
      params: { audience },
      search: { mode: 'deck', slide: search.slide, pitch: search.pitch },
    })

  const closeDeck = () =>
    navigate({
      to: '/docs/present/$audience',
      params: { audience },
      search: { mode: undefined, slide: undefined, pitch: search.pitch },
      replace: true,
    })

  const syncSlide = (index: number) =>
    navigate({
      to: '/docs/present/$audience',
      params: { audience },
      search: { mode: 'deck', slide: index + 1, pitch: search.pitch },
      replace: true,
    })

  const print = () => window.print()

  return (
    <>
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-[1000] focus:rounded-md focus:bg-white focus:px-4 focus:py-2 focus:shadow-lg focus:ring-2 focus:ring-highlight">Skip to main content</a>
      {/* On-screen read view — hidden when printing (the handout prints instead) */}
      <div className="no-print">
        <PresentShell activeAudience={audience}>
          <PresentTrack
            track={track}
            onPresent={openDeck}
            onPrint={print}
            pitchHighlight={search.pitch}
          />
        </PresentShell>
      </div>

      {/* Printable handout: hidden on screen, all slides one-per-page in print */}
      <PrintHandout slides={track.slides} title={track.label} />

      {/* Presenter overlay */}
      {deckOpen && (
        <Deck
          slides={track.slides}
          initialIndex={initialIndex}
          title={track.label}
          onClose={closeDeck}
          onIndexChange={syncSlide}
          onPrint={print}
        />
      )}
    </>
  )
}
