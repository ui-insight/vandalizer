import { useCallback, useEffect, useId, useState, type CSSProperties } from 'react'
import { Maximize2, Minimize2 } from 'lucide-react'

/** The viewer's expand button shows the file full screen inside Vandalizer.
 *
 * Support ticket: expand opened PDFs in a new browser tab and downloaded
 * .md, .docx and .xlsx files, taking users out of their work. Now the
 * viewer itself fills the window, in the same tab. It stays the same
 * component (no remount, no portal), so its page, zoom, search and scroll
 * position are all kept when the full view closes. */
export function useFullView() {
  const [expanded, setExpanded] = useState(false)
  const id = useId()

  const open = useCallback(() => setExpanded(true), [])
  const close = useCallback(() => setExpanded(false), [])

  useEffect(() => {
    if (!expanded) return
    const root = document.querySelector<HTMLElement>(`[data-full-view="${id}"]`)
    // Everything outside the full view is covered, so keyboard and screen
    // readers skip it too: each ancestor's other children become inert.
    const covered: HTMLElement[] = []
    for (let node = root; node && node !== document.body; node = node.parentElement) {
      for (const sibling of Array.from(node.parentElement?.children ?? [])) {
        if (sibling === node || !(sibling instanceof HTMLElement) || sibling.inert) continue
        covered.push(sibling)
        sibling.inert = true
      }
    }
    // Escape closes the full view, unless a field in it (the find bar) used it.
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) return
      const target = event.target as HTMLElement | null
      if (target?.closest('input, textarea, select, [contenteditable="true"]')) return
      setExpanded(false)
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      covered.forEach(node => { node.inert = false })
    }
  }, [expanded, id])

  // Above the workspace's panels and editors, below app dialogs and toasts.
  const style: CSSProperties = expanded
    ? { position: 'fixed', inset: 0, zIndex: 1100, height: '100dvh', backgroundColor: '#fff' }
    : {}
  const rootProps = {
    'data-full-view': id,
    ...(expanded ? { role: 'dialog', 'aria-modal': true, 'aria-label': 'Full view of the document' } as const : {}),
  }

  return { expanded, open, close, style, rootProps }
}

/** The toolbar's expand button; in the full view, the labelled way back.
 * One button either way, so keyboard focus stays on it. */
export function FullViewButton({ expanded, onOpen, onClose, style }: {
  expanded: boolean
  onOpen: () => void
  onClose: () => void
  style: CSSProperties
}) {
  return (
    <button
      type="button"
      onClick={expanded ? onClose : onOpen}
      title={expanded ? 'Exit full view (Esc)' : 'Full view'}
      aria-label={expanded ? 'Exit full view' : 'Full view'}
      style={expanded
        ? { ...style, width: 'auto', gap: 'var(--workspace-space-6)', padding: '0 var(--workspace-space-12)', fontWeight: 600 }
        : style}
    >
      {expanded ? <Minimize2 size={16} aria-hidden="true" /> : <Maximize2 size={16} aria-hidden="true" />}
      {expanded && 'Exit full view'}
    </button>
  )
}
