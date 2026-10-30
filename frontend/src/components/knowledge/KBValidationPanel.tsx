import { QualityBadge } from '../library/QualityBadge'
import { ValidationNav } from '../shared/ValidationNav'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ShieldCheck, Loader2, ChevronDown, ChevronRight } from 'lucide-react'
import {
  listKBTestQueries,
  getKBQuality,
  getKBValidationGrader,
  downloadKBValidationRunExport,
  type KBTestQuery,
  type KBValidationExportFormat,
  type KBValidationGrader,
  type KBValidationResult,
} from '../../api/knowledge'
import { describeKBScoreWithValues, explainKBScore } from './kbScoreFormula'
import { AutovalidateTab } from './AutovalidateTab'
import { KBTestQueriesTab } from './KBTestQueriesTab'
import { KBValidationRunTab } from './KBValidationRunTab'
import { useKBValidationRun } from '../../hooks/useKBValidationRun'
import { KBQualityHistoryTab } from './KBQualityHistoryTab'

type Tab = 'autovalidate' | 'queries' | 'run' | 'history'

interface Props {
  kbUuid: string
  kbReady: boolean
  canManage: boolean
  /** Whether the KB has any sources at all. ``kbReady`` alone can't tell an
   *  empty KB from one still indexing, and only the empty case gets the "add a
   *  source" wording in History. */
  kbHasSources?: boolean
  /** Called with the new KB's uuid after the user clones a KB they can't
   * manage, so the parent can navigate to their own copy. */
  onCloned?: (newUuid: string) => void
  onRunCompleted?: (kbUuid: string) => void
  /** Collapse state is owned by the parent so it can trade screen space
   * between this panel and sibling sections (e.g. the Sources list). The
   * header stays visible when collapsed, keeping the latest score chip in
   * view. Omit both props to render always-expanded. */
  collapsed?: boolean
  onToggleCollapsed?: () => void
}

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
  source?: string | null
  result_snapshot?: KBValidationResult | null
}

/** A run over hand-picked queries ("Run selected") is a smoke test — it
 * must never stand in for the KB's quality score in the header. */
const isSmokeTest = (h: KBHistoryItem) => h.source === 'smoke_test'

/** Provenance summary for the score chip in the validation header. We surface
 * judge model, eval-set size, mode, and age so users can tell whether the
 * "85" they see is fresh, on a comparable judge, and on a comparable set —
 * which addresses the audit's "no labeling, no reconciliation" gap. */
type LatestQualitySummary = {
  tier?: string | null
  limitedEvidence: boolean
  score: number
  // Overall-score composition + the judge's answer accuracy, so the chip's
  // hover can say the score is a composite instead of reading as "judged N".
  breakdown: string | null
  answerAccuracy: number | null
  judgeModel: string | null
  // The tuned answer model could not be used (removed from System Config);
  // the score came from ``used`` and must not be read as the tuned config's.
  answerModelFallback: { configured: string; used: string } | null
  numQueries: number | null
  mode: string | null
  createdAt: string | null
}

export function KBValidationPanel({ kbUuid, kbReady, canManage, kbHasSources = true, onCloned, onRunCompleted, collapsed = false, onToggleCollapsed }: Props) {
  const [tab, setTab] = useState<Tab>('queries')
  const [editingQuestion, setEditingQuestion] = useState(false)
  const [draftNotice, setDraftNotice] = useState(false)
  useEffect(() => { if (!editingQuestion) setDraftNotice(false) }, [editingQuestion])
  const [queries, setQueries] = useState<KBTestQuery[]>([])
  const [latestRun, setLatestRun] = useState<KBValidationResult | null>(null)
  // Persisted uuid of the run shown in the Run-now tab, so its results can be
  // exported. null until a run lands (or is hydrated from history).
  const [latestRunUuid, setLatestRunUuid] = useState<string | null>(null)
  const [displayedRunDate, setDisplayedRunDate] = useState<string | null>(null)
  const [latestQuality, setLatestQuality] = useState<LatestQualitySummary | null>(null)
  const [loading, setLoading] = useState(false)
  // Run state lives here (not in KBValidationRunTab) so an in-flight validation
  // survives tab switches — the Run now tab is conditionally rendered and would
  // otherwise unmount mid-run, dropping its `running`/`error` local state and
  // showing the idle "Run Validation" button as if nothing were happening.
  const [runError, setRunError] = useState<string | null>(null)
  // Questions ticked on Test Queries and handed to Run now by "Run selected",
  // where the count and category mix are shown before the run starts.
  const [handedSelection, setHandedSelection] = useState<string[] | null>(null)
  // A "Run selected" hand-off applies to the visit it opened; choosing a tab
  // from the strip starts clean, so a later Run visit opens on the full set.
  const selectTab = (id: Tab) => {
    if (id !== 'queries' && editingQuestion) { setDraftNotice(true); return }
    setHandedSelection(null)
    setTab(id)
  }
  // The system-wide grader, named on the Run tab before a run starts.
  const [grader, setGrader] = useState<KBValidationGrader | null>(null)
  // Bumped whenever a run finishes so the History tab refetches even if it's
  // already mounted (it otherwise only loads on mount, so a freshly persisted
  // run wouldn't appear until a full page reload).
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0)
  // Guards against committing poll results after the panel unmounts (KB closed
  // mid-run). The polling loop awaits across many seconds, so it can resolve
  // long after React has torn the component down.
  const mountedRef = useRef(true)
  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

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
    const last = history.find(h => !isSmokeTest(h))
    const snap = last?.result_snapshot ?? null
    setLatestQuality(last?.score != null ? {
      score: Number(last.score),
      tier: snap?.quality_tier,
      limitedEvidence: !!snap?.score_breakdown?.sample_size_penalty,
      breakdown: snap ? describeKBScoreWithValues(explainKBScore(snap).components) : null,
      answerAccuracy: snap?.retrieval_precision?.avg_judge_score ?? null,
      judgeModel: last.judge_model ?? null,
      answerModelFallback: snap?.answer_model_fallback ?? null,
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

  const { start: runValidation, retry: retryValidation, running, progress, activeOptions } = useKBValidationRun(kbUuid, (uuid, result) => {
    setLatestRun(result)
    setLatestRunUuid(uuid)
    setDisplayedRunDate(null)
    setRunError(null)
    setHistoryRefreshKey(k => k + 1)
    void refreshHistory()
    onRunCompleted?.(kbUuid)
  })

  // Export the run currently shown in the Run-now tab. Failures surface in
  // the tab's existing error slot rather than dying silently.
  const exportLatestRun = useCallback(async (format: KBValidationExportFormat) => {
    if (!latestRunUuid) return
    try {
      await downloadKBValidationRunExport(kbUuid, latestRunUuid, format)
    } catch (e) {
      if (mountedRef.current) setRunError(`Export failed: ${(e as Error).message}`)
    }
  }, [kbUuid, latestRunUuid])

  useEffect(() => {
    setLoading(true)
    Promise.all([refreshQueries(), refreshHistory()]).finally(() => setLoading(false))
  }, [refreshQueries, refreshHistory])

  // Re-read on entry to the Run tab: an admin can change the grader at any time.
  useEffect(() => {
    if (tab !== 'run') return
    let cancelled = false
    getKBValidationGrader(kbUuid)
      .then(g => { if (!cancelled) setGrader(g) })
      .catch(() => { /* optional context; the run works without it */ })
    return () => { cancelled = true }
  }, [tab, kbUuid])

  // Re-pull the test-query list on every entry to the Test Queries tab. The
  // Validate-tab wizard generates and persists queries server-side, so the
  // snapshot held here goes stale; refetching on entry keeps the tab honest
  // without a page reload. Runs in the background — it doesn't clear the
  // existing rows, so there's no spinner flash.
  useEffect(() => {
    if (tab === 'queries') void refreshQueries()
  }, [tab, refreshQueries])

  const latestScore = latestQuality?.score ?? null
  // Build the "source of this score" tooltip — answers the audit's #11 directly.
  // Leads with what the number IS (a composite) before who judged it, because
  // "Score: 91 · judged by X" read as the judge's score, which it is not.
  const tooltip = useMemo(() => {
    if (!latestQuality) return undefined
    const parts: string[] = []
    parts.push(`Overall quality ${latestQuality.score.toFixed(0)}`)
    if (latestQuality.breakdown) parts.push(`= ${latestQuality.breakdown}`)
    if (latestQuality.answerAccuracy != null) {
      parts.push(`answer accuracy ${(latestQuality.answerAccuracy * 100).toFixed(0)}%`)
    }
    if (latestQuality.judgeModel) parts.push(`judged by ${latestQuality.judgeModel}`)
    if (latestQuality.answerModelFallback) {
      parts.push(
        `answered by ${latestQuality.answerModelFallback.used}, not the tuned `
        + `${latestQuality.answerModelFallback.configured} (no longer in System Config)`,
      )
    }
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
    <div className="validation-workspace"
      style={{
        marginTop: 'var(--workspace-space-12)',
        padding: 'var(--workspace-space-12)',
        backgroundColor: 'var(--workspace-surface)',
        border: '1px solid var(--workspace-border)',
        borderRadius: 'var(--workspace-radius-medium)',
      }}
    >
      {/* Keep the collapse control separate from the evaluation disclosure. */}
      <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 'var(--workspace-space-12)', marginBottom: collapsed ? 0 : 10 }}>
        <button
          type="button"
          onClick={onToggleCollapsed}
          aria-expanded={onToggleCollapsed ? !collapsed : undefined}
          disabled={!onToggleCollapsed}
          style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-12)', padding: 0,
            background: 'transparent', border: 'none', fontFamily: 'inherit',
            cursor: onToggleCollapsed ? 'pointer' : 'default', textAlign: 'left' }}
        >
          {onToggleCollapsed && (
            collapsed
              ? <ChevronRight size={14} style={{ color: 'var(--workspace-muted)', flexShrink: 0 }} />
              : <ChevronDown size={14} style={{ color: 'var(--workspace-muted)', flexShrink: 0 }} />
          )}
          <ShieldCheck size={16} style={{ color: 'var(--workspace-muted)' }} aria-hidden="true" />
          <span style={{ fontSize: 'var(--workspace-font-body)', fontWeight: 600, color: 'var(--workspace-text)' }}>Validation</span>
        </button>
        <QualityBadge tier={latestQuality?.tier} score={latestScore}
          testCaseCount={latestQuality?.numQueries} lastValidatedAt={latestQuality?.createdAt}
          limitedEvidence={latestQuality?.limitedEvidence} title={tooltip} />
        {provenance && (
          <span
            title={tooltip}
            style={{
              fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)',
              maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}
          >
            {provenance}
          </span>
        )}
        {latestQuality?.answerModelFallback && (
          <span
            title={`The applied optimization pins ${latestQuality.answerModelFallback.configured}, which is no longer in System Config. This score was answered by ${latestQuality.answerModelFallback.used}. Re-run Autovalidate or revert the optimization to clear this.`}
            style={{
              fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-warning)',
              maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}
          >
            tuned model unavailable · answered by {shortenModel(latestQuality.answerModelFallback.used)}
          </span>
        )}
        {collapsed && running && (
          <Loader2 size={12} style={{ color: 'var(--workspace-muted)', animation: 'spin 1s linear infinite' }} aria-label="Validation running" />
        )}
        <span style={{ marginLeft: 'auto', fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-muted)' }}>
          {queries.length} {queries.length === 1 ? 'query' : 'queries'}
        </span>
      </div>

      {!collapsed && (<>
      <ValidationNav active={tab === 'queries' ? 'examples' : tab === 'autovalidate' ? 'improve' : 'check'}
        onChange={stage => selectTab(stage === 'examples' ? 'queries' : stage === 'improve' ? 'autovalidate' : 'run')}
        running={running} summary={tab === 'queries' ? `${queries.length} test questions. Save expected answers to measure quality.`
          : tab === 'autovalidate' ? 'Compare retrieval and answer settings, then review proposed changes.'
          : 'Check answers against your examples. Review failures and their source evidence.'} />
      {(tab === 'run' || tab === 'history') && <button type="button" onClick={() => selectTab(tab === 'history' ? 'run' : 'history')}
        style={{ marginBottom: 12, padding: '8px 12px', background: '#fff', border: '1px solid var(--workspace-border)', borderRadius: 6, cursor: 'pointer' }}>
        {tab === 'history' ? 'Back to latest result' : 'View run history'}
      </button>}
      {tab !== 'run' && progress && (
        <div role={progress.phase === 'failed' ? 'alert' : 'status'} style={{ padding: "var(--workspace-space-12) 0", fontSize: 'var(--workspace-font-control)', color: progress.phase === 'failed' ? 'var(--workspace-danger)' : 'var(--workspace-muted)', lineHeight: 1.6 }}>
          <div>{progress.message}</div>
          {progress.delayed && <div>This check is taking longer than usual; it remains active.</div>}
          {running && <button type="button" onClick={retryValidation} style={{ display: 'block', marginTop: 'var(--workspace-space-8)', padding: "7px var(--workspace-space-12)", color: 'var(--workspace-text)', background: 'var(--workspace-surface)', border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-small)', cursor: 'pointer' }}>Check status / reconnect</button>}
        </div>
      )}
      {draftNotice && <p role="alert" className="validation-save-error">Save or cancel your question edits before leaving Examples. Your draft is still here.</p>}
      {/* Tab content */}
      <div role="region" aria-label={tab === 'queries' ? 'Knowledge base examples' : tab === 'run' ? 'Knowledge base run and results' : tab === 'history' ? 'Validation history' : 'Improve knowledge base'}>
      {loading ? (
        <div role="status" aria-live="polite" style={{ textAlign: 'center', padding: 'var(--workspace-space-24)', color: 'var(--workspace-muted)' }}>
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
          onChanged={() => { void refreshHistory(); onRunCompleted?.(kbUuid); setHistoryRefreshKey(key => key + 1) }}
        />
      ) : tab === 'queries' ? (
        <KBTestQueriesTab
          kbUuid={kbUuid}
          kbReady={kbReady}
          canManage={canManage}
          queries={queries}
          onChange={refreshQueries}
          onEditingChange={setEditingQuestion}
          running={running}
          onRunSelected={uuids => {
            if (editingQuestion) { setDraftNotice(true); return }
            // Review before running: Run now opens on this selection (judge
            // only, so it costs what the handful of questions costs) and
            // states the count and categories; the user starts it there.
            setHandedSelection(uuids)
            setTab('run')
          }}
        />
      ) : tab === 'run' ? (
        <KBValidationRunTab
          kbReady={kbReady}
          canManage={canManage}
          queries={queries}
          selectedUuids={handedSelection}
          latestRun={latestRun}
          displayedRunLabel={latestRunUuid ? `Saved run ${displayedRunDate ? new Date(displayedRunDate).toLocaleString() + ' · ' : ''}${latestRunUuid}` : undefined}
          running={running}
          progress={progress}
          activeOptions={activeOptions}
          onRetryStatus={retryValidation}
          error={runError}
          onRun={(mode, queryUuids) => { setRunError(null); runValidation(mode, queryUuids) }}
          onExport={latestRunUuid ? exportLatestRun : undefined}
          onChooseQuestions={() => setTab('queries')}
          grader={grader}
        />
      ) : (
        <KBQualityHistoryTab
          kbUuid={kbUuid}
          onSwitchToAutovalidate={() => setTab('autovalidate')}
          refreshKey={historyRefreshKey}
          polling={running}
          kbHasSources={kbHasSources}
          onOpenRun={(uuid, result, createdAt) => {
            setLatestRun(result)
            setLatestRunUuid(uuid)
            setDisplayedRunDate(createdAt ?? null)
            setHandedSelection(null)
            setTab('run')

          }}
        />
      )}
      </div>
      </>)}
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
