import { useEffect, useRef, useState } from 'react'
import { MoreHorizontal, Pencil, Trash2 } from 'lucide-react'

/** A single, keyboard-accessible entry point for secondary row actions. */
export function ActivityActions({ title, disabled, onRename, onDelete }: {
  title: string
  disabled: boolean
  onRename?: () => void
  onDelete: (event: React.MouseEvent) => void
}) {
  const [open, setOpen] = useState(false)
  const [above, setAbove] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    menu.current?.querySelector<HTMLButtonElement>('button')?.focus({ preventScroll: true })
    const outside = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false)
    }
    const reposition = (e: Event) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', outside)
    window.addEventListener('resize', reposition)
    // Dismiss for user scrolling, not the browser's focus/scroll-into-view events.
    window.addEventListener('wheel', reposition, { capture: true, passive: true })
    window.addEventListener('touchmove', reposition, { capture: true, passive: true })
    return () => {
      document.removeEventListener('pointerdown', outside)
      window.removeEventListener('resize', reposition)
      window.removeEventListener('wheel', reposition, true)
      window.removeEventListener('touchmove', reposition, true)
    }
  }, [open])

  return <div ref={root} className="activity-actions" onBlur={e => {
    // Safari pointer clicks can blur to the document before dispatching click.
    // Only a known outside focus target means the user has left the menu;
    // outside pointer presses are handled separately above.
    if (e.relatedTarget && !e.currentTarget.contains(e.relatedTarget as Node)) setOpen(false)
  }}>
    <button ref={trigger} type="button" className="activity-actions__trigger"
      aria-label={`Actions for ${title}`} title="More actions" aria-haspopup="menu" aria-expanded={open}
      onClick={() => {
        const bounds = trigger.current?.getBoundingClientRect()
        const scrollBounds = trigger.current?.closest('.activity-rail__scroll')?.getBoundingClientRect()
        setAbove(!!bounds && bounds.bottom + 112 > (scrollBounds?.bottom ?? window.innerHeight))
        setOpen(!open)
      }}><MoreHorizontal size={18} aria-hidden="true" /></button>
    {open && <div ref={menu} role="menu" aria-label={`Actions for ${title}`}
      className={`activity-actions__menu${above ? ' activity-actions__menu--above' : ''}`}
      onKeyDown={e => {
        const items = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'))
        const index = items.indexOf(document.activeElement as HTMLButtonElement)
        if (e.key === 'Escape') {
          e.preventDefault(); e.stopPropagation(); setOpen(false); trigger.current?.focus()
        } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) {
          e.preventDefault()
          const next = e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1
            : (index + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length
          items[next]?.focus()
        }
      }}>
      {onRename && <button type="button" role="menuitem" aria-label={`Rename chat: ${title}`}
        onClick={() => { setOpen(false); onRename() }}><Pencil size={15} aria-hidden="true" />Rename chat</button>}
      <button type="button" role="menuitem" aria-label={`Delete activity: ${title}`} disabled={disabled}
        className="activity-actions__danger"
        onClick={e => { trigger.current?.focus(); setOpen(false); onDelete(e) }}><Trash2 size={15} aria-hidden="true" />Delete activity</button>
    </div>}
  </div>
}
