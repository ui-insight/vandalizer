import { useState, useRef, useEffect } from 'react'
import type { ReactNode } from 'react'
import { HelpCircle } from 'lucide-react'

interface ConceptTipProps {
  /** The term being explained, e.g. "Extraction". */
  term: string
  /** Plain-language explanation shown in the popover. */
  children: ReactNode
}

/**
 * A small, accessible "what does this mean?" affordance for jargon.
 *
 * Renders the term with a help icon; click (or keyboard) opens a popover with a
 * plain-language explanation. Built for research administrators who may not know
 * platform vocabulary like "extraction" or "knowledge base". Closes on outside
 * click or Escape, and clamps to the viewport so it never runs off small screens.
 */
export function ConceptTip({ term, children }: ConceptTipProps) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const popRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (
        triggerRef.current && !triggerRef.current.contains(e.target as Node) &&
        popRef.current && !popRef.current.contains(e.target as Node)
      ) {
        setOpen(false)
      }
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <span style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}>
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        aria-label={`What is ${term}?`}
        onClick={(e) => { e.stopPropagation(); setOpen(o => !o) }}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          padding: '4px 9px',
          borderRadius: 9999,
          fontSize: 12,
          fontWeight: 500,
          fontFamily: 'inherit',
          border: '1px solid #e5e7eb',
          background: '#fff',
          color: '#475569',
          cursor: 'pointer',
          transition: 'border-color 0.15s, background 0.15s',
        }}
        onMouseEnter={e => {
          e.currentTarget.style.borderColor = 'var(--highlight-color, #eab308)'
          e.currentTarget.style.background = 'color-mix(in srgb, var(--highlight-color, #eab308) 7%, white)'
        }}
        onMouseLeave={e => {
          e.currentTarget.style.borderColor = '#e5e7eb'
          e.currentTarget.style.background = '#fff'
        }}
      >
        <HelpCircle size={13} style={{ opacity: 0.7 }} />
        {term}
      </button>

      {open && (
        <div
          ref={popRef}
          role="tooltip"
          onClick={(e) => e.stopPropagation()}
          style={{
            position: 'absolute',
            top: '100%',
            left: '50%',
            transform: 'translateX(-50%)',
            marginTop: 6,
            width: 'max-content',
            maxWidth: 'min(280px, calc(100vw - 24px))',
            background: '#fff',
            border: '1px solid #e5e7eb',
            borderRadius: 8,
            boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
            padding: 12,
            zIndex: 100,
            fontSize: 12,
            lineHeight: 1.5,
            color: '#374151',
            textAlign: 'left',
            whiteSpace: 'normal',
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 13 }}>{term}</div>
          <div>{children}</div>
        </div>
      )}
    </span>
  )
}

/** The core platform vocabulary, explained at an onboarding level for RAs. */
const CONCEPTS: Array<{ term: string; explanation: ReactNode }> = [
  {
    term: 'Extraction',
    explanation: 'Pulls specific fields — dates, dollar amounts, names, deadlines — out of a document into a neat table you can reuse or export.',
  },
  {
    term: 'Workflow',
    explanation: 'A saved sequence of steps (extract, summarize, compare, classify…) you can run over a document or a whole folder in one go.',
  },
  {
    term: 'Knowledge base',
    explanation: 'A searchable index of your documents and sources. Once built, the assistant answers questions grounded in them — with citations, not guesses.',
  },
  {
    term: 'Quality score',
    explanation: "How accurate a template is, measured against examples you've confirmed are correct. Higher means more trustworthy — it's a measurement, not a guess.",
  },
]

/**
 * A row of ConceptTips teaching the core nouns. Shown in the chat empty state
 * for users who may be new to the platform's vocabulary.
 */
export function ConceptStrip({ heading = 'New here? Tap a term to see what it means:' }: { heading?: string }) {
  return (
    <div>
      {heading && (
        <div style={{ fontSize: 12, color: '#9ca3af', marginBottom: 8, fontWeight: 500 }}>
          {heading}
        </div>
      )}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        {CONCEPTS.map(c => (
          <ConceptTip key={c.term} term={c.term}>{c.explanation}</ConceptTip>
        ))}
      </div>
    </div>
  )
}
