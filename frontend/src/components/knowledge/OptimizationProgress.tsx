import { Loader2, X, Sparkles, Target } from 'lucide-react'
import type { KBOptimizationRun } from '../../api/knowledge'

interface Props {
  run: KBOptimizationRun
  onCancel: () => void
  cancelling: boolean
}

export function OptimizationProgress({ run, onCancel, cancelling }: Props) {
  const trialPct = run.total_trials_planned > 0
    ? (run.current_trial_index / run.total_trials_planned) * 100
    : 0
  const tokenPct = run.token_budget > 0
    ? (run.tokens_used / run.token_budget) * 100
    : 0

  return (
    <div style={{
      padding: 16, background: 'linear-gradient(135deg, #1a1f2e 0%, #1f1f1f 100%)',
      border: '1px solid rgba(124, 58, 237, 0.3)', borderRadius: 8,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <Loader2 size={16} style={{ color: '#a78bfa', animation: 'spin 1s linear infinite' }} />
        <span style={{ fontSize: 14, fontWeight: 600, color: '#fff' }}>
          {run.status === 'queued' ? 'Optimization queued' : 'Optimization running'}
        </span>
        <span style={{
          marginLeft: 'auto', fontSize: 10, fontWeight: 600,
          padding: '2px 8px', borderRadius: 8,
          color: '#a78bfa', backgroundColor: 'rgba(124, 58, 237, 0.15)',
        }}>
          {run.phase}
        </span>
      </div>

      {/* Progress message */}
      <div style={{
        padding: '10px 12px', marginBottom: 12,
        backgroundColor: 'rgba(0,0,0,0.25)', borderRadius: 6,
        fontSize: 12, color: '#ddd', minHeight: 20,
      }}>
        {run.progress_message || 'Initializing…'}
      </div>

      {/* Progress bars */}
      {run.total_trials_planned > 0 && (
        <ProgressRow
          label="Trials"
          subtitle={`${run.current_trial_index} of ${run.total_trials_planned}`}
          pct={trialPct}
          color="#a78bfa"
        />
      )}
      <ProgressRow
        label="Token budget"
        subtitle={`${formatTokens(run.tokens_used)} / ${formatTokens(run.token_budget)}`}
        pct={tokenPct}
        color={tokenPct > 90 ? '#f59e0b' : '#3b82f6'}
      />

      {/* No-KB target (score to beat) — shown as soon as phase 1 completes */}
      {run.baseline_no_kb_score != null && (
        <div style={{
          marginTop: 12, padding: '10px 12px',
          display: 'flex', alignItems: 'center', gap: 10,
          backgroundColor: 'rgba(245, 158, 11, 0.08)',
          border: '1px solid rgba(245, 158, 11, 0.25)', borderRadius: 6,
        }}>
          <Target size={16} style={{ color: '#f59e0b', flexShrink: 0 }} />
          <div style={{ flex: 1 }}>
            <div style={{
              fontSize: 10, color: '#f59e0b', textTransform: 'uppercase', letterSpacing: 0.5,
              marginBottom: 2,
            }}>
              Score to beat (no-KB baseline)
            </div>
            <div style={{ fontSize: 11, color: '#aaa' }}>
              How well the model answers without retrieval — the KB needs to clear this bar.
            </div>
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#fff' }}>
            {(run.baseline_no_kb_score * 100).toFixed(0)}%
          </div>
        </div>
      )}

      {/* Best-so-far */}
      {run.best_score_so_far != null && (
        <div style={{
          marginTop: 12, padding: '10px 12px',
          backgroundColor: 'rgba(34, 197, 94, 0.08)',
          border: '1px solid rgba(34, 197, 94, 0.25)', borderRadius: 6,
        }}>
          <div style={{
            fontSize: 10, color: '#22c55e', textTransform: 'uppercase', letterSpacing: 0.5,
            marginBottom: 2,
          }}>
            <Sparkles size={10} style={{ display: 'inline', marginRight: 4 }} />
            Best so far
            {run.baseline_no_kb_score != null && (
              <span style={{ marginLeft: 8, color: '#888', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>
                {run.best_score_so_far > run.baseline_no_kb_score
                  ? `+${((run.best_score_so_far - run.baseline_no_kb_score) * 100).toFixed(0)}pp vs no-KB`
                  : `${((run.best_score_so_far - run.baseline_no_kb_score) * 100).toFixed(0)}pp vs no-KB`}
              </span>
            )}
          </div>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#fff' }}>
            {(run.best_score_so_far * 100).toFixed(0)}%
          </div>
          {run.best_config_so_far && (
            <div style={{ fontSize: 11, color: '#888', marginTop: 2 }}>
              {summariseConfig(run.best_config_so_far)}
            </div>
          )}
        </div>
      )}

      {/* Recent trials mini-list */}
      {run.trials.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 10, color: '#666', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>
            Recent trials
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            {run.trials.slice(-5).reverse().map(t => (
              <div key={t.trial_id} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '5px 8px', fontSize: 11, color: '#aaa',
                backgroundColor: 'rgba(0,0,0,0.2)', borderRadius: 4,
              }}>
                <span style={{
                  width: 6, height: 6, borderRadius: '50%',
                  backgroundColor: scoreColor(t.score),
                }} />
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {summariseConfig(t.config)}
                </span>
                <span style={{ fontWeight: 600, color: '#e5e5e5' }}>
                  {(t.score * 100).toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Cancel */}
      <div style={{ marginTop: 14, display: 'flex', justifyContent: 'flex-end' }}>
        <button
          onClick={onCancel}
          disabled={cancelling || run.cancel_requested}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            padding: '5px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
            color: run.cancel_requested ? '#666' : '#fca5a5',
            backgroundColor: 'transparent',
            border: '1px solid ' + (run.cancel_requested ? '#444' : 'rgba(239, 68, 68, 0.3)'),
            borderRadius: 5,
            cursor: cancelling || run.cancel_requested ? 'not-allowed' : 'pointer',
          }}
        >
          {cancelling ? <Loader2 size={11} style={{ animation: 'spin 1s linear infinite' }} /> : <X size={11} />}
          {run.cancel_requested ? 'Cancelling…' : cancelling ? 'Sending…' : 'Cancel'}
        </button>
      </div>
    </div>
  )
}

function ProgressRow({ label, subtitle, pct, color }: { label: string; subtitle: string; pct: number; color: string }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#888', marginBottom: 3 }}>
        <span>{label}</span>
        <span>{subtitle}</span>
      </div>
      <div style={{ height: 6, backgroundColor: '#2a2a2a', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{
          width: `${Math.min(100, Math.max(0, pct))}%`, height: '100%',
          backgroundColor: color, transition: 'width 0.3s',
        }} />
      </div>
    </div>
  )
}

function summariseConfig(c: { k: number; model: string | null; prompt_variant: string; query_rewriting: boolean; source_label_visibility: boolean }) {
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

function formatTokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`
  return String(n)
}
