import { useCallback, useLayoutEffect, useRef, useState } from 'react'

/** A spot on a page: the element path the embed script reported and its text. */
export interface PageSpot { path: string | null; text: string }

/** One outer scroll, while authored HTML remains isolated from the application.
 *
 * Page feedback: with `picking`, a click inside the page reports the clicked
 * element to `onPick` instead of acting on it; with `spot`, that element is
 * outlined and scrolled into view (`onSpotShown` says whether it was found).
 */
export function PublishedPageContent({ src, picking = false, onPick, spot, onSpotShown }: {
  src: string
  picking?: boolean
  onPick?: (spot: PageSpot) => void
  spot?: PageSpot | null
  onSpotShown?: (found: boolean) => void
}) {
  const frame = useRef<HTMLIFrameElement>(null)
  const [height, setHeight] = useState<number>()
  const [loaded, setLoaded] = useState(false)
  const handlers = useRef({ onPick, onSpotShown })
  handlers.current = { onPick, onSpotShown }
  useLayoutEffect(() => {
    const receive = (event: MessageEvent) => {
      if (!frame.current?.contentWindow || event.source !== frame.current.contentWindow) return
      const data: unknown = event.data
      if (!data || typeof data !== 'object' || !('type' in data)) return
      if (data.type === 'vandalizer:page-pick') {
        const d = data as { path?: unknown; text?: unknown }
        handlers.current.onPick?.({
          path: typeof d.path === 'string' && /^\d{1,4}(\/\d{1,4}){0,40}$/.test(d.path) ? d.path : null,
          text: typeof d.text === 'string' ? d.text.slice(0, 300) : '',
        })
        return
      }
      if (data.type === 'vandalizer:spot-shown') {
        const d = data as { found?: unknown; top?: unknown }
        if (d.found === true && typeof d.top === 'number' && Number.isFinite(d.top) && frame.current) {
          const at = frame.current.getBoundingClientRect().top + window.scrollY + d.top - 120
          window.scrollTo?.({ top: Math.max(0, at), behavior: 'smooth' })
        }
        handlers.current.onSpotShown?.(d.found === true)
        return
      }
      if (data.type !== 'vandalizer:page-height'
        || !('height' in data) || typeof data.height !== 'number' || !Number.isFinite(data.height)
        || data.height < 1 || data.height > 1_000_000) return
      setHeight(Math.ceil(data.height))
    }
    window.addEventListener('message', receive)
    return () => window.removeEventListener('message', receive)
  }, [])
  const send = useCallback((message: Record<string, unknown>) => {
    frame.current?.contentWindow?.postMessage(message, '*')
  }, [])
  useLayoutEffect(() => { if (loaded) send({ type: 'vandalizer:pick-mode', on: picking }) }, [loaded, picking, send])
  useLayoutEffect(() => {
    if (loaded && spot) send({ type: 'vandalizer:show-spot', path: spot.path ?? '', text: spot.text })
  }, [loaded, spot, send])
  const url = `${src}${src.includes('?') ? '&' : '?'}view=embed`
  return <iframe ref={frame} className="page-published-content" title="Published page content" src={url}
    sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer"
    onLoad={() => setLoaded(true)}
    style={height ? { height } : undefined} />
}
