import { useEffect } from 'react'
import { X } from 'lucide-react'
import type { ExtractionTrial } from '../../api/extractions'
import { scoreColor } from '../shared/TrialsTable'
import {
  describeExtractionTrialPlainly,
  explainExtractionOutcome,
  explainExtractionParameters,
} from './extractionTrialExplanations'

interface Props {
  trial: ExtractionTrial | null
  onClose: () => void
}

const STATUS_BADGE: Record<string, { label: string; color: string }> = {
  completed: { label: 'Completed', color: '#22c55e' },
  early_stopped: { label: 'Stopped early', color: '#f59e0b' },
  failed: { label: 'Failed', color: '#ef4444' },
}

/**
 * Plain-English explainer for a single extraction optimization trial. Opened by
 * tapping a trial row. Answers: what this trial tried, how well it extracted,
 * and what each engine setting it used means and why it matters.
 */
export function ExtractionTrialExplainerModal({ trial, onClose }: Props) {
  useEffect(() => {
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
  const params = explainExtractionParameters(trial.config)
  const whatItTried = describeExtractionTrialPlainly(trial.config)
  const outcome = explainExtractionOutcome(trial)
  const badge = STATUS_BADGE[trial.status] ?? { label: trial.status, color: '#888' }
  const lift = trial.lift_vs_default
  const cf = trial.cross_field_summary

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
          background: '#1a1a1a',
          border: '1px solid #2e2e2e',
          borderRadius: 10,
          display: 'flex', flexDirection: 'column',
          fontFamily: 'inherit',
        }}
      >
        {/* Header */}
        <header style={{
          padding: '14px 18px',
          borderBottom: '1px solid #2e2e2e',
          display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <span style={{
              width: 9, height: 9, borderRadius: '50%', flexShrink: 0,
              backgroundColor: scoreColor(score),
            }} />
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: '#fff' }}>
                Trial details
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 3 }}>
                <span style={{ fontSize: 18, fontWeight: 700, color: '#e5e5e5' }}>
                  {scorePct}%
                </span>
                {lift != null && (
                  <span style={{
                    fontSize: 11, fontWeight: 600,
                    color: lift > 0 ? '#22c55e' : lift < 0 ? '#ef4444' : '#888',
                  }}>
                    {lift > 0 ? '+' : ''}{Math.round(lift * 100)} pts vs current
                  </span>
                )}
                <span style={{
                  fontSize: 10, fontWeight: 600, color: badge.color,
                  border: `1px solid ${badge.color}55`, borderRadius: 999,
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
              background: 'transparent', border: 'none', color: '#888',
              cursor: 'pointer', padding: 4, flexShrink: 0,
            }}
          >
            <X size={16} />
          </button>
        </header>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '14px 18px 18px' }}>
          {/* What it tried */}
          <Section title="What this trial tried">
            <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.6, color: '#cfcfcf' }}>
              {whatItTried}
            </p>
            <p style={{ margin: '8px 0 0', fontSize: 12, lineHeight: 1.6, color: '#9a9a9a' }}>
              {outcome}
            </p>
            {trial.error && (
              <p style={{
                margin: '10px 0 0', fontSize: 12, lineHeight: 1.55, color: '#ef4444',
                background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)',
                borderRadius: 6, padding: '8px 10px',
              }}>
                {trial.error}
              </p>
            )}
          </Section>

          {/* Settings used */}
          <Section title="Settings it used, and why they matter">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {params.map((p) => (
                <div key={p.key} style={{
                  display: 'grid', gridTemplateColumns: '140px 1fr', gap: 10,
                  alignItems: 'baseline',
                }}>
                  <div style={{ fontSize: 12, color: '#888' }}>{p.label}</div>
                  <div>
                    <div style={{ fontSize: 12.5, fontWeight: 600, color: '#e9e9e9' }}>
                      {p.value}
                    </div>
                    <div style={{ fontSize: 11.5, lineHeight: 1.55, color: '#8f8f8f', marginTop: 2 }}>
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
              <Stat label="Overall score" value={`${scorePct}%`} />
              {trial.accuracy != null && (
                <Stat label="Accuracy" value={`${Math.round(trial.accuracy * 100)}%`} />
              )}
              {trial.consistency != null && (
                <Stat label="Consistency" value={`${Math.round(trial.consistency * 100)}%`} />
              )}
              {cf && (cf.pass + cf.fail) > 0 && (
                <Stat label="Cross-field rules" value={`${cf.pass}/${cf.pass + cf.fail} pass`} />
              )}
              {typeof trial.duration_seconds === 'number' && (
                <Stat label="Time" value={`${trial.duration_seconds.toFixed(1)}s`} />
              )}
              {typeof trial.tokens_used === 'number' && trial.tokens_used > 0 && (
                <Stat label="Tokens used" value={trial.tokens_used.toLocaleString()} />
              )}
            </div>
            <p style={{ margin: '10px 0 0', fontSize: 11.5, lineHeight: 1.55, color: '#8f8f8f' }}>
              <strong style={{ color: '#bdbdbd' }}>Accuracy</strong> is how often the extracted
              value matched the expected answer; <strong style={{ color: '#bdbdbd' }}>consistency</strong> is
              how often repeated runs produced the same value.
              {cf && (cf.pass + cf.fail) > 0 && (
                <> <strong style={{ color: '#bdbdbd' }}>Cross-field rules</strong> are checks that
                span more than one field (e.g. amounts that should add up).</>
              )}
            </p>
          </Section>
        </div>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: 18 }}>
      <h3 style={{
        margin: '0 0 8px', fontSize: 11, fontWeight: 600,
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
      padding: '5px 10px',
      background: 'rgba(255,255,255,0.03)', border: '1px solid #2a2a2a',
      borderRadius: 6,
    }}>
      <span style={{ fontSize: 9.5, color: '#777', textTransform: 'uppercase', letterSpacing: 0.3 }}>
        {label}
      </span>
      <span style={{ fontSize: 13, fontWeight: 600, color: '#e9e9e9', fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </span>
    </span>
  )
}
