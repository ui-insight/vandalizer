import { useCallback, useEffect, useState } from 'react'
import { CheckCircle, XCircle, Loader2, Clock, FileText, ChevronDown, ChevronRight, Zap } from 'lucide-react'
import { relativeTime } from '../../utils/time'

export interface HistoryRun {
  id: string
  status: string
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  error: string
  tokens_input: number
  tokens_output: number
  documents_touched: number
  steps_completed?: number
  steps_total?: number
  session_id?: string
  result_snapshot: Record<string, unknown>
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  const secs = ms / 1000
  if (secs < 60) return `${secs.toFixed(1)}s`
  const mins = Math.floor(secs / 60)
  const remSecs = Math.round(secs % 60)
  return `${mins}m ${remSecs}s`
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'completed') return <CheckCircle style={{ width: 14, height: 14, color: '#16a34a', flexShrink: 0 }} />
  if (status === 'failed' || status === 'error') return <XCircle style={{ width: 14, height: 14, color: '#dc2626', flexShrink: 0 }} />
  if (status === 'running' || status === 'queued') return <Loader2 style={{ width: 14, height: 14, color: '#2563eb', flexShrink: 0, animation: 'spin 1s linear infinite' }} />
  return <Clock style={{ width: 14, height: 14, color: '#9ca3af', flexShrink: 0 }} />
}

function ResultPreview({ snapshot, type }: { snapshot: Record<string, unknown>; type: 'workflow' | 'extraction' }) {
  if (!snapshot || Object.keys(snapshot).length === 0) return null

  if (type === 'extraction') {
    const normalized = snapshot.normalized as Record<string, unknown> | undefined
    if (!normalized || Object.keys(normalized).length === 0) return null
    const entries = Object.entries(normalized)
    return (
      <div style={{ marginTop: 8, fontSize: 12, color: '#374151' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <tbody>
            {entries.map(([key, val]) => (
              <tr key={key}>
                <td style={{ padding: '3px 8px 3px 0', color: '#6b7280', fontWeight: 500, verticalAlign: 'top', whiteSpace: 'nowrap' }}>{key}</td>
                <td style={{ padding: '3px 0', wordBreak: 'break-word' }}>{val != null ? String(val) : <span style={{ color: '#d1d5db' }}>--</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  // Workflow: just show a summary of what's in the snapshot
  const keys = Object.keys(snapshot)
  if (keys.length === 0) return null
  return (
    <div style={{ marginTop: 8, fontSize: 12, color: '#6b7280' }}>
      {keys.length} result field{keys.length !== 1 ? 's' : ''}
    </div>
  )
}

function RunRow({ run, type }: { run: HistoryRun; type: 'workflow' | 'extraction' }) {
  const [expanded, setExpanded] = useState(false)
  const hasResults = run.result_snapshot && Object.keys(run.result_snapshot).length > 0

  return (
    <div style={{
      borderBottom: '1px solid #f3f4f6',
    }}>
      <button
        onClick={() => hasResults && setExpanded(e => !e)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '12px 24px',
          background: 'none',
          border: 'none',
          cursor: hasResults ? 'pointer' : 'default',
          fontFamily: 'inherit',
          textAlign: 'left',
        }}
      >
        <StatusIcon status={run.status} />

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 500, color: '#202124' }}>
              {run.started_at ? relativeTime(run.started_at) : 'Unknown'}
            </span>
            <span style={{
              fontSize: 11,
              fontWeight: 500,
              padding: '1px 6px',
              borderRadius: 4,
              backgroundColor: run.status === 'completed' ? '#dcfce7' : run.status === 'failed' || run.status === 'error' ? '#fef2f2' : '#f3f4f6',
              color: run.status === 'completed' ? '#166534' : run.status === 'failed' || run.status === 'error' ? '#991b1b' : '#6b7280',
            }}>
              {run.status}
            </span>
          </div>

          <div style={{ display: 'flex', gap: 12, marginTop: 4, fontSize: 11, color: '#9ca3af' }}>
            {run.duration_ms != null && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <Clock style={{ width: 11, height: 11 }} />
                {formatDuration(run.duration_ms)}
              </span>
            )}
            {run.documents_touched > 0 && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <FileText style={{ width: 11, height: 11 }} />
                {run.documents_touched} doc{run.documents_touched !== 1 ? 's' : ''}
              </span>
            )}
            {type === 'workflow' && run.steps_total != null && run.steps_total > 0 && (
              <span>
                {run.steps_completed ?? 0}/{run.steps_total} steps
              </span>
            )}
            {(run.tokens_input > 0 || run.tokens_output > 0) && (
              <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                <Zap style={{ width: 11, height: 11 }} />
                {(run.tokens_input + run.tokens_output).toLocaleString()} tokens
              </span>
            )}
          </div>

          {run.error && (
            <div style={{ fontSize: 12, color: '#dc2626', marginTop: 4 }}>
              {run.error.length > 120 ? run.error.slice(0, 120) + '...' : run.error}
            </div>
          )}
        </div>

        {hasResults && (
          expanded
            ? <ChevronDown style={{ width: 14, height: 14, color: '#9ca3af', flexShrink: 0 }} />
            : <ChevronRight style={{ width: 14, height: 14, color: '#9ca3af', flexShrink: 0 }} />
        )}
      </button>

      {expanded && hasResults && (
        <div style={{ padding: '0 24px 12px 48px' }}>
          <ResultPreview snapshot={run.result_snapshot} type={type} />
        </div>
      )}
    </div>
  )
}

export function RunHistoryTab({
  fetchHistory,
  type,
}: {
  fetchHistory: () => Promise<{ runs: HistoryRun[] }>
  type: 'workflow' | 'extraction'
}) {
  const [runs, setRuns] = useState<HistoryRun[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchHistory()
      setRuns(data.runs)
    } catch {
      // silent
    } finally {
      setLoading(false)
    }
  }, [fetchHistory])

  useEffect(() => { load() }, [load])

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48, color: '#9ca3af' }}>
        <Loader2 style={{ width: 20, height: 20, animation: 'spin 1s linear infinite' }} />
      </div>
    )
  }

  if (runs.length === 0) {
    return (
      <div style={{ padding: '48px 24px', textAlign: 'center', color: '#9ca3af', fontSize: 13 }}>
        No runs yet. Results will appear here after you run this {type}.
      </div>
    )
  }

  return (
    <div>
      <div style={{ padding: '12px 24px 8px', fontSize: 12, color: '#9ca3af', fontWeight: 500 }}>
        {runs.length} run{runs.length !== 1 ? 's' : ''}
      </div>
      {runs.map(run => (
        <RunRow key={run.id} run={run} type={type} />
      ))}
    </div>
  )
}
