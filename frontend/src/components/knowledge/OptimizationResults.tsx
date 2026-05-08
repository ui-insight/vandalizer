import { useState } from 'react'
import { CheckCircle2, AlertTriangle, AlertCircle, Info, RotateCcw, Sparkles, Loader2 } from 'lucide-react'
import type { KBOptimizationRun, OptimizationSuggestion, OptimizationTrial } from '../../api/knowledge'
import { OptimizationHistoryPanel } from './OptimizationHistoryPanel'

interface Props {
  run: KBOptimizationRun
  canManage: boolean
  onApply: () => void
  applying: boolean
  onRunAgain: () => void
  /** Optional click-through to view a different past run from the history list. */
  onSelectPastRun?: (runUuid: string) => void
}

export function OptimizationResults({ run, canManage, onApply, applying, onRunAgain, onSelectPastRun }: Props) {
  if (run.status === 'failed') {
    return (
      <FailedBanner
        message={run.error_message || 'Optimization failed.'}
        onRunAgain={onRunAgain}
      />
    )
  }
  if (run.status === 'cancelled') {
    return (
      <CancelledBanner
        completedTrials={run.trials.length}
        onRunAgain={onRunAgain}
      />
    )
  }

  const noKb = run.baseline_no_kb_score
  const defaultKb = run.baseline_default_score
  const optimized = run.optimized_score
  const variance = run.judge_variance ?? 0
  const ci = variance * 1.96  // 95% CI half-width

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* Comparison card */}
      <ComparisonCard
        noKb={noKb}
        defaultKb={defaultKb}
        optimized={optimized}
        ci={ci}
      />

      {/* Best config + Apply */}
      {run.best_config && (
        <BestConfigCard
          config={run.best_config}
          isAlreadyApplied={!!run.options?.apply_on_finish}
          canManage={canManage}
          onApply={onApply}
          applying={applying}
        />
      )}

      {/* Suggestions */}
      {run.data_source_suggestions.length > 0 && (
        <SuggestionsList suggestions={run.data_source_suggestions} />
      )}

      {/* Trials table */}
      {run.trials.length > 0 && (
        <TrialsTable trials={run.trials} />
      )}

      {/* Past runs */}
      <OptimizationHistoryPanel
        kbUuid={run.kb_uuid}
        excludeRunUuid={run.uuid}
        onSelect={onSelectPastRun}
      />

      {/* Re-run */}
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <button
          onClick={onRunAgain}
          disabled={!canManage}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
            color: canManage ? '#a78bfa' : '#555',
            background: 'transparent',
            border: '1px solid ' + (canManage ? 'rgba(124, 58, 237, 0.3)' : '#333'),
            borderRadius: 6, cursor: canManage ? 'pointer' : 'not-allowed',
          }}
        >
          <RotateCcw size={12} />
          Re-run
        </button>
      </div>
    </div>
  )
}

function ComparisonCard({
  noKb, defaultKb, optimized, ci,
}: { noKb: number | null; defaultKb: number | null; optimized: number | null; ci: number }) {
  const noKbPct = (noKb ?? 0) * 100
  const defaultPct = (defaultKb ?? 0) * 100
  const optimizedPct = (optimized ?? 0) * 100
  const liftVsDefault = optimized != null && defaultKb != null ? (optimized - defaultKb) * 100 : null
  const liftVsNoKb = optimized != null && noKb != null ? (optimized - noKb) * 100 : null
  const liftSignificant = liftVsDefault != null && Math.abs(liftVsDefault / 100) > 2 * ci

  return (
    <div style={{
      padding: 16, backgroundColor: '#1f1f1f',
      border: '1px solid #2e2e2e', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <CheckCircle2 size={16} style={{ color: '#22c55e' }} />
        <h3 style={{ margin: 0, fontSize: 14, color: '#fff' }}>Optimization complete</h3>
        {ci > 0 && (
          <span style={{ marginLeft: 'auto', fontSize: 10, color: '#666' }}>
            95% CI: ±{(ci * 100).toFixed(1)}pts
          </span>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <BarRow label="No KB" pct={noKbPct} color="#888" />
        <BarRow label="Default" pct={defaultPct} color="#3b82f6" />
        <BarRow label="Optimized" pct={optimizedPct} color="#22c55e" emphasised />
      </div>

      {liftVsDefault != null && (
        <div style={{
          marginTop: 14, padding: '10px 12px',
          backgroundColor: liftVsDefault > 0 ? 'rgba(34, 197, 94, 0.08)' : 'rgba(239, 68, 68, 0.08)',
          border: '1px solid ' + (liftVsDefault > 0 ? 'rgba(34, 197, 94, 0.25)' : 'rgba(239, 68, 68, 0.25)'),
          borderRadius: 6,
        }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
            <span style={{
              fontSize: 18, fontWeight: 700,
              color: liftVsDefault > 0 ? '#22c55e' : '#ef4444',
            }}>
              {liftVsDefault > 0 ? '+' : ''}{liftVsDefault.toFixed(0)}pts
            </span>
            <span style={{ fontSize: 12, color: '#aaa' }}>over default settings</span>
            {liftVsNoKb != null && (
              <>
                <span style={{ fontSize: 12, color: '#666' }}>·</span>
                <span style={{ fontSize: 12, color: '#aaa' }}>
                  +{liftVsNoKb.toFixed(0)}pts over no-KB baseline
                </span>
              </>
            )}
          </div>
          {!liftSignificant && Math.abs(liftVsDefault) < 5 && (
            <div style={{ marginTop: 6, fontSize: 11, color: '#f59e0b' }}>
              ⚠ Improvement is within judge noise — consider this "no significant change."
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function BarRow({ label, pct, color, emphasised = false }: { label: string; pct: number; color: string; emphasised?: boolean }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{
        width: 80, fontSize: 12, fontWeight: emphasised ? 600 : 400,
        color: emphasised ? '#fff' : '#aaa',
      }}>
        {label}
      </div>
      <div style={{ flex: 1, height: 12, backgroundColor: '#1a1a1a', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ width: `${Math.max(0, Math.min(100, pct))}%`, height: '100%', backgroundColor: color }} />
      </div>
      <div style={{
        width: 50, textAlign: 'right',
        fontSize: emphasised ? 16 : 13, fontWeight: emphasised ? 700 : 600,
        color: emphasised ? color : '#ddd',
      }}>
        {pct.toFixed(0)}%
      </div>
    </div>
  )
}

function BestConfigCard({
  config, isAlreadyApplied, canManage, onApply, applying,
}: { config: OptimizationTrial['config']; isAlreadyApplied: boolean; canManage: boolean; onApply: () => void; applying: boolean }) {
  const rows: { label: string; value: string }[] = [
    { label: 'Top-k chunks', value: String(config.k) },
    { label: 'Model', value: config.model || 'default' },
    { label: 'Prompt variant', value: config.prompt_variant },
    { label: 'Query rewriting', value: config.query_rewriting ? 'on' : 'off' },
    { label: 'Source labels in context', value: config.source_label_visibility ? 'visible' : 'hidden' },
  ]
  return (
    <div style={{
      padding: 14, backgroundColor: '#1f1f1f',
      border: '1px solid #2e2e2e', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <Sparkles size={14} style={{ color: '#a78bfa' }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>Best configuration</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        {rows.map(r => (
          <div key={r.label} style={{
            padding: '6px 10px', backgroundColor: '#262626', borderRadius: 4,
          }}>
            <div style={{ fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5 }}>{r.label}</div>
            <div style={{ fontSize: 12, color: '#e5e5e5', marginTop: 2 }}>{r.value}</div>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
        <button
          onClick={onApply}
          disabled={!canManage || applying}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
            color: !canManage ? '#555' : '#fff',
            background: !canManage ? '#222' : 'linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)',
            border: '1px solid ' + (!canManage ? '#333' : '#7c3aed'),
            borderRadius: 6, cursor: !canManage || applying ? 'not-allowed' : 'pointer',
          }}
        >
          {applying ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Sparkles size={12} />}
          {applying ? 'Applying…' : isAlreadyApplied ? 'Apply again' : 'Apply optimized settings'}
        </button>
        {isAlreadyApplied && (
          <span style={{ fontSize: 11, color: '#22c55e' }}>
            ✓ Already applied automatically
          </span>
        )}
      </div>
    </div>
  )
}

function SuggestionsList({ suggestions }: { suggestions: OptimizationSuggestion[] }) {
  return (
    <div style={{
      padding: 14, backgroundColor: '#1f1f1f',
      border: '1px solid #2e2e2e', borderRadius: 8,
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#fff', marginBottom: 10 }}>
        Data-source suggestions
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {suggestions.map((s, i) => {
          const Icon =
            s.severity === 'critical' ? AlertCircle :
            s.severity === 'warning' ? AlertTriangle : Info
          const color =
            s.severity === 'critical' ? '#ef4444' :
            s.severity === 'warning' ? '#f59e0b' : '#3b82f6'
          return (
            <div
              key={i}
              style={{
                display: 'flex', alignItems: 'flex-start', gap: 8,
                padding: '8px 10px',
                backgroundColor: `${color}0e`,
                border: `1px solid ${color}33`,
                borderRadius: 6,
              }}
            >
              <Icon size={13} style={{ color, flexShrink: 0, marginTop: 2 }} />
              <div style={{ fontSize: 12, color: '#ddd', lineHeight: 1.5 }}>
                {s.message}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function TrialsTable({ trials }: { trials: OptimizationTrial[] }) {
  const [sortBy, setSortBy] = useState<'score' | 'lift' | 'duration'>('score')
  const sorted = [...trials].sort((a, b) => {
    if (sortBy === 'score') return b.score - a.score
    if (sortBy === 'lift') return (b.lift_vs_default ?? 0) - (a.lift_vs_default ?? 0)
    return (b.duration_seconds ?? 0) - (a.duration_seconds ?? 0)
  })

  return (
    <div style={{
      padding: 14, backgroundColor: '#1f1f1f',
      border: '1px solid #2e2e2e', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>
          Trials ({trials.length})
        </span>
        <span style={{ marginLeft: 'auto', fontSize: 10, color: '#666' }}>Sort by:</span>
        <select
          value={sortBy}
          onChange={e => setSortBy(e.target.value as 'score' | 'lift' | 'duration')}
          style={{
            background: '#1a1a1a', color: '#e5e5e5', border: '1px solid #333',
            borderRadius: 4, padding: '2px 6px', fontSize: 11, fontFamily: 'inherit',
          }}
        >
          <option value="score">Score</option>
          <option value="lift">Lift</option>
          <option value="duration">Duration</option>
        </select>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 320, overflowY: 'auto' }}>
        {sorted.map(t => (
          <div key={t.trial_id} style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '6px 10px', fontSize: 11, color: '#ddd',
            backgroundColor: t.status === 'failed' ? 'rgba(239, 68, 68, 0.05)' : 'rgba(0,0,0,0.2)',
            borderRadius: 4,
          }}>
            <span style={{
              width: 6, height: 6, borderRadius: '50%',
              backgroundColor: scoreColor(t.score),
            }} />
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#aaa' }}>
              {summariseConfig(t.config)}
            </span>
            {t.lift_vs_default != null && (
              <span style={{
                fontSize: 10,
                color: t.lift_vs_default > 0 ? '#22c55e' : t.lift_vs_default < 0 ? '#ef4444' : '#666',
              }}>
                {t.lift_vs_default > 0 ? '+' : ''}{(t.lift_vs_default * 100).toFixed(0)}pts
              </span>
            )}
            <span style={{ width: 50, textAlign: 'right', fontWeight: 600, color: '#e5e5e5' }}>
              {(t.score * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function FailedBanner({ message, onRunAgain }: { message: string; onRunAgain: () => void }) {
  return (
    <div style={{
      padding: 14, backgroundColor: 'rgba(239, 68, 68, 0.08)',
      border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <AlertCircle size={16} style={{ color: '#ef4444' }} />
        <span style={{ fontSize: 14, fontWeight: 600, color: '#fff' }}>Optimization failed</span>
      </div>
      <div style={{ fontSize: 12, color: '#fca5a5', marginBottom: 10 }}>{message}</div>
      <button onClick={onRunAgain} style={{
        padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
        color: '#fff', backgroundColor: '#7c3aed',
        border: '1px solid #7c3aed', borderRadius: 6, cursor: 'pointer',
      }}>
        Try again
      </button>
    </div>
  )
}

function CancelledBanner({ completedTrials, onRunAgain }: { completedTrials: number; onRunAgain: () => void }) {
  return (
    <div style={{
      padding: 14, backgroundColor: '#1f1f1f',
      border: '1px solid #333', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <Info size={16} style={{ color: '#888' }} />
        <span style={{ fontSize: 14, fontWeight: 600, color: '#fff' }}>Optimization cancelled</span>
      </div>
      <div style={{ fontSize: 12, color: '#aaa', marginBottom: 10 }}>
        {completedTrials} trial{completedTrials !== 1 ? 's' : ''} completed before you cancelled.
      </div>
      <button onClick={onRunAgain} style={{
        padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
        color: '#fff', backgroundColor: '#7c3aed',
        border: '1px solid #7c3aed', borderRadius: 6, cursor: 'pointer',
      }}>
        Run again
      </button>
    </div>
  )
}

function summariseConfig(c: OptimizationTrial['config']) {
  const bits = [`k=${c.k}`]
  if (c.model) bits.push(c.model)
  if (c.prompt_variant && c.prompt_variant !== 'default') bits.push(c.prompt_variant)
  if (c.query_rewriting) bits.push('query-rewrite')
  if (c.source_label_visibility === false) bits.push('no-source-labels')
  return bits.join(' · ')
}

function scoreColor(s: number) {
  if (s >= 0.7) return '#22c55e'
  if (s >= 0.4) return '#f59e0b'
  return '#ef4444'
}
