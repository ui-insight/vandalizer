import { useCallback, useEffect, useRef, useState } from 'react'
import { AlertCircle, ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react'

import { getWorkflowEvents, type PaginatedWorkflows } from '../../api/admin'
import { downloadCSV, formatDateTime, formatDuration, formatNumber } from './shared/format'
import { ExportButton, SearchInput, StatusBadge, UserAvatar } from './shared/primitives'

export function WorkflowsTab() {
  const [data, setData] = useState<PaginatedWorkflows | null>(null)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<string>('')
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const searchDebounce = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const load = useCallback(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getWorkflowEvents(page, status || undefined, search || undefined)
      .then(res => { if (!cancelled) setData(res) })
      .catch(e => { if (!cancelled) setError(e?.message || 'Failed to load workflow events') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [page, status, search])

  useEffect(() => load(), [load])

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
      ])
    )
  }

  const summary = data?.summary

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Summary stats row */}
      {summary && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 12 }}>
          {[
            { label: 'Total', value: formatNumber(summary.total), color: '#374151' },
            { label: 'Success Rate', value: `${summary.success_rate}%`, color: '#16a34a' },
            { label: 'Avg Duration', value: formatDuration(summary.avg_duration_ms), color: '#3b82f6' },
            { label: 'Failed', value: formatNumber(summary.failed), color: '#dc2626' },
            { label: 'Total Tokens', value: formatNumber(summary.total_tokens), color: '#8b5cf6' },
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

      {/* Filters + search */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        {filters.map(f => (
          <button
            key={f}
            onClick={() => { setStatus(f); setPage(1) }}
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
        <ExportButton onClick={handleExport} />
      </div>

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
        {loading && !data ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading workflows...</div>
        ) : error && !data ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
            <AlertCircle size={28} color="#d1d5db" style={{ marginBottom: 12 }} />
            <div style={{ fontSize: 14, color: '#374151' }}>{error}</div>
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
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                  <th style={{ padding: '10px 8px', width: 28 }} />
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
                    <tr key={ev.id} tabIndex={0} role="button" aria-expanded={isExpanded} aria-label="Toggle event details" onClick={() => setExpandedId(isExpanded ? null : ev.id)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpandedId(isExpanded ? null : ev.id) } }} style={{ borderBottom: '1px solid #f3f4f6', cursor: 'pointer' }}>
                      <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                        {isExpanded ? <ChevronDown size={14} color="#6b7280" /> : <ChevronRight size={14} color="#9ca3af" />}
                      </td>
                      <td style={{ padding: '10px 16px' }}><StatusBadge status={ev.status} /></td>
                      <td style={{ padding: '10px 16px', fontSize: 14, fontWeight: 500 }}>{ev.title || 'Untitled'}</td>
                      <td style={{ padding: '10px 16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <UserAvatar name={ev.user_name || ev.user_email} />
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 500 }}>{ev.user_name || 'Unknown'}</div>
                            {ev.team_name && <div style={{ fontSize: 11, color: '#9ca3af' }}>{ev.team_name}</div>}
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
            </table>

            {/* Expanded detail - rendered below table as an info panel */}
            {expandedId && (() => {
              const ev = data.items.find(e => e.id === expandedId)
              if (!ev) return null
              return (
                <div style={{ padding: '16px 20px', borderTop: '1px solid #e5e7eb', background: '#f9fafb' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, fontSize: 13 }}>
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
                </div>
              )
            })()}

            {/* Pagination */}
            {data.pages > 1 && (
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
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
