import { useRef, type ChangeEvent, type ReactNode } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  Award,
  BookOpen,
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
import { useWorkspaceTour } from '../../contexts/WorkspaceTourContext'
import { ConceptStrip } from './ConceptTip'
import { useUploadPolicy } from '../../hooks/useUploadPolicy'

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

const DEFAULT_RETURNING_PROMPTS = [
  'Help me plan and carry out a task.',
  'Find the knowledge bases available to me.',
  'Help me turn a recurring task into a workflow.',
  'Summarize the documents I select and cite the sources.',
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
          gap: 'var(--workspace-space-8)',
          padding: "11px var(--workspace-space-16)",
          borderRadius: 'var(--workspace-radius-large)',
          border: 'none',
          background: 'var(--highlight-color, #eab308)',
          color: '#111827',
          fontFamily: 'inherit',
          fontSize: 'var(--workspace-font-body)',
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
          padding: "var(--workspace-space-12) var(--workspace-space-12)",
          borderRadius: 'var(--workspace-radius-large)',
          border: inverse ? '1px solid rgba(255,255,255,0.22)' : '1px solid #e5e7eb',
          background: inverse ? 'rgba(255,255,255,0.10)' : '#ffffff',
          color: inverse ? '#ffffff' : '#374151',
          fontFamily: 'inherit',
          fontSize: 'var(--workspace-font-control)',
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
        padding: "var(--workspace-space-12) var(--workspace-space-12)",
        borderRadius: 'var(--workspace-radius-large)',
        border: inverse ? '1px solid rgba(255,255,255,0.22)' : '1px solid #e5e7eb',
        background: inverse ? 'rgba(255,255,255,0.10)' : '#ffffff',
        color: inverse ? '#ffffff' : '#374151',
        fontFamily: 'inherit',
        fontSize: 'var(--workspace-font-control)',
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
          gap: 'var(--workspace-space-12)',
        }}
      >
        <div>
          <div
            style={{
              fontSize: 'var(--workspace-font-meta)',
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
            gap: 'var(--workspace-space-6)',
            padding: "var(--workspace-space-6) var(--workspace-space-8)",
            borderRadius: 999,
            background: inverse ? 'rgba(255,255,255,0.12)' : '#ffffff',
            color: inverse ? '#ffffff' : '#334155',
            fontSize: 'var(--workspace-font-meta)',
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
          marginTop: 'var(--workspace-space-12)',
          padding: "var(--workspace-space-8) var(--workspace-space-12)",
          borderRadius: 'var(--workspace-radius-large)',
          background: inverse ? 'rgba(255,255,255,0.08)' : '#ffffff',
          border: inverse ? '1px solid rgba(255,255,255,0.12)' : '1px solid #e5e7eb',
          fontSize: 'var(--workspace-font-meta)',
          lineHeight: 1.5,
          color: inverse ? 'rgba(255,255,255,0.82)' : '#475569',
        }}
      >
        <strong>Question:</strong> When are letters of commitment due?
      </div>

      <div
        style={{
          marginTop: 'var(--workspace-space-12)',
          display: 'grid',
          gridTemplateColumns: '1fr auto',
          gap: 'var(--workspace-space-12)',
          alignItems: 'end',
        }}
      >
        <div>
          <div style={{ fontSize: 'var(--workspace-font-meta)', color: inverse ? 'rgba(255,255,255,0.72)' : '#64748b' }}>Answer</div>
          <div
            style={{
              marginTop: 'var(--workspace-space-4)',
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
          <div style={{ fontSize: 'var(--workspace-font-meta)', color: inverse ? 'rgba(255,255,255,0.72)' : '#64748b' }}>Source</div>
          <div
            style={{
              marginTop: 'var(--workspace-space-4)',
              fontSize: 'var(--workspace-font-control)',
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
          marginTop: 'var(--workspace-space-12)',
          padding: "var(--workspace-space-12) 11px",
          borderRadius: 'var(--workspace-radius-large)',
          border: inverse ? '1px solid rgba(255,255,255,0.14)' : '1px solid #e5e7eb',
          background: inverse ? 'rgba(0,0,0,0.08)' : '#ffffff',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 7,
            marginBottom: 'var(--workspace-space-6)',
            fontSize: 'var(--workspace-font-meta)',
            fontWeight: 800,
            color: inverse ? '#ffffff' : '#374151',
          }}
        >
          <FileSearch size={13} style={{ color: inverse ? '#ffffff' : 'var(--highlight-on-light, #806600)' }} />
          Linked evidence
        </div>
        <div
          style={{
            fontSize: 'var(--workspace-font-control)',
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
        borderRadius: 'var(--workspace-radius-large)',
        border: "1px solid var(--workspace-border)",
        backgroundColor: '#ffffff',
        padding: "var(--workspace-space-12) var(--workspace-space-12)",
      }}
    >
      <summary
        style={{
          cursor: 'pointer',
          fontSize: 'var(--workspace-font-meta)',
          fontWeight: 700,
          color: '#64748b',
          listStyle: 'none',
        }}
      >
        New here? See key terms
      </summary>
      <div style={{ marginTop: 'var(--workspace-space-12)' }}>
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
        padding: 'var(--workspace-space-20)',
        borderRadius: 'var(--ui-radius, 12px)',
        border: "1px solid var(--workspace-border)",
        backgroundColor: '#ffffff',
        boxShadow: '0 12px 28px rgba(0,0,0,0.04)',
      }}
    >
      <div style={{ fontSize: 'var(--workspace-font-card-title)', fontWeight: 700, color: '#111827' }}>{title}</div>
      <div style={{ marginTop: 'var(--workspace-space-6)', fontSize: 'var(--workspace-font-control)', lineHeight: 1.5, color: '#6b7280' }}>{subtitle}</div>
      <div style={{ marginTop: 'var(--workspace-space-16)' }}>{children}</div>
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
        gap: 'var(--workspace-space-12)',
        width: '100%',
        padding: "11px var(--workspace-space-12)",
        borderRadius: 'var(--workspace-radius-large)',
        border: "1px solid var(--workspace-border)",
        backgroundColor: '#ffffff',
        color: '#374151',
        cursor: 'pointer',
        fontFamily: 'inherit',
        fontSize: 'var(--workspace-font-control)',
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
  return 'What would you like to get done?'
}

function starterSuggestions(status: OnboardingStatus | null, suggestionPills: string[]): string[] {
  if (suggestionPills.length > 0) return suggestionPills.slice(0, 4)
  if (status?.suggestion_pills?.length) return status.suggestion_pills.slice(0, 4)
  return DEFAULT_RETURNING_PROMPTS
}

type ReturningActionKind = 'knowledge' | 'upload' | 'resume' | 'alert' | 'process' | 'composer' | 'demo'

interface ReturningPrimaryAction {
  kind: ReturningActionKind
  eyebrow: string
  title: string
  description: string
  cta: string
  icon: LucideIcon
  prompt?: string
  activityId?: string
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
): ReturningPrimaryAction {
  const startAction: ReturningPrimaryAction = {
    kind: 'composer',
    eyebrow: 'Start with a goal',
    title: 'Ask a question or give the assistant a task',
    description: 'Explore an idea, draft a plan, use a knowledge base, or build a workflow. Add sources when your task needs them.',
    cta: 'Start a conversation',
    icon: MessageSquare,
  }
  if (!status) return startAction

  const firstAlert = status.active_alerts[0]
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
      activityId: recent.id,
    }
  }

  if (status.has_ready_knowledge_base) {
    return {
      kind: 'knowledge', eyebrow: 'Ready to explore',
      title: 'Ask your knowledge base',
      description: 'Choose a knowledge base and ask across its sources, with references you can inspect.',
      cta: 'Choose a knowledge base', icon: BookOpen,
    }
  }

  if (!status.has_documents && status.has_workflows) {
    return {
      kind: 'resume', eyebrow: 'Use your tools',
      title: 'Work with your saved workflows',
      description: 'Find a workflow, inspect its steps, or adapt it to your next task.',
      cta: 'Find a workflow', icon: Workflow,
      prompt: 'List my available workflows and help me choose one for my next task.',
    }
  }

  if (status.has_only_onboarding_docs) return startAction

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

  return startAction
}

function FocusNowCard({
  action,
  disabled,
  onRunDemo,
  onAttachFiles,
  onFocusComposer,
  onChooseKnowledgeBase,
  onSendMessage,
  onOpenActivity,
}: {
  action: ReturningPrimaryAction
  disabled?: boolean
  onRunDemo: () => void
  onAttachFiles: (files: File[]) => void
  onFocusComposer: () => void
  onChooseKnowledgeBase: () => void
  onSendMessage: (message: string) => void
  onOpenActivity: (activityId: string) => void
}) {
  const Icon = action.icon

  const handleAction = () => {
    if (action.kind === 'knowledge') {
      onChooseKnowledgeBase()
      return
    }
    if (action.kind === 'demo') {
      onRunDemo()
      return
    }
    if (action.kind === 'composer') {
      onFocusComposer()
      return
    }
    if (action.activityId) {
      onOpenActivity(action.activityId)
      return
    }
    if (action.prompt) {
      onSendMessage(action.prompt)
    }
  }

  return (
    <div
      style={{
        padding: 'var(--workspace-space-16)',
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
          padding: "var(--workspace-space-6) 9px",
          borderRadius: 999,
          background: '#edf0f2',
          fontSize: 'var(--workspace-font-meta)',
          fontWeight: 650,
          letterSpacing: '0.05em',
          textTransform: 'uppercase',
          color: '#59616b',
        }}
      >
        {action.eyebrow}
      </div>

      <div style={{ marginTop: 'var(--workspace-space-12)', display: 'flex', alignItems: 'flex-start', gap: 'var(--workspace-space-12)' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 38,
            height: 38,
            borderRadius: 'var(--workspace-radius-large)',
            background: '#edf0f2',
            flexShrink: 0,
          }}
        >
          <Icon size={18} />
        </div>
        <div>
          <div style={{ fontSize: 'var(--workspace-font-section-title)', lineHeight: 1.15, fontWeight: 650, color: '#242b32' }}>
            {action.title}
          </div>
          <div style={{ marginTop: 7, fontSize: 'var(--workspace-font-control)', lineHeight: 1.55, color: '#59616b' }}>
            {action.description}
          </div>
        </div>
      </div>

      <div style={{ marginTop: 'var(--workspace-space-16)' }}>
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
              gap: 'var(--workspace-space-8)',
              padding: "11px var(--workspace-space-16)",
              borderRadius: 'var(--workspace-radius-large)',
              border: 'none',
              background: 'var(--highlight-color, #eab308)',
              color: '#111827',
              fontFamily: 'inherit',
              fontSize: 'var(--workspace-font-body)',
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
        border: "color-mix(in srgb, var(--highlight-color, #eab308) 42%, var(--workspace-border))",
        background: 'color-mix(in srgb, var(--highlight-color, #eab308) 8%, white)',
        icon: '#a16207',
      }
    : {
        border: "var(--workspace-border)",
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
        padding: "var(--workspace-space-12) var(--workspace-space-12)",
        borderRadius: 'var(--workspace-radius-large)',
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
          borderRadius: 'var(--workspace-radius-large)',
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
        <div style={{ fontSize: 'var(--workspace-font-body)', fontWeight: 700, color: '#111827', lineHeight: 1.35 }}>{title}</div>
        <div style={{ marginTop: 'var(--workspace-space-4)', fontSize: 'var(--workspace-font-meta)', lineHeight: 1.5, color: '#6b7280' }}>{subtitle}</div>
      </div>
      <ArrowRight size={14} style={{ marginTop: 'var(--workspace-space-2)', flexShrink: 0, color: 'var(--highlight-on-light, #806600)' }} />
    </button>
  )
}

function ResumeQueue({
  status,
  onSendMessage,
  onOpenActivity,
}: {
  status: OnboardingStatus | null
  onSendMessage: (message: string) => void
  onOpenActivity: (activityId: string) => void
}) {
  if (!status) {
    return (
      <SurfaceCard
        title="Continue where you left off"
        subtitle="This section turns into a work queue as soon as the workspace has files, runs, or alerts."
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-12)' }}>
          <PromptButton
            label="Help me choose a useful task to start with."
            onClick={() => onSendMessage('Help me choose a useful task to start with.')}
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
            marginBottom: 'var(--workspace-space-12)',
            padding: "var(--workspace-space-8) var(--workspace-space-12)",
            borderRadius: 'var(--workspace-radius-large)',
            background: '#f8fafc',
            border: "1px solid var(--workspace-border)",
            fontSize: 'var(--workspace-font-meta)',
            lineHeight: 1.5,
            color: '#64748b',
          }}
        >
          {status.since_last_visit}
        </div>
      )}

      {!hasQueue ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-12)' }}>
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
                label="Help me choose a useful task to start with."
                onClick={() => onSendMessage('Help me choose a useful task to start with.')}
              />
              <PromptButton
                label="Show me how source-linked answers work."
                onClick={() => onSendMessage('Show me how source-linked answers work in Vandalizer.')}
              />
            </>
          )}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-12)' }}>
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
              key={item.id}
              icon={ACTIVITY_ICONS[item.type] ?? Clock3}
              title={item.title}
              subtitle={recentActivityLabel(item)}
              onClick={() => onOpenActivity(item.id)}
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
              title="Choose your next task"
              subtitle="Continue with a question, a knowledge base, your own files, or a reusable workflow."
              onClick={() => onSendMessage('Help me choose a useful task to start with.')}
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
        gap: 'var(--workspace-space-6)',
        padding: "var(--workspace-space-6) 9px",
        borderRadius: 999,
        border: "1px solid var(--workspace-border)",
        background: '#ffffff',
        fontSize: 'var(--workspace-font-meta)',
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
  onChooseKnowledgeBase: () => void
  onSendMessage: (message: string) => void
}

export function FirstSessionHome({ orgName, brandIcon, disabled, onRunDemo, onAttachFiles, onFocusComposer, onChooseKnowledgeBase, onSendMessage }: SharedHomeProps) {
  const certCta = useCertificationCta()
  const openTour = useWorkspaceTour()
  return (
    <div className="chat-home first-session-home">
      <div className="chat-home-heading">
        {brandIcon && <img src={brandIcon} alt="" />}
        <div><span className="home-eyebrow">Welcome to {orgName}</span><h2>What would you like to get done?</h2><p>Ask a question, upload a source, or try a sample.</p></div>
      </div>
      <div className="home-primary-actions">
        <ActionPillButton label="Start a conversation" icon={MessageSquare} disabled={disabled} onClick={onFocusComposer} />
        <UploadPillButton label="Upload a document" disabled={disabled} onAttachFiles={onAttachFiles} />
      </div>
      <details>
        <summary className="home-learning-link">Try a sample document demo</summary>
        <div className="home-two-columns">
          <SurfaceCard title="See one example" subtitle="Use a sample proposal to try extraction and source references.">
            <ActionPillButton label="Run sample demo" icon={Zap} disabled={disabled} onClick={onRunDemo} />
          </SurfaceCard>
          <SampleAnswerPreview />
        </div>
      </details>
      <ol className="first-task-steps" aria-label="Your first useful task">
        <li><strong>1</strong> Upload or try a sample</li>
        <li><strong>2</strong> Ask a specific question</li>
        <li><strong>3</strong> Inspect the source</li>
        <li><strong>4</strong> Export or reuse</li>
      </ol>
      <div className="home-two-columns">
        <SurfaceCard title="Explore your knowledge" subtitle="Ask across a knowledge base and follow the references back to the original sources.">
          <ActionPillButton label="Choose a knowledge base" icon={BookOpen} disabled={disabled} onClick={onChooseKnowledgeBase} />
        </SurfaceCard>
        <SurfaceCard title="Put the assistant to work" subtitle="Build a reusable workflow for a recurring task.">
          <ActionPillButton label="Build a workflow" icon={Workflow} disabled={disabled} onClick={() => onSendMessage('Help me turn a recurring task into a workflow.')} />
        </SurfaceCard>
      </div>
      <p className="home-evidence-note">For document and knowledge-base answers, open the source references to check the original context. Missing or incomplete sources can limit an answer.</p>
      <GlossaryDisclosure />
      {openTour && <button className="home-learning-link" type="button" onClick={openTour}>Take a quick tour</button>}
      {certCta && <button className="home-learning-link" type="button" disabled={disabled} onClick={() => onSendMessage(certCta.message)}><Award size={14} /> {certCta.label}</button>}
    </div>
  )
}

export function ReturningHome({ orgName, brandIcon, disabled, onRunDemo, onAttachFiles, onFocusComposer, onChooseKnowledgeBase, onSendMessage, onOpenActivity, status, suggestionPills }: SharedHomeProps & { onOpenActivity: (activityId: string) => void; status: OnboardingStatus | null; suggestionPills: string[] }) {
  const certCta = useCertificationCta()
  const openTour = useWorkspaceTour()
  const primaryAction = deriveReturningPrimaryAction(status)
  const suggestions = starterSuggestions(status, suggestionPills).slice(0, 3)
  const hasQueue = !!status && (status.recent_activity.length > 0 || status.active_alerts.length > 0 || status.unprocessed_doc_count > 0 || status.has_only_onboarding_docs)
  const readyBadges = [status?.top_extraction_set_name ? `Extraction: ${status.top_extraction_set_name}` : null, status?.top_workflow_name ? `Workflow: ${status.top_workflow_name}` : null, status?.has_ready_knowledge_base ? 'Knowledge base ready' : null].filter((value): value is string => !!value)
  return (
    <div className="chat-home">
      <div className="chat-home-heading">
        {brandIcon && <img src={brandIcon} alt="" />}
        <div><span className="home-eyebrow">Your {orgName} workspace</span><h2>{returningHeroTitle(status)}</h2>{status?.daily_guidance && <p>{status.daily_guidance}</p>}</div>
      </div>
      <FocusNowCard action={primaryAction} disabled={disabled} onRunDemo={onRunDemo} onAttachFiles={onAttachFiles} onFocusComposer={onFocusComposer} onChooseKnowledgeBase={onChooseKnowledgeBase} onSendMessage={onSendMessage} onOpenActivity={onOpenActivity} />
      <div className="home-primary-actions">
        {primaryAction.kind !== 'knowledge' && <ActionPillButton label="Choose a knowledge base" icon={BookOpen} disabled={disabled} onClick={onChooseKnowledgeBase} />}
        <ActionPillButton label="Build a workflow" icon={Workflow} disabled={disabled} onClick={() => onSendMessage('Help me turn a recurring task into a workflow.')} />
        {primaryAction.kind !== 'upload' && <UploadPillButton label="Upload a document" disabled={disabled} onAttachFiles={onAttachFiles} />}
        {!status?.has_documents && <ActionPillButton label="Run sample demo" icon={Zap} disabled={disabled} onClick={onRunDemo} />}
      </div>
      <div className="home-two-columns">
        {hasQueue && <ResumeQueue status={status} onSendMessage={onSendMessage} onOpenActivity={onOpenActivity} />}
        <SurfaceCard title="Suggested questions" subtitle="Start from your existing documents and tools.">
          {suggestions.map(suggestion => <PromptButton key={suggestion} label={suggestion} onClick={() => onSendMessage(suggestion)} />)}
        </SurfaceCard>
      </div>
      {readyBadges.length > 0 && <div className="home-ready-assets"><span>Ready in this workspace</span>{readyBadges.map(badge => <ReadyAssetBadge key={badge} label={badge} />)}</div>}
      {openTour && <button className="home-learning-link" type="button" onClick={openTour}>Take a quick tour</button>}
      {certCta && <button className="home-learning-link" type="button" disabled={disabled} onClick={() => onSendMessage(certCta.message)}><Award size={14} /> {certCta.label}</button>}
    </div>
  )
}
