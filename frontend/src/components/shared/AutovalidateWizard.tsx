import { createPortal } from './panelPortal'
import { usePanelEffect } from './usePanelEffect'
import { useState } from 'react'
import type { Dispatch, ReactNode, SetStateAction } from 'react'
import { FocusTrap } from './PanelFocusTrap'
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

  usePanelEffect(() => {
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

  return createPortal(
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
          width: 560, maxWidth: 'calc(100vw - 24px)', maxHeight: '90dvh', overflow: 'hidden', display: 'flex', flexDirection: 'column',
          padding: 'var(--workspace-space-16)', backgroundColor: 'var(--workspace-surface)',
          border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-large)',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', marginBottom: 'var(--workspace-space-4)', flexShrink: 0 }}>
          <Sparkles size={18} aria-hidden="true" style={{ color: 'var(--workspace-accent-ink)' }} />
          <h3 id="autovalidate-wizard-title" style={{ margin: 0, fontSize: 'var(--workspace-font-card-title)', color: 'var(--workspace-text)' }}>{title}</h3>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            style={{ marginLeft: 'auto', background: 'transparent', border: 'none', cursor: 'pointer', padding: 'var(--workspace-space-2)', color: 'var(--workspace-muted)' }}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        {/* Step indicator */}
        <WizardSteps steps={stepIds} current={currentStep.id} labels={stepLabels} />

        {/* Body */}
        <div key={currentStep.id} role="region" aria-label={currentStep.label} tabIndex={0} style={{ minHeight: 0, overflowY: 'auto', marginTop: 'var(--workspace-space-16)', padding: 'var(--workspace-space-4)' }}>
          {currentStep.render(options, setOptions)}
        </div>

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 'var(--workspace-space-8)', flexWrap: 'wrap', marginTop: 'var(--workspace-space-16)', flexShrink: 0 }}>
          <button onClick={isFirst ? onClose : prev} style={btn()}>
            {isFirst ? 'Cancel' : (<><ChevronLeft size={12} />Back</>)}
          </button>
          {!isLast ? (
            <button onClick={next} disabled={!canAdvance} style={btn(canAdvance, 'var(--highlight-color, #eab308)')}>
              Next<ChevronRight size={12} />
            </button>
          ) : (
            <button onClick={confirm} disabled={!canAdvance} style={btn(canAdvance, 'var(--highlight-color, #eab308)')}>
              <Sparkles size={12} />
              {typeof confirmLabel === 'function' ? confirmLabel(options) : confirmLabel}
            </button>
          )}
        </div>
      </div>
      </FocusTrap>
    </div>, document.body
  )
}

function btn(enabled: boolean = true, color?: string): React.CSSProperties {
  return {
    display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)',
    padding: "var(--workspace-space-6) var(--workspace-space-12)", fontSize: 'var(--workspace-font-meta)', fontWeight: 600, fontFamily: 'inherit',
    color: enabled ? color ? 'var(--highlight-text-color, #000)' : 'var(--workspace-text)' : 'var(--workspace-muted)',
    backgroundColor: color ? color : 'var(--workspace-surface)',
    border: `1px solid ${color || 'var(--workspace-border)'}`,
    borderRadius: 'var(--workspace-radius-small)',
    cursor: enabled ? 'pointer' : 'not-allowed',
    opacity: enabled ? 1 : 0.5,
  }
}
