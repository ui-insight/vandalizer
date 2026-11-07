import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ArrowUpRight, Copy, Download, FolderPlus, Link, Loader2, MoreHorizontal, Pencil, Share2, Trash2 } from 'lucide-react'
import { artifactContentUrl, type Artifact } from '../../api/artifacts'

export type PageCardAction = 'rename' | 'duplicate' | 'copy' | 'project' | 'delete'

export function PageCardMenu({ page, busy, publicToken, onAction }: {
  page: Artifact; busy: boolean; publicToken?: string; onAction: (action: PageCardAction) => void
}) {
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState({ top: 0, left: 0 })
  const trigger = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const id = useId()
  const href = `/pages/${encodeURIComponent(page.uuid)}`
  useLayoutEffect(() => {
    if (!open) return
    const positionMenu = () => {
      if (!trigger.current || !menu.current) return
      const anchor = trigger.current.getBoundingClientRect()
      const bounds = menu.current.getBoundingClientRect()
      setPosition({ left: Math.max(12, Math.min(anchor.right - bounds.width, window.innerWidth - bounds.width - 12)),
        top: Math.max(12, anchor.bottom + bounds.height + 8 > window.innerHeight ? anchor.top - bounds.height - 6 : anchor.bottom + 6) })
    }
    positionMenu()
    menu.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus({ preventScroll: true })
    window.addEventListener('scroll', positionMenu, true)
    return () => window.removeEventListener('scroll', positionMenu, true)
  }, [open])
  useEffect(() => {
    if (!open) return
    const outside = (event: Event) => {
      if (!menu.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) setOpen(false)
    }
    const close = () => setOpen(false)
    document.addEventListener('pointerdown', outside)
    document.addEventListener('focusin', outside)
    // Focus can scroll a lower card into view after its menu opens. Dismiss
    // on user scrolling, not those delayed browser scroll events.
    window.addEventListener('wheel', outside, { capture: true, passive: true })
    window.addEventListener('touchmove', outside, { capture: true, passive: true })
    window.addEventListener('resize', close)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('focusin', outside)
      window.removeEventListener('wheel', outside, true)
      window.removeEventListener('touchmove', outside, true)
      window.removeEventListener('resize', close)
    }
  }, [open])
  const act = (action: PageCardAction) => { trigger.current?.focus(); setOpen(false); onAction(action) }
  return <>
    <button ref={trigger} className="page-icon-button" type="button" title="More actions" disabled={busy}
      aria-label={`Actions for ${page.title}`} aria-busy={busy} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined}
      onClick={() => setOpen(!open)} onKeyDown={event => { if (event.key === 'ArrowDown') { event.preventDefault(); setOpen(true) } }}>{busy ? <Loader2 size={18} className="animate-spin" aria-hidden="true" /> : <MoreHorizontal size={18} aria-hidden="true" />}</button>
    {open && createPortal(<div ref={menu} id={id} role="menu" aria-label={`Actions for ${page.title}`} className="page-card-menu" style={position}
      onKeyDown={event => {
        const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]'))
        const index = items.indexOf(document.activeElement as HTMLElement)
        if (event.key === 'Escape' || event.key === 'Tab') {
          if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation() }
          trigger.current?.focus(); setOpen(false)
        } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
          event.preventDefault()
          const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length
          items[next]?.focus()
        }
      }}>
      <a role="menuitem" href={href} onClick={() => setOpen(false)}><ArrowUpRight size={16} />Open</a>
      {page.can_manage && <button role="menuitem" onClick={() => act('rename')}><Pencil size={16} />Rename</button>}
      <button role="menuitem" onClick={() => act('duplicate')}><Copy size={16} />Duplicate</button>
      {page.can_manage && <a role="menuitem" href={`${href}#share`} onClick={() => setOpen(false)}><Share2 size={16} />Share</a>}
      {publicToken && <button role="menuitem" onClick={() => act('copy')}><Link size={16} />Copy public link</button>}
      <a role="menuitem" href={`${artifactContentUrl(page.uuid, page.latest_revision)}?download=true`} onClick={() => setOpen(false)}><Download size={16} />Download HTML</a>
      <button role="menuitem" onClick={() => act('project')}><FolderPlus size={16} />Add to project</button>
      {page.can_manage && <button role="menuitem" className="page-card-menu-danger" onClick={() => act('delete')}><Trash2 size={16} />Delete</button>}
    </div>, document.body)}
  </>
}
