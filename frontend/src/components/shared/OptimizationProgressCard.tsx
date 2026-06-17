import { useEffect, useState } from 'react'
import { Loader2, X, Sparkles, Target, Clock } from 'lucide-react'
import { ProgressRow } from './ProgressRow'
import { scoreColor } from './TrialsTable'

/** Shape the card needs from a run. Caller maps domain types into this. */
export interface ProgressRunShape<TConfig> {
  status: string
  phase: string
  progress_message: string
  current_trial_index: number
  total_trials_planned: number
  token_budget: number
  tokens_used: number
  best_score_so_far: number | null
  best_config_so_far: TConfig | null
  trials: Array<{ trial_id: string; config: TConfig; score: number; status: string }>
  cancel_requested: boolean
  /** Server-set start timestamp (ISO). Drives the live elapsed-time readout. */
  started_at?: string | null
}

interface OptimizationProgressCardProps<TConfig> {
  run: ProgressRunShape<TConfig>
  /** Score the optimizer is trying to beat (no-tool / no-workflow / no-KB). Null = not yet measured. */
  scoreFloor: number | null
  /** Caller-supplied summary string for a config (domain-specific fields). */
  summariseConfig: (config: TConfig) => string
  onCancel: () => void
  cancelling: boolean
  /** Heading shown while running. Default "Optimization running". */
  runningLabel?: string
  /** Heading shown while queued. Default "Optimization queued". */
  queuedLabel?: string
  /** Label for the score-floor sub-card. Default "Score to beat (baseline)". */
  scoreFloorLabel?: string
  /** Description for the score-floor sub-card. Default explains the baseline concept. */
  scoreFloorDescription?: string
  /** Suffix on best-so-far lift readout. Default "vs baseline". */
  liftLabel?: string
  /** Heading on the token-spend progress bar. Default "Token budget". Set to
   *  e.g. "Judge spend" when the tracked tokens are only one slice of the
   *  total cost so users aren't misled into reading the bar as total spend. */
  tokensBarLabel?: string
}

export function OptimizationProgressCard<TConfig>({
  run, scoreFloor, summariseConfig, onCancel, cancelling,
  runningLabel = 'Optimization running',
  queuedLabel = 'Optimization queued',
  scoreFloorLabel = 'Score to beat (baseline)',
  scoreFloorDescription = 'How well the system performs without this optimization — the result needs to clear this bar.',
  liftLabel = 'vs baseline',
  tokensBarLabel = 'Token budget',
}: OptimizationProgressCardProps<TConfig>) {
  const trialPct = run.total_trials_planned > 0
    ? (run.current_trial_index / run.total_trials_planned) * 100
    : 0
  const tokenPct = run.token_budget > 0
    ? (run.tokens_used / run.token_budget) * 100
    : 0

  // Live elapsed time, anchored to the server-set started_at so it stays
  // accurate across UI reloads and polling lag (unlike a client-side
  // Date.now() captured when the panel happened to mount). Ticks once a
  // second while the run is active.
  const elapsedSeconds = useElapsedSeconds(run.started_at, run.status)

  return (
    <div style={{
      padding: 16, background: 'linear-gradient(135deg, #1a1f2e 0%, #1f1f1f 100%)',
      border: '1px solid rgba(124, 58, 237, 0.3)', borderRadius: 8,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <Loader2 size={16} style={{ color: '#a78bfa', animation: 'spin 1s linear infinite' }} />
        <span style={{ fontSize: 14, fontWeight: 600, color: '#fff' }}>
          {run.status === 'queued' ? queuedLabel : runningLabel}
        </span>
        {elapsedSeconds != null && (
          <span style={{
            marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 4,
            fontSize: 11, color: '#9ca3af', fontVariantNumeric: 'tabular-nums',
          }}>
            <Clock size={11} style={{ color: '#6b7280' }} />
            {formatElapsed(elapsedSeconds)}
          </span>
        )}
        <span style={{
          marginLeft: elapsedSeconds != null ? 0 : 'auto', fontSize: 10, fontWeight: 600,
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
      {/* Tokens bar — only when a budget was set. Without a budget the bar
          carries no information (0 / 0) and the previous unconditional render
          implied an accounting that wasn't happening. */}
      {run.token_budget > 0 && (
        <ProgressRow
          label={tokensBarLabel}
          subtitle={`${formatTokens(run.tokens_used)} / ${formatTokens(run.token_budget)}`}
          pct={tokenPct}
          color={tokenPct > 90 ? '#f59e0b' : '#3b82f6'}
        />
      )}

      {/* Score floor (no-tool / no-KB / no-workflow baseline) */}
      {scoreFloor != null && (
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
              {scoreFloorLabel}
            </div>
            <div style={{ fontSize: 11, color: '#aaa' }}>
              {scoreFloorDescription}
            </div>
          </div>
          <div style={{ fontSize: 20, fontWeight: 700, color: '#fff' }}>
            {(scoreFloor * 100).toFixed(0)}%
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
            {scoreFloor != null && (
              <span style={{ marginLeft: 8, color: '#888', fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>
                {run.best_score_so_far > scoreFloor
                  ? `+${((run.best_score_so_far - scoreFloor) * 100).toFixed(0)}pp ${liftLabel}`
                  : `${((run.best_score_so_far - scoreFloor) * 100).toFixed(0)}pp ${liftLabel}`}
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

function formatTokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}k`
  return String(n)
}

function formatElapsed(seconds: number) {
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

/**
 * Seconds elapsed since `startedAt`, re-rendering once a second while the run
 * is queued/running. Returns null when there's no start timestamp yet or the
 * run is no longer active, so callers can omit the readout entirely.
 */
function useElapsedSeconds(startedAt: string | null | undefined, status: string): number | null {
  const active = status === 'queued' || status === 'running'
  const startMs = startedAt ? new Date(startedAt).getTime() : NaN
  const [elapsed, setElapsed] = useState<number>(() =>
    active && Number.isFinite(startMs) ? Math.max(0, Math.round((Date.now() - startMs) / 1000)) : 0,
  )

  useEffect(() => {
    if (!active || !Number.isFinite(startMs)) return
    const tick = () => setElapsed(Math.max(0, Math.round((Date.now() - startMs) / 1000)))
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [active, startMs])

  if (!active || !Number.isFinite(startMs)) return null
  return elapsed
}
