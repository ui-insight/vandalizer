import { useEffect, useState, useCallback } from 'react'
import {
  Shield, BarChart3, Users, Building2, Workflow, Settings,
  Palette, Cpu, Lock, Globe, Plus, Trash2, Pencil, ChevronLeft,
  ChevronRight, RefreshCw, MessageSquare, Search, Zap,
  CheckCircle2, XCircle, Clock, UserCircle,
} from 'lucide-react'
import { PageLayout } from '../components/layout/PageLayout'
import { useAuth } from '../hooks/useAuth'
import { useTeams } from '../hooks/useTeams'
import { getThemeConfig, updateThemeConfig } from '../api/config'
import type { ThemeConfig } from '../api/config'
import {
  getUsageStats, getUserLeaderboard, getTeamLeaderboard,
  getWorkflowEvents, getSystemConfig, updateSystemConfig,
  addModel, updateModel, deleteModel, addOAuthProvider, updateOAuthProvider,
  deleteOAuthProvider, updateAuthMethods,
} from '../api/admin'
import type {
  UsageStats, UserLeaderboardItem, TeamLeaderboardItem,
  WorkflowEventItem, PaginatedWorkflows, SystemConfigData,
} from '../api/admin'

function applyThemeToDOM(theme: ThemeConfig) {
  const root = document.documentElement
  root.style.setProperty('--highlight-color', theme.highlight_color)
  root.style.setProperty('--ui-radius', theme.ui_radius)
}

type Tab = 'usage' | 'users' | 'teams' | 'workflows' | 'config'

const TABS: { key: Tab; label: string; icon: typeof BarChart3 }[] = [
  { key: 'usage', label: 'Usage', icon: BarChart3 },
  { key: 'users', label: 'Users', icon: Users },
  { key: 'teams', label: 'Teams', icon: Building2 },
  { key: 'workflows', label: 'Workflows', icon: Workflow },
  { key: 'config', label: 'Config', icon: Settings },
]

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
  if (ms === null) return '-'
  if (ms < 1000) return `${ms}ms`
  const secs = ms / 1000
  if (secs < 60) return `${secs.toFixed(1)}s`
  const mins = Math.floor(secs / 60)
  const remainSecs = Math.round(secs % 60)
  return `${mins}m ${remainSecs}s`
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

function KpiCard({ label, value, icon: Icon, color }: { label: string; value: string | number; icon: typeof BarChart3; color: string }) {
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
        <div style={{ fontSize: 26, fontWeight: 700, color: '#111827', fontFamily: 'ui-monospace, monospace' }}>{value}</div>
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

// ──────────────────────────────────────────
// Usage Tab
// ──────────────────────────────────────────

function UsageTab() {
  const [stats, setStats] = useState<UsageStats | null>(null)
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    getUsageStats(days).then(setStats).finally(() => setLoading(false))
  }, [days])

  useEffect(() => { load() }, [load])

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
              color: days === d ? '#000' : '#374151',
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
          {/* KPI Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
            <KpiCard label="Conversations" value={formatNumber(stats.conversations)} icon={MessageSquare} color="#3b82f6" />
            <KpiCard label="Search Runs" value={formatNumber(stats.search_runs)} icon={Search} color="#8b5cf6" />
            <KpiCard label="Workflows Started" value={formatNumber(stats.workflows_started)} icon={Zap} color="#f59e0b" />
            <KpiCard label="Completed" value={formatNumber(stats.workflows_completed)} icon={CheckCircle2} color="#22c55e" />
            <KpiCard label="Failed" value={formatNumber(stats.workflows_failed)} icon={XCircle} color="#ef4444" />
            <KpiCard label="Active Users" value={formatNumber(stats.active_users)} icon={Users} color="#06b6d4" />
          </div>

          {/* Token Usage */}
          <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>Token Usage</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 24 }}>
              <div>
                <div style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase', marginBottom: 4 }}>Input Tokens</div>
                <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'ui-monospace, monospace' }}>{formatNumber(stats.tokens_in)}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase', marginBottom: 4 }}>Output Tokens</div>
                <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'ui-monospace, monospace' }}>{formatNumber(stats.tokens_out)}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase', marginBottom: 4 }}>Total Tokens</div>
                <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'ui-monospace, monospace' }}>{formatNumber(stats.tokens_in + stats.tokens_out)}</div>
              </div>
            </div>
          </div>

          {/* Summary cards */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Active Teams</div>
              <div style={{ fontSize: 36, fontWeight: 700, color: 'var(--highlight-color, #eab308)' }}>{stats.active_teams}</div>
              <div style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>in the last {days} days</div>
            </div>
            <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Active Users</div>
              <div style={{ fontSize: 36, fontWeight: 700, color: 'var(--highlight-color, #eab308)' }}>{stats.active_users}</div>
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

function UsersTab() {
  const [users, setUsers] = useState<UserLeaderboardItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getUserLeaderboard().then(setUsers).finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading users...</div>

  const maxTokens = users.length > 0 ? users[0].tokens_total : 1

  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 15, fontWeight: 600 }}>
        User Leaderboard ({users.length})
      </div>
      {users.length === 0 ? (
        <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No activity recorded yet.</div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
              <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>#</th>
              <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>User</th>
              <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Token Usage</th>
              <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Workflows</th>
              <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Last Active</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u, i) => (
              <tr key={u.user_id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                <td style={{ padding: '12px 16px', fontSize: 14, fontWeight: 600, color: '#9ca3af' }}>{i + 1}</td>
                <td style={{ padding: '12px 16px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <UserAvatar name={u.name || u.email} />
                    <div>
                      <div style={{ fontSize: 14, fontWeight: 500 }}>{u.name || 'Unknown'}</div>
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
                <td style={{ padding: '12px 16px', textAlign: 'right', fontSize: 13, color: '#6b7280' }}>{formatDate(u.last_active)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ──────────────────────────────────────────
// Teams Tab
// ──────────────────────────────────────────

function TeamsTab() {
  const [teams, setTeams] = useState<TeamLeaderboardItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getTeamLeaderboard().then(setTeams).finally(() => setLoading(false))
  }, [])

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading teams...</div>

  const maxTokens = teams.length > 0 ? teams[0].tokens_total : 1

  return (
    <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
      <div style={{ padding: '16px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 15, fontWeight: 600 }}>
        Team Leaderboard ({teams.length})
      </div>
      {teams.length === 0 ? (
        <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>No team activity recorded.</div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: '#f9fafb', borderBottom: '1px solid #e5e7eb' }}>
              <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Team</th>
              <th style={{ padding: '10px 16px', textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Token Usage</th>
              <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Workflows</th>
              <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Active Users</th>
              <th style={{ padding: '10px 16px', textAlign: 'right', fontSize: 11, fontWeight: 600, color: '#6b7280', textTransform: 'uppercase' }}>Avg Latency</th>
            </tr>
          </thead>
          <tbody>
            {teams.map((t) => (
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
                <td style={{ padding: '12px 16px', textAlign: 'right', fontSize: 13, color: '#6b7280' }}>{formatDuration(t.avg_latency_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
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
  const [loading, setLoading] = useState(true)

  const load = useCallback(() => {
    setLoading(true)
    getWorkflowEvents(page, status || undefined).then(setData).finally(() => setLoading(false))
  }, [page, status])

  useEffect(() => { load() }, [load])

  const filters = ['', 'completed', 'running', 'failed']

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Status filters */}
      <div style={{ display: 'flex', gap: 8 }}>
        {filters.map(f => (
          <button
            key={f}
            onClick={() => { setStatus(f); setPage(1) }}
            style={{
              padding: '6px 16px', borderRadius: 'var(--ui-radius, 12px)', border: '1px solid #e5e7eb',
              fontSize: 13, fontWeight: 500, cursor: 'pointer', textTransform: 'capitalize',
              backgroundColor: status === f ? 'var(--highlight-color, #eab308)' : '#fff',
              color: status === f ? '#000' : '#374151',
            }}
          >
            {f || 'All'}
          </button>
        ))}
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
                {data.items.map(ev => (
                  <tr key={ev.id} style={{ borderBottom: '1px solid #f3f4f6' }}>
                    <td style={{ padding: '10px 16px' }}><StatusBadge status={ev.status} /></td>
                    <td style={{ padding: '10px 16px', fontSize: 14, fontWeight: 500 }}>{ev.title || 'Untitled'}</td>
                    <td style={{ padding: '10px 16px', fontSize: 13, color: '#6b7280', fontFamily: 'ui-monospace, monospace' }}>{ev.user_id.slice(0, 8)}</td>
                    <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 13 }}>{ev.steps_completed}/{ev.steps_total}</td>
                    <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 13, fontFamily: 'ui-monospace, monospace' }}>
                      {formatNumber(ev.tokens_in + ev.tokens_out)}
                    </td>
                    <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 13, color: '#6b7280' }}>{formatDuration(ev.duration_ms)}</td>
                    <td style={{ padding: '10px 16px', textAlign: 'right', fontSize: 13, color: '#6b7280' }}>{formatDateTime(ev.started_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>

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
                      color: extractionMode === mode ? '#000' : '#374151',
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
                      background: 'var(--highlight-color, #eab308)', color: '#000', fontSize: 13, fontWeight: 600, cursor: 'pointer',
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
                    background: 'var(--highlight-color, #eab308)', color: '#000', fontSize: 13, fontWeight: 600, cursor: 'pointer',
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
            <div style={{ backgroundColor: themeColor, borderRadius: `${themeRadius}px`, padding: '8px 20px', color: '#000', fontWeight: 600, fontSize: 13 }}>
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

export default function Admin() {
  const { user } = useAuth()
  const { currentTeam } = useTeams()
  const [activeTab, setActiveTab] = useState<Tab>('usage')

  const isGlobalAdmin = !!user?.is_admin
  const isTeamAdmin = currentTeam?.role === 'owner' || currentTeam?.role === 'admin'
  const hasAccess = isGlobalAdmin || isTeamAdmin

  // Only global admins see the Config tab
  const visibleTabs = isGlobalAdmin ? TABS : TABS.filter(t => t.key !== 'config')

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
          {activeTab === 'config' && isGlobalAdmin && <ConfigTab />}
        </div>
      </div>
    </PageLayout>
  )
}
