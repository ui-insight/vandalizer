import { MessageSquare, FileSearch, Workflow, AlertTriangle, ArrowRight, CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import type { RecentActivityItem, ActiveAlertItem, MaturityStage } from '../../api/config'

// ---------------------------------------------------------------------------
// Activity row — a single recent activity item
// ---------------------------------------------------------------------------

const TYPE_ICONS: Record<string, typeof MessageSquare> = {
  conversation: MessageSquare,
  search_set_run: FileSearch,
  workflow_run: Workflow,
}

const STATUS_STYLES: Record<string, { color: string; Icon: typeof CheckCircle2 }> = {
  completed: { color: '#22c55e', Icon: CheckCircle2 },
  failed: { color: '#ef4444', Icon: XCircle },
  running: { color: 'var(--highlight-color, #eab308)', Icon: Loader2 },
}

function activityResumeMessage(item: RecentActivityItem): string {
  const t = item.title
  if (item.type === 'search_set_run') {
    if (item.status === 'failed') return `My "${t}" extraction failed — help me understand what went wrong`
    if (item.status === 'running') return `Check on my running "${t}" extraction`
    return `Show me the results from my "${t}" extraction`
  }
  if (item.type === 'workflow_run') {
    if (item.status === 'failed') return `My "${t}" workflow failed — help me debug it`
    if (item.status === 'running') return `Check on my running "${t}" workflow`
    return `Show me the results from my "${t}" workflow run`
  }
  // conversation
  return `Continue our conversation about "${t}"`
}

function ActivityRow({ item, onSendMessage }: { item: RecentActivityItem; onSendMessage: (msg: string) => void }) {
  const Icon = TYPE_ICONS[item.type] ?? MessageSquare
  const status = STATUS_STYLES[item.status] ?? STATUS_STYLES.completed
  const StatusIcon = status.Icon

  return (
    <button
      onClick={() => onSendMessage(activityResumeMessage(item))}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        width: '100%',
        padding: '8px 10px',
        borderRadius: 8,
        border: 'none',
        backgroundColor: 'transparent',
        cursor: 'pointer',
        fontFamily: 'inherit',
        textAlign: 'left',
        transition: 'background-color 0.12s',
      }}
      onMouseEnter={e => { e.currentTarget.style.backgroundColor = '#f3f4f6' }}
      onMouseLeave={e => { e.currentTarget.style.backgroundColor = 'transparent' }}
    >
      <Icon size={14} style={{ flexShrink: 0, color: '#9ca3af' }} />
      <span style={{
        flex: 1,
        fontSize: 13,
        color: '#374151',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}>
        {item.title}
      </span>
      <span style={{ fontSize: 11, color: '#9ca3af', flexShrink: 0 }}>
        {item.relative_time}
      </span>
      <StatusIcon
        size={12}
        style={{
          flexShrink: 0,
          color: status.color,
          ...(item.status === 'running' ? { animation: 'spin 1s linear infinite' } : {}),
        }}
      />
    </button>
  )
}

// ---------------------------------------------------------------------------
// Alert row — a quality alert
// ---------------------------------------------------------------------------

const SEVERITY_STYLES: Record<string, { bg: string; border: string; text: string }> = {
  critical: { bg: 'rgba(239,68,68,0.08)', border: '#fca5a5', text: '#dc2626' },
  warning: { bg: 'rgba(234,179,8,0.06)', border: '#fde68a', text: '#a16207' },
  info: { bg: 'rgba(59,130,246,0.06)', border: '#bfdbfe', text: '#2563eb' },
}

function AlertRow({ alert, onSendMessage }: { alert: ActiveAlertItem; onSendMessage: (msg: string) => void }) {
  const style = SEVERITY_STYLES[alert.severity] ?? SEVERITY_STYLES.info

  return (
    <button
      onClick={() => onSendMessage(`Check quality of ${alert.item_name}`)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        width: '100%',
        padding: '7px 10px',
        borderRadius: 8,
        border: `1px solid ${style.border}`,
        backgroundColor: style.bg,
        cursor: 'pointer',
        fontFamily: 'inherit',
        textAlign: 'left',
        transition: 'filter 0.12s',
      }}
      onMouseEnter={e => { e.currentTarget.style.filter = 'brightness(0.97)' }}
      onMouseLeave={e => { e.currentTarget.style.filter = 'none' }}
    >
      <AlertTriangle size={13} style={{ flexShrink: 0, color: style.text }} />
      <span style={{
        flex: 1,
        fontSize: 12,
        color: style.text,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}>
        {alert.message}
      </span>
      <ArrowRight size={12} style={{ flexShrink: 0, color: style.text, opacity: 0.5 }} />
    </button>
  )
}

// ---------------------------------------------------------------------------
// Next-step nudge — maturity-appropriate guidance
// ---------------------------------------------------------------------------

const STAGE_NUDGE: Record<string, (ctx: { unprocessedDocCount: number }) => { label: string; action: string } | null> = {
  newcomer: () => ({ label: 'Upload your first document to get started.', action: 'Help me upload and analyze my first document' }),
  explorer: ({ unprocessedDocCount }) =>
    unprocessedDocCount > 0
      ? { label: `You have ${unprocessedDocCount} document${unprocessedDocCount !== 1 ? 's' : ''} ready. Try running an extraction template on them.`, action: 'Run an extraction template on my documents' }
      : { label: 'Try running an extraction template on your documents.', action: 'Run an extraction template on my documents' },
  practitioner: () => ({ label: 'You\'ve been running extractions. Chain them into a workflow for repeatability.', action: 'Help me turn my extraction into a repeatable workflow' }),
  builder: () => ({ label: 'Automate your workflow with folder watching or API triggers.', action: 'Help me set up automation for my workflow' }),
  architect: () => null,
}

function NextStepNudge({ stage, unprocessedDocCount, onSendMessage }: { stage: MaturityStage; unprocessedDocCount: number; onSendMessage: (msg: string) => void }) {
  const fn = STAGE_NUDGE[stage]
  const nudge = fn?.({ unprocessedDocCount })
  if (!nudge) return null

  return (
    <button
      onClick={() => onSendMessage(nudge.action)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        width: '100%',
        padding: '8px 10px',
        borderRadius: 8,
        backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 5%, white)',
        border: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 15%, #e5e7eb)',
        cursor: 'pointer',
        fontFamily: 'inherit',
        textAlign: 'left',
        transition: 'all 0.12s',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 10%, white)'
        e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 30%, #e5e7eb)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 5%, white)'
        e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 15%, #e5e7eb)'
      }}
    >
      <ArrowRight size={13} style={{ flexShrink: 0, color: 'var(--highlight-color, #eab308)' }} />
      <span style={{ fontSize: 12, color: '#4b5563', lineHeight: 1.4 }}>
        {nudge.label}
      </span>
    </button>
  )
}

// ---------------------------------------------------------------------------
// WorkspaceBriefing — main exported component
// ---------------------------------------------------------------------------

interface WorkspaceBriefingProps {
  recentActivity: RecentActivityItem[]
  activeAlerts: ActiveAlertItem[]
  maturityStage: MaturityStage
  unprocessedDocCount: number
  dailyGuidance?: string | null
  sinceLastVisit?: string | null
  hasOnlyOnboardingDocs?: boolean
  onSendMessage: (message: string) => void
}

export function WorkspaceBriefing({
  recentActivity,
  activeAlerts,
  maturityStage,
  unprocessedDocCount,
  dailyGuidance,
  sinceLastVisit,
  hasOnlyOnboardingDocs,
  onSendMessage,
}: WorkspaceBriefingProps) {
  // Architect-level users with no alerts and no guidance: auto-hide
  if (maturityStage === 'architect' && activeAlerts.length === 0 && !dailyGuidance) return null

  // Nothing to show at all
  if (recentActivity.length === 0 && activeAlerts.length === 0 && maturityStage === 'newcomer' && !dailyGuidance) return null

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
      padding: '12px 14px',
      borderRadius: 'var(--ui-radius, 12px)',
      backgroundColor: '#fff',
      border: '1px solid #e5e7eb',
    }}>
      {/* Synthesized daily guidance — the lead recommendation */}
      {dailyGuidance && (
        <button
          onClick={() => onSendMessage(dailyGuidance)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            width: '100%',
            padding: '10px 12px',
            borderRadius: 8,
            border: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 25%, #e5e7eb)',
            backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 4%, white)',
            cursor: 'pointer',
            fontFamily: 'inherit',
            textAlign: 'left',
            transition: 'all 0.12s',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 8%, white)'
            e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 40%, #e5e7eb)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 4%, white)'
            e.currentTarget.style.borderColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 25%, #e5e7eb)'
          }}
        >
          <span style={{ fontSize: 13, color: '#374151', lineHeight: 1.4 }}>
            {dailyGuidance}
          </span>
          <ArrowRight size={14} style={{ flexShrink: 0, color: 'var(--highlight-color, #eab308)', opacity: 0.6 }} />
        </button>
      )}

      {/* Since last visit — delta summary */}
      {sinceLastVisit && (
        <div style={{
          fontSize: 11,
          color: '#9ca3af',
          paddingLeft: 10,
          lineHeight: 1.5,
        }}>
          {sinceLastVisit}
        </div>
      )}

      {/* Post-demo: targeted bridge to real work */}
      {hasOnlyOnboardingDocs && !dailyGuidance && (
        <button
          onClick={() => onSendMessage('Help me upload and analyze my first real document')}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            width: '100%',
            padding: '10px 12px',
            borderRadius: 8,
            border: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 25%, #e5e7eb)',
            backgroundColor: 'color-mix(in srgb, var(--highlight-color, #eab308) 4%, white)',
            cursor: 'pointer',
            fontFamily: 'inherit',
            textAlign: 'left',
            transition: 'all 0.12s',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 8%, white)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.backgroundColor = 'color-mix(in srgb, var(--highlight-color, #eab308) 4%, white)'
          }}
        >
          <span style={{ fontSize: 13, color: '#374151', lineHeight: 1.4 }}>
            You've seen the demo — now upload one of your own documents and I'll help you build a custom template.
          </span>
          <ArrowRight size={14} style={{ flexShrink: 0, color: 'var(--highlight-color, #eab308)', opacity: 0.6 }} />
        </button>
      )}

      {/* Recent activity */}
      {recentActivity.length > 0 && !hasOnlyOnboardingDocs && (
        <div>
          <div style={{
            fontSize: 11,
            fontWeight: 600,
            color: '#9ca3af',
            textTransform: 'uppercase' as const,
            letterSpacing: '0.05em',
            marginBottom: 4,
            paddingLeft: 10,
          }}>
            Recent activity
          </div>
          {recentActivity.map((item, i) => (
            <ActivityRow key={i} item={item} onSendMessage={onSendMessage} />
          ))}
        </div>
      )}

      {/* Quality alerts */}
      {activeAlerts.length > 0 && (
        <div>
          <div style={{
            fontSize: 11,
            fontWeight: 600,
            color: '#9ca3af',
            textTransform: 'uppercase' as const,
            letterSpacing: '0.05em',
            marginBottom: 4,
            paddingLeft: 10,
          }}>
            Needs attention
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {activeAlerts.map((alert, i) => (
              <AlertRow key={i} alert={alert} onSendMessage={onSendMessage} />
            ))}
          </div>
        </div>
      )}

      {/* Maturity-appropriate nudge */}
      {!hasOnlyOnboardingDocs && (
        <NextStepNudge stage={maturityStage} unprocessedDocCount={unprocessedDocCount} onSendMessage={onSendMessage} />
      )}
    </div>
  )
}
