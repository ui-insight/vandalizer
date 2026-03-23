import { Upload, MessageSquare, Workflow, Compass, Check } from 'lucide-react'
import type { OnboardingStatus } from '../../api/config'

// ---------------------------------------------------------------------------
// Action card
// ---------------------------------------------------------------------------

interface ActionCardProps {
  icon: React.ReactNode
  title: string
  description: string
  onClick: () => void
}

function ActionCard({ icon, title, description, onClick }: ActionCardProps) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 12,
        padding: '16px 14px',
        border: '1px solid #e5e7eb',
        borderRadius: 'var(--ui-radius, 12px)',
        backgroundColor: '#fff',
        cursor: 'pointer',
        textAlign: 'left',
        fontFamily: 'inherit',
        transition: 'all 0.2s ease',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = 'var(--highlight-color, #eab308)'
        e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 5%, white)'
        e.currentTarget.style.transform = 'translateY(-1px)'
        e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = '#e5e7eb'
        e.currentTarget.style.backgroundColor = '#fff'
        e.currentTarget.style.transform = 'translateY(0)'
        e.currentTarget.style.boxShadow = 'none'
      }}
    >
      <div
        style={{
          flexShrink: 0,
          width: 36,
          height: 36,
          borderRadius: 8,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 12%, white)',
          color: 'var(--highlight-color, #eab308)',
        }}
      >
        {icon}
      </div>
      <div>
        <div style={{ fontSize: 14, fontWeight: 600, color: '#111827', lineHeight: 1.3 }}>
          {title}
        </div>
        <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2, lineHeight: 1.4 }}>
          {description}
        </div>
      </div>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Onboarding stepper (exported separately so ChatPanel can persist it)
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
        borderTop: '1px solid #f3f4f6',
        backgroundColor: '#fafafa',
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

// ---------------------------------------------------------------------------
// Welcome action cards (shown in the empty chat area for new users)
// ---------------------------------------------------------------------------

interface WelcomeActionCardsProps {
  onboardingStatus: OnboardingStatus | null
  onSwitchToFiles: () => void
  onSendMessage: (message: string, includeOnboardingContext: boolean) => void
  onNeedDocumentsFirst: () => void
}

export function WelcomeActionCards({
  onboardingStatus,
  onSwitchToFiles,
  onSendMessage,
  onNeedDocumentsFirst,
}: WelcomeActionCardsProps) {
  const hasDocs = onboardingStatus?.has_documents ?? false

  return (
    <div style={{ maxWidth: 640, margin: '0 auto' }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(2, 1fr)',
          gap: 10,
        }}
      >
        <ActionCard
          icon={<Upload size={18} />}
          title="Upload documents"
          description="Add PDFs, Word docs, spreadsheets, or images to get started"
          onClick={onSwitchToFiles}
        />
        <ActionCard
          icon={<MessageSquare size={18} />}
          title="Chat with your files"
          description="Ask questions grounded in your uploaded documents"
          onClick={() =>
            hasDocs
              ? onSendMessage('How do I chat with my documents? Walk me through the steps.', true)
              : onNeedDocumentsFirst()
          }
        />
        <ActionCard
          icon={<Workflow size={18} />}
          title="Build a workflow"
          description="Automate extraction, classification, and analysis across documents"
          onClick={() =>
            hasDocs
              ? onSendMessage('Help me build my first extraction workflow, step by step.', true)
              : onNeedDocumentsFirst()
          }
        />
        <ActionCard
          icon={<Compass size={18} />}
          title="Take a quick tour"
          description="See everything Vandalizer can do for your research"
          onClick={() => onSendMessage(
            'Give me a quick tour of what Vandalizer can do. What should I try first?',
            true,
          )}
        />
      </div>
    </div>
  )
}
