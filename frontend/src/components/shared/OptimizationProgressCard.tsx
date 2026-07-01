import { useEffect, useRef, useState } from 'react'
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
  /** Server-set start timestamp (ISO). Fallback anchor for the elapsed readout. */
  started_at?: string | null
  /** Server-computed elapsed seconds (started_at → completed_at|now). Preferred
   *  anchor for the live timer — see `useElapsedSeconds`. */
  elapsed_seconds?: number | null
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

  // Live elapsed time, anchored to the server-computed elapsed so it stays
  // accurate across UI reloads and polling lag, and — unlike the old
  // Date.now() − started_at math — immune to client/server clock skew. Ticks
  // once a second while the run is active.
  const elapsedSeconds = useElapsedSeconds(run.elapsed_seconds, run.started_at, run.status)

  return (
    <div role="status" aria-live="polite" style={{
      padding: 16, background: 'linear-gradient(135deg, #1a1f2e 0%, #1f1f1f 100%)',
      border: '1px solid rgba(124, 58, 237, 0.3)', borderRadius: 8,
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <Loader2 size={16} aria-hidden="true" style={{ color: '#a78bfa', animation: 'spin 1s linear infinite' }} />
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
          {cancelling ? <Loader2 size={11} aria-hidden="true" style={{ animation: 'spin 1s linear infinite' }} /> : <X size={11} aria-hidden="true" />}
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
 * Epoch ms for a server timestamp, treating timezone-less ISO strings as UTC.
 *
 * Datetimes read back from Mongo can serialize without an offset (the Motor
 * client isn't tz_aware). Left as-is, the browser parses such a string as
 * *local* time, which for users west of UTC puts the start in the future and
 * pins elapsed at 0s. Forcing UTC when no offset is present keeps the readout
 * correct even if a backend serializer slips — the failure mode that kept the
 * workflow tuning elapsed-time readout broken across earlier fixes.
 */
export function parseServerTimeMs(ts: string): number {
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(ts)
  return new Date(hasTz ? ts : ts + 'Z').getTime()
}

/**
 * Project a server-reported elapsed base forward by however long the client
 * has held it. `baseSeconds` was the elapsed at `anchoredAtMs` (a client
 * Date.now()); we add only the *client-clock delta* since then.
 *
 * Crucially this never compares the client clock to a server-derived absolute
 * timestamp, so client/server clock skew can't leak in: when nowMs equals
 * anchoredAtMs the result is exactly `baseSeconds`, whatever the skew. The old
 * `Date.now() − started_at` math instead surfaced the full skew as a sudden
 * jump (e.g. to ~3m30s on a drifted Docker-VM backend) the instant polling
 * replaced the optimistic client-side seed.
 */
export function projectElapsedSeconds(baseSeconds: number, anchoredAtMs: number, nowMs: number): number {
  return Math.max(0, baseSeconds) + Math.max(0, Math.round((nowMs - anchoredAtMs) / 1000))
}

/**
 * Seconds elapsed for an active run, re-rendering once a second. Prefers the
 * server-computed `elapsedSecondsBase` (skew-immune; see
 * `projectElapsedSeconds`) and falls back to the parsed `startedAt` delta for
 * payloads that predate the field. Returns null when there's no usable anchor
 * or the run is no longer active, so callers can omit the readout entirely.
 */
function useElapsedSeconds(
  elapsedSecondsBase: number | null | undefined,
  startedAt: string | null | undefined,
  status: string,
): number | null {
  const active = status === 'queued' || status === 'running'
  const serverBase =
    typeof elapsedSecondsBase === 'number' && Number.isFinite(elapsedSecondsBase)
      ? elapsedSecondsBase
      : null
  const startMs = startedAt ? parseServerTimeMs(startedAt) : NaN
  const hasAnchor = serverBase !== null || Number.isFinite(startMs)

  // Pin the server base to the client instant we received it, so the ticker
  // only ever adds client-clock deltas. Re-anchors whenever the polled base
  // changes. Mutating a ref during render is safe here — it's an idempotent
  // cache keyed on the current `serverBase`.
  const anchor = useRef<{ base: number; at: number } | null>(null)
  if (serverBase === null) {
    anchor.current = null
  } else if (!anchor.current || anchor.current.base !== serverBase) {
    anchor.current = { base: serverBase, at: Date.now() }
  }

  const compute = () => {
    if (anchor.current) return projectElapsedSeconds(anchor.current.base, anchor.current.at, Date.now())
    if (Number.isFinite(startMs)) return Math.max(0, Math.round((Date.now() - startMs) / 1000))
    return 0
  }

  const [elapsed, setElapsed] = useState<number>(() => (active && hasAnchor ? compute() : 0))

  useEffect(() => {
    if (!active || !hasAnchor) return
    const tick = () => setElapsed(compute())
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
    // `serverBase` re-anchors the ref above; `startMs` is the fallback anchor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, hasAnchor, serverBase, startMs])

  if (!active || !hasAnchor) return null
  return elapsed
}
