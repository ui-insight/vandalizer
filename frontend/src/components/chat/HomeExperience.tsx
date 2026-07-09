import { useRef, type ChangeEvent, type ReactNode } from 'react'
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock3,
  FileSearch,
  FileUp,
  MessageSquare,
  Shield,
  Sparkles,
  Workflow,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import type { OnboardingStatus, RecentActivityItem } from '../../api/config'
import { ConceptStrip } from './ConceptTip'
import { OnboardingStepper } from './WelcomeExperience'
import { WorkspaceBriefing } from './WorkspaceBriefing'

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

const FIRST_RUN_TRUST_SIGNALS = [
  'Every answer links back to source passages you can review.',
  'Validated templates carry measured quality signals, not vague confidence language.',
  'Documents, workflows, and knowledge stay scoped to your workspace.',
]

const DEFAULT_RETURNING_PROMPTS = [
  'Summarize my latest document in 5 bullets.',
  'Extract deadlines, owners, and deliverables from my latest documents.',
  'Find compliance gaps or missing fields in the documents I should review today.',
  'Compare two versions and tell me what changed.',
]

interface ActionCardProps {
  title: string
  description: string
  icon: LucideIcon
  accent?: boolean
  disabled?: boolean
  onClick: () => void
}

function ActionCard({ title, description, icon: Icon, accent, disabled, onClick }: ActionCardProps) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        gap: 10,
        width: '100%',
        minHeight: 118,
        padding: '16px 18px',
        borderRadius: 'var(--ui-radius, 12px)',
        border: accent
          ? '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 32%, #ffffff)'
          : '1px solid #e5e7eb',
        background: accent
          ? 'linear-gradient(180deg, color-mix(in srgb, var(--highlight-color, #eab308) 18%, white), white)'
          : '#ffffff',
        color: '#111827',
        cursor: disabled ? 'default' : 'pointer',
        fontFamily: 'inherit',
        textAlign: 'left',
        boxShadow: accent ? '0 16px 30px rgba(0,0,0,0.06)' : '0 10px 24px rgba(0,0,0,0.04)',
        opacity: disabled ? 0.55 : 1,
        transition: 'transform 0.16s ease, box-shadow 0.16s ease, filter 0.16s ease',
      }}
      onMouseEnter={e => {
        if (disabled) return
        e.currentTarget.style.transform = 'translateY(-1px)'
        e.currentTarget.style.boxShadow = accent ? '0 20px 36px rgba(0,0,0,0.08)' : '0 14px 28px rgba(0,0,0,0.07)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.transform = 'translateY(0)'
        e.currentTarget.style.boxShadow = accent ? '0 16px 30px rgba(0,0,0,0.06)' : '0 10px 24px rgba(0,0,0,0.04)'
      }}
    >
      <div
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 34,
          height: 34,
          borderRadius: 10,
          background: accent
            ? 'var(--highlight-color, #eab308)'
            : 'color-mix(in srgb, var(--highlight-color, #eab308) 12%, white)',
          color: accent ? '#111827' : 'var(--highlight-on-light, #806600)',
        }}
      >
        <Icon size={16} />
      </div>
      <div>
        <div style={{ fontSize: 15, fontWeight: 700, lineHeight: 1.25 }}>{title}</div>
        <div style={{ marginTop: 6, fontSize: 13, lineHeight: 1.5, color: '#4b5563' }}>
          {description}
        </div>
      </div>
    </button>
  )
}

interface UploadActionCardProps {
  title: string
  description: string
  disabled?: boolean
  onAttachFiles: (files: File[]) => void
}

function UploadActionCard({ title, description, disabled, onAttachFiles }: UploadActionCardProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    if (files.length > 0) onAttachFiles(files)
    event.target.value = ''
  }

  return (
    <>
      <ActionCard
        title={title}
        description={description}
        icon={FileUp}
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
      />
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        aria-label={title}
        onChange={handleChange}
      />
    </>
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

function MetricChip({
  icon: Icon,
  label,
  value,
  tone = 'neutral',
}: {
  icon: LucideIcon
  label: string
  value: string
  tone?: 'neutral' | 'warning'
}) {
  const palette = tone === 'warning'
    ? {
        background: 'rgba(234,179,8,0.10)',
        border: 'rgba(234,179,8,0.26)',
        text: '#854d0e',
      }
    : {
        background: 'rgba(255,255,255,0.14)',
        border: 'rgba(255,255,255,0.22)',
        text: '#ffffff',
      }

  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        padding: '8px 10px',
        borderRadius: 999,
        border: `1px solid ${palette.border}`,
        background: palette.background,
        color: palette.text,
      }}
    >
      <Icon size={14} />
      <span style={{ fontSize: 12, fontWeight: 600 }}>{label}</span>
      <span style={{ fontSize: 12, opacity: 0.88 }}>{value}</span>
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

function returningHeroTitle(status: OnboardingStatus | null): string {
  if (status?.has_only_onboarding_docs) return 'Turn the demo into real work'
  if ((status?.active_alerts.length ?? 0) > 0) return 'A few items need attention'
  if ((status?.recent_activity.length ?? 0) > 0) return 'Pick up where you left off'
  if (status?.has_documents) return 'Your workspace is ready'
  return 'Start with a document or question'
}

function returningHeroSubtitle(status: OnboardingStatus | null): string {
  if (status?.daily_guidance) return status.daily_guidance
  if (status?.since_last_visit) return status.since_last_visit
  if (status?.has_only_onboarding_docs) {
    return 'You have seen the sample flow. Upload one of your own documents to personalize the results, templates, and follow-up work.'
  }
  if (status?.has_documents) {
    return 'Resume prior work, review items that changed, or run the next extraction without starting from scratch.'
  }
  return 'Upload a real document, ask a question, or run the sample demo if you want a quick refresher.'
}

function starterSuggestions(status: OnboardingStatus | null, suggestionPills: string[]): string[] {
  if (suggestionPills.length > 0) return suggestionPills.slice(0, 4)
  if (status?.suggestion_pills?.length) return status.suggestion_pills.slice(0, 4)
  return DEFAULT_RETURNING_PROMPTS
}

function WorkspaceSnapshot({
  status,
  onSendMessage,
}: {
  status: OnboardingStatus | null
  onSendMessage: (message: string) => void
}) {
  if (!status) {
    return (
      <SurfaceCard
        title="Recent work and alerts"
        subtitle="Once you upload documents or run workflows, your active work will appear here."
      >
        <div style={{ fontSize: 13, color: '#6b7280', lineHeight: 1.5 }}>
          No workspace activity yet.
        </div>
      </SurfaceCard>
    )
  }

  const hasBriefing =
    status.recent_activity.length > 0 ||
    status.active_alerts.length > 0 ||
    !!status.daily_guidance ||
    !!status.has_only_onboarding_docs ||
    status.unprocessed_doc_count > 0 ||
    status.maturity_stage !== 'newcomer'

  if (!hasBriefing) {
    return (
      <SurfaceCard
        title="Recent work and alerts"
        subtitle="Your home screen will start surfacing work queues, recent runs, and follow-ups as soon as you begin using them."
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <PromptButton
            label="Help me upload and analyze my first document."
            onClick={() => onSendMessage('Help me upload and analyze my first document.')}
          />
          <PromptButton
            label="Show me how source-linked answers work."
            onClick={() => onSendMessage('Show me how source-linked answers work in Vandalizer.')}
          />
        </div>
      </SurfaceCard>
    )
  }

  return (
    <div>
      <div style={{ fontSize: 16, fontWeight: 700, color: '#111827', marginBottom: 6 }}>
        Recent work and alerts
      </div>
      <div style={{ fontSize: 13, lineHeight: 1.5, color: '#6b7280', marginBottom: 14 }}>
        Resume unfinished work, review alerts, and see what changed since your last visit.
      </div>
      <WorkspaceBriefing
        recentActivity={status.recent_activity}
        activeAlerts={status.active_alerts}
        maturityStage={status.maturity_stage}
        unprocessedDocCount={status.unprocessed_doc_count}
        dailyGuidance={status.daily_guidance}
        sinceLastVisit={status.since_last_visit}
        hasOnlyOnboardingDocs={status.has_only_onboarding_docs}
        onSendMessage={onSendMessage}
      />
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

export function FirstSessionHome({
  orgName,
  brandIcon,
  disabled,
  onRunDemo,
  onAttachFiles,
  onFocusComposer,
  onSendMessage,
}: SharedHomeProps) {
  return (
    <div style={{ maxWidth: 760, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div
        className="relative overflow-hidden text-white"
        style={{
          padding: '24px 24px 22px',
          borderRadius: 'var(--ui-radius, 12px)',
          background: 'linear-gradient(135deg, #7c2d12, color-mix(in srgb, var(--highlight-color, #eab308) 74%, #ffffff 26%))',
          boxShadow: '0 22px 40px rgba(124,45,18,0.16)',
        }}
      >
        <div
          style={{
            position: 'absolute',
            top: '-40%',
            right: '-15%',
            width: '58%',
            height: '180%',
            background: 'linear-gradient(180deg, rgba(255,255,255,0.18), rgba(255,255,255,0))',
            transform: 'rotate(28deg)',
          }}
        />
        <div style={{ position: 'relative', zIndex: 1 }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              padding: '6px 10px',
              borderRadius: 999,
              background: 'rgba(255,255,255,0.14)',
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '0.04em',
              textTransform: 'uppercase',
            }}
          >
            Start here
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, marginTop: 14 }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 44,
                height: 44,
                borderRadius: 14,
                background: 'rgba(255,255,255,0.14)',
                flexShrink: 0,
              }}
            >
              {brandIcon ? (
                <img
                  src={brandIcon}
                  alt={orgName}
                  style={{ width: 24, height: 24, objectFit: 'contain' }}
                />
              ) : (
                <Sparkles size={20} />
              )}
            </div>
            <div>
              <div style={{ fontSize: 28, lineHeight: 1.12, fontWeight: 800, maxWidth: 620 }}>
                Turn complex documents into answers you can verify.
              </div>
              <div style={{ marginTop: 10, fontSize: 15, lineHeight: 1.6, maxWidth: 620, opacity: 0.92 }}>
                Run the sample demo or upload one of your own files. {orgName} extracts deadlines,
                budget details, and compliance risks with source-linked evidence you can audit.
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 16 }}>
            <MetricChip icon={Shield} label="Trust" value="Source-linked answers" />
            <MetricChip icon={CheckCircle2} label="Proof" value="Measured quality signals" />
            <MetricChip icon={BookOpen} label="Fit" value="Research administration" />
          </div>
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 12,
        }}
      >
        <ActionCard
          title="Run sample demo"
          description="See the full flow on a real grant example before you touch your own files."
          icon={Zap}
          accent
          disabled={disabled}
          onClick={onRunDemo}
        />
        <UploadActionCard
          title="Upload a document"
          description="Add a PDF, DOCX, spreadsheet, or policy file and start with your own work."
          disabled={disabled}
          onAttachFiles={onAttachFiles}
        />
        <ActionCard
          title="Ask a question"
          description="Jump straight to the composer if you already know what you want to find."
          icon={MessageSquare}
          disabled={disabled}
          onClick={onFocusComposer}
        />
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 12,
        }}
      >
        <SurfaceCard
          title="Start with a real task"
          subtitle="These prompts get you to a useful result fast instead of teaching product vocabulary first."
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {FIRST_RUN_PROMPTS.map((prompt) => (
              <PromptButton
                key={prompt.label}
                label={prompt.label}
                onClick={() => onSendMessage(prompt.prompt)}
              />
            ))}
          </div>
        </SurfaceCard>

        <SurfaceCard
          title="What makes the output trustworthy"
          subtitle="The first result should show you why the answer is believable, not just what it says."
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {FIRST_RUN_TRUST_SIGNALS.map((item) => (
              <div key={item} style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <CheckCircle2
                  size={16}
                  style={{ marginTop: 2, flexShrink: 0, color: 'var(--highlight-on-light, #806600)' }}
                />
                <div style={{ fontSize: 13, lineHeight: 1.55, color: '#374151' }}>{item}</div>
              </div>
            ))}
          </div>

          <div
            style={{
              marginTop: 16,
              padding: 14,
              borderRadius: 12,
              background: '#f8fafc',
              border: '1px solid #e5e7eb',
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Example proof panel
            </div>
            <div style={{ marginTop: 10, display: 'flex', flexDirection: 'column', gap: 10 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <div>
                  <div style={{ fontSize: 12, color: '#6b7280' }}>Deadline</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: '#111827' }}>Oct 5, 2026</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: 12, color: '#6b7280' }}>Source</div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>Page 4, Timeline</div>
                </div>
              </div>
              <div style={{ padding: 10, borderRadius: 10, backgroundColor: '#ffffff', border: '1px solid #e5e7eb' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                  <FileSearch size={14} style={{ color: 'var(--highlight-on-light, #806600)' }} />
                  <span style={{ fontSize: 12, fontWeight: 700, color: '#374151' }}>Linked evidence</span>
                </div>
                <div style={{ fontSize: 13, lineHeight: 1.55, color: '#4b5563' }}>
                  "Letters of commitment are due no later than October 5, 2026 and must name the responsible site lead."
                </div>
              </div>
            </div>
          </div>
        </SurfaceCard>
      </div>

      <div style={{ marginTop: 2 }}>
        <ConceptStrip />
      </div>
    </div>
  )
}

export function ReturningHome({
  orgName,
  brandIcon,
  disabled,
  onRunDemo,
  onAttachFiles,
  onFocusComposer,
  onSendMessage,
  status,
  suggestionPills,
}: SharedHomeProps & {
  status: OnboardingStatus | null
  suggestionPills: string[]
}) {
  const recent = status?.recent_activity[0] ?? null
  const alerts = status?.active_alerts.length ?? 0
  const suggestions = starterSuggestions(status, suggestionPills)
  const primaryAction = status?.has_only_onboarding_docs
    ? {
        title: 'Upload a real document',
        description: 'Move from the sample experience into your own live workflow.',
        kind: 'upload' as const,
      }
    : recent
      ? {
          title: 'Resume recent work',
          description: recent.title,
          kind: 'resume' as const,
        }
      : alerts > 0
        ? {
            title: 'Review active alerts',
            description: `${alerts} quality item${alerts === 1 ? '' : 's'} need attention.`,
            kind: 'alert' as const,
          }
        : {
            title: status?.has_documents ? 'Ask about current work' : 'Run sample demo',
            description: status?.has_documents
              ? 'Start from a question, summary, or extraction request.'
              : `See ${orgName} work on a sample document.`,
            kind: status?.has_documents ? 'composer' as const : 'demo' as const,
          }

  const showBasicsStepper = !!status && ['newcomer', 'explorer'].includes(status.maturity_stage)
  const showGlossary = !!status && !status.has_documents && ['newcomer', 'explorer'].includes(status.maturity_stage)

  return (
    <div style={{ maxWidth: 760, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div
        className="relative overflow-hidden text-white"
        style={{
          padding: '22px 24px',
          borderRadius: 'var(--ui-radius, 12px)',
          background: 'linear-gradient(135deg, #1f2937, color-mix(in srgb, var(--highlight-color, #eab308) 58%, #ffffff 18%))',
          boxShadow: '0 22px 40px rgba(17,24,39,0.14)',
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: 'radial-gradient(circle at top right, rgba(255,255,255,0.16), transparent 45%)',
          }}
        />
        <div style={{ position: 'relative', zIndex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 42,
                height: 42,
                borderRadius: 14,
                background: 'rgba(255,255,255,0.14)',
                flexShrink: 0,
              }}
            >
              {brandIcon ? (
                <img
                  src={brandIcon}
                  alt={orgName}
                  style={{ width: 22, height: 22, objectFit: 'contain' }}
                />
              ) : (
                <Clock3 size={18} />
              )}
            </div>
            <div>
              <div style={{ fontSize: 28, lineHeight: 1.12, fontWeight: 800 }}>
                {returningHeroTitle(status)}
              </div>
              <div style={{ marginTop: 10, fontSize: 15, lineHeight: 1.6, maxWidth: 620, opacity: 0.92 }}>
                {returningHeroSubtitle(status)}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 16 }}>
            <MetricChip
              icon={Clock3}
              label="Recent work"
              value={`${status?.recent_activity.length ?? 0} item${(status?.recent_activity.length ?? 0) === 1 ? '' : 's'}`}
            />
            <MetricChip
              icon={AlertTriangle}
              label="Needs review"
              value={`${alerts} alert${alerts === 1 ? '' : 's'}`}
              tone={alerts > 0 ? 'warning' : 'neutral'}
            />
            <MetricChip
              icon={FileSearch}
              label="Docs to process"
              value={`${status?.unprocessed_doc_count ?? 0}`}
            />
            <MetricChip
              icon={Workflow}
              label="Stage"
              value={status?.maturity_stage ?? 'newcomer'}
            />
          </div>
        </div>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 12,
        }}
      >
        {primaryAction.kind === 'upload' ? (
          <UploadActionCard
            title={primaryAction.title}
            description={primaryAction.description}
            disabled={disabled}
            onAttachFiles={onAttachFiles}
          />
        ) : (
          <ActionCard
            title={primaryAction.title}
            description={primaryAction.description}
            icon={primaryAction.kind === 'resume' ? Clock3 : primaryAction.kind === 'alert' ? AlertTriangle : Zap}
            accent
            disabled={disabled}
            onClick={() => {
              if (primaryAction.kind === 'resume' && recent) {
                onSendMessage(activityResumeMessage(recent))
                return
              }
              if (primaryAction.kind === 'alert' && status?.active_alerts[0]) {
                onSendMessage(`Check quality of ${status.active_alerts[0].item_name}`)
                return
              }
              if (primaryAction.kind === 'composer') {
                onFocusComposer()
                return
              }
              onRunDemo()
            }}
          />
        )}

        <UploadActionCard
          title={status?.has_documents ? 'Upload another document' : 'Upload a document'}
          description="Keep new work flowing into the assistant instead of starting from an empty chat."
          disabled={disabled}
          onAttachFiles={onAttachFiles}
        />

        <ActionCard
          title="Ask a question"
          description="Jump to the composer to summarize, compare, troubleshoot, or plan next steps."
          icon={MessageSquare}
          disabled={disabled}
          onClick={onFocusComposer}
        />
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 12,
          alignItems: 'start',
        }}
      >
        <WorkspaceSnapshot status={status} onSendMessage={onSendMessage} />

        <SurfaceCard
          title="Suggested next actions"
          subtitle="These are task-oriented prompts designed to get you back into useful work quickly."
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {suggestions.map((suggestion) => (
              <PromptButton
                key={suggestion}
                label={suggestion}
                onClick={() => onSendMessage(suggestion)}
              />
            ))}
          </div>

          <div
            style={{
              marginTop: 16,
              padding: 12,
              borderRadius: 12,
              background: 'color-mix(in srgb, var(--highlight-color, #eab308) 7%, white)',
              border: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 20%, #e5e7eb)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Shield size={14} style={{ color: 'var(--highlight-on-light, #806600)' }} />
              <span style={{ fontSize: 12, fontWeight: 700, color: '#374151', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                Trust stays visible
              </span>
            </div>
            <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.55, color: '#4b5563' }}>
              Source-linked answers, validated extraction quality, and reusable workflows should be one click away from this screen.
            </div>
          </div>
        </SurfaceCard>
      </div>

      {showBasicsStepper && status && (
        <OnboardingStepper
          status={status}
          hasChatAboutDocs={status.has_chatted_with_docs}
        />
      )}

      {showGlossary && <ConceptStrip />}
    </div>
  )
}
