import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertCircle, BarChart3, CheckCircle2, Clock, Minus, Play, RefreshCw,
  ShieldCheck, TrendingDown, TrendingUp, XCircle,
} from 'lucide-react'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

import {
  acknowledgeAlert, getQualityAlerts, getQualityItemDetail, getQualityItems,
  getQualitySummary, getQualityTimeline, getSystemConfig, runRegressionSuite,
  type QualityAlert, type QualityItem, type QualityItemDetail, type QualitySummary,
  type QualityTimelinePoint, type RegressionResult, type SystemConfigData,
} from '../../api/admin'
import { useToast } from '../../contexts/ToastContext'
import { relativeTime } from '../../utils/time'
import { downloadCSV } from './shared/format'
import { ExportButton, KpiCard, SortableHeader } from './shared/primitives'

export function QualityTab() {
  const { toast } = useToast()
  const [summary, setSummary] = useState<QualitySummary | null>(null)
  const [timeline, setTimeline] = useState<QualityTimelinePoint[]>([])
  const [days, setDays] = useState(90)
  const [loading, setLoading] = useState(true)
  const [regressionResult, setRegressionResult] = useState<RegressionResult | null>(null)
  const [regressionRunning, setRegressionRunning] = useState(false)
  const [regressionModel, setRegressionModel] = useState('')
  const [cfg, setCfg] = useState<SystemConfigData | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Alert feed state
  const [alerts, setAlerts] = useState<QualityAlert[]>([])

  // Per-item quality state
  const [qualityItems, setQualityItems] = useState<QualityItem[]>([])
  const [expandedItem, setExpandedItem] = useState<{ kind: string; id: string } | null>(null)
  const [itemDetail, setItemDetail] = useState<QualityItemDetail | null>(null)
  const [itemSort, setItemSort] = useState<{ key: string; dir: 'asc' | 'desc' }>({ key: 'score', dir: 'asc' })

  const load = useCallback(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([
      getQualitySummary(),
      getQualityTimeline(days),
      getQualityAlerts(50, false),
      getQualityItems('score', 'asc', 100),
    ]).then(([s, t, a, qi]) => {
      if (cancelled) return
      setSummary(s)
      setTimeline(t.timeline)
      setAlerts(a.alerts)
      setQualityItems(qi.items)
    }).catch(e => { if (!cancelled) setError(e?.message || 'Failed to load quality data') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [days])

  useEffect(() => load(), [load])

  // Config is fetched separately and tolerantly: it's superadmin-only
  // (`GET /api/admin/config` calls `_require_superadmin`), so staff users
  // reject it. It only feeds the optional model <select> in the regression
  // panel below, which degrades to an empty/default-only list when cfg is
  // null — it must not block the tab's real payload (the four calls above).
  useEffect(() => {
    let cancelled = false
    getSystemConfig().then(cfg => { if (!cancelled) setCfg(cfg) }).catch(() => {})
    return () => { cancelled = true }
  }, [])

  const handleRunRegression = async () => {
    setRegressionRunning(true)
    try {
      const result = await runRegressionSuite(regressionModel || undefined)
      setRegressionResult(result)
    } catch (e) {
      toast(`Failed to run regression suite: ${e instanceof Error ? e.message : 'unknown error'}`, 'error')
    } finally {
      setRegressionRunning(false)
    }
  }

  const handleAcknowledgeAlert = async (uuid: string) => {
    try {
      await acknowledgeAlert(uuid)
      setAlerts(prev => prev.filter(a => a.uuid !== uuid))
    } catch (e) {
      toast(`Failed to acknowledge alert: ${e instanceof Error ? e.message : 'unknown error'}`, 'error')
    }
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

  if (loading && !summary) return <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>Loading quality data...</div>

  if (error && !summary) return (
    <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
      <AlertCircle size={28} color="#d1d5db" style={{ marginBottom: 12 }} />
      <div style={{ fontSize: 14, color: '#374151' }}>{error}</div>
    </div>
  )

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
                      {(alert.alert_type === 'regression' || alert.alert_type === 'baseline_drift') && alert.previous_score != null && alert.current_score != null && (
                        <span style={{
                          marginLeft: 8, fontFamily: 'ui-monospace, monospace', fontWeight: 600,
                          color: '#dc2626',
                        }}>
                          {alert.previous_score} &rarr; {alert.current_score}
                        </span>
                      )}
                      {alert.alert_type === 'baseline_drift' && (
                        <span style={{
                          marginLeft: 8, padding: '1px 6px', borderRadius: 4,
                          backgroundColor: '#fef3c7', color: '#78350f',
                          fontSize: 10, fontWeight: 700, textTransform: 'uppercase',
                        }}>
                          Drift
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
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16, gap: 12, flexWrap: 'wrap' }}>
          <h3 style={{ fontSize: 15, fontWeight: 600, margin: 0 }}>Quality Timeline</h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <select
              value={days}
              onChange={e => setDays(Number(e.target.value))}
              style={{ padding: '4px 8px', fontSize: 12, borderRadius: 6, border: '1px solid #e5e7eb' }}
            >
              <option value={30}>30 days</option>
              <option value={60}>60 days</option>
              <option value={90}>90 days</option>
              <option value={180}>180 days</option>
              <option value={365}>1 year</option>
              <option value={730}>2 years</option>
            </select>
            <ExportButton onClick={() => downloadCSV(
              `quality-timeline-${days}d.csv`,
              ['Date', 'Avg Score', 'Run Count', 'Items Validated'],
              timeline.map(p => [p.date, p.avg_score, p.run_count, p.items_validated]),
            )} />
          </div>
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
                formatter={(value) => [`${Number(value ?? 0)}%`, 'Avg Score']}
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
                                            formatter={(value) => [`${Number(value ?? 0)}%`, 'Score']}
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
