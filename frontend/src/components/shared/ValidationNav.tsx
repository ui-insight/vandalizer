import { useId, useRef } from 'react'
import './validation-workspace.css'

export type ValidationStage = 'examples' | 'check' | 'improve'

/** Shared navigation for checking a KB, extraction, or workflow. State stays
 * with the caller so moving between stages never restarts an active check. */
export function ValidationNav({ active, onChange, summary, running = false }: {
  active: ValidationStage
  onChange: (stage: ValidationStage) => void
  summary: string
  running?: boolean
}) {
  const id = useId()
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const stages = [
    { key: 'examples' as const, label: 'Examples' },
    { key: 'check' as const, label: 'Run & results' },
    { key: 'improve' as const, label: 'Improve' },
  ]
  return <div className="validation-navigation">
    <nav aria-label="Validation stages" className="validation-stages">
      {stages.map((stage, index) => <button key={stage.key} type="button"
        ref={el => { refs.current[index] = el }}
        aria-current={active === stage.key ? 'step' : undefined}
        aria-describedby={`${id}-summary`}
        onClick={() => onChange(stage.key)}
        onKeyDown={event => {
          const next = event.key === 'ArrowRight' ? (index + 1) % 3
            : event.key === 'ArrowLeft' ? (index + 2) % 3
              : event.key === 'Home' ? 0 : event.key === 'End' ? 2 : null
          if (next == null) return
          event.preventDefault()
          refs.current[next]?.focus()
        }}>
        <span className="validation-stage-number" aria-hidden="true">{index + 1}</span>
        <span>{stage.label}</span>
        {stage.key === 'check' && running && <span className="validation-running" aria-label="Check running" />}
      </button>)}
    </nav>
    <p id={`${id}-summary`} className="validation-stage-summary">{summary}</p>
  </div>
}
