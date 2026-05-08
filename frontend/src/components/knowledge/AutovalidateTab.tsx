import { useCallback, useEffect, useRef, useState } from 'react'
import { Sparkles, Loader2 } from 'lucide-react'
import {
  startKBOptimization,
  getActiveKBOptimization,
  getKBOptimization,
  cancelKBOptimization,
  applyKBOptimization,
  type KBOptimizationRun,
  type StartOptimizationOptions,
} from '../../api/knowledge'
import { AutovalidateModal } from './AutovalidateModal'
import { OptimizationProgress } from './OptimizationProgress'
import { OptimizationResults } from './OptimizationResults'
import { OptimizationHistoryPanel } from './OptimizationHistoryPanel'

interface Props {
  kbUuid: string
  kbReady: boolean
  canManage: boolean
}

const POLL_INTERVAL_MS = 3000

export function AutovalidateTab({ kbUuid, kbReady, canManage }: Props) {
  const [run, setRun] = useState<KBOptimizationRun | null>(null)
  const [showModal, setShowModal] = useState(false)
  const [loading, setLoading] = useState(true)
  const [actionPending, setActionPending] = useState<'cancel' | 'apply' | null>(null)
  const [error, setError] = useState<string | null>(null)
  // When set, we're viewing a *historical* run (not the active/latest). The
  // results view renders read-only so users can't accidentally apply or
  // mutate from a historical context.
  const [viewingPast, setViewingPast] = useState<KBOptimizationRun | null>(null)
  const [viewingPastLoading, setViewingPastLoading] = useState(false)
  const pollRef = useRef<number | null>(null)

  const stopPolling = useCallback(() => {
    if (pollRef.current != null) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const startPolling = useCallback((runUuid: string) => {
    stopPolling()
    pollRef.current = window.setInterval(async () => {
      try {
        const fresh = await getKBOptimization(kbUuid, runUuid)
        setRun(fresh)
        if (fresh.status === 'completed' || fresh.status === 'failed' || fresh.status === 'cancelled') {
          stopPolling()
        }
      } catch (e) {
        console.error('Polling optimization failed', e)
      }
    }, POLL_INTERVAL_MS)
  }, [kbUuid, stopPolling])

  // Initial load: see if there's an active or recent run.
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
          onRunAgain={handleNewRun}
          onSelectPastRun={handleViewPastRun}
        />
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

  // STATE A: idle
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {error && <ErrorBanner message={error} />}
      <IdleHero
        kbReady={kbReady}
        canManage={canManage}
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

function PastRunBanner({ startedAt, onExit }: { startedAt: string | null; onExit: () => void }) {
  const when = startedAt ? new Date(startedAt).toLocaleString() : 'Unknown date'
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '8px 12px',
      backgroundColor: 'rgba(124, 58, 237, 0.10)',
      border: '1px solid rgba(124, 58, 237, 0.35)', borderRadius: 6,
      fontSize: 12, color: '#e5e5e5',
    }}>
      <Sparkles size={13} style={{ color: '#a78bfa', flexShrink: 0 }} />
      <span style={{ flex: 1 }}>
        Viewing past run from <b>{when}</b> — read-only.
      </span>
      <button
        onClick={onExit}
        style={{
          padding: '4px 10px', fontSize: 11, fontWeight: 600, fontFamily: 'inherit',
          color: '#e5e5e5', background: 'transparent',
          border: '1px solid rgba(124, 58, 237, 0.4)', borderRadius: 5,
          cursor: 'pointer',
        }}
      >
        Back to current
      </button>
    </div>
  )
}


function IdleHero({ kbReady, canManage, onStart }: { kbReady: boolean; canManage: boolean; onStart: () => void }) {
  const disabled = !kbReady || !canManage
  const reason = !kbReady ? 'KB is still building' : !canManage ? 'You cannot manage this KB' : null
  return (
    <div style={{
      padding: 18, background: 'linear-gradient(135deg, #1f1f2e 0%, #1a1a1a 100%)',
      border: '1px solid rgba(124, 58, 237, 0.25)', borderRadius: 8,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <Sparkles size={18} style={{ color: '#a78bfa' }} />
        <h3 style={{ margin: 0, fontSize: 15, color: '#fff' }}>Optimize this knowledge base</h3>
      </div>
      <p style={{ margin: '0 0 12px 0', fontSize: 13, color: '#bbb', lineHeight: 1.5 }}>
        Autovalidate sweeps RAG settings — retrieval depth, prompt variants,
        models, and query rewriting — and keeps whichever combination scores
        best on test questions. You'll see the lift over a no-retrieval baseline
        plus suggestions for improving the data itself.
      </p>
      <ul style={{ fontSize: 12, color: '#999', margin: '0 0 14px 0', paddingLeft: 18, lineHeight: 1.7 }}>
        <li>Compares <b>No KB</b> · <b>Default settings</b> · <b>Optimized</b> side-by-side</li>
        <li>Uses an LLM judge to score each configuration on the test set</li>
        <li>Surfaces data-source suggestions when KB coverage is the bottleneck</li>
      </ul>
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
        Autovalidate
      </button>
    </div>
  )
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div style={{
      padding: 10, marginBottom: 10, fontSize: 12,
      color: '#fca5a5', backgroundColor: 'rgba(239, 68, 68, 0.1)',
      border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: 6,
    }}>
      {message}
    </div>
  )
}
