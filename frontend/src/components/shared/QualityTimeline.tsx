import { useEffect, useRef, useState } from 'react'
import { Download, Loader2, Sparkles } from 'lucide-react'

// While a run is in flight, re-pull history on this cadence so a freshly
// persisted ValidationRun appears without a manual reload.
const POLL_INTERVAL_MS = 4000

/**
 * Generic quality-over-time component used by KB, Extraction, and Workflow
 * surfaces. Each surface supplies a ``fetchHistory`` adapter that returns
 * the normalized ``QualityHistoryItem`` shape — the same shape that
 * ``quality_service.get_quality_history`` already returns for every
 * ``item_kind``.
 *
 * Phase 4 of the loop-closure plan: one timeline, three surfaces. Replaces
 * the per-surface bespoke history tabs so the rendering, judge-model-change
 * warning, CI ribbon, and tooltips don't drift over time.
 */

export interface QualityHistoryItem {
  uuid?: string
  result_snapshot?: unknown
  score?: number
  grade?: string | null
  created_at?: string
  num_test_queries?: number
  num_queries_judged?: number
  num_test_cases?: number
  num_checks?: number
  mode?: string
  /** The model that executed the run (task model) — distinct from the judge. */
  model?: string | null
  judge_model?: string | null
  judge_variance?: number | null
  judge_variance_meta?: { sigma: number | null; n: number; sampled_query_uuids?: string[] } | null
  /** Optional source tag — when set to ``"optimizer_apply"`` (Phase 4) the
   *  row renders with a sparkles glyph so users can see that this point
   *  came from an Apply, not a regular validation run. ``"smoke_test"``
   *  marks a run over hand-picked queries: listed and exportable, but not
   *  the item's quality score. */
  source?: string | null
  /** On a smoke-test run: how many queries were chosen out of the set.
   *  ``requested`` (newer runs) is what the caller asked for; the route now
   *  refuses a selection that doesn't fully match, so it equals ``selected``. */
  query_selection?: { selected: number; requested?: number; total: number } | null
  /** KB runs: the question set measured. Absent on older runs and on other
   *  item kinds, which then show no set marker. */
  question_set?: { fingerprint: string; count?: number | null; category_counts?: Record<string, number> } | null
}

/** For each row, whether it measured a different question set than the
 *  nearest older run of the same kind (full vs. subset) that recorded one.
 *  Comparing a full run with a smoke test would flag every full run after a
 *  spot-check, so the two tracks are compared separately. ``items`` is newest
 *  first, as history returns it. */
export function questionSetChanges(items: QualityHistoryItem[]): boolean[] {
  return items.map((it, i) => {
    const fp = it.question_set?.fingerprint
    if (!fp) return false
    const smoke = it.source === SMOKE_TEST_SOURCE
    const prev = items.slice(i + 1).find(
      o => o.question_set?.fingerprint && (o.source === SMOKE_TEST_SOURCE) === smoke,
    )
    return !!prev && prev.question_set!.fingerprint !== fp
  })
}

/** Source tag for a "Run selected" smoke test — a run over hand-picked
 *  queries that is listed and exportable but never the quality score. */
const SMOKE_TEST_SOURCE = 'smoke_test'
/** How faded a smoke-test bar draws: visible, but not mistakable for a run
 *  that counted. */
const SMOKE_TEST_BAR_OPACITY = 0.35

interface Props {
  fetchHistory: () => Promise<{ history: QualityHistoryItem[] }>
  /** Singular noun for what was scored — "KB", "extraction", "workflow". */
  itemKindLabel: string
  /** Plural form used in the empty-state and ITEM_NOUNS labels. */
  itemKindPluralLabel: string
  onSwitchToAutovalidate?: () => void
  /** When provided, used to count sample-size in the row label
   *  (queries / cases / checks). Defaults to "items". */
  sampleNoun?: string
  /** Bump to force an immediate refetch — e.g. a validation run just finished
   *  and its row should appear without a page reload. */
  refreshKey?: number
  /** When true, a run is in flight: poll history on an interval so the new run
   *  lands here even while the user sits on this tab. */
  polling?: boolean
  /** When provided, full-run rows get a download menu (CSV / Excel / JSON)
   *  that exports the run's per-query results. Optimizer-apply rows carry no
   *  per-query results, so they never show the menu. */
  onExportRun?: (runUuid: string, format: QualityRunExportFormat) => void | Promise<void>
  onOpenRun?: (item: QualityHistoryItem) => void
  canOpenRun?: (item: QualityHistoryItem) => boolean
  /** Why this item can't be validated yet (e.g. a KB with no sources). When
   *  set and there is no history, the empty state states that plainly rather
   *  than pitching a Validate & improve run the item can't do. */
  blockedReason?: string | null
}

export type QualityRunExportFormat = 'csv' | 'xlsx' | 'json'

export function QualityTimeline({
  fetchHistory, itemKindLabel, itemKindPluralLabel, onSwitchToAutovalidate, sampleNoun = 'items',
  refreshKey, polling = false, onExportRun, onOpenRun, canOpenRun, blockedReason,
}: Props) {
  const [items, setItems] = useState<QualityHistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [retryKey, setRetryKey] = useState(0)
  // Only the first fetch drives the spinner; background refreshes (poll ticks,
  // refreshKey bumps) swap rows in place rather than flashing the loader.
  const firstLoadRef = useRef(true)

  useEffect(() => {
    let cancelled = false
    let pending = false
    const load = () => {
      if (pending) return
      pending = true
      fetchHistory()
        .then(out => { if (!cancelled) { setItems((out.history || []).slice(0, 30)); setError(false) } })
        .catch(() => { if (!cancelled) setError(true) })
        .finally(() => {
          pending = false
          if (!cancelled && firstLoadRef.current) {
            firstLoadRef.current = false
            setLoading(false)
          }
        })
    }
    load()
    const timer = polling ? setInterval(load, POLL_INTERVAL_MS) : undefined
    return () => { cancelled = true; if (timer) clearInterval(timer) }
  }, [fetchHistory, refreshKey, polling, retryKey])

  if (loading) {
    return (
      <div role="status" aria-live="polite" style={{ textAlign: 'center', padding: 'var(--workspace-space-24)', color: 'var(--workspace-muted)' }}>
        <Loader2 size={18} aria-hidden="true" style={{ animation: 'spin 1s linear infinite' }} />
        <span style={{
          position: 'absolute', width: 1, height: 1, padding: 0, margin: -1,
          overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap', border: 0,
        }}>
          Loading quality history…
        </span>
      </div>
    )
  }

  const recovery = error && (
    <div role="alert" style={{ padding: 'var(--workspace-space-12)', marginBottom: 'var(--workspace-space-12)', border: '1px solid #835b32', borderRadius: 'var(--workspace-radius-small)', color: 'var(--workspace-warning)', fontSize: 'var(--workspace-font-control)' }}>
      <p style={{ margin: "0 0 var(--workspace-space-8)" }}>{items.length ? 'History could not refresh. Previously loaded runs are still shown.' : 'History could not load. Your saved runs have not been changed.'}</p>
      <button type="button" onClick={() => setRetryKey(k => k + 1)} style={actionStyle}>Retry history</button>
    </div>
  )
  if (error && items.length === 0) return recovery

  if (items.length === 0 && blockedReason) {
    // Nothing to show and nothing the user could run from here: state the
    // absence, in the register of the "No prior optimization runs" note, and
    // leave the pitch to the Validate tab.
    return (
      <div role="status" aria-live="polite" style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', padding: "var(--workspace-space-12) var(--workspace-space-8)", lineHeight: 1.6 }}>
        No validation runs yet for this {itemKindLabel}. {blockedReason}
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div role="status" aria-live="polite" style={{
        padding: 'var(--workspace-space-20)', margin: "var(--workspace-space-12) 0",
        background: 'var(--workspace-canvas)',
        border: '1px solid rgba(124, 58, 237, 0.25)', borderRadius: 'var(--workspace-radius-medium)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--workspace-space-8)', marginBottom: 'var(--workspace-space-8)' }}>
          <Sparkles size={16} style={{ color: 'var(--workspace-info)' }} />
          <h3 style={{ margin: 0, fontSize: 'var(--workspace-font-body)', color: 'var(--workspace-text)', fontWeight: 600 }}>
            No quality history yet for this {itemKindLabel}
          </h3>
        </div>
        <p style={{ margin: "0 0 var(--workspace-space-16) 0", fontSize: 'var(--workspace-font-control)', color: 'var(--workspace-muted)', lineHeight: 1.55 }}>
          Each Validate &amp; improve run records a quality score here so you can
          watch {itemKindPluralLabel} improve over time. Nothing is mutated until
          you choose to apply a winning configuration.
        </p>
        {onSwitchToAutovalidate && (
          <button
            type="button"
            onClick={onSwitchToAutovalidate}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 'var(--workspace-space-6)',
              padding: "var(--workspace-space-8) var(--workspace-space-16)", fontSize: 'var(--workspace-font-meta)', fontWeight: 600, fontFamily: 'inherit',
              color: 'var(--highlight-text-color, #000)',
              background: 'var(--highlight-color, #eab308)',
              border: '1px solid var(--workspace-accent-ink)', borderRadius: 'var(--workspace-radius-small)', cursor: 'pointer',
            }}
          >
            <Sparkles size={12} />
            Validate &amp; improve
          </button>
        )}
      </div>
    )
  }

  const ordered = [...items].reverse()
  const setChanges = questionSetChanges(items)
  // Smoke tests don't set the axis: a 2-of-150 run at 100% must not stretch
  // the scale the full runs are read against. (They still draw, faded and
  // outlined, at their position on the full-run scale.)
  const scoreValues = ordered
    .filter(i => i.source !== SMOKE_TEST_SOURCE)
    .map(i => i.score ?? 0)
  const max = Math.max(...scoreValues, 100)
  const min = Math.min(...scoreValues, 0)

  const judgeModels = new Set(ordered.map(i => i.judge_model || '').filter(Boolean))
  const judgeModelChanged = judgeModels.size > 1

  // Same trap as a judge swap, on the other side of the measurement: a score
  // dip caused by switching the model under test must not read as a content
  // regression. Runs without attribution (legacy, mixed-model workflows)
  // don't count toward "changed" — absence is a coverage gap, not a change.
  const taskModels = new Set(ordered.map(i => i.model || '').filter(Boolean))
  const taskModelChanged = taskModels.size > 1

  return (
    <div>
      {recovery}
      <p style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', lineHeight: 1.6 }}>Compare runs with the same test set, scoring mode, and grader. Selected-question checks do not update the quality score.</p>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', gap: 'var(--workspace-space-8)', marginBottom: 'var(--workspace-space-8)' }}>
        <div style={{ fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)' }}>
          Last {ordered.length} runs
        </div>
        {judgeModelChanged && (
          <span
            title={`Judge model changed across this window: ${[...judgeModels].join(', ')}`}
            style={{
              fontSize: 'var(--workspace-font-meta)', fontWeight: 600,
              padding: "1px var(--workspace-space-6)", borderRadius: 'var(--workspace-radius-small)',
              color: 'var(--workspace-warning)', backgroundColor: 'rgba(245, 158, 11, 0.1)',
              border: '1px solid rgba(245, 158, 11, 0.3)',
            }}
          >
            judge model changed
          </span>
        )}
        {taskModelChanged && (
          <span
            title={`Model under test changed across this window: ${[...taskModels].join(', ')} — score changes may reflect the model swap, not the content`}
            style={{
              fontSize: 'var(--workspace-font-meta)', fontWeight: 600,
              padding: "1px var(--workspace-space-6)", borderRadius: 'var(--workspace-radius-small)',
              color: 'var(--workspace-warning)', backgroundColor: 'rgba(245, 158, 11, 0.1)',
              border: '1px solid rgba(245, 158, 11, 0.3)',
            }}
          >
            model changed
          </span>
        )}
      </div>
      <div style={{
        display: 'flex', alignItems: 'flex-end', gap: 'var(--workspace-space-2)',
        height: 80, padding: 'var(--workspace-space-8)', backgroundColor: 'var(--workspace-canvas)',
        border: '1px solid var(--workspace-border)', borderRadius: 'var(--workspace-radius-small)', marginBottom: 'var(--workspace-space-12)',
        position: 'relative',
      }}>
        {ordered.map((it, i) => {
          const score = it.score ?? 0
          const heightPct = max === min ? 50 : ((score - min) / (max - min)) * 100
          const c = it.score == null ? 'var(--workspace-muted)' : scoreColor(score)
          const sigmaPts = (it.judge_variance ?? 0) * 100
          const ciHalfPct = max === min ? 0 : ((sigmaPts * 1.96) / (max - min)) * 100
          const titleBits: string[] = []
          titleBits.push(it.score == null ? 'Score unavailable' : `${score.toFixed(0)}%`)
          if (it.created_at) titleBits.push(new Date(it.created_at).toLocaleString())
          if (it.judge_model) titleBits.push(`judge: ${it.judge_model}`)
          const nq = it.num_queries_judged ?? it.num_test_queries ?? it.num_test_cases ?? it.num_checks
          if (nq != null) titleBits.push(`n=${nq} ${sampleNoun}`)
          if (it.mode) titleBits.push(`mode: ${it.mode}`)
          if (it.source === 'optimizer_apply') titleBits.push('source: optimizer apply')
          if (it.source === 'passive_monthly') titleBits.push('source: monthly auto-re-judge')
          const isSmoke = it.source === SMOKE_TEST_SOURCE
          if (isSmoke) {
            const sel = it.query_selection
            titleBits.push(
              `smoke test${sel ? ` (${sel.selected} of ${sel.total} ${sampleNoun})` : ''}, not counted toward the quality score`,
            )
            if (sel) titleBits.push(`selected ${sel.selected}/${sel.total}`)
          }
          if (sigmaPts > 0) {
            const meta = it.judge_variance_meta
            const provenance = meta?.n ? ` (σ from n=${meta.n})` : ''
            titleBits.push(`±${(sigmaPts * 1.96).toFixed(1)}pts 95% CI${provenance}`)
          }
          const isApply = it.source === 'optimizer_apply'
          const title = titleBits.join(' · ')
          return (
            <div
              key={it.uuid || i}
              role="img"
              title={title}
              aria-label={title}
              data-source={it.source || undefined}
              style={{
                flex: 1, minWidth: 0, position: 'relative',
                height: `${Math.max(4, heightPct)}%`,
                display: 'flex', flexDirection: 'column-reverse',
                // A smoke-test bar is faded with a dashed outline so a
                // 2-of-150 run at 100% reads as a smoke test, not as a jump
                // in the score. The outline sits on the wrapper so it stays
                // crisp while the fill below is dimmed.
                outline: isSmoke ? '1px dashed #fbbf24' : undefined,
                outlineOffset: isSmoke ? -1 : undefined,
                borderRadius: 2,
              }}
            >
              <div style={{
                width: '100%', height: '100%',
                backgroundColor: c, borderRadius: 2,
                opacity: isSmoke ? SMOKE_TEST_BAR_OPACITY : undefined,
                outline: isApply ? '1px solid #a78bfa' : undefined,
              }} />
              {ciHalfPct > 0 && (
                <div
                  style={{
                    position: 'absolute',
                    left: 0, right: 0, bottom: '100%',
                    height: `${Math.min(ciHalfPct, 200)}%`,
                    backgroundColor: c, opacity: 0.18, borderRadius: '2px 2px 0 0',
                    pointerEvents: 'none',
                  }}
                />
              )}
            </div>
          )
        })}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--workspace-space-4)' }}>
        {items.map((it, i) => (
          <Row
            key={it.uuid || i}
            item={it}
            setChanged={setChanges[i]}
            sampleNoun={sampleNoun}
            onExportRun={onExportRun}
            onOpenRun={canOpenRun?.(it) ? onOpenRun : undefined}
          />
        ))}
      </div>
    </div>
  )
}

const actionStyle = {
  fontFamily: 'inherit', fontSize: 'var(--workspace-font-meta)', fontWeight: 600, padding: "7px var(--workspace-space-12)",
  borderRadius: 'var(--workspace-radius-small)', color: '#d5eaff', background: '#253447', border: '1px solid #52657e', cursor: 'pointer',
} as const

function Row({ item, setChanged = false, sampleNoun, onExportRun, onOpenRun }: {
  item: QualityHistoryItem
  setChanged?: boolean
  sampleNoun: string
  onExportRun?: (runUuid: string, format: QualityRunExportFormat) => void | Promise<void>
  onOpenRun?: (item: QualityHistoryItem) => void
}) {
  const sigmaPts = (item.judge_variance ?? 0) * 100
  const nq = item.num_queries_judged ?? item.num_test_queries ?? item.num_test_cases ?? item.num_checks
  const isApply = item.source === 'optimizer_apply'
  const isSmoke = item.source === SMOKE_TEST_SOURCE
  const source = isApply ? 'Optimizer configuration applied' : isSmoke ? 'Selected-question check' : item.source === 'passive_monthly' ? 'Monthly automatic check' : item.source || 'Source not recorded'
  const date = item.created_at ? new Date(item.created_at).toLocaleString() : 'Date not recorded'
  return (
    <article aria-label={`Validation run ${date}${item.uuid ? ` · ${item.uuid}` : ''}`} style={{
      padding: 'var(--workspace-space-12)', fontSize: 'var(--workspace-font-meta)', color: 'var(--workspace-muted)', backgroundColor: 'var(--workspace-surface)', border: '1px solid #393939', borderRadius: 'var(--workspace-radius-small)', overflowWrap: 'anywhere',
    }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 'var(--workspace-space-8)', justifyContent: 'space-between' }}>
        <strong style={{ color: 'var(--workspace-text)' }}>{date}</strong>
        <strong style={{ color: 'var(--workspace-text)' }}>{item.score == null ? 'Score unavailable' : `${item.score.toFixed(0)}%`}</strong>
      </div>
      <div style={{ marginTop: 'var(--workspace-space-6)', lineHeight: 1.7 }}>
        <div>{source}{isSmoke && <> · {item.query_selection ? `${item.query_selection.selected} of ${item.query_selection.total} ${sampleNoun} · ` : ''}Does not update quality score</>}</div>
        <div>{nq == null ? 'Sample size not recorded' : `${nq} ${sampleNoun}`} · Mode: {item.mode || 'not recorded'}</div>
        <div>Grader: {item.judge_model || 'not recorded'}{item.model && <> · Answer model: {item.model}</>}</div>
        {item.question_set ? <div>Question set: <code>{item.question_set.fingerprint}</code>
          {item.question_set.category_counts && <div>{Object.entries(item.question_set.category_counts).map(([c, n]) => `${c}: ${n}`).join(' · ')}</div>}
        </div> : (sampleNoun === 'queries' || sampleNoun === 'questions') && <div>Question set not recorded; question-level comparison is unavailable.</div>}
        {setChanged && <div style={{ color: 'var(--workspace-warning)' }}>Different {sampleNoun} from the previous {isSmoke ? 'selected-question' : 'full'} run. These scores are not directly comparable.</div>}
        {sigmaPts > 0 && <div>95% noise-floor band: ±{(sigmaPts * 1.96).toFixed(1)} points{item.judge_variance_meta?.n ? ` (estimated from ${item.judge_variance_meta.n} samples)` : ''}</div>}
        {item.uuid && <div style={{ color: 'var(--workspace-muted)' }}>Run: <code>{item.uuid}</code></div>}
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--workspace-space-8)', alignItems: 'center', marginTop: 'var(--workspace-space-8)' }}>
        {onOpenRun && <button type="button" style={actionStyle} onClick={() => onOpenRun(item)}>Open results</button>}
        {onExportRun && item.uuid && !isApply && <RowExportMenu onExport={format => onExportRun(item.uuid!, format)} />}
      </div>
    </article>
  )
}

/** Compact per-row export control: a download icon that expands into the
 * three format choices inline (no floating popover to position/clip). */
function RowExportMenu({ onExport }: { onExport: (format: QualityRunExportFormat) => void | Promise<void> }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)
  const busyRef = useRef(false)

  const run = async (format: QualityRunExportFormat) => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setError(false)
    try {
      await onExport(format)
      setOpen(false)
    } catch {
      setError(true)
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  const fmtButton = (format: QualityRunExportFormat, label: string) => (
    <button
      key={format}
      type="button"
      disabled={busy}
      onClick={() => void run(format)}
      style={{
        fontFamily: 'inherit', fontSize: 'var(--workspace-font-meta)', fontWeight: 600,
        padding: "7px var(--workspace-space-12)", borderRadius: 'var(--workspace-radius-small)',
        color: busy ? 'var(--workspace-muted)' : 'var(--workspace-info)', background: 'transparent',
        border: '1px solid #2e3a52', cursor: busy ? 'wait' : 'pointer',
      }}
    >
      {label}
    </button>
  )

  return (
    <span style={{ display: 'inline-flex', flexWrap: 'wrap', alignItems: 'center', gap: 'var(--workspace-space-6)', maxWidth: '100%' }}>
      {error && <span role="alert" style={{ color: 'var(--workspace-danger)', flexBasis: '100%' }}>Export failed. Choose a format to retry.</span>}
      {busy && <span role="status">Preparing download…</span>}
      {open && (
        busy
          ? <Loader2 size={11} style={{ color: 'var(--workspace-muted)', animation: 'spin 1s linear infinite' }} aria-hidden="true" />
          : <>
              {fmtButton('csv', 'CSV')}
              {fmtButton('xlsx', 'Excel')}
              {fmtButton('json', 'JSON')}
            </>
      )}
      <button
        type="button"
        disabled={busy}
        aria-expanded={open}
        aria-label="Export run results"
        title="Export this run's per-query results"
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'inline-flex', alignItems: 'center',
          gap: 'var(--workspace-space-6)', padding: "7px var(--workspace-space-12)", fontSize: 'var(--workspace-font-meta)', background: 'transparent', border: 'none',
          color: open ? 'var(--workspace-info)' : 'var(--workspace-muted)', cursor: 'pointer',
        }}
      >
        <Download size={12} aria-hidden="true" /> Export
      </button>
    </span>
  )
}

function scoreColor(s: number) {
  if (s >= 90) return 'var(--workspace-success)'
  if (s >= 70) return '#3b82f6'
  if (s >= 50) return 'var(--workspace-warning)'
  return 'var(--workspace-danger)'
}
