import { useEffect, useState, useCallback, useMemo } from 'react'
import {
  ArrowLeft, Check, MessageSquare, CheckCircle2, Cpu, FileText, XCircle, Zap,
  Download, AlertCircle,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import {
  getUserLeaderboard, getUserDetail, getUserHistory, updateUserRoles,
} from '../../api/admin'
import type {
  UserLeaderboardItem, UserDetailResponse, UserHistoryItem,
} from '../../api/admin'
import * as auditApi from '../../api/audit'
import { useAuth } from '../../hooks/useAuth'
import { useConfirm } from '../shared/useConfirm'
import { useToast } from '../../contexts/ToastContext'
import { downloadCSV, formatDate, formatDateTime, formatDuration, formatNumber } from './shared/format'
import {
  StatusBadge, RoleBadge, KpiCard, UserAvatar, SortableHeader, SearchInput, ExportButton, TimeRangeSelector, type DayOption,
} from './shared/primitives'

type UserSortKey = 'tokens_total' | 'workflows_run' | 'conversations' | 'last_active' | 'name'

function UserDrillDown({ userId, onBack }: { userId: string; onBack: () => void }) {
  const { user: currentUser } = useAuth()
  const confirm = useConfirm()
  const { toast } = useToast()
  const [data, setData] = useState<UserDetailResponse | null>(null)
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [savingRoles, setSavingRoles] = useState(false)

  const load = useCallback(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getUserDetail(userId, days)
      .then(res => { if (!cancelled) setData(res) })
      .catch(e => { if (!cancelled) setError(e?.message || 'Failed to load') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [userId, days])

  useEffect(() => load(), [load])

  const prev = data?.previous_period

  if (loading && !data) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading user details...</div>
  if (error) return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <button onClick={onBack} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: '#6b7280', padding: '4px 0' }}>
        <ArrowLeft size={16} /> Back to Users
      </button>
      <div style={{ padding: 40, textAlign: 'center', color: '#dc2626' }}>Error: {error}</div>
    </div>
  )
  if (!data) return null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Back + header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <button onClick={onBack} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: '#6b7280', padding: '4px 0' }}>
          <ArrowLeft size={16} /> Back to Users
        </button>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <UserAvatar name={data.name || data.email} />
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 20, fontWeight: 700 }}>{data.name || 'Unknown'}</span>
            {data.is_admin && <RoleBadge role="admin" />}
            {data.is_staff && <RoleBadge role="staff" />}
            {data.is_examiner && <RoleBadge role="examiner" />}
          </div>
          <div style={{ fontSize: 13, color: '#6b7280' }}>{data.email || data.user_id}</div>
        </div>
      </div>

      {/* Role management (admin only) */}
      {currentUser?.is_admin && (
        <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: '16px 20px' }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 12 }}>Platform Roles</div>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {(['is_admin', 'is_staff', 'is_examiner'] as const).map(role => {
              const label = role === 'is_admin' ? 'Admin' : role === 'is_staff' ? 'Staff' : 'Examiner'
              const active = !!data[role]
              const isSelfAdmin = role === 'is_admin' && !!currentUser && currentUser.user_id === userId
              const disabled = savingRoles || isSelfAdmin
              return (
                <button
                  key={role}
                  disabled={disabled}
                  title={isSelfAdmin ? 'You cannot change your own Admin role. Ask another admin to do this to avoid locking yourself out.' : undefined}
                  onClick={async () => {
                    if (isSelfAdmin) return
                    const granting = !active
                    const ok = await confirm({
                      title: `${granting ? 'Grant' : 'Revoke'} ${label} role?`,
                      message: role === 'is_admin' ? (
                        <>
                          {granting ? 'Grant' : 'Revoke'} the <strong>Admin</strong> role for{' '}
                          <strong>{data.name || data.email || userId}</strong>?{' '}
                          {granting
                            ? 'They will be able to manage LLM credentials, retention policy, and platform-wide authentication configuration — the highest-privilege access in the product.'
                            : 'They will immediately lose access to LLM credentials, retention policy, and platform-wide configuration.'}
                        </>
                      ) : (
                        <>
                          {granting ? 'Grant' : 'Revoke'} the <strong>{label}</strong> role for{' '}
                          <strong>{data.name || data.email || userId}</strong>?
                        </>
                      ),
                      confirmLabel: granting ? 'Grant' : 'Revoke',
                      destructive: !granting,
                    })
                    if (!ok) return
                    setSavingRoles(true)
                    try {
                      await updateUserRoles(userId, { [role]: !active })
                      setData(prev => prev ? { ...prev, [role]: !active } : prev)
                    } catch (e) {
                      toast(`Failed to ${granting ? 'grant' : 'revoke'} ${label} role: ${e instanceof Error ? e.message : 'unknown error'}`, 'error')
                    } finally {
                      setSavingRoles(false)
                    }
                  }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '8px 16px', borderRadius: 'var(--ui-radius, 12px)',
                    border: active ? '2px solid #22c55e' : '2px solid #e5e7eb',
                    background: active ? '#f0fdf4' : '#fff',
                    cursor: disabled ? (isSelfAdmin ? 'not-allowed' : 'wait') : 'pointer',
                    fontSize: 13, fontWeight: 600,
                    color: active ? '#166534' : '#6b7280',
                    opacity: disabled ? 0.6 : 1,
                  }}
                >
                  <div style={{
                    width: 18, height: 18, borderRadius: 4,
                    border: active ? '2px solid #22c55e' : '2px solid #d1d5db',
                    background: active ? '#22c55e' : '#fff',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    {active && <Check size={12} color="#fff" />}
                  </div>
                  {label}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* Time range */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <TimeRangeSelector value={days} onChange={v => setDays(typeof v === 'number' ? v : 30)} onRefresh={load} />
        <div style={{ flex: 1 }} />
        <ExportButton onClick={() => {
          const dayRows = data.timeseries.map(d => [
            d.date, d.conversations, d.search_runs, d.workflows_started,
            d.workflows_completed, d.workflows_failed, d.tokens_in, d.tokens_out,
          ])
          const wfRows = data.recent_workflows.map(ev => [
            ev.started_at, ev.status, ev.title, formatDuration(ev.duration_ms),
            ev.tokens_in + ev.tokens_out,
          ])
          downloadCSV(
            `user-${data.email || data.user_id}-${days}d.csv`,
            ['Section', 'A', 'B', 'C', 'D', 'E', 'F', 'G'],
            [
              ['SUMMARY', '', '', '', '', '', '', ''],
              ['Conversations', data.conversations, '', '', '', '', '', ''],
              ['Workflows Started', data.workflows_started, '', '', '', '', '', ''],
              ['Workflows Completed', data.workflows_completed, '', '', '', '', '', ''],
              ['Workflows Failed', data.workflows_failed, '', '', '', '', '', ''],
              ['Tokens In', data.tokens_in, '', '', '', '', '', ''],
              ['Tokens Out', data.tokens_out, '', '', '', '', '', ''],
              ['Documents', data.document_count, '', '', '', '', '', ''],
              ['', '', '', '', '', '', '', ''],
              ['DAILY', 'Date', 'Conversations', 'Searches', 'WF Started', 'WF Completed', 'WF Failed', 'Tokens In/Out'],
              ...dayRows.map(r => ['', ...r]),
              ['', '', '', '', '', '', '', ''],
              ['RECENT WORKFLOWS', 'Started', 'Status', 'Title', 'Duration', 'Tokens', '', ''],
              ...wfRows.map(r => ['', ...r]),
            ],
          )
        }} />
      </div>

      {/* KPI Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        <KpiCard label="Conversations" value={formatNumber(data.conversations)} icon={MessageSquare} color="#3b82f6" trend={prev ? { current: data.conversations, previous: prev.conversations } : undefined} />
        <KpiCard label="Workflows Completed" value={formatNumber(data.workflows_completed)} icon={CheckCircle2} color="#22c55e" trend={prev ? { current: data.workflows_completed, previous: prev.workflows_completed } : undefined} />
        <KpiCard label="Total Tokens" value={formatNumber(data.tokens_in + data.tokens_out)} icon={Cpu} color="#8b5cf6" trend={prev ? { current: data.tokens_in + data.tokens_out, previous: prev.tokens_in + prev.tokens_out } : undefined} />
        <KpiCard label="Documents" value={formatNumber(data.document_count)} icon={FileText} color="#f59e0b" />
        <KpiCard label="Failed" value={formatNumber(data.workflows_failed)} icon={XCircle} color="#ef4444" trend={prev ? { current: data.workflows_failed, previous: prev.workflows_failed, invert: true } : undefined} />
        <KpiCard label="Workflows Started" value={formatNumber(data.workflows_started)} icon={Zap} color="#06b6d4" trend={prev ? { current: data.workflows_started, previous: prev.workflows_started } : undefined} />
      </div>

      {/* Daily Activity Chart */}
      {data.timeseries.length > 0 && (
        <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Daily Activity</div>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={data.timeseries}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#9ca3af' }} tickFormatter={v => v.slice(5)} />
              <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} width={50} />
              <Tooltip contentStyle={{ borderRadius: 8, fontSize: 13, border: '1px solid #e5e7eb' }} />
              <Area type="monotone" dataKey="conversations" stackId="1" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.15} name="Conversations" />
              <Area type="monotone" dataKey="workflows_started" stackId="1" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.15} name="Workflows" />
              <Area type="monotone" dataKey="search_runs" stackId="1" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.15} name="Searches" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Recent Workflows */}
      {data.recent_workflows.length > 0 && (
        <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 15, fontWeight: 600 }}>
            Recent Workflows
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Status</th>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Workflow</th>
                <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Duration</th>
                <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Tokens</th>
                <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Started</th>
              </tr>
            </thead>
            <tbody>
              {data.recent_workflows.map(ev => (
                <tr key={ev.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '10px 16px' }}><StatusBadge status={ev.status} /></td>
                  <td style={{ padding: '10px 16px', fontSize: 14 }}>{ev.title || '-'}</td>
                  <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 13, color: '#6b7280' }}>{formatDuration(ev.duration_ms)}</td>
                  <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 13, fontFamily: 'ui-monospace, monospace' }}>{formatNumber(ev.tokens_in + ev.tokens_out)}</td>
                  <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 13, color: '#6b7280' }}>{formatDateTime(ev.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Full activity history (audit trail + activity telemetry) */}
      <UserActivityHistory userId={userId} email={data.email} />
    </div>
  )
}

const HISTORY_PAGE_SIZE = 50

function SourceBadge({ source }: { source: 'audit' | 'activity' }) {
  const c = source === 'audit'
    ? { bg: '#e2e8f0', text: '#334155', label: 'Audit' }
    : { bg: '#dbeafe', text: '#1e40af', label: 'Activity' }
  return (
    <span style={{
      display: 'inline-block', padding: '1px 8px', borderRadius: 9999,
      fontSize: 10, fontWeight: 700, backgroundColor: c.bg, color: c.text,
      textTransform: 'uppercase', letterSpacing: 0.5,
    }}>
      {c.label}
    </span>
  )
}

function UserActivityHistory({ userId, email }: { userId: string; email: string | null }) {
  const [items, setItems] = useState<UserHistoryItem[]>([])
  const [total, setTotal] = useState(0)
  const [capped, setCapped] = useState(false)
  const [days, setDays] = useState(90)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Reload from scratch whenever the time range changes.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getUserHistory(userId, days, 0, HISTORY_PAGE_SIZE)
      .then(res => {
        if (cancelled) return
        setItems(res.items)
        setTotal(res.total)
        setCapped(res.capped)
      })
      .catch(e => { if (!cancelled) setError(e?.message || 'Failed to load history') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [userId, days])

  const loadMore = useCallback(() => {
    setLoadingMore(true)
    getUserHistory(userId, days, items.length, HISTORY_PAGE_SIZE)
      .then(res => {
        setItems(prev => [...prev, ...res.items])
        setTotal(res.total)
        setCapped(res.capped)
      })
      .catch(e => setError(e?.message || 'Failed to load history'))
      .finally(() => setLoadingMore(false))
  }, [userId, days, items.length])

  const startTime = useMemo(
    () => new Date(Date.now() - days * 86400000).toISOString(),
    [days],
  )

  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 15, fontWeight: 600 }}>Activity History</div>
        <div style={{ flex: 1 }} />
        <TimeRangeSelector value={days} onChange={v => setDays(typeof v === 'number' ? v : 90)} />
        <a
          href={auditApi.exportAuditLog({ actor_user_id: userId, start_time: startTime })}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '6px 12px', borderRadius: 'var(--ui-radius, 12px)',
            border: '1px solid #e5e7eb', background: '#fff', cursor: 'pointer',
            fontSize: 13, fontWeight: 600, color: '#374151', textDecoration: 'none',
          }}
          title="Download this user's immutable audit trail as CSV"
        >
          <Download size={14} /> Export audit trail
        </a>
      </div>

      {capped && (
        <div style={{ padding: '10px 20px', background: '#fffbeb', borderBottom: '1px solid #fde68a', fontSize: 13, color: '#92400e', display: 'flex', alignItems: 'center', gap: 8 }}>
          <AlertCircle size={14} /> Showing the most recent events only — narrow the time range to see older history.
        </div>
      )}

      {loading ? (
        <div style={{ padding: 32, textAlign: 'center', color: '#6b7280', fontSize: 14 }}>Loading activity history...</div>
      ) : error ? (
        <div style={{ padding: 32, textAlign: 'center', color: '#dc2626', fontSize: 14 }}>Error: {error}</div>
      ) : items.length === 0 ? (
        <div style={{ padding: 32, textAlign: 'center', color: '#6b7280', fontSize: 14 }}>No recorded activity in this period.</div>
      ) : (
        <>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>When</th>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Source</th>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Action</th>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Resource</th>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Status</th>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>IP</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it, i) => (
                <tr key={`${it.source}-${it.resource_id ?? ''}-${it.timestamp ?? ''}-${i}`} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '10px 16px', fontSize: 13, color: '#6b7280', whiteSpace: 'nowrap' }}>{formatDateTime(it.timestamp)}</td>
                  <td style={{ padding: '10px 16px' }}><SourceBadge source={it.source} /></td>
                  <td style={{ padding: '10px 16px', fontSize: 13, fontFamily: 'ui-monospace, monospace' }}>{it.action}</td>
                  <td style={{ padding: '10px 16px', fontSize: 13 }}>
                    {it.title || (it.resource_type ? <span style={{ color: '#9ca3af' }}>{it.resource_type}</span> : '-')}
                  </td>
                  <td style={{ padding: '10px 16px' }}>{it.status ? <StatusBadge status={it.status} /> : <span style={{ color: '#d1d5db' }}>—</span>}</td>
                  <td style={{ padding: '10px 16px', fontSize: 12, color: '#6b7280', fontFamily: 'ui-monospace, monospace' }}>{it.ip_address || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ padding: '12px 20px', display: 'flex', alignItems: 'center', gap: 12, borderTop: '1px solid #f3f4f6' }}>
            <span role="status" aria-live="polite" style={{ fontSize: 12, color: '#6b7280' }}>Showing {items.length} of {total}{email ? ` · ${email}` : ''}</span>
            <div style={{ flex: 1 }} />
            {items.length < total && (
              <button
                onClick={loadMore}
                disabled={loadingMore}
                style={{
                  padding: '6px 14px', borderRadius: 'var(--ui-radius, 12px)',
                  border: '1px solid #e5e7eb', background: '#fff',
                  cursor: loadingMore ? 'wait' : 'pointer', fontSize: 13, fontWeight: 600, color: '#374151',
                }}
              >
                {loadingMore ? 'Loading...' : 'Load more'}
              </button>
            )}
          </div>
        </>
      )}
    </div>
  )
}

export function UsersTab() {
  const [users, setUsers] = useState<UserLeaderboardItem[]>([])
  const [capped, setCapped] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<{ key: UserSortKey; dir: 'asc' | 'desc' }>({ key: 'tokens_total', dir: 'desc' })
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const [days, setDays] = useState<DayOption>('all')

  const load = useCallback(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    const arg = typeof days === 'number' ? days : undefined
    getUserLeaderboard(arg)
      .then(res => { if (!cancelled) { setUsers(res.items); setCapped(res.capped) } })
      .catch(e => { if (!cancelled) setError(e?.message || 'Failed to load users') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [days])

  useEffect(() => load(), [load])

  const handleSort = (key: string) => {
    setSort(prev => ({
      key: key as UserSortKey,
      dir: prev.key === key && prev.dir === 'desc' ? 'asc' : 'desc',
    }))
  }

  const filtered = useMemo(() => {
    let list = users
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(u =>
        (u.name || '').toLowerCase().includes(q) || (u.email || '').toLowerCase().includes(q)
      )
    }
    const sorted = [...list].sort((a, b) => {
      let cmp = 0
      switch (sort.key) {
        case 'name': cmp = (a.name || '').localeCompare(b.name || ''); break
        case 'tokens_total': cmp = a.tokens_total - b.tokens_total; break
        case 'workflows_run': cmp = a.workflows_run - b.workflows_run; break
        case 'conversations': cmp = a.conversations - b.conversations; break
        case 'last_active': cmp = (a.last_active || '').localeCompare(b.last_active || ''); break
      }
      return sort.dir === 'asc' ? cmp : -cmp
    })
    return sorted
  }, [users, search, sort])

  const maxTokens = users.reduce((max, u) => Math.max(max, u.tokens_total), 1)

  const handleExport = () => {
    downloadCSV('users.csv',
      ['#', 'Name', 'Email', 'Roles', 'Tokens', 'Workflows', 'Conversations', 'Last Active'],
      filtered.map((u, i) => [
        i + 1, u.name, u.email,
        [u.is_admin ? 'admin' : '', u.is_staff ? 'staff' : '', u.is_examiner ? 'examiner' : ''].filter(Boolean).join(', '),
        u.tokens_total, u.workflows_run, u.conversations, u.last_active,
      ])
    )
  }

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading users...</div>

  if (selectedUserId) {
    return <UserDrillDown userId={selectedUserId} onBack={() => setSelectedUserId(null)} />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <TimeRangeSelector value={days} onChange={setDays} includeAll onRefresh={load} />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <SearchInput value={search} onChange={setSearch} placeholder="Search users..." />
        <div style={{ flex: 1 }} />
        <ExportButton onClick={handleExport} />
      </div>

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 15, fontWeight: 600 }}>
          User Leaderboard ({filtered.length}) {days !== 'all' && <span style={{ fontSize: 12, color: '#6b7280', fontWeight: 400 }}>· last {days} days</span>}
        </div>
        {capped && (
          <div style={{ padding: '10px 20px', background: '#fffbeb', borderBottom: '1px solid #fde68a', fontSize: 13, color: '#92400e', display: 'flex', alignItems: 'center', gap: 8 }}>
            <AlertCircle size={14} /> Showing the top {users.length} users by token usage — this list is truncated. Sorting and export cover only these loaded rows, not the full user base.
          </div>
        )}
        {error && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '10px 16px', background: '#fef2f2', borderBottom: '1px solid #fecaca',
            color: '#991b1b', fontSize: 13,
          }}>
            <AlertCircle size={14} /> {error}
          </div>
        )}
        {filtered.length === 0 ? (
          !error && <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No users found.</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>#</th>
                <SortableHeader label="User" sortKey="name" currentSort={sort} onSort={handleSort} />
                <SortableHeader label="Token Usage" sortKey="tokens_total" currentSort={sort} onSort={handleSort} />
                <SortableHeader label="Workflows" sortKey="workflows_run" currentSort={sort} onSort={handleSort} align="right" />
                <SortableHeader label="Chats" sortKey="conversations" currentSort={sort} onSort={handleSort} align="right" />
                <SortableHeader label="Last Active" sortKey="last_active" currentSort={sort} onSort={handleSort} align="right" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((u, i) => (
                <tr key={u.user_id} tabIndex={0} role="button" aria-label={`View ${u.user_id}`} onClick={() => setSelectedUserId(u.user_id)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedUserId(u.user_id) } }} style={{ borderBottom: '1px solid #f3f4f6', cursor: 'pointer' }} onMouseEnter={e => (e.currentTarget.style.backgroundColor = '#f9fafb')} onMouseLeave={e => (e.currentTarget.style.backgroundColor = '')}>
                  <td style={{ padding: '12px 16px', fontSize: 14, fontWeight: 600, color: '#9ca3af' }}>{i + 1}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <UserAvatar name={u.name || u.email} />
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{ fontSize: 14, fontWeight: 500 }}>{u.name || 'Unknown'}</span>
                          {u.is_admin && <RoleBadge role="admin" />}
                          {u.is_staff && <RoleBadge role="staff" />}
                          {u.is_examiner && <RoleBadge role="examiner" />}
                        </div>
                        <div style={{ fontSize: 12, color: '#6b7280' }}>{u.email || u.user_id}</div>
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{ flex: 1, height: 6, backgroundColor: '#f3f4f6', borderRadius: 3, overflow: 'hidden' }}>
                        <div style={{ width: `${(u.tokens_total / maxTokens) * 100}%`, height: '100%', backgroundColor: 'var(--highlight-color, #eab308)', borderRadius: 3 }} />
                      </div>
                      <span style={{ fontSize: 13, fontFamily: 'ui-monospace, monospace', color: '#374151', minWidth: 60, textAlign: 'right' }}>
                        {formatNumber(u.tokens_total)}
                      </span>
                    </div>
                  </td>
                  <td style={{ padding: '12px 16px', textAlign: 'right', fontSize: 14, fontFamily: 'ui-monospace, monospace' }}>{u.workflows_run}</td>
                  <td style={{ padding: '12px 16px', textAlign: 'right', fontSize: 14, fontFamily: 'ui-monospace, monospace' }}>{u.conversations}</td>
                  <td style={{ padding: '12px 16px', textAlign: 'right', fontSize: 13, color: '#6b7280' }}>{formatDate(u.last_active)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
