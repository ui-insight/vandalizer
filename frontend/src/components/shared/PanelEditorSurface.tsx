import { useLayoutEffect, useRef, type ReactNode } from 'react'
import { usePanelVisible } from './PanelVisibility'

/** Whether *node* is an editor surface shown above one at *layer*: a higher
 * layer, or the same layer later in the pane. Such a surface is never made
 * inert by the one it covers.
 *
 * Support ticket: after picking a task, its details were frozen until a
 * browser refresh. Reloading the workflow re-mounted the step editor and the
 * task editor in one render; the step editor's effect ran first and made its
 * sibling, the task editor on top of it, inert. */
function coversSurface(node: HTMLElement, surface: HTMLElement, layer: number): boolean {
  const other = Number(node.dataset.panelLayer)
  if (Number.isNaN(other) || node.dataset.panelLayer === undefined) return false
  return other > layer || (other === layer && Boolean(surface.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_FOLLOWING))
}

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
      .filter((node): node is HTMLElement => node instanceof HTMLElement && node !== surface && !coversSurface(node, surface, layer))
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
  }, [visible, layer])
  return (
    <div ref={ref} role="region" aria-label={label} tabIndex={-1} data-panel-layer={layer}
      onKeyDown={event => { if (event.key === 'Escape' && !event.defaultPrevented) { event.stopPropagation(); onClose() } }}
      style={{ position: 'absolute', inset: 0, zIndex: layer, background: '#fff', display: 'flex', flexDirection: 'column', minWidth: 0, overflowY: 'auto' }}>
      {children}
    </div>
  )
}
