import { useAdminViewState } from './shared/AdminViewState'
import { TableRegion } from './shared/TableRegion'
import { useAdminQuery } from './shared/useAdminQuery'
import { useEffect, useRef, useCallback } from 'react'
import { AlertCircle, ChevronLeft, ChevronRight, Download } from 'lucide-react'

import * as auditApi from '../../api/audit'

export function AuditTab() {
  const [page, setPage] = useAdminViewState('AuditTab.page', 0)
  const [actionFilter, setActionFilter] = useAdminViewState('AuditTab.actionFilter', '')
  const [debouncedActionFilter, setDebouncedActionFilter] = useAdminViewState('AuditTab.debouncedActionFilter', '')
  const [resourceTypeFilter, setResourceTypeFilter] = useAdminViewState('AuditTab.resourceTypeFilter', '')
  const actionDebounce = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const limit = 25

  // Debounce the free-text action filter so typing does not fire a request
  // per keystroke; the input itself stays controlled/responsive via
  // `actionFilter`, only the fetch trigger (`debouncedActionFilter`) lags.
  const handleActionFilterChange = (v: string) => {
    setActionFilter(v)
    if (actionDebounce.current) clearTimeout(actionDebounce.current)
    actionDebounce.current = setTimeout(() => { setDebouncedActionFilter(v); setPage(0) }, 400)
  }

  // Clear any pending debounce timer on unmount so it can't fire after teardown.
  useEffect(() => () => { if (actionDebounce.current) clearTimeout(actionDebounce.current) }, [])

  const request = useCallback(() => auditApi.queryAuditLog({ action: debouncedActionFilter || undefined, resource_type: resourceTypeFilter || undefined, skip: page * limit, limit }), [page, debouncedActionFilter, resourceTypeFilter])
  const { data, loading, error, load } = useAdminQuery(request)
  const entries = data?.entries ?? []
  const total = data?.total ?? 0
  const loadedOnce = !!data

  const ACTION_COLORS: Record<string, string> = {
    'document.create': '#dcfce7', 'document.delete': '#fee2e2',
    'extraction.run': '#dbeafe', 'workflow.run': '#f3e8ff',
    'workflow.approve': '#dcfce7', 'workflow.reject': '#fee2e2',
    'user.login': '#f3f4f6', 'config.update': '#ffedd5',
    'folder.delete': '#fee2e2', 'knowledge_base.delete': '#fee2e2',
    'credential.delete': '#fee2e2', 'extraction.delete': '#fee2e2',
    'automation.delete': '#fee2e2', 'chat.delete': '#fee2e2',
    'library_item.remove': '#fee2e2',
  }
  const totalPages = Math.ceil(total / limit)

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 20 }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>
          Audit Log {loadedOnce && <span style={{ fontSize: 14, fontWeight: 400, color: '#59616b' }}>({total} entries)</span>}
        </h2>
        <a href={auditApi.exportAuditLog({ action: actionFilter, resource_type: resourceTypeFilter })}
          style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, color: '#374151', textDecoration: 'none' }}>
          <Download size={14} /> Export CSV
        </a>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 16 }}>
        <input type="text" aria-label="Filter audit actions" value={actionFilter} onChange={e => handleActionFilterChange(e.target.value)}
          placeholder="Filter by action…" style={{ maxWidth: '100%', padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, fontFamily: 'inherit' }} />
        <select aria-label="Filter audit resources" value={resourceTypeFilter} onChange={e => { setResourceTypeFilter(e.target.value); setPage(0) }}
          style={{ maxWidth: '100%', padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, fontFamily: 'inherit' }}>
          <option value="">All resources</option>
          {['document','folder','workflow','extraction','knowledge_base','credential','automation','chat','library_item','user','team','config','organization','approval'].map(r => (
            <option key={r} value={r}>{r.split('_').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}</option>
          ))}
        </select>
      </div>
      <p style={{ fontSize: 13, color: '#59616b', marginBottom: 12 }}>Recorded actions show who did what and when. An event does not establish that a document or result is correct. Export includes all matching events.</p>
      {error && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16,
          padding: '10px 14px', borderRadius: 8, background: '#fef2f2',
          border: '1px solid #fecaca', color: '#991b1b', fontSize: 13,
        }}>
          <span role="alert"><AlertCircle size={14} /> {error}</span><button type="button" onClick={load} className="admin-open-record">Retry audit log</button>
        </div>
      )}
      <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden', backgroundColor: '#fff' }}>
        <TableRegion label="Audit events — scroll for more columns"><table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
          <thead>
            <tr style={{ backgroundColor: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
              {['Time','Action','Actor','Resource','Details'].map(h => (
                <th key={h} style={{ padding: '10px 14px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading && !loadedOnce ? (
              <tr><td colSpan={5} style={{ padding: '32px', textAlign: 'center', color: '#59616b' }}>Loading…</td></tr>
            ) : error && !loadedOnce ? (
              <tr><td colSpan={5} style={{ padding: '32px', textAlign: 'center', color: '#dc2626' }}>Failed to load audit log</td></tr>
            ) : entries.length === 0 ? (
              <tr><td colSpan={5} style={{ padding: '32px', textAlign: 'center', color: '#59616b' }}>No entries found</td></tr>
            ) : entries.map(entry => (
              <tr key={entry.uuid} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td style={{ padding: '10px 14px', whiteSpace: 'nowrap', color: '#6b7280' }}>
                  {entry.timestamp ? new Date(entry.timestamp).toLocaleDateString() + ' ' + new Date(entry.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '-'}
                </td>
                <td style={{ padding: '10px 14px' }}>
                  <span style={{ display: 'inline-block', padding: '2px 8px', borderRadius: 12, fontSize: 11, fontWeight: 500, backgroundColor: ACTION_COLORS[entry.action] ?? '#f3f4f6', color: '#374151' }}>
                    {entry.action}
                  </span>
                </td>
                <td style={{ padding: '10px 14px', color: '#374151' }}>{entry.actor_user_id}</td>
                <td style={{ padding: '10px 14px', color: '#374151' }}>
                  {entry.resource_name || entry.resource_id || '-'}
                  <span style={{ marginLeft: 6, fontSize: 11, color: '#59616b' }}>{entry.resource_type}</span>
                </td>
                <td style={{ padding: '10px 14px', color: '#59616b', fontSize: 12, minWidth: 180, maxWidth: 360 }}>
                  {Object.keys(entry.detail).length > 0 ? <details><summary style={{ cursor: 'pointer' }}>View event details</summary><dl className="admin-audit-details">{Object.entries(entry.detail).filter(([, value]) => value === null || typeof value !== 'object').map(([key, value]) => <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{value === null ? 'Not recorded' : String(value)}</dd></div>)}</dl><details><summary>Raw event JSON</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', marginTop: 8 }}>{JSON.stringify(entry.detail, null, 2)}</pre></details></details> : 'No details recorded'}
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
