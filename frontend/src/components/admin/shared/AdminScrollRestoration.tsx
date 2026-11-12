import { useCallback, useLayoutEffect, useRef, type ReactNode } from 'react'
import { useAdminViewState } from './AdminViewState'

/** Wait for asynchronously loaded content before restoring its saved position.
 * Any deliberate input cancels restoration so it never fights the reader. */
export function restoreAdminScroll(container: HTMLElement, content: HTMLElement, top: number) {
  let stopped = false
  let resize: ResizeObserver | undefined
  const stop = () => {
    stopped = true
    resize?.disconnect()
    mutations?.disconnect()
    for (const event of ['wheel', 'touchstart', 'pointerdown', 'keydown']) container.removeEventListener(event, stop)
  }
  const restore = () => {
    if (stopped || container.scrollHeight - container.clientHeight + 1 < top) return
    container.scrollTop = top
    stop()
  }
  for (const event of ['wheel', 'touchstart', 'pointerdown', 'keydown']) container.addEventListener(event, stop, { passive: true })
  if (typeof ResizeObserver !== 'undefined') { resize = new ResizeObserver(restore); resize.observe(content) }
  const mutations = new MutationObserver(restore)
  mutations.observe(content, { childList: true, subtree: true })
  restore()
  return { stop, pending: () => !stopped }
}

export function AdminScrollRestoration({ section, children }: { section: string; children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useAdminViewState(`scroll:${section}`, 0)
  const initial = useRef(position)
  useLayoutEffect(() => {
    const content = root.current
    const container = content?.closest('main')?.parentElement
    if (!content || !container) return
    const restoration = restoreAdminScroll(container, content, initial.current)
    let last = initial.current
    const remember = () => { if (!restoration.pending()) last = container.scrollTop }
    container.addEventListener('scroll', remember)
    return () => {
      remember()
      restoration.stop()
      container.removeEventListener('scroll', remember)
      setPosition(last)
    }
  }, [setPosition])
  return <div ref={root}>{children}</div>
}

/** Details temporarily replace a loaded list; return to its exact position. */
export function useAdminDetailScroll(detailId: string | null, onSelect: (id: string | null) => void) {
  const listTop = useRef(0)
  const previous = useRef<string | null>(null)
  useLayoutEffect(() => {
    const content = document.getElementById('main-content')
    const container = content?.parentElement
    if (!container || !content) return
    let restoration: ReturnType<typeof restoreAdminScroll> | undefined
    if (detailId && !previous.current) {
      container.scrollTop = 0
    } else if (!detailId && previous.current) {
      restoration = restoreAdminScroll(container, content, listTop.current)
    }
    previous.current = detailId
    return () => {
      restoration?.stop()
    }
  }, [detailId])
  return useCallback((id: string | null) => {
    // Capture before React replaces the long table: the browser can clamp its
    // scroll position during the DOM update, before layout-effect cleanup.
    if (id && !detailId) listTop.current = document.getElementById('main-content')?.parentElement?.scrollTop ?? 0
    onSelect(id)
  }, [detailId, onSelect])
}
