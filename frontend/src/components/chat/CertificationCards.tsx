/**
 * Rich in-chat cards for the certification tools.
 *
 * The certification program renders as structured cards inside the chat
 * stream — the LLM narrates around them, but the course content, checks, and
 * progress come verbatim from the deterministic backend (the same
 * certification_service the Certification panel uses). Lesson navigation and
 * certificate retrieval are direct actions; other buttons can ask the agent
 * for help or open the split view.
 */
import { Award, Check, Circle, CircleCheck, Columns2, Info, Sparkles, Star, X } from 'lucide-react'
import { useWorkspace } from '../../contexts/WorkspaceContext'
import { useCertificationPanelOptional } from '../../contexts/CertificationPanelContext'
import { renderMarkdown } from './markdown'
import './certification-cards.css'
import { ChatCertificateAccess } from './ChatCertificateAccess'
import { ChatLessonReader } from './ChatLessonReader'
import { ChatModuleLessons } from './ChatModuleLessons'
import { hasOutcomeAssessment } from '../../lib/certificationAssessment'
import { isCourseProgressionPolicy } from '../../lib/certificationPayload'
import { CourseLearningPolicy } from '../certification/CourseLearningPolicy'

const ACCENT = 'var(--highlight-color, #eab308)'

interface ModuleRow {
  module_id: string
  title: string
  xp: number
  completed: boolean
  stars: number
}

interface CheckRow {
  role?: 'required' | 'advisory'
  name: string
  passed: boolean
  detail: string
}

function Stars({ count, content }: { count: number; content: Record<string, unknown> }) {
  if (count <= 0 || content.credit_basis === 'required_outcomes' || content.assessment_mode === 'selected_saved_outcomes') return null
  const maximum = typeof content.maximum_stars === 'number' ? content.maximum_stars : content.enrollment_id ? null : 3
  const label = maximum ? `${count} of ${maximum} stars` : `${count} stars recorded`
  return (
    <span role="img" aria-label={label} style={{ display: 'inline-flex', gap: 1, verticalAlign: 'middle' }}>
      {Array.from({ length: count }, (_, i) => (
        <Star key={i} aria-hidden="true" size={10} fill="var(--highlight-on-light, #806600)" style={{ color: 'var(--highlight-on-light, #806600)' }} />
      ))}
    </span>
  )
}

function matchesSelectedCourse(content: Record<string, unknown>, certification: ReturnType<typeof useCertificationPanelOptional>) {
  const enrolled = typeof content.enrollment_id === 'string'
  if (!certification) return !enrolled
  const { progress, course } = certification
  if (!progress) return false
  if (!enrolled) return !progress.enrollment_id && !course
  return !!course && course.enrollment_id === content.enrollment_id && progress.enrollment_id === content.enrollment_id
    && course.course_version === content.course_version && progress.course_version === content.course_version
    && course.manifest_sha256 === content.manifest_sha256 && progress.manifest_sha256 === content.manifest_sha256
    && (typeof content.module_id !== 'string' || course.modules.some(module => module.id === content.module_id))
}

function CardShell({ children, content, footer, readingOnly = false }: { children: React.ReactNode; content: Record<string, unknown>; footer?: React.ReactNode; readingOnly?: boolean }) {
  const certification = useCertificationPanelOptional()
  const stale = !matchesSelectedCourse(content, certification)
  return (
    <div className="cert-chat-card" style={{ marginTop: 'var(--workspace-space-6)', marginLeft: 'var(--workspace-space-20)' }}>
      <div
        style={{
          border: "1px solid color-mix(in srgb, var(--highlight-color, #eab308) 30%, var(--workspace-border))",
          background: 'color-mix(in srgb, var(--highlight-color, #eab308) 5%, white)',
          borderRadius: 'var(--workspace-radius-large)',
          padding: "var(--workspace-space-12) var(--workspace-space-16)",
          fontSize: 'var(--workspace-font-meta)',
          color: '#374151',
        }}
      >
        {typeof content.course_title === 'string' && <p className="mb-2 text-xs font-medium text-gray-700">{content.course_title}{typeof content.course_version === 'string' ? ` · ${content.course_version}` : ''}</p>}
        {stale && <div className="mb-3 text-sm text-gray-700" role="status">
          <p>This card is from an earlier or unavailable course selection. Refresh your progress to continue.</p>
          {certification && <button type="button" className="mt-1 underline" onClick={() => void certification.refresh()}>Refresh progress</button>}
        </div>}
        <fieldset disabled={stale && !readingOnly} onClickCapture={event => {
          const control = event.target instanceof Element ? event.target.closest('button, input, select, textarea') : null
          if (stale && !readingOnly && control) { event.preventDefault(); event.stopPropagation() }
        }} style={{ minWidth: 0, margin: 0, padding: 0, border: 0 }}>{children}</fieldset>
        {footer}
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
        display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-6)',
        padding: "var(--workspace-space-6) var(--workspace-space-12)", fontSize: 'var(--workspace-font-meta)', fontWeight: 500, fontFamily: 'inherit',
        borderRadius: 'var(--workspace-radius-medium)', border: "1px solid var(--workspace-border)",
        background: '#fff', color: '#374151', cursor: 'pointer',
      } : {
        display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-6)',
        fontSize: 'var(--workspace-font-meta)', padding: "var(--workspace-space-6) var(--workspace-space-16)",
      }}
    >
      {icon}
      {label}
    </button>
  )
}

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
    <CardShell content={content} footer={certified && <ChatCertificateAccess enrollmentId={typeof content.enrollment_id === 'string' ? content.enrollment_id : undefined} />}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 'var(--workspace-space-8)', marginBottom: 'var(--workspace-space-8)' }}>
        <Award size={15} style={{ color: ACCENT, flexShrink: 0 }} />
        <span style={{ fontWeight: 700, fontSize: 'var(--workspace-font-control)' }}>{typeof content.course_title === 'string' ? 'Course progress' : 'Vandal Workflow Architect'}</span>
        <span style={{ flex: 1 }} />
        <span style={{ color: 'var(--cert-text-muted)', textTransform: 'capitalize' }}>
          {level} · {xp.toLocaleString()} XP
        </span>
      </div>

      <div role="progressbar" aria-label="Course modules completed" aria-valuemin={0} aria-valuemax={Math.max(1, total)} aria-valuenow={completed} aria-valuetext={`${completed} of ${total} modules complete`} style={{ height: 5, borderRadius: 'var(--workspace-radius-small)', background: '#e5e7eb', overflow: 'hidden', marginBottom: 'var(--workspace-space-4)' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: ACCENT, transition: 'width 0.4s ease' }} />
      </div>
      <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--cert-text-muted)', marginBottom: 'var(--workspace-space-12)' }}>
        {completed}/{total} modules complete
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-4)' }}>
        {modules.map((m) => (
          <div key={m.module_id} style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-6)', lineHeight: 1.5 }}>
            {m.completed
              ? <CircleCheck role="img" aria-label="Completed" size={13} style={{ color: 'var(--cert-text-success)', flexShrink: 0 }} />
              : <Circle role="img" aria-label={m.module_id === nextId ? 'Next module' : 'Not completed'} size={13} style={{ color: m.module_id === nextId ? 'var(--highlight-on-light, #806600)' : '#6b7280', flexShrink: 0 }} />}
            <span style={{
              color: m.completed ? 'var(--cert-text-muted)' : '#374151',
              fontWeight: m.module_id === nextId ? 600 : 400,
            }}>
              {m.title}
            </span>
            <Stars count={m.completed ? m.stars : 0} content={content} />
            <span style={{ flex: 1 }} />
            <span style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--cert-text-muted)' }}>{m.xp} XP</span>
          </div>
        ))}
      </div>

      {certified ? (
        <div style={{ marginTop: 'var(--workspace-space-12)', display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-6)', color: 'var(--cert-text-success)', fontWeight: 600 }}>
          <Sparkles size={13} aria-hidden="true" /> Course complete
        </div>
      ) : nextModule && (
        <div style={{ marginTop: 'var(--workspace-space-12)' }}>
          <CardButton
            label={completed === 0 ? `Start with ${nextModule.title}` : `Continue: ${nextModule.title}`}
            onClick={() => sendChatMessage(
              `Let's work on the "${nextModule.title}" certification module.`,
            )}
          />
        </div>
      )}
      {isCourseProgressionPolicy(content.progression_policy) && <CourseLearningPolicy course={{ progression_policy: content.progression_policy }} />}
    </CardShell>
  )
}

// ---------------------------------------------------------------------------
// Module card — one module's exercise from get_certification_module
// ---------------------------------------------------------------------------

export function CertModuleCard({ content }: { content: Record<string, unknown> }) {
  const { sendChatMessage, chatSplitOpen, setChatSplitOpen } = useWorkspace()
  const certification = useCertificationPanelOptional()
  const { course, progress } = certification ?? {}
  const enrolledCard = typeof content.enrollment_id === 'string'
  const currentEnrolledCard = !!course && !!progress && enrolledCard
    && course.enrollment_id === content.enrollment_id && progress.enrollment_id === content.enrollment_id
    && course.course_version === content.course_version && progress.course_version === content.course_version
    && course.manifest_sha256 === content.manifest_sha256 && progress.manifest_sha256 === content.manifest_sha256
  const currentModule = currentEnrolledCard ? course.modules.find(module => module.id === content.module_id) : undefined
  const staleCard = enrolledCard ? !currentModule : !!certification && (!!course || !!progress?.enrollment_id)
  const outcomeAssessment = hasOutcomeAssessment(currentModule)
  const required = currentModule ? course?.prerequisites?.[currentModule.id] : undefined
  const prerequisitesMet = !!required && required.every(id => progress?.modules[id]?.completed)
  const title = String(content.title ?? content.module_id ?? 'Module')
  const xp = Number(content.xp ?? 0)
  const completed = Boolean(content.completed)
  const stars = Number(content.stars ?? 0)
  const overview = String(content.overview ?? '')
  const instructions = (content.instructions as string[]) || []
  const expectedFields = (content.expected_fields as string[]) || []
  const starCriteria = (content.star_criteria as Record<string, string>) || {}
  const requiredOutcomes = (content.required_outcomes as { outcome_id: string; statement: string }[]) || []
  const assessmentKeys = (content.assessment_keys as string[]) || []
  const isReflective = assessmentKeys.length > 0
  const hasDocs = ((content.sample_documents as string[]) || []).length > 0
  const lessonCount = ((content.lesson_titles as string[]) || []).length

  return (
    <CardShell content={content} footer={staleCard && <div className="mt-3 space-y-2">
      <p className="text-sm text-gray-700">These saved instructions are not bound to your selected course. Open the current course before preparing or assessing work.</p>
      {certification && <CardButton label="Open current course" onClick={() => certification.openPanel()} />}
    </div>}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 'var(--workspace-space-8)', marginBottom: 'var(--workspace-space-6)' }}>
        <Award size={15} style={{ color: ACCENT, flexShrink: 0 }} />
        <span style={{ flex: '1 1 8rem', minWidth: 0, fontWeight: 700, fontSize: 'var(--workspace-font-control)' }}>{title}</span>
        {completed && (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-4)', color: 'var(--cert-text-success)', fontSize: 'var(--workspace-font-meta)', fontWeight: 600, whiteSpace: 'nowrap' }}>
            <Check size={11} /> Completed <Stars count={stars} content={content} />
          </span>
        )}
        <span style={{ flex: 1 }} />
        <span style={{
          whiteSpace: 'nowrap', flexShrink: 0, fontSize: 'var(--workspace-font-meta)', fontWeight: 700, padding: "var(--workspace-space-2) var(--workspace-space-8)", borderRadius: 999,
          background: 'color-mix(in srgb, var(--highlight-color, #eab308) 18%, white)',
          color: '#806600',
        }}>
          {xp} XP
        </span>
      </div>

      {overview && (
        <div className="chat-markdown" style={{ lineHeight: 1.55, marginBottom: instructions.length ? 8 : 0 }} dangerouslySetInnerHTML={{ __html: renderMarkdown(overview) }} />
      )}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--workspace-space-6)', marginTop: 'var(--workspace-space-4)' }}>
        {lessonCount > 0 && !completed && (
          <ChatModuleLessons content={content} />
        )}
        {staleCard ? null
          : outcomeAssessment && currentModule && certification ? <button type="button" className="chat-action-btn"
            disabled={!prerequisitesMet} onClick={() => certification.openAssessment(currentModule.id, String(content.enrollment_id), String(content.manifest_sha256))}>
            Open module assessment
          </button> : isReflective ? (
          <CardButton
            subtle={lessonCount > 0 && !completed}
            label="Answer the reflection questions"
            onClick={() => sendChatMessage(
              `I'm ready to answer the "${title}" reflection questions — ask me one at a time.`,
            )}
          />
        ) : (
          <CardButton
            subtle={lessonCount > 0 && !completed}
            label="Check my progress"
            onClick={() => sendChatMessage(`Check my progress on the "${title}" certification module.`)}
          />
        )}
        {hasDocs && !staleCard && (
          <CardButton subtle label="Set up lab" onClick={() => sendChatMessage(`Set up the certification lab for the "${title}" module using its assigned sample documents.`)} />
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
      {outcomeAssessment && !prerequisitesMet && <p className="mt-2 text-sm text-gray-700">Complete the required earlier modules in your selected course before opening this assessment.</p>}

      {(instructions.length > 0 || expectedFields.length > 0) && (
        <details className="my-3">
          <summary className="cursor-pointer font-semibold text-gray-800" style={{ minHeight: 44, paddingBlock: 10 }}>
            Exercise instructions · {instructions.length} {instructions.length === 1 ? 'step' : 'steps'}{expectedFields.length > 0 ? ` · ${expectedFields.length} expected fields` : ''}
          </summary>
          <div className="mt-2">
            {instructions.length > 0 && (
              <ol className="cert-procedure" style={{ listStyleType: 'decimal', margin: "0 0 var(--workspace-space-8)", paddingLeft: 'var(--workspace-space-20)', display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-4)', lineHeight: 1.5 }}>
                {instructions.map((step, i) => (
                  <li key={i}><div className="chat-markdown" dangerouslySetInnerHTML={{ __html: renderMarkdown(step) }} /></li>
                ))}
              </ol>
            )}

            {expectedFields.length > 0 && (
              <div style={{ marginBottom: 'var(--workspace-space-8)' }}>
                <div style={{ fontSize: 'var(--workspace-font-meta)', fontWeight: 700, color: 'var(--cert-text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 'var(--workspace-space-4)' }}>
                  Expected fields
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--workspace-space-4)' }}>
                  {expectedFields.map((f) => (
                    <span key={f} style={{
                      fontSize: 'var(--workspace-font-meta)', padding: "var(--workspace-space-2) 7px", borderRadius: 999,
                      background: '#fff', border: "1px solid var(--workspace-border)", color: '#4b5563',
                    }}>
                      {f}
                    </span>
                  ))}
                </div>
              </div>
            )}

          </div>
        </details>
      )}

      {requiredOutcomes.length > 0 ? (
        <div className="my-3">
          <h4 className="mb-1 font-semibold text-gray-800">Required outcomes</h4>
          <p className="mb-2 text-gray-700">All required outcomes must pass. Open the module assessment for the evidence and passing checks.</p>
          <ul className="list-disc space-y-2 pl-5 text-gray-700">
            {requiredOutcomes.map(outcome => <li key={outcome.outcome_id}>{outcome.statement}</li>)}
          </ul>
        </div>
      ) : Object.keys(starCriteria).length > 0 && (
        <div style={{ marginBottom: 'var(--workspace-space-8)', display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-2)' }}>
          <h4 className="mb-1 font-semibold text-gray-800">Passing requirements</h4>
          {Object.entries(starCriteria).sort(([a], [b]) => a.localeCompare(b)).map(([n, crit]) => (
            <div key={n} style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--workspace-space-6)', fontSize: 'var(--workspace-font-meta)', color: 'var(--cert-text-muted)' }}>
              <Stars count={Number(n) || 1} content={content} />
              <span style={{ lineHeight: 1.45 }}>{crit}</span>
            </div>
          ))}
        </div>
      )}

    </CardShell>
  )
}

// ---------------------------------------------------------------------------
// Lesson card — one lesson's content from get_certification_lesson
// ---------------------------------------------------------------------------

export function CertLessonCard({ content }: { content: Record<string, unknown> }) {
  const certification = useCertificationPanelOptional()
  const readOnly = !matchesSelectedCourse(content, certification)
  return <CardShell content={content} readingOnly><ChatLessonReader readOnly={readOnly} key={`${content.enrollment_id ?? 'legacy'}:${content.manifest_sha256 ?? ''}:${content.module_id}:${content.lesson_id ?? content.lesson_number}`} content={content} /></CardShell>
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
    <CardShell content={content}>
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 'var(--workspace-space-8)', marginBottom: 'var(--workspace-space-8)' }}>
        <span style={{ fontWeight: 700, fontSize: 'var(--workspace-font-control)' }}>{title}</span>
        <span style={{
          display: 'inline-flex', flexWrap: 'wrap', alignItems: 'center', gap: 'var(--workspace-space-4)',
          fontSize: 'var(--workspace-font-meta)', fontWeight: 600,
          color: passed ? 'var(--cert-text-success)' : '#b45309',
        }}>
          {passed ? <><Check size={12} /> {checks.length > 0 && checks.every(check => check.passed) ? 'All checks passed' : 'Module requirements met'} <Stars count={stars} content={content} /></> : 'Not there yet'}
        </span>
      </div>

      {passed && checks.some(check => !check.passed && check.role === 'advisory') && <p className="mb-3 text-sm text-gray-700">Advisory suggestions do not block completion.</p>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-6)' }}>
        {checks.map((c, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--workspace-space-6)' }}>
            {c.passed
              ? <Check size={13} style={{ color: 'var(--cert-text-success)', flexShrink: 0, marginTop: 1 }} />
              : c.role === 'advisory'
                ? <Info size={13} aria-hidden="true" style={{ color: '#92400e', flexShrink: 0, marginTop: 1 }} />
                : <X size={13} style={{ color: '#dc2626', flexShrink: 0, marginTop: 1 }} />}
            <div style={{ lineHeight: 1.45 }}>
              <span style={{ fontWeight: 600 }}>{c.name}</span>
              {c.role && <span> — {c.role === 'advisory' ? `Advisory: ${c.passed ? 'Met' : 'Suggestion'}` : `Required: ${c.passed ? 'Met' : 'Not met'}`}</span>}
              {c.detail && <span style={{ color: 'var(--cert-text-muted)' }}> — {c.detail}</span>}
            </div>
          </div>
        ))}
      </div>

      {passed && (
        <div style={{ marginTop: 'var(--workspace-space-12)' }}>
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
  const certification = useCertificationPanelOptional()
  const stale = !matchesSelectedCourse(content, certification)
  const title = String(content.title ?? content.module_id ?? 'Module')
  const xpEarned = Number(content.xp_earned ?? 0)
  const totalXp = Number(content.total_xp ?? 0)
  const stars = Number(content.stars ?? 0)
  const level = String(content.level ?? '')
  const levelUp = Boolean(content.level_up)
  const certified = Boolean(content.certified)

  return (
    <div className="cert-chat-card" style={{ marginTop: 'var(--workspace-space-6)', marginLeft: 'var(--workspace-space-20)' }}>
      <div style={{
        border: '1px solid #bbf7d0',
        background: '#f0fdf4',
        borderRadius: 'var(--workspace-radius-large)',
        padding: "var(--workspace-space-12) var(--workspace-space-16)",
        fontSize: 'var(--workspace-font-meta)',
        color: '#374151',
      }}>
        {typeof content.course_title === 'string' && <p className="mb-2 text-xs font-medium text-gray-700">{content.course_title}</p>}
        {typeof content.course_version === 'string' && <p className="mb-2 text-xs text-gray-700">Course version: {content.course_version}</p>}
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', marginBottom: 'var(--workspace-space-4)' }}>
          <Sparkles size={15} style={{ color: 'var(--cert-text-success)', flexShrink: 0 }} />
          <span style={{ fontWeight: 700, fontSize: 'var(--workspace-font-control)', color: '#166534' }}>
            {title} complete
          </span>
          <Stars count={stars} content={content} />
        </div>
        <div style={{ lineHeight: 1.6 }}>
          {content.credit_origin === 'transferred' ? <>{Number(content.xp_carried ?? 0)} XP carried · no new XP reward · </> : xpEarned > 0 ? <>+{xpEarned} XP · </> : null}
          {totalXp.toLocaleString()} XP total ·{' '}
          <span style={{ textTransform: 'capitalize' }}>
            {levelUp ? <strong>level up — {level}!</strong> : `level: ${level}`}
          </span>
        </div>
        {certified ? (
          <div style={{ marginTop: 'var(--workspace-space-8)', display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-6)', color: '#166534', fontWeight: 700 }}>
            <Award size={14} /> {typeof content.course_title === 'string' ? `${content.course_title} complete` : 'Certification complete'} — {typeof content.modules_total === 'number' && content.modules_total > 0 ? `all ${content.modules_total} modules complete.` : 'the course requirements are complete.'}
          </div>
        ) : (
          <div style={{ marginTop: 'var(--workspace-space-8)' }}>
            {stale ? <>
              <p className="mb-2 text-sm text-gray-700">This saved result belongs to an earlier or unavailable course selection.</p>
              {certification && <CardButton label="Open current course" onClick={() => certification.openPanel()} />}
            </> : <CardButton
              subtle
              label="What's next?"
              onClick={() => sendChatMessage('Show my certification progress and the next module.')}
            />}
          </div>
        )}
        {certified && <>
          <ChatCertificateAccess enrollmentId={typeof content.enrollment_id === 'string' ? content.enrollment_id : undefined} />
        </>}
      </div>
    </div>
  )
}
