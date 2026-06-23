import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

type Kind = 'kb' | 'extraction' | 'workflow'
type Theme = 'dark' | 'light'

interface Props {
  kind: Kind
  theme?: Theme
}

const BULLETS: Record<Kind, { when: string; why: string }[]> = {
  kb: [
    { when: 'First time', why: 'right after you\'ve added 5–10 documents and want to know if your KB is actually helping' },
    { when: 'After big edits', why: 'when you\'ve added/removed >20% of sources or changed chunking' },
    { when: 'Quarterly', why: 'to confirm quality hasn\'t drifted as documents age' },
    { when: 'Before sharing', why: 'when handing this KB to a teammate or stakeholder who needs to trust its answers' },
  ],
  extraction: [
    { when: 'First time', why: 'after you\'ve drafted the extraction fields and want to know how accurate the defaults are' },
    { when: 'After schema changes', why: 'when you\'ve added/removed fields or rewritten prompts' },
    { when: 'When accuracy slips', why: 'if you\'re seeing wrong values on documents the extraction used to handle' },
    { when: 'Before sharing', why: 'when handing this extraction to a teammate who\'ll rely on its output' },
  ],
  workflow: [
    { when: 'First time', why: 'after you\'ve configured the steps and want a baseline so future changes have something to beat' },
    { when: 'After step changes', why: 'when you\'ve swapped models, rewritten prompts, or restructured steps and want to confirm the change actually helped' },
    { when: 'Before handing off', why: 'before teammates or production traffic start relying on the workflow, since you don\'t want them finding the regressions' },
    { when: 'Quarterly', why: 'for workflows you depend on, since models drift and last quarter\'s best config may not be today\'s' },
  ],
}

export function WhenToRunDisclosure({ kind, theme = 'dark' }: Props) {
  const [open, setOpen] = useState(false)
  const bullets = BULLETS[kind]
  const triggerColor = theme === 'light' ? '#6b21a8' : '#a78bfa'
  const bodyColor = theme === 'light' ? '#4b5563' : '#bbb'
  const labelColor = theme === 'light' ? '#111827' : '#ddd'

  return (
    <div style={{ margin: '0 0 12px 0' }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 4,
          background: 'transparent', border: 'none', padding: 0,
          fontSize: 11, color: triggerColor, fontFamily: 'inherit', cursor: 'pointer',
        }}
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        When should I run this?
      </button>
      {open && (
        <ul style={{
          margin: '8px 0 0 0', paddingLeft: 18, fontSize: 12, color: bodyColor, lineHeight: 1.7,
        }}>
          {bullets.map(b => (
            <li key={b.when}>
              <b style={{ color: labelColor }}>{b.when}:</b> {b.why}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
