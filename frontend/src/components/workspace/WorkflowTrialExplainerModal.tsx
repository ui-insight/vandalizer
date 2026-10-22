import { usePanelEffect } from '../shared/usePanelEffect'
import { X } from 'lucide-react'
import type { WorkflowOptimizationTrial } from '../../api/workflows'
import { scoreColor } from '../shared/TrialsTable'
import {
  describeWorkflowTrialPlainly,
  explainWorkflowOutcome,
  explainWorkflowSteps,
} from './workflowTrialExplanations'

interface Props {
  trial: WorkflowOptimizationTrial | null
  onClose: () => void
}

const STATUS_BADGE: Record<string, { label: string; color: string }> = {
  completed: { label: 'Completed', color: 'var(--workspace-success)' },
  early_stopped: { label: 'Stopped early', color: 'var(--workspace-warning)' },
  failed: { label: 'Failed', color: 'var(--workspace-danger)' },
  cancelled: { label: 'Cancelled', color: 'var(--workspace-muted)' },
}

/**
 * Plain-English explainer for a single workflow optimization trial. Opened by
 * tapping a trial row. Because a workflow trial tweaks settings per LLM step,
 * the "settings" section reads step-by-step, and the score section shows how
 * each step did.
 */
export function WorkflowTrialExplainerModal({ trial, onClose }: Props) {
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
  const steps = explainWorkflowSteps(trial.config)
  const whatItTried = describeWorkflowTrialPlainly(trial.config)
  const outcome = explainWorkflowOutcome(trial)
  const badge = STATUS_BADGE[trial.status] ?? { label: trial.status, color: 'var(--workspace-muted)' }
  const lift = trial.lift_vs_default
  const breakdown = trial.step_breakdown ?? []

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
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 'min(560px, 92vw)',
          maxHeight: '88vh',
          background: 'var(--workspace-canvas)',
          border: '1px solid var(--workspace-border)',
          borderRadius: 'var(--workspace-radius-large)',
          display: 'flex', flexDirection: 'column',
          fontFamily: 'inherit',
        }}
      >
        {/* Header */}
        <header style={{
          padding: "var(--workspace-space-16) var(--workspace-space-20)",
          borderBottom: '1px solid var(--workspace-border)',
          display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 'var(--workspace-space-12)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-12)', minWidth: 0 }}>
            <span style={{
              width: 9, height: 9, borderRadius: '50%', flexShrink: 0,
              backgroundColor: scoreColor(score),
            }} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 'var(--workspace-font-body)', fontWeight: 600, color: 'var(--workspace-text)' }}>
                Trial details
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', marginTop: 'var(--workspace-space-4)' }}>
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
            aria-label="Close"
            onClick={onClose}
            style={{
              background: 'transparent', border: 'none', color: 'var(--workspace-muted)',
              cursor: 'pointer', padding: 'var(--workspace-space-4)', flexShrink: 0,
            }}
          >
            <X size={16} />
          </button>
        </header>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: "var(--workspace-space-16) var(--workspace-space-20) var(--workspace-space-20)" }}>
          {/* What it tried */}
          <Section title="What this trial tried">
            <p style={{ margin: 0, fontSize: 'var(--workspace-font-control)', lineHeight: 1.6, color: 'var(--workspace-text)' }}>
              {whatItTried}
            </p>
            <p style={{ margin: "var(--workspace-space-8) 0 0", fontSize: 'var(--workspace-font-meta)', lineHeight: 1.6, color: 'var(--workspace-muted)' }}>
              {outcome}
            </p>
            {trial.error && (
              <p style={{
                margin: "var(--workspace-space-12) 0 0", fontSize: 'var(--workspace-font-meta)', lineHeight: 1.55, color: 'var(--workspace-danger)',
                background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)',
                borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-8) var(--workspace-space-12)",
              }}>
                {trial.error}
              </p>
            )}
          </Section>

          {/* Per-step settings */}
          <Section title="What it changed, step by step">
            {steps.length === 0 ? (
              <p style={{ margin: 0, fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
                No step-level changes. This trial ran the workflow with its current settings.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-12)' }}>
                {steps.map((s) => (
                  <div key={s.step} style={{
                    border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-small)', padding: "var(--workspace-space-8) var(--workspace-space-12)",
                  }}>
                    <div style={{ fontSize: 'var(--workspace-font-control)', fontWeight: 600, color: 'var(--workspace-text)', marginBottom: 'var(--workspace-space-4)' }}>
                      {s.step}
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: "var(--workspace-space-2) var(--workspace-space-16)", fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
                      <span><span style={{ color: 'var(--workspace-muted)' }}>Model:</span> {s.model}</span>
                      <span><span style={{ color: 'var(--workspace-muted)' }}>Prompt:</span> {s.promptVariant}</span>
                    </div>
                    {s.promptWhy && (
                      <div style={{ fontSize: 'var(--workspace-font-meta)', lineHeight: 1.5, color: 'var(--workspace-muted)', marginTop: 'var(--workspace-space-4)' }}>
                        {s.promptWhy}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            <p style={{ margin: "var(--workspace-space-12) 0 0", fontSize: 'var(--workspace-font-meta)', lineHeight: 1.5, color: '#6f6f6f' }}>
              Each step can run on a different AI model and prompt style. Stronger
              models reason better but cost more; the prompt style nudges how the
              step answers. Steps not listed kept their current settings.
            </p>
          </Section>

          {/* How it scored */}
          <Section title="How it scored">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--workspace-space-6)' }}>
              <Stat label="Overall score" value={`${scorePct}%`} />
              {trial.weighted_pass_rate != null && (
                <Stat label="Weighted pass rate" value={`${Math.round(trial.weighted_pass_rate * 100)}%`} />
              )}
              {typeof trial.num_inputs_run === 'number' && typeof trial.num_inputs_total === 'number' && (
                <Stat label="Inputs run" value={`${trial.num_inputs_run}/${trial.num_inputs_total}`} />
              )}
              {typeof trial.duration_seconds === 'number' && (
                <Stat label="Time" value={`${trial.duration_seconds.toFixed(1)}s`} />
              )}
              {typeof trial.tokens_used === 'number' && trial.tokens_used > 0 && (
                <Stat label="Tokens used" value={trial.tokens_used.toLocaleString()} />
              )}
            </div>

            {breakdown.length > 0 && (
              <div style={{ marginTop: 'var(--workspace-space-12)', display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-4)' }}>
                {breakdown.map((b) => (
                  <div key={b.step} style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', fontSize: 'var(--workspace-font-meta)' }}>
                    <span style={{ width: 150, color: 'var(--workspace-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {b.step}
                    </span>
                    <div style={{ flex: 1, height: 5, background: 'var(--workspace-surface)', borderRadius: 3, overflow: 'hidden' }}>
                      <div style={{
                        width: `${Math.max(0, Math.min(100, b.score))}%`, height: '100%',
                        background: b.score >= 80 ? '#22c55e' : b.score >= 60 ? '#f59e0b' : '#ef4444',
                      }} />
                    </div>
                    <span style={{ width: 70, textAlign: 'right', color: 'var(--workspace-muted)', fontVariantNumeric: 'tabular-nums' }}>
                      {b.score.toFixed(0)}% · {b.pass}/{b.total}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <p style={{ margin: "var(--workspace-space-12) 0 0", fontSize: 'var(--workspace-font-meta)', lineHeight: 1.5, color: '#6f6f6f' }}>
              The score is the share of test inputs the workflow handled well. The
              per-step bars show where in the workflow the quality came from (or
              fell down), as a pass count out of the inputs evaluated.
            </p>
          </Section>
        </div>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: 'var(--workspace-space-20)' }}>
      <h3 style={{
        margin: "0 0 var(--workspace-space-8)", fontSize: 'var(--workspace-font-meta)', fontWeight: 600,
        letterSpacing: 0.4, textTransform: 'uppercase', color: '#7a7a7a',
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
      padding: "var(--workspace-space-6) var(--workspace-space-12)",
      background: 'var(--workspace-canvas)', border: '1px solid var(--workspace-border)',
      borderRadius: 'var(--workspace-radius-small)',
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
