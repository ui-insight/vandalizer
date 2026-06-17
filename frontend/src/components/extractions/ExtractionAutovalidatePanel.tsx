/**
 * "Tune this extraction" panel — drives the extraction tuning loop end-to-end
 * inside the Validate tab.
 *
 * Three states, mirroring KB Autovalidate:
 *
 *   A (idle)      Hero card; "Start tuning" button opens the 4-step wizard.
 *                 Past runs are surfaced underneath so users can revisit them
 *                 even before a new run is kicked off.
 *   B (running)   Live progress via shared OptimizationProgressCard + cancel.
 *   C (completed) Shared trust primitives — QualityComparisonCard, best-config
 *                 grid, suggestions, trials table, reproducibility, history.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { RotateCcw, Sparkles } from 'lucide-react'
import {
  getActiveExtractionOptimization,
  getExtractionOptimization,
  listExtractionOptimizationHistory,
  cancelExtractionOptimization,
  applyExtractionOptimization,
  revertExtractionConfig,
  listTestCases,
  type ExtractionOptimizationRun,
  type ExtractionTrial,
} from '../../api/extractions'
import { OptimizationProgressCard, type ProgressRunShape } from '../shared/OptimizationProgressCard'
import { QualityComparisonCard, type BaselinePoint } from '../shared/QualityComparisonCard'
import { ApplyBackButton } from '../shared/ApplyBackButton'
import { ApplyPreviewModal } from '../shared/ApplyPreviewModal'
import { FailedBanner, CancelledBanner, ErrorBanner, PastRunBanner } from '../shared/RunBanners'
import { SuggestionsList, type Suggestion, type SuggestionSeverity } from '../shared/SuggestionsList'
import { TrialsTable, makeStandardSortOptions, scoreColor } from '../shared/TrialsTable'
import { ReproducibilityPanel } from '../shared/ReproducibilityPanel'
import { useIntervalPoll } from '../shared/hooks/useIntervalPoll'
import { WhenToRunDisclosure } from '../shared/WhenToRunDisclosure'
import { useToast } from '../../contexts/ToastContext'
import { ExtractionAutovalidateWizard } from './ExtractionAutovalidateWizard'
import { ExtractionOptimizationHistoryPanel } from './ExtractionOptimizationHistoryPanel'
import { ExtractionTrialExplainerModal } from './ExtractionTrialExplainerModal'
import { summariseExtractionTrialConfig } from './extractionTrialExplanations'
import { TermDef } from '../shared/TermDef'
import { DOMAIN_LABELS } from '../shared/labels'

const POLL_INTERVAL_MS = 3000

interface Props {
  searchSetUuid: string
  /** Whether the current user can manage this SearchSet (gates Start/Apply). */
  canManage: boolean
  /** Called after a successful Apply so the parent can refresh its config view. */
  onApplied?: () => void
}

export function ExtractionAutovalidatePanel({ searchSetUuid, canManage, onApplied }: Props) {
  const { toast } = useToast()
  const [run, setRun] = useState<ExtractionOptimizationRun | null>(null)
  const [loading, setLoading] = useState(true)
  const [cancelling, setCancelling] = useState(false)
  const [applying, setApplying] = useState(false)
  const [reverting, setReverting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showWizard, setShowWizard] = useState(false)
  // Test-case count drives the cold-start hint in the idle hero. Null while
  // loading; 0 = cold start.
  const [testCaseCount, setTestCaseCount] = useState<number | null>(null)
  // When set, the user is browsing a historical run instead of the live one.
  // The panel renders the past run in read-only mode (apply/revert hidden,
  // re-run disabled, history click-throughs return us here, not the active run).
  const [viewingPast, setViewingPast] = useState<ExtractionOptimizationRun | null>(null)
  const [viewingPastLoading, setViewingPastLoading] = useState(false)
  const mountedRef = useRef(true)

  const poll = useIntervalPoll<ExtractionOptimizationRun>()
  const { stop: stopPolling } = poll

  const startPolling = useCallback((runUuid: string) => {
    poll.start({
      fetch: () => getExtractionOptimization(searchSetUuid, runUuid),
      intervalMs: POLL_INTERVAL_MS,
      isTerminal: (r) => r.status === 'completed' || r.status === 'failed' || r.status === 'cancelled',
      onUpdate: (r) => { if (mountedRef.current) setRun(r) },
      onError: (e) => console.error('Tuning polling failed', e),
    })
  }, [searchSetUuid, poll])

  // Initial mount: detect active/recent run + load test-case count for cold-start hint
  useEffect(() => {
    mountedRef.current = true
    setLoading(true)
    ;(async () => {
      try {
        const out = await getActiveExtractionOptimization(searchSetUuid)
        if (!mountedRef.current) return
        if (out.run) {
          setRun(out.run)
          if (out.run.status === 'queued' || out.run.status === 'running') {
            startPolling(out.run.uuid)
          }
          return
        }
        // No active run — restore the most recent finished one so a completed
        // result survives tab switches and page reloads instead of dropping
        // back to the idle hero (mirrors KB AutovalidateTab). Summaries omit
        // per-trial detail, so fetch the full run before rendering.
        const history = await listExtractionOptimizationHistory(searchSetUuid, { limit: 1 })
        if (!mountedRef.current) return
        const latest = history.items[0]
        if (latest) {
          const full = await getExtractionOptimization(searchSetUuid, latest.uuid)
          if (mountedRef.current) setRun(full)
        }
      } catch (e) {
        if (mountedRef.current) console.error('getActiveExtractionOptimization failed', e)
      } finally {
        if (mountedRef.current) setLoading(false)
      }
    })()
    listTestCases(searchSetUuid)
      .then(cases => { if (mountedRef.current) setTestCaseCount(cases.length) })
      .catch(() => { if (mountedRef.current) setTestCaseCount(0) })
    return () => {
      mountedRef.current = false
      stopPolling()
    }
  }, [searchSetUuid, startPolling, stopPolling])

  // Wizard owns the API call; we just seed a placeholder run and begin polling.
  const handleWizardStarted = (runUuid: string) => {
    setError(null)
    const seed: ExtractionOptimizationRun = {
      uuid: runUuid,
      search_set_uuid: searchSetUuid,
      status: 'queued',
      phase: 'queued',
      progress_message: 'Queued…',
      current_trial_index: 0,
      total_trials_planned: 0,
      best_score_so_far: null,
      best_config_so_far: null,
      token_budget: 0,
      tokens_used: 0,
      estimated_cost_usd: null,
      actual_cost_usd: null,
      baseline_no_tool_score: null,
      baseline_default_score: null,
      optimized_score: null,
      judge_variance: null,
      judge_score_se: null,
      tied_with_baseline: false,
      winner_selection_reason: null,
      excluded_models: [],
      judge_model: null,
      best_config: null,
      trials: [],
      field_breakdown: [],
      suggestions: [],
      previous_override: null,
      options: {},
      error_message: null,
      started_at: new Date().toISOString(),
      completed_at: null,
      cancel_requested: false,
    }
    setRun(seed)
    startPolling(runUuid)
  }

  const handleCancel = async () => {
    if (!run) return
    setCancelling(true)
    try {
      await cancelExtractionOptimization(searchSetUuid, run.uuid)
      toast('Cancellation requested', 'info')
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to cancel', 'error')
    } finally {
      setCancelling(false)
    }
  }

  // Phase 2: apply click shows the regression-count preview modal first so
  // users see "K fields will change, R regress" before the override flips.
  // Falls back to the legacy direct-apply path when the run lacks preview
  // data (older runs that pre-date the rollup).
  const [showApplyPreview, setShowApplyPreview] = useState(false)
  // Trial tapped open in the plain-English explainer modal.
  const [selectedTrial, setSelectedTrial] = useState<ExtractionTrial | null>(null)

  const handleApply = () => {
    if (!run) return
    if (run.apply_preview) {
      setShowApplyPreview(true)
    } else {
      void doApply()
    }
  }

  const doApply = async () => {
    if (!run) return
    setApplying(true)
    try {
      await applyExtractionOptimization(searchSetUuid, run.uuid)
      toast('Tuned settings applied', 'success')
      onApplied?.()
      // Refetch the run to update the previous_override field
      const fresh = await getExtractionOptimization(searchSetUuid, run.uuid)
      setRun(fresh)
      setShowApplyPreview(false)
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to apply', 'error')
    } finally {
      setApplying(false)
    }
  }

  const handleSelectPastRun = async (runUuid: string) => {
    setViewingPastLoading(true)
    try {
      const fresh = await getExtractionOptimization(searchSetUuid, runUuid)
      setViewingPast(fresh)
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to load past run', 'error')
    } finally {
      setViewingPastLoading(false)
    }
  }

  const handleExitPastRun = () => setViewingPast(null)

  const handleRevert = async () => {
    if (!run) return
    setReverting(true)
    try {
      await revertExtractionConfig(searchSetUuid)
      toast('Reverted to your previous configuration', 'success')
      onApplied?.()
      // Reset previous_override locally so the UI flips back to "Apply" state
      setRun({ ...run, previous_override: null })
    } catch (e) {
      toast(e instanceof Error ? e.message : 'Failed to revert', 'error')
    } finally {
      setReverting(false)
    }
  }

  const handleRunAgain = () => {
    setRun(null)
    setError(null)
    setShowWizard(true)
  }

  if (loading) return null

  // State A: idle — hero + button that opens the wizard + past runs
  if (!run) {
    return (
      <>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <IdleHero
            canManage={canManage}
            coldStart={testCaseCount === 0}
            onStart={() => setShowWizard(true)}
            error={error}
          />
          <ExtractionOptimizationHistoryPanel
            searchSetUuid={searchSetUuid}
            onSelect={handleSelectPastRun}
          />
        </div>
        {showWizard && (
          <ExtractionAutovalidateWizard
            searchSetUuid={searchSetUuid}
            onClose={() => setShowWizard(false)}
            onStarted={(runUuid) => {
              setShowWizard(false)
              handleWizardStarted(runUuid)
            }}
          />
        )}
      </>
    )
  }

  // State C: failed
  if (run.status === 'failed') {
    return (
      <FailedBanner
        message={run.error_message || 'Tuning failed.'}
        onRunAgain={handleRunAgain}
      />
    )
  }

  // State C: cancelled
  if (run.status === 'cancelled') {
    return (
      <CancelledBanner
        completedTrials={(run.trials || []).length}
        onRunAgain={handleRunAgain}
      />
    )
  }

  // State B: running (or queued)
  if (run.status === 'queued' || run.status === 'running') {
    const progressRun: ProgressRunShape<Record<string, unknown>> = {
      status: run.status,
      phase: run.phase,
      progress_message: run.progress_message,
      current_trial_index: run.current_trial_index,
      total_trials_planned: run.total_trials_planned,
      token_budget: run.token_budget,
      tokens_used: run.tokens_used,
      best_score_so_far: run.best_score_so_far,
      best_config_so_far: run.best_config_so_far,
      trials: (run.trials || []).map(t => ({
        trial_id: t.trial_id,
        config: t.config,
        score: t.score ?? 0,
        status: t.status,
      })),
      cancel_requested: run.cancel_requested,
      started_at: run.started_at,
    }
    return (
      <OptimizationProgressCard<Record<string, unknown>>
        run={progressRun}
        scoreFloor={run.baseline_no_tool_score}
        summariseConfig={(c) => summariseExtractionConfig(c, true)}
        onCancel={handleCancel}
        cancelling={cancelling}
        runningLabel="Tuning running"
        queuedLabel="Tuning queued"
        scoreFloorLabel={DOMAIN_LABELS.extraction.scoreFloorLabel}
        scoreFloorDescription={DOMAIN_LABELS.extraction.scoreFloorDescription}
        liftLabel={DOMAIN_LABELS.extraction.liftLabel}
        /* Only judge tokens are tracked end-to-end; extraction tokens aren't
           counted yet, so labeling this "Token budget" would overclaim. */
        tokensBarLabel="Judge spend"
      />
    )
  }

  // State C: completed.
  //
  // The displayed run is either the live one or a historical one (when the
  // user clicked through from the history panel). Past runs are rendered
  // read-only — apply/revert/re-run are hidden, and a PastRunBanner indicates
  // the read-only state with a "back to current" exit.
  const displayedRun = viewingPast ?? run
  const isPast = viewingPast !== null

  const extractionLabels = DOMAIN_LABELS.extraction.baselineTile
  const baselines: BaselinePoint[] = [
    { id: 'no-tool', label: extractionLabels.noBaseline, score: displayedRun.baseline_no_tool_score, color: '#9ca3af' },
    { id: 'default', label: extractionLabels.yourSettings, score: displayedRun.baseline_default_score, color: '#3b82f6' },
    { id: 'optimized', label: extractionLabels.tuned, score: displayedRun.optimized_score, color: '#22c55e', emphasised: true },
  ]
  const isAlreadyApplied = displayedRun.previous_override !== null

  // Translate backend suggestions (which carry an extraction-specific 'kind')
  // into the shared component's domain-neutral shape.
  const suggestionsList: Suggestion[] = (displayedRun.suggestions || []).map(s => ({
    severity: s.severity as SuggestionSeverity,
    message: s.message,
  }))

  return (
    // Cohesive dark surface for the whole completed view. Every child here
    // (QualityComparisonCard, BestConfigCard, the trials/reproducibility/history
    // panels, and the tinted result banners) is dark-themed with light text —
    // they assume a dark backdrop. This panel renders inside the extraction
    // editor's Validate tab, which is a white (#fff) page, so without this
    // wrapper the dark cards float as washed-out islands and the translucent
    // tint banners composite over white into near-invisible pastels. The
    // wrapper mirrors the sibling WorkflowAutovalidatePanel, which solves the
    // same problem the same way in the workflow editor's Validate tab. #1a1a1a
    // (a hair darker than the #1f1f1f cards) gives them subtle elevation.
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 12,
      padding: 16, borderRadius: 8,
      background: '#1a1a1a', border: '1px solid #2a2a2a',
    }}>
      {isPast && (
        <PastRunBanner
          startedAt={displayedRun.started_at}
          onExit={handleExitPastRun}
        />
      )}
      {viewingPastLoading && (
        <div style={{ fontSize: 12, color: '#888', padding: 8 }}>Loading past run…</div>
      )}
      <QualityComparisonCard
        baselines={baselines}
        /* judge_score_se is σ / √N — the SE on the per-trial mean. Prefer
           it over the per-item σ so the displayed ±N pts CI matches the
           significance gate that drives tied_with_baseline. Falls back to
           judge_variance for legacy runs that don't carry the SE field. */
        variance={displayedRun.judge_score_se ?? displayedRun.judge_variance ?? 0}
        secondaryBaselineId="no-tool"
      />
      {/* The scores above are discounted for a small test set so they sit on the
          same scale as the official quality tile (which applies the same
          discount). Without this, the card read higher than the certified score
          and apply looked like a regression. Disclose the discount + how to
          clear it. */}
      {displayedRun.score_sample_size
        && displayedRun.score_sample_size.sample_size_factor < 1
        && displayedRun.score_sample_size.test_cases_needed > 0 && (
        <div style={{ fontSize: 11, color: '#fbbf24', marginTop: -4 }}>
          Scores are discounted for a small test set — measured on{' '}
          {displayedRun.score_sample_size.num_test_cases} test case
          {displayedRun.score_sample_size.num_test_cases === 1 ? '' : 's'}.
          Add {displayedRun.score_sample_size.test_cases_needed} more to score at full confidence.
        </div>
      )}
      {/* Significance-gated outcome banner. When the optimizer's best trial
          is statistically tied with the user's current config (within 2 × SE
          of judge noise), apply is disabled and we explain why — otherwise
          we'd be writing a config change the data can't justify. */}
      {displayedRun.tied_with_baseline && (
        <div
          role="status"
          style={{
            padding: '10px 14px', borderRadius: 6, fontSize: 13,
            background: 'rgba(245, 158, 11, 0.08)',
            border: '1px solid rgba(245, 158, 11, 0.3)',
            color: '#fbbf24',
            display: 'flex', flexDirection: 'column', gap: 4,
          }}
        >
          <div style={{ fontWeight: 600 }}>No significant improvement</div>
          <div style={{ color: '#d1d5db' }}>
            The best trial was within the <TermDef term="noise-floor">judge's measurement noise</TermDef> (±{((displayedRun.judge_score_se ?? 0.02) * 200).toFixed(1)} pts confidence interval)
            of your current settings. Apply is disabled — your settings already perform as well as anything we tried.
          </div>
        </div>
      )}
      {displayedRun.excluded_models && displayedRun.excluded_models.length > 0 && (
        <ExcludedModelsDisclosure count={displayedRun.excluded_models.length} />
      )}
      {displayedRun.winner_cross_field_summary && (
        <WinnerCrossFieldPanel
          summary={displayedRun.winner_cross_field_summary}
          ruleBreakdown={displayedRun.winner_cross_field_rule_breakdown || []}
        />
      )}
      {displayedRun.post_apply_validation && (
        <PostApplyDelta
          before={displayedRun.optimized_score}
          after={displayedRun.post_apply_validation}
        />
      )}
      {displayedRun.best_config && (
        <BestConfigCard
          config={displayedRun.best_config}
          canManage={canManage && !displayedRun.tied_with_baseline}
          isPast={isPast}
          isAlreadyApplied={isAlreadyApplied}
          onApply={handleApply}
          applying={applying}
          onRevert={handleRevert}
          reverting={reverting}
        />
      )}
      <WinnerExplanation run={displayedRun} />
      {suggestionsList.length > 0 && (
        <SuggestionsList
          title="Suggestions"
          suggestions={suggestionsList}
        />
      )}
      {(displayedRun.trials || []).length > 0 && (
        <TrialsTable<ExtractionTrial>
          trials={displayedRun.trials}
          sortOptions={EXTRACTION_TRIAL_SORT_OPTIONS}
          renderRow={(t) => (
            <ExtractionTrialRow trial={t} />
          )}
          getRowKey={(t) => t.trial_id}
          onRowClick={setSelectedTrial}
          title="Trials — tap any for a plain-English breakdown"
        />
      )}

      {/* Plain-English explainer for a tapped trial. */}
      <ExtractionTrialExplainerModal trial={selectedTrial} onClose={() => setSelectedTrial(null)} />
      <ReproducibilityPanel
        run={{
          judge_model: displayedRun.judge_model,
          judge_variance: displayedRun.judge_variance,
          started_at: displayedRun.started_at,
        }}
      />
      <ExtractionOptimizationHistoryPanel
        searchSetUuid={searchSetUuid}
        excludeRunUuid={displayedRun.uuid}
        onSelect={handleSelectPastRun}
      />
      {!isPast && (
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button
            onClick={handleRunAgain}
            disabled={!canManage}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '6px 14px', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
              color: canManage ? '#a78bfa' : '#555',
              background: 'transparent',
              border: '1px solid ' + (canManage ? 'rgba(124, 58, 237, 0.3)' : '#333'),
              borderRadius: 6, cursor: canManage ? 'pointer' : 'not-allowed',
            }}
          >
            <RotateCcw size={12} />
            Re-run
          </button>
        </div>
      )}
      {!isPast && displayedRun.apply_preview && (
        <ApplyPreviewModal
          open={showApplyPreview}
          preview={displayedRun.apply_preview}
          itemNoun="field"
          itemNounPlural="fields"
          onConfirm={() => void doApply()}
          onCancel={() => setShowApplyPreview(false)}
          applying={applying}
        />
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
// Excluded-models disclosure — surfaces same-family exclusion as a collapsible
// detail instead of an unexplained breadcrumb the first-time reader has to parse.
// ---------------------------------------------------------------------------

function ExcludedModelsDisclosure({ count }: { count: number }) {
  const [open, setOpen] = useState(false)
  return (
    <div
      style={{
        padding: '8px 12px', borderRadius: 6, fontSize: 12,
        background: 'rgba(59, 130, 246, 0.06)',
        border: '1px solid rgba(59, 130, 246, 0.2)',
        color: '#9ca3af',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        <span>
          We excluded {count} model{count === 1 ? '' : 's'} that would have unfairly graded {count === 1 ? 'itself' : 'themselves'}.
        </span>
        <button
          type="button"
          onClick={() => setOpen(v => !v)}
          aria-expanded={open}
          style={{
            background: 'transparent', border: 'none', padding: 0,
            color: '#a78bfa', fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
            cursor: 'pointer', textDecoration: 'underline dotted', textUnderlineOffset: 2,
          }}
        >
          Why?
        </button>
      </div>
      {open && (
        <div style={{ marginTop: 6, lineHeight: 1.5 }}>
          Asking an AI to grade answers from its own family tends to inflate the score for those answers (the grader recognises its own style). We drop those candidates from the sweep so the comparison stays fair.
        </div>
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
// Idle hero
// ---------------------------------------------------------------------------

function IdleHero({
  canManage, coldStart, onStart, error,
}: { canManage: boolean; coldStart: boolean; onStart: () => void; error: string | null }) {
  return (
    <div style={{
      padding: 18, background: 'linear-gradient(135deg, #1f1f2e 0%, #1a1a1a 100%)',
      border: '1px solid rgba(124, 58, 237, 0.25)', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <Sparkles size={18} style={{ color: '#a78bfa' }} />
        <h3 style={{ margin: 0, fontSize: 15, color: '#fff' }}>Get an accuracy score for this extraction — and a one-click recipe to improve it</h3>
      </div>
      <p style={{ margin: '0 0 12px 0', fontSize: 13, color: '#bbb', lineHeight: 1.5 }}>
        Typically <b>$1–$5</b> and <b>5–15 minutes</b>. We score your extraction
        against test cases, try many model/strategy combinations, and recommend
        the best. Nothing changes until you click Apply.
      </p>
      {coldStart && (
        <div style={{
          padding: '10px 12px', marginBottom: 12,
          backgroundColor: 'rgba(124, 58, 237, 0.06)',
          border: '1px solid rgba(124, 58, 237, 0.2)', borderRadius: 6,
        }}>
          <div style={{
            fontSize: 10, color: '#a78bfa', textTransform: 'uppercase', letterSpacing: 0.5,
            marginBottom: 6, fontWeight: 600,
          }}>
            What happens next
          </div>
          <ol style={{
            margin: 0, paddingLeft: 20, fontSize: 12, color: '#ccc', lineHeight: 1.6,
          }}>
            <li>We'll suggest expected values for a few documents</li>
            <li>You'll review them before anything else runs</li>
            <li>We try many setups and recommend the best — you decide whether to apply</li>
          </ol>
        </div>
      )}
      <ul style={{ fontSize: 12, color: '#999', margin: '0 0 10px 0', paddingLeft: 18, lineHeight: 1.7 }}>
        <li>See how much your custom settings actually help vs. defaults</li>
        <li>Get a recommended setup with one-click apply</li>
        <li>Spot which fields are pulling weight and which aren't</li>
      </ul>
      <WhenToRunDisclosure kind="extraction" />
      {error && <ErrorBanner message={error} />}
      <button
        onClick={onStart}
        disabled={!canManage}
        title={!canManage ? 'You cannot manage this extraction' : ''}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '8px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
          color: !canManage ? '#555' : '#fff',
          background: !canManage ? '#222' : 'linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)',
          border: '1px solid ' + (!canManage ? '#333' : '#7c3aed'),
          borderRadius: 6, cursor: !canManage ? 'not-allowed' : 'pointer',
        }}
      >
        <Sparkles size={14} />
        Validate & improve
      </button>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Best-config card — structured grid with per-field tooltips (parallel to KB)
// ---------------------------------------------------------------------------

function BestConfigCard({
  config, canManage, isPast, isAlreadyApplied,
  onApply, applying, onRevert, reverting,
}: {
  config: Record<string, unknown>
  canManage: boolean
  isPast: boolean
  isAlreadyApplied: boolean
  onApply: () => void
  applying: boolean
  onRevert: () => void
  reverting: boolean
}) {
  const chunkSize = (config as { chunking?: { chunk_size?: number } }).chunking?.chunk_size
  const rows: { label: string; value: string; hint: string }[] = [
    {
      label: 'Model',
      value: String(config.model ?? 'default'),
      hint: 'Which LLM does the extraction.',
    },
    {
      label: 'Strategy',
      value: String(config.strategy ?? 'one-pass'),
      hint: 'one-pass = extract everything in a single call. two-pass = a planning pass followed by a structured extraction pass; slower but often more accurate on complex schemas.',
    },
    {
      label: 'Thinking',
      value: config.thinking ? 'on' : 'off',
      hint: 'Whether the model uses extended thinking before answering. Slower and more expensive, but often more accurate on hard fields.',
    },
    {
      label: 'Image mode',
      value: config.use_images ? 'on' : 'off',
      hint: 'When on, documents are sent to the model as images instead of extracted text. Useful for fillable PDFs and scans.',
    },
    {
      label: 'Chunk size',
      value: typeof chunkSize === 'number' ? String(chunkSize) : 'auto',
      hint: 'How many characters per chunk when documents are long enough to need splitting.',
    },
  ]
  return (
    <div style={{
      padding: 14, backgroundColor: '#1f1f1f',
      border: '1px solid #2e2e2e', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <Sparkles size={14} style={{ color: '#a78bfa' }} />
        <span style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>Best configuration</span>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        {rows.map(r => (
          <div key={r.label} title={r.hint} style={{
            padding: '6px 10px', backgroundColor: '#262626', borderRadius: 4, cursor: 'help',
          }}>
            <div style={{ fontSize: 10, color: '#888', textTransform: 'uppercase', letterSpacing: 0.5 }}>{r.label}</div>
            <div style={{ fontSize: 12, color: '#e5e5e5', marginTop: 2 }}>{r.value}</div>
          </div>
        ))}
      </div>
      {!isPast && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
          <ApplyBackButton
            canApply={canManage}
            onApply={onApply}
            applying={applying}
            isAlreadyApplied={isAlreadyApplied}
          />
          {isAlreadyApplied && (
            <button
              onClick={onRevert}
              disabled={!canManage || reverting}
              style={{
                padding: '6px 12px', fontSize: 12, fontWeight: 500, fontFamily: 'inherit',
                color: canManage && !reverting ? '#bbb' : '#555',
                background: 'transparent',
                border: '1px solid #3a3a3a',
                borderRadius: 6,
                cursor: canManage && !reverting ? 'pointer' : 'not-allowed',
              }}
              title="Restore your previous configuration"
            >
              {reverting ? 'Reverting…' : 'Revert'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
// Trials table — sort options + config summariser
// ---------------------------------------------------------------------------

const EXTRACTION_TRIAL_SORT_OPTIONS = makeStandardSortOptions<ExtractionTrial>()

/** Domain-specific config formatter for extraction trial configs.
 *
 * Delegates to the shared decoder so the row, the progress card, and the
 * explainer modal all read the real (nested) config shape — strategy, thinking,
 * consensus, chunking, prompt variant, model. The terse form is for the trials
 * table; the verbose form is for the running-state summary. */
function summariseExtractionConfig(c: Record<string, unknown>, verbose = false): string {
  return summariseExtractionTrialConfig(c, verbose)
}


// ---------------------------------------------------------------------------
// Extraction-specific trial row — adds a cross-field pass/fail chip alongside
// the standard score/lift readout. Doesn't extend the shared TrialRow because
// the chip is extraction-specific.
// ---------------------------------------------------------------------------

function ExtractionTrialRow({ trial }: { trial: ExtractionTrial }) {
  const score = trial.score ?? 0
  const cf = trial.cross_field_summary
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '6px 10px', fontSize: 11, color: '#ddd',
      backgroundColor: trial.status === 'failed' ? 'rgba(239, 68, 68, 0.05)' : 'rgba(0,0,0,0.2)',
      borderRadius: 4,
    }}>
      <span style={{
        width: 6, height: 6, borderRadius: '50%',
        backgroundColor: scoreColor(score),
      }} />
      <span style={{
        flex: 1, overflow: 'hidden', textOverflow: 'ellipsis',
        whiteSpace: 'nowrap', color: '#aaa',
      }}>
        {summariseExtractionConfig(trial.config)}
      </span>
      {cf && (cf.pass + cf.fail) > 0 && (
        <span
          title={`Cross-field rules — ${cf.pass} pass / ${cf.fail} fail${cf.unparseable ? ` / ${cf.unparseable} unparseable` : ''}`}
          style={{
            fontSize: 10, padding: '1px 6px', borderRadius: 4,
            color: cf.fail === 0 ? '#22c55e' : cf.pass === 0 ? '#ef4444' : '#fbbf24',
            background: cf.fail === 0
              ? 'rgba(34, 197, 94, 0.12)'
              : cf.pass === 0
                ? 'rgba(239, 68, 68, 0.12)'
                : 'rgba(245, 158, 11, 0.12)',
            border: '1px solid ' + (cf.fail === 0
              ? 'rgba(34, 197, 94, 0.3)'
              : cf.pass === 0
                ? 'rgba(239, 68, 68, 0.3)'
                : 'rgba(245, 158, 11, 0.3)'),
          }}
        >
          rules {cf.pass}/{cf.pass + cf.fail}
        </span>
      )}
      {trial.lift_vs_default != null && (
        <span style={{
          fontSize: 10,
          color: trial.lift_vs_default > 0 ? '#22c55e'
            : trial.lift_vs_default < 0 ? '#ef4444' : '#666',
        }}>
          {trial.lift_vs_default > 0 ? '+' : ''}{(trial.lift_vs_default * 100).toFixed(0)}pts
        </span>
      )}
      <span style={{
        width: 50, textAlign: 'right', fontWeight: 600, color: '#e5e5e5',
      }}>
        {(score * 100).toFixed(0)}%
      </span>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Winner cross-field panel — headline pass-rate plus per-rule breakdown.
// Only rendered when the SearchSet has rules; otherwise summary is null and
// the panel doesn't appear at all.
// ---------------------------------------------------------------------------

function WinnerCrossFieldPanel({
  summary, ruleBreakdown,
}: {
  summary: NonNullable<ExtractionOptimizationRun['winner_cross_field_summary']>
  ruleBreakdown: NonNullable<ExtractionOptimizationRun['winner_cross_field_rule_breakdown']>
}) {
  const decisive = summary.pass + summary.fail
  // No decisive evaluations means every rule was unparseable — don't claim a
  // pass-rate the data doesn't support.
  if (decisive === 0) return null
  const passRate = summary.pass_rate ?? (summary.pass / decisive)
  const passRatePct = Math.round(passRate * 100)
  const tone = summary.fail === 0
    ? 'good'
    : passRate >= 0.7 ? 'warn' : 'bad'
  const palette = tone === 'good'
    ? { fg: '#22c55e', bg: 'rgba(34, 197, 94, 0.08)', border: 'rgba(34, 197, 94, 0.25)' }
    : tone === 'warn'
      ? { fg: '#fbbf24', bg: 'rgba(245, 158, 11, 0.08)', border: 'rgba(245, 158, 11, 0.25)' }
      : { fg: '#fca5a5', bg: 'rgba(239, 68, 68, 0.08)', border: 'rgba(239, 68, 68, 0.25)' }
  return (
    <div style={{
      padding: 14, borderRadius: 8,
      background: palette.bg, border: '1px solid ' + palette.border,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <div style={{
          fontSize: 10, color: palette.fg, textTransform: 'uppercase', letterSpacing: 0.5,
          fontWeight: 600,
        }}>
          Cross-field rules on winning config
        </div>
        <div style={{ marginLeft: 'auto', fontSize: 18, fontWeight: 700, color: '#fff' }}>
          {summary.pass}/{decisive} pass
          <span style={{ marginLeft: 8, fontSize: 12, color: palette.fg, fontWeight: 500 }}>
            ({passRatePct}%)
          </span>
        </div>
      </div>
      {summary.unparseable > 0 && (
        <div style={{ fontSize: 11, color: '#888', marginBottom: 10 }}>
          {summary.unparseable} rule evaluation{summary.unparseable === 1 ? '' : 's'} couldn't be parsed and are excluded from the pass rate.
        </div>
      )}
      {ruleBreakdown.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {ruleBreakdown.map((r) => {
            const ruleDecisive = r.pass + r.fail
            const rulePct = ruleDecisive > 0 ? Math.round((r.pass / ruleDecisive) * 100) : null
            const failOnly = r.fail > 0 && r.pass === 0
            return (
              <div key={r.rule_id} style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '5px 8px', fontSize: 11, color: '#ddd',
                background: 'rgba(0,0,0,0.2)', borderRadius: 4,
              }}>
                <span style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: r.fail === 0 ? '#22c55e' : failOnly ? '#ef4444' : '#fbbf24',
                }} />
                <span style={{
                  flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  color: '#bbb',
                }}>
                  {r.label || r.type || r.rule_id}
                </span>
                <span style={{ fontSize: 10, color: '#888' }}>
                  {r.pass}/{ruleDecisive}{r.unparseable ? ` (+${r.unparseable} unparseable)` : ''}
                </span>
                {rulePct != null && (
                  <span style={{
                    width: 40, textAlign: 'right', fontWeight: 600,
                    color: r.fail === 0 ? '#22c55e' : failOnly ? '#ef4444' : '#fbbf24',
                  }}>
                    {rulePct}%
                  </span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
// Post-apply validation delta — closes the loop by showing how the tuned
// config actually performed when re-validated against the test set after
// being applied.
// ---------------------------------------------------------------------------

function PostApplyDelta({
  before, after,
}: {
  before: number | null
  after: NonNullable<ExtractionOptimizationRun['post_apply_validation']>
}) {
  const beforePct = before != null ? Math.round(before * 100) : null
  // Certified score = the authoritative, sample-size–penalized number that
  // also drives the official quality tile. This is the headline — once it's
  // here the user never needs the standalone validation panel for a score.
  const certified = after.score ?? after.accuracy
  const certifiedPct = certified != null ? Math.round(certified * 100) : null
  // Both numbers now carry the same sample-size discount: the optimizer's
  // headline (``before``) is discounted to the certified scale (Option A), and
  // ``after.score`` is the certified, penalized measurement. Comparing like to
  // like keeps a small test set's discount from masquerading as a regression.
  const delta = (beforePct != null && certifiedPct != null) ? certifiedPct - beforePct : null
  const penalty = after.score_breakdown
  const penalized = penalty != null && penalty.sample_size_penalty > 0
  return (
    <div style={{
      padding: 12, borderRadius: 8,
      background: 'rgba(59, 130, 246, 0.06)',
      border: '1px solid rgba(59, 130, 246, 0.25)',
    }}>
      <div style={{
        fontSize: 10, color: '#60a5fa', textTransform: 'uppercase', letterSpacing: 0.5,
        fontWeight: 600, marginBottom: 6,
      }}>
        Certified score · measured after apply
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        {certifiedPct != null && (
          <span style={{ fontSize: 12, color: '#aaa' }}>
            Quality score:{' '}
            <b style={{ color: '#fff', fontSize: 16 }}>{certifiedPct}%</b>
            {after.quality_tier && (
              <span style={{
                marginLeft: 6, fontSize: 10, textTransform: 'capitalize',
                color: '#9ca3af', border: '1px solid #3a3a3a', borderRadius: 4, padding: '1px 5px',
              }}>
                {after.quality_tier}
              </span>
            )}
          </span>
        )}
        {beforePct != null && (
          <span style={{ fontSize: 12, color: '#aaa' }}>
            Optimizer estimate: <b style={{ color: '#e5e5e5' }}>{beforePct}%</b>
          </span>
        )}
        {delta != null && (
          <span style={{
            marginLeft: 'auto', fontSize: 12, fontWeight: 600,
            color: delta >= 0 ? '#22c55e' : '#ef4444',
          }}>
            {delta >= 0 ? '+' : ''}{delta}pp vs estimate
          </span>
        )}
      </div>
      <div style={{ marginTop: 6, fontSize: 11, color: '#888' }}>
        This is the official quality score — no need to run validation separately.
        Measured on {after.test_case_count} test case{after.test_case_count === 1 ? '' : 's'}
        {after.num_runs ? ` × ${after.num_runs} runs` : ''} on{' '}
        {new Date(after.ran_at).toLocaleString()}.
        {after.source === 'apply_on_finish' && ' Triggered by "apply on finish".'}
      </div>
      {penalized && penalty && (
        <div style={{ marginTop: 6, fontSize: 11, color: '#fbbf24' }}>
          Discounted for small sample size ({Math.round(penalty.raw_score)}% → {Math.round(penalty.final_score)}%).
          Add{penalty.test_cases_needed > 0 ? ` ${penalty.test_cases_needed} more test case${penalty.test_cases_needed === 1 ? '' : 's'}` : ''}
          {penalty.test_cases_needed > 0 && penalty.runs_needed > 0 ? ' and' : ''}
          {penalty.runs_needed > 0 ? ` ${penalty.runs_needed} more run${penalty.runs_needed === 1 ? '' : 's'}` : ''}
          {' '}to certify at full confidence.
        </div>
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
// Winner explainer — plain-English account of why the chosen config won, or
// why apply is disabled. Signal lives on the run doc already; this just
// renders it so the user doesn't have to read backend tag names.
// ---------------------------------------------------------------------------

function WinnerExplanation({ run }: { run: ExtractionOptimizationRun }) {
  const reason = run.winner_selection_reason
  if (!reason) return null
  const se = run.judge_score_se ?? null
  // Judge noise band the significance gate uses (±2σ on the per-trial mean).
  const bandPts = se != null ? (se * 2 * 100).toFixed(1) : null
  let body: string
  if (reason === 'highest_score') {
    body = bandPts != null
      ? `The winning trial beat the runner-up by more than the judge-noise band (±${bandPts} pts at 2σ, measured on the default baseline). Apply is enabled.`
      : 'The winning trial cleared the significance threshold against the runner-up.'
  } else if (reason === 'default_in_cluster') {
    body = bandPts != null
      ? `Your current settings are within ±${bandPts} pts (2σ) of the best trial — the data can't justify changing them. Apply is disabled.`
      : 'Your current settings are statistically tied with the best trial. Apply is disabled.'
  } else if (reason === 'closest_to_default') {
    body = 'Multiple non-default configs tied with the leader; we picked the one that changes the fewest knobs from your current settings — fewer surprises downstream.'
  } else if (reason === 'no_judge_variance') {
    body = 'Judge variance could not be measured (judge was off, or too few samples to estimate σ). We used a default noise floor for the significance check — treat the lift as a rough estimate.'
  } else {
    body = `Winner selected by rule: ${reason}.`
  }
  return (
    <div style={{
      padding: '10px 12px', borderRadius: 6, fontSize: 12, color: '#ccc',
      background: 'rgba(124, 58, 237, 0.05)', border: '1px solid rgba(124, 58, 237, 0.2)',
      lineHeight: 1.5,
    }}>
      <div style={{
        fontSize: 10, color: '#a78bfa', textTransform: 'uppercase', letterSpacing: 0.5,
        fontWeight: 600, marginBottom: 4,
      }}>
        Why this config won
      </div>
      {body}
    </div>
  )
}
