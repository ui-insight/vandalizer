import { useEffect, useState } from 'react'
import type { Dispatch, ReactNode, SetStateAction } from 'react'
import { FocusTrap } from 'focus-trap-react'
import { Sparkles, X, ChevronRight, ChevronLeft } from 'lucide-react'
import { WizardSteps } from './WizardSteps'

export interface WizardStep<TOptions> {
  /** Unique id used as the step key and in the breadcrumb. */
  id: string
  /** Label shown in the breadcrumb. */
  label: string
  /** Renders the step body. Receives the wizard's options + setter. */
  render: (options: TOptions, setOptions: Dispatch<SetStateAction<TOptions>>) => ReactNode
  /** Optional gate: when this returns false, Next is disabled. */
  canAdvance?: (options: TOptions) => boolean
}

interface AutovalidateWizardProps<TOptions> {
  steps: WizardStep<TOptions>[]
  initialOptions: TOptions
  onConfirm: (options: TOptions) => void
  onClose: () => void
  title?: string
  /** Label on the final step's primary button. Default "Start optimization".
   * Pass a function to compute the label from current options (e.g. to bake
   * the selected tier's cost into the button: "Validate & improve — $2.40, ~15 min"). */
  confirmLabel?: string | ((options: TOptions) => string)
}

/**
 * Generic 3-to-N step wizard modal shell.
 *
 * Owns: the modal chrome, step navigation, options state, and the back/next
 * button bar. Callers provide a `steps` array; each step renders its own body.
 *
 * KB Autovalidate uses this for Concept → Test set → Budget → Advanced.
 * Extraction and workflow autovalidate will reuse it with their own steps.
 */
export function AutovalidateWizard<TOptions>({
  steps,
  initialOptions,
  onConfirm,
  onClose,
  title = 'Validate & improve',
  confirmLabel = 'Start optimization',
}: AutovalidateWizardProps<TOptions>) {
  const [stepIndex, setStepIndex] = useState(0)
  const [options, setOptions] = useState<TOptions>(initialOptions)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  if (steps.length === 0) return null
  const currentStep = steps[stepIndex]
  const isLast = stepIndex === steps.length - 1
  const isFirst = stepIndex === 0
  const canAdvance = currentStep.canAdvance ? currentStep.canAdvance(options) : true

  const stepIds = steps.map(s => s.id)
  const stepLabels = Object.fromEntries(steps.map(s => [s.id, s.label])) as Record<string, string>

  const next = () => { if (!isLast && canAdvance) setStepIndex(i => i + 1) }
  const prev = () => { if (!isFirst) setStepIndex(i => i - 1) }
  const confirm = () => { if (canAdvance) onConfirm(options) }

  return (
    <div style={{
      position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
    }}>
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: 'none' } }}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="autovalidate-wizard-title"
        style={{
          width: 520, maxHeight: '90vh', overflowY: 'auto',
          padding: 22, backgroundColor: '#1f1f1f',
          border: '1px solid #2e2e2e', borderRadius: 10,
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <Sparkles size={18} aria-hidden="true" style={{ color: '#a78bfa' }} />
          <h3 id="autovalidate-wizard-title" style={{ margin: 0, fontSize: 16, color: '#fff' }}>{title}</h3>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            style={{ marginLeft: 'auto', background: 'transparent', border: 'none', cursor: 'pointer', padding: 2, color: '#888' }}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        {/* Step indicator */}
        <WizardSteps steps={stepIds} current={currentStep.id} labels={stepLabels} />

        {/* Body */}
        <div style={{ minHeight: 240, marginTop: 14 }}>
          {currentStep.render(options, setOptions)}
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 16 }}>
          <button onClick={isFirst ? onClose : prev} style={btn()}>
            {isFirst ? 'Cancel' : (<><ChevronLeft size={12} />Back</>)}
          </button>
          {!isLast ? (
            <button onClick={next} disabled={!canAdvance} style={btn(canAdvance, '#7c3aed')}>
              Next<ChevronRight size={12} />
            </button>
          ) : (
            <button onClick={confirm} disabled={!canAdvance} style={btn(canAdvance, '#7c3aed')}>
              <Sparkles size={12} />
              {typeof confirmLabel === 'function' ? confirmLabel(options) : confirmLabel}
            </button>
          )}
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}

function btn(enabled: boolean = true, color?: string): React.CSSProperties {
  return {
    display: 'inline-flex', alignItems: 'center', gap: 4,
    padding: '6px 12px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
    color: enabled ? '#e5e5e5' : '#555',
    backgroundColor: color ? color : '#2a2a2a',
    border: `1px solid ${color || '#3a3a3a'}`,
    borderRadius: 5,
    cursor: enabled ? 'pointer' : 'not-allowed',
    opacity: enabled ? 1 : 0.5,
  }
}
