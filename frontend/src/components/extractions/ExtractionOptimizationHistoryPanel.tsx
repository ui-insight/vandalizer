/**
 * Collapsible list of past tuning runs for a SearchSet.
 *
 * Lazy-loads history on first open. Clicking a row notifies the parent so
 * it can fetch the full run document and flip into a read-only "viewing past
 * run" state. Uses the same neutral surfaces and semantic colors as the validation tools.
 */
import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, History, Loader2 } from 'lucide-react'
import {
  listExtractionOptimizationHistory,
  type ExtractionOptimizationRunSummary,
} from '../../api/extractions'
import { StatusDot } from '../shared/StatusDot'

interface Props {
  searchSetUuid: string
  /** Run UUID to suppress from the list (typically the currently displayed run). */
  excludeRunUuid?: string
  /** Called when a past run is clicked. Parent fetches the full payload. */
  onSelect?: (runUuid: string) => void
}

export function ExtractionOptimizationHistoryPanel({
  searchSetUuid, excludeRunUuid, onSelect,
}: Props) {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<ExtractionOptimizationRunSummary[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || items !== null) return
    setLoading(true)
    listExtractionOptimizationHistory(searchSetUuid, { limit: 20 })
      .then(out => setItems(out.items))
      .catch(e => setError((e as Error).message))
      .finally(() => setLoading(false))
  }, [open, items, searchSetUuid])

  // Reset cache when the SearchSet changes.
  useEffect(() => { setItems(null); setOpen(false) }, [searchSetUuid])

  const filtered = (items ?? []).filter(r => r.uuid !== excludeRunUuid)

  return (
    <div style={{
      backgroundColor: 'var(--workspace-surface)',
      border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-medium)',
      overflow: 'hidden',
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', width: '100%',
          padding: "var(--workspace-space-12) var(--workspace-space-16)", background: 'transparent', border: 'none',
          fontFamily: 'inherit', cursor: 'pointer', color: 'var(--workspace-text)',
          textAlign: 'left',
        }}
      >
        {open ? <ChevronDown size={14} style={{ color: 'var(--workspace-muted)' }} /> : <ChevronRight size={14} style={{ color: 'var(--workspace-muted)' }} />}
        <History size={14} style={{ color: 'var(--workspace-muted)' }} />
        <span style={{ fontSize: 'var(--workspace-font-control)', fontWeight: 600 }}>Previous runs</span>
        {items != null && (
          <span style={{ marginLeft: 'auto', fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
            {filtered.length} {filtered.length === 1 ? 'run' : 'runs'}
          </span>
        )}
      </button>

      {open && (
        <div style={{ padding: "0 var(--workspace-space-12) var(--workspace-space-12) var(--workspace-space-12)" }}>
          {loading && (
            <div style={{ textAlign: 'center', padding: 'var(--workspace-space-16)', color: 'var(--workspace-muted)' }}>
              <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
            </div>
          )}
          {error && (
            <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-danger)', padding: 'var(--workspace-space-8)' }}>{error}</div>
          )}
          {items != null && !loading && filtered.length === 0 && (
            <div style={{ padding: "var(--workspace-space-12) var(--workspace-space-8)" }}>
              <div style={{ fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-text)', fontWeight: 600, marginBottom: 'var(--workspace-space-6)' }}>
                No prior tuning runs for this extraction
              </div>
              <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', lineHeight: 1.55 }}>
                Each run scores your extraction against test cases and lands here, so
                you can see whether model or strategy changes are actually helping.
                A run takes <b style={{ color: 'var(--workspace-muted)' }}>5–15 minutes</b> for small
                extractions and <b style={{ color: 'var(--workspace-muted)' }}>up to 60–90 minutes</b> for
                large ones (it keeps running on the server if you close the tab), and uses
                about <b style={{ color: 'var(--workspace-muted)' }}>$1–$5</b> worth of LLM tokens
                (an estimate of AI usage, not a charge to you) — nothing changes
                until you click Apply on a recipe.
              </div>
            </div>
          )}
          {items != null && filtered.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-4)' }}>
              {filtered.map(run => (
                <HistoryRow key={run.uuid} run={run} onSelect={onSelect} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function HistoryRow({
  run, onSelect,
}: { run: ExtractionOptimizationRunSummary; onSelect?: (runUuid: string) => void }) {
  const score = run.optimized_score
  const baseline = run.baseline_default_score
  const lift = score != null && baseline != null ? (score - baseline) * 100 : null

  return (
    <button
      onClick={() => onSelect?.(run.uuid)}
      disabled={!onSelect}
      style={{
        display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)',
        padding: "7px var(--workspace-space-12)", textAlign: 'left',
        background: 'var(--workspace-canvas)', border: '1px solid var(--workspace-border)',
        borderRadius: 'var(--workspace-radius-small)', cursor: onSelect ? 'pointer' : 'default',
        fontFamily: 'inherit', color: 'var(--workspace-text)',
      }}
      onMouseEnter={e => onSelect && (e.currentTarget.style.borderColor = 'var(--workspace-accent-ink)')}
      onMouseLeave={e => onSelect && (e.currentTarget.style.borderColor = 'var(--workspace-border)')}
    >
      <StatusDot status={run.status} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-text)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {run.started_at ? new Date(run.started_at).toLocaleString() : 'Unknown date'}
          <span style={{ color: 'var(--workspace-muted)' }}> · {run.num_trials} trial{run.num_trials !== 1 ? 's' : ''}</span>
          {run.options?.apply_on_finish ? <span style={{ color: 'var(--workspace-info)' }}> · auto-applied</span> : null}
        </div>
        {run.judge_model && (
          <div style={{
            fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 1,
          }}>
            judge: {run.judge_model}
          </div>
        )}
        {run.error_message && run.status === 'failed' && (
          <div style={{
            fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-danger)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 1,
          }}>
            {run.error_message}
          </div>
        )}
      </div>
      {score != null && (
        <span style={{ fontSize: 'var(--workspace-font-meta)', fontWeight: 600, color: scoreColor(score), minWidth: 42, textAlign: 'right' }}>
          {(score * 100).toFixed(0)}%
        </span>
      )}
      {lift != null && (
        <span style={{
          fontSize: 'var(--workspace-font-meta)',
          color: lift > 0 ? 'var(--workspace-success)' : lift < 0 ? 'var(--workspace-danger)' : 'var(--workspace-muted)',
          minWidth: 50, textAlign: 'right',
        }}>
          {lift > 0 ? '+' : ''}{lift.toFixed(0)}pts
        </span>
      )}
    </button>
  )
}

function scoreColor(s: number) {
  if (s >= 0.7) return 'var(--workspace-success)'
  if (s >= 0.4) return 'var(--workspace-warning)'
  return 'var(--workspace-danger)'
}
