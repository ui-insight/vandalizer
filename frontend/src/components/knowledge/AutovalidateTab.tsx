import { useCallback, useEffect, useState } from 'react'
import { Sparkles, Loader2 } from 'lucide-react'
import {
  startKBOptimization,
  getActiveKBOptimization,
  getKBOptimization,
  listKBOptimizationHistory,
  cancelKBOptimization,
  applyKBOptimization,
  revertKBOptimization,
  getKBFeedbackImpact,
  type KBFeedbackImpact,
  type KBOptimizationRun,
  type StartOptimizationOptions,
} from '../../api/knowledge'
import { AutovalidateModal } from './AutovalidateModal'
import { OptimizationProgress } from './OptimizationProgress'
import { OptimizationResults } from './OptimizationResults'
import { OptimizationHistoryPanel } from './OptimizationHistoryPanel'
import { ErrorBanner, PastRunBanner } from '../shared/RunBanners'
import { useIntervalPoll } from '../shared/hooks/useIntervalPoll'
import { WhenToRunDisclosure } from '../shared/WhenToRunDisclosure'

interface Props {
  kbUuid: string
  kbReady: boolean
  canManage: boolean
  /** Total test queries this KB has — used to detect cold-start (0 queries)
   * so the idle hero can show an onboarding checklist. */
  queriesCount?: number
  /** Optional: lets the tuning wizard route to the Test Queries tab when the
   * user wants to review or write their own questions instead of using the
   * auto-generated set. */
  onSwitchToQueries?: () => void
}

const POLL_INTERVAL_MS = 3000

export function AutovalidateTab({ kbUuid, kbReady, canManage, queriesCount, onSwitchToQueries }: Props) {
  const [run, setRun] = useState<KBOptimizationRun | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [loading, setLoading] = useState(true)
  const [actionPending, setActionPending] = useState<'cancel' | 'apply' | 'revert' | null>(null)
  const [error, setError] = useState<string | null>(null)
  // When set, we're viewing a *historical* run (not the active/latest). The
  // results view renders read-only so users can't accidentally apply or
  // mutate from a historical context.
  const [viewingPast, setViewingPast] = useState<KBOptimizationRun | null>(null)
  const [viewingPastLoading, setViewingPastLoading] = useState(false)

  const poll = useIntervalPoll<KBOptimizationRun>()
  const { stop: stopPolling } = poll

  const startPolling = useCallback((runUuid: string) => {
    poll.start({
      fetch: () => getKBOptimization(kbUuid, runUuid),
      intervalMs: POLL_INTERVAL_MS,
      isTerminal: (r) => r.status === 'completed' || r.status === 'failed' || r.status === 'cancelled',
      onUpdate: setRun,
      onError: (e) => console.error('Polling optimization failed', e),
    })
  }, [kbUuid, poll])

  // Initial load: see if there's an active or recent run.
  //
  // This tab unmounts when the user switches to another validation tab and
  // remounts on return, so local `run` state alone can't survive a tab switch
  // (or a page reload). We restore from the server here: first any in-flight
  // run, and failing that the most recent completed/failed/cancelled run — so
  // a finished tuning result keeps showing instead of dropping back to the
  // "Start tuning" idle hero.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    ;(async () => {
      try {
        const out = await getActiveKBOptimization(kbUuid)
        if (cancelled) return
        if (out.run) {
          setRun(out.run)
          if (out.run.status === 'queued' || out.run.status === 'running') {
            startPolling(out.run.uuid)
          }
          return
        }
        // No active run — fall back to the latest run from history so a
        // completed result persists across tab switches and reloads. History
        // summaries omit per-trial detail, so fetch the full run to render.
        const history = await listKBOptimizationHistory(kbUuid, { limit: 1 })
        if (cancelled) return
        const latest = history.items[0]
        if (latest) {
          const full = await getKBOptimization(kbUuid, latest.uuid)
          if (cancelled) return
          setRun(full)
        }
      } catch (e) {
        if (!cancelled) console.error('getActiveKBOptimization failed', e)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true; stopPolling() }
  }, [kbUuid, startPolling, stopPolling])

  const handleStart = async (opts: StartOptimizationOptions) => {
    setShowModal(false)
    setError(null)
    try {
      const { run_uuid } = await startKBOptimization(kbUuid, opts)
      // Immediately seed a placeholder run so the UI flips into running state.
      const seed: KBOptimizationRun = {
        uuid: run_uuid, kb_uuid: kbUuid, status: 'queued', phase: 'queued',
        progress_message: 'Queued…',
        current_trial_index: 0, total_trials_planned: 0,
        best_score_so_far: null, best_config_so_far: null,
        token_budget: opts.token_budget, tokens_used: 0,
        estimated_cost_usd: null, actual_cost_usd: null,
        baseline_no_kb_score: null, baseline_default_score: null,
        optimized_score: null, judge_variance: null, judge_model: null,
        best_config: null, trials: [], data_source_suggestions: [],
        options: opts as unknown as Record<string, unknown>,
        error_message: null,
        started_at: new Date().toISOString(), completed_at: null,
        cancel_requested: false,
      }
      setRun(seed)
      startPolling(run_uuid)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const handleCancel = async () => {
    if (!run) return
    setActionPending('cancel')
    try {
      await cancelKBOptimization(kbUuid, run.uuid)
      const fresh = await getKBOptimization(kbUuid, run.uuid)
      setRun(fresh)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setActionPending(null)
    }
  }

  const handleApply = async () => {
    if (!run) return
    setActionPending('apply')
    try {
      await applyKBOptimization(kbUuid, run.uuid)
      // Refresh so the UI flips to "applied" state with the revert button.
      const fresh = await getKBOptimization(kbUuid, run.uuid)
      setRun(fresh)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setActionPending(null)
    }
  }

  const handleRevert = async () => {
    if (!run) return
    setActionPending('revert')
    try {
      await revertKBOptimization(kbUuid, run.uuid)
      const fresh = await getKBOptimization(kbUuid, run.uuid)
      setRun(fresh)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setActionPending(null)
    }
  }

  const handleNewRun = () => {
    setRun(null)
    setViewingPast(null)
    setShowModal(true)
  }

  const handleViewPastRun = async (runUuid: string) => {
    setViewingPastLoading(true)
    setError(null)
    try {
      const past = await getKBOptimization(kbUuid, runUuid)
      setViewingPast(past)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setViewingPastLoading(false)
    }
  }

  const handleExitPastRunView = () => setViewingPast(null)

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 24, color: '#888' }}>
        <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />
      </div>
    )
  }

  // VIEWING A PAST RUN: read-only view, regardless of current state.
  if (viewingPast) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {error && <ErrorBanner message={error} />}
        <PastRunBanner
          startedAt={viewingPast.started_at}
          onExit={handleExitPastRunView}
        />
        <OptimizationResults
          run={viewingPast}
          canManage={false}            // read-only
          onApply={() => { /* no-op */ }}
          applying={false}
          onRunAgain={handleNewRun}
        />
      </div>
    )
  }

  if (viewingPastLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 24, color: '#888' }}>
        <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} />
      </div>
    )
  }

  // STATE B: a run is in flight
  if (run && (run.status === 'queued' || run.status === 'running')) {
    return (
      <div>
        {error && <ErrorBanner message={error} />}
        <OptimizationProgress
          run={run}
          onCancel={handleCancel}
          cancelling={actionPending === 'cancel'}
        />
      </div>
    )
  }

  // STATE C: a run has finished
  if (run && (run.status === 'completed' || run.status === 'failed' || run.status === 'cancelled')) {
    return (
      <div>
        {error && <ErrorBanner message={error} />}
        <OptimizationResults
          run={run}
          canManage={canManage}
          onApply={handleApply}
          applying={actionPending === 'apply'}
          onRevert={handleRevert}
          reverting={actionPending === 'revert'}
          onRunAgain={handleNewRun}
          onSelectPastRun={handleViewPastRun}
        />
        {showModal && (
          <AutovalidateModal
            kbUuid={kbUuid}
            onConfirm={handleStart}
            onClose={() => setShowModal(false)}
            onSwitchToQueries={onSwitchToQueries}
          />
        )}
      </div>
    )
  }

  // STATE A: idle
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {error && <ErrorBanner message={error} />}
      <IdleHero
        kbUuid={kbUuid}
        kbReady={kbReady}
        canManage={canManage}
        coldStart={queriesCount === 0}
        onStart={() => setShowModal(true)}
      />
      {/* Surface past runs even before any new run is kicked off, so the user
          can revisit a previous optimization's results. */}
      <OptimizationHistoryPanel kbUuid={kbUuid} onSelect={handleViewPastRun} />
      {showModal && (
        <AutovalidateModal
          kbUuid={kbUuid}
          onConfirm={handleStart}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  )
}

/** Surfaces a single line of downstream impact evidence above the bullets:
 * "Since you tuned this KB, thumbs-up rate is +X% (Y→Z%, n=N)." Renders
 * nothing when the post-apply sample is too small (n_after < 10) or there's
 * no apply timestamp yet — the bar for showing a number must be high so the
 * Idle hero never advertises a stat the user can't trust. */
function FeedbackImpactCallout({ impact }: { impact: KBFeedbackImpact | null }) {
  if (!impact || !impact.applied_at) return null
  if (impact.n_after < 10) return null
  if (impact.thumbs_up_rate_after == null) return null
  const after = impact.thumbs_up_rate_after
  const before = impact.thumbs_up_rate_before
  if (before == null || impact.n_before < 5) {
    // We can still show "Since tuning, X% of chats answered using this KB got
    // thumbs-up (n=N)" — useful even without a before/after split.
    return (
      <div style={{
        margin: '8px 0 12px 0', padding: '8px 10px',
        backgroundColor: 'rgba(34, 197, 94, 0.06)',
        border: '1px solid rgba(34, 197, 94, 0.22)', borderRadius: 6,
        fontSize: 12, color: '#bbf7d0',
      }}>
        Since you tuned this KB, <b>{(after * 100).toFixed(0)}%</b> of chats grounded in it
        got a thumbs-up <span style={{ color: '#888' }}>(n={impact.n_after} ratings)</span>.
      </div>
    )
  }
  const deltaPts = (after - before) * 100
  const positive = deltaPts >= 0
  return (
    <div style={{
      margin: '8px 0 12px 0', padding: '8px 10px',
      backgroundColor: positive ? 'rgba(34, 197, 94, 0.06)' : 'rgba(245, 158, 11, 0.06)',
      border: '1px solid ' + (positive ? 'rgba(34, 197, 94, 0.22)' : 'rgba(245, 158, 11, 0.25)'),
      borderRadius: 6, fontSize: 12, color: positive ? '#bbf7d0' : '#fde68a',
    }}>
      Since you tuned this KB, chat thumbs-up rate is{' '}
      <b>{positive ? '+' : ''}{deltaPts.toFixed(0)}pts</b>
      {' '}({(before * 100).toFixed(0)}% → {(after * 100).toFixed(0)}%,{' '}
      <span style={{ color: '#888' }}>n={impact.n_before}→{impact.n_after} ratings</span>).
    </div>
  )
}

function IdleHero({
  kbUuid, kbReady, canManage, coldStart, onStart,
}: { kbUuid: string; kbReady: boolean; canManage: boolean; coldStart?: boolean; onStart: () => void }) {
  const disabled = !kbReady || !canManage
  const reason = !kbReady ? 'KB is still building' : !canManage ? 'You cannot manage this KB' : null

  // Fetch downstream impact (chat thumbs-up rate before/after the most recent
  // applied optimization) so we can show evidence the tuning actually helped
  // real chat users — not just the optimizer's own score. Gated client-side
  // on n_after >= 10 so we never render an unreliable callout.
  const [impact, setImpact] = useState<KBFeedbackImpact | null>(null)
  useEffect(() => {
    let cancelled = false
    getKBFeedbackImpact(kbUuid)
      .then(r => { if (!cancelled) setImpact(r) })
      .catch(() => { /* downstream-impact is optional polish — silent on failure */ })
    return () => { cancelled = true }
  }, [kbUuid])

  return (
    <div style={{
      padding: 18, background: 'linear-gradient(135deg, #1f1f2e 0%, #1a1a1a 100%)',
      border: '1px solid rgba(124, 58, 237, 0.25)', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <Sparkles size={18} style={{ color: '#a78bfa' }} />
        <h3 style={{ margin: 0, fontSize: 15, color: '#fff' }}>Get a quality score for this KB — and a one-click recipe to improve it</h3>
      </div>
      <FeedbackImpactCallout impact={impact} />
      <p style={{ margin: '0 0 12px 0', fontSize: 13, color: '#bbb', lineHeight: 1.5 }}>
        Typically <b>$1–$5</b> and <b>10–20 minutes</b>. We test your KB against
        expected answers, try dozens of retrieval setups, and recommend the
        best. Nothing changes until you click Apply.
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
            <li>We'll write test questions from your documents</li>
            <li>You'll review them before anything else runs</li>
            <li>We try many setups and recommend the best — you decide whether to apply</li>
          </ol>
        </div>
      )}
      <ul style={{ fontSize: 12, color: '#999', margin: '0 0 10px 0', paddingLeft: 18, lineHeight: 1.7 }}>
        <li>See how much your knowledge base actually helps vs. asking the model directly</li>
        <li>Get a recommended setup with one-click apply</li>
        <li>Find out which documents are pulling weight and which aren't</li>
      </ul>
      <WhenToRunDisclosure kind="kb" />
      <button
        onClick={onStart}
        disabled={disabled}
        title={reason || ''}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 6,
          padding: '8px 16px', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
          color: disabled ? '#555' : '#fff',
          background: disabled ? '#222' : 'linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)',
          border: '1px solid ' + (disabled ? '#333' : '#7c3aed'),
          borderRadius: 6, cursor: disabled ? 'not-allowed' : 'pointer',
        }}
      >
        <Sparkles size={14} />
        Start tuning
      </button>
    </div>
  )
}

