import { useState, useRef, useEffect, useLayoutEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'

interface InfoHintProps {
  /** Tooltip body. Plain text or nodes. */
  content: React.ReactNode
  /** Accessible name for the trigger; defaults to "More information". */
  label?: string
  theme?: 'dark' | 'light'
}

/**
 * Small ⓘ trigger with a real popover that opens on hover or click/tap.
 * Replaces native `title` tooltips, which need a long motionless hover and
 * never fire on touch — users saw the `cursor: help` "?" and assumed the
 * bubble was broken (support ticket, July 2026). Positioning/portal logic
 * mirrors TermDef: rendered on document.body and clamped to the viewport so
 * it can't overflow a narrow scroll container.
 */
export function InfoHint({ content, label = 'More information', theme = 'dark' }: InfoHintProps) {
  const [open, setOpen] = useState(false)
  // Click pins the popover so touch users (no hover) can open it and mouse
  // users can keep it up while moving the pointer away.
  const [pinned, setPinned] = useState(false)
  const wrapRef = useRef<HTMLSpanElement | null>(null)
  const tipRef = useRef<HTMLSpanElement | null>(null)
  const closeTimer = useRef<number | null>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)

  const reposition = useCallback(() => {
    const trigger = wrapRef.current
    const tip = tipRef.current
    if (!trigger || !tip) return
    const r = trigger.getBoundingClientRect()
    const margin = 8
    const vw = document.documentElement.clientWidth
    const vh = document.documentElement.clientHeight
    const tw = tip.offsetWidth
    const th = tip.offsetHeight
    let left = r.left
    if (left + tw > vw - margin) left = vw - margin - tw
    if (left < margin) left = margin
    let top = r.bottom + 6
    if (top + th > vh - margin && r.top - th - 6 >= margin) top = r.top - th - 6
    setPos({ top, left })
  }, [])

  useLayoutEffect(() => {
    if (!open) {
      setPos(null)
      return
    }
    reposition()
  }, [open, reposition])

  useEffect(() => {
    if (!open) return
    function onDocClick(e: MouseEvent) {
      const t = e.target as Node
      if (wrapRef.current?.contains(t) || tipRef.current?.contains(t)) return
      setOpen(false)
      setPinned(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setOpen(false)
        setPinned(false)
      }
    }
    const onReflow = () => reposition()
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    window.addEventListener('resize', onReflow)
    window.addEventListener('scroll', onReflow, true)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
      window.removeEventListener('resize', onReflow)
      window.removeEventListener('scroll', onReflow, true)
    }
  }, [open, reposition])

  useEffect(() => () => {
    if (closeTimer.current != null) window.clearTimeout(closeTimer.current)
  }, [])

  const hoverOpen = () => {
    if (closeTimer.current != null) {
      window.clearTimeout(closeTimer.current)
      closeTimer.current = null
    }
    setOpen(true)
  }
  // Grace period so the pointer can cross the 6px gap into the popover
  // without it closing.
  const hoverClose = () => {
    if (pinned) return
    if (closeTimer.current != null) window.clearTimeout(closeTimer.current)
    closeTimer.current = window.setTimeout(() => setOpen(false), 150)
  }

  const isDark = theme === 'dark'
  const tipBg = isDark ? '#1f1f2e' : '#fff'
  const tipBorder = isDark ? '#3a3a4a' : '#d1d5db'
  const tipText = isDark ? '#e5e5e5' : '#1f2937'

  return (
    <span ref={wrapRef} style={{ display: 'inline-flex' }}>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          if (open && pinned) {
            setOpen(false)
            setPinned(false)
          } else {
            setOpen(true)
            setPinned(true)
          }
        }}
        onMouseEnter={hoverOpen}
        onMouseLeave={hoverClose}
        onFocus={hoverOpen}
        onBlur={hoverClose}
        aria-expanded={open}
        aria-label={label}
        style={{
          fontSize: 11, color: isDark ? '#888' : '#6b7280',
          cursor: 'help', userSelect: 'none',
          background: 'transparent',
          border: `1px solid ${isDark ? '#444' : '#9ca3af'}`,
          borderRadius: '50%',
          width: 14, height: 14, padding: 0, lineHeight: '12px',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        i
      </button>
      {open && createPortal(
        <span
          ref={tipRef}
          role="tooltip"
          onMouseEnter={hoverOpen}
          onMouseLeave={hoverClose}
          style={{
            position: 'fixed',
            zIndex: 1000,
            top: pos?.top ?? 0,
            left: pos?.left ?? 0,
            visibility: pos ? 'visible' : 'hidden',
            minWidth: 240,
            maxWidth: 320,
            padding: '10px 12px',
            background: tipBg,
            border: `1px solid ${tipBorder}`,
            borderRadius: 6,
            boxShadow: isDark
              ? '0 6px 24px rgba(0,0,0,0.4)'
              : '0 6px 24px rgba(0,0,0,0.12)',
            fontSize: 12,
            lineHeight: 1.5,
            color: tipText,
            fontWeight: 400,
            textAlign: 'left',
            whiteSpace: 'normal',
          }}
        >
          {content}
        </span>,
        document.body,
      )}
    </span>
  )
}
