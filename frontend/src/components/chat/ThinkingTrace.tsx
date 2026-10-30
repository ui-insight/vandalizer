import { useId, useState } from 'react'
import { BrainCircuit, ChevronRight } from 'lucide-react'
import './thinking-trace.css'

/** A single disclosure for the model's trace; tool calls keep their own entries. */
export function ThinkingTrace({ text, duration, status }: {
  text: string
  duration: number | null
  /** Actual current activity, only while this disclosure owns progress. */
  status?: string
}) {
  const [expanded, setExpanded] = useState(false)
  const id = useId()
  const elapsed = duration != null && Number.isFinite(duration) && duration >= 0
    ? duration < 1 ? '<1s' : `${Math.round(duration)}s`
    : null

  return <div className="thinking-trace" data-active={!!status}>
    <button
      type="button"
      className="thinking-trace-toggle"
      onClick={() => setExpanded(value => !value)}
      aria-expanded={expanded}
      aria-controls={id}
      aria-label={expanded ? 'Collapse thinking' : 'Expand thinking'}
    >
      <BrainCircuit size={16} className="thinking-trace-icon" aria-hidden="true" />
      <span className="thinking-trace-label">{status || 'Reasoning'}</span>
      {elapsed && <span className="thinking-trace-duration" aria-label={`Thinking time: ${elapsed}`}>{elapsed}</span>}
      <ChevronRight size={14} className="thinking-trace-chevron" aria-hidden="true" />
    </button>
    <div id={id} hidden={!expanded} className="thinking-trace-body">
      {expanded && <div className="thinking-trace-text">{text}</div>}
    </div>
  </div>
}
