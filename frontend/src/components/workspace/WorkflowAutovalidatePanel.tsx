/**
 * Workflow Autovalidate panel — the v2 replacement for WorkflowOptimizationPanel.
 *
 * Consumes the shared autovalidate components so the workflow surface matches
 * KB and extraction:
 *
 *   - AutovalidateWizard (via WorkflowAutovalidateWizard) — launch UX
 *   - OptimizationProgressCard — live progress while running
 *   - QualityComparisonCard — no-workflow / current / optimized lift readout
 *   - SuggestionsList — per-step + run-level recommendations
 *   - ApplyBackButton — apply/revert with already-applied awareness
 *
 * Polling interval (2.5s) is unchanged from v1 — workflow trials take minutes
 * each, so tighter polling just spams the API.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Sparkles } from 'lucide-react'
import {
  applyWorkflowOptimization,
  cancelWorkflowOptimization,
  getActiveWorkflowOptimization,
  getWorkflowOptimization,
  revertWorkflowOptimization,
  type WorkflowOptimizationRun,
  type WorkflowOptimizationTrial,
  type WorkflowStepBreakdownEntry,
  type WorkflowStepOverride,
} from '../../api/workflows'
import { OptimizationProgressCard, type ProgressRunShape } from '../shared/OptimizationProgressCard'
import { QualityComparisonCard, type BaselinePoint } from '../shared/QualityComparisonCard'
import { SuggestionsList, type Suggestion } from '../shared/SuggestionsList'
import { ApplyBackButton } from '../shared/ApplyBackButton'
import { ApplyPreviewModal } from '../shared/ApplyPreviewModal'
import { TrialsTable, TrialRow, makeStandardSortOptions } from '../shared/TrialsTable'
import { WorkflowTrialExplainerModal } from './WorkflowTrialExplainerModal'
import { summariseWorkflowTrialConfig } from './workflowTrialExplanations'
import { WorkflowAutovalidateWizard } from './WorkflowAutovalidateWizard'
import { DOMAIN_LABELS } from '../shared/labels'
import { WhenToRunDisclosure } from '../shared/WhenToRunDisclosure'


export function WorkflowAutovalidatePanel({ workflowId }: { workflowId: string }) {
  const [run, setRun] = useState<WorkflowOptimizationRun | null>(null)
  const [showWizard, setShowWizard] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const [applying, setApplying] = useState(false)
  const [reverting, setReverting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  // Load any in-progress run on mount.
  useEffect(() => {
    getActiveWorkflowOptimization(workflowId)
      .then(({ run: r }) => { if (r) setRun(r) })
      .catch(() => {})
    return () => stopPoll()
  }, [workflowId, stopPoll])

  // Poll while running.
  useEffect(() => {
    if (!run || (run.status !== 'queued' && run.status !== 'running')) {
      stopPoll()
      return
    }
    if (pollRef.current) return
    pollRef.current = setInterval(async () => {
      try {
        const fresh = await getWorkflowOptimization(workflowId, run.uuid)
        setRun(fresh)
        if (fresh.status !== 'queued' && fresh.status !== 'running') stopPoll()
      } catch (e) {
        if (e instanceof Error) setError(e.message)
      }
    }, 2500)
    return () => stopPoll()
  }, [run, workflowId, stopPoll])

  const handleCancel = useCallback(async () => {
    if (!run) return
    setCancelling(true)
    try {
      await cancelWorkflowOptimization(workflowId, run.uuid)
      const fresh = await getWorkflowOptimization(workflowId, run.uuid)
      setRun(fresh)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to cancel')
    } finally {
      setCancelling(false)
    }
  }, [run, workflowId])

  // Phase 2: apply click shows the regression-count preview modal first.
  // Older runs without ``apply_preview`` go through the direct path.
  const [showApplyPreview, setShowApplyPreview] = useState(false)

  const handleApply = useCallback(() => {
    if (!run) return
    if (run.apply_preview) {
      setShowApplyPreview(true)
    } else {
      void doApply()
    }
    // doApply is defined below — useCallback dep handled by run/workflowId.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run])

  // Phase 3: when the user selects a subset of step IDs in CompletedView,
  // we pass only those to the apply endpoint. Empty/undefined = apply all.
  const [selectedStepIds, setSelectedStepIds] = useState<string[] | undefined>(undefined)

  const doApply = useCallback(async () => {
    if (!run) return
    setApplying(true)
    try {
      await applyWorkflowOptimization(
        workflowId, run.uuid,
        selectedStepIds && selectedStepIds.length > 0 ? selectedStepIds : undefined,
      )
      const fresh = await getWorkflowOptimization(workflowId, run.uuid)
      setRun(fresh)
      setShowApplyPreview(false)
      setSelectedStepIds(undefined)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to apply config')
    } finally {
      setApplying(false)
    }
  }, [run, workflowId, selectedStepIds])

  const handleRevert = useCallback(async () => {
    if (!run) return
    setReverting(true)
    try {
      await revertWorkflowOptimization(workflowId, run.uuid)
      const fresh = await getWorkflowOptimization(workflowId, run.uuid)
      setRun(fresh)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to revert')
    } finally {
      setReverting(false)
    }
  }, [run, workflowId])

  const handleStarted = useCallback(async (runUuid: string) => {
    try {
      const fresh = await getWorkflowOptimization(workflowId, runUuid)
      setRun(fresh)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load run')
    }
  }, [workflowId])

  const isIdle = !run || run.status === 'completed' || run.status === 'failed' || run.status === 'cancelled'
  const isRunning = run && (run.status === 'queued' || run.status === 'running')

  return (
    <div
      style={{
        padding: 20,
        border: '1px solid #2e2e2e',
        borderRadius: 8,
        background: '#1f1f1f',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Sparkles size={16} style={{ color: '#a78bfa' }} />
            <div style={{ fontSize: 15, fontWeight: 600, color: '#fff' }}>
              Tune this workflow
            </div>
          </div>
          <div style={{ fontSize: 13, color: '#bbb', marginTop: 4, lineHeight: 1.5 }}>
            Try different per-step model and prompt-style combinations against your expected
            outputs. Apply the best config back with one click.
          </div>
          <div style={{ marginTop: 10 }}>
            <WhenToRunDisclosure kind="workflow" />
          </div>
        </div>
        {isIdle && (
          <button
            type="button"
            onClick={() => setShowWizard(true)}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              padding: '8px 14px', borderRadius: 6,
              background: 'linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)',
              color: '#fff',
              border: '1px solid #7c3aed',
              fontSize: 13, fontWeight: 600, fontFamily: 'inherit', cursor: 'pointer',
            }}
          >
            <Sparkles size={14} />
            {run ? 'Re-run tuning' : 'Tune workflow'}
          </button>
        )}
      </div>

      {error && (
        <div
          style={{
            marginTop: 12, padding: '8px 12px', borderRadius: 6,
            background: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            color: '#fca5a5', fontSize: 13,
          }}
        >
          {error}
        </div>
      )}

      {isRunning && run && (
        <div style={{ marginTop: 16 }}>
          <OptimizationProgressCard<WorkflowOptimizationTrial['config']>
            run={runForProgress(run)}
            scoreFloor={run.baseline_no_workflow_score ?? run.baseline_default_score}
            summariseConfig={summariseConfig}
            onCancel={handleCancel}
            cancelling={cancelling}
            scoreFloorLabel={DOMAIN_LABELS.workflow.scoreFloorLabel}
            scoreFloorDescription={DOMAIN_LABELS.workflow.scoreFloorDescription}
            liftLabel={DOMAIN_LABELS.workflow.liftLabel}
          />
        </div>
      )}

      {isIdle && run && run.status === 'failed' && (
        <div style={{ marginTop: 12, color: '#fca5a5', fontSize: 13 }}>
          Tuning failed: {run.error_message || 'unknown error'}
        </div>
      )}

      {isIdle && run && run.status === 'cancelled' && (
        <div style={{ marginTop: 12, color: '#9ca3af', fontSize: 13 }}>
          Cancelled. {run.trials.length > 0
            ? `Best so far: ${formatScore(run.best_score_so_far)}.`
            : 'No trial results.'}
        </div>
      )}

      {isIdle && run && run.status === 'completed' && (
        <CompletedView
          run={run}
          onApply={handleApply}
          onRevert={handleRevert}
          applying={applying}
          reverting={reverting}
          selectedStepIds={selectedStepIds}
          onSelectionChange={setSelectedStepIds}
        />
      )}

      {showWizard && (
        <WorkflowAutovalidateWizard
          workflowId={workflowId}
          onClose={() => setShowWizard(false)}
          onStarted={handleStarted}
        />
      )}
      {run && run.apply_preview && (
        <ApplyPreviewModal
          open={showApplyPreview}
          preview={run.apply_preview}
          itemNoun="step"
          itemNounPlural="steps"
          onConfirm={() => void doApply()}
          onCancel={() => setShowApplyPreview(false)}
          applying={applying}
        />
      )}
    </div>
  )
}


const WORKFLOW_TRIAL_SORT_OPTIONS = makeStandardSortOptions<WorkflowOptimizationTrial>()

function CompletedView({
  run, onApply, onRevert, applying, reverting,
  selectedStepIds, onSelectionChange,
}: {
  run: WorkflowOptimizationRun
  onApply: () => void
  onRevert: () => void
  applying: boolean
  reverting: boolean
  /** Phase 3: subset of step IDs to apply. Undefined / empty = apply all. */
  selectedStepIds: string[] | undefined
  onSelectionChange: (next: string[] | undefined) => void
}) {
  const workflowLabels = DOMAIN_LABELS.workflow.baselineTile
  const baselines: BaselinePoint[] = useMemo(() => {
    const out: BaselinePoint[] = []
    if (run.baseline_no_workflow_score != null) {
      out.push({
        id: 'no-workflow',
        label: workflowLabels.noBaseline,
        score: run.baseline_no_workflow_score,
        color: '#94a3b8',
      })
    }
    out.push({
      id: 'default',
      label: workflowLabels.yourSettings,
      score: run.baseline_default_score,
      color: '#3b82f6',
    })
    out.push({
      id: 'optimized',
      label: workflowLabels.tuned,
      score: run.optimized_score,
      color: '#22c55e',
      emphasised: true,
    })
    return out
  }, [run, workflowLabels])

  const suggestions: Suggestion[] = useMemo(() => {
    return (run.suggestions || []).map(s => ({
      severity: s.severity,
      message: s.message,
    }))
  }, [run.suggestions])

  // "Already applied" detection — the run wrote its best_config to
  // Workflow.config_override; once revert has run, previous_override is the
  // null/empty state we restored to. The backend doesn't surface a direct
  // "is this run currently applied?" boolean, so we use the presence of
  // best_config + winner_selection_reason as a proxy. Conservative — a fresh
  // re-run will overwrite this if the user re-applies.
  const isAlreadyApplied = false  // backend doesn't expose this yet; safe default

  const canApply = !!run.best_config && !run.tied_with_baseline
  const canRevert = run.previous_override !== undefined && run.previous_override !== null

  // Trial tapped open in the plain-English explainer modal.
  const [selectedTrial, setSelectedTrial] = useState<WorkflowOptimizationTrial | null>(null)

  return (
    <div style={{ marginTop: 16 }}>
      <QualityComparisonCard
        baselines={baselines}
        variance={run.judge_variance ?? 0}
        defaultBaselineId="default"
        optimizedBaselineId="optimized"
        secondaryBaselineId="no-workflow"
        title="Tuning complete"
      />

      {run.step_breakdown.length > 0 && (
        <details style={{ marginTop: 12 }}>
          <summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 500, color: '#e5e5e5' }}>
            Per-step breakdown ({run.step_breakdown.length} steps)
          </summary>
          <div style={{ marginTop: 8 }}>
            {run.step_breakdown.map((s: WorkflowStepBreakdownEntry) => (
              <div
                key={s.step}
                style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0', fontSize: 12 }}
              >
                <span style={{ width: 140, color: '#bbb' }}>{s.step}</span>
                <div style={{ flex: 1, height: 6, background: '#2e2e2e', borderRadius: 3, overflow: 'hidden' }}>
                  <div
                    style={{
                      width: `${Math.max(0, Math.min(100, s.score))}%`,
                      height: '100%',
                      background: s.score >= 80 ? '#22c55e' : s.score >= 60 ? '#f59e0b' : '#ef4444',
                    }}
                  />
                </div>
                <span style={{ width: 50, textAlign: 'right', color: '#888' }}>
                  {s.score.toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </details>
      )}

      {suggestions.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <SuggestionsList suggestions={suggestions} />
        </div>
      )}

      {/* Trials — each tunes the workflow's steps differently. Tap one for a
          plain-English breakdown of what it changed and how it scored. */}
      {(run.trials || []).length > 0 && (
        <div style={{ marginTop: 12 }}>
          <TrialsTable<WorkflowOptimizationTrial>
            trials={run.trials}
            sortOptions={WORKFLOW_TRIAL_SORT_OPTIONS}
            renderRow={(t) => (
              <TrialRow trial={t} summariseConfig={(c) => summariseWorkflowTrialConfig(c)} />
            )}
            getRowKey={(t) => t.trial_id}
            onRowClick={setSelectedTrial}
            title="Trials — tap any for a plain-English breakdown"
          />
        </div>
      )}

      {/* Plain-English explainer for a tapped trial. */}
      <WorkflowTrialExplainerModal trial={selectedTrial} onClose={() => setSelectedTrial(null)} />

      {Object.keys(run.best_per_step_config || {}).length > 0 && (
        <details style={{ marginTop: 12 }} open={selectedStepIds !== undefined}>
          <summary style={{ cursor: 'pointer', fontSize: 13, fontWeight: 500, color: '#e5e5e5' }}>
            Best configuration
            {selectedStepIds && selectedStepIds.length > 0 && (
              <span style={{ marginLeft: 8, color: '#a78bfa', fontWeight: 400 }}>
                · applying {selectedStepIds.length} of {Object.keys(run.best_per_step_config).length}
              </span>
            )}
          </summary>
          <div style={{ marginTop: 8, fontSize: 12, color: '#ccc', display: 'flex', flexDirection: 'column', gap: 4 }}>
            <div style={{ display: 'flex', gap: 8, marginBottom: 4 }}>
              <button
                type="button"
                onClick={() => onSelectionChange(undefined)}
                style={{
                  padding: '2px 8px', fontSize: 11, fontWeight: 500, fontFamily: 'inherit',
                  color: selectedStepIds === undefined ? '#a78bfa' : '#888',
                  background: 'transparent',
                  border: '1px solid ' + (selectedStepIds === undefined ? 'rgba(124, 58, 237, 0.45)' : '#3a3a3a'),
                  borderRadius: 4, cursor: 'pointer',
                }}
              >
                Apply all
              </button>
              <button
                type="button"
                onClick={() => onSelectionChange([])}
                style={{
                  padding: '2px 8px', fontSize: 11, fontWeight: 500, fontFamily: 'inherit',
                  color: selectedStepIds !== undefined ? '#a78bfa' : '#888',
                  background: 'transparent',
                  border: '1px solid ' + (selectedStepIds !== undefined ? 'rgba(124, 58, 237, 0.45)' : '#3a3a3a'),
                  borderRadius: 4, cursor: 'pointer',
                }}
              >
                Pick steps…
              </button>
            </div>
            {Object.entries(run.best_per_step_config).map(([step, ov]) => {
              const stepSelectable = selectedStepIds !== undefined
              const checked = stepSelectable && selectedStepIds.includes(step)
              return (
                <label
                  key={step}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    padding: '2px 0',
                    cursor: stepSelectable ? 'pointer' : 'default',
                    opacity: stepSelectable ? 1 : 0.85,
                  }}
                >
                  {stepSelectable && (
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => {
                        if (!selectedStepIds) return
                        const next = e.target.checked
                          ? [...selectedStepIds, step]
                          : selectedStepIds.filter(s => s !== step)
                        onSelectionChange(next)
                      }}
                    />
                  )}
                  <strong style={{ color: '#e5e5e5' }}>{step}:</strong> {ov.model ?? '—'}
                  {ov.prompt_variant && ov.prompt_variant !== 'default' && (
                    <span style={{ color: '#888' }}> · {ov.prompt_variant}</span>
                  )}
                </label>
              )
            })}
          </div>
        </details>
      )}

      <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center' }}>
        {canApply && (
          <ApplyBackButton
            canApply={canApply && (selectedStepIds === undefined || selectedStepIds.length > 0)}
            onApply={onApply}
            applying={applying}
            isAlreadyApplied={isAlreadyApplied}
            label={
              selectedStepIds && selectedStepIds.length > 0
                ? `Apply ${selectedStepIds.length} selected step${selectedStepIds.length === 1 ? '' : 's'}`
                : 'Apply optimized settings'
            }
          />
        )}
        {canRevert && (
          <button
            type="button"
            onClick={onRevert}
            disabled={reverting}
            style={{
              padding: '6px 12px', borderRadius: 6,
              background: 'transparent', color: reverting ? '#555' : '#bbb',
              border: '1px solid #3a3a3a',
              fontSize: 12, fontWeight: 500, fontFamily: 'inherit',
              cursor: reverting ? 'wait' : 'pointer',
            }}
          >
            {reverting ? 'Reverting…' : 'Revert'}
          </button>
        )}
      </div>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Adapters
// ---------------------------------------------------------------------------


function runForProgress(
  run: WorkflowOptimizationRun,
): ProgressRunShape<WorkflowOptimizationTrial['config']> {
  return {
    status: run.status,
    phase: run.phase,
    progress_message: run.progress_message,
    current_trial_index: run.current_trial_index,
    total_trials_planned: run.total_trials_planned,
    token_budget: run.token_budget,
    tokens_used: run.tokens_used,
    best_score_so_far: run.best_score_so_far,
    best_config_so_far: run.best_config_so_far,
    trials: run.trials.map(t => ({
      trial_id: t.trial_id,
      config: t.config,
      score: t.score ?? 0,
      status: t.status,
    })),
    cancel_requested: run.cancel_requested,
    started_at: run.started_at,
  }
}


function summariseConfig(config: WorkflowOptimizationTrial['config']): string {
  const overrides: Record<string, WorkflowStepOverride> = config?.step_overrides || {}
  const entries = Object.entries(overrides)
  if (entries.length === 0) return 'default'
  if (entries.length === 1) {
    const [step, ov] = entries[0]
    return `${step}: ${ov.model ?? '—'}${ov.prompt_variant && ov.prompt_variant !== 'default' ? ` · ${ov.prompt_variant}` : ''}`
  }
  // Multi-step trial — summarise as "N steps overridden"
  return `${entries.length} steps overridden`
}


function formatScore(score: number | null): string {
  if (score == null) return '—'
  return `${(score * 100).toFixed(1)}%`
}
