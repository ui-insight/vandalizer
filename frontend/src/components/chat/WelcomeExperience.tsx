import { Check } from 'lucide-react'
import type { OnboardingStatus } from '../../api/config'

// ---------------------------------------------------------------------------
// Onboarding stepper (shown in ChatPanel for users who haven't finished basics)
// ---------------------------------------------------------------------------

interface StepProps {
  label: string
  done: boolean
  number: number
}

function Step({ label, done, number }: StepProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div
        style={{
          width: 20,
          height: 20,
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 11,
          fontWeight: 600,
          ...(done
            ? {
                backgroundColor: 'var(--highlight-color, #eab308)',
                color: 'var(--highlight-text-color, #000)',
              }
            : {
                backgroundColor: '#f3f4f6',
                color: '#9ca3af',
                border: '1px solid #e5e7eb',
              }),
        }}
      >
        {done ? <Check size={12} strokeWidth={3} /> : number}
      </div>
      <span
        style={{
          fontSize: 13,
          color: done ? '#6b7280' : '#374151',
          textDecoration: done ? 'line-through' : 'none',
        }}
      >
        {label}
      </span>
    </div>
  )
}

export interface OnboardingStepperProps {
  status: OnboardingStatus
  hasChatAboutDocs: boolean
}

export function OnboardingStepper({ status, hasChatAboutDocs }: OnboardingStepperProps) {
  const step1 = status.has_documents
  const step2 = hasChatAboutDocs
  const step3 = status.has_extraction_sets || status.has_run_workflow
  const allDone = step1 && step2 && step3

  if (allDone) return null

  return (
    <div
      style={{
        padding: '10px 16px',
        borderRadius: 'var(--ui-radius, 12px)',
        backgroundColor: '#fafafa',
        border: '1px solid #f3f4f6',
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          color: '#9ca3af',
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          marginBottom: 8,
        }}
      >
        Getting started
      </div>
      <div style={{ display: 'flex', gap: 20 }}>
        <Step number={1} label="Upload a document" done={step1} />
        <Step number={2} label="Chat about your files" done={step2} />
        <Step number={3} label="Run an extraction" done={step3} />
      </div>
    </div>
  )
}
