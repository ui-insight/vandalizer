import { FullExportButton } from './shared/FullExportButton'
import { useAdminViewState } from './shared/AdminViewState'
import { TableRegion } from './shared/TableRegion'
import { useAdminQuery } from './shared/useAdminQuery'
import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertCircle, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react'

import { getWorkflowEvents } from '../../api/admin'
import { downloadCSV, formatDateTime, formatDuration, formatNumber } from './shared/format'
import { ExportButton, SearchInput, StatusBadge, UserAvatar } from './shared/primitives'

export type WorkflowPeriod = { status?: string; from?: string; until?: string }
export function WorkflowsTab({ linkedFilter, onFilterChange }: { linkedFilter?: WorkflowPeriod; onFilterChange?: (filter: WorkflowPeriod) => void } = {}) {
  const [page, setPage] = useAdminViewState('WorkflowsTab.page', 1)
  const [storedStatus, setStatus] = useAdminViewState<string>('WorkflowsTab.status', '')
  const status = linkedFilter?.status ?? storedStatus
  const [savedPeriod, setSavedPeriod] = useAdminViewState<WorkflowPeriod>('WorkflowsTab.period', {})
  const hasLink = linkedFilter?.status !== undefined || !!linkedFilter?.from || !!linkedFilter?.until
  const from = hasLink ? linkedFilter?.from : savedPeriod.from
  const until = hasLink ? linkedFilter?.until : savedPeriod.until
  useEffect(() => { if (hasLink) setSavedPeriod({ from, until }) }, [hasLink, from, until, setSavedPeriod])
  useEffect(() => { if (linkedFilter?.status !== undefined) setStatus(linkedFilter.status); if (linkedFilter?.status !== undefined || from || until) setPage(1) }, [linkedFilter?.status, from, until, setStatus, setPage])
  const [search, setSearch] = useAdminViewState('WorkflowsTab.search', '')
  const [searchInput, setSearchInput] = useAdminViewState('WorkflowsTab.searchInput', '')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const searchDebounce = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const request = useCallback(() => getWorkflowEvents(page, status || undefined, search || undefined, { from, until }), [page, status, search, from, until])
  const { data, loading, error, load } = useAdminQuery(request)

  const handleSearchChange = (v: string) => {
    setSearchInput(v)
    if (searchDebounce.current) clearTimeout(searchDebounce.current)
    searchDebounce.current = setTimeout(() => { setSearch(v); setPage(1) }, 400)
  }

  // Clear any pending debounce timer on unmount so it can't fire after teardown.
  useEffect(() => () => { if (searchDebounce.current) clearTimeout(searchDebounce.current) }, [])

  const filters = ['', 'completed', 'running', 'failed', 'queued', 'canceled']

  const handleExport = () => {
    if (!data) return
    downloadCSV('workflows.csv',
      ['Status', 'Workflow', 'User', 'Team', 'Steps', 'Tokens', 'Duration (ms)', 'Started'],
      data.items.map(ev => [
        ev.status, ev.title, ev.user_name || ev.user_id, ev.team_name || ev.team_id,
        `${ev.steps_completed}/${ev.steps_total}`, ev.tokens_in + ev.tokens_out,
        ev.duration_ms, ev.started_at,
      ]),
      { Scope: 'Current page', Page: String(page), 'Status filter': status || 'all', Search: search, 'Start (UTC)': from || 'all', 'End exclusive (UTC)': until || 'all', Timezone: 'UTC' }
    )
  }

  const summary = data?.summary

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Summary stats row */}
      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 110px), 1fr))', gap: 12 }}>
          {[
            { label: 'Total', value: formatNumber(summary.total), color: '#374151' },
            { label: 'Completion Rate', value: `${summary.success_rate}%`, color: '#15803d' },
            { label: 'Avg Duration', value: formatDuration(summary.avg_duration_ms), color: '#1d4ed8' },
            { label: 'Failed', value: formatNumber(summary.failed), color: '#dc2626' },
            { label: 'Total Tokens', value: formatNumber(summary.total_tokens), color: '#6d28d9' },
          ].map(s => (
            <div key={s.label} style={{
              background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)',
              padding: '14px 16px', textAlign: 'center',
            }}>
              <div style={{ fontSize: 11, color: '#6b7280', textTransform: 'uppercase', marginBottom: 4 }}>{s.label}</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: s.color, fontFamily: 'ui-monospace, monospace' }}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      <p style={{ margin: 0, fontSize: 13, color: '#59616b' }}>Completion records finished execution, not correctness. Inspect failed events for the reason; Export CSV includes the loaded page; Export all matching records includes every match.</p>

      {(from || until) && <p role="status" style={{ margin: 0, fontSize: 13 }}>Workflow start window (UTC): {from || 'any start'} to {until || 'now'} (end exclusive). <button type="button" className="admin-open-record" onClick={() => { setSavedPeriod({}); setPage(1); onFilterChange?.({ status }) }}>Clear date range</button></p>}

      {/* Filters + search */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {filters.map(f => (
          <button
            key={f}
            aria-pressed={status === f}
            onClick={() => { setStatus(f); setPage(1); onFilterChange?.({ from, until, status: f }) }}
            style={{
              padding: '6px 16px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #e5e7eb',
              fontSize: 13, fontWeight: 500, cursor: 'pointer', textTransform: 'capitalize',
              backgroundColor: status === f ? 'var(--highlight-color, #eab308)' : '#fff',
              color: status === f ? 'var(--highlight-text-color, #000)' : '#374151',
            }}
          >
            {f || 'All'}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <SearchInput value={searchInput} onChange={handleSearchChange} placeholder="Search workflows..." />
        <ExportButton onClick={handleExport} disabled={loading || !!error || !data} />
        <FullExportButton scope={JSON.stringify([status, search, from, until])} filename="workflows-all-matching.csv" disabled={loading || !!error}
          headers={['Status', 'Workflow', 'User', 'Team', 'Steps', 'Tokens', 'Duration (ms)', 'Started']}
          fetchPage={offset => getWorkflowEvents(Math.floor(offset / 50) + 1, status || undefined, search || undefined, { from, until })} getKey={event => event.id}
          row={event => [event.status, event.title, event.user_name || event.user_id, event.team_name || event.team_id, `${event.steps_completed}/${event.steps_total}`, event.tokens_in + event.tokens_out, event.duration_ms, event.started_at]}
          metadata={{ 'Status filter': status || 'all', Search: search, 'Start (UTC)': from || 'all', 'End exclusive (UTC)': until || 'all', Timezone: 'UTC' }} />
      </div>

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading workflows...</div>
        ) : error ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
            <AlertCircle size={28} color="#d1d5db" style={{ marginBottom: 12 }} />
            <div role="alert" style={{ fontSize: 14, color: '#991b1b' }}>{error}</div>
            <button type="button" onClick={load} className="admin-open-record">Retry workflows</button>
          </div>
        ) : !data || data.items.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No workflow events found.</div>
        ) : (
          <>
            {error && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '10px 16px', background: '#fef2f2', borderBottom: '1px solid #fecaca',
                color: '#991b1b', fontSize: 13,
              }}>
                <AlertCircle size={14} /> {error}
              </div>
            )}
            <TableRegion label="Workflow events — scroll for more columns"><table style={{ width: '100%', minWidth: 1080, borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                  <th className="admin-icon-column"><span className="sr-only">Details</span></th>
                  <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Status</th>
                  <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Workflow</th>
                  <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>User</th>
                  <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Steps</th>
                  <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Tokens</th>
                  <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Duration</th>
                  <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Started</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map(ev => {
                  const isExpanded = expandedId === ev.id
                  return (
                    <tr key={ev.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                      <td className="admin-icon-column" style={{ textAlign: 'center' }}>
                        <button type="button" className="admin-open-record" aria-expanded={isExpanded} aria-controls="workflow-event-detail" aria-label={`Details for ${ev.title || 'Untitled workflow'} · ${formatDateTime(ev.started_at)} · ${ev.status}`} onClick={() => setExpandedId(isExpanded ? null : ev.id)}>{isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}</button>
                      </td>
                      <td style={{ padding: '10px 16px' }}><StatusBadge status={ev.status} /></td>
                      <td style={{ padding: '10px 16px', minWidth: 220, fontSize: 14, fontWeight: 500 }}>{ev.title || 'Untitled'}</td>
                      <td style={{ padding: '10px 16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <UserAvatar name={ev.user_name || ev.user_email} />
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 500 }}>{ev.user_name || 'Unknown'}</div>
                            {ev.team_name && <div style={{ fontSize: 11, color: '#59616b' }}>{ev.team_name}</div>}
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 13 }}>{ev.steps_completed}/{ev.steps_total}</td>
                      <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 13, fontFamily: 'ui-monospace, monospace' }}>
                        {formatNumber(ev.tokens_in + ev.tokens_out)}
                      </td>
                      <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 13, color: '#6b7280' }}>{formatDuration(ev.duration_ms)}</td>
                      <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 13, color: '#6b7280' }}>{formatDateTime(ev.started_at)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table></TableRegion>

            {/* Expanded detail - rendered below table as an info panel */}
            {expandedId && (() => {
              const ev = data.items.find(e => e.id === expandedId)
              if (!ev) return null
              return (
                <section id="workflow-event-detail" aria-label={`Event details: ${ev.title || 'Untitled workflow'}`} style={{ padding: '16px 20px', borderTop: '1px solid #e5e7eb', background: '#f9fafb' }}>
                  <h2 style={{ fontSize: 16, marginBottom: 12 }}>{ev.title || 'Untitled workflow'}</h2>
                  <div className="admin-detail-grid" style={{ fontSize: 13 }}>
                    <div>
                      <div style={{ color: '#6b7280', fontWeight: 500, marginBottom: 4 }}>User ID</div>
                      <div style={{ fontFamily: 'ui-monospace, monospace', fontSize: 12 }}>{ev.user_id}</div>
                    </div>
                    <div>
                      <div style={{ color: '#6b7280', fontWeight: 500, marginBottom: 4 }}>Email</div>
                      <div>{ev.user_email || '-'}</div>
                    </div>
                    <div>
                      <div style={{ color: '#6b7280', fontWeight: 500, marginBottom: 4 }}>Team</div>
                      <div>{ev.team_name || ev.team_id || '-'}</div>
                    </div>
                    <div>
                      <div style={{ color: '#6b7280', fontWeight: 500, marginBottom: 4 }}>Finished</div>
                      <div>{formatDateTime(ev.finished_at)}</div>
                    </div>
                    <div>
                      <div style={{ color: '#6b7280', fontWeight: 500, marginBottom: 4 }}>Input Tokens</div>
                      <div style={{ fontFamily: 'ui-monospace, monospace' }}>{formatNumber(ev.tokens_in)}</div>
                    </div>
                    <div>
                      <div style={{ color: '#6b7280', fontWeight: 500, marginBottom: 4 }}>Output Tokens</div>
                      <div style={{ fontFamily: 'ui-monospace, monospace' }}>{formatNumber(ev.tokens_out)}</div>
                    </div>
                    <div>
                      <div style={{ color: '#6b7280', fontWeight: 500, marginBottom: 4 }}>Duration</div>
                      <div>{formatDuration(ev.duration_ms)}</div>
                    </div>
                    <div>
                      <div style={{ color: '#6b7280', fontWeight: 500, marginBottom: 4 }}>Steps</div>
                      <div>{ev.steps_completed} / {ev.steps_total}</div>
                    </div>
                  </div>
                  {ev.error && (
                    <div style={{ marginTop: 12, padding: '10px 14px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8, color: '#991b1b', fontSize: 13 }}>
                      {ev.error}
                    </div>
                  )}
                </section>
              )
            })()}

            {/* Pagination */}
            {data.pages > 1 && (
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12,
                padding: '12px 16px', borderTop: '1px solid #e5e7eb',
              }}>
                <span style={{ fontSize: 13, color: '#6b7280' }}>
                  Page {data.page} of {data.pages} ({data.total} total)
                </span>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    disabled={page <= 1}
                    onClick={() => setPage(p => p - 1)}
                    style={{
                      padding: '6px 12px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #e5e7eb',
                      fontSize: 13, cursor: page <= 1 ? 'default' : 'pointer', opacity: page <= 1 ? 0.4 : 1,
                      background: '#fff', display: 'flex', alignItems: 'center', gap: 4,
                    }}
                  >
                    <ChevronLeft size={14} /> Prev
                  </button>
                  <button
                    disabled={page >= data.pages}
                    onClick={() => setPage(p => p + 1)}
                    style={{
                      padding: '6px 12px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #e5e7eb',
                      fontSize: 13, cursor: page >= data.pages ? 'default' : 'pointer', opacity: page >= data.pages ? 0.4 : 1,
                      background: '#fff', display: 'flex', alignItems: 'center', gap: 4,
                    }}
                  >
                    Next <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
