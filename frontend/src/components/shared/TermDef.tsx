import { useState, useRef, useEffect, useLayoutEffect } from 'react'

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
  // Horizontal shift (px) applied to keep the tooltip inside the viewport.
  // Without it, a trigger near the right edge pushes the tooltip off-screen,
  // which spawns a horizontal scrollbar the user can't reach without closing it.
  const [shiftX, setShiftX] = useState(0)

  useLayoutEffect(() => {
    if (!open) {
      setShiftX(0)
      return
    }
    const tip = tipRef.current
    if (!tip) return
    const margin = 8
    const vw = document.documentElement.clientWidth
    const rect = tip.getBoundingClientRect()
    let shift = 0
    if (rect.right > vw - margin) shift = vw - margin - rect.right
    if (rect.left + shift < margin) shift = margin - rect.left
    setShiftX(shift)
  }, [open])

  useEffect(() => {
    if (!open) return
    function onDocClick(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

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
      {open && (
        <span
          ref={tipRef}
          role="tooltip"
          style={{
            position: 'absolute',
            zIndex: 1000,
            top: 'calc(100% + 6px)',
            left: shiftX,
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
        </span>
      )}
    </span>
  )
}
