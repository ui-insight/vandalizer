import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle, CheckCircle2, Eye, Play, RefreshCw, Sparkles, XCircle,
} from 'lucide-react'
import {
  getOptimizerActivity,
  type OptimizerActivityResponse,
  type OptimizerActivityRun,
} from '../../api/admin'
import { relativeTime } from '../../utils/time'
import { KpiCard, StatusBadge } from './shared/primitives'

/**
 * Optimizer activity — read-only operator view of every tuning run.
 *
 * The per-item panels only show one item's history and a user's inbox only
 * shows their own items, so neither answers "is the optimizer healthy?".
 * This tab does: run volume, what's waiting on a human, and which failures
 * are repeating. There are no actions here on purpose — applying a config
 * belongs to whoever owns the item, from their own inbox.
 */

const SURFACE_LABEL: Record<string, string> = {
  kb: 'Knowledge base',
  extraction: 'Extraction set',
  workflow: 'Workflow',
}

const DAY_OPTIONS = [7, 14, 30, 90]

function pct(score: number | null): string {
  return score == null ? '—' : `${Math.round(score * 100)}`
}

function triggerLabel(run: OptimizerActivityRun): string {
  if (!run.trigger) return 'user-launched'
  return run.trigger.replace(/_/g, ' ')
}

export function OptimizerTab() {
  const [data, setData] = useState<OptimizerActivityResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [days, setDays] = useState(14)
  const [surface, setSurface] = useState('')
  const [status, setStatus] = useState('')
  const [trigger, setTrigger] = useState<'' | 'auto' | 'user'>('')

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    getOptimizerActivity({
      days,
      surface: surface || undefined,
      status: status || undefined,
      trigger: trigger || undefined,
      limit: 200,
    })
      .then(setData)
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load optimizer activity'))
      .finally(() => setLoading(false))
  }, [days, surface, status, trigger])

  useEffect(() => { load() }, [load])

  const summary = data?.summary

  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        flexWrap: 'wrap', marginBottom: 16,
      }}>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: '#111827', margin: 0 }}>
            Optimizer activity
          </h2>
          <p style={{ fontSize: 12, color: '#6b7280', margin: '4px 0 0' }}>
            Every tuning run across workflows, extraction sets, and knowledge bases.
            Read-only — owners act on their own suggestions from Tuning suggestions.
          </p>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          <select value={days} onChange={e => setDays(Number(e.target.value))} style={selectStyle} aria-label="Time window">
            {DAY_OPTIONS.map(d => <option key={d} value={d}>Last {d} days</option>)}
          </select>
          <select value={surface} onChange={e => setSurface(e.target.value)} style={selectStyle} aria-label="Surface">
            <option value="">All surfaces</option>
            <option value="workflow">Workflows</option>
            <option value="extraction">Extraction sets</option>
            <option value="kb">Knowledge bases</option>
          </select>
          <select value={status} onChange={e => setStatus(e.target.value)} style={selectStyle} aria-label="Status">
            <option value="">All statuses</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="running">Running</option>
            <option value="queued">Queued</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <select
            value={trigger}
            onChange={e => setTrigger(e.target.value as '' | 'auto' | 'user')}
            style={selectStyle}
            aria-label="Trigger"
          >
            <option value="">Any trigger</option>
            <option value="auto">Auto-triggered</option>
            <option value="user">User-launched</option>
          </select>
          <button onClick={load} disabled={loading} style={buttonStyle}>
            <RefreshCw size={12} style={{ animation: loading ? 'spin 1s linear infinite' : undefined }} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: 12, marginBottom: 16,
          background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8,
          color: '#991b1b', fontSize: 13,
        }}>
          <AlertTriangle size={14} />
          {error}
        </div>
      )}

      {summary && (
        <>
          <div style={{
            display: 'grid', gap: 12, marginBottom: 16,
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          }}>
            <KpiCard label="Runs" value={summary.total} icon={Play} color="#0050d7" />
            <KpiCard label="Waiting on review" value={summary.pending_review} icon={Eye} color="#b45309" />
            <KpiCard label="Failed" value={summary.failed} icon={XCircle} color="#b3261e" />
            <KpiCard label="Applied" value={summary.applied} icon={CheckCircle2} color="#1a7f37" />
            <KpiCard label="Auto-triggered" value={summary.auto_triggered} icon={Sparkles} color="#7c3aed" />
          </div>

          {summary.truncated && (
            <p style={{ fontSize: 11, color: '#9a3412', margin: '0 0 12px' }}>
              A surface hit the 200-run fetch cap — totals below are a floor, not the
              exact fleet count. Narrow the window or filter by surface for exact numbers.
            </p>
          )}

          {summary.failure_reasons.length > 0 && (
            <section style={{
              background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12,
              padding: 16, marginBottom: 16,
            }}>
              <h3 style={{ fontSize: 13, fontWeight: 700, color: '#111827', margin: '0 0 8px' }}>
                Why runs failed
              </h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {summary.failure_reasons.map(f => (
                  <div
                    key={f.reason}
                    style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12 }}
                  >
                    <span style={{
                      minWidth: 28, textAlign: 'right', fontWeight: 700,
                      color: '#991b1b', fontVariantNumeric: 'tabular-nums',
                    }}>
                      {f.count}
                    </span>
                    <span style={{ color: '#374151', wordBreak: 'break-word' }}>
                      {f.reason.replace(/_/g, ' ')}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      <div style={{
        background: '#fff', border: '1px solid #e5e7eb', borderRadius: 12,
        overflow: 'hidden',
      }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ background: '#f9fafb', textAlign: 'left' }}>
                {['Item', 'Surface', 'Status', 'Trigger', 'Score', 'Owner', 'Started', 'Detail'].map(h => (
                  <th key={h} style={thStyle}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data?.runs || []).map(run => (
                <tr key={`${run.surface}:${run.run_uuid}`} style={{ borderTop: '1px solid #f3f4f6' }}>
                  <td style={tdStyle}>
                    <span style={{ fontWeight: 600, color: '#111827' }}>
                      {run.item_name || '(deleted)'}
                    </span>
                    {run.is_live && (
                      <span style={{ marginLeft: 6, fontSize: 10, color: '#1a7f37', fontWeight: 700 }}>
                        LIVE
                      </span>
                    )}
                    {run.dismissed_at && (
                      <span style={{ marginLeft: 6, fontSize: 10, color: '#6b7280', fontWeight: 700 }}>
                        DISMISSED
                      </span>
                    )}
                  </td>
                  <td style={tdStyle}>{SURFACE_LABEL[run.surface] || run.surface}</td>
                  <td style={tdStyle}><StatusBadge status={run.status} /></td>
                  <td style={{ ...tdStyle, color: run.trigger ? '#7c3aed' : '#6b7280' }}>
                    {triggerLabel(run)}
                  </td>
                  <td style={{ ...tdStyle, fontVariantNumeric: 'tabular-nums' }}>
                    {pct(run.baseline_score)} → {pct(run.optimized_score)}
                    {run.tied_with_baseline && (
                      <span style={{ marginLeft: 6, fontSize: 10, color: '#92400e' }}>tied</span>
                    )}
                  </td>
                  <td style={{ ...tdStyle, color: '#6b7280' }}>{run.user_email || run.user_id || '—'}</td>
                  <td style={{ ...tdStyle, color: '#6b7280', whiteSpace: 'nowrap' }}>
                    {run.started_at ? relativeTime(run.started_at) : '—'}
                  </td>
                  <td style={{ ...tdStyle, maxWidth: 320 }}>
                    {run.status === 'failed' ? (
                      <span style={{ color: '#991b1b', wordBreak: 'break-word' }}>
                        {run.error_code ? `${run.error_code.replace(/_/g, ' ')}: ` : ''}
                        {run.error_message || 'no error recorded'}
                      </span>
                    ) : run.status === 'running' || run.status === 'queued' ? (
                      <span style={{ color: '#0050d7' }}>{run.progress_message || run.phase || '—'}</span>
                    ) : (
                      <span style={{ color: '#6b7280' }}>{run.stopped_reason?.replace(/_/g, ' ') || '—'}</span>
                    )}
                  </td>
                </tr>
              ))}
              {!loading && (data?.runs.length || 0) === 0 && (
                <tr>
                  <td colSpan={8} style={{ ...tdStyle, textAlign: 'center', color: '#6b7280', padding: 24 }}>
                    No optimizer runs in this window.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

const selectStyle: React.CSSProperties = {
  padding: '5px 8px', fontSize: 12, borderRadius: 6,
  border: '1px solid #d1d5db', background: '#fff', color: '#374151',
}

const buttonStyle: React.CSSProperties = {
  display: 'inline-flex', alignItems: 'center', gap: 5,
  padding: '5px 10px', fontSize: 12, fontWeight: 600, borderRadius: 6,
  border: '1px solid #d1d5db', background: '#fff', color: '#374151', cursor: 'pointer',
}

const thStyle: React.CSSProperties = {
  padding: '8px 12px', fontSize: 11, fontWeight: 700, color: '#6b7280',
  textTransform: 'uppercase', letterSpacing: 0.4, whiteSpace: 'nowrap',
}

const tdStyle: React.CSSProperties = {
  padding: '8px 12px', verticalAlign: 'top', color: '#374151',
}
