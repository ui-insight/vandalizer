import { useState, useRef, useEffect, useLayoutEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'

type TermKey =
  | 'judge'
  | 'baseline'
  | 'candidate'
  | 'tier'
  | 'noise-floor'
  | 'accuracy'
  | 'test-set'
  | 'expected-answer'

interface Definition {
  short: string
  example?: string
}

const DEFINITIONS: Record<TermKey, Definition> = {
  judge: {
    short:
      'Another AI that grades each answer against the correct answer you provided. Think of it as an automated grader.',
    example: 'Question: "Who runs the lab?" • Expected: "Dr. Lin" • Answer: "Lin" → judge says: match.',
  },
  baseline: {
    short:
      'What the score looks like before any tuning — your current setup, or no setup at all. We compare every trial against the baseline so you know whether tuning actually helped.',
  },
  candidate: {
    short:
      'One specific combination of settings we try (a model + strategy + prompt + …). We run many candidates and keep the best one.',
    example: 'Candidate A: GPT-4o + one-pass. Candidate B: Claude Sonnet + two-pass + extended thinking.',
  },
  tier: {
    short:
      'How thoroughly we search — Quick tries fewer combinations and finishes faster, Thorough tries more and finishes slower. Standard is a sensible default.',
  },
  'noise-floor': {
    short:
      "How much a score can wiggle from one run to the next, even on identical inputs. If a trial only beats the baseline by less than the noise floor, the win isn't real — we won't let you apply it.",
  },
  accuracy: {
    short:
      'A 0–100 score for how close the AI\'s answers were to the correct answers. Higher is better. Aggregated across all your test cases.',
  },
  'test-set': {
    short:
      'A collection of example questions or documents with their correct answers, used to grade the AI. Tuning is only as good as the test set you give it.',
  },
  'expected-answer': {
    short:
      "The correct answer for a test question — what you'd want the AI to say. The judge compares the AI's response against this.",
  },
}

interface TermDefProps {
  term: TermKey
  children?: React.ReactNode
  theme?: 'dark' | 'light'
}

/**
 * Dotted-underline tooltip that defines a load-bearing validation term inline.
 * Reused across KB, Extraction, and Workflow surfaces so a first-day user
 * never hits "judge" or "baseline" without an inline definition.
 */
export function TermDef({ term, children, theme = 'dark' }: TermDefProps) {
  const def = DEFINITIONS[term]
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLSpanElement | null>(null)
  const tipRef = useRef<HTMLSpanElement | null>(null)
  // Fixed-viewport coordinates for the popover. We render it in a portal on
  // document.body so it can never overflow — and thus never spawn a horizontal
  // scrollbar on — a narrow ancestor (e.g. the tuning wizard's scroll body).
  // That overflow was the bug: a scrollbar would appear, and dragging it fired
  // the click-away handler and closed the popover before it could be read.
  // Null until measured so the first paint doesn't flash at an unclamped spot.
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
    // Left-align to the trigger, then clamp both edges into the viewport.
    let left = r.left
    if (left + tw > vw - margin) left = vw - margin - tw
    if (left < margin) left = margin
    // Prefer below the trigger; flip above when it would clip the bottom and
    // there's more room up top.
    let top = r.bottom + 6
    if (top + th > vh - margin && r.top - th - 6 >= margin) top = r.top - th - 6
    setPos({ top, left })
  }, [])

  // Measure + clamp before paint (useLayoutEffect) so the popover never appears
  // off-screen for a frame.
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
      // Keep open while interacting with the trigger or the popover itself
      // (the popover now lives outside wrapRef in a body portal).
      if (wrapRef.current?.contains(t) || tipRef.current?.contains(t)) return
      setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    // Keep the fixed popover glued to the trigger as the page or any nested
    // container scrolls (capture phase catches scrolls on ancestor elements).
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

  const isDark = theme === 'dark'
  const triggerColor = isDark ? '#c4b5fd' : '#7c3aed'
  const tipBg = isDark ? '#1f1f2e' : '#fff'
  const tipBorder = isDark ? 'rgba(124, 58, 237, 0.4)' : '#d1d5db'
  const tipText = isDark ? '#e5e5e5' : '#1f2937'
  const tipMeta = isDark ? '#9ca3af' : '#6b7280'

  return (
    <span ref={wrapRef} style={{ position: 'relative', display: 'inline-block' }}>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          setOpen((v) => !v)
        }}
        aria-expanded={open}
        aria-label={`Definition of ${term}`}
        style={{
          background: 'transparent',
          border: 'none',
          padding: 0,
          margin: 0,
          font: 'inherit',
          color: triggerColor,
          cursor: 'help',
          textDecoration: 'underline dotted',
          textUnderlineOffset: 2,
        }}
      >
        {children ?? term}
      </button>
      {open && createPortal(
        <span
          ref={tipRef}
          role="tooltip"
          style={{
            position: 'fixed',
            zIndex: 1000,
            top: pos?.top ?? 0,
            left: pos?.left ?? 0,
            // Hidden until measured/clamped so it never flashes off-screen.
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
          <div>{def.short}</div>
          {def.example && (
            <div style={{ marginTop: 6, fontSize: 11, color: tipMeta }}>
              {def.example}
            </div>
          )}
        </span>,
        document.body,
      )}
    </span>
  )
}
