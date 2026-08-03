import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertCircle, ArrowLeft, Building2, CheckCircle2, ChevronDown, ChevronUp, Cpu, FileText, MessageSquare, Plus, Users, XCircle,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'

import { useConfirm } from '../shared/useConfirm'
import { nameWithoutEmail } from '../../lib/displayName'
import { useToast } from '../../contexts/ToastContext'
import { getTeamMembers } from '../../api/teams'
import {
  getTeamLeaderboard,
  getTeamDetail,
  getSystemConfig, updateSystemConfig,
  adminListAllTeams, adminCreateTeam, adminAddUserToTeam, adminRemoveUserFromTeam, getIsolatedUsers,
  type TeamLeaderboardItem,
  type TeamDetailResponse,
  type AdminTeamItem, type IsolatedUserItem,
} from '../../api/admin'
import { downloadCSV, formatDate, formatDateTime, formatDuration, formatNumber } from './shared/format'
import {
  StatusBadge, RoleBadge, KpiCard, UserAvatar, SortableHeader, SearchInput, ExportButton, TimeRangeSelector, type DayOption,
} from './shared/primitives'

type TeamSortKey = 'name' | 'tokens_total' | 'workflows_completed' | 'active_users' | 'member_count' | 'avg_latency_ms'

function TeamDrillDown({ teamId, onBack }: { teamId: string; onBack: () => void }) {
  const [data, setData] = useState<TeamDetailResponse | null>(null)
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getTeamDetail(teamId, days)
      .then(res => { if (!cancelled) setData(res) })
      .catch(e => { if (!cancelled) setError(e?.message || 'Failed to load') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [teamId, days])

  useEffect(() => load(), [load])

  const prev = data?.previous_period
  const maxMemberTokens = (data?.members ?? []).reduce((max, m) => Math.max(max, m.tokens_total), 1)

  if (loading && !data) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading team details...</div>
  if (error) return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <button onClick={onBack} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: '#6b7280', padding: '4px 0' }}>
        <ArrowLeft size={16} /> Back to Teams
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
          <ArrowLeft size={16} /> Back to Teams
        </button>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <div style={{
          width: 44, height: 44, borderRadius: 'var(--ui-radius, 12px)', backgroundColor: '#ede9fe',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <Building2 size={22} color="#7c3aed" />
        </div>
        <span style={{ fontSize: 20, fontWeight: 700 }}>{data.name}</span>
      </div>

      {/* Time range */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <TimeRangeSelector value={days} onChange={v => setDays(typeof v === 'number' ? v : 30)} onRefresh={load} />
        <div style={{ flex: 1 }} />
        <ExportButton onClick={() => {
          const dayRows = data.timeseries.map(d => [
            d.date, d.conversations, d.search_runs, d.workflows_started,
            d.workflows_completed, d.workflows_failed, d.tokens_in, d.tokens_out, d.active_users,
          ])
          const memberRows = data.members.map(m => [
            nameWithoutEmail(m.name, m.email) || m.user_id, m.email || '', m.role,
            m.tokens_total, m.workflows_run, m.conversations, m.last_active,
          ])
          downloadCSV(
            `team-${data.name}-${days}d.csv`,
            ['Section', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'],
            [
              ['SUMMARY', '', '', '', '', '', '', '', ''],
              ['Conversations', data.conversations, '', '', '', '', '', '', ''],
              ['Workflows Started', data.workflows_started, '', '', '', '', '', '', ''],
              ['Workflows Completed', data.workflows_completed, '', '', '', '', '', '', ''],
              ['Workflows Failed', data.workflows_failed, '', '', '', '', '', '', ''],
              ['Tokens In', data.tokens_in, '', '', '', '', '', '', ''],
              ['Tokens Out', data.tokens_out, '', '', '', '', '', '', ''],
              ['Active Users', data.active_users, '', '', '', '', '', '', ''],
              ['Documents', data.document_count, '', '', '', '', '', '', ''],
              ['', '', '', '', '', '', '', '', ''],
              ['DAILY', 'Date', 'Conversations', 'Searches', 'WF Started', 'WF Completed', 'WF Failed', 'Tokens In', 'Tokens Out'],
              ...dayRows.map(r => ['', ...r]),
              ['', '', '', '', '', '', '', '', ''],
              ['MEMBERS', 'Name', 'Email', 'Role', 'Tokens', 'Workflows', 'Conversations', 'Last Active', ''],
              ...memberRows.map(r => ['', ...r, '']),
            ],
          )
        }} />
      </div>

      {/* KPI Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
        <KpiCard label="Conversations" value={formatNumber(data.conversations)} icon={MessageSquare} color="#3b82f6" trend={prev ? { current: data.conversations, previous: prev.conversations } : undefined} />
        <KpiCard label="Workflows Completed" value={formatNumber(data.workflows_completed)} icon={CheckCircle2} color="#22c55e" trend={prev ? { current: data.workflows_completed, previous: prev.workflows_completed } : undefined} />
        <KpiCard label="Active Users" value={formatNumber(data.active_users)} icon={Users} color="#06b6d4" trend={prev ? { current: data.active_users, previous: prev.active_users } : undefined} />
        <KpiCard label="Total Tokens" value={formatNumber(data.tokens_in + data.tokens_out)} icon={Cpu} color="#8b5cf6" trend={prev ? { current: data.tokens_in + data.tokens_out, previous: prev.tokens_in + prev.tokens_out } : undefined} />
        <KpiCard label="Documents" value={formatNumber(data.document_count)} icon={FileText} color="#f59e0b" />
        <KpiCard label="Failed" value={formatNumber(data.workflows_failed)} icon={XCircle} color="#ef4444" trend={prev ? { current: data.workflows_failed, previous: prev.workflows_failed, invert: true } : undefined} />
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

      {/* Members Table */}
      {data.members.length > 0 && (
        <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 15, fontWeight: 600 }}>
            Members ({data.members.length})
          </div>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Member</th>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Role</th>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Token Usage</th>
                <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Workflows</th>
                <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Chats</th>
                <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Last Active</th>
              </tr>
            </thead>
            <tbody>
              {data.members.map(m => (
                <tr key={m.user_id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '10px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <UserAvatar name={nameWithoutEmail(m.name, m.email) || m.email} />
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 500 }}>{nameWithoutEmail(m.name, m.email) || 'Unknown'}</div>
                        <div style={{ fontSize: 12, color: '#6b7280' }}>{m.email || m.user_id}</div>
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: '10px 16px' }}><RoleBadge role={m.role} /></td>
                  <td style={{ padding: '10px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{ flex: 1, height: 6, backgroundColor: '#f3f4f6', borderRadius: 3, overflow: 'hidden' }}>
                        <div style={{ width: `${(m.tokens_total / maxMemberTokens) * 100}%`, height: '100%', backgroundColor: 'var(--highlight-color, #eab308)', borderRadius: 3 }} />
                      </div>
                      <span style={{ fontSize: 13, fontFamily: 'ui-monospace, monospace', color: '#374151', minWidth: 60, textAlign: 'right' }}>
                        {formatNumber(m.tokens_total)}
                      </span>
                    </div>
                  </td>
                  <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 14, fontFamily: 'ui-monospace, monospace' }}>{m.workflows_run}</td>
                  <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 14, fontFamily: 'ui-monospace, monospace' }}>{m.conversations}</td>
                  <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 13, color: '#6b7280' }}>{formatDate(m.last_active)}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>User</th>
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
                  <td style={{ padding: '10px 16px', fontSize: 13, color: '#374151' }}>{ev.user_name || ev.user_id}</td>
                  <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 13, color: '#6b7280' }}>{formatDuration(ev.duration_ms)}</td>
                  <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 13, fontFamily: 'ui-monospace, monospace' }}>{formatNumber(ev.tokens_in + ev.tokens_out)}</td>
                  <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 13, color: '#6b7280' }}>{formatDateTime(ev.started_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function TeamsTab() {
  const confirm = useConfirm()
  const { toast } = useToast()
  const [subTab, setSubTab] = useState<'manage' | 'stats' | 'isolated'>('manage')

  // ── Manage sub-tab state ──────────────────────────────────────────────────
  const [allTeams, setAllTeams] = useState<AdminTeamItem[]>([])
  const [allTeamsCapped, setAllTeamsCapped] = useState(false)
  const [loadingAll, setLoadingAll] = useState(true)
  const [allTeamsError, setAllTeamsError] = useState<string | null>(null)
  const [newTeamName, setNewTeamName] = useState('')
  const [creating, setCreating] = useState(false)
  const [expandedTeamUuid, setExpandedTeamUuid] = useState<string | null>(null)
  const [teamMembers, setTeamMembers] = useState<Record<string, { user_id: string; name: string | null; email: string | null; role: string }[]>>({})
  const [addUserInputs, setAddUserInputs] = useState<Record<string, string>>({})
  const [addUserLoading, setAddUserLoading] = useState<Record<string, boolean>>({})
  const [defaultTeamUuid, setDefaultTeamUuid] = useState<string>('')
  const [settingDefault, setSettingDefault] = useState(false)

  // ── Stats sub-tab state ───────────────────────────────────────────────────
  const [statsTeams, setStatsTeams] = useState<TeamLeaderboardItem[]>([])
  const [statsCapped, setStatsCapped] = useState(false)
  const [loadingStats, setLoadingStats] = useState(false)
  const [statsError, setStatsError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<{ key: TeamSortKey; dir: 'asc' | 'desc' }>({ key: 'tokens_total', dir: 'desc' })
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null)
  const [statsDays, setStatsDays] = useState<DayOption>('all')

  // ── Isolated sub-tab state ───────────────────────────────────────────────
  const [isolated, setIsolated] = useState<IsolatedUserItem[]>([])
  const [isolatedCapped, setIsolatedCapped] = useState(false)
  const [isolatedLoaded, setIsolatedLoaded] = useState(false)
  const [loadingIsolated, setLoadingIsolated] = useState(false)
  const [isolatedError, setIsolatedError] = useState<string | null>(null)
  const [assignTargets, setAssignTargets] = useState<Record<string, string>>({})
  const [assignLoading, setAssignLoading] = useState<Record<string, boolean>>({})

  // Per-team add-user error messages
  const [addUserErrors, setAddUserErrors] = useState<Record<string, string>>({})

  const refreshAllTeams = useCallback(() => {
    let cancelled = false
    setLoadingAll(true)
    setAllTeamsError(null)
    adminListAllTeams().then(res => {
      if (cancelled) return
      setAllTeams(res.items)
      setAllTeamsCapped(res.capped)
      const def = res.items.find(x => x.is_default)
      if (def) setDefaultTeamUuid(def.uuid)
    }).catch(e => { if (!cancelled) setAllTeamsError(e?.message || 'Failed to load teams') })
      .finally(() => { if (!cancelled) setLoadingAll(false) })
    return () => { cancelled = true }
  }, [])

  const refreshIsolated = useCallback(() => {
    let cancelled = false
    setLoadingIsolated(true)
    setIsolatedError(null)
    getIsolatedUsers().then(res => {
      if (cancelled) return
      setIsolated(res.items)
      setIsolatedCapped(res.capped)
      setIsolatedLoaded(true)
    }).catch(e => {
      if (cancelled) return
      setIsolatedError(e?.message || 'Failed to load isolated users')
      setIsolatedLoaded(true)
    }).finally(() => { if (!cancelled) setLoadingIsolated(false) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    const cancelAllTeams = refreshAllTeams()
    const cancelIsolated = refreshIsolated()  // Load eagerly so badge shows immediately
    let cfgCancelled = false
    getSystemConfig().then(cfg => {
      if (cfgCancelled) return
      if (cfg.default_team_id) setDefaultTeamUuid(cfg.default_team_id)
    }).catch(() => {})
    return () => {
      cancelAllTeams()
      cancelIsolated()
      cfgCancelled = true
    }
  }, [refreshAllTeams, refreshIsolated])

  const refreshStats = useCallback(() => {
    let cancelled = false
    setLoadingStats(true)
    setStatsError(null)
    const arg = typeof statsDays === 'number' ? statsDays : undefined
    getTeamLeaderboard(arg)
      .then(res => { if (!cancelled) { setStatsTeams(res.items); setStatsCapped(res.capped) } })
      .catch(e => { if (!cancelled) setStatsError(e?.message || 'Failed to load team stats') })
      .finally(() => { if (!cancelled) setLoadingStats(false) })
    return () => { cancelled = true }
  }, [statsDays])

  useEffect(() => {
    if (subTab === 'stats') {
      return refreshStats()
    }
  }, [subTab, refreshStats])

  const handleCreateTeam = async () => {
    if (!newTeamName.trim()) return
    setCreating(true)
    try {
      await adminCreateTeam(newTeamName.trim())
      setNewTeamName('')
      refreshAllTeams()
    } catch (e) {
      toast(`Failed to create team: ${e instanceof Error ? e.message : 'unknown error'}`, 'error')
    } finally {
      setCreating(false)
    }
  }

  const handleSetDefault = async (teamUuid: string) => {
    setSettingDefault(true)
    try {
      await updateSystemConfig({ default_team_id: teamUuid === defaultTeamUuid ? '' : teamUuid })
      setDefaultTeamUuid(teamUuid === defaultTeamUuid ? '' : teamUuid)
      refreshAllTeams()
    } catch (e) {
      toast(`Failed to update default team: ${e instanceof Error ? e.message : 'unknown error'}`, 'error')
    } finally {
      setSettingDefault(false)
    }
  }

  const handleExpandTeam = async (teamUuid: string) => {
    if (expandedTeamUuid === teamUuid) {
      setExpandedTeamUuid(null)
      return
    }
    setExpandedTeamUuid(teamUuid)
    if (!teamMembers[teamUuid]) {
      const members = await getTeamMembers(teamUuid)
      setTeamMembers(prev => ({ ...prev, [teamUuid]: members }))
    }
  }

  const handleAddUser = async (teamUuid: string) => {
    const userId = (addUserInputs[teamUuid] || '').trim()
    if (!userId) return
    setAddUserErrors(prev => ({ ...prev, [teamUuid]: '' }))
    setAddUserLoading(prev => ({ ...prev, [teamUuid]: true }))
    try {
      await adminAddUserToTeam(teamUuid, userId)
      setAddUserInputs(prev => ({ ...prev, [teamUuid]: '' }))
      const members = await getTeamMembers(teamUuid)
      setTeamMembers(prev => ({ ...prev, [teamUuid]: members }))
      refreshAllTeams()
      refreshIsolated()
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'User not found'
      setAddUserErrors(prev => ({ ...prev, [teamUuid]: msg }))
    } finally {
      setAddUserLoading(prev => ({ ...prev, [teamUuid]: false }))
    }
  }

  const handleRemoveUser = async (teamUuid: string, userId: string, userName: string) => {
    const ok = await confirm({
      title: 'Remove user from team?',
      message: (
        <>
          Are you sure you want to remove <strong>{userName}</strong> from this team? They will lose access to the team's content.
        </>
      ),
      confirmLabel: 'Remove',
      destructive: true,
    })
    if (!ok) return
    try {
      await adminRemoveUserFromTeam(teamUuid, userId)
      const members = await getTeamMembers(teamUuid)
      setTeamMembers(prev => ({ ...prev, [teamUuid]: members }))
      refreshAllTeams()
      refreshIsolated()
    } catch (e) {
      toast(`Failed to remove ${userName} from team: ${e instanceof Error ? e.message : 'unknown error'}`, 'error')
    }
  }

  const handleAssignIsolated = async (userId: string) => {
    const teamUuid = assignTargets[userId]
    if (!teamUuid) return
    setAssignLoading(prev => ({ ...prev, [userId]: true }))
    try {
      await adminAddUserToTeam(teamUuid, userId)
      setIsolated(prev => prev.filter(u => u.user_id !== userId))
    } catch (e) {
      toast(`Failed to assign user to team: ${e instanceof Error ? e.message : 'unknown error'}`, 'error')
    } finally {
      setAssignLoading(prev => ({ ...prev, [userId]: false }))
    }
  }

  // Stats tab helpers
  const handleSort = (key: string) => {
    setSort(prev => ({ key: key as TeamSortKey, dir: prev.key === key && prev.dir === 'desc' ? 'asc' : 'desc' }))
  }
  const filteredStats = useMemo(() => {
    let list = statsTeams
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(t => t.name.toLowerCase().includes(q))
    }
    return [...list].sort((a, b) => {
      let cmp = 0
      switch (sort.key) {
        case 'name': cmp = a.name.localeCompare(b.name); break
        case 'tokens_total': cmp = a.tokens_total - b.tokens_total; break
        case 'workflows_completed': cmp = a.workflows_completed - b.workflows_completed; break
        case 'active_users': cmp = a.active_users - b.active_users; break
        case 'member_count': cmp = a.member_count - b.member_count; break
        case 'avg_latency_ms': cmp = (a.avg_latency_ms || 0) - (b.avg_latency_ms || 0); break
      }
      return sort.dir === 'asc' ? cmp : -cmp
    })
  }, [statsTeams, search, sort])
  const maxTokens = statsTeams.reduce((max, t) => Math.max(max, t.tokens_total), 1)

  if (selectedTeamId) {
    return <TeamDrillDown teamId={selectedTeamId} onBack={() => setSelectedTeamId(null)} />
  }

  const subTabStyle = (key: string) => ({
    padding: '6px 14px', borderRadius: 8, fontSize: 13, fontWeight: 500, cursor: 'pointer', border: 'none',
    background: subTab === key ? 'var(--highlight-color, #eab308)' : 'transparent',
    color: subTab === key ? 'var(--highlight-text-color, #000)' : '#6b7280',
    fontFamily: 'inherit',
  } as React.CSSProperties)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Sub-tab bar */}
      <div
        role="tablist"
        aria-label="Teams views"
        onKeyDown={e => {
          const keys: Array<'manage' | 'stats' | 'isolated'> = ['manage', 'stats', 'isolated']
          const idx = keys.indexOf(subTab)
          if (idx < 0) return
          let next = idx
          if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = (idx + 1) % keys.length
          else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = (idx - 1 + keys.length) % keys.length
          else if (e.key === 'Home') next = 0
          else if (e.key === 'End') next = keys.length - 1
          else return
          e.preventDefault()
          setSubTab(keys[next])
          const btns = e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')
          btns[next]?.focus()
        }}
        style={{ display: 'flex', alignItems: 'center', gap: 4, background: '#f9fafb', borderRadius: 10, padding: 4, width: 'fit-content' }}
      >
        <button type="button" role="tab" id="admin-teams-tab-manage" aria-controls="admin-teams-panel-manage" aria-selected={subTab === 'manage'} tabIndex={subTab === 'manage' ? 0 : -1} style={subTabStyle('manage')} onClick={() => setSubTab('manage')}>Manage Teams</button>
        <button type="button" role="tab" id="admin-teams-tab-stats" aria-controls="admin-teams-panel-stats" aria-selected={subTab === 'stats'} tabIndex={subTab === 'stats' ? 0 : -1} style={subTabStyle('stats')} onClick={() => setSubTab('stats')}>Usage Stats</button>
        <button type="button" role="tab" id="admin-teams-tab-isolated" aria-controls="admin-teams-panel-isolated" aria-selected={subTab === 'isolated'} tabIndex={subTab === 'isolated' ? 0 : -1} style={subTabStyle('isolated')} onClick={() => setSubTab('isolated')}>
          Isolated Users {isolatedLoaded && isolated.length > 0 ? `(${isolated.length})` : ''}
        </button>
      </div>

      {/* ── Manage Teams ─────────────────────────────────────────── */}
      {subTab === 'manage' && (
        <div role="tabpanel" id="admin-teams-panel-manage" aria-labelledby="admin-teams-tab-manage" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Create team */}
          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: '16px 20px' }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Create New Team</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                value={newTeamName}
                onChange={e => setNewTeamName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleCreateTeam()}
                placeholder="Team name (e.g. Research Administration)"
                style={{ flex: 1, padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 8, fontSize: 14, fontFamily: 'inherit' }}
              />
              <button
                onClick={handleCreateTeam}
                disabled={!newTeamName.trim() || creating}
                style={{
                  padding: '8px 18px', background: 'var(--highlight-color, #eab308)', color: 'var(--highlight-text-color, #000)',
                  border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 600, cursor: 'pointer',
                  opacity: !newTeamName.trim() || creating ? 0.5 : 1, fontFamily: 'inherit',
                  flexShrink: 0, display: 'inline-flex', alignItems: 'center', gap: 4, whiteSpace: 'nowrap',
                }}
              >
                <Plus size={14} />
                Create
              </button>
            </div>
          </div>

          {/* Teams list */}
          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
            <div style={{ padding: '14px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 14, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
              All Teams ({allTeams.length})
              <span style={{ marginLeft: 8, fontSize: 12, fontWeight: 400, color: '#6b7280' }}>
                Click a team to manage its members. Star to set as the default for new users.
              </span>
            </div>
            {allTeamsCapped && (
              <div style={{ padding: '10px 20px', background: '#fffbeb', borderBottom: '1px solid #fde68a', fontSize: 13, color: '#92400e', display: 'flex', alignItems: 'center', gap: 8 }}>
                <AlertCircle size={14} /> Showing the first {allTeams.length} teams only — there are more teams than fit here, and this view has no way to reach them yet.
              </div>
            )}
            {allTeamsError && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '10px 16px', background: '#fef2f2', borderBottom: '1px solid #fecaca',
                color: '#991b1b', fontSize: 13,
              }}>
                <AlertCircle size={14} /> {allTeamsError}
              </div>
            )}
            {loadingAll ? (
              <div style={{ padding: 32, textAlign: 'center', color: '#9ca3af' }}>Loading...</div>
            ) : allTeams.length === 0 ? (
              !allTeamsError && <div style={{ padding: 32, textAlign: 'center', color: '#9ca3af' }}>No teams yet.</div>
            ) : allTeams.map(team => (
              <div key={team.uuid} style={{ borderBottom: '1px solid #f3f4f6' }}>
                {/* Team row */}
                <div
                  style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer' }}
                  onClick={() => handleExpandTeam(team.uuid)}
                  onMouseEnter={e => (e.currentTarget.style.backgroundColor = '#fafafa')}
                  onMouseLeave={e => (e.currentTarget.style.backgroundColor = '')}
                >
                  <div style={{
                    width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                    backgroundColor: team.is_default ? 'rgba(234,179,8,0.15)' : '#ede9fe',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <Building2 size={16} color={team.is_default ? '#b45309' : '#7c3aed'} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
                      {team.name}
                      {team.is_default && (
                        <span style={{ fontSize: 11, background: '#fef3c7', color: '#92400e', padding: '1px 7px', borderRadius: 10, fontWeight: 600 }}>
                          Default
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: 12, color: '#9ca3af', marginTop: 1 }}>
                      {team.member_count} member{team.member_count !== 1 ? 's' : ''}
                    </div>
                  </div>
                  <button
                    onClick={e => { e.stopPropagation(); handleSetDefault(team.uuid) }}
                    disabled={settingDefault}
                    title={team.is_default ? 'Remove as default' : 'Set as default for new users'}
                    style={{
                      padding: '4px 10px', fontSize: 12, fontWeight: 500,
                      border: `1px solid ${team.is_default ? '#fbbf24' : '#e5e7eb'}`,
                      background: team.is_default ? '#fef3c7' : '#fff',
                      color: team.is_default ? '#92400e' : '#6b7280',
                      borderRadius: 6, cursor: 'pointer', fontFamily: 'inherit',
                    }}
                  >
                    {team.is_default ? '★ Default' : '☆ Set Default'}
                  </button>
                  {expandedTeamUuid === team.uuid ? <ChevronUp size={16} color="#9ca3af" /> : <ChevronDown size={16} color="#9ca3af" />}
                </div>

                {/* Expanded member panel */}
                {expandedTeamUuid === team.uuid && (
                  <div style={{ background: '#f9fafb', borderTop: '1px solid #f3f4f6', padding: '12px 20px' }}>
                    {/* Add user */}
                    <div style={{ marginBottom: 12 }}>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <input
                          value={addUserInputs[team.uuid] || ''}
                          onChange={e => {
                            setAddUserInputs(prev => ({ ...prev, [team.uuid]: e.target.value }))
                            setAddUserErrors(prev => ({ ...prev, [team.uuid]: '' }))
                          }}
                          onKeyDown={e => e.key === 'Enter' && handleAddUser(team.uuid)}
                          placeholder="User ID or email address..."
                          style={{
                            flex: 1, padding: '6px 10px', fontSize: 13, fontFamily: 'inherit',
                            border: `1px solid ${addUserErrors[team.uuid] ? '#fca5a5' : '#d1d5db'}`,
                            borderRadius: 6,
                          }}
                        />
                        <button
                          onClick={() => handleAddUser(team.uuid)}
                          disabled={addUserLoading[team.uuid] || !addUserInputs[team.uuid]?.trim()}
                          style={{
                            padding: '6px 14px', background: '#111', color: '#fff',
                            border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                            opacity: addUserLoading[team.uuid] || !addUserInputs[team.uuid]?.trim() ? 0.5 : 1,
                          }}
                        >
                          {addUserLoading[team.uuid] ? 'Adding…' : 'Add'}
                        </button>
                      </div>
                      {addUserErrors[team.uuid] && (
                        <div style={{ marginTop: 4, fontSize: 12, color: '#dc2626' }}>{addUserErrors[team.uuid]}</div>
                      )}
                    </div>

                    {/* Members list */}
                    {(teamMembers[team.uuid] || []).length === 0 ? (
                      <div style={{ fontSize: 13, color: '#9ca3af', textAlign: 'center', padding: '8px 0' }}>No members yet.</div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        {(teamMembers[team.uuid] || []).map(m => (
                          <div key={m.user_id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 8px', background: '#fff', borderRadius: 6, border: '1px solid #f3f4f6' }}>
                            <div style={{ flex: 1 }}>
                              <span style={{ fontSize: 13, fontWeight: 500 }}>{nameWithoutEmail(m.name, m.email) || m.user_id}</span>
                              {m.email && <span style={{ fontSize: 12, color: '#9ca3af', marginLeft: 8 }}>{m.email}</span>}
                            </div>
                            <span style={{
                              fontSize: 11, padding: '2px 7px', borderRadius: 8, fontWeight: 600,
                              background: m.role === 'owner' ? '#ede9fe' : m.role === 'admin' ? '#dbeafe' : '#f3f4f6',
                              color: m.role === 'owner' ? '#6d28d9' : m.role === 'admin' ? '#1d4ed8' : '#374151',
                            }}>
                              {m.role}
                            </span>
                            {m.role !== 'owner' && (
                              <button
                                onClick={() => handleRemoveUser(team.uuid, m.user_id, m.name || m.user_id)}
                                style={{ padding: '3px 8px', background: 'transparent', border: '1px solid #fca5a5', color: '#dc2626', borderRadius: 5, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}
                              >
                                Remove
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Usage Stats ──────────────────────────────────────────── */}
      {subTab === 'stats' && (
        <div role="tabpanel" id="admin-teams-panel-stats" aria-labelledby="admin-teams-tab-stats" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
            <TimeRangeSelector value={statsDays} onChange={setStatsDays} includeAll onRefresh={refreshStats} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <SearchInput value={search} onChange={setSearch} placeholder="Search teams..." />
            <div style={{ flex: 1 }} />
            <ExportButton onClick={() => downloadCSV(
              `teams-${statsDays === 'all' ? 'all' : statsDays + 'd'}.csv`,
              ['Team', 'Tokens', 'Workflows', 'Active Users', 'Members', 'Avg Latency (ms)'],
              filteredStats.map(t => [t.name, t.tokens_total, t.workflows_completed, t.active_users, t.member_count, t.avg_latency_ms])
            )} />
          </div>
          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
            <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 15, fontWeight: 600 }}>
              Team Leaderboard ({filteredStats.length}) {statsDays !== 'all' && <span style={{ fontSize: 12, color: '#6b7280', fontWeight: 400 }}>· last {statsDays} days</span>}
            </div>
            {statsCapped && (
              <div style={{ padding: '10px 20px', background: '#fffbeb', borderBottom: '1px solid #fde68a', fontSize: 13, color: '#92400e', display: 'flex', alignItems: 'center', gap: 8 }}>
                <AlertCircle size={14} /> Showing the top {statsTeams.length} teams by token usage — this list is truncated. Sorting and export cover only these loaded rows, not every team.
              </div>
            )}
            {statsError && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '10px 16px', background: '#fef2f2', borderBottom: '1px solid #fecaca',
                color: '#991b1b', fontSize: 13,
              }}>
                <AlertCircle size={14} /> {statsError}
              </div>
            )}
            {loadingStats ? (
              <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading...</div>
            ) : filteredStats.length === 0 ? (
              !statsError && <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No teams found.</div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                    <SortableHeader label="Team" sortKey="name" currentSort={sort} onSort={handleSort} />
                    <SortableHeader label="Token Usage" sortKey="tokens_total" currentSort={sort} onSort={handleSort} />
                    <SortableHeader label="Workflows" sortKey="workflows_completed" currentSort={sort} onSort={handleSort} align="right" />
                    <SortableHeader label="Active Users" sortKey="active_users" currentSort={sort} onSort={handleSort} align="right" />
                    <SortableHeader label="Members" sortKey="member_count" currentSort={sort} onSort={handleSort} align="right" />
                    <SortableHeader label="Avg Latency" sortKey="avg_latency_ms" currentSort={sort} onSort={handleSort} align="right" />
                  </tr>
                </thead>
                <tbody>
                  {filteredStats.map((t) => (
                    <tr key={t.team_id} tabIndex={0} role="button" aria-label={`View team ${t.name || t.team_id}`} onClick={() => setSelectedTeamId(t.team_id)} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSelectedTeamId(t.team_id) } }} style={{ borderBottom: '1px solid #f3f4f6', cursor: 'pointer' }} onMouseEnter={e => (e.currentTarget.style.backgroundColor = '#f9fafb')} onMouseLeave={e => (e.currentTarget.style.backgroundColor = '')}>
                      <td style={{ padding: '12px 16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <div style={{ width: 32, height: 32, borderRadius: 'var(--ui-radius, 12px)', backgroundColor: '#ede9fe', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                            <Building2 size={16} color="#7c3aed" />
                          </div>
                          <div style={{ fontSize: 14, fontWeight: 500 }}>{t.name}</div>
                        </div>
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <div style={{ flex: 1, height: 6, backgroundColor: '#f3f4f6', borderRadius: 3, overflow: 'hidden' }}>
                            <div style={{ width: `${(t.tokens_total / maxTokens) * 100}%`, height: '100%', backgroundColor: 'var(--highlight-color, #eab308)', borderRadius: 3 }} />
                          </div>
                          <span style={{ fontSize: 13, fontFamily: 'ui-monospace, monospace', color: '#374151', minWidth: 60, textAlign: 'right' }}>{formatNumber(t.tokens_total)}</span>
                        </div>
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'right', fontSize: 14, fontFamily: 'ui-monospace, monospace' }}>{t.workflows_completed}</td>
                      <td style={{ padding: '12px 16px', textAlign: 'right', fontSize: 14, fontFamily: 'ui-monospace, monospace' }}>{t.active_users}</td>
                      <td style={{ padding: '12px 16px', textAlign: 'right', fontSize: 14, fontFamily: 'ui-monospace, monospace' }}>{t.member_count}</td>
                      <td style={{ padding: '12px 16px', textAlign: 'right', fontSize: 13, color: '#6b7280' }}>{formatDuration(t.avg_latency_ms)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* ── Isolated Users ───────────────────────────────────────── */}
      {subTab === 'isolated' && (
        <div role="tabpanel" id="admin-teams-panel-isolated" aria-labelledby="admin-teams-tab-isolated" style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
          <div style={{ padding: '14px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 14, fontWeight: 600 }}>
            Isolated Users (only on their personal team) ({isolated.length})
          </div>
          {isolatedCapped && (
            <div style={{ padding: '10px 20px', background: '#fffbeb', borderBottom: '1px solid #fde68a', fontSize: 13, color: '#92400e', display: 'flex', alignItems: 'center', gap: 8 }}>
              <AlertCircle size={14} /> Showing the first {isolated.length} isolated users only — there are more than fit here.
            </div>
          )}
          {isolatedError && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '10px 16px', background: '#fef2f2', borderBottom: '1px solid #fecaca',
              color: '#991b1b', fontSize: 13,
            }}>
              <AlertCircle size={14} /> {isolatedError}
            </div>
          )}
          {loadingIsolated && !isolatedLoaded ? (
            <div style={{ padding: 32, textAlign: 'center', color: '#9ca3af' }}>Loading...</div>
          ) : isolated.length === 0 ? (
            !isolatedError && (
              <div style={{ padding: 32, textAlign: 'center', color: '#6b7280' }}>
                No isolated users. Everyone is on at least one shared team.
              </div>
            )
          ) : isolated.map(u => (
            <div key={u.user_id} style={{ padding: '12px 20px', borderBottom: '1px solid #f3f4f6', display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 500 }}>{nameWithoutEmail(u.name, u.email) || u.user_id}</div>
                {u.email && <div style={{ fontSize: 12, color: '#9ca3af' }}>{u.email}</div>}
              </div>
              <select
                value={assignTargets[u.user_id] || ''}
                onChange={e => setAssignTargets(prev => ({ ...prev, [u.user_id]: e.target.value }))}
                style={{ padding: '6px 10px', border: '1px solid #d1d5db', borderRadius: 6, fontSize: 13, fontFamily: 'inherit' }}
              >
                <option value="">Select team...</option>
                {allTeams.map(t => (
                  <option key={t.uuid} value={t.uuid}>{t.name}{t.is_default ? ' (default)' : ''}</option>
                ))}
              </select>
              <button
                onClick={() => handleAssignIsolated(u.user_id)}
                disabled={!assignTargets[u.user_id] || assignLoading[u.user_id]}
                style={{
                  padding: '6px 14px', background: 'var(--highlight-color, #eab308)', color: 'var(--highlight-text-color, #000)',
                  border: 'none', borderRadius: 6, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit',
                  opacity: !assignTargets[u.user_id] || assignLoading[u.user_id] ? 0.5 : 1,
                  flexShrink: 0, whiteSpace: 'nowrap',
                }}
              >
                Add to Team
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
