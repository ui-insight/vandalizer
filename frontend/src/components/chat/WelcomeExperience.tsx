import { Shield, CheckCircle2, Upload, GraduationCap, Check, ArrowRight, Sparkles, Target, Zap } from 'lucide-react'
import type { OnboardingStatus } from '../../api/config'

// ---------------------------------------------------------------------------
// Value proposition card (used in the new-user welcome)
// ---------------------------------------------------------------------------

interface ValueCardProps {
  icon: React.ReactNode
  title: string
  description: string
}

function ValueCard({ icon, title, description }: ValueCardProps) {
  return (
    <div
      style={{
        display: 'flex',
        gap: 14,
        padding: '18px 16px',
        borderRadius: 'var(--ui-radius, 12px)',
        backgroundColor: '#fff',
        border: '1px solid #e5e7eb',
      }}
    >
      <div
        style={{
          flexShrink: 0,
          width: 40,
          height: 40,
          borderRadius: 10,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 10%, white)',
          color: 'var(--highlight-color, #eab308)',
        }}
      >
        {icon}
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: '#111827', lineHeight: 1.3 }}>
          {title}
        </div>
        <div style={{ fontSize: 13, color: '#6b7280', marginTop: 4, lineHeight: 1.5 }}>
          {description}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Value-driven welcome (shown for first-session new users)
// ---------------------------------------------------------------------------

interface ValueWelcomeProps {
  onSwitchToFiles: () => void
  onSendMessage: (message: string, includeOnboardingContext: boolean) => void
}

export function ValueWelcome({ onSwitchToFiles, onSendMessage }: ValueWelcomeProps) {
  return (
    <div style={{ maxWidth: 640, margin: '0 auto' }}>
      {/* Value proposition cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 20 }}>
        <ValueCard
          icon={<Shield size={20} />}
          title="Your documents stay private"
          description="Unlike ChatGPT, Claude, and other consumer AI tools, your files never leave your institution's control. No data is used for AI training. You choose the model, and if it's a private endpoint, your data never touches a third party."
        />
        <ValueCard
          icon={<CheckCircle2 size={20} />}
          title="Workflows you can trust"
          description="Every extraction workflow is validated with documented quality metrics. See exactly how well each workflow performs before you trust it with real decisions. Accuracy, consistency, and edge cases are tested and maintained."
        />
        <ValueCard
          icon={<Upload size={20} />}
          title="Built for research administration"
          description="Purpose-built for grants, compliance, and institutional documents, not a generic chatbot with a file upload bolted on. Multi-format support (PDF, Word, Excel, images), automatic OCR, and team collaboration out of the box."
        />
        <ValueCard
          icon={<Sparkles size={20} />}
          title="Prove your knowledge base earns its keep"
          description="Run Validate & improve on any KB to get a quality score and a one-click recipe to improve it. Typically $1–$5 in tokens and 10–20 minutes — and nothing changes until you click Apply."
        />
        <ValueCard
          icon={<Target size={20} />}
          title="Know your extractions are right before you trust them"
          description="Run Validate & improve on any extraction to score it against test cases and get a one-click recipe to improve accuracy. Typically $1–$5 and 5–15 minutes — and nothing changes until you click Apply."
        />
        <ValueCard
          icon={<Zap size={20} />}
          title="Stop guessing which workflow config is best"
          description="Run Validate & improve on any workflow to find the per-step model and prompt combination that scores highest on your test inputs. Typically $5–$15 and 15–30 minutes — and nothing changes until you click Apply."
        />
      </div>

      {/* First step CTA */}
      <div
        style={{
          marginTop: 20,
          padding: '16px 20px',
          borderRadius: 'var(--ui-radius, 12px)',
          backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 6%, white)',
          border: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 25%, #e5e7eb)',
        }}
      >
        <div style={{ fontSize: 14, fontWeight: 600, color: '#111827', marginBottom: 6 }}>
          Ready to get started?
        </div>
        <div style={{ fontSize: 13, color: '#6b7280', lineHeight: 1.5, marginBottom: 14 }}>
          Upload your first document and see what Vandalizer can do with it: extract data, summarize, classify, or just chat about it.
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button
            onClick={onSwitchToFiles}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '8px 16px',
              fontSize: 13,
              fontWeight: 600,
              fontFamily: 'inherit',
              border: 'none',
              borderRadius: 8,
              backgroundColor: 'var(--highlight-color, #eab308)',
              color: 'var(--highlight-text-color, #000)',
              cursor: 'pointer',
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.opacity = '0.9'
              e.currentTarget.style.transform = 'translateY(-1px)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.opacity = '1'
              e.currentTarget.style.transform = 'translateY(0)'
            }}
          >
            Upload a document <ArrowRight size={14} />
          </button>
          <button
            onClick={() => onSendMessage(
              'Walk me through what Vandalizer can do and how it works.',
              true,
            )}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '8px 16px',
              fontSize: 13,
              fontWeight: 500,
              fontFamily: 'inherit',
              border: '1px solid #d1d5db',
              borderRadius: 8,
              backgroundColor: '#fff',
              color: '#374151',
              cursor: 'pointer',
              transition: 'all 0.15s',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.borderColor = 'var(--highlight-color, #eab308)'
              e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 5%, white)'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.borderColor = '#d1d5db'
              e.currentTarget.style.backgroundColor = '#fff'
            }}
          >
            Show me how it works
          </button>
        </div>
      </div>

      {/* Certification link */}
      <button
        onClick={() => onSendMessage(
          'Tell me about the Vandal Workflow Architect certification program.',
          true,
        )}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          width: '100%',
          marginTop: 12,
          padding: '12px 16px',
          borderRadius: 'var(--ui-radius, 12px)',
          backgroundColor: '#fff',
          border: '1px solid #e5e7eb',
          cursor: 'pointer',
          fontFamily: 'inherit',
          textAlign: 'left',
          transition: 'all 0.15s',
        }}
        onMouseEnter={e => {
          e.currentTarget.style.borderColor = 'var(--highlight-color, #eab308)'
          e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 4%, white)'
        }}
        onMouseLeave={e => {
          e.currentTarget.style.borderColor = '#e5e7eb'
          e.currentTarget.style.backgroundColor = '#fff'
        }}
      >
        <div
          style={{
            flexShrink: 0,
            width: 32,
            height: 32,
            borderRadius: 8,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 10%, white)',
            color: 'var(--highlight-color, #eab308)',
          }}
        >
          <GraduationCap size={16} />
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>
            Want to go deeper?
          </span>
          <span style={{ fontSize: 13, color: '#6b7280', marginLeft: 6 }}>
            Earn your Vandal Workflow Architect certification with guided, hands-on modules.
          </span>
        </div>
        <ArrowRight size={14} style={{ flexShrink: 0, color: '#6b7280' }} />
      </button>
    </div>
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
                color: '#6b7280',
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
          color: '#6b7280',
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
