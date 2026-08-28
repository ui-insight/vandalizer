import { useId, useState, type ReactNode } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

/**
 * A titled section that folds to one line. The header is a real button
 * (keyboard + screen-reader friendly, aria-expanded/aria-controls wired), and
 * a `summary` line stands in for the body while it is collapsed so a folded
 * section still says what it is set to. Built for the workflow Input tab's
 * Input / Output Configuration sections and meant to be reused wherever a
 * long form should be worked through one section at a time (the automation
 * wizard asked for the same).
 */
export function CollapsibleSection({
  title,
  summary,
  defaultOpen = true,
  open: controlledOpen,
  onToggle,
  children,
  headerRight,
  testId,
}: {
  title: string
  /** Shown beside the title while collapsed (and, muted, while open). */
  summary?: ReactNode
  defaultOpen?: boolean
  /** Controlled mode: pass `open` and `onToggle`. */
  open?: boolean
  onToggle?: (open: boolean) => void
  children: ReactNode
  /** Extra controls on the header row, outside the toggle button. */
  headerRight?: ReactNode
  testId?: string
}) {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen)
  const isControlled = controlledOpen !== undefined
  const open = isControlled ? controlledOpen : uncontrolledOpen
  const bodyId = useId()

  const toggle = () => {
    const next = !open
    if (!isControlled) setUncontrolledOpen(next)
    onToggle?.(next)
  }

  const Chevron = open ? ChevronDown : ChevronRight

  return (
    <section data-testid={testId} style={{ border: '1px solid #e5e7eb', borderRadius: 8, backgroundColor: '#fff' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px' }}>
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          aria-controls={bodyId}
          style={{
            flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 8,
            background: 'none', border: 'none', padding: 0, cursor: 'pointer',
            fontFamily: 'inherit', textAlign: 'left', color: '#202124',
          }}
        >
          <Chevron aria-hidden="true" style={{ width: 16, height: 16, color: '#6b7280', flexShrink: 0 }} />
          <span style={{ fontSize: 14, fontWeight: 600 }}>{title}</span>
          {summary && (
            <span
              style={{
                fontSize: 12, color: '#6b7280', fontWeight: 400, marginLeft: 4,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}
            >
              {summary}
            </span>
          )}
        </button>
        {headerRight}
      </div>
      <div id={bodyId} hidden={!open} style={{ padding: '4px 12px 14px', borderTop: '1px solid #f3f4f6' }}>
        {children}
      </div>
    </section>
  )
}
