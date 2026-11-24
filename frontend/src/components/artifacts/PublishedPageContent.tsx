import { useCallback, useLayoutEffect, useRef, useState } from 'react'
import type { PageTextEdit } from '../../api/artifacts'

/** A spot on a page: the element path the embed script reported and its text. */
export interface PageSpot { path: string | null; text: string }

/** One outer scroll, while authored HTML remains isolated from the application.
 *
 * Page feedback: with `picking`, a click inside the page reports the clicked
 * element to `onPick` instead of acting on it; with `spot`, that element is
 * outlined and scrolled into view (`onSpotShown` says whether it was found).
 */
export function PublishedPageContent({ src, picking = false, onPick, spot, onSpotShown, editing = false, onEditCount, collect = 0, onEdits }: {
  src: string
  picking?: boolean
  onPick?: (spot: PageSpot) => void
  spot?: PageSpot | null
  onSpotShown?: (found: boolean) => void
  /** Edit text: the page's text blocks become editable in place (owner only). */
  editing?: boolean
  onEditCount?: (count: number) => void
  /** Bump to ask the frame for the changed blocks; they arrive in `onEdits`. */
  collect?: number
  onEdits?: (edits: PageTextEdit[]) => void
}) {
  const frame = useRef<HTMLIFrameElement>(null)
  const [height, setHeight] = useState<number>()
  const [loaded, setLoaded] = useState(false)
  const handlers = useRef({ onPick, onSpotShown, onEditCount, onEdits })
  handlers.current = { onPick, onSpotShown, onEditCount, onEdits }
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
      if (data.type === 'vandalizer:edit-count') {
        const count = (data as { count?: unknown }).count
        if (typeof count === 'number' && Number.isInteger(count) && count >= 0) handlers.current.onEditCount?.(count)
        return
      }
      if (data.type === 'vandalizer:edits') {
        const raw = (data as { edits?: unknown }).edits
        const edits = Array.isArray(raw) ? raw.filter((e): e is PageTextEdit => !!e && typeof e === 'object'
          && typeof e.tag === 'string' && /^[a-z0-9]{1,12}$/.test(e.tag) && Number.isInteger(e.index) && e.index >= 0
          && typeof e.original === 'string' && typeof e.text === 'string').slice(0, 200) : []
        handlers.current.onEdits?.(edits)
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
  useLayoutEffect(() => { if (loaded) send({ type: 'vandalizer:edit-mode', on: editing }) }, [loaded, editing, send])
  useLayoutEffect(() => { if (loaded && editing && collect > 0) send({ type: 'vandalizer:edit-collect' }) }, [loaded, editing, collect, send])
  useLayoutEffect(() => {
    if (loaded && spot) send({ type: 'vandalizer:show-spot', path: spot.path ?? '', text: spot.text })
  }, [loaded, spot, send])
  const url = `${src}${src.includes('?') ? '&' : '?'}view=embed`
  return <iframe ref={frame} className="page-published-content" title="Published page content" src={url}
    sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox" referrerPolicy="no-referrer"
    onLoad={() => setLoaded(true)}
    style={height ? { height } : undefined} />
}
