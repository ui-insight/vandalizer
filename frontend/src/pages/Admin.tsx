import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react'
import {
  Shield, ShieldCheck, BarChart3, Users, Building2, Workflow, Settings,
  Palette, Cpu, Lock, Globe, Plus, Trash2, Pencil, ChevronLeft,
  ChevronRight, RefreshCw, MessageSquare, Search, Zap, Bug,
  CheckCircle2, XCircle, Clock, Download, TrendingUp, TrendingDown,
  ChevronDown, ChevronUp, ArrowUpDown, Play, Minus, AlertCircle,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
  LineChart, Line,
} from 'recharts'
import { PageLayout } from '../components/layout/PageLayout'
import { useAuth } from '../hooks/useAuth'
import { useTeams } from '../hooks/useTeams'
import { getThemeConfig, updateThemeConfig } from '../api/config'
import type { ThemeConfig } from '../api/config'
import {
  getUsageStats, getUsageTimeseries, getUserLeaderboard, getTeamLeaderboard,
  getWorkflowEvents, getSystemConfig, updateSystemConfig,
  addModel, updateModel, deleteModel, addOAuthProvider, updateOAuthProvider,
  deleteOAuthProvider, updateAuthMethods,
  getQualitySummary, getQualityTimeline, runRegressionSuite,
  getQualityAlerts, acknowledgeAlert, getQualityItems, getQualityItemDetail,
} from '../api/admin'
import {
  getDemoStats, getDemoApplications, releaseDemoUser, activateDemoUser,
  getPostExperienceResponses,
} from '../api/demo'
import type { DemoAdminStats, DemoApplication as DemoApp, PostExperienceResponseAdmin } from '../types/demo'
import { POST_SURVEY_FIELDS } from '../components/survey/postSurveyFields'
import { SurveyFieldRenderer } from '../components/survey/SurveyFieldRenderer'
import type {
  UsageStats, TimeseriesResponse, UserLeaderboardItem, TeamLeaderboardItem,
  WorkflowEventItem, PaginatedWorkflows, SystemConfigData,
  QualitySummary, QualityTimelinePoint, RegressionResult,
  QualityAlert, QualityItem, QualityItemDetail,
} from '../api/admin'
import { relativeTime } from '../utils/time'

function applyThemeToDOM(theme: ThemeConfig) {
  const root = document.documentElement
  root.style.setProperty('--highlight-color', theme.highlight_color)
  root.style.setProperty('--ui-radius', theme.ui_radius)
}

type Tab = 'usage' | 'users' | 'teams' | 'workflows' | 'quality' | 'demo' | 'debugging' | 'config'

const TABS: { key: Tab; label: string; icon: typeof BarChart3 }[] = [
  { key: 'usage', label: 'Usage', icon: BarChart3 },
  { key: 'users', label: 'Users', icon: Users },
  { key: 'teams', label: 'Teams', icon: Building2 },
  { key: 'workflows', label: 'Workflows', icon: Workflow },
  { key: 'quality', label: 'Quality', icon: ShieldCheck },
  { key: 'demo', label: 'Demo', icon: Zap },
  { key: 'debugging', label: 'Debugging', icon: Bug },
  { key: 'config', label: 'Config', icon: Settings },
]

const CHART_COLORS = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4']

function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return n.toString()
}

function formatDate(d: string | null): string {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatDateTime(d: string | null): string {
  if (!d) return '-'
  return new Date(d).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function formatDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return '-'
  if (ms < 1000) return `${ms}ms`
  const secs = ms / 1000
  if (secs < 60) return `${secs.toFixed(1)}s`
  const mins = Math.floor(secs / 60)
  const remainSecs = Math.round(secs % 60)
  return `${mins}m ${remainSecs}s`
}

function downloadCSV(filename: string, headers: string[], rows: (string | number | null)[][]) {
  const escape = (v: string | number | null) => {
    if (v === null || v === undefined) return ''
    const s = String(v)
    return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s
  }
  const csv = [headers.join(','), ...rows.map(r => r.map(escape).join(','))].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    completed: { bg: '#dcfce7', text: '#166534' },
    failed: { bg: '#fee2e2', text: '#991b1b' },
    error: { bg: '#fee2e2', text: '#991b1b' },
    running: { bg: '#dbeafe', text: '#1e40af' },
    queued: { bg: '#e0e7ff', text: '#3730a3' },
    canceled: { bg: '#fef3c7', text: '#92400e' },
  }
  const c = colors[status] || { bg: '#f3f4f6', text: '#374151' }
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: 9999,
      fontSize: 12, fontWeight: 600, backgroundColor: c.bg, color: c.text,
    }}>
      {status}
    </span>
  )
}

function RoleBadge({ role }: { role: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    admin: { bg: '#fef3c7', text: '#92400e' },
    examiner: { bg: '#dbeafe', text: '#1e40af' },
  }
  const c = colors[role] || { bg: '#f3f4f6', text: '#374151' }
  return (
    <span style={{
      display: 'inline-block', padding: '1px 8px', borderRadius: 9999,
      fontSize: 10, fontWeight: 700, backgroundColor: c.bg, color: c.text,
      textTransform: 'uppercase', letterSpacing: 0.5,
    }}>
      {role}
    </span>
  )
}

function TrendDelta({ current, previous, invert }: { current: number; previous: number; invert?: boolean }) {
  if (previous === 0 && current === 0) return null
  const pct = previous === 0 ? 100 : Math.round(((current - previous) / previous) * 100)
  const isUp = pct > 0
  const isGood = invert ? !isUp : isUp
  if (pct === 0) return <span style={{ fontSize: 11, color: '#9ca3af' }}>0%</span>
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2, fontSize: 11, fontWeight: 600, color: isGood ? '#16a34a' : '#dc2626' }}>
      {isUp ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
      {isUp ? '+' : ''}{pct}%
    </span>
  )
}

function KpiCard({ label, value, icon: Icon, color, trend }: {
  label: string; value: string | number; icon: typeof BarChart3; color: string
  trend?: { current: number; previous: number; invert?: boolean }
}) {
  return (
    <div style={{
      background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)',
      padding: '20px', display: 'flex', alignItems: 'center', gap: 16,
    }}>
      <div style={{
        width: 44, height: 44, borderRadius: 'var(--ui-radius, 12px)', backgroundColor: color + '18',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        <Icon size={22} color={color} />
      </div>
      <div>
        <div style={{ fontSize: 13, color: '#6b7280', textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 500 }}>{label}</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <div style={{ fontSize: 26, fontWeight: 700, color: '#111827', fontFamily: 'ui-monospace, monospace' }}>{value}</div>
          {trend && <TrendDelta current={trend.current} previous={trend.previous} invert={trend.invert} />}
        </div>
      </div>
    </div>
  )
}

function UserAvatar({ name }: { name: string | null }) {
  const letter = (name || '?')[0].toUpperCase()
  const hue = (letter.charCodeAt(0) * 37) % 360
  return (
    <div style={{
      width: 32, height: 32, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
      backgroundColor: `hsl(${hue}, 55%, 88%)`, color: `hsl(${hue}, 55%, 35%)`, fontWeight: 700, fontSize: 14, flexShrink: 0,
    }}>
      {letter}
    </div>
  )
}

function SortableHeader({ label, sortKey, currentSort, onSort }: {
  label: string; sortKey: string
  currentSort: { key: string; dir: 'asc' | 'desc' }
  onSort: (key: string) => void
}) {
  const active = currentSort.key === sortKey
  return (
    <th
      onClick={() => onSort(sortKey)}
      style={{
        padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280',
        textTransform: 'uppercase', cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap',
      }}
    >
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
        {label}
        {active ? (currentSort.dir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />) : <ArrowUpDown size={10} style={{ opacity: 0.4 }} />}
      </span>
    </th>
  )
}

function SearchInput({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <div style={{ position: 'relative', maxWidth: 300 }}>
      <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#9ca3af' }} />
      <input
        type="text"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        style={{
          width: '100%', padding: '7px 12px 7px 32px', borderRadius: 'var(--ui-radius, 12px)',
          border: '1px solid #e5e7eb', fontSize: 13, outline: 'none',
        }}
      />
    </div>
  )
}

function ExportButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 6, padding: '6px 14px',
        borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #e5e7eb',
        fontSize: 12, fontWeight: 500, cursor: 'pointer', background: '#fff', color: '#374151',
      }}
    >
      <Download size={13} /> Export CSV
    </button>
  )
}

// ──────────────────────────────────────────
// Usage Tab
// ──────────────────────────────────────────

function UsageTab() {
  const [stats, setStats] = useState<UsageStats | null>(null)
  const [timeseries, setTimeseries] = useState<TimeseriesResponse | null>(null)
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([getUsageStats(days), getUsageTimeseries(days)])
      .then(([s, ts]) => { setStats(s); setTimeseries(ts) })
      .finally(() => setLoading(false))
  }, [days])

  useEffect(() => { load() }, [load])

  const prev = timeseries?.previous_period

  // Token donut data
  const tokenDonut = stats ? [
    { name: 'Input', value: stats.tokens_in },
    { name: 'Output', value: stats.tokens_out },
  ] : []

  // Workflow status donut
  const workflowDonut = stats ? [
    { name: 'Completed', value: stats.workflows_completed },
    { name: 'Failed', value: stats.workflows_failed },
    { name: 'Other', value: Math.max(0, stats.workflows_started - stats.workflows_completed - stats.workflows_failed) },
  ].filter(d => d.value > 0) : []

  if (loading && !stats) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading usage data...</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Time range selector */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 13, color: '#6b7280', fontWeight: 500 }}>Time Range:</span>
        {[7, 14, 30, 90].map(d => (
          <button
            key={d}
            onClick={() => setDays(d)}
            style={{
              padding: '5px 14px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #e5e7eb',
              fontSize: 13, fontWeight: 500, cursor: 'pointer',
              backgroundColor: days === d ? 'var(--highlight-color, #eab308)' : '#fff',
              color: days === d ? 'var(--highlight-text-color, #000)' : '#374151',
            }}
          >
            {d}d
          </button>
        ))}
        <button onClick={load} style={{ marginLeft: 8, background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: 4 }}>
          <RefreshCw size={16} />
        </button>
      </div>

      {stats && (
        <>
          {/* KPI Grid with trend deltas */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
            <KpiCard label="Conversations" value={formatNumber(stats.conversations)} icon={MessageSquare} color="#3b82f6" trend={prev ? { current: stats.conversations, previous: prev.conversations } : undefined} />
            <KpiCard label="Search Runs" value={formatNumber(stats.search_runs)} icon={Search} color="#8b5cf6" trend={prev ? { current: stats.search_runs, previous: prev.search_runs } : undefined} />
            <KpiCard label="Workflows Started" value={formatNumber(stats.workflows_started)} icon={Zap} color="#f59e0b" trend={prev ? { current: stats.workflows_started, previous: prev.workflows_started } : undefined} />
            <KpiCard label="Completed" value={formatNumber(stats.workflows_completed)} icon={CheckCircle2} color="#22c55e" trend={prev ? { current: stats.workflows_completed, previous: prev.workflows_completed } : undefined} />
            <KpiCard label="Failed" value={formatNumber(stats.workflows_failed)} icon={XCircle} color="#ef4444" trend={prev ? { current: stats.workflows_failed, previous: prev.workflows_failed, invert: true } : undefined} />
            <KpiCard label="Active Users" value={formatNumber(stats.active_users)} icon={Users} color="#06b6d4" trend={prev ? { current: stats.active_users, previous: prev.active_users } : undefined} />
          </div>

          {/* Daily Activity Chart */}
          {timeseries && timeseries.days.length > 0 && (
            <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Daily Activity</div>
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={timeseries.days}>
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

          {/* Token + Workflow donut charts side by side */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Token Breakdown</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 16 }}>
                <div>
                  <div style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase', marginBottom: 4 }}>Input Tokens</div>
                  <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'ui-monospace, monospace' }}>{formatNumber(stats.tokens_in)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase', marginBottom: 4 }}>Output Tokens</div>
                  <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'ui-monospace, monospace' }}>{formatNumber(stats.tokens_out)}</div>
                </div>
              </div>
              {(stats.tokens_in + stats.tokens_out) > 0 && (
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie data={tokenDonut} cx="50%" cy="50%" innerRadius={50} outerRadius={75} paddingAngle={3} dataKey="value">
                      {tokenDonut.map((_, i) => <Cell key={i} fill={CHART_COLORS[i]} />)}
                    </Pie>
                    <Tooltip formatter={(v: number) => formatNumber(v)} contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                    <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>

            <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Workflow Status</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 16 }}>
                <div>
                  <div style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase', marginBottom: 4 }}>Success Rate</div>
                  <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'ui-monospace, monospace' }}>
                    {stats.workflows_started > 0 ? `${Math.round((stats.workflows_completed / stats.workflows_started) * 100)}%` : '-'}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase', marginBottom: 4 }}>Total</div>
                  <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'ui-monospace, monospace' }}>{formatNumber(stats.tokens_in + stats.tokens_out)}</div>
                </div>
              </div>
              {workflowDonut.length > 0 && (
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie data={workflowDonut} cx="50%" cy="50%" innerRadius={50} outerRadius={75} paddingAngle={3} dataKey="value">
                      {workflowDonut.map((_, i) => <Cell key={i} fill={[CHART_COLORS[1], CHART_COLORS[3], CHART_COLORS[5]][i]} />)}
                    </Pie>
                    <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                    <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* Summary cards */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Active Teams</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <div style={{ fontSize: 36, fontWeight: 700, color: 'var(--highlight-color, #eab308)' }}>{stats.active_teams}</div>
                {prev && <TrendDelta current={stats.active_teams} previous={prev.active_teams} />}
              </div>
              <div style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>in the last {days} days</div>
            </div>
            <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Active Users</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <div style={{ fontSize: 36, fontWeight: 700, color: 'var(--highlight-color, #eab308)' }}>{stats.active_users}</div>
                {prev && <TrendDelta current={stats.active_users} previous={prev.active_users} />}
              </div>
              <div style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>in the last {days} days</div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ──────────────────────────────────────────
// Users Tab
// ──────────────────────────────────────────

type UserSortKey = 'tokens_total' | 'workflows_run' | 'conversations' | 'last_active' | 'name'

function UsersTab() {
  const [users, setUsers] = useState<UserLeaderboardItem[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<{ key: UserSortKey; dir: 'asc' | 'desc' }>({ key: 'tokens_total', dir: 'desc' })

  useEffect(() => {
    getUserLeaderboard().then(setUsers).finally(() => setLoading(false))
  }, [])

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

  const maxTokens = users.length > 0 ? Math.max(...users.map(u => u.tokens_total), 1) : 1

  const handleExport = () => {
    downloadCSV('users.csv',
      ['#', 'Name', 'Email', 'Roles', 'Tokens', 'Workflows', 'Conversations', 'Last Active'],
      filtered.map((u, i) => [
        i + 1, u.name, u.email,
        [u.is_admin ? 'admin' : '', u.is_examiner ? 'examiner' : ''].filter(Boolean).join(', '),
        u.tokens_total, u.workflows_run, u.conversations, u.last_active,
      ])
    )
  }

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading users...</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <SearchInput value={search} onChange={setSearch} placeholder="Search users..." />
        <div style={{ flex: 1 }} />
        <ExportButton onClick={handleExport} />
      </div>

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 15, fontWeight: 600 }}>
          User Leaderboard ({filtered.length})
        </div>
        {filtered.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No users found.</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>#</th>
                <SortableHeader label="User" sortKey="name" currentSort={sort} onSort={handleSort} />
                <SortableHeader label="Token Usage" sortKey="tokens_total" currentSort={sort} onSort={handleSort} />
                <SortableHeader label="Workflows" sortKey="workflows_run" currentSort={sort} onSort={handleSort} />
                <SortableHeader label="Chats" sortKey="conversations" currentSort={sort} onSort={handleSort} />
                <SortableHeader label="Last Active" sortKey="last_active" currentSort={sort} onSort={handleSort} />
              </tr>
            </thead>
            <tbody>
              {filtered.map((u, i) => (
                <tr key={u.user_id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '12px 16px', fontSize: 14, fontWeight: 600, color: '#9ca3af' }}>{i + 1}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <UserAvatar name={u.name || u.email} />
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{ fontSize: 14, fontWeight: 500 }}>{u.name || 'Unknown'}</span>
                          {u.is_admin && <RoleBadge role="admin" />}
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

// ──────────────────────────────────────────
// Teams Tab
// ──────────────────────────────────────────

type TeamSortKey = 'name' | 'tokens_total' | 'workflows_completed' | 'active_users' | 'member_count' | 'avg_latency_ms'

function TeamsTab() {
  const [teams, setTeams] = useState<TeamLeaderboardItem[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<{ key: TeamSortKey; dir: 'asc' | 'desc' }>({ key: 'tokens_total', dir: 'desc' })

  useEffect(() => {
    getTeamLeaderboard().then(setTeams).finally(() => setLoading(false))
  }, [])

  const handleSort = (key: string) => {
    setSort(prev => ({
      key: key as TeamSortKey,
      dir: prev.key === key && prev.dir === 'desc' ? 'asc' : 'desc',
    }))
  }

  const filtered = useMemo(() => {
    let list = teams
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(t => t.name.toLowerCase().includes(q))
    }
    const sorted = [...list].sort((a, b) => {
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
    return sorted
  }, [teams, search, sort])

  const maxTokens = teams.length > 0 ? Math.max(...teams.map(t => t.tokens_total), 1) : 1

  const handleExport = () => {
    downloadCSV('teams.csv',
      ['Team', 'Tokens', 'Workflows', 'Active Users', 'Members', 'Avg Latency (ms)'],
      filtered.map(t => [t.name, t.tokens_total, t.workflows_completed, t.active_users, t.member_count, t.avg_latency_ms])
    )
  }

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading teams...</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <SearchInput value={search} onChange={setSearch} placeholder="Search teams..." />
        <div style={{ flex: 1 }} />
        <ExportButton onClick={handleExport} />
      </div>

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
        <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 15, fontWeight: 600 }}>
          Team Leaderboard ({filtered.length})
        </div>
        {filtered.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No teams found.</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                <SortableHeader label="Team" sortKey="name" currentSort={sort} onSort={handleSort} />
                <SortableHeader label="Token Usage" sortKey="tokens_total" currentSort={sort} onSort={handleSort} />
                <SortableHeader label="Workflows" sortKey="workflows_completed" currentSort={sort} onSort={handleSort} />
                <SortableHeader label="Active Users" sortKey="active_users" currentSort={sort} onSort={handleSort} />
                <SortableHeader label="Members" sortKey="member_count" currentSort={sort} onSort={handleSort} />
                <SortableHeader label="Avg Latency" sortKey="avg_latency_ms" currentSort={sort} onSort={handleSort} />
              </tr>
            </thead>
            <tbody>
              {filtered.map((t) => (
                <tr key={t.team_id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{
                        width: 32, height: 32, borderRadius: 'var(--ui-radius, 12px)', backgroundColor: '#ede9fe',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                      }}>
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
                      <span style={{ fontSize: 13, fontFamily: 'ui-monospace, monospace', color: '#374151', minWidth: 60, textAlign: 'right' }}>
                        {formatNumber(t.tokens_total)}
                      </span>
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
  )
}

// ──────────────────────────────────────────
// Workflows Tab
// ──────────────────────────────────────────

function WorkflowsTab() {
  const [data, setData] = useState<PaginatedWorkflows | null>(null)
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState<string>('')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const searchDebounce = useRef<ReturnType<typeof setTimeout>>()

  const load = useCallback(() => {
    setLoading(true)
    getWorkflowEvents(page, status || undefined, search || undefined).then(setData).finally(() => setLoading(false))
  }, [page, status, search])

  useEffect(() => { load() }, [load])

  const handleSearchChange = (v: string) => {
    if (searchDebounce.current) clearTimeout(searchDebounce.current)
    searchDebounce.current = setTimeout(() => { setSearch(v); setPage(1) }, 400)
  }

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
        <SearchInput value="" onChange={handleSearchChange} placeholder="Search workflows..." />
        <ExportButton onClick={handleExport} />
      </div>

      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
        {loading && !data ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading workflows...</div>
        ) : !data || data.items.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No workflow events found.</div>
        ) : (
          <>
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
                    <tr key={ev.id} style={{ borderBottom: '1px solid #f3f4f6', cursor: 'pointer' }} onClick={() => setExpandedId(isExpanded ? null : ev.id)}>
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

// ──────────────────────────────────────────
// Quality Tab
// ──────────────────────────────────────────

function QualityTab() {
  const [summary, setSummary] = useState<QualitySummary | null>(null)
  const [timeline, setTimeline] = useState<QualityTimelinePoint[]>([])
  const [days, setDays] = useState(90)
  const [loading, setLoading] = useState(true)
  const [regressionResult, setRegressionResult] = useState<RegressionResult | null>(null)
  const [regressionRunning, setRegressionRunning] = useState(false)
  const [regressionModel, setRegressionModel] = useState('')
  const [cfg, setCfg] = useState<SystemConfigData | null>(null)

  // Alert feed state
  const [alerts, setAlerts] = useState<QualityAlert[]>([])

  // Per-item quality state
  const [qualityItems, setQualityItems] = useState<QualityItem[]>([])
  const [expandedItem, setExpandedItem] = useState<{ kind: string; id: string } | null>(null)
  const [itemDetail, setItemDetail] = useState<QualityItemDetail | null>(null)
  const [itemSort, setItemSort] = useState<{ key: string; dir: 'asc' | 'desc' }>({ key: 'score', dir: 'asc' })

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([
      getQualitySummary(),
      getQualityTimeline(days),
      getSystemConfig(),
      getQualityAlerts(50, false),
      getQualityItems('score', 'asc', 100),
    ]).then(([s, t, c, a, qi]) => {
      setSummary(s)
      setTimeline(t.timeline)
      setCfg(c)
      setAlerts(a.alerts)
      setQualityItems(qi.items)
    }).finally(() => setLoading(false))
  }, [days])

  useEffect(() => { load() }, [load])

  const handleRunRegression = async () => {
    setRegressionRunning(true)
    try {
      const result = await runRegressionSuite(regressionModel || undefined)
      setRegressionResult(result)
    } finally {
      setRegressionRunning(false)
    }
  }

  const handleAcknowledgeAlert = async (uuid: string) => {
    await acknowledgeAlert(uuid)
    setAlerts(prev => prev.filter(a => a.uuid !== uuid))
  }

  const handleExpandItem = async (kind: string, id: string) => {
    if (expandedItem?.kind === kind && expandedItem?.id === id) {
      setExpandedItem(null)
      setItemDetail(null)
      return
    }
    setExpandedItem({ kind, id })
    setItemDetail(null)
    const detail = await getQualityItemDetail(kind, id)
    setItemDetail(detail)
  }

  const handleItemSort = (key: string) => {
    setItemSort(prev => ({
      key,
      dir: prev.key === key && prev.dir === 'desc' ? 'asc' : 'desc',
    }))
  }

  const sortedQualityItems = useMemo(() => {
    const list = [...qualityItems]
    list.sort((a, b) => {
      let cmp = 0
      switch (itemSort.key) {
        case 'name': cmp = a.display_name.localeCompare(b.display_name); break
        case 'kind': cmp = a.item_kind.localeCompare(b.item_kind); break
        case 'score': cmp = (a.quality_score ?? -1) - (b.quality_score ?? -1); break
        case 'tier': cmp = (a.quality_tier || '').localeCompare(b.quality_tier || ''); break
        case 'last_validated': cmp = (a.last_validated_at || '').localeCompare(b.last_validated_at || ''); break
        case 'runs': cmp = a.validation_run_count - b.validation_run_count; break
      }
      return itemSort.dir === 'asc' ? cmp : -cmp
    })
    return list
  }, [qualityItems, itemSort])

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading quality data...</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Alert Feed Panel */}
      {alerts.length > 0 && (
        <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
          <div style={{
            padding: '14px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 15, fontWeight: 600,
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <AlertCircle size={16} color="#f59e0b" />
            Quality Alerts ({alerts.length})
          </div>
          <div style={{ maxHeight: 320, overflowY: 'auto' }}>
            {alerts.map(alert => {
              const severityColors: Record<string, { bg: string; text: string; border: string }> = {
                info: { bg: '#eff6ff', text: '#1e40af', border: '#bfdbfe' },
                warning: { bg: '#fffbeb', text: '#92400e', border: '#fde68a' },
                critical: { bg: '#fef2f2', text: '#991b1b', border: '#fecaca' },
              }
              const sc = severityColors[alert.severity] || severityColors.info
              return (
                <div
                  key={alert.uuid}
                  style={{
                    padding: '12px 20px', borderBottom: '1px solid #f3f4f6',
                    display: 'flex', alignItems: 'center', gap: 12,
                  }}
                >
                  <span style={{
                    display: 'inline-block', padding: '2px 10px', borderRadius: 9999,
                    fontSize: 11, fontWeight: 700, textTransform: 'uppercase',
                    backgroundColor: sc.bg, color: sc.text, border: `1px solid ${sc.border}`,
                    flexShrink: 0,
                  }}>
                    {alert.severity}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>{alert.item_name}</div>
                    <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                      {alert.message}
                      {alert.alert_type === 'regression' && alert.previous_score != null && alert.current_score != null && (
                        <span style={{
                          marginLeft: 8, fontFamily: 'ui-monospace, monospace', fontWeight: 600,
                          color: '#dc2626',
                        }}>
                          {alert.previous_score} &rarr; {alert.current_score}
                        </span>
                      )}
                    </div>
                  </div>
                  <span style={{ fontSize: 11, color: '#9ca3af', flexShrink: 0, whiteSpace: 'nowrap' }}>
                    {alert.created_at ? relativeTime(alert.created_at) : '-'}
                  </span>
                  <button
                    onClick={() => handleAcknowledgeAlert(alert.uuid)}
                    style={{
                      padding: '4px 12px', borderRadius: 'var(--ui-radius, 12px)',
                      border: '1px solid #e5e7eb', background: '#fff', fontSize: 12,
                      fontWeight: 500, cursor: 'pointer', color: '#374151',
                      flexShrink: 0, display: 'flex', alignItems: 'center', gap: 4,
                    }}
                  >
                    <CheckCircle2 size={12} /> Acknowledge
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Summary KPI Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
        <KpiCard label="Avg Quality Score" value={summary ? `${summary.avg_score}%` : '-'} icon={ShieldCheck} color="#22c55e" />
        <KpiCard label="Total Runs" value={summary?.total_runs ?? '-'} icon={BarChart3} color="#3b82f6" />
        <KpiCard label="Items Validated" value={summary ? `${summary.items_validated}/${summary.total_verified}` : '-'} icon={CheckCircle2} color="#8b5cf6" />
        <KpiCard label="Below Threshold" value={summary?.items_below_threshold ?? '-'} icon={XCircle} color="#ef4444" />
      </div>

      {/* Quality Timeline Chart */}
      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h3 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>Quality Timeline</h3>
          <select
            value={days}
            onChange={e => setDays(Number(e.target.value))}
            style={{ padding: '4px 8px', fontSize: 12, borderRadius: 6, border: '1px solid #e5e7eb' }}
          >
            <option value={30}>30 days</option>
            <option value={60}>60 days</option>
            <option value={90}>90 days</option>
            <option value={180}>180 days</option>
          </select>
        </div>
        {timeline.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px 0', color: '#9ca3af', fontSize: 13 }}>
            No validation data yet. Run validation on items to see the timeline.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={timeline}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} tickLine={false} axisLine={{ stroke: '#e5e7eb' }} />
              <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} tickLine={false} axisLine={{ stroke: '#e5e7eb' }} />
              <Tooltip
                contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 }}
                formatter={(value: number) => [`${value}%`, 'Avg Score']}
              />
              <Line type="monotone" dataKey="avg_score" stroke="#22c55e" strokeWidth={2} dot={false} name="Avg Score" />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Regression Suite Panel */}
      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
        <h3 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 12px' }}>Regression Suite</h3>
        <p style={{ fontSize: 13, color: '#6b7280', margin: '0 0 16px' }}>
          Run validation on all verified items to detect quality regressions after model or configuration changes.
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <select
            value={regressionModel}
            onChange={e => setRegressionModel(e.target.value)}
            style={{ padding: '6px 12px', fontSize: 13, borderRadius: 6, border: '1px solid #e5e7eb', minWidth: 200 }}
          >
            <option value="">Default Model</option>
            {cfg?.available_models?.map((m, i) => (
              <option key={i} value={m.name}>{m.name} ({m.tag})</option>
            ))}
          </select>
          <button
            onClick={handleRunRegression}
            disabled={regressionRunning}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 16px', borderRadius: 'var(--ui-radius, 12px)',
              border: 'none', background: '#111827', color: '#fff',
              fontSize: 13, fontWeight: 600, cursor: regressionRunning ? 'wait' : 'pointer',
              opacity: regressionRunning ? 0.6 : 1,
            }}
          >
            {regressionRunning ? (
              <><RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} /> Running...</>
            ) : (
              <><Play size={14} /> Run Regression Suite</>
            )}
          </button>
        </div>

        {regressionResult && (
          <div>
            <div style={{ display: 'flex', gap: 16, marginBottom: 12, fontSize: 13 }}>
              <span style={{ color: '#6b7280' }}>Total: <strong>{regressionResult.total_items}</strong></span>
              <span style={{ color: '#16a34a' }}>Succeeded: <strong>{regressionResult.succeeded}</strong></span>
              <span style={{ color: '#dc2626' }}>Failed: <strong>{regressionResult.failed}</strong></span>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>Name</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>Kind</th>
                    <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>Score</th>
                    <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>Grade</th>
                    <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>Delta</th>
                    <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {regressionResult.results.map((r, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                      <td style={{ padding: '8px 12px', fontWeight: 500 }}>{r.name}</td>
                      <td style={{ padding: '8px 12px' }}>
                        <span style={{
                          fontSize: 11, padding: '1px 8px', borderRadius: 9999,
                          background: r.kind === 'workflow' ? '#f3e8ff' : '#e0f2fe',
                          color: r.kind === 'workflow' ? '#7c3aed' : '#0369a1',
                        }}>{r.kind}</span>
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', fontFamily: 'ui-monospace, monospace' }}>
                        {r.score != null ? `${r.score}%` : '-'}
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 700 }}>
                        {r.grade || '-'}
                      </td>
                      <td style={{
                        padding: '8px 12px', textAlign: 'right', fontWeight: 600,
                        color: r.delta == null ? '#9ca3af' : r.delta > 0 ? '#16a34a' : r.delta < 0 ? '#dc2626' : '#9ca3af',
                      }}>
                        {r.delta == null ? '-' : r.delta > 0 ? `+${r.delta}` : r.delta}
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                        {r.status === 'ok' ? (
                          <CheckCircle2 size={16} color="#16a34a" />
                        ) : (
                          <span style={{ fontSize: 11, color: '#dc2626' }}>{r.status}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* Per-Item Quality Table */}
      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
        <div style={{ padding: '14px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 15, fontWeight: 600 }}>
          Per-Item Quality ({qualityItems.length})
        </div>
        {qualityItems.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#9ca3af', fontSize: 13 }}>
            No quality items found. Validate items to see them here.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
                  <SortableHeader label="Name" sortKey="name" currentSort={itemSort} onSort={handleItemSort} />
                  <SortableHeader label="Kind" sortKey="kind" currentSort={itemSort} onSort={handleItemSort} />
                  <SortableHeader label="Score" sortKey="score" currentSort={itemSort} onSort={handleItemSort} />
                  <th style={{ padding: '10px 16px', textAlign: 'center', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Tier</th>
                  <th style={{ padding: '10px 16px', textAlign: 'center', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Trend</th>
                  <SortableHeader label="Last Validated" sortKey="last_validated" currentSort={itemSort} onSort={handleItemSort} />
                  <th style={{ padding: '10px 16px', textAlign: 'center', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Stale</th>
                </tr>
              </thead>
              <tbody>
                {sortedQualityItems.map(item => {
                  const isExpanded = expandedItem?.kind === item.item_kind && expandedItem?.id === item.item_id
                  const scoreColor = item.quality_score == null ? '#9ca3af'
                    : item.quality_score >= 90 ? '#16a34a'
                    : item.quality_score >= 70 ? '#2563eb'
                    : item.quality_score >= 50 ? '#f59e0b'
                    : '#dc2626'
                  const tierColors: Record<string, { bg: string; text: string }> = {
                    excellent: { bg: '#dcfce7', text: '#166534' },
                    good: { bg: '#dbeafe', text: '#1e40af' },
                    fair: { bg: '#fef3c7', text: '#92400e' },
                    poor: { bg: '#fee2e2', text: '#991b1b' },
                  }
                  const tc = tierColors[item.quality_tier || ''] || { bg: '#f3f4f6', text: '#374151' }
                  return (
                    <React.Fragment key={`${item.item_kind}-${item.item_id}`}>
                      <tr
                        onClick={() => handleExpandItem(item.item_kind, item.item_id)}
                        style={{
                          borderBottom: '1px solid #f3f4f6', cursor: 'pointer',
                          background: isExpanded ? '#f9fafb' : undefined,
                        }}
                      >
                        <td style={{ padding: '10px 16px', fontWeight: 500 }}>{item.display_name}</td>
                        <td style={{ padding: '10px 16px' }}>
                          <span style={{
                            fontSize: 11, padding: '1px 8px', borderRadius: 9999,
                            background: item.item_kind === 'workflow' ? '#f3e8ff' : '#e0f2fe',
                            color: item.item_kind === 'workflow' ? '#7c3aed' : '#0369a1',
                          }}>{item.item_kind}</span>
                        </td>
                        <td style={{ padding: '10px 16px', textAlign: 'right', fontFamily: 'ui-monospace, monospace', fontWeight: 600, color: scoreColor }}>
                          {item.quality_score != null ? `${item.quality_score}%` : '-'}
                        </td>
                        <td style={{ padding: '10px 16px', textAlign: 'center' }}>
                          {item.quality_tier ? (
                            <span style={{
                              display: 'inline-block', padding: '2px 10px', borderRadius: 9999,
                              fontSize: 11, fontWeight: 600, backgroundColor: tc.bg, color: tc.text,
                              textTransform: 'capitalize',
                            }}>
                              {item.quality_tier}
                            </span>
                          ) : '-'}
                        </td>
                        <td style={{ padding: '10px 16px', textAlign: 'center' }}>
                          {item.trend === 'up' && <TrendingUp size={16} color="#16a34a" />}
                          {item.trend === 'down' && <TrendingDown size={16} color="#dc2626" />}
                          {item.trend === 'flat' && <Minus size={16} color="#9ca3af" />}
                        </td>
                        <td style={{ padding: '10px 16px', fontSize: 12, color: '#6b7280' }}>
                          {item.last_validated_at ? relativeTime(item.last_validated_at) : '-'}
                        </td>
                        <td style={{ padding: '10px 16px', textAlign: 'center' }}>
                          {item.stale && <Clock size={15} color="#f59e0b" />}
                        </td>
                      </tr>
                      {/* Per-Item Drill-Down */}
                      {isExpanded && (
                        <tr>
                          <td colSpan={7} style={{ padding: 0, background: '#f9fafb' }}>
                            <div style={{ padding: '16px 20px' }}>
                              {!itemDetail ? (
                                <div style={{ textAlign: 'center', padding: '20px 0', color: '#9ca3af', fontSize: 13 }}>
                                  Loading detail...
                                </div>
                              ) : (
                                <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                                  {/* Score Timeline Chart */}
                                  <div style={{
                                    flex: '1 1 400px', background: '#fff', border: '1px solid #e5e7eb',
                                    borderRadius: 'var(--ui-radius, 12px)', padding: 16,
                                  }}>
                                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Score Timeline</div>
                                    {itemDetail.history.length === 0 ? (
                                      <div style={{ textAlign: 'center', padding: '20px 0', color: '#9ca3af', fontSize: 12 }}>
                                        No history available.
                                      </div>
                                    ) : (
                                      <ResponsiveContainer width="100%" height={200}>
                                        <LineChart data={itemDetail.history.map(h => ({
                                          date: h.created_at.slice(0, 10),
                                          score: h.score,
                                          grade: h.grade,
                                        }))}>
                                          <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                                          <XAxis dataKey="date" tick={{ fontSize: 10 }} tickLine={false} axisLine={{ stroke: '#e5e7eb' }} />
                                          <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} tickLine={false} axisLine={{ stroke: '#e5e7eb' }} />
                                          <Tooltip
                                            contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 12 }}
                                            formatter={(value: number) => [`${value}%`, 'Score']}
                                          />
                                          <Line type="monotone" dataKey="score" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} name="Score" />
                                        </LineChart>
                                      </ResponsiveContainer>
                                    )}
                                  </div>
                                  {/* Model Comparison */}
                                  <div style={{
                                    flex: '0 1 280px', background: '#fff', border: '1px solid #e5e7eb',
                                    borderRadius: 'var(--ui-radius, 12px)', padding: 16,
                                  }}>
                                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Model Comparison</div>
                                    {itemDetail.model_comparison.length === 0 ? (
                                      <div style={{ textAlign: 'center', padding: '20px 0', color: '#9ca3af', fontSize: 12 }}>
                                        No model data available.
                                      </div>
                                    ) : (
                                      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                        {itemDetail.model_comparison.map((mc, i) => (
                                          <div key={i} style={{
                                            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                            padding: '8px 12px', borderRadius: 8, background: '#f9fafb',
                                            border: '1px solid #f3f4f6',
                                          }}>
                                            <div>
                                              <div style={{ fontSize: 13, fontWeight: 500, color: '#111827' }}>{mc.model}</div>
                                              <div style={{ fontSize: 11, color: '#9ca3af' }}>{mc.run_count} run{mc.run_count !== 1 ? 's' : ''}</div>
                                            </div>
                                            <div style={{
                                              fontSize: 18, fontWeight: 700, fontFamily: 'ui-monospace, monospace',
                                              color: mc.avg_score >= 90 ? '#16a34a' : mc.avg_score >= 70 ? '#2563eb' : mc.avg_score >= 50 ? '#f59e0b' : '#dc2626',
                                            }}>
                                              {mc.avg_score}%
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Monitoring Status */}
      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
        <h3 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 16px' }}>Monitoring Status</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          <div style={{
            padding: 16, borderRadius: 'var(--ui-radius, 12px)', background: '#f0fdf4',
            border: '1px solid #bbf7d0', textAlign: 'center',
          }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: '#166534', fontFamily: 'ui-monospace, monospace' }}>
              {qualityItems.length}
            </div>
            <div style={{ fontSize: 12, color: '#15803d', fontWeight: 500, marginTop: 4 }}>Total Monitored Items</div>
          </div>
          <div style={{
            padding: 16, borderRadius: 'var(--ui-radius, 12px)', background: '#fffbeb',
            border: '1px solid #fde68a', textAlign: 'center',
          }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: '#92400e', fontFamily: 'ui-monospace, monospace' }}>
              {alerts.length}
            </div>
            <div style={{ fontSize: 12, color: '#a16207', fontWeight: 500, marginTop: 4 }}>Items with Alerts</div>
          </div>
          <div style={{
            padding: 16, borderRadius: 'var(--ui-radius, 12px)', background: '#fef2f2',
            border: '1px solid #fecaca', textAlign: 'center',
          }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: '#991b1b', fontFamily: 'ui-monospace, monospace' }}>
              {qualityItems.filter(i => i.stale).length}
            </div>
            <div style={{ fontSize: 12, color: '#b91c1c', fontWeight: 500, marginTop: 4 }}>Stale Items</div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────
// Config Tab
// ──────────────────────────────────────────

function ConfigTab() {
  const [cfg, setCfg] = useState<SystemConfigData | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Theme state
  const [themeColor, setThemeColor] = useState('#eab308')
  const [themeRadius, setThemeRadius] = useState(12)
  const [themeSaving, setThemeSaving] = useState(false)
  const [themeSaved, setThemeSaved] = useState(false)

  // Extraction config
  const [extractionMode, setExtractionMode] = useState('one_pass')
  const [chunkingEnabled, setChunkingEnabled] = useState(false)
  const [maxKeysPerChunk, setMaxKeysPerChunk] = useState(10)
  const [repetitionEnabled, setRepetitionEnabled] = useState(false)
  const [onePassThinking, setOnePassThinking] = useState(true)
  const [onePassStructured, setOnePassStructured] = useState(true)
  const [onePassModel, setOnePassModel] = useState('')
  const [twoPassP1Thinking, setTwoPassP1Thinking] = useState(true)
  const [twoPassP1Structured, setTwoPassP1Structured] = useState(false)
  const [twoPassP1Model, setTwoPassP1Model] = useState('')
  const [twoPassP2Thinking, setTwoPassP2Thinking] = useState(false)
  const [twoPassP2Structured, setTwoPassP2Structured] = useState(true)
  const [twoPassP2Model, setTwoPassP2Model] = useState('')

  // Quality config
  const [requireValidation, setRequireValidation] = useState(false)
  const [minAccuracy, setMinAccuracy] = useState(70)
  const [minConsistency, setMinConsistency] = useState(80)
  const [minWorkflowGrade, setMinWorkflowGrade] = useState('C')
  const [excellentThreshold, setExcellentThreshold] = useState(90)
  const [goodThreshold, setGoodThreshold] = useState(70)
  const [fairThreshold, setFairThreshold] = useState(50)

  // Endpoints
  const [ocrEndpoint, setOcrEndpoint] = useState('')

  // Auth
  const [authMethods, setAuthMethods] = useState<string[]>(['password'])
  const [authSaving, setAuthSaving] = useState(false)

  // Add/edit model form
  const [showModelForm, setShowModelForm] = useState(false)
  const [editingModelIndex, setEditingModelIndex] = useState<number | null>(null)
  const [savingModel, setSavingModel] = useState(false)
  const [newModel, setNewModel] = useState({ name: '', tag: '', external: false, thinking: false, endpoint: '', api_protocol: '', api_key: '' })

  // Add provider form
  const [showAddProvider, setShowAddProvider] = useState(false)
  const [newProvider, setNewProvider] = useState({ provider: 'oauth', display_name: '', client_id: '', client_secret: '', redirect_uri: '', tenant_id: '' })

  useEffect(() => {
    setLoading(true)
    getSystemConfig().then(c => {
      setCfg(c)
      setThemeColor(c.highlight_color || '#eab308')
      setThemeRadius(parseInt(c.ui_radius) || 12)
      setOcrEndpoint(c.ocr_endpoint || '')
      setAuthMethods(c.auth_methods || ['password'])
      // Extraction config
      const ec = c.extraction_config || {}
      setExtractionMode((ec as Record<string, unknown>).mode as string || 'one_pass')
      const chunking = (ec as Record<string, unknown>).chunking as Record<string, unknown> || {}
      setChunkingEnabled(!!chunking.enabled)
      setMaxKeysPerChunk((chunking.max_keys_per_chunk as number) || 10)
      setRepetitionEnabled(!!((ec as Record<string, unknown>).repetition as Record<string, unknown>)?.enabled)
      const onePass = (ec as Record<string, unknown>).one_pass as Record<string, unknown> || {}
      setOnePassThinking(onePass.thinking !== false)
      setOnePassStructured((onePass.structured_output ?? onePass.structured) !== false)
      setOnePassModel((onePass.model as string) || '')
      const twoPass = (ec as Record<string, unknown>).two_pass as Record<string, unknown> || {}
      const pass1 = (twoPass.pass1 as Record<string, unknown> ?? twoPass.pass_1 as Record<string, unknown>) || {}
      const pass2 = (twoPass.pass2 as Record<string, unknown> ?? twoPass.pass_2 as Record<string, unknown>) || {}
      setTwoPassP1Thinking(pass1.thinking !== false)
      setTwoPassP1Structured(!!(pass1.structured_output ?? pass1.structured))
      setTwoPassP1Model((pass1.model as string) || '')
      setTwoPassP2Thinking(!!(pass2.thinking))
      setTwoPassP2Structured((pass2.structured_output ?? pass2.structured) !== false)
      setTwoPassP2Model((pass2.model as string) || '')
      // Quality config
      const qc = (c.quality_config || {}) as Record<string, unknown>
      const gates = (qc.verification_gates || {}) as Record<string, unknown>
      setRequireValidation(!!gates.require_validation)
      setMinAccuracy(Math.round(((gates.min_extraction_accuracy as number) ?? 0.7) * 100))
      setMinConsistency(Math.round(((gates.min_extraction_consistency as number) ?? 0.8) * 100))
      setMinWorkflowGrade((gates.min_workflow_grade as string) || 'C')
      const tiers = (qc.quality_tiers || {}) as Record<string, Record<string, unknown>>
      setExcellentThreshold((tiers.excellent?.min_score as number) ?? 90)
      setGoodThreshold((tiers.good?.min_score as number) ?? 70)
      setFairThreshold((tiers.fair?.min_score as number) ?? 50)
    }).finally(() => setLoading(false))

    getThemeConfig().then(t => {
      setThemeColor(t.highlight_color)
      setThemeRadius(parseInt(t.ui_radius) || 12)
    }).catch(() => {})
  }, [])

  const handleSaveConfig = async () => {
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      await updateSystemConfig({
        extraction_config: {
          mode: extractionMode,
          one_pass: { thinking: onePassThinking, structured: onePassStructured, model: onePassModel || '' },
          two_pass: {
            pass_1: { thinking: twoPassP1Thinking, structured: twoPassP1Structured, model: twoPassP1Model || '' },
            pass_2: { thinking: twoPassP2Thinking, structured: twoPassP2Structured, model: twoPassP2Model || '' },
          },
          chunking: { enabled: chunkingEnabled, max_keys_per_chunk: maxKeysPerChunk },
          repetition: { enabled: repetitionEnabled },
        },
        quality_config: {
          verification_gates: {
            require_validation: requireValidation,
            min_extraction_accuracy: minAccuracy / 100,
            min_extraction_consistency: minConsistency / 100,
            min_workflow_grade: minWorkflowGrade,
          },
          quality_tiers: {
            excellent: { min_score: excellentThreshold },
            good: { min_score: goodThreshold },
            fair: { min_score: fairThreshold },
          },
        },
        ocr_endpoint: ocrEndpoint,
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleSaveTheme = async () => {
    setThemeSaving(true)
    setThemeSaved(false)
    try {
      const updated = await updateThemeConfig({ highlight_color: themeColor, ui_radius: `${themeRadius}px` })
      applyThemeToDOM(updated)
      setThemeSaved(true)
      setTimeout(() => setThemeSaved(false), 3000)
    } finally {
      setThemeSaving(false)
    }
  }

  const handleSaveModel = async () => {
    if (!newModel.name.trim()) {
      setError('Model name is required')
      return
    }
    if (!newModel.tag.trim()) {
      setError('Tag is required')
      return
    }
    setSavingModel(true)
    setError(null)
    try {
      let res
      if (editingModelIndex !== null) {
        res = await updateModel(editingModelIndex, newModel)
      } else {
        res = await addModel(newModel)
      }
      if (cfg) setCfg({ ...cfg, available_models: res.models })
      setNewModel({ name: '', tag: '', external: false, thinking: false, endpoint: '', api_protocol: '', api_key: '' })
      setShowModelForm(false)
      setEditingModelIndex(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save model')
    } finally {
      setSavingModel(false)
    }
  }

  const handleEditModel = (index: number) => {
    const m = cfg?.available_models[index]
    if (!m) return
    setNewModel({
      name: m.name,
      tag: m.tag,
      external: m.external,
      thinking: m.thinking,
      endpoint: m.endpoint || '',
      api_protocol: m.api_protocol || '',
      api_key: m.api_key || '',
    })
    setEditingModelIndex(index)
    setShowModelForm(true)
  }

  const handleDeleteModel = async (index: number) => {
    try {
      await deleteModel(index)
      if (cfg) {
        const models = [...cfg.available_models]
        models.splice(index, 1)
        setCfg({ ...cfg, available_models: models })
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete model')
    }
  }

  const handleSaveAuthMethods = async () => {
    setAuthSaving(true)
    try {
      await updateAuthMethods(authMethods)
    } finally {
      setAuthSaving(false)
    }
  }

  const handleAddProvider = async () => {
    if (!newProvider.display_name || !newProvider.client_id) return
    try {
      await addOAuthProvider(newProvider as unknown as Record<string, string>)
      // Refresh config
      const c = await getSystemConfig()
      setCfg(c)
      setNewProvider({ provider: 'oauth', display_name: '', client_id: '', client_secret: '', redirect_uri: '', tenant_id: '' })
      setShowAddProvider(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add provider')
    }
  }

  const handleDeleteProvider = async (index: number) => {
    try {
      await deleteOAuthProvider(index)
      const c = await getSystemConfig()
      setCfg(c)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete provider')
    }
  }

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading config...</div>

  const sectionStyle = {
    background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' as const,
  }
  const sectionHeaderStyle = {
    padding: '14px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 15, fontWeight: 600 as const,
    display: 'flex', alignItems: 'center', gap: 10,
  }
  const sectionBodyStyle = { padding: 20 }
  const labelStyle = { display: 'block', fontSize: 13, fontWeight: 500 as const, color: '#374151', marginBottom: 6 }
  const inputStyle = {
    width: '100%', padding: '8px 12px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
    fontSize: 14, outline: 'none',
  }
  const checkStyle = { marginRight: 8, accentColor: 'var(--highlight-color, #eab308)' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {error && (
        <div style={{ padding: '10px 16px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 'var(--ui-radius, 12px)', color: '#991b1b', fontSize: 13 }}>
          {error}
        </div>
      )}

      {/* Extraction Configuration */}
      <div style={sectionStyle}>
        <div style={sectionHeaderStyle}>
          <Cpu size={18} color="#6b7280" /> Extraction Configuration
        </div>
        <div style={sectionBodyStyle}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Mode */}
            <div>
              <label style={labelStyle}>Extraction Mode</label>
              <div style={{ display: 'flex', gap: 8 }}>
                {['one_pass', 'two_pass'].map(mode => (
                  <button
                    key={mode}
                    onClick={() => setExtractionMode(mode)}
                    style={{
                      padding: '8px 20px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
                      fontSize: 13, fontWeight: 500, cursor: 'pointer', textTransform: 'capitalize',
                      backgroundColor: extractionMode === mode ? 'var(--highlight-color, #eab308)' : '#fff',
                      color: extractionMode === mode ? 'var(--highlight-text-color, #000)' : '#374151',
                    }}
                  >
                    {mode.replace('_', '-')}
                  </button>
                ))}
              </div>
            </div>

            {/* Mode-specific options */}
            {extractionMode === 'one_pass' ? (
              <div style={{ padding: 16, background: '#f9fafb', borderRadius: 'var(--ui-radius, 12px)' }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>One-Pass Settings</div>
                <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, marginBottom: 8, cursor: 'pointer' }}>
                  <input type="checkbox" checked={onePassThinking} onChange={e => setOnePassThinking(e.target.checked)} style={checkStyle} />
                  Thinking
                </label>
                <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, marginBottom: 12, cursor: 'pointer' }}>
                  <input type="checkbox" checked={onePassStructured} onChange={e => setOnePassStructured(e.target.checked)} style={checkStyle} />
                  Structured
                </label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <label style={{ fontSize: 13, color: '#5f6368' }}>Model:</label>
                  <select value={onePassModel} onChange={e => setOnePassModel(e.target.value)} style={{ ...inputStyle, maxWidth: 260 }}>
                    <option value="">Default</option>
                    {cfg?.available_models?.map(m => (
                      <option key={m.tag} value={m.name}>{m.tag || m.name}</option>
                    ))}
                  </select>
                </div>
              </div>
            ) : (
              <div style={{ padding: 16, background: '#f9fafb', borderRadius: 'var(--ui-radius, 12px)' }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>Two-Pass Settings</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', marginBottom: 8 }}>Pass 1 (Draft)</div>
                    <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, marginBottom: 8, cursor: 'pointer' }}>
                      <input type="checkbox" checked={twoPassP1Thinking} onChange={e => setTwoPassP1Thinking(e.target.checked)} style={checkStyle} />
                      Thinking
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, marginBottom: 12, cursor: 'pointer' }}>
                      <input type="checkbox" checked={twoPassP1Structured} onChange={e => setTwoPassP1Structured(e.target.checked)} style={checkStyle} />
                      Structured
                    </label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <label style={{ fontSize: 13, color: '#5f6368' }}>Model:</label>
                      <select value={twoPassP1Model} onChange={e => setTwoPassP1Model(e.target.value)} style={{ ...inputStyle, maxWidth: 200 }}>
                        <option value="">Default</option>
                        {cfg?.available_models?.map(m => (
                          <option key={m.tag} value={m.name}>{m.tag || m.name}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', marginBottom: 8 }}>Pass 2 (Final)</div>
                    <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, marginBottom: 8, cursor: 'pointer' }}>
                      <input type="checkbox" checked={twoPassP2Thinking} onChange={e => setTwoPassP2Thinking(e.target.checked)} style={checkStyle} />
                      Thinking
                    </label>
                    <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, marginBottom: 12, cursor: 'pointer' }}>
                      <input type="checkbox" checked={twoPassP2Structured} onChange={e => setTwoPassP2Structured(e.target.checked)} style={checkStyle} />
                      Structured
                    </label>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <label style={{ fontSize: 13, color: '#5f6368' }}>Model:</label>
                      <select value={twoPassP2Model} onChange={e => setTwoPassP2Model(e.target.value)} style={{ ...inputStyle, maxWidth: 200 }}>
                        <option value="">Default</option>
                        {cfg?.available_models?.map(m => (
                          <option key={m.tag} value={m.name}>{m.tag || m.name}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Chunking */}
            <div>
              <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, fontWeight: 500, cursor: 'pointer' }}>
                <input type="checkbox" checked={chunkingEnabled} onChange={e => setChunkingEnabled(e.target.checked)} style={checkStyle} />
                Enable Chunking
              </label>
              {chunkingEnabled && (
                <div style={{ marginTop: 12, paddingLeft: 24 }}>
                  <label style={labelStyle}>Max Keys Per Chunk</label>
                  <input
                    type="number" min={1} max={100} value={maxKeysPerChunk}
                    onChange={e => setMaxKeysPerChunk(Number(e.target.value))}
                    style={{ ...inputStyle, maxWidth: 120 }}
                  />
                </div>
              )}
            </div>

            {/* Repetition */}
            <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, fontWeight: 500, cursor: 'pointer' }}>
              <input type="checkbox" checked={repetitionEnabled} onChange={e => setRepetitionEnabled(e.target.checked)} style={checkStyle} />
              Enable Repetition/Consensus
            </label>
          </div>
        </div>
      </div>

      {/* Endpoints */}
      <div style={sectionStyle}>
        <div style={sectionHeaderStyle}>
          <Globe size={18} color="#6b7280" /> Endpoints
        </div>
        <div style={sectionBodyStyle}>
          <div>
            <label style={labelStyle}>OCR Endpoint</label>
            <input
              type="url" value={ocrEndpoint} onChange={e => setOcrEndpoint(e.target.value)}
              placeholder="https://..." style={{ ...inputStyle, maxWidth: 500 }}
            />
          </div>
        </div>
      </div>

      {/* Quality & Verification Gates */}
      <div style={sectionStyle}>
        <div style={sectionHeaderStyle}>
          <ShieldCheck size={18} color="#6b7280" /> Quality &amp; Verification Gates
        </div>
        <div style={sectionBodyStyle}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, fontWeight: 500, cursor: 'pointer' }}>
              <input type="checkbox" checked={requireValidation} onChange={e => setRequireValidation(e.target.checked)} style={checkStyle} />
              Require validation before verification submission
            </label>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
              <div>
                <label style={labelStyle}>Min Extraction Accuracy (%)</label>
                <input type="number" min={0} max={100} value={minAccuracy} onChange={e => setMinAccuracy(Number(e.target.value))} style={{ ...inputStyle, maxWidth: 120 }} />
              </div>
              <div>
                <label style={labelStyle}>Min Extraction Consistency (%)</label>
                <input type="number" min={0} max={100} value={minConsistency} onChange={e => setMinConsistency(Number(e.target.value))} style={{ ...inputStyle, maxWidth: 120 }} />
              </div>
              <div>
                <label style={labelStyle}>Min Workflow Grade</label>
                <select value={minWorkflowGrade} onChange={e => setMinWorkflowGrade(e.target.value)} style={{ ...inputStyle, maxWidth: 120 }}>
                  <option value="A">A</option>
                  <option value="B">B</option>
                  <option value="C">C</option>
                  <option value="D">D</option>
                  <option value="F">F</option>
                </select>
              </div>
            </div>

            <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: '#374151', marginBottom: 12 }}>Quality Tiers</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
                <div>
                  <label style={labelStyle}>Excellent threshold</label>
                  <input type="number" min={0} max={100} value={excellentThreshold} onChange={e => setExcellentThreshold(Number(e.target.value))} style={{ ...inputStyle, maxWidth: 120 }} />
                </div>
                <div>
                  <label style={labelStyle}>Good threshold</label>
                  <input type="number" min={0} max={100} value={goodThreshold} onChange={e => setGoodThreshold(Number(e.target.value))} style={{ ...inputStyle, maxWidth: 120 }} />
                </div>
                <div>
                  <label style={labelStyle}>Fair threshold</label>
                  <input type="number" min={0} max={100} value={fairThreshold} onChange={e => setFairThreshold(Number(e.target.value))} style={{ ...inputStyle, maxWidth: 120 }} />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Save config button */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <button
          onClick={handleSaveConfig}
          disabled={saving}
          style={{
            padding: '10px 24px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
            backgroundColor: '#111827', color: '#fff', fontSize: 14, fontWeight: 600, cursor: 'pointer',
            opacity: saving ? 0.6 : 1,
          }}
        >
          {saving ? 'Saving...' : 'Save Configuration'}
        </button>
        {saved && <span style={{ fontSize: 13, color: '#16a34a' }}>Configuration saved!</span>}
      </div>

      {/* Authentication */}
      <div style={sectionStyle}>
        <div style={sectionHeaderStyle}>
          <Lock size={18} color="#6b7280" /> Authentication
        </div>
        <div style={sectionBodyStyle}>
          <div style={{ marginBottom: 20 }}>
            <label style={labelStyle}>Auth Methods</label>
            <div style={{ display: 'flex', gap: 16 }}>
              {['password', 'oauth'].map(m => (
                <label key={m} style={{ display: 'flex', alignItems: 'center', fontSize: 14, cursor: 'pointer', textTransform: 'capitalize' }}>
                  <input
                    type="checkbox"
                    checked={authMethods.includes(m)}
                    onChange={e => {
                      if (e.target.checked) setAuthMethods(prev => [...prev, m])
                      else setAuthMethods(prev => prev.filter(x => x !== m))
                    }}
                    style={checkStyle}
                  />
                  {m === 'oauth' ? 'OAuth / SAML' : m}
                </label>
              ))}
            </div>
            <button
              onClick={handleSaveAuthMethods}
              disabled={authSaving}
              style={{
                marginTop: 12, padding: '6px 16px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
                fontSize: 13, fontWeight: 500, cursor: 'pointer', background: '#fff',
              }}
            >
              {authSaving ? 'Saving...' : 'Update Methods'}
            </button>
          </div>

          {/* OAuth Providers */}
          <div style={{ borderTop: '1px solid #e5e7eb', paddingTop: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <label style={{ ...labelStyle, marginBottom: 0 }}>OAuth / SAML Providers</label>
              <button
                onClick={() => setShowAddProvider(!showAddProvider)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 4, padding: '6px 12px',
                  borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
                  fontSize: 13, fontWeight: 500, cursor: 'pointer', background: '#fff',
                }}
              >
                <Plus size={14} /> Add Provider
              </button>
            </div>

            {cfg?.oauth_providers && cfg.oauth_providers.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {cfg.oauth_providers.map((p, i) => (
                  <div key={i} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    padding: '10px 16px', background: '#f9fafb', borderRadius: 'var(--ui-radius, 12px)',
                    border: '1px solid #e5e7eb',
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <Globe size={16} color="#6b7280" />
                      <span style={{ fontSize: 14, fontWeight: 500 }}>{(p as Record<string, unknown>).display_name as string || (p as Record<string, unknown>).provider as string}</span>
                      <span style={{
                        fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: '#dbeafe', color: '#1e40af', fontWeight: 600,
                      }}>
                        {((p as Record<string, unknown>).provider as string || 'oauth').toUpperCase()}
                      </span>
                    </div>
                    <button
                      onClick={() => handleDeleteProvider(i)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: 4 }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: 13, color: '#9ca3af', padding: '8px 0' }}>No providers configured.</div>
            )}

            {showAddProvider && (
              <div style={{ marginTop: 12, padding: 16, background: '#f9fafb', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #e5e7eb' }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>New Provider</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div>
                    <label style={labelStyle}>Type</label>
                    <select
                      value={newProvider.provider}
                      onChange={e => setNewProvider({ ...newProvider, provider: e.target.value })}
                      style={inputStyle}
                    >
                      <option value="oauth">OAuth 2.0</option>
                      <option value="azure">Azure AD</option>
                      <option value="saml">SAML</option>
                    </select>
                  </div>
                  <div>
                    <label style={labelStyle}>Display Name</label>
                    <input value={newProvider.display_name} onChange={e => setNewProvider({ ...newProvider, display_name: e.target.value })} style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>Client ID</label>
                    <input value={newProvider.client_id} onChange={e => setNewProvider({ ...newProvider, client_id: e.target.value })} style={inputStyle} />
                  </div>
                  <div>
                    <label style={labelStyle}>Client Secret</label>
                    <input type="password" value={newProvider.client_secret} onChange={e => setNewProvider({ ...newProvider, client_secret: e.target.value })} style={inputStyle} />
                  </div>
                  <div style={{ gridColumn: '1 / -1' }}>
                    <label style={labelStyle}>Redirect URI</label>
                    <input value={newProvider.redirect_uri} onChange={e => setNewProvider({ ...newProvider, redirect_uri: e.target.value })} style={inputStyle} />
                  </div>
                  {newProvider.provider === 'azure' && (
                    <div style={{ gridColumn: '1 / -1' }}>
                      <label style={labelStyle}>Tenant ID</label>
                      <input value={newProvider.tenant_id} onChange={e => setNewProvider({ ...newProvider, tenant_id: e.target.value })} style={inputStyle} />
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                  <button
                    onClick={handleAddProvider}
                    style={{
                      padding: '8px 16px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
                      background: 'var(--highlight-color, #eab308)', color: 'var(--highlight-text-color, #000)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
                    }}
                  >
                    Add Provider
                  </button>
                  <button
                    onClick={() => setShowAddProvider(false)}
                    style={{
                      padding: '8px 16px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
                      background: '#fff', fontSize: 13, cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Available Models */}
      <div style={sectionStyle}>
        <div style={sectionHeaderStyle}>
          <Cpu size={18} color="#6b7280" /> Available Models
          <div style={{ flex: 1 }} />
          <button
            onClick={() => {
              setNewModel({ name: '', tag: '', external: false, thinking: false, endpoint: '', api_protocol: '', api_key: '' })
              setEditingModelIndex(null)
              setShowModelForm(!showModelForm)
            }}
            style={{
              display: 'flex', alignItems: 'center', gap: 4, padding: '6px 12px',
              borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
              fontSize: 13, fontWeight: 500, cursor: 'pointer', background: '#fff',
            }}
          >
            <Plus size={14} /> Add Model
          </button>
        </div>
        <div style={sectionBodyStyle}>
          {cfg?.available_models && cfg.available_models.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {cfg.available_models.map((m, i) => (
                <div key={i} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '10px 16px', background: '#f9fafb', borderRadius: 'var(--ui-radius, 12px)',
                  border: '1px solid #e5e7eb',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 14, fontWeight: 500 }}>{m.name}</span>
                    <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: '#f3f4f6', color: '#6b7280', fontWeight: 600 }}>{m.tag}</span>
                    {m.external && (
                      <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: '#fef3c7', color: '#92400e', fontWeight: 600 }}>External</span>
                    )}
                    {m.thinking && (
                      <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: '#dbeafe', color: '#1e40af', fontWeight: 600 }}>Thinking</span>
                    )}
                    {m.api_protocol && (
                      <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: '#e0e7ff', color: '#3730a3', fontWeight: 600 }}>{m.api_protocol}</span>
                    )}
                    {m.api_key && (
                      <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 9999, background: '#d1fae5', color: '#065f46', fontWeight: 600 }}>API Key</span>
                    )}
                    {m.endpoint && (
                      <span style={{ fontSize: 11, color: '#9ca3af', fontFamily: 'ui-monospace, monospace' }}>{m.endpoint}</span>
                    )}
                  </div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button
                      onClick={() => handleEditModel(i)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: 4 }}
                      title="Edit model"
                    >
                      <Pencil size={16} />
                    </button>
                    <button
                      onClick={() => handleDeleteModel(i)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: 4 }}
                      title="Delete model"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: 13, color: '#9ca3af' }}>No models configured.</div>
          )}

          {showModelForm && (
            <div style={{ marginTop: 16, padding: 16, background: '#f9fafb', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #e5e7eb' }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>{editingModelIndex !== null ? 'Edit Model' : 'New Model'}</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={labelStyle}>Model Name</label>
                  <input value={newModel.name} onChange={e => { const v = e.target.value; setNewModel(prev => ({ ...prev, name: v })) }} placeholder="gpt-4o" style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>Tag</label>
                  <input value={newModel.tag} onChange={e => { const v = e.target.value; setNewModel(prev => ({ ...prev, tag: v })) }} placeholder="openai" style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>Endpoint (optional)</label>
                  <input value={newModel.endpoint} onChange={e => { const v = e.target.value; setNewModel(prev => ({ ...prev, endpoint: v })) }} placeholder="https://..." style={inputStyle} />
                </div>
                <div>
                  <label style={labelStyle}>API Protocol</label>
                  <select value={newModel.api_protocol} onChange={e => { const v = e.target.value; setNewModel(prev => ({ ...prev, api_protocol: v })) }} style={inputStyle}>
                    <option value="">Auto-detect</option>
                    <option value="openai">OpenAI</option>
                    <option value="ollama">Ollama</option>
                    <option value="vllm">VLLM</option>
                  </select>
                </div>
                <div style={{ gridColumn: '1 / -1' }}>
                  <label style={labelStyle}>API Key (optional)</label>
                  <input type="password" value={newModel.api_key} onChange={e => { const v = e.target.value; setNewModel(prev => ({ ...prev, api_key: v })) }} placeholder="sk-..." style={inputStyle} />
                </div>
              </div>
              <div style={{ display: 'flex', gap: 16, marginTop: 12 }}>
                <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, cursor: 'pointer' }}>
                  <input type="checkbox" checked={newModel.external} onChange={e => { const v = e.target.checked; setNewModel(prev => ({ ...prev, external: v })) }} style={checkStyle} />
                  External
                </label>
                <label style={{ display: 'flex', alignItems: 'center', fontSize: 14, cursor: 'pointer' }}>
                  <input type="checkbox" checked={newModel.thinking} onChange={e => { const v = e.target.checked; setNewModel(prev => ({ ...prev, thinking: v })) }} style={checkStyle} />
                  Thinking
                </label>
              </div>
              {error && (
                <div style={{ marginTop: 12, padding: '8px 12px', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 'var(--ui-radius, 12px)', color: '#991b1b', fontSize: 13 }}>
                  {error}
                </div>
              )}
              <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                <button
                  onClick={handleSaveModel}
                  disabled={savingModel}
                  style={{
                    padding: '8px 16px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
                    background: 'var(--highlight-color, #eab308)', color: 'var(--highlight-text-color, #000)', fontSize: 13, fontWeight: 600, cursor: 'pointer',
                    opacity: savingModel ? 0.6 : 1,
                  }}
                >
                  {savingModel ? 'Saving...' : editingModelIndex !== null ? 'Save Changes' : 'Add Model'}
                </button>
                <button
                  onClick={() => { setShowModelForm(false); setEditingModelIndex(null) }}
                  style={{
                    padding: '8px 16px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db',
                    background: '#fff', fontSize: 13, cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* UI Theme */}
      <div style={sectionStyle}>
        <div style={sectionHeaderStyle}>
          <Palette size={18} color="#6b7280" /> UI Theme
        </div>
        <div style={sectionBodyStyle}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
            <div>
              <label style={labelStyle}>Highlight Color</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <input type="color" value={themeColor} onChange={e => setThemeColor(e.target.value)} style={{ height: 40, width: 56, borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #d1d5db', cursor: 'pointer' }} />
                <input type="text" value={themeColor} onChange={e => setThemeColor(e.target.value)} style={{ ...inputStyle, fontFamily: 'ui-monospace, monospace' }} />
              </div>
            </div>
            <div>
              <label style={labelStyle}>Corner Radius: {themeRadius}px</label>
              <input type="range" min={0} max={24} value={themeRadius} onChange={e => setThemeRadius(Number(e.target.value))} style={{ width: '100%', marginTop: 8, accentColor: 'var(--highlight-color, #eab308)' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9ca3af', marginTop: 4 }}>
                <span>0px (sharp)</span>
                <span>24px (round)</span>
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 16 }}>
            <div style={{ backgroundColor: themeColor, borderRadius: `${themeRadius}px`, padding: '8px 20px', color: 'var(--highlight-text-color, #000)', fontWeight: 600, fontSize: 13 }}>
              Sample Button
            </div>
            <div style={{ border: `2px solid ${themeColor}`, borderRadius: `${themeRadius}px`, padding: '8px 20px', color: themeColor, fontWeight: 600, fontSize: 13 }}>
              Outline Button
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 16 }}>
            <button
              onClick={handleSaveTheme}
              disabled={themeSaving}
              style={{
                padding: '8px 20px', borderRadius: 'var(--ui-radius, 12px)', border: 'none',
                background: '#111827', color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
                opacity: themeSaving ? 0.6 : 1,
              }}
            >
              {themeSaving ? 'Saving...' : 'Save Theme'}
            </button>
            {themeSaved && <span style={{ fontSize: 13, color: '#16a34a' }}>Theme saved!</span>}
          </div>
        </div>
      </div>
    </div>
  )
}

// ──────────────────────────────────────────
// Main Admin Component
// ──────────────────────────────────────────

// ---------------------------------------------------------------------------
// Demo Program Tab
// ---------------------------------------------------------------------------

function DemoTab() {
  const [stats, setStats] = useState<DemoAdminStats | null>(null)
  const [apps, setApps] = useState<DemoApp[]>([])
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [loading, setLoading] = useState(true)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [s, a] = await Promise.all([
        getDemoStats(),
        getDemoApplications(statusFilter || undefined),
      ])
      setStats(s)
      setApps(a)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => { loadData() }, [loadData])

  async function handleActivate(uuid: string) {
    await activateDemoUser(uuid)
    loadData()
  }

  async function handleRelease(uuid: string) {
    await releaseDemoUser(uuid)
    loadData()
  }

  const statusColors: Record<string, { bg: string; text: string }> = {
    pending: { bg: '#fef3c7', text: '#92400e' },
    active: { bg: '#dcfce7', text: '#166534' },
    expired: { bg: '#fee2e2', text: '#991b1b' },
    completed: { bg: '#dbeafe', text: '#1e40af' },
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Demo Program</h2>
        <button
          onClick={loadData}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '8px 16px', border: '1px solid #e5e7eb', borderRadius: 8,
            background: '#fff', cursor: 'pointer', fontSize: 13, fontFamily: 'inherit',
          }}
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Stats cards */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 16, marginBottom: 24 }}>
          {[
            { label: 'Total', value: stats.total_applications, color: '#6b7280' },
            { label: 'Active', value: stats.active_count, color: '#16a34a' },
            { label: 'Waitlist', value: stats.waitlist_count, color: '#d97706' },
            { label: 'Expired', value: stats.expired_count, color: '#dc2626' },
            { label: 'Completed', value: stats.completed_count, color: '#2563eb' },
          ].map((card) => (
            <div key={card.label} style={{
              padding: 20, borderRadius: 12, border: '1px solid #e5e7eb', background: '#fff',
            }}>
              <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 4 }}>{card.label}</div>
              <div style={{ fontSize: 28, fontWeight: 700, color: card.color }}>{card.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Organization breakdown */}
      {stats && stats.by_organization.length > 0 && (
        <div style={{ marginBottom: 24, padding: 20, borderRadius: 12, border: '1px solid #e5e7eb', background: '#fff' }}>
          <h3 style={{ fontSize: 15, fontWeight: 600, marginBottom: 12 }}>By Organization</h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {stats.by_organization.map((org) => (
              <span key={org.organization} style={{
                padding: '4px 12px', borderRadius: 20, background: '#f3f4f6',
                fontSize: 13, color: '#374151',
              }}>
                {org.organization}: {org.count}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Filter */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        {['', 'pending', 'active', 'expired', 'completed'].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            style={{
              padding: '6px 16px', borderRadius: 20, border: '1px solid #e5e7eb',
              background: statusFilter === s ? '#111827' : '#fff',
              color: statusFilter === s ? '#fff' : '#374151',
              fontSize: 13, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 500,
            }}
          >
            {s || 'All'}
          </button>
        ))}
      </div>

      {/* Applications table */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#9ca3af' }}>Loading...</div>
      ) : (
        <div style={{ borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden', background: '#fff' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ background: '#f9fafb' }}>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Name</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Email</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Organization</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Status</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Applied</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {apps.map((app) => {
                const sc = statusColors[app.status] || { bg: '#f3f4f6', text: '#374151' }
                return (
                  <tr key={app.uuid} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '12px 16px', fontWeight: 500 }}>{app.name}</td>
                    <td style={{ padding: '12px 16px', color: '#6b7280' }}>{app.email}</td>
                    <td style={{ padding: '12px 16px', color: '#6b7280' }}>{app.organization}</td>
                    <td style={{ padding: '12px 16px' }}>
                      <span style={{
                        display: 'inline-block', padding: '2px 10px', borderRadius: 12,
                        background: sc.bg, color: sc.text, fontSize: 12, fontWeight: 600,
                      }}>
                        {app.status}
                      </span>
                    </td>
                    <td style={{ padding: '12px 16px', color: '#6b7280', fontSize: 13 }}>
                      {formatDate(app.created_at)}
                    </td>
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ display: 'flex', gap: 6 }}>
                        {app.status === 'pending' && (
                          <button
                            onClick={() => handleActivate(app.uuid)}
                            style={{
                              padding: '4px 12px', borderRadius: 6, border: '1px solid #16a34a',
                              background: '#f0fdf4', color: '#16a34a', fontSize: 12, fontWeight: 600,
                              cursor: 'pointer', fontFamily: 'inherit',
                            }}
                          >
                            Activate
                          </button>
                        )}
                        {(app.status === 'expired' || app.status === 'completed') && !app.admin_released && (
                          <button
                            onClick={() => handleRelease(app.uuid)}
                            style={{
                              padding: '4px 12px', borderRadius: 6, border: '1px solid #2563eb',
                              background: '#eff6ff', color: '#2563eb', fontSize: 12, fontWeight: 600,
                              cursor: 'pointer', fontFamily: 'inherit',
                            }}
                          >
                            Release
                          </button>
                        )}
                        {app.admin_released && (
                          <span style={{ fontSize: 12, color: '#16a34a', fontWeight: 500 }}>Released</span>
                        )}
                        {app.post_questionnaire_completed && (
                          <span style={{ fontSize: 12, color: '#6b7280' }}>Feedback done</span>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
              {apps.length === 0 && (
                <tr>
                  <td colSpan={6} style={{ padding: 40, textAlign: 'center', color: '#9ca3af' }}>
                    No applications found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function DebuggingTab() {
  const [responses, setResponses] = useState<PostExperienceResponseAdmin[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedUuid, setExpandedUuid] = useState<string | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const [previewAnswers, setPreviewAnswers] = useState<Record<string, unknown>>({})
  const previewSections = useMemo(() => {
    const sections: { name: string; fields: typeof POST_SURVEY_FIELDS }[] = []
    let current: { name: string; fields: typeof POST_SURVEY_FIELDS } | null = null
    for (const f of POST_SURVEY_FIELDS) {
      const sec = f.section || ''
      if (!current || current.name !== sec) {
        current = { name: sec, fields: [] }
        sections.push(current)
      }
      current.fields.push(f)
    }
    return sections
  }, [])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getPostExperienceResponses()
      setResponses(data)
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  function renderValue(val: unknown): string {
    if (val === null || val === undefined) return '-'
    if (Array.isArray(val)) return val.join(', ')
    if (typeof val === 'object') {
      return Object.entries(val as Record<string, unknown>)
        .map(([k, v]) => `${k}: ${v}`)
        .join('; ')
    }
    return String(val)
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>Survey Responses</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={() => { setShowPreview(!showPreview); setPreviewAnswers({}) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '8px 16px', border: '1px solid #e5e7eb', borderRadius: 8,
              background: showPreview ? '#111827' : '#fff',
              color: showPreview ? '#fff' : '#374151',
              cursor: 'pointer', fontSize: 13, fontFamily: 'inherit',
            }}
          >
            <MessageSquare size={14} /> {showPreview ? 'Hide Preview' : 'Preview Post-Survey'}
          </button>
          <button
            onClick={loadData}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '8px 16px', border: '1px solid #e5e7eb', borderRadius: 8,
              background: '#fff', cursor: 'pointer', fontSize: 13, fontFamily: 'inherit',
            }}
          >
            <RefreshCw size={14} /> Refresh
          </button>
        </div>
      </div>

      {showPreview && (
        <div style={{
          marginBottom: 24, padding: 24, borderRadius: 12,
          border: '1px solid #e5e7eb', background: '#0a0a0a',
          color: '#e5e7eb',
        }}>
          <div style={{ textAlign: 'center', marginBottom: 20 }}>
            <MessageSquare size={32} color="#f1b300" style={{ margin: '0 auto 8px' }} />
            <h3 style={{ fontSize: 18, fontWeight: 700, color: '#fff', margin: 0 }}>
              Post-Survey Preview
            </h3>
            <p style={{ fontSize: 13, color: '#9ca3af', marginTop: 4 }}>
              This is what participants see after their demo expires.
            </p>
          </div>
          {previewSections.map((sec) => (
            <div key={sec.name} style={{
              marginBottom: 16, border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 12, overflow: 'hidden',
            }}>
              <div style={{
                padding: '10px 16px', background: 'rgba(255,255,255,0.05)',
                fontSize: 12, fontWeight: 700, color: '#f1b300',
                textTransform: 'uppercase', letterSpacing: '0.05em',
              }}>
                {sec.name}
              </div>
              <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
                {sec.fields.map((field) => (
                  <div key={field.key}>
                    <label style={{
                      display: 'block', fontSize: 13, fontWeight: 500,
                      color: '#d1d5db', marginBottom: 6,
                    }}>
                      {field.label}{field.required ? ' *' : ''}
                    </label>
                    <SurveyFieldRenderer
                      field={field}
                      value={previewAnswers[field.key]}
                      onChange={(k, v) => setPreviewAnswers(prev => ({ ...prev, [k]: v }))}
                    />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#9ca3af' }}>Loading...</div>
      ) : responses.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#9ca3af' }}>
          No survey responses yet.
        </div>
      ) : (
        <div style={{ borderRadius: 12, border: '1px solid #e5e7eb', overflow: 'hidden', background: '#fff' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ background: '#f9fafb' }}>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Name</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Email</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Organization</th>
                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: '1px solid #e5e7eb' }}>Submitted</th>
              </tr>
            </thead>
            <tbody>
              {responses.map((resp) => (
                <React.Fragment key={resp.uuid}>
                  <tr
                    onClick={() => setExpandedUuid(expandedUuid === resp.uuid ? null : resp.uuid)}
                    style={{ borderBottom: '1px solid #f3f4f6', cursor: 'pointer' }}
                  >
                    <td style={{ padding: '12px 16px', fontWeight: 500 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        {expandedUuid === resp.uuid ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        {resp.name}
                      </div>
                    </td>
                    <td style={{ padding: '12px 16px', color: '#6b7280' }}>{resp.email}</td>
                    <td style={{ padding: '12px 16px', color: '#6b7280' }}>{resp.organization}</td>
                    <td style={{ padding: '12px 16px', color: '#6b7280', fontSize: 13 }}>
                      {formatDate(resp.created_at)}
                    </td>
                  </tr>
                  {expandedUuid === resp.uuid && (
                    <tr>
                      <td colSpan={4} style={{ padding: '0 16px 16px 40px', background: '#fafbfc' }}>
                        {/* Pre-Survey (Questionnaire) */}
                        {Object.keys(resp.questionnaire_responses).length > 0 && (
                          <div style={{ marginTop: 8 }}>
                            <div style={{
                              fontSize: 13, fontWeight: 700, color: '#111827',
                              marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em',
                            }}>
                              Pre-Survey
                            </div>
                            <div style={{
                              display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '8px 16px',
                              padding: 16, borderRadius: 8, border: '1px solid #e5e7eb', background: '#fff',
                            }}>
                              {resp.title && (
                                <React.Fragment>
                                  <div style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>title</div>
                                  <div style={{ fontSize: 13, color: '#6b7280' }}>{resp.title}</div>
                                </React.Fragment>
                              )}
                              {Object.entries(resp.questionnaire_responses).map(([key, val]) => (
                                <React.Fragment key={key}>
                                  <div style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>
                                    {key.replace(/_/g, ' ')}
                                  </div>
                                  <div style={{ fontSize: 13, color: '#6b7280', wordBreak: 'break-word' }}>
                                    {renderValue(val)}
                                  </div>
                                </React.Fragment>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Post-Survey (Feedback) */}
                        <div style={{ marginTop: 12 }}>
                          <div style={{
                            fontSize: 13, fontWeight: 700, color: '#111827',
                            marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em',
                          }}>
                            Post-Survey
                          </div>
                          <div style={{
                            display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '8px 16px',
                            padding: 16, borderRadius: 8, border: '1px solid #e5e7eb', background: '#fff',
                          }}>
                            {Object.entries(resp.responses).map(([key, val]) => (
                              <React.Fragment key={key}>
                                <div style={{ fontSize: 13, fontWeight: 600, color: '#374151' }}>
                                  {key.replace(/_/g, ' ')}
                                </div>
                                <div style={{ fontSize: 13, color: '#6b7280', wordBreak: 'break-word' }}>
                                  {renderValue(val)}
                                </div>
                              </React.Fragment>
                            ))}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function Admin() {
  const { user } = useAuth()
  const { currentTeam } = useTeams()
  const [activeTab, setActiveTab] = useState<Tab>('usage')

  const isGlobalAdmin = !!user?.is_admin
  const isTeamAdmin = currentTeam?.role === 'owner' || currentTeam?.role === 'admin'
  const hasAccess = isGlobalAdmin || isTeamAdmin

  // Only global admins see the Config, Quality, and Demo tabs
  const visibleTabs = isGlobalAdmin ? TABS : TABS.filter(t => t.key !== 'config' && t.key !== 'quality' && t.key !== 'demo' && t.key !== 'debugging')

  if (!hasAccess) {
    return (
      <PageLayout>
        <div style={{ maxWidth: 480, margin: '60px auto', textAlign: 'center' }}>
          <Shield size={40} color="#d1d5db" style={{ marginBottom: 16 }} />
          <h2 style={{ fontSize: 18, fontWeight: 600, color: '#111827' }}>Access Denied</h2>
          <p style={{ fontSize: 14, color: '#6b7280', marginTop: 8 }}>
            You must be a team admin or system administrator to view this page.
          </p>
        </div>
      </PageLayout>
    )
  }

  return (
    <PageLayout>
      <div style={{ display: 'flex', gap: 0, minHeight: 'calc(100vh - 130px)' }}>
        {/* Sidebar */}
        <nav style={{
          width: 220, flexShrink: 0,
          borderRight: '1px solid #e5e7eb',
          backgroundColor: '#fff',
          padding: '20px 0',
          borderRadius: 'var(--ui-radius, 12px) 0 0 var(--ui-radius, 12px)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 20px', marginBottom: 20 }}>
            <Shield size={20} color="#6b7280" />
            <h1 style={{ fontSize: 17, fontWeight: 700, margin: 0 }}>
              {isGlobalAdmin ? 'Admin' : 'Team Admin'}
            </h1>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2, padding: '0 8px' }}>
            {visibleTabs.map(tab => {
              const Icon = tab.icon
              const isActive = activeTab === tab.key
              return (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '10px 14px', border: 'none', cursor: 'pointer',
                    fontSize: 14, fontWeight: isActive ? 600 : 400,
                    color: isActive ? '#111827' : '#6b7280',
                    backgroundColor: isActive ? '#f3f4f6' : 'transparent',
                    borderRadius: 8, fontFamily: 'inherit',
                    transition: 'background-color 0.15s, color 0.15s',
                    width: '100%', textAlign: 'left',
                    borderLeft: isActive ? '3px solid var(--highlight-color, #eab308)' : '3px solid transparent',
                  }}
                >
                  <Icon size={18} style={{ flexShrink: 0 }} />
                  {tab.label}
                </button>
              )
            })}
          </div>
        </nav>

        {/* Content */}
        <div style={{ flex: 1, padding: '20px 32px', minWidth: 0 }}>
          {activeTab === 'usage' && <UsageTab />}
          {activeTab === 'users' && <UsersTab />}
          {activeTab === 'teams' && <TeamsTab />}
          {activeTab === 'workflows' && <WorkflowsTab />}
          {activeTab === 'quality' && <QualityTab />}
          {activeTab === 'demo' && isGlobalAdmin && <DemoTab />}
          {activeTab === 'debugging' && isGlobalAdmin && <DebuggingTab />}
          {activeTab === 'config' && isGlobalAdmin && <ConfigTab />}
        </div>
      </div>
    </PageLayout>
  )
}
