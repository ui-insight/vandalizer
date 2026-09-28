import { useRef, type ChangeEvent, type ReactNode } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  Award,
  CheckCircle2,
  Clock3,
  FileSearch,
  FileUp,
  MessageSquare,
  Workflow,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import type { OnboardingStatus, RecentActivityItem } from '../../api/config'
import { useCertificationPanelOptional } from '../../contexts/CertificationPanelContext'
import { ConceptStrip } from './ConceptTip'
import { useUploadPolicy } from '../../hooks/useUploadPolicy'
import { OnboardingStepper } from './WelcomeExperience'

/**
 * "Start certification" / "Continue certification" home CTA. The course runs
 * right in chat (certification tools + cards), so the button just sends the
 * kickoff message. Null when the user is already certified. Works without the
 * CertificationPanelProvider (unit tests) — it then falls back to "start".
 */
function useCertificationCta(): { label: string; message: string } | null {
  const cert = useCertificationPanelOptional()
  const progress = cert?.progress ?? null
  if (progress?.certified) return null
  const completedCount = progress
    ? Object.values(progress.modules ?? {}).filter((m) => m?.completed).length
    : 0
  if (completedCount > 0) {
    return {
      label: `Continue certification (${completedCount}/11)`,
      message: 'Continue my certification — show my progress and the next module.',
    }
  }
  return {
    label: 'Start the certification course',
    message: 'Start the Vandalizer certification course — show me where to begin.',
  }
}

const FIRST_RUN_PROMPTS = [
  {
    label: 'Extract deadlines',
    prompt: 'Extract every deadline, deliverable, and owner from this document.',
  },
  {
    label: 'Find compliance gaps',
    prompt: 'Review this document for compliance gaps, missing requirements, and follow-up risks.',
  },
  {
    label: 'Summarize a proposal',
    prompt: 'Summarize this grant proposal into the key aims, budget notes, timeline, and risk areas.',
  },
  {
    label: 'Compare versions',
    prompt: 'Compare these two documents and highlight the material differences that need review.',
  },
] as const

const DEFAULT_RETURNING_PROMPTS = [
  'Summarize my latest document in 5 bullets.',
  'Extract deadlines, owners, and deliverables from my latest documents.',
  'Find compliance gaps or missing fields in the documents I should review today.',
  'Compare two versions and tell me what changed.',
]

interface UploadPrimaryButtonProps {
  label?: string
  disabled?: boolean
  onAttachFiles: (files: File[]) => void
}

function UploadPrimaryButton({
  label = 'Upload a document',
  disabled,
  onAttachFiles,
}: UploadPrimaryButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const { accept } = useUploadPolicy()

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    if (files.length > 0) onAttachFiles(files)
    event.target.value = ''
  }

  return (
    <>
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 8,
          padding: '11px 16px',
          borderRadius: 12,
          border: 'none',
          background: 'var(--highlight-color, #eab308)',
          color: '#111827',
          fontFamily: 'inherit',
          fontSize: 14,
          fontWeight: 800,
          cursor: disabled ? 'default' : 'pointer',
          boxShadow: '0 12px 28px rgba(0,0,0,0.16)',
          opacity: disabled ? 0.55 : 1,
        }}
      >
        <FileUp size={16} />
        {label}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple
        className="hidden"
        aria-label={label}
        onChange={handleChange}
      />
    </>
  )
}

function UploadPillButton({
  label,
  inverse,
  disabled,
  onAttachFiles,
}: {
  label: string
  inverse?: boolean
  disabled?: boolean
  onAttachFiles: (files: File[]) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const { accept } = useUploadPolicy()

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    if (files.length > 0) onAttachFiles(files)
    event.target.value = ''
  }

  return (
    <>
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 7,
          padding: '10px 12px',
          borderRadius: 12,
          border: inverse ? '1px solid rgba(255,255,255,0.22)' : '1px solid #e5e7eb',
          background: inverse ? 'rgba(255,255,255,0.10)' : '#ffffff',
          color: inverse ? '#ffffff' : '#374151',
          fontFamily: 'inherit',
          fontSize: 13,
          fontWeight: 700,
          cursor: disabled ? 'default' : 'pointer',
          opacity: disabled ? 0.55 : 1,
        }}
      >
        <FileUp size={14} />
        {label}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        multiple
        className="hidden"
        aria-label={label}
        onChange={handleChange}
      />
    </>
  )
}

function ActionPillButton({
  label,
  icon: Icon,
  inverse,
  disabled,
  onClick,
}: {
  label: string
  icon: LucideIcon
  inverse?: boolean
  disabled?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 7,
        padding: '10px 12px',
        borderRadius: 12,
        border: inverse ? '1px solid rgba(255,255,255,0.22)' : '1px solid #e5e7eb',
        background: inverse ? 'rgba(255,255,255,0.10)' : '#ffffff',
        color: inverse ? '#ffffff' : '#374151',
        fontFamily: 'inherit',
        fontSize: 13,
        fontWeight: 700,
        cursor: disabled ? 'default' : 'pointer',
        opacity: disabled ? 0.55 : 1,
      }}
    >
      <Icon size={14} />
      {label}
    </button>
  )
}

function SampleAnswerPreview({ inverse = false }: { inverse?: boolean }) {
  return (
    <div
      style={{
        padding: inverse ? 14 : 12,
        borderRadius: 14,
        border: inverse ? '1px solid rgba(255,255,255,0.16)' : '1px solid #e5e7eb',
        background: inverse ? 'rgba(255,255,255,0.10)' : '#f8fafc',
        backdropFilter: inverse ? 'blur(6px)' : undefined,
        boxShadow: inverse ? '0 10px 30px rgba(0,0,0,0.10)' : 'none',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 10,
        }}
      >
        <div>
          <div
            style={{
              fontSize: 11,
              fontWeight: 800,
              letterSpacing: '0.05em',
              textTransform: 'uppercase',
              color: inverse ? 'rgba(255,255,255,0.72)' : '#64748b',
            }}
          >
            Preview of the demo result
          </div>
        </div>
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '5px 8px',
            borderRadius: 999,
            background: inverse ? 'rgba(255,255,255,0.12)' : '#ffffff',
            color: inverse ? '#ffffff' : '#334155',
            fontSize: 11,
            fontWeight: 700,
            border: inverse ? '1px solid rgba(255,255,255,0.16)' : '1px solid #e5e7eb',
          }}
        >
          <CheckCircle2 size={12} />
          Includes source
        </div>
      </div>

      <div
        style={{
          marginTop: 12,
          padding: '8px 10px',
          borderRadius: 10,
          background: inverse ? 'rgba(255,255,255,0.08)' : '#ffffff',
          border: inverse ? '1px solid rgba(255,255,255,0.12)' : '1px solid #e5e7eb',
          fontSize: 12,
          lineHeight: 1.5,
          color: inverse ? 'rgba(255,255,255,0.82)' : '#475569',
        }}
      >
        <strong>Question:</strong> When are letters of commitment due?
      </div>

      <div
        style={{
          marginTop: 12,
          display: 'grid',
          gridTemplateColumns: '1fr auto',
          gap: 10,
          alignItems: 'end',
        }}
      >
        <div>
          <div style={{ fontSize: 12, color: inverse ? 'rgba(255,255,255,0.72)' : '#64748b' }}>Answer</div>
          <div
            style={{
              marginTop: 3,
              fontSize: 21,
              lineHeight: 1.1,
              fontWeight: 800,
              color: inverse ? '#ffffff' : '#111827',
            }}
          >
            Oct 5, 2026
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 12, color: inverse ? 'rgba(255,255,255,0.72)' : '#64748b' }}>Source</div>
          <div
            style={{
              marginTop: 3,
              fontSize: 13,
              fontWeight: 700,
              color: inverse ? '#ffffff' : '#334155',
            }}
          >
            Page 4, Timeline
          </div>
        </div>
      </div>

      <div
        style={{
          marginTop: 12,
          padding: '10px 11px',
          borderRadius: 12,
          border: inverse ? '1px solid rgba(255,255,255,0.14)' : '1px solid #e5e7eb',
          background: inverse ? 'rgba(0,0,0,0.08)' : '#ffffff',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 7,
            marginBottom: 6,
            fontSize: 12,
            fontWeight: 800,
            color: inverse ? '#ffffff' : '#374151',
          }}
        >
          <FileSearch size={13} style={{ color: inverse ? '#ffffff' : 'var(--highlight-on-light, #806600)' }} />
          Linked evidence
        </div>
        <div
          style={{
            fontSize: 13,
            lineHeight: 1.55,
            color: inverse ? 'rgba(255,255,255,0.88)' : '#4b5563',
          }}
        >
          "Letters of commitment are due no later than October 5, 2026 and must name the responsible site lead."
        </div>
      </div>
    </div>
  )
}

function GlossaryDisclosure() {
  return (
    <details
      style={{
        borderRadius: 12,
        border: '1px solid #e5e7eb',
        backgroundColor: '#ffffff',
        padding: '10px 12px',
      }}
    >
      <summary
        style={{
          cursor: 'pointer',
          fontSize: 12,
          fontWeight: 700,
          color: '#64748b',
          listStyle: 'none',
        }}
      >
        New here? See key terms
      </summary>
      <div style={{ marginTop: 12 }}>
        <ConceptStrip heading="" />
      </div>
    </details>
  )
}

function SurfaceCard({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: string
  children: ReactNode
}) {
  return (
    <div
      style={{
        padding: 18,
        borderRadius: 'var(--ui-radius, 12px)',
        border: '1px solid #e5e7eb',
        backgroundColor: '#ffffff',
        boxShadow: '0 12px 28px rgba(0,0,0,0.04)',
      }}
    >
      <div style={{ fontSize: 16, fontWeight: 700, color: '#111827' }}>{title}</div>
      <div style={{ marginTop: 6, fontSize: 13, lineHeight: 1.5, color: '#6b7280' }}>{subtitle}</div>
      <div style={{ marginTop: 14 }}>{children}</div>
    </div>
  )
}

function PromptButton({
  label,
  onClick,
}: {
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 10,
        width: '100%',
        padding: '11px 12px',
        borderRadius: 10,
        border: '1px solid #e5e7eb',
        backgroundColor: '#ffffff',
        color: '#374151',
        cursor: 'pointer',
        fontFamily: 'inherit',
        fontSize: 13,
        fontWeight: 600,
        textAlign: 'left',
        transition: 'border-color 0.15s ease, background-color 0.15s ease',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.borderColor = 'var(--highlight-color, #eab308)'
        e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 6%, white)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.borderColor = '#e5e7eb'
        e.currentTarget.style.backgroundColor = '#ffffff'
      }}
    >
      <span>{label}</span>
      <ArrowRight size={14} style={{ color: 'var(--highlight-on-light, #806600)', flexShrink: 0 }} />
    </button>
  )
}

function activityResumeMessage(item: RecentActivityItem): string {
  const title = item.title
  if (item.type === 'search_set_run') {
    if (item.status === 'failed') return `My "${title}" extraction failed. Help me understand what went wrong`
    if (item.status === 'running') return `Check on my running "${title}" extraction`
    return `Show me the results from my "${title}" extraction`
  }
  if (item.type === 'workflow_run') {
    if (item.status === 'failed') return `My "${title}" workflow failed. Help me debug it`
    if (item.status === 'running') return `Check on my running "${title}" workflow`
    return `Show me the results from my "${title}" workflow run`
  }
  return `Continue our conversation about "${title}"`
}

function alertReviewMessage(itemName: string): string {
  return `Check quality of ${itemName}`
}

const ACTIVITY_ICONS: Record<string, LucideIcon> = {
  conversation: MessageSquare,
  search_set_run: FileSearch,
  workflow_run: Workflow,
}

function recentActivityLabel(item: RecentActivityItem): string {
  if (item.status === 'running') return `${item.relative_time || 'Active now'} • Running`
  if (item.status === 'failed') return `${item.relative_time || 'Needs review'} • Failed`
  return `${item.relative_time || 'Recent'} • Completed`
}

function returningHeroTitle(status: OnboardingStatus | null): string {
  if (status?.has_only_onboarding_docs) return 'Make this workspace yours'
  if ((status?.active_alerts.length ?? 0) > 0) return 'Review what changed since your last visit'
  if ((status?.recent_activity.length ?? 0) > 0) return 'Resume work in one click'
  if ((status?.unprocessed_doc_count ?? 0) > 0) return 'Your latest documents are ready'
  if (status?.has_documents) return 'Jump back into active work'
  return 'Start with one real document'
}

function starterSuggestions(status: OnboardingStatus | null, suggestionPills: string[]): string[] {
  if (suggestionPills.length > 0) return suggestionPills.slice(0, 4)
  if (status?.suggestion_pills?.length) return status.suggestion_pills.slice(0, 4)
  if (status?.has_only_onboarding_docs) {
    return [
      'Help me move from the sample demo to my own documents.',
      'What should I upload first to get useful results fast?',
      'Show me the exact pattern I should reuse on my own files.',
      'Run the sample demo again and tell me what to notice.',
    ]
  }
  if (status && !status.has_documents) {
    return [
      'Help me upload and analyze my first document.',
      'Show me how source-linked answers work in Vandalizer.',
      'What kind of documents can I upload here?',
      'Run the sample demo and explain what to notice.',
    ]
  }
  return DEFAULT_RETURNING_PROMPTS
}

type ReturningActionKind = 'upload' | 'resume' | 'alert' | 'process' | 'composer' | 'demo'

interface ReturningPrimaryAction {
  kind: ReturningActionKind
  eyebrow: string
  title: string
  description: string
  cta: string
  icon: LucideIcon
  prompt?: string
}

function processingPrompt(status: OnboardingStatus): string {
  if (status.top_extraction_set_name) {
    return `Run ${status.top_extraction_set_name} on my latest documents`
  }
  if (status.top_workflow_name) {
    return `Run ${status.top_workflow_name} on my latest documents`
  }
  return 'Extract deadlines, owners, and deliverables from my latest documents.'
}

function deriveReturningPrimaryAction(
  status: OnboardingStatus | null,
  orgName: string,
): ReturningPrimaryAction {
  if (!status) {
    return {
      kind: 'upload',
      eyebrow: 'Start here',
      title: 'Upload a document',
      description: `${orgName} gets useful once it has a real file to analyze.`,
      cta: 'Upload a document',
      icon: FileUp,
    }
  }

  const firstAlert = status.active_alerts[0]
  if (status.has_only_onboarding_docs) {
    return {
      kind: 'upload',
      eyebrow: 'Next step',
      title: 'Upload one of your own documents',
      description: 'Replace the demo with a real proposal, policy, or compliance file so this home can start surfacing actual work.',
      cta: 'Upload your document',
      icon: FileUp,
    }
  }

  if (firstAlert) {
    return {
      kind: 'alert',
      eyebrow: 'Needs review',
      title: firstAlert.item_name,
      description: firstAlert.message,
      cta: 'Review alert',
      icon: AlertTriangle,
      prompt: alertReviewMessage(firstAlert.item_name),
    }
  }

  const recent = status.recent_activity[0]
  if (recent) {
    return {
      kind: 'resume',
      eyebrow: 'Resume',
      title: recent.title,
      description: recentActivityLabel(recent),
      cta: recent.type === 'conversation' ? 'Continue chat' : recent.status === 'failed' ? 'Debug run' : 'Open results',
      icon: ACTIVITY_ICONS[recent.type] ?? Clock3,
      prompt: activityResumeMessage(recent),
    }
  }

  if (status.unprocessed_doc_count > 0) {
    return {
      kind: 'process',
      eyebrow: 'Ready to process',
      title: status.top_extraction_set_name
        ? `Run ${status.top_extraction_set_name}`
        : status.top_workflow_name
          ? `Run ${status.top_workflow_name}`
          : 'Process the latest documents',
      description: `${status.unprocessed_doc_count} document${status.unprocessed_doc_count === 1 ? '' : 's'} are ready for a first pass.`,
      cta: status.top_extraction_set_name ? 'Run extraction' : status.top_workflow_name ? 'Run workflow' : 'Start with summary',
      icon: status.top_extraction_set_name ? FileSearch : status.top_workflow_name ? Workflow : FileSearch,
      prompt: processingPrompt(status),
    }
  }

  if (status.has_documents && !status.has_chatted_with_docs) {
    return {
      kind: 'composer',
      eyebrow: 'First grounded question',
      title: 'Ask about the documents already in your workspace',
      description: 'Start with a summary, a deadline check, or a compliance question tied to your actual files.',
      cta: 'Ask about current work',
      icon: MessageSquare,
    }
  }

  if (status.has_documents) {
    return {
      kind: 'composer',
      eyebrow: 'Fastest path',
      title: 'Ask about current work',
      description: 'Use the composer to summarize, compare, extract, or troubleshoot against the documents you already have loaded.',
      cta: 'Open composer',
      icon: MessageSquare,
    }
  }

  return {
    kind: 'upload',
    eyebrow: 'Activation',
    title: 'Upload a real document',
    description: 'Skip the generic tour and give the workspace something real to reason over.',
    cta: 'Upload a document',
    icon: FileUp,
  }
}

function FocusNowCard({
  action,
  disabled,
  onRunDemo,
  onAttachFiles,
  onFocusComposer,
  onSendMessage,
}: {
  action: ReturningPrimaryAction
  disabled?: boolean
  onRunDemo: () => void
  onAttachFiles: (files: File[]) => void
  onFocusComposer: () => void
  onSendMessage: (message: string) => void
}) {
  const Icon = action.icon

  const handleAction = () => {
    if (action.kind === 'demo') {
      onRunDemo()
      return
    }
    if (action.kind === 'composer') {
      onFocusComposer()
      return
    }
    if (action.prompt) {
      onSendMessage(action.prompt)
    }
  }

  return (
    <div
      style={{
        padding: 16,
        borderRadius: 16,
        border: '1px solid #dce1e5',
        background: '#f7f8f9',
        backdropFilter: 'blur(8px)',
        boxShadow: 'none',
      }}
    >
      <div
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 7,
          padding: '5px 9px',
          borderRadius: 999,
          background: '#edf0f2',
          fontSize: 11,
          fontWeight: 650,
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
          color: '#59616b',
        }}
      >
        {action.eyebrow}
      </div>

      <div style={{ marginTop: 12, display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 38,
            height: 38,
            borderRadius: 12,
            background: '#edf0f2',
            flexShrink: 0,
          }}
        >
          <Icon size={18} />
        </div>
        <div>
          <div style={{ fontSize: 18, lineHeight: 1.15, fontWeight: 650, color: '#242b32' }}>
            {action.title}
          </div>
          <div style={{ marginTop: 7, fontSize: 13, lineHeight: 1.55, color: '#59616b' }}>
            {action.description}
          </div>
        </div>
      </div>

      <div style={{ marginTop: 14 }}>
        {action.kind === 'upload' ? (
          <UploadPrimaryButton
            label={action.cta}
            disabled={disabled}
            onAttachFiles={onAttachFiles}
          />
        ) : (
          <button
            type="button"
            disabled={disabled}
            onClick={handleAction}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              padding: '11px 16px',
              borderRadius: 12,
              border: 'none',
              background: 'var(--highlight-color, #eab308)',
              color: '#111827',
              fontFamily: 'inherit',
              fontSize: 14,
              fontWeight: 650,
              cursor: disabled ? 'default' : 'pointer',
              opacity: disabled ? 0.55 : 1,
            }}
          >
            {action.cta}
            <ArrowRight size={15} />
          </button>
        )}
      </div>
    </div>
  )
}

function QueueItemButton({
  icon: Icon,
  title,
  subtitle,
  tone = 'neutral',
  onClick,
}: {
  icon: LucideIcon
  title: string
  subtitle: string
  tone?: 'neutral' | 'warning'
  onClick: () => void
}) {
  const palette = tone === 'warning'
    ? {
        border: 'color-mix(in srgb, var(--highlight-color, #eab308) 42%, #e5e7eb)',
        background: 'color-mix(in srgb, var(--highlight-color, #eab308) 8%, white)',
        icon: '#a16207',
      }
    : {
        border: '#e5e7eb',
        background: '#ffffff',
        icon: '#6b7280',
      }

  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 11,
        width: '100%',
        padding: '12px 12px',
        borderRadius: 12,
        border: `1px solid ${palette.border}`,
        background: palette.background,
        color: '#111827',
        cursor: 'pointer',
        fontFamily: 'inherit',
        textAlign: 'left',
        transition: 'border-color 0.15s ease, transform 0.15s ease',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.transform = 'translateY(-1px)'
        e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 50%, #d1d5db)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.transform = 'translateY(0)'
        e.currentTarget.style.borderColor = palette.border
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 34,
          height: 34,
          borderRadius: 10,
          background: tone === 'warning'
            ? 'rgba(234,179,8,0.14)'
            : 'color-mix(in srgb, var(--highlight-color, #eab308) 10%, white)',
          color: palette.icon,
          flexShrink: 0,
        }}
      >
        <Icon size={16} />
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: '#111827', lineHeight: 1.35 }}>{title}</div>
        <div style={{ marginTop: 4, fontSize: 12, lineHeight: 1.5, color: '#6b7280' }}>{subtitle}</div>
      </div>
      <ArrowRight size={14} style={{ marginTop: 2, flexShrink: 0, color: 'var(--highlight-on-light, #806600)' }} />
    </button>
  )
}

function ResumeQueue({
  status,
  onSendMessage,
}: {
  status: OnboardingStatus | null
  onSendMessage: (message: string) => void
}) {
  if (!status) {
    return (
      <SurfaceCard
        title="Continue where you left off"
        subtitle="This section turns into a work queue as soon as the workspace has files, runs, or alerts."
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <PromptButton
            label="Help me upload and analyze my first document."
            onClick={() => onSendMessage('Help me upload and analyze my first document.')}
          />
        </div>
      </SurfaceCard>
    )
  }

  const hasQueue =
    status.recent_activity.length > 0 ||
    status.active_alerts.length > 0 ||
    status.unprocessed_doc_count > 0 ||
    status.has_only_onboarding_docs

  return (
    <SurfaceCard
      title="Continue where you left off"
      subtitle="Recent runs and items that need your attention."
    >
      {status.since_last_visit && (
        <div
          style={{
            marginBottom: 12,
            padding: '8px 10px',
            borderRadius: 10,
            background: '#f8fafc',
            border: '1px solid #e5e7eb',
            fontSize: 12,
            lineHeight: 1.5,
            color: '#64748b',
          }}
        >
          {status.since_last_visit}
        </div>
      )}

      {!hasQueue ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {status.has_documents ? (
            <>
              <PromptButton
                label="Ask about the documents already in my workspace."
                onClick={() => onSendMessage('Ask about the documents already in my workspace.')}
              />
              <PromptButton
                label="Suggest the next best workflow for the files I have."
                onClick={() => onSendMessage('Suggest the next best workflow for the files I have.')}
              />
            </>
          ) : (
            <>
              <PromptButton
                label="Help me upload and analyze my first document."
                onClick={() => onSendMessage('Help me upload and analyze my first document.')}
              />
              <PromptButton
                label="Show me how source-linked answers work."
                onClick={() => onSendMessage('Show me how source-linked answers work in Vandalizer.')}
              />
            </>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {status.active_alerts.map((alert) => (
            <QueueItemButton
              key={`${alert.item_name}-${alert.message}`}
              icon={AlertTriangle}
              title={alert.item_name}
              subtitle={alert.message}
              tone="warning"
              onClick={() => onSendMessage(alertReviewMessage(alert.item_name))}
            />
          ))}

          {status.recent_activity.map((item) => (
            <QueueItemButton
              key={`${item.type}-${item.title}-${item.relative_time}`}
              icon={ACTIVITY_ICONS[item.type] ?? Clock3}
              title={item.title}
              subtitle={recentActivityLabel(item)}
              onClick={() => onSendMessage(activityResumeMessage(item))}
            />
          ))}

          {status.unprocessed_doc_count > 0 && (
            <QueueItemButton
              icon={FileSearch}
              title={
                status.top_extraction_set_name
                  ? `Run ${status.top_extraction_set_name}`
                  : status.top_workflow_name
                    ? `Run ${status.top_workflow_name}`
                    : 'Process new documents'
              }
              subtitle={`${status.unprocessed_doc_count} document${status.unprocessed_doc_count === 1 ? '' : 's'} are waiting for a first pass.`}
              onClick={() => onSendMessage(processingPrompt(status))}
            />
          )}

          {status.has_only_onboarding_docs && (
            <QueueItemButton
              icon={FileUp}
              title="Replace the sample with your own file"
              subtitle="Upload a real document so the assistant can show live deadlines, risks, and extracted fields from your work."
              onClick={() => onSendMessage('Help me move from the sample demo to my own documents.')}
            />
          )}
        </div>
      )}
    </SurfaceCard>
  )
}

function ReadyAssetBadge({ label }: { label: string }) {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '6px 9px',
        borderRadius: 999,
        border: '1px solid #e5e7eb',
        background: '#ffffff',
        fontSize: 12,
        fontWeight: 700,
        color: '#374151',
      }}
    >
      <CheckCircle2 size={12} style={{ color: 'var(--highlight-on-light, #806600)' }} />
      {label}
    </div>
  )
}

interface SharedHomeProps {
  orgName: string
  brandIcon: string | null
  disabled?: boolean
  onRunDemo: () => void
  onAttachFiles: (files: File[]) => void
  onFocusComposer: () => void
  onSendMessage: (message: string) => void
}

export function FirstSessionHome({ orgName, brandIcon, disabled, onRunDemo, onAttachFiles, onSendMessage }: SharedHomeProps) {
  const certCta = useCertificationCta()
  return (
    <div className="chat-home first-session-home">
      <div className="chat-home-heading">
        {brandIcon && <img src={brandIcon} alt="" />}
        <div><span className="home-eyebrow">Welcome to {orgName}</span><h2>Start with a document. Find an answer.</h2><p>Upload a file or try the sample, then ask a question and inspect its supporting sources.</p></div>
      </div>
      <ol className="first-task-steps" aria-label="Your first task"><li aria-current="step"><strong>1</strong> Choose a document</li><li><strong>2</strong> Ask a question</li><li><strong>3</strong> Check the evidence</li></ol>
      <div className="home-primary-actions"><UploadPrimaryButton disabled={disabled} onAttachFiles={onAttachFiles} /><ActionPillButton label="Run sample demo" icon={Zap} disabled={disabled} onClick={onRunDemo} /></div>
      <div className="home-two-columns">
        <SurfaceCard title="Questions to try" subtitle="Once your file is attached, start with a specific question.">
          {FIRST_RUN_PROMPTS.map(prompt => <PromptButton key={prompt.label} label={prompt.label} onClick={() => onSendMessage(prompt.prompt)} />)}
        </SurfaceCard>
        <SampleAnswerPreview />
      </div>
      <p className="home-evidence-note">For document and knowledge-base answers, open the source references to check the original context. Missing or incomplete sources can limit an answer.</p>
      <GlossaryDisclosure />
      {certCta && <button className="home-learning-link" type="button" disabled={disabled} onClick={() => onSendMessage(certCta.message)}><Award size={14} /> {certCta.label}</button>}
    </div>
  )
}

export function ReturningHome({ orgName, brandIcon, disabled, onRunDemo, onAttachFiles, onFocusComposer, onSendMessage, status, suggestionPills }: SharedHomeProps & { status: OnboardingStatus | null; suggestionPills: string[] }) {
  const certCta = useCertificationCta()
  const primaryAction = deriveReturningPrimaryAction(status, orgName)
  const suggestions = starterSuggestions(status, suggestionPills).slice(0, 3)
  const hasQueue = !!status && (status.recent_activity.length > 0 || status.active_alerts.length > 0 || status.unprocessed_doc_count > 0 || status.has_only_onboarding_docs)
  const readyBadges = [status?.top_extraction_set_name ? `Extraction: ${status.top_extraction_set_name}` : null, status?.top_workflow_name ? `Workflow: ${status.top_workflow_name}` : null, status?.has_ready_knowledge_base ? 'Knowledge base ready' : null].filter((value): value is string => !!value)
  return (
    <div className="chat-home">
      <div className="chat-home-heading">
        {brandIcon && <img src={brandIcon} alt="" />}
        <div><span className="home-eyebrow">Your workspace</span><h2>{returningHeroTitle(status)}</h2>{status?.daily_guidance && <p>{status.daily_guidance}</p>}</div>
      </div>
      <FocusNowCard action={primaryAction} disabled={disabled} onRunDemo={onRunDemo} onAttachFiles={onAttachFiles} onFocusComposer={onFocusComposer} onSendMessage={onSendMessage} />
      <div className="home-primary-actions">
        {primaryAction.kind !== 'upload' && <UploadPillButton label="Upload another document" disabled={disabled} onAttachFiles={onAttachFiles} />}
        {!status?.has_documents && <ActionPillButton label="Run sample demo" icon={Zap} disabled={disabled} onClick={onRunDemo} />}
      </div>
      <div className="home-two-columns">
        {hasQueue && <ResumeQueue status={status} onSendMessage={onSendMessage} />}
        <SurfaceCard title="Suggested questions" subtitle="Start from your existing documents and tools.">
          {suggestions.map(suggestion => <PromptButton key={suggestion} label={suggestion} onClick={() => onSendMessage(suggestion)} />)}
        </SurfaceCard>
      </div>
      {readyBadges.length > 0 && <div className="home-ready-assets"><span>Ready in this workspace</span>{readyBadges.map(badge => <ReadyAssetBadge key={badge} label={badge} />)}</div>}
      {status && !status.has_documents && <OnboardingStepper status={status} hasChatAboutDocs={status.has_chatted_with_docs} />}
      {certCta && <button className="home-learning-link" type="button" disabled={disabled} onClick={() => onSendMessage(certCta.message)}><Award size={14} /> {certCta.label}</button>}
    </div>
  )
}
