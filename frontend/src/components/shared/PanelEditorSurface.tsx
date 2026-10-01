import { useLayoutEffect, useRef, type ReactNode } from 'react'
import { usePanelVisible } from './PanelVisibility'

/** An editor replaces only its own pane. Covered siblings become inert while
 * sources and navigation remain usable, including with the keyboard. */
export function PanelEditorSurface({ label, onClose, children, layer = 1000 }: {
  label: string; onClose: () => void; children: ReactNode; layer?: number
}) {
  const ref = useRef<HTMLDivElement>(null)
  const opener = useRef<HTMLElement | null>(null)
  const visible = usePanelVisible()
  const visibleRef = useRef(visible)
  visibleRef.current = visible
  useLayoutEffect(() => {
    const surface = ref.current
    if (!surface || !visible) return
    opener.current ??= document.activeElement instanceof HTMLElement ? document.activeElement : null
    const siblings = Array.from(surface.parentElement?.children ?? [])
      .filter((node): node is HTMLElement => node instanceof HTMLElement && node !== surface)
      .map(node => ({ node, inert: node.inert }))
    siblings.forEach(({ node }) => { node.inert = true })
    surface.focus({ preventScroll: true })
    return () => {
      siblings.forEach(({ node, inert }) => { node.inert = inert })
      requestAnimationFrame(() => {
        // StrictMode cleanup keeps the surface connected; hidden retained
        // panels must not steal focus from the user's new location.
        if (!surface.isConnected && visibleRef.current && opener.current?.isConnected && !opener.current.closest('[inert]')) {
          opener.current.focus({ preventScroll: true })
        }
      })
    }
  }, [visible])
  return (
    <div ref={ref} role="region" aria-label={label} tabIndex={-1}
      onKeyDown={event => { if (event.key === 'Escape' && !event.defaultPrevented) { event.stopPropagation(); onClose() } }}
      style={{ position: 'absolute', inset: 0, zIndex: layer, background: '#fff', display: 'flex', flexDirection: 'column', minWidth: 0, overflowY: 'auto' }}>
      {children}
    </div>
  )
}
