import { useCallback, useEffect, useState } from 'react'
import { getWorkflowHistory, getWorkflowStatus, type RunHistoryEntry } from '../api/workflows'
import type { WorkflowStatus } from '../types/workflow'

/** Read persisted history on every editor mount, including after a refresh. */
export function useLastWorkflowRun(workflowId: string | null, shareToken?: string) {
  const [lastRun, setLastRun] = useState<RunHistoryEntry | null>(null)
  const [status, setStatus] = useState<WorkflowStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const retry = useCallback(() => setAttempt(n => n + 1), [])
  useEffect(() => {
    let cancelled = false
    setLastRun(null); setStatus(null); setError(null)
    if (!workflowId) return
    void (async () => {
      try {
        const { runs } = await getWorkflowHistory(workflowId, 1)
        if (cancelled) return
        const latest = runs.find(run => run.session_id) ?? null
        setLastRun(latest)
        if (!latest?.session_id) return
        // A missing preview must not hide the action to reopen the saved run.
        const detail = await getWorkflowStatus(latest.session_id, shareToken)
        if (!cancelled) setStatus(detail)
      } catch {
        if (!cancelled) setError('Could not load your last run.')
      }
    })()
    return () => { cancelled = true }
  }, [workflowId, shareToken, attempt])
  return { lastRun, status, error, retry }
}
