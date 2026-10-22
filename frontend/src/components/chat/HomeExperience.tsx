import { useRef, useState, type ChangeEvent, type ReactNode } from 'react'
import {
  Award,
  BookOpen,
  CheckCircle2,
  FileSearch,
  FileUp,
  MessageSquare,
  Workflow,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import type { ActiveAlertItem, OnboardingStatus, RecentActivityItem } from '../../api/config'
import { useCertificationPanelOptional } from '../../contexts/CertificationPanelContext'
import { certificationChatEntry } from '../../lib/certificationChat'
import { useWorkspaceTour } from '../../contexts/WorkspaceTourContext'
import { ConceptStrip } from './ConceptTip'
import { useUploadPolicy } from '../../hooks/useUploadPolicy'
import { HomeQualityAlerts } from './HomeQualityAlerts'
import { HomeTaskShortcuts, type TaskDocument } from './HomeTaskShortcuts'
import { CertificationRefreshNotice } from '../certification/CertificationRefreshNotice'
import './home-work.css'

/**
 * "Start certification" / "Continue certification" home CTA. The course runs
 * right in chat (certification tools + cards), so the button just sends the
 * kickoff message. Null when the user is already certified. Works without the
 * CertificationPanelProvider (unit tests) — it then falls back to "start".
 */
function useCertificationCta(): { label: string; message: string } | null {
  const cert = useCertificationPanelOptional()
  const entry = certificationChatEntry(cert?.progress, cert?.course)
  return entry.certified ? null : entry
}

function CertificationHomeActions({ disabled, onSendMessage }: { disabled?: boolean; onSendMessage: (message: string) => void }) {
  const certCta = useCertificationCta()
  const certification = useCertificationPanelOptional()
  if (!certCta && !certification) return null
  return <div className="home-learning-area"><div className="flex flex-wrap items-center gap-x-4 gap-y-2">
    {certCta && <button className="home-learning-link" type="button" disabled={disabled} onClick={() => onSendMessage(certCta.message)}><Award size={14} /> {certCta.label}</button>}
    {certification && <button className="home-learning-link" type="button" onClick={certification.openPanel}><BookOpen size={14} /> {certification.progress?.certified ? 'Review completed course' : 'Open course without chat'}</button>}
  </div><CertificationRefreshNotice compact /></div>
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
        className="home-upload-action"
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

// Per-browser Home preferences. Storage can be unavailable (private mode,
// blocked site data); Home then simply shows its defaults.
const HIDE_TASKS_KEY = 'vandalizer:home:hide-task-starters'
function readFlag(key: string): boolean {
  try { return localStorage.getItem(key) === '1' } catch { return false }
}
function writeFlag(key: string, on: boolean) {
  try { if (on) localStorage.setItem(key, '1'); else localStorage.removeItem(key) } catch { /* keep the in-page choice */ }
}

function activityLabel(item: RecentActivityItem): string {
  if (item.pending_review) return 'Awaiting review'
  if (item.type === 'conversation') return 'Conversation'
  if (item.status === 'running') return 'Processing'
  if (item.status === 'queued') return 'Queued'
  if (item.status === 'failed') return 'Run failed'
  if (item.status === 'canceled') return 'Canceled · no results'
  if (item.status === 'completed') return 'Run completed · results need your review'
  return 'Status unavailable'
}

interface SharedHomeProps {
  embedded?: boolean
  orgName: string
  brandIcon: string | null
  disabled?: boolean
  onRunDemo: () => void
  onAttachFiles: (files: File[]) => void
  onFocusComposer: () => void
  onChooseKnowledgeBase: () => void
  onSendMessage: (message: string) => void
}

export function FirstSessionHome({ embedded, orgName, brandIcon, disabled, onRunDemo, onAttachFiles, onFocusComposer, onChooseKnowledgeBase, onSendMessage }: SharedHomeProps) {
  const openTour = useWorkspaceTour()
  return (
    <div className="chat-home first-session-home">
      {!embedded && <div className="chat-home-heading">
        {brandIcon && <img src={brandIcon} alt="" />}
        <div><span className="home-eyebrow">Welcome to {orgName}</span><h2>What would you like to get done?</h2><p>Ask a question, upload a source, or try a sample.</p></div>
      </div>}
      <div className="home-primary-actions">
        {!embedded && <ActionPillButton label="Start a conversation" icon={MessageSquare} disabled={disabled} onClick={onFocusComposer} />}
        <UploadPillButton label="Upload a document" disabled={disabled} onAttachFiles={onAttachFiles} />
        {embedded && <button className="home-text-action" type="button" disabled={disabled} onClick={onChooseKnowledgeBase}>Choose a knowledge base</button>}
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
      <details className="home-other-actions" open={embedded ? undefined : true}>
        <summary>Learn the basics</summary>
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
      </details>
      <CertificationHomeActions disabled={disabled} onSendMessage={onSendMessage} />
    </div>
  )
}

export function ReturningHome({ embedded, orgName, brandIcon, disabled, onRunDemo, onAttachFiles, onFocusComposer, onChooseKnowledgeBase, onSendMessage, onOpenActivity, onOpenTool, onSelectDocument, onChooseDocuments, onNoticeChanged, onPrepareTask, onOpenProjects, workspaceLabel, status, workQueue }: SharedHomeProps & {
  onOpenActivity: (activityId: string) => void
  onOpenTool?: (alert: ActiveAlertItem) => void
  onSelectDocument?: (document: { uuid: string; title: string }) => void
  onChooseDocuments?: () => void
  status: OnboardingStatus | null
  suggestionPills: string[] // Older callers may still provide these; unscoped run prompts are not rendered.
  onNoticeChanged?: () => void
  workQueue?: ReactNode
  workspaceLabel?: string
  onOpenProjects?: () => void
  onPrepareTask?: (prompt: string, document?: TaskDocument) => void
}) {
  const openTour = useWorkspaceTour()
  const activities = [...new Map((status?.recent_activity || []).filter(item => item.type !== 'quality_alert').map(item => [item.id, item])).values()]
  const unfinished = activities.filter(item => item.type !== 'conversation' && (item.pending_review || ['running', 'queued', 'failed'].includes(item.status)))
  const recent = activities.filter(item => !unfinished.includes(item))
  const documents = [...new Map((status?.recent_documents || []).map(doc => [doc.uuid, doc])).values()]
  // Once there is real work on the page, the composer is the one dominant
  // action; a "Start a conversation" button beside it only repeats it.
  const hasWork = activities.length > 0 || documents.length > 0
  const [tasksHidden, setTasksHidden] = useState(() => readFlag(HIDE_TASKS_KEY))
  const toggleTasks = (hidden: boolean) => { writeFlag(HIDE_TASKS_KEY, hidden); setTasksHidden(hidden) }
  const activityRow = (item: RecentActivityItem) => {
    const Icon = item.type === 'conversation' ? MessageSquare : item.type === 'workflow_run' ? Workflow : FileSearch
    const label = item.pending_review ? 'Review submission' : item.type === 'conversation' ? 'Continue chat' : item.status === 'failed' ? 'Inspect failed run' : item.status === 'canceled' ? 'View canceled run' : ['running', 'queued'].includes(item.status) ? 'View progress' : item.status === 'completed' ? 'Open results' : 'View details'
    return <li key={item.id}>
      <Icon size={18} aria-hidden="true" />
      <div><strong>{item.title}</strong><p>{activityLabel(item)}{item.relative_time ? ` · ${item.relative_time}` : ''}</p></div>
      <button type="button" className="home-text-action" onClick={() => onOpenActivity(item.id)} aria-label={`${label}: ${item.title}`}>{label}</button>
    </li>
  }
  return (
    <div className="chat-home returning-home">
      {!embedded && <div className="chat-home-heading">
        {brandIcon && <img src={brandIcon} alt="" />}
        <div><span className="home-eyebrow">{orgName}{workspaceLabel ? ` · ${workspaceLabel}` : ''}</span><h2>Your workspace</h2><p>Pick up your work, or ask the assistant anything.</p></div>
      </div>}
      {workQueue}
      {unfinished.length > 0 && <section className="home-activity home-attention" aria-label="Work in progress">
        <h3>Work in progress</h3><ul>{unfinished.map(activityRow)}</ul>
      </section>}
      <div className="home-start-actions">
        <div className="home-primary-actions">
          {!embedded && !hasWork && <ActionPillButton label="Start a conversation" icon={MessageSquare} disabled={disabled} onClick={onFocusComposer} />}
          <UploadPillButton label="Upload a document" disabled={disabled} onAttachFiles={onAttachFiles} />
          {onOpenProjects && <button type="button" className="home-text-action" onClick={onOpenProjects}>Open projects</button>}
        </div>
        {onPrepareTask && !tasksHidden && <HomeTaskShortcuts documents={documents} disabled={disabled} onPrepare={onPrepareTask} onChooseDocuments={onChooseDocuments} onHide={() => toggleTasks(true)} />}
      </div>
      {recent.length > 0 && <section className="home-activity" aria-label="Recent work">
        <h3>Recent work</h3><ul>{recent.slice(0, 3).map(activityRow)}</ul>
        {recent.length > 3 && <details className="home-other-actions"><summary>More recent work ({recent.length - 3})</summary><ul>{recent.slice(3).map(activityRow)}</ul></details>}
      </section>}
      {!status && <p className="home-meta" role="status">Workspace activity is unavailable. You can still start a conversation or upload a document.</p>}
      <HomeQualityAlerts alerts={status?.active_alerts || []} recentActivity={activities} onOpenActivity={onOpenActivity} onOpenTool={onOpenTool} onSendMessage={onSendMessage} onNoticeChanged={onNoticeChanged} disabled={disabled} />
      <div className="home-utilities">
        {(documents.length > 0 || status?.has_ready_knowledge_base || status?.has_documents) && <details className="home-sources">
          <summary>Choose from your sources</summary>
          {documents.length > 0 && <>
            <p className="home-meta">Select a document to attach to your next question.</p>
            <ul>{documents.map(doc => <li key={doc.uuid}><FileSearch size={16} aria-hidden="true" /><span>{doc.title}</span><button className="home-text-action" type="button" disabled={disabled || !onSelectDocument} aria-label={`Select document: ${doc.title}`} onClick={() => onSelectDocument?.(doc)}>Select document</button></li>)}</ul>
            {onChooseDocuments && <button type="button" className="home-text-action" onClick={onChooseDocuments}>Choose other documents</button>}
          </>}
          {status?.has_ready_knowledge_base && <div className="home-knowledge-action"><button type="button" className="home-text-action" disabled={disabled} onClick={onChooseKnowledgeBase}>Choose a knowledge base</button><p className="home-meta">Select the sources for a question across documents.</p></div>}
          {status?.has_documents && documents.length === 0 && onChooseDocuments && <button type="button" className="home-text-action" onClick={onChooseDocuments}>Choose documents to work with</button>}
        </details>}
        <details className="home-other-actions"><summary>More ways to work</summary>
          {onPrepareTask && tasksHidden && <button type="button" className="home-text-action" onClick={() => toggleTasks(false)}>Show task starters</button>}
          {!status?.has_ready_knowledge_base && <ActionPillButton label="Choose a knowledge base" icon={BookOpen} disabled={disabled} onClick={onChooseKnowledgeBase} />}
          <ActionPillButton label="Build a workflow" icon={Workflow} disabled={disabled} onClick={() => onSendMessage('Help me turn a recurring task into a workflow.')} />
          {!status?.has_documents && <ActionPillButton label="Run sample demo" icon={Zap} disabled={disabled} onClick={onRunDemo} />}
          {openTour && <button className="home-learning-link" type="button" onClick={openTour}>Take a quick tour</button>}
        </details>
        <CertificationHomeActions disabled={disabled} onSendMessage={onSendMessage} />
      </div>
    </div>
  )
}
