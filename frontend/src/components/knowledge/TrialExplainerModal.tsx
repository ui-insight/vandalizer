import { usePanelEffect } from '../shared/usePanelEffect'
import './comparison-layout.css'
import { FocusTrap } from '../shared/PanelFocusTrap'
import { X } from 'lucide-react'
import type { OptimizationTrial } from '../../api/knowledge'
import { scoreColor } from '../shared/TrialsTable'
import {
  describeTrialPlainly,
  explainEarlyStop,
  explainTrialOutcome,
  explainTrialParameters,
} from './trialExplanations'

interface Props {
  /** The trial to explain, or null to keep the modal closed. */
  trial: OptimizationTrial | null
  onClose: () => void
}

const STATUS_BADGE: Record<string, { label: string; color: string }> = {
  completed: { label: 'Completed', color: 'var(--workspace-success)' },
  early_stopped: { label: 'Stopped early', color: 'var(--workspace-warning)' },
  failed: { label: 'Failed', color: 'var(--workspace-danger)' },
}

/**
 * Plain-English explainer for a single KB optimization trial.
 *
 * Opened by tapping a trial row. Answers, in order: what did this trial try,
 * how did it score, and what each setting it used means and why it matters —
 * written for a reader who may be seeing these terms for the first time.
 */
export function TrialExplainerModal({ trial, onClose }: Props) {
  // Escape-to-close. Effect runs unconditionally (hook order stays stable);
  // the listener is a no-op while the modal is closed.
  usePanelEffect(() => {
    if (!trial) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [trial, onClose])

  if (!trial) return null

  const score = trial.score ?? 0
  const scorePct = Math.round(score * 100)
  const params = explainTrialParameters(trial.config)
  const whatItTried = describeTrialPlainly(trial.config)
  const outcome = explainTrialOutcome(trial)
  const earlyStop = explainEarlyStop(trial.early_stop_reason)
  const badge = STATUS_BADGE[trial.status] ?? { label: trial.status, color: 'var(--workspace-muted)' }
  const lift = trial.lift_vs_default
  const disc = trial.discrimination_summary

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Trial details"
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0, 0, 0, 0.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <FocusTrap focusTrapOptions={{ allowOutsideClick: true, escapeDeactivates: false, tabbableOptions: { displayCheck: import.meta.env.MODE === 'test' ? 'none' : 'full' } }}>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 'min(560px, 92vw)', containerType: 'inline-size',
          maxHeight: 'calc(100dvh - 24px)',
          overflowWrap: 'anywhere',
          background: 'var(--workspace-canvas)',
          border: '1px solid var(--workspace-border)',
          borderRadius: 10,
          display: 'flex', flexDirection: 'column',
          fontFamily: 'inherit',
        }}
      >
        {/* Header */}
        <header style={{
          padding: '14px 18px', flexShrink: 0,
          borderBottom: '1px solid var(--workspace-border)',
          display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <span style={{
              width: 9, height: 9, borderRadius: '50%', flexShrink: 0,
              backgroundColor: scoreColor(score),
            }} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 'var(--workspace-font-body)', fontWeight: 600, color: 'var(--workspace-text)' }}>
                Trial details
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginTop: 3 }}>
                <span style={{ fontSize: 'var(--workspace-font-section-title)', fontWeight: 700, color: 'var(--workspace-text)' }}>
                  {scorePct}%
                </span>
                {lift != null && (
                  <span style={{
                    fontSize: 'var(--workspace-font-meta)', fontWeight: 600,
                    color: lift > 0 ? 'var(--workspace-success)' : lift < 0 ? 'var(--workspace-danger)' : 'var(--workspace-muted)',
                  }}>
                    {lift > 0 ? '+' : ''}{Math.round(lift * 100)} pts vs current
                  </span>
                )}
                <span style={{
                  fontSize: 'var(--workspace-font-meta)', fontWeight: 600, color: badge.color,
                  border: `1px solid color-mix(in srgb, ${badge.color} 33.33%, transparent)`, borderRadius: 999,
                  padding: '1px 7px',
                }}>
                  {badge.label}
                </span>
              </div>
            </div>
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            style={{
              background: 'transparent', border: 'none', color: 'var(--workspace-muted)',
              cursor: 'pointer', padding: 4, flexShrink: 0, minWidth: 36, minHeight: 36,
            }}
          >
            <X size={16} aria-hidden="true" />
          </button>
        </header>

        {/* Body */}
        <div tabIndex={0} role="region" aria-label="Trial explanation" style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '14px 18px 18px' }}>
          {/* What it tried */}
          <Section title="What this trial tried">
            <p style={{ margin: 0, fontSize: 'var(--workspace-font-control)', lineHeight: 1.6, color: 'var(--workspace-text)' }}>
              {whatItTried}
            </p>
            <p style={{ margin: '8px 0 0', fontSize: 'var(--workspace-font-meta)', lineHeight: 1.6, color: 'var(--workspace-muted)' }}>
              {outcome}
            </p>
            {earlyStop && (
              <p style={{
                margin: '10px 0 0', fontSize: 'var(--workspace-font-meta)', lineHeight: 1.55, color: 'var(--workspace-warning)',
                background: 'rgba(245,158,11,0.08)', border: '1px solid rgba(245,158,11,0.25)',
                borderRadius: 6, padding: '8px 10px',
              }}>
                {earlyStop}
              </p>
            )}
          </Section>

          {/* Settings used */}
          <Section title="Settings it used, and why they matter">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {params.map((p) => (
                <div key={p.key} className="optimization-trial-parameter" style={{
                  display: 'grid', gap: 10,
                  alignItems: 'baseline',
                }}>
                  <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
                    {p.label}
                  </div>
                  <div>
                    <div style={{ fontSize: 'var(--workspace-font-control)', fontWeight: 600, color: 'var(--workspace-text)' }}>
                      {p.value}
                    </div>
                    <div style={{ fontSize: 'var(--workspace-font-meta)', lineHeight: 1.55, color: 'var(--workspace-muted)', marginTop: 2 }}>
                      {p.why}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Section>

          {/* How it scored */}
          <Section title="How it scored">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              <Stat label="Overall quality" value={`${scorePct}%`} />
              {trial.judge_score != null && (
                <Stat label="Answer-quality grade" value={`${Math.round(trial.judge_score * 100)}%`} />
              )}
              {trial.num_queries_judged != null && (
                <Stat label="Questions graded" value={String(trial.num_queries_judged)} />
              )}
              {typeof trial.duration_seconds === 'number' && (
                <Stat label="Time" value={`${trial.duration_seconds.toFixed(1)}s`} />
              )}
              {typeof trial.tokens_used === 'number' && trial.tokens_used > 0 && (
                <Stat label="Tokens used" value={trial.tokens_used.toLocaleString()} />
              )}
            </div>
            {disc && (disc.useful + disc.redundant + disc.failing + disc.other) > 0 && (
              <p style={{ margin: '10px 0 0', fontSize: 'var(--workspace-font-meta)', lineHeight: 1.55, color: 'var(--workspace-muted)' }}>
                Of the graded questions: <strong style={{ color: 'var(--workspace-success)' }}>{disc.useful} answered
                well</strong>, {disc.redundant} where the knowledge base added little, and{' '}
                <strong style={{ color: 'var(--workspace-danger)' }}>{disc.failing} that failed</strong>.
              </p>
            )}
            <p style={{ margin: '10px 0 0', fontSize: 'var(--workspace-font-meta)', lineHeight: 1.5, color: 'var(--workspace-muted)' }}>
              The overall quality score blends the AI answer-quality grade (40%) with retrieval
              precision (25%), source health (20%), and how much of each document the
              answers drew on (15%).
            </p>
          </Section>
        </div>
      </div>
      </FocusTrap>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: 18 }}>
      <h3 style={{
        margin: '0 0 8px', fontSize: 'var(--workspace-font-meta)', fontWeight: 600,
        letterSpacing: 0.4, textTransform: 'uppercase', color: 'var(--workspace-muted)',
      }}>
        {title}
      </h3>
      {children}
    </section>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span style={{
      display: 'inline-flex', flexDirection: 'column', gap: 1,
      padding: '5px 10px',
      background: 'var(--workspace-canvas)', border: '1px solid var(--workspace-border)',
      borderRadius: 6,
    }}>
      <span style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', textTransform: 'uppercase', letterSpacing: 0.3 }}>
        {label}
      </span>
      <span style={{ fontSize: 'var(--workspace-font-control)', fontWeight: 600, color: 'var(--workspace-text)', fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </span>
    </span>
  )
}
