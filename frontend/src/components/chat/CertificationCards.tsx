/**
 * Rich in-chat cards for the certification tools.
 *
 * The certification program renders as structured cards inside the chat
 * stream — the LLM narrates around them, but the course content, checks, and
 * progress come verbatim from the deterministic backend (the same
 * certification_service the Certification panel uses). Buttons here send
 * chat messages (so the agent stays in the loop) or open the split view.
 */
import { useEffect, useRef } from 'react'
import { Award, Check, Circle, CircleCheck, Columns2, Sparkles, Star, X } from 'lucide-react'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useCertificationPanelOptional } from '../../contexts/CertificationPanelContext'

const ACCENT = 'var(--highlight-color, #eab308)'

interface ModuleRow {
  module_id: string
  title: string
  xp: number
  completed: boolean
  stars: number
}

interface CheckRow {
  name: string
  passed: boolean
  detail: string
}

function Stars({ count }: { count: number }) {
  if (count <= 0) return null
  return (
    <span style={{ display: 'inline-flex', gap: 1, verticalAlign: 'middle' }}>
      {Array.from({ length: count }, (_, i) => (
        <Star key={i} size={10} fill={ACCENT} style={{ color: ACCENT }} />
      ))}
    </span>
  )
}

function CardShell({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ marginTop: 6, marginLeft: 20 }}>
      <div
        style={{
          border: '1px solid color-mix(in srgb, var(--highlight-color, #eab308) 30%, #e5e7eb)',
          background: 'color-mix(in srgb, var(--highlight-color, #eab308) 5%, white)',
          borderRadius: 10,
          padding: '12px 14px',
          fontSize: 12,
          color: '#374151',
        }}
      >
        {children}
      </div>
    </div>
  )
}

function CardButton({ label, icon, onClick, subtle }: {
  label: string
  icon?: React.ReactNode
  onClick: () => void
  subtle?: boolean
}) {
  return (
    <button
      onClick={onClick}
      className={subtle ? undefined : 'chat-action-btn'}
      style={subtle ? {
        display: 'inline-flex', alignItems: 'center', gap: 5,
        padding: '5px 12px', fontSize: 12, fontWeight: 500, fontFamily: 'inherit',
        borderRadius: 8, border: '1px solid #d1d5db',
        background: '#fff', color: '#374151', cursor: 'pointer',
      } : {
        display: 'inline-flex', alignItems: 'center', gap: 5,
        fontSize: 12, padding: '6px 14px',
      }}
    >
      {icon}
      {label}
    </button>
  )
}

/**
 * Refresh the shared certification context (panel, rail badge) after a
 * chat-driven certification write lands — chat and panel stay one program.
 * Only fires when the result arrives live in this session, not on history
 * replay of old conversations.
 */
export function useCertificationSync(toolName: string, hasResult: boolean) {
  const cert = useCertificationPanelOptional()
  const refreshRef = useRef(cert?.refresh)
  refreshRef.current = cert?.refresh
  const hadResultOnMount = useRef(hasResult)
  useEffect(() => {
    if (!hasResult || hadResultOnMount.current) return
    if (!CERT_SYNC_TOOLS.has(toolName)) return
    refreshRef.current?.().catch(() => {})
  }, [hasResult, toolName])
}

const CERT_SYNC_TOOLS = new Set([
  'provision_certification_lab',
  'complete_certification_module',
  'submit_certification_assessment',
])

// ---------------------------------------------------------------------------
// Progress card — journey overview from get_certification_progress
// ---------------------------------------------------------------------------

export function CertProgressCard({ content }: { content: Record<string, unknown> }) {
  const { sendChatMessage } = useWorkspace()
  const modules = (content.modules as ModuleRow[]) || []
  const completed = Number(content.modules_completed ?? 0)
  const total = Number(content.modules_total ?? modules.length)
  const level = String(content.level ?? '')
  const xp = Number(content.total_xp ?? 0)
  const certified = Boolean(content.certified)
  const nextId = content.next_module_id as string | null
  const nextModule = modules.find((m) => m.module_id === nextId)
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0

  return (
    <CardShell>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <Award size={15} style={{ color: ACCENT, flexShrink: 0 }} />
        <span style={{ fontWeight: 700, fontSize: 13 }}>Vandal Workflow Architect</span>
        <span style={{ flex: 1 }} />
        <span style={{ color: '#6b7280', textTransform: 'capitalize' }}>
          {level} · {xp.toLocaleString()} XP
        </span>
      </div>

      <div style={{ height: 5, borderRadius: 4, background: '#e5e7eb', overflow: 'hidden', marginBottom: 4 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: ACCENT, transition: 'width 0.4s ease' }} />
      </div>
      <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 10 }}>
        {completed}/{total} modules complete
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        {modules.map((m) => (
          <div key={m.module_id} style={{ display: 'flex', alignItems: 'center', gap: 6, lineHeight: 1.5 }}>
            {m.completed
              ? <CircleCheck size={13} style={{ color: '#16a34a', flexShrink: 0 }} />
              : <Circle size={13} style={{ color: m.module_id === nextId ? ACCENT : '#d1d5db', flexShrink: 0 }} />}
            <span style={{
              color: m.completed ? '#6b7280' : '#374151',
              fontWeight: m.module_id === nextId ? 600 : 400,
            }}>
              {m.title}
            </span>
            <Stars count={m.completed ? m.stars : 0} />
            <span style={{ flex: 1 }} />
            <span style={{ fontSize: 10, color: '#9ca3af' }}>{m.xp} XP</span>
          </div>
        ))}
      </div>

      {certified ? (
        <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 6, color: '#16a34a', fontWeight: 600 }}>
          <Sparkles size={13} /> Certified Vandal Workflow Architect
        </div>
      ) : nextModule && (
        <div style={{ marginTop: 10 }}>
          <CardButton
            label={completed === 0 ? `Start with ${nextModule.title}` : `Continue: ${nextModule.title}`}
            onClick={() => sendChatMessage(
              `Let's work on the "${nextModule.title}" certification module.`,
            )}
          />
        </div>
      )}
    </CardShell>
  )
}

// ---------------------------------------------------------------------------
// Module card — one module's exercise from get_certification_module
// ---------------------------------------------------------------------------

export function CertModuleCard({ content }: { content: Record<string, unknown> }) {
  const { sendChatMessage, chatSplitOpen, setChatSplitOpen } = useWorkspace()
  const title = String(content.title ?? content.module_id ?? 'Module')
  const xp = Number(content.xp ?? 0)
  const completed = Boolean(content.completed)
  const stars = Number(content.stars ?? 0)
  const overview = String(content.overview ?? '')
  const instructions = (content.instructions as string[]) || []
  const expectedFields = (content.expected_fields as string[]) || []
  const starCriteria = (content.star_criteria as Record<string, string>) || {}
  const assessmentKeys = (content.assessment_keys as string[]) || []
  const isReflective = assessmentKeys.length > 0
  const hasDocs = ((content.sample_documents as string[]) || []).length > 0

  return (
    <CardShell>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <Award size={15} style={{ color: ACCENT, flexShrink: 0 }} />
        <span style={{ fontWeight: 700, fontSize: 13 }}>{title}</span>
        {completed && (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, color: '#16a34a', fontSize: 11, fontWeight: 600 }}>
            <Check size={11} /> Completed <Stars count={stars} />
          </span>
        )}
        <span style={{ flex: 1 }} />
        <span style={{
          fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 999,
          background: 'color-mix(in srgb, var(--highlight-color, #eab308) 18%, white)',
          color: '#806600',
        }}>
          {xp} XP
        </span>
      </div>

      {overview && (
        <div style={{ lineHeight: 1.55, marginBottom: instructions.length ? 8 : 0 }}>{overview}</div>
      )}

      {instructions.length > 0 && (
        <ol style={{ margin: '0 0 8px', paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 3, lineHeight: 1.5 }}>
          {instructions.map((step, i) => (
            <li key={i}>{step}</li>
          ))}
        </ol>
      )}

      {expectedFields.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 4 }}>
            Expected fields
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {expectedFields.map((f) => (
              <span key={f} style={{
                fontSize: 10, padding: '2px 7px', borderRadius: 999,
                background: '#fff', border: '1px solid #e5e7eb', color: '#4b5563',
              }}>
                {f}
              </span>
            ))}
          </div>
        </div>
      )}

      {Object.keys(starCriteria).length > 0 && (
        <div style={{ marginBottom: 8, display: 'flex', flexDirection: 'column', gap: 2 }}>
          {Object.entries(starCriteria).sort(([a], [b]) => a.localeCompare(b)).map(([n, crit]) => (
            <div key={n} style={{ display: 'flex', alignItems: 'flex-start', gap: 5, fontSize: 11, color: '#6b7280' }}>
              <Stars count={Number(n) || 1} />
              <span style={{ lineHeight: 1.45 }}>{crit}</span>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
        {isReflective ? (
          <CardButton
            label="Answer the reflection questions"
            onClick={() => sendChatMessage(
              `I'm ready to answer the "${title}" reflection questions — ask me one at a time.`,
            )}
          />
        ) : (
          <CardButton
            label="Check my progress"
            onClick={() => sendChatMessage(`Check my progress on the "${title}" certification module.`)}
          />
        )}
        {hasDocs && !chatSplitOpen && (
          <CardButton
            subtle
            icon={<Columns2 size={12} />}
            label="Open files beside chat"
            onClick={() => setChatSplitOpen(true)}
          />
        )}
      </div>
    </CardShell>
  )
}

// ---------------------------------------------------------------------------
// Check card — validator results from check_certification_module
// ---------------------------------------------------------------------------

export function CertCheckCard({ content }: { content: Record<string, unknown> }) {
  const { sendChatMessage } = useWorkspace()
  const title = String(content.title ?? content.module_id ?? 'Module')
  const passed = Boolean(content.passed)
  const stars = Number(content.stars ?? 0)
  const checks = (content.checks as CheckRow[]) || []

  return (
    <CardShell>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ fontWeight: 700, fontSize: 13 }}>{title}</span>
        <span style={{
          display: 'inline-flex', alignItems: 'center', gap: 4,
          fontSize: 11, fontWeight: 600,
          color: passed ? '#16a34a' : '#b45309',
        }}>
          {passed ? <><Check size={12} /> All checks passed <Stars count={stars} /></> : 'Not there yet'}
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        {checks.map((c, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 6 }}>
            {c.passed
              ? <Check size={13} style={{ color: '#16a34a', flexShrink: 0, marginTop: 1 }} />
              : <X size={13} style={{ color: '#dc2626', flexShrink: 0, marginTop: 1 }} />}
            <div style={{ lineHeight: 1.45 }}>
              <span style={{ fontWeight: 600 }}>{c.name}</span>
              {c.detail && <span style={{ color: '#6b7280' }}> — {c.detail}</span>}
            </div>
          </div>
        ))}
      </div>

      {passed && (
        <div style={{ marginTop: 10 }}>
          <CardButton
            label="Complete the module"
            onClick={() => sendChatMessage(`Complete the "${title}" certification module and bank my XP.`)}
          />
        </div>
      )}
    </CardShell>
  )
}

// ---------------------------------------------------------------------------
// Completion card — XP award from complete_certification_module
// ---------------------------------------------------------------------------

export function CertCompletionCard({ content }: { content: Record<string, unknown> }) {
  const { sendChatMessage } = useWorkspace()
  const title = String(content.title ?? content.module_id ?? 'Module')
  const xpEarned = Number(content.xp_earned ?? 0)
  const totalXp = Number(content.total_xp ?? 0)
  const stars = Number(content.stars ?? 0)
  const level = String(content.level ?? '')
  const levelUp = Boolean(content.level_up)
  const certified = Boolean(content.certified)

  return (
    <div style={{ marginTop: 6, marginLeft: 20 }}>
      <div style={{
        border: '1px solid #bbf7d0',
        background: '#f0fdf4',
        borderRadius: 10,
        padding: '12px 14px',
        fontSize: 12,
        color: '#374151',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
          <Sparkles size={15} style={{ color: '#16a34a', flexShrink: 0 }} />
          <span style={{ fontWeight: 700, fontSize: 13, color: '#166534' }}>
            {title} complete
          </span>
          <Stars count={stars} />
        </div>
        <div style={{ lineHeight: 1.6 }}>
          {xpEarned > 0 ? <>+{xpEarned} XP · </> : null}
          {totalXp.toLocaleString()} XP total ·{' '}
          <span style={{ textTransform: 'capitalize' }}>
            {levelUp ? <strong>level up — {level}!</strong> : `level: ${level}`}
          </span>
        </div>
        {certified ? (
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6, color: '#166534', fontWeight: 700 }}>
            <Award size={14} /> You&rsquo;re a Certified Vandal Workflow Architect — all 11 modules complete.
          </div>
        ) : (
          <div style={{ marginTop: 8 }}>
            <CardButton
              subtle
              label="What's next?"
              onClick={() => sendChatMessage('Show my certification progress and the next module.')}
            />
          </div>
        )}
      </div>
    </div>
  )
}
