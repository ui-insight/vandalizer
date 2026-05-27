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
      backgroundColor: '#1f1f1f',
      border: '1px solid #2e2e2e', borderRadius: 8,
      overflow: 'hidden',
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 8, width: '100%',
          padding: '10px 14px', background: 'transparent', border: 'none',
          fontFamily: 'inherit', cursor: 'pointer', color: '#e5e5e5',
          textAlign: 'left',
        }}
      >
        {open ? <ChevronDown size={14} style={{ color: '#888' }} /> : <ChevronRight size={14} style={{ color: '#888' }} />}
        <History size={14} style={{ color: '#888' }} />
        <span style={{ fontSize: 13, fontWeight: 600 }}>Previous runs</span>
        {items != null && (
          <span style={{ marginLeft: 'auto', fontSize: 11, color: '#666' }}>
            {filtered.length} {filtered.length === 1 ? 'run' : 'runs'}
          </span>
        )}
      </button>

      {open && (
        <div style={{ padding: '0 12px 12px 12px' }}>
          {loading && (
            <div style={{ textAlign: 'center', padding: 16, color: '#888' }}>
              <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
            </div>
          )}
          {error && (
            <div style={{ fontSize: 12, color: '#fca5a5', padding: 8 }}>{error}</div>
          )}
          {items != null && !loading && filtered.length === 0 && (
            <div style={{ fontSize: 12, color: '#888', padding: '12px 8px' }}>
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
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '7px 10px',
        background: '#1a1a1a', border: '1px solid #2a2a2a',
        borderRadius: 5,
      }}
    >
      <button
        onClick={() => onSelect?.(run.uuid)}
        disabled={!onSelect}
        style={{
          flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 8,
          background: 'transparent', border: 'none', padding: 0,
          cursor: onSelect ? 'pointer' : 'default',
          fontFamily: 'inherit', color: '#e5e5e5', textAlign: 'left',
        }}
      >
        <StatusDot status={run.status} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 12, color: '#ddd',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {run.started_at ? new Date(run.started_at).toLocaleString() : 'Unknown date'}
            <span style={{ color: '#666' }}> · {run.num_trials} trial{run.num_trials !== 1 ? 's' : ''}</span>
            {run.options?.apply_on_finish ? <span style={{ color: '#a78bfa' }}> · auto-applied</span> : null}
          </div>
          <div style={{
            fontSize: 10, color: '#666',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 1,
          }}>
            {run.judge_model && <>judge: {run.judge_model}</>}
            {run.judge_model && run.eval_set_size != null && ' · '}
            {run.eval_set_size != null && <>n={run.eval_set_size}</>}
            {(run.judge_model || run.eval_set_size != null) && run.judge_prompt_version && ' · '}
            {run.judge_prompt_version && <>prompt {run.judge_prompt_version.replace(/^kb-judge-/, '')}</>}
          </div>
          {run.error_message && run.status === 'failed' && (
            <div style={{
              fontSize: 10, color: '#fca5a5',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 1,
            }}>
              {run.error_message}
            </div>
          )}
        </div>
        {score != null && (
          <span style={{ fontSize: 12, fontWeight: 600, color: scoreColor(score), minWidth: 42, textAlign: 'right' }}>
            {(score * 100).toFixed(0)}%
          </span>
        )}
        {lift != null && (
          <span style={{
            fontSize: 10,
            color: lift > 0 ? '#22c55e' : lift < 0 ? '#ef4444' : '#666',
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
            padding: '4px 8px', fontSize: 10, fontWeight: 600, fontFamily: 'inherit',
            color: '#a78bfa', background: 'transparent',
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

