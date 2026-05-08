import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, History, Loader2 } from 'lucide-react'
import {
  listKBOptimizationHistory,
  type KBOptimizationRunSummary,
  type OptimizationStatus,
} from '../../api/knowledge'

interface Props {
  kbUuid: string
  /** Run UUID to suppress from the list (typically the currently displayed run). */
  excludeRunUuid?: string
  /** Called when a past run is clicked. The parent can fetch the full payload. */
  onSelect?: (runUuid: string) => void
}

export function OptimizationHistoryPanel({ kbUuid, excludeRunUuid, onSelect }: Props) {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<KBOptimizationRunSummary[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
}: { run: KBOptimizationRunSummary; onSelect?: (runUuid: string) => void }) {
  const score = run.optimized_score
  const baseline = run.baseline_default_score
  const lift = score != null && baseline != null ? (score - baseline) * 100 : null

  return (
    <button
      onClick={() => onSelect?.(run.uuid)}
      disabled={!onSelect}
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '7px 10px', textAlign: 'left',
        background: '#1a1a1a', border: '1px solid #2a2a2a',
        borderRadius: 5, cursor: onSelect ? 'pointer' : 'default',
        fontFamily: 'inherit', color: '#e5e5e5',
      }}
      onMouseEnter={e => onSelect && (e.currentTarget.style.borderColor = '#3a3a3a')}
      onMouseLeave={e => onSelect && (e.currentTarget.style.borderColor = '#2a2a2a')}
    >
      <StatusDot status={run.status} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, color: '#ddd', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {run.started_at ? new Date(run.started_at).toLocaleString() : 'Unknown date'}
          <span style={{ color: '#666' }}> · {run.num_trials} trial{run.num_trials !== 1 ? 's' : ''}</span>
          {run.options?.apply_on_finish ? <span style={{ color: '#a78bfa' }}> · auto-applied</span> : null}
        </div>
        {run.error_message && run.status === 'failed' && (
          <div style={{
            fontSize: 10, color: '#fca5a5', overflow: 'hidden',
            textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 1,
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
  )
}

function StatusDot({ status }: { status: OptimizationStatus }) {
  const c =
    status === 'completed' ? '#22c55e' :
    status === 'cancelled' ? '#888' :
    status === 'failed' ? '#ef4444' :
    '#a78bfa'  // queued / running
  return (
    <span style={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: c, flexShrink: 0 }} />
  )
}

function scoreColor(s: number) {
  if (s >= 0.7) return '#22c55e'
  if (s >= 0.4) return '#f59e0b'
  return '#ef4444'
}
