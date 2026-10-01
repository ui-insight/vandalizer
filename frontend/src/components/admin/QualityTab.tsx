import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertCircle, BarChart3, CheckCircle2, Clock, Minus, Play, RefreshCw,
  ShieldCheck, TrendingDown, TrendingUp, XCircle,
} from 'lucide-react'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

import {
  acknowledgeAlert, getJudgeCalibration, getQualityAlerts, getQualityByModel,
  getQualityItemDetail, getQualityItems, getQualitySummary, getQualityTimeline,
  getRegressionSuiteRun, getRegressionSuiteRuns, runRegressionSuite,
  type RegressionItemResult, type RegressionSuiteRunDetail,
} from '../../api/admin'
import { getModels } from '../../api/config'

type SuiteRow = RegressionItemResult & { otherScore?: number | null; compareDelta?: number | null }
import { useToast } from '../../contexts/ToastContext'
import { relativeTime } from '../../utils/time'
import { downloadCSV } from './shared/format'
import { ExportButton, KpiCard, SortableHeader } from './shared/primitives'
import { TableRegion } from './shared/TableRegion'
import { useAdminQuery } from './shared/useAdminQuery'

export function QualityTab() {
  const { toast } = useToast()
  const [days, setDays] = useState(90)
  const [regressionStarting, setRegressionStarting] = useState(false)
  const starting = useRef(false)
  const [regressionModel, setRegressionModel] = useState('')
  const [activeSuite, setActiveSuite] = useState<RegressionSuiteRunDetail | null>(null)
  const [compareSuite, setCompareSuite] = useState<RegressionSuiteRunDetail | null>(null)
  const [selectedRun, setSelectedRun] = useState('')
  const [comparisonRun, setComparisonRun] = useState('')
  const [suiteError, setSuiteError] = useState<string | null>(null)
  const [comparisonError, setComparisonError] = useState<string | null>(null)
  const suiteVersion = useRef(0)
  const comparisonVersion = useRef(0)
  const acknowledging = useRef(new Set<string>())
  const [pendingAlerts, setPendingAlerts] = useState<string[]>([])
  const [expandedItem, setExpandedItem] = useState<{ kind: string; id: string } | null>(null)
  const [itemSort, setItemSort] = useState<{ key: string; dir: 'asc' | 'desc' }>({ key: 'score', dir: 'asc' })

  const request = useCallback(() => Promise.all([
    getQualitySummary(), getQualityTimeline(days), getQualityAlerts(50, false), getQualityItems('score', 'asc', 100),
  ]), [days])
  const { data, setData, loading, error, load } = useAdminQuery(request)
  const summary = data?.[0] ?? null
  const timeline = data?.[1].timeline ?? []
  const alerts = data?.[2].alerts ?? []
  const qualityItems = useMemo(() => data?.[3].items ?? [], [data])
  // Independent panels expose their own recovery without blanking the whole tab.
  const calibrationQuery = useAdminQuery(getJudgeCalibration)
  const judgeCalibration = calibrationQuery.data?.surfaces ?? []
  const modelsQuery = useAdminQuery(getModels)
  const availableModels = modelsQuery.data ?? []
  const runsQuery = useAdminQuery(getRegressionSuiteRuns)
  const suiteRuns = runsQuery.data?.runs ?? []
  const loadSuiteRuns = runsQuery.load
  const modelRequest = useCallback(() => getQualityByModel(days), [days])
  const modelQuery = useAdminQuery(modelRequest)
  const modelRows = modelQuery.data?.models ?? []
  const loadModelRows = modelQuery.load
  const itemRequest = useCallback(() => expandedItem ? getQualityItemDetail(expandedItem.kind, expandedItem.id) : Promise.resolve(null), [expandedItem])
  const itemQuery = useAdminQuery(itemRequest)
  const itemDetail = itemQuery.data

  useEffect(() => () => { suiteVersion.current++; comparisonVersion.current++ }, [])

  // A response for a previously viewed run must never replace the current one.
  useEffect(() => {
    if (activeSuite?.status !== 'running') return
    let cancelled = false
    let pending = false
    const runUuid = activeSuite.run_uuid
    const id = setInterval(async () => {
      if (pending) return
      pending = true
      try {
        const result = await getRegressionSuiteRun(runUuid)
        if (cancelled) return
        setActiveSuite(result)
        setSuiteError(null)
        if (result.status !== 'running') { loadSuiteRuns(); loadModelRows() }
      } catch (reason) {
        if (!cancelled) setSuiteError(reason instanceof Error ? reason.message : 'Unable to refresh this run.')
      } finally { pending = false }
    }, 4000)
    return () => { cancelled = true; clearInterval(id) }
  }, [activeSuite?.status, activeSuite?.run_uuid, loadSuiteRuns, loadModelRows])

  const handleViewSuite = async (runUuid: string) => {
    const version = ++suiteVersion.current
    comparisonVersion.current++
    setSelectedRun(runUuid)
    setComparisonRun('')
    setComparisonError(null)
    setCompareSuite(null)
    setActiveSuite(null)
    setSuiteError(null)
    try {
      const result = await getRegressionSuiteRun(runUuid)
      if (version === suiteVersion.current) setActiveSuite(result)
    } catch (reason) {
      if (version === suiteVersion.current) setSuiteError(reason instanceof Error ? reason.message : 'Unable to load this run.')
    }
  }

  const handleRunRegression = async () => {
    if (starting.current) return
    starting.current = true
    setRegressionStarting(true)
    try {
      const { run_uuid } = await runRegressionSuite(regressionModel || undefined)
      // Once accepted, a failed status read must retry this run, not start another.
      await handleViewSuite(run_uuid)
      loadSuiteRuns()
    } catch (reason) {
      toast(`Failed to start regression suite: ${reason instanceof Error ? reason.message : 'unknown error'}`, 'error')
    } finally {
      starting.current = false
      setRegressionStarting(false)
    }
  }

  const handleCompareSuite = async (runUuid: string) => {
    const version = ++comparisonVersion.current
    setComparisonRun(runUuid)
    setComparisonError(null)
    setCompareSuite(null)
    if (!runUuid) return
    try {
      const result = await getRegressionSuiteRun(runUuid)
      if (version === comparisonVersion.current) setCompareSuite(result)
    } catch (reason) {
      if (version === comparisonVersion.current) setComparisonError(reason instanceof Error ? reason.message : 'Unable to load comparison.')
    }
  }

  // Join the two suites' per-item rows by (kind, item_id) so two models'
  // sweeps line up even when item order or coverage differs.
  const suiteComparison = useMemo(() => {
    if (!activeSuite || !compareSuite) return null
    const byKey = new Map(compareSuite.results.map(r => [`${r.kind}:${r.item_id}`, r]))
    return activeSuite.results.map(r => {
      const other = byKey.get(`${r.kind}:${r.item_id}`) ?? null
      const delta = r.score != null && other?.score != null
        ? Math.round((r.score - other.score) * 10) / 10
        : null
      return { ...r, otherScore: other?.score ?? null, compareDelta: delta }
    })
  }, [activeSuite, compareSuite])

  const handleAcknowledgeAlert = async (uuid: string) => {
    if (acknowledging.current.has(uuid)) return
    acknowledging.current.add(uuid)
    setPendingAlerts([...acknowledging.current])
    try {
      await acknowledgeAlert(uuid)
      setData(previous => previous ? [previous[0], previous[1], { alerts: previous[2].alerts.filter(alert => alert.uuid !== uuid) }, previous[3]] : previous)
    } catch (e) {
      toast(`Failed to acknowledge alert: ${e instanceof Error ? e.message : 'unknown error'}`, 'error')
    } finally {
      acknowledging.current.delete(uuid)
      setPendingAlerts([...acknowledging.current])
    }
  }

  const handleExpandItem = (kind: string, id: string) => {
    setExpandedItem(previous => previous?.kind === kind && previous.id === id ? null : { kind, id })
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
      <div role="alert" style={{ fontSize: 14, color: '#374151' }}>{error}</div>
      <button type="button" onClick={load} className="admin-open-record">Retry quality data</button>
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24, minWidth: 0, overflowWrap: 'anywhere' }}>
      <p style={{ fontSize: 13, color: '#59616b', margin: 0 }}>Recorded validation scores measure performance on test cases. Review the affected item and its evidence before relying on it for a new document.</p>
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
                    display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 12,
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
                  <div style={{ flex: '1 1 180px', minWidth: 0 }}>
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
                  <span style={{ fontSize: 11, color: '#59616b', flexShrink: 0, whiteSpace: 'nowrap' }}>
                    {alert.created_at ? relativeTime(alert.created_at) : '-'}
                  </span>
                  <button
                    onClick={() => handleAcknowledgeAlert(alert.uuid)}
                    aria-label={`Acknowledge alert for ${alert.item_name}`}
                    disabled={pendingAlerts.includes(alert.uuid)}
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
              aria-label="Quality time range"
              value={days}
              onChange={e => setDays(Number(e.target.value))}
              style={{ maxWidth: '100%', padding: '4px 8px', fontSize: 12, borderRadius: 6, border: '1px solid #e5e7eb' }}
            >
              <option value={30}>30 days</option>
              <option value={60}>60 days</option>
              <option value={90}>90 days</option>
              <option value={180}>180 days</option>
              <option value={365}>1 year</option>
              <option value={730}>2 years</option>
            </select>
            <ExportButton disabled={loading || !!error} onClick={() => downloadCSV(
              `quality-timeline-${days}d.csv`,
              ['Date', 'Avg Score', 'Run Count', 'Items Validated'],
              timeline.map(p => [p.date, p.avg_score, p.run_count, p.items_validated]),
            )} />
          </div>
        </div>
        {timeline.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px 0', color: '#59616b', fontSize: 13 }}>
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
        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
          <select
            aria-label="Regression model"
            value={regressionModel}
            onChange={e => setRegressionModel(e.target.value)}
            style={{ padding: '6px 12px', fontSize: 13, borderRadius: 6, border: '1px solid #e5e7eb', minWidth: 0, maxWidth: '100%', flex: '0 1 280px' }}
          >
            <option value="">Default Model</option>
            {availableModels.map((m, i) => (
              <option key={i} value={m.name}>{m.name} ({m.tag})</option>
            ))}
          </select>
          <button
            onClick={handleRunRegression}
            disabled={regressionStarting || (!!selectedRun && !activeSuite) || activeSuite?.status === 'running'}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              padding: '6px 16px', borderRadius: 'var(--ui-radius, 12px)',
              border: 'none', background: '#111827', color: '#fff',
              fontSize: 13, fontWeight: 600,
              cursor: (regressionStarting || (!!selectedRun && !activeSuite) || activeSuite?.status === 'running') ? 'wait' : 'pointer',
              opacity: (regressionStarting || (!!selectedRun && !activeSuite) || activeSuite?.status === 'running') ? 0.6 : 1,
            }}
          >
            {(regressionStarting || (!!selectedRun && !activeSuite) || activeSuite?.status === 'running') ? (
              <><RefreshCw size={14} /> {regressionStarting ? 'Starting…' : activeSuite?.status === 'running' ? 'Running…' : 'Awaiting run status'}</>
            ) : (
              <><Play size={14} /> Run Regression Suite</>
            )}
          </button>
        </div>

        {modelsQuery.error && <ReadFailure message={modelsQuery.error} retry={modelsQuery.load} label="Retry models" />}
        {runsQuery.error && <ReadFailure message={runsQuery.error} retry={loadSuiteRuns} label="Retry suite history" />}
        {suiteError && <ReadFailure message={`Run ${selectedRun}: ${suiteError}`} retry={() => handleViewSuite(selectedRun)} label="Retry run status" />}
        {selectedRun && !activeSuite && !suiteError && <p role="status">Loading selected run…</p>}
        {suiteRuns.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
            {suiteRuns.map(run => {
              const isActive = activeSuite?.run_uuid === run.run_uuid
              return (
                <button
                  key={run.run_uuid}
                  onClick={() => handleViewSuite(run.run_uuid)}
                  aria-pressed={selectedRun === run.run_uuid}
                  title={run.started_at ? new Date(run.started_at).toLocaleString() : undefined}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 6,
                    padding: '4px 10px', borderRadius: 9999, fontSize: 12,
                    border: isActive ? '1px solid #111827' : '1px solid #e5e7eb',
                    background: isActive ? '#111827' : '#fff',
                    color: isActive ? '#fff' : '#374151', cursor: 'pointer',
                  }}
                >
                  <span style={{ fontWeight: 600 }}>{run.model || 'default'}</span>
                  <span>
                    {run.status === 'running'
                      ? `${run.completed_items}/${run.total_items || '?'}…`
                      : run.status === 'failed'
                        ? 'failed'
                        : run.mean_score != null ? `${run.mean_score}%` : '—'}
                  </span>
                  {run.started_at && (
                    <span>{relativeTime(run.started_at)}</span>
                  )}
                </button>
              )
            })}
          </div>
        )}

        {activeSuite && (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 16, marginBottom: 12, fontSize: 13 }}>
              <span style={{
                fontSize: 11, fontWeight: 700, padding: '2px 10px', borderRadius: 9999, textTransform: 'uppercase',
                background: activeSuite.status === 'completed' ? '#dcfce7' : activeSuite.status === 'failed' ? '#fee2e2' : '#dbeafe',
                color: activeSuite.status === 'completed' ? '#166534' : activeSuite.status === 'failed' ? '#991b1b' : '#1e40af',
              }}>{activeSuite.status}</span>
              <span style={{ color: '#6b7280' }}>Model: <strong>{activeSuite.model || 'default'}</strong></span>
              <span style={{ color: '#6b7280' }}>
                {activeSuite.status === 'running'
                  ? <>Progress: <strong>{activeSuite.completed_items}/{activeSuite.total_items || '?'}</strong></>
                  : <>Total: <strong>{activeSuite.total_items}</strong></>}
              </span>
              <span style={{ color: '#15803d' }}>Succeeded: <strong>{activeSuite.succeeded}</strong></span>
              <span style={{ color: '#dc2626' }}>Failed: <strong>{activeSuite.failed}</strong></span>
              {activeSuite.mean_score != null && (
                <span style={{ color: '#111827', fontSize: 15 }}>
                  Catalog mean: <strong>{activeSuite.mean_score}%</strong>
                </span>
              )}
              {activeSuite.status === 'completed' && suiteRuns.some(r => r.status === 'completed' && r.run_uuid !== activeSuite.run_uuid) && (
                <label style={{ marginLeft: 'auto', display: 'flex', flexWrap: 'wrap', maxWidth: '100%', alignItems: 'center', gap: 6, color: '#6b7280' }}>
                  Compare with
                  <select
                    value={comparisonRun}
                    onChange={e => handleCompareSuite(e.target.value)}
                    style={{ maxWidth: '100%', padding: '4px 8px', fontSize: 12, borderRadius: 6, border: '1px solid #e5e7eb' }}
                  >
                    <option value="">—</option>
                    {suiteRuns
                      .filter(r => r.status === 'completed' && r.run_uuid !== activeSuite.run_uuid)
                      .map(r => (
                        <option key={r.run_uuid} value={r.run_uuid}>
                          {r.model || 'default'} · {r.mean_score != null ? `${r.mean_score}%` : '—'} · {r.started_at ? relativeTime(r.started_at) : ''}
                        </option>
                      ))}
                  </select>
                </label>
              )}
            </div>
            {activeSuite.status === 'failed' && activeSuite.error && (
              <div style={{ marginBottom: 12, padding: '8px 12px', borderRadius: 8, background: '#fee2e2', color: '#991b1b', fontSize: 13 }}>
                {activeSuite.error}
              </div>
            )}
            {comparisonError && <ReadFailure message={comparisonError} retry={() => handleCompareSuite(comparisonRun)} label="Retry comparison" />}
            {compareSuite && suiteComparison && (
              <div style={{ marginBottom: 12, fontSize: 13, color: '#6b7280' }}>
                Mean: <strong style={{ color: '#111827' }}>{activeSuite.model || 'default'} {activeSuite.mean_score != null ? `${activeSuite.mean_score}%` : '—'}</strong>
                {' vs '}
                <strong style={{ color: '#111827' }}>{compareSuite.model || 'default'} {compareSuite.mean_score != null ? `${compareSuite.mean_score}%` : '—'}</strong>
              </div>
            )}
            <TableRegion label="Regression suite results — scroll for more columns">
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>Name</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>Kind</th>
                    <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>
                      {compareSuite ? `Score (${activeSuite.model || 'default'})` : 'Score'}
                    </th>
                    {compareSuite ? (
                      <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>
                        Score ({compareSuite.model || 'default'})
                      </th>
                    ) : (
                      <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>Grade</th>
                    )}
                    <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>Delta</th>
                    <th style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {((suiteComparison ?? activeSuite.results) as SuiteRow[]).map((r, i) => {
                    const delta = suiteComparison ? r.compareDelta ?? null : r.delta
                    return (
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
                        {suiteComparison ? (
                          <td style={{ padding: '8px 12px', textAlign: 'right', fontFamily: 'ui-monospace, monospace' }}>
                            {r.otherScore != null ? `${r.otherScore}%` : '-'}
                          </td>
                        ) : (
                          <td style={{ padding: '8px 12px', textAlign: 'center', fontWeight: 700 }}>
                            {r.grade || '-'}
                          </td>
                        )}
                        <td style={{
                          padding: '8px 12px', textAlign: 'right', fontWeight: 600,
                          color: delta == null ? '#59616b' : delta > 0 ? '#15803d' : delta < 0 ? '#dc2626' : '#59616b',
                        }}>
                          {delta == null ? '-' : delta > 0 ? `+${delta}` : delta}
                        </td>
                        <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                          {r.status === 'ok' ? (
                            <CheckCircle2 size={16} color="#15803d" />
                          ) : (
                            <span style={{ fontSize: 11, color: '#dc2626' }}>{r.status}</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </TableRegion>
          </div>
        )}
      </div>

      {/* Model Performance (by-model rollup) */}
      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
        <h3 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 4px' }}>Model Performance</h3>
        <p style={{ fontSize: 13, color: '#6b7280', margin: '0 0 12px' }}>
          Validation quality over the last {days} days, grouped by the model that executed each run.
        </p>
        {modelQuery.error ? <ReadFailure message={modelQuery.error} retry={modelQuery.load} label="Retry model performance" /> : modelQuery.loading ? <p role="status">Loading model performance…</p> : modelRows.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: '#59616b', fontSize: 13 }}>
            No validation runs in this window yet.
          </div>
        ) : (
          <TableRegion label="Quality by model — scroll for more columns">
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>Model</th>
                  <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>Avg Score</th>
                  <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>Runs</th>
                  <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>Items</th>
                  <th style={{ padding: '8px 12px', textAlign: 'left', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>By Kind</th>
                  <th style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 600, color: '#6b7280', fontSize: 11, textTransform: 'uppercase' }}>Last Run</th>
                </tr>
              </thead>
              <tbody>
                {modelRows.map((row, i) => {
                  const scoreColor = row.avg_score >= 90 ? '#15803d'
                    : row.avg_score >= 70 ? '#2563eb'
                    : row.avg_score >= 50 ? '#92400e'
                    : '#dc2626'
                  return (
                    <tr key={i} style={{ borderBottom: '1px solid #f3f4f6' }}>
                      <td style={{ padding: '8px 12px', fontWeight: 500, color: row.model ? '#111827' : '#59616b' }}
                        title={row.model ? undefined : 'Runs that recorded no task model — older history, and workflow validations graded over mixed-model executions'}>
                        {row.model || '(unattributed)'}
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', fontFamily: 'ui-monospace, monospace', fontWeight: 700, color: scoreColor }}>
                        {row.avg_score}%
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', fontFamily: 'ui-monospace, monospace' }}>{row.run_count}</td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', fontFamily: 'ui-monospace, monospace' }}>{row.items_validated}</td>
                      <td style={{ padding: '8px 12px', color: '#6b7280', fontSize: 12 }}>
                        {Object.entries(row.kinds).map(([kind, k]) => `${kind.replace('_', ' ')}: ${k.avg_score}% (${k.run_count})`).join(' · ')}
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'right', color: '#6b7280', fontSize: 12 }}>
                        {row.last_run_at ? relativeTime(row.last_run_at) : '-'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </TableRegion>
        )}
      </div>

      {/* Per-Item Quality Table */}
      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', overflow: 'hidden' }}>
        <div style={{ padding: '14px 20px', borderBottom: '1px solid #e5e7eb', fontSize: 15, fontWeight: 600 }}>
          Per-Item Quality ({qualityItems.length})
        </div>
        {qualityItems.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: '#59616b', fontSize: 13 }}>
            No quality items found. Validate items to see them here.
          </div>
        ) : (
          <TableRegion label="Quality by item — scroll for more columns">
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
                  const scoreColor = item.quality_score == null ? '#59616b'
                    : item.quality_score >= 90 ? '#15803d'
                    : item.quality_score >= 70 ? '#2563eb'
                    : item.quality_score >= 50 ? '#92400e'
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
                        style={{
                          borderBottom: '1px solid #f3f4f6',
                          background: isExpanded ? '#f9fafb' : undefined,
                        }}
                      >
                        <td style={{ padding: '10px 16px', fontWeight: 500 }}><button type="button" className="admin-open-record" aria-expanded={isExpanded} onClick={() => handleExpandItem(item.item_kind, item.item_id)} aria-label={`View quality for ${item.display_name}`}>{item.display_name}</button></td>
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
                          {item.trend === 'up' && <TrendingUp size={16} color="#15803d" />}
                          {item.trend === 'down' && <TrendingDown size={16} color="#dc2626" />}
                          {item.trend === 'flat' && <Minus size={16} color="#59616b" />}
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
                              {itemQuery.error ? <ReadFailure message={itemQuery.error} retry={itemQuery.load} label="Retry item quality" /> : !itemDetail ? (
                                <div style={{ textAlign: 'center', padding: '20px 0', color: '#59616b', fontSize: 13 }}>
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
                                      <div style={{ textAlign: 'center', padding: '20px 0', color: '#59616b', fontSize: 12 }}>
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
                                      <div style={{ textAlign: 'center', padding: '20px 0', color: '#59616b', fontSize: 12 }}>
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
                                              <div style={{ fontSize: 11, color: '#59616b' }}>{mc.run_count} run{mc.run_count !== 1 ? 's' : ''}</div>
                                            </div>
                                            <div style={{
                                              fontSize: 18, fontWeight: 700, fontFamily: 'ui-monospace, monospace',
                                              color: mc.avg_score >= 90 ? '#15803d' : mc.avg_score >= 70 ? '#2563eb' : mc.avg_score >= 50 ? '#92400e' : '#dc2626',
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
          </TableRegion>
        )}
      </div>

      {/* Judge Calibration */}
      {(calibrationQuery.loading || calibrationQuery.error || judgeCalibration.length > 0) && (
        <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
          <h3 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 12px' }}>Judge Calibration</h3>
          <p style={{ fontSize: 13, color: '#6b7280', margin: '0 0 16px' }}>
            Every quality score here is produced by an LLM judge. The published agreement
            floors were measured against the model this project&apos;s weekly integration job
            runs on — <strong>not</strong> against your models. A model shown as unmeasured
            carries no agreement figure at all, rather than borrowing one.
          </p>
          {calibrationQuery.error && <ReadFailure message={calibrationQuery.error} retry={calibrationQuery.load} label="Retry judge calibration" />}
          {calibrationQuery.loading && <p role="status">Loading calibration…</p>}
          {judgeCalibration.map(surface => (
            <div key={surface.surface} style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span style={{ fontSize: 13, fontWeight: 600, textTransform: 'capitalize' }}>
                  {surface.surface}
                </span>
                {surface.published_floor != null && (
                  <span style={{ fontSize: 12, color: '#6b7280', fontFamily: 'ui-monospace, monospace' }}>
                    published floor κ ≥ {surface.published_floor.toFixed(2)}
                  </span>
                )}
                {!surface.drift_detectable && (
                  <span style={{
                    fontSize: 11, padding: '1px 6px', borderRadius: 4,
                    background: '#fffbeb', border: '1px solid #fde68a', color: '#a16207',
                  }}>
                    drift undetectable — no model has 3 runs yet ({surface.ledger_entries} in the ledger)
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {surface.models.length === 0 && (
                  <span style={{ fontSize: 12, color: '#6b7280' }}>No models configured.</span>
                )}
                {surface.models.map(m => {
                  // Three states, not two. A model measured once has a κ but no
                  // baseline to detect drift against — presenting that as the
                  // same settled green as a model with a real history is the
                  // over-claim this panel exists to stop. `calibration_for`
                  // says it plainly: one run is a data point, not a baseline.
                  const thin = m.calibrated && !m.drift_detectable
                  const palette = !m.calibrated
                    ? { border: '#e5e7eb', background: '#f9fafb', color: '#6b7280' }
                    : thin
                      ? { border: '#fde68a', background: '#fffbeb', color: '#a16207' }
                      : { border: '#bbf7d0', background: '#f0fdf4', color: '#15803d' }
                  return (
                    <span
                      key={m.judge_model}
                      title={m.calibrated
                        ? `κ ${m.kappa?.toFixed(3)} over ${m.n_runs} run(s), last measured ${m.measured_at}`
                          + (thin ? ' — too few runs for drift detection (needs 3)' : '')
                        : 'This model has never been measured against human-labeled cases on this surface.'}
                      style={{
                        fontSize: 11, padding: '2px 8px', borderRadius: 4,
                        border: `1px solid ${palette.border}`,
                        background: palette.background,
                        color: palette.color,
                        fontFamily: 'ui-monospace, monospace',
                      }}
                    >
                      {m.judge_model}: {m.calibrated ? `κ ${m.kappa?.toFixed(2)}` : 'κ unmeasured'}
                      {thin && ` (${m.n_runs} of 3 runs)`}
                    </span>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Monitoring Status */}
      <div style={{ background: '#fff', border: '1px solid #e5e7eb', borderRadius: 'var(--ui-radius, 12px)', padding: 20 }}>
        <h3 style={{ fontSize: 15, fontWeight: 600, margin: '0 0 16px' }}>Monitoring Status</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 180px), 1fr))', gap: 16 }}>
          <div style={{
            padding: 16, borderRadius: 'var(--ui-radius, 12px)', background: '#f0fdf4',
            border: '1px solid #bbf7d0', textAlign: 'center',
          }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: '#166534', fontFamily: 'ui-monospace, monospace' }}>
              {qualityItems.length}
            </div>
            <div style={{ fontSize: 12, color: '#15803d', fontWeight: 500, marginTop: 4 }}>Loaded items (up to 100)</div>
          </div>
          <div style={{
            padding: 16, borderRadius: 'var(--ui-radius, 12px)', background: '#fffbeb',
            border: '1px solid #fde68a', textAlign: 'center',
          }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: '#92400e', fontFamily: 'ui-monospace, monospace' }}>
              {alerts.length}
            </div>
            <div style={{ fontSize: 12, color: '#a16207', fontWeight: 500, marginTop: 4 }}>Open alerts (up to 50)</div>
          </div>
          <div style={{
            padding: 16, borderRadius: 'var(--ui-radius, 12px)', background: '#fef2f2',
            border: '1px solid #fecaca', textAlign: 'center',
          }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: '#991b1b', fontFamily: 'ui-monospace, monospace' }}>
              {qualityItems.filter(i => i.stale).length}
            </div>
            <div style={{ fontSize: 12, color: '#b91c1c', fontWeight: 500, marginTop: 4 }}>Stale loaded items</div>
          </div>
        </div>
      </div>
    </div>
  )
}

function ReadFailure({ message, retry, label }: { message: string; retry: () => void; label: string }) {
  return <div style={{ margin: '8px 0', fontSize: 13, color: '#991b1b' }}><p role="alert">{message}</p><button type="button" className="admin-open-record" onClick={retry}>{label}</button></div>
}
