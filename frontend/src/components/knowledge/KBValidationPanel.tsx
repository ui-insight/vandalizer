import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ShieldCheck, Loader2, Sparkles } from 'lucide-react'
import {
  listKBTestQueries,
  getKBQuality,
  runKBValidationAsync,
  type KBTestQuery,
  type KBValidationMode,
  type KBValidationResult,
} from '../../api/knowledge'
import { AutovalidateTab } from './AutovalidateTab'
import { KBTestQueriesTab } from './KBTestQueriesTab'
import { KBValidationRunTab } from './KBValidationRunTab'
import { KBQualityHistoryTab } from './KBQualityHistoryTab'

type Tab = 'autovalidate' | 'queries' | 'run' | 'history'

interface Props {
  kbUuid: string
  kbReady: boolean
  canManage: boolean
  /** Called with the new KB's uuid after the user clones a KB they can't
   * manage, so the parent can navigate to their own copy. */
  onCloned?: (newUuid: string) => void
}

// Validation runs off the request/response path (a background Celery task), so
// the UI polls the quality history until the new run lands instead of blocking
// on a single long HTTP call that would trip the 60s client fetch timeout.
const POLL_INTERVAL_MS = 4000
const MAX_POLL_MS = 10 * 60 * 1000 // give up after 10 min; the run still lands in History
const sleep = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms))

// One row of GET /knowledge/{uuid}/quality history. ``result_snapshot`` carries
// the full KBValidationResult the Run-now tab renders, so we can hydrate the
// rich result view straight from the polled history without a second fetch.
type KBHistoryItem = {
  uuid?: string
  score?: number
  judge_model?: string | null
  num_queries_judged?: number | null
  num_test_queries?: number | null
  mode?: string | null
  created_at?: string | null
  result_snapshot?: KBValidationResult | null
}

const TAB_LABELS: { id: Tab; label: string; icon?: typeof Sparkles }[] = [
  { id: 'autovalidate', label: 'Validate', icon: Sparkles },
  { id: 'queries', label: 'Test Queries' },
  { id: 'run', label: 'Run now' },
  { id: 'history', label: 'History' },
]

/** Provenance summary for the score chip in the validation header. We surface
 * judge model, eval-set size, mode, and age so users can tell whether the
 * "85" they see is fresh, on a comparable judge, and on a comparable set —
 * which addresses the audit's "no labeling, no reconciliation" gap. */
type LatestQualitySummary = {
  score: number
  judgeModel: string | null
  numQueries: number | null
  mode: string | null
  createdAt: string | null
}

export function KBValidationPanel({ kbUuid, kbReady, canManage, onCloned }: Props) {
  const [tab, setTab] = useState<Tab>('autovalidate')
  const [queries, setQueries] = useState<KBTestQuery[]>([])
  const [latestRun, setLatestRun] = useState<KBValidationResult | null>(null)
  const [latestQuality, setLatestQuality] = useState<LatestQualitySummary | null>(null)
  const [loading, setLoading] = useState(false)
  // Run state lives here (not in KBValidationRunTab) so an in-flight validation
  // survives tab switches — the Run now tab is conditionally rendered and would
  // otherwise unmount mid-run, dropping its `running`/`error` local state and
  // showing the idle "Run Validation" button as if nothing were happening.
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  // Bumped whenever a run finishes so the History tab refetches even if it's
  // already mounted (it otherwise only loads on mount, so a freshly persisted
  // run wouldn't appear until a full page reload).
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0)
  // Guards against committing poll results after the panel unmounts (KB closed
  // mid-run). The polling loop awaits across many seconds, so it can resolve
  // long after React has torn the component down.
  const mountedRef = useRef(true)
  useEffect(() => () => { mountedRef.current = false }, [])

  // Roving focus for the tab strip (keyboard arrow navigation).
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([])
  const onTabKeyDown = (e: React.KeyboardEvent, idx: number) => {
    if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(e.key)) return
    e.preventDefault()
    const n = TAB_LABELS.length
    const next =
      e.key === 'ArrowRight' ? (idx + 1) % n
      : e.key === 'ArrowLeft' ? (idx - 1 + n) % n
      : e.key === 'Home' ? 0
      : n - 1
    setTab(TAB_LABELS[next].id)
    tabRefs.current[next]?.focus()
  }

  const refreshQueries = useCallback(async () => {
    try {
      const out = await listKBTestQueries(kbUuid)
      setQueries(out.test_queries)
    } catch (e) {
      console.error('listKBTestQueries failed', e)
    }
  }, [kbUuid])

  const fetchHistory = useCallback(async (): Promise<KBHistoryItem[]> => {
    const out = await getKBQuality(kbUuid)
    return (out.history as KBHistoryItem[]) ?? []
  }, [kbUuid])

  const applyLatestQuality = useCallback((history: KBHistoryItem[]) => {
    const last = history[0]
    setLatestQuality(last?.score != null ? {
      score: Number(last.score),
      judgeModel: last.judge_model ?? null,
      numQueries: last.num_queries_judged ?? last.num_test_queries ?? null,
      mode: last.mode ?? null,
      createdAt: last.created_at ?? null,
    } : null)
  }, [])

  const refreshHistory = useCallback(async () => {
    try {
      applyLatestQuality(await fetchHistory())
    } catch (e) {
      console.error('getKBQuality failed', e)
    }
  }, [fetchHistory, applyLatestQuality])

  // Run validation as a background task and poll for the result. The synchronous
  // endpoint can take minutes for a large eval set and would blow past the
  // client's 60s fetch timeout — the request aborted with "Request timed out"
  // even though the server finished and persisted the run (it only surfaced
  // later in History). Instead we enqueue the Celery task and poll the quality
  // history until the new ValidationRun lands, then render its full snapshot.
  const runValidation = useCallback(async (mode: KBValidationMode) => {
    setRunning(true)
    setRunError(null)
    try {
      // Remember the runs that already exist so we can spot the new one.
      let priorUuids = new Set<string>()
      try {
        priorUuids = new Set(
          (await fetchHistory()).map(h => h.uuid).filter((u): u is string => !!u),
        )
      } catch {
        // Non-fatal — worst case we match the first completed run we see.
      }

      await runKBValidationAsync(kbUuid, { mode })

      const deadline = Date.now() + MAX_POLL_MS
      let result: KBValidationResult | null = null
      while (Date.now() < deadline) {
        await sleep(POLL_INTERVAL_MS)
        if (!mountedRef.current) return
        let history: KBHistoryItem[]
        try {
          history = await fetchHistory()
        } catch {
          continue // transient fetch error — keep polling
        }
        // The freshest run we haven't seen before that carries a full validation
        // payload (skips lightweight optimizer-apply / passive rows).
        const fresh = history.find(
          h => h.uuid && !priorUuids.has(h.uuid) && h.result_snapshot?.retrieval_precision,
        )
        if (fresh?.result_snapshot) {
          result = fresh.result_snapshot
          applyLatestQuality(history)
          break
        }
      }
      if (!mountedRef.current) return
      if (result) {
        setLatestRun(result)
        // Surface the new run in History without waiting for a reload.
        setHistoryRefreshKey(k => k + 1)
      } else {
        setRunError(
          'Validation is still running — large evaluation sets can take several ' +
          'minutes. It will appear in the History tab when it finishes.',
        )
      }
    } catch (e) {
      if (mountedRef.current) setRunError((e as Error).message)
    } finally {
      if (mountedRef.current) setRunning(false)
    }
  }, [kbUuid, fetchHistory, applyLatestQuality])

  useEffect(() => {
    setLoading(true)
    Promise.all([refreshQueries(), refreshHistory()]).finally(() => setLoading(false))
  }, [refreshQueries, refreshHistory])

  // Re-pull the test-query list on every entry to the Test Queries tab. The
  // Validate-tab wizard generates and persists queries server-side, so the
  // snapshot held here goes stale; refetching on entry keeps the tab honest
  // without a page reload. Runs in the background — it doesn't clear the
  // existing rows, so there's no spinner flash.
  useEffect(() => {
    if (tab === 'queries') void refreshQueries()
  }, [tab, refreshQueries])

  const latestScore = latestQuality?.score ?? null
  const scoreColor =
    latestScore == null ? '#666'
    : latestScore >= 90 ? '#22c55e'
    : latestScore >= 70 ? '#3b82f6'
    : latestScore >= 50 ? '#f59e0b'
    : '#ef4444'

  // Build the "source of this score" tooltip — answers the audit's #11 directly.
  const tooltip = useMemo(() => {
    if (!latestQuality) return undefined
    const parts: string[] = []
    parts.push(`Score: ${latestQuality.score.toFixed(0)}`)
    if (latestQuality.judgeModel) parts.push(`judged by ${latestQuality.judgeModel}`)
    if (latestQuality.numQueries != null) parts.push(`on ${latestQuality.numQueries} queries`)
    if (latestQuality.mode) parts.push(`(${latestQuality.mode})`)
    if (latestQuality.createdAt) {
      const when = new Date(latestQuality.createdAt)
      parts.push(`at ${when.toLocaleString()}`)
    }
    return parts.join(' · ')
  }, [latestQuality])

  // Inline provenance line shown next to the score chip — keeps the score's
  // meaning visible without forcing a hover.
  const provenance = latestQuality
    ? [
        latestQuality.judgeModel && shortenModel(latestQuality.judgeModel),
        latestQuality.numQueries != null ? `n=${latestQuality.numQueries}` : null,
        latestQuality.createdAt ? relativeTime(latestQuality.createdAt) : null,
      ].filter(Boolean).join(' · ')
    : null

  return (
    <div
      style={{
        marginTop: 16,
        padding: 12,
        backgroundColor: '#1f1f1f',
        border: '1px solid #2e2e2e',
        borderRadius: 8,
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <ShieldCheck size={16} style={{ color: '#7d8590' }} aria-hidden="true" />
        <span style={{ fontSize: 14, fontWeight: 600, color: '#e5e5e5' }}>Validation</span>
        {latestScore != null && (
          <span
            role="status"
            aria-live="polite"
            title={tooltip}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 8,
              color: scoreColor, backgroundColor: 'rgba(255,255,255,0.05)',
              border: `1px solid ${scoreColor}33`,
            }}
          >
            <span style={{
              width: 6, height: 6, borderRadius: '50%', backgroundColor: scoreColor,
            }} />
            {latestScore.toFixed(0)}
          </span>
        )}
        {provenance && (
          <span
            title={tooltip}
            style={{
              fontSize: 10, color: '#666',
              maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}
          >
            {provenance}
          </span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: 11, color: '#888' }}>
          {queries.length} {queries.length === 1 ? 'query' : 'queries'}
        </span>
      </div>

      {/* Orientation hint — single sentence above the tab strip so new users
          know what each tab is for without clicking through. */}
      <div
        style={{
          fontSize: 11, color: '#888', marginBottom: 6, lineHeight: 1.5,
        }}
      >
        <b style={{ color: '#bbb' }}>Validate</b> to score &amp; improve. <b style={{ color: '#bbb' }}>Run now</b> to spot-check.{' '}
        <b style={{ color: '#bbb' }}>Test Queries</b> are the rubric.
      </div>

      {/* Tabs */}
      <div role="tablist" aria-label="Validation views" style={{ display: 'flex', gap: 2, borderBottom: '1px solid #2e2e2e', marginBottom: 10 }}>
        {TAB_LABELS.map((t, idx) => {
          const active = tab === t.id
          const Icon = t.icon
          const isAuto = t.id === 'autovalidate'
          return (
            <button
              key={t.id}
              type="button"
              role="tab"
              id={`vtab-${t.id}`}
              aria-selected={active}
              aria-controls="vtabpanel"
              tabIndex={active ? 0 : -1}
              ref={el => { tabRefs.current[idx] = el }}
              onKeyDown={e => onTabKeyDown(e, idx)}
              onClick={() => setTab(t.id)}
              style={{
                fontFamily: 'inherit',
                display: 'inline-flex', alignItems: 'center', gap: 5,
                background: 'transparent',
                color: active ? '#fff' : '#888',
                border: 'none',
                padding: '6px 12px',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                borderBottom: active
                  ? `2px solid ${isAuto ? '#a78bfa' : '#2563eb'}`
                  : '2px solid transparent',
                marginBottom: -1,
              }}
            >
              {Icon && <Icon size={12} style={{ color: active ? (isAuto ? '#a78bfa' : '#fff') : '#888' }} aria-hidden="true" />}
              {t.label}
            </button>
          )
        })}
      </div>

      {/* Tab content */}
      <div role="tabpanel" id="vtabpanel" aria-labelledby={`vtab-${tab}`}>
      {loading ? (
        <div role="status" aria-live="polite" style={{ textAlign: 'center', padding: 24, color: '#888' }}>
          <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} aria-hidden="true" />
          <span style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clip: 'rect(0 0 0 0)' }}>Loading…</span>
        </div>
      ) : tab === 'autovalidate' ? (
        <AutovalidateTab
          kbUuid={kbUuid}
          kbReady={kbReady}
          canManage={canManage}
          queriesCount={queries.length}
          onSwitchToQueries={() => setTab('queries')}
          onCloned={onCloned}
        />
      ) : tab === 'queries' ? (
        <KBTestQueriesTab
          kbUuid={kbUuid}
          kbReady={kbReady}
          canManage={canManage}
          queries={queries}
          onChange={refreshQueries}
        />
      ) : tab === 'run' ? (
        <KBValidationRunTab
          kbReady={kbReady}
          canManage={canManage}
          numQueries={queries.length}
          latestRun={latestRun}
          running={running}
          error={runError}
          onRun={runValidation}
        />
      ) : (
        <KBQualityHistoryTab
          kbUuid={kbUuid}
          onSwitchToAutovalidate={() => setTab('autovalidate')}
          refreshKey={historyRefreshKey}
          polling={running}
        />
      )}
      </div>
    </div>
  )
}

/** Compact model identifier — drop provider prefix and version dates so the
 * provenance string stays readable in the header. */
function shortenModel(name: string): string {
  const noProvider = name.split('/').pop() ?? name
  const noDate = noProvider.replace(/-\d{4}-\d{2}-\d{2}$/, '')
  return noDate.length > 24 ? noDate.slice(0, 22) + '…' : noDate
}

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const seconds = Math.round((Date.now() - then) / 1000)
  if (seconds < 90) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 90) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 36) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 14) return `${days}d ago`
  const weeks = Math.round(days / 7)
  return `${weeks}w ago`
}
