import { useCallback } from 'react'
import { AlertCircle, ChevronLeft, ChevronRight, Download } from 'lucide-react'

import { useAdminViewState } from './shared/AdminViewState'
import { TableRegion } from './shared/TableRegion'
import { useAdminQuery } from './shared/useAdminQuery'
import * as auditApi from '../../api/audit'

// Where a search came from, in the words an admin would use.
const FEATURE_LABELS: Record<string, string> = {
  chat: 'Chat',
  workflow: 'Workflow',
  kb_source_suggestions: 'Knowledge base topic search',
  web_search_test: 'Admin test',
  unattributed: 'Unattributed',
}
const STATUS_LABELS: Record<string, string> = { ok: 'OK', error: 'Failed', not_configured: 'Not configured' }
const STATUS_COLORS: Record<string, string> = { ok: '#dcfce7', error: '#fee2e2', not_configured: '#f3f4f6' }

const featureLabel = (f: string) => FEATURE_LABELS[f] ?? f.replaceAll('_', ' ')

const controlStyle = { maxWidth: '100%', padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, fontFamily: 'inherit' }
const cell = { padding: '10px 14px', color: '#374151' }

export function WebSearchLog() {
  const [page, setPage] = useAdminViewState('WebSearchLog.page', 0)
  const [feature, setFeature] = useAdminViewState('WebSearchLog.feature', '')
  const [status, setStatus] = useAdminViewState('WebSearchLog.status', '')
  const limit = 25

  const request = useCallback(
    () => auditApi.queryWebSearches({ feature, status, skip: page * limit, limit }),
    [page, feature, status],
  )
  const { data, loading, error, load } = useAdminQuery(request)
  const entries = data?.entries ?? []
  const total = data?.total ?? 0
  const loadedOnce = !!data
  const totalPages = Math.ceil(total / limit)
  const byFeature = Object.entries(data?.by_feature ?? {}).sort((a, b) => b[1] - a[1])
  const failed = (data?.by_status?.error ?? 0) + (data?.by_status?.not_configured ?? 0)

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>
          Web Searches {loadedOnce && <span style={{ fontSize: 14, fontWeight: 400, color: '#59616b' }}>({total} searches)</span>}
        </h2>
        <a href={auditApi.exportWebSearches({ feature, status })}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, color: '#374151', textDecoration: 'none' }}>
          <Download size={14} /> Export CSV
        </a>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
        <select aria-label="Filter web searches by source" value={feature} onChange={e => { setFeature(e.target.value); setPage(0) }} style={controlStyle}>
          <option value="">All sources</option>
          {Object.keys(FEATURE_LABELS).map(f => <option key={f} value={f}>{FEATURE_LABELS[f]}</option>)}
        </select>
        <select aria-label="Filter web searches by outcome" value={status} onChange={e => { setStatus(e.target.value); setPage(0) }} style={controlStyle}>
          <option value="">All outcomes</option>
          {Object.keys(STATUS_LABELS).map(s => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
        </select>
      </div>
      <p style={{ fontSize: 13, color: '#59616b', marginBottom: 12 }}>
        Each query sent to the web search provider, from chat, workflow Web Search steps, knowledge-base topic search and the
        admin test. The query left this deployment for the provider; only its first 200 characters are kept here. With a paid
        provider, this count is the one to check against the bill.
      </p>
      {loadedOnce && total > 0 && (
        <p role="status" style={{ fontSize: 13, color: '#374151', marginBottom: 12 }}>
          {byFeature.map(([f, n]) => `${featureLabel(f)} ${n}`).join(' · ')}
          {failed > 0 && <span style={{ color: '#991b1b' }}>{` · ${failed} did not return results`}</span>}
        </p>
      )}
      {error && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, padding: '10px 14px', borderRadius: 8, background: '#fef2f2', border: '1px solid #fecaca', color: '#991b1b', fontSize: 13 }}>
          <span role="alert"><AlertCircle size={14} /> {error}</span><button type="button" onClick={load} className="admin-open-record">Retry web searches</button>
        </div>
      )}
      <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden', backgroundColor: '#fff' }}>
        <TableRegion label="Web searches — scroll for more columns"><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ backgroundColor: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
              {['Time', 'Source', 'User', 'Query', 'Provider', 'Results', 'Outcome'].map(h => (
                <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && !loadedOnce ? (
              <tr><td colSpan={7} style={{ padding: 32, textAlign: 'center', color: '#59616b' }}>Loading…</td></tr>
            ) : error && !loadedOnce ? (
              <tr><td colSpan={7} style={{ padding: 32, textAlign: 'center', color: '#dc2626' }}>Failed to load web searches</td></tr>
            ) : entries.length === 0 ? (
              <tr><td colSpan={7} style={{ padding: 32, textAlign: 'center', color: '#59616b' }}>No web searches recorded</td></tr>
            ) : entries.map(e => (
              <tr key={e.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td style={{ ...cell, whiteSpace: 'nowrap', color: '#6b7280' }}>
                  {e.timestamp ? new Date(e.timestamp).toLocaleDateString() + ' ' + new Date(e.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '-'}
                </td>
                <td style={cell}>{featureLabel(e.feature)}</td>
                <td style={cell}>{e.user_id || '-'}</td>
                <td style={{ ...cell, minWidth: 220, maxWidth: 420, overflowWrap: 'anywhere' }}>{e.query || '-'}</td>
                <td style={cell}>{e.provider || '-'}</td>
                <td style={cell}>{e.result_count}</td>
                <td style={cell}>
                  <span title={e.error || undefined} style={{ display: 'inline-block', padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 500, backgroundColor: STATUS_COLORS[e.status] ?? '#f3f4f6' }}>
                    {STATUS_LABELS[e.status] ?? e.status}
                  </span>
                  {e.error && <div style={{ fontSize: 12, color: '#991b1b', marginTop: 4 }}>{e.error}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table></TableRegion>
      </div>
      {totalPages > 1 && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginTop: 12 }}>
          <span style={{ fontSize: 13, color: '#6b7280' }}>Page {page + 1} of {totalPages}</span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}
              style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '5px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, cursor: page === 0 ? 'not-allowed' : 'pointer', opacity: page === 0 ? 0.5 : 1, backgroundColor: '#fff', fontFamily: 'inherit' }}>
              <ChevronLeft size={14} /> Previous
            </button>
            <button onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1}
              style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '5px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, cursor: page >= totalPages - 1 ? 'not-allowed' : 'pointer', opacity: page >= totalPages - 1 ? 0.5 : 1, backgroundColor: '#fff', fontFamily: 'inherit' }}>
              Next <ChevronRight size={14} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
