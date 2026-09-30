import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, History, Loader2, ArrowLeftRight } from 'lucide-react'
import {
  listKBOptimizationHistory,
  type KBOptimizationRunSummary,
} from '../../api/knowledge'
import { StatusDot } from '../shared/StatusDot'
import { scoreColor } from '../shared/TrialsTable'
import { CompareRunsView } from './CompareRunsView'

interface Props {
  kbUuid: string
  /** Run UUID to suppress from the list (typically the currently displayed run). */
  excludeRunUuid?: string
  /** Called when a past run is clicked. The parent can fetch the full payload. */
  onSelect?: (runUuid: string) => void
  /** When present, enables a "Compare" button on each row that diffs that run
   * against this one. Typically set to the same run that ``excludeRunUuid``
   * suppresses (the run the user is currently viewing). */
  compareAgainstRunUuid?: string
}

export function OptimizationHistoryPanel({
  kbUuid, excludeRunUuid, onSelect, compareAgainstRunUuid,
}: Props) {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<KBOptimizationRunSummary[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [compareWith, setCompareWith] = useState<string | null>(null)

  useEffect(() => {
    if (!open || items !== null) return
    setLoading(true)
    listKBOptimizationHistory(kbUuid, { limit: 20 })
      .then(out => setItems(out.items))
      .catch(e => setError((e as Error).message))
      .finally(() => setLoading(false))
  }, [open, items, kbUuid])

  // Reset cache when the KB changes.
  useEffect(() => { setItems(null); setOpen(false) }, [kbUuid])

  const filtered = (items ?? []).filter(r => r.uuid !== excludeRunUuid)

  return (
    <div style={{
      backgroundColor: 'var(--workspace-surface)',
      border: '1px solid var(--workspace-border)', borderRadius: 8,
      overflow: 'hidden',
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        style={{
          display: 'flex', alignItems: 'center', gap: 8, width: '100%',
          padding: '10px 14px', background: 'transparent', border: 'none',
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
        <div style={{ padding: '0 12px 12px 12px' }}>
          {loading && (
            <div style={{ textAlign: 'center', padding: 16, color: 'var(--workspace-muted)' }}>
              <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
            </div>
          )}
          {error && (
            <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-danger)', padding: 8 }}>{error}</div>
          )}
          {items != null && !loading && filtered.length === 0 && (
            <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', padding: '12px 8px' }}>
              No prior optimization runs for this KB.
            </div>
          )}
          {items != null && filtered.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {filtered.map(run => (
                <HistoryRow
                  key={run.uuid}
                  run={run}
                  onSelect={onSelect}
                  onCompare={compareAgainstRunUuid ? () => setCompareWith(run.uuid) : undefined}
                />
              ))}
            </div>
          )}
        </div>
      )}

      <CompareRunsView
        open={compareWith != null}
        kbUuid={kbUuid}
        currentRunUuid={compareAgainstRunUuid ?? null}
        otherRunUuid={compareWith}
        onClose={() => setCompareWith(null)}
      />
    </div>
  )
}

function HistoryRow({
  run, onSelect, onCompare,
}: {
  run: KBOptimizationRunSummary
  onSelect?: (runUuid: string) => void
  onCompare?: () => void
}) {
  const score = run.optimized_score
  const baseline = run.baseline_default_score
  const lift = score != null && baseline != null ? (score - baseline) * 100 : null

  return (
    <div
      style={{
        display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8,
        padding: '7px 10px',
        background: 'var(--workspace-canvas)', border: '1px solid var(--workspace-border)',
        borderRadius: 5,
      }}
    >
      <button
        onClick={() => onSelect?.(run.uuid)}
        disabled={!onSelect}
        style={{
          flex: '1 1 220px', minWidth: 0, display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, minHeight: 36,
          background: 'transparent', border: 'none', padding: 0,
          cursor: onSelect ? 'pointer' : 'default',
          fontFamily: 'inherit', color: 'var(--workspace-text)', textAlign: 'left',
        }}
      >
        <StatusDot status={run.status} />
        <div style={{ flex: '1 1 160px', minWidth: 0 }}>
          <div style={{
            fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-text)',
            overflowWrap: 'anywhere',
          }}>
            {run.started_at ? new Date(run.started_at).toLocaleString() : 'Unknown date'}
            <span style={{ color: 'var(--workspace-muted)' }}> · {run.num_trials} trial{run.num_trials !== 1 ? 's' : ''}</span>
            {run.options?.apply_on_finish ? <span style={{ color: 'var(--workspace-info)' }}> · auto-applied</span> : null}
          </div>
          <div style={{
            fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)',
            overflowWrap: 'anywhere', marginTop: 1,
          }}>
            {run.judge_model && <>judge: {run.judge_model}</>}
            {run.judge_model && run.eval_set_size != null && ' · '}
            {run.eval_set_size != null && <>n={run.eval_set_size}</>}
            {(run.judge_model || run.eval_set_size != null) && run.judge_prompt_version && ' · '}
            {run.judge_prompt_version && <>prompt {run.judge_prompt_version.replace(/^kb-judge-/, '')}</>}
          </div>
          {run.error_message && run.status === 'failed' && (
            <div style={{
              fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-danger)',
              overflowWrap: 'anywhere', marginTop: 1,
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
      {onCompare && run.status === 'completed' && (
        <button
          onClick={onCompare}
          title="Compare this run with the current one"
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 4,
            minHeight: 36, padding: '4px 8px', fontSize: 'var(--workspace-font-meta)', fontWeight: 600, fontFamily: 'inherit',
            color: 'var(--workspace-info)', background: 'transparent',
            border: '1px solid rgba(124, 58, 237, 0.3)', borderRadius: 4,
            cursor: 'pointer',
          }}
        >
          <ArrowLeftRight size={10} />
          Compare
        </button>
      )}
    </div>
  )
}

