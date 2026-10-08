import { useAdminViewState } from './shared/AdminViewState'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  MessageSquare, Search, Zap, CheckCircle2, XCircle, Users, AlertCircle,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'
import {
  getUsageStats, getUsageTimeseries,
} from '../../api/admin'
import type { UsageStats, TimeseriesResponse } from '../../api/admin'
import { downloadCSV, formatNumber } from './shared/format'
import { TrendDelta, KpiCard, ExportButton, TimeRangeSelector } from './shared/primitives'

const CHART_COLORS = ['#3b82f6', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4']

export function UsageTab() {
  const [stats, setStats] = useState<UsageStats | null>(null)
  const [timeseries, setTimeseries] = useState<TimeseriesResponse | null>(null)
  const [days, setDays] = useAdminViewState('UsageTab.days', 30)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [loadedDays, setLoadedDays] = useState<number | null>(null)
  const requestVersion = useRef(0)

  const load = useCallback(() => {
    const version = ++requestVersion.current
    setLoading(true)
    setError(null)
    Promise.all([getUsageStats(days), getUsageTimeseries(days)])
      .then(([s, ts]) => { if (version === requestVersion.current) { setStats(s); setTimeseries(ts); setLoadedDays(days) } })
      .catch(e => { if (version === requestVersion.current) setError(e?.message || 'Failed to load usage data') })
      .finally(() => { if (version === requestVersion.current) setLoading(false) })
  }, [days])

  useEffect(() => { load(); const requests = requestVersion; return () => { requests.current++ } }, [load])

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

  const handleExport = () => {
    if (!stats || loading || error || loadedDays !== days) return
    const dayRows = (timeseries?.days ?? []).map(d => [
      d.date, d.conversations, d.search_runs, d.workflows_started,
      d.workflows_completed, d.workflows_failed, d.tokens_in, d.tokens_out, d.active_users,
    ])
    const summaryRows: (string | number | null)[][] = [
      ['SUMMARY', '', '', '', '', '', '', '', ''],
      ['Window (days)', days, '', '', '', '', '', '', ''],
      ['Conversations', stats.conversations, '', '', '', '', '', '', ''],
      ['Search runs', stats.search_runs, '', '', '', '', '', '', ''],
      ['Workflows started', stats.workflows_started, '', '', '', '', '', '', ''],
      ['Workflows completed', stats.workflows_completed, '', '', '', '', '', '', ''],
      ['Workflows failed', stats.workflows_failed, '', '', '', '', '', '', ''],
      ['Tokens in', stats.tokens_in, '', '', '', '', '', '', ''],
      ['Tokens out', stats.tokens_out, '', '', '', '', '', '', ''],
      ['Active users', stats.active_users, '', '', '', '', '', '', ''],
      ['Active teams', stats.active_teams, '', '', '', '', '', '', ''],
      ['', '', '', '', '', '', '', '', ''],
      ['DAILY', '', '', '', '', '', '', '', ''],
    ]
    downloadCSV(
      `usage-${days}d.csv`,
      ['Date', 'Conversations', 'Searches', 'Workflows Started', 'Workflows Completed', 'Workflows Failed', 'Tokens In', 'Tokens Out', 'Active Users'],
      [...summaryRows, ...dayRows],
    )
  }

  if (loading && !stats) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading usage data...</div>

  if (error && !stats) return (
    <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
      <AlertCircle size={28} color="#d1d5db" style={{ marginBottom: 12 }} />
      <div role="alert" style={{ fontSize: 14, color: '#374151' }}>{error}</div>
      <button type="button" onClick={load} style={{ marginTop: 12, padding: '8px 12px', border: '1px solid #d1d5db', borderRadius: 6 }}>Retry usage data</button>
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <p style={{ margin: 0, fontSize: 13 }}>Selected window: last {days} days. Trends compare with the preceding {days} days. Chart dates use UTC; exported timestamps retain their recorded timezone.</p>
      {/* Time range selector */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <TimeRangeSelector value={days} onChange={v => setDays(typeof v === 'number' ? v : 30)} onRefresh={load} />
        <div style={{ flex: 1 }} />
        <ExportButton onClick={handleExport} disabled={loading || !!error || loadedDays !== days} />
      </div>

      <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: '#59616b' }}>Use this view to understand activity and investigate workflow failures. Completed means execution finished; it does not establish correct output or a successful submission. Tokens measure model input and output volume, not money or time saved. Return to the <a href="/" style={{ textDecoration: 'underline' }}>workspace</a> and open Activity to inspect your runs; team-level configuration is under Workflows.</p>
      {loading && stats && <p role="status" style={{ margin: 0, fontSize: 13, color: '#59616b' }}>Loading the selected range. Showing the last loaded {loadedDays}-day window until it is ready.</p>}
      {error && stats && <p role="alert" style={{ margin: 0, fontSize: 13, color: '#991b1b' }}>Could not load the selected range: {error}. Values below are from the last loaded {loadedDays}-day window. Use Refresh to retry.</p>}
      {stats && (
        <>
          {/* KPI Grid with trend deltas */}
          <div className="admin-metrics-grid">
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
                  <XAxis dataKey="date" tick={{ fontSize: 11, fill: 'var(--ui-text-muted, #59616b)' }} tickFormatter={v => v.slice(5)} />
                  <YAxis tick={{ fontSize: 11, fill: 'var(--ui-text-muted, #59616b)' }} width={50} />
                  <Tooltip contentStyle={{ borderRadius: 8, fontSize: 13, border: '1px solid #e5e7eb' }} />
                  <Area type="monotone" dataKey="conversations" stackId="1" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.15} name="Conversations" />
                  <Area type="monotone" dataKey="workflows_started" stackId="1" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.15} name="Workflows" />
                  <Area type="monotone" dataKey="search_runs" stackId="1" stroke="#8b5cf6" fill="#8b5cf6" fillOpacity={0.15} name="Searches" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          {timeseries?.days.length === 0 && <p style={{ margin: 0, fontSize: 13, color: '#59616b' }}>No daily records were returned for this window. The summary above is shown separately.</p>}
          {/* Token + Workflow donut charts side by side */}
          <div className="admin-chart-grid">
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
                    <Tooltip formatter={(v) => formatNumber(Number(v ?? 0))} contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                    <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>

            <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Workflow Status</div>
              <p style={{ fontSize: 12, lineHeight: 1.5, color: '#59616b', margin: '0 0 12px' }}>Completion rate is completed runs divided by started runs in this window. Other includes runs without a completed or failed state.</p>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 16 }}>
                <div>
                  <div style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase', marginBottom: 4 }}>Completion Rate</div>
                  <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'ui-monospace, monospace' }}>
                    {stats.workflows_started > 0 ? `${Math.round((stats.workflows_completed / stats.workflows_started) * 100)}%` : '-'}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: '#6b7280', textTransform: 'uppercase', marginBottom: 4 }}>Total</div>
                  <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'ui-monospace, monospace' }}>{formatNumber(stats.workflows_started)}</div>
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
          <div className="admin-chart-grid">
            <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Active Teams</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <div style={{ fontSize: 36, fontWeight: 700, color: 'var(--highlight-on-light, #806600)' }}>{stats.active_teams}</div>
                {prev && <TrendDelta current={stats.active_teams} previous={prev.active_teams} />}
              </div>
              <div style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>in the last {loadedDays ?? days} days</div>
            </div>
            <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Active Users</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                <div style={{ fontSize: 36, fontWeight: 700, color: 'var(--highlight-on-light, #806600)' }}>{stats.active_users}</div>
                {prev && <TrendDelta current={stats.active_users} previous={prev.active_users} />}
              </div>
              <div style={{ fontSize: 13, color: '#6b7280', marginTop: 4 }}>in the last {loadedDays ?? days} days</div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
