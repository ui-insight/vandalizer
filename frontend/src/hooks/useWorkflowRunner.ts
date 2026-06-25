import { useCallback, useEffect, useRef, useState } from 'react'
import { cancelWorkflow, getBatchStatus, getWorkflowStatus, runWorkflow } from '../api/workflows'
import type { BatchStatus } from '../api/workflows'
import { useWorkspace } from '../contexts/WorkspaceContext'
import type { WorkflowStatus } from '../types/workflow'

export function useWorkflowRunner() {
  // openWorkflowShareToken is set when the open workflow was reached via a share
  // link. Threading it through run/poll/cancel lets a recipient who isn't on the
  // owner's team run the workflow (against their own docs) and poll its status —
  // without it, every execution call would 404 with "Workflow not found".
  const { bumpActivitySignal, openWorkflowShareToken } = useWorkspace()
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [batchId, setBatchId] = useState<string | null>(null)
  const [status, setStatus] = useState<WorkflowStatus | null>(null)
  const [batchStatus, setBatchStatus] = useState<BatchStatus | null>(null)
  const [running, setRunning] = useState(false)
  const [cancelling, setCancelling] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  const shareToken = openWorkflowShareToken ?? undefined

  const poll = useCallback(async (sid: string) => {
    try {
      const s = await getWorkflowStatus(sid, shareToken)
      setStatus(s)
      const terminal = s.status === 'completed' || s.status === 'error' || s.status === 'failed' || s.status === 'canceled'
      const paused = s.status === 'pending_approval'
      setRunning(!terminal && !paused)
      if (terminal) stopPolling()
    } catch {
      // Keep polling on transient errors
    }
  }, [stopPolling, shareToken])

  const pollBatch = useCallback(async (bid: string) => {
    try {
      const s = await getBatchStatus(bid, shareToken)
      setBatchStatus(s)
      if (s.status === 'completed' || s.status === 'failed') {
        setRunning(false)
        stopPolling()
      }
    } catch {
      // Keep polling on transient errors
    }
  }, [stopPolling, shareToken])

  const start = useCallback(async (workflowId: string, documentUuids: string[], model?: string, batchMode?: boolean) => {
    setRunning(true)
    setStatus(null)
    setBatchStatus(null)
    setBatchId(null)
    setSessionId(null)

    let result: Awaited<ReturnType<typeof runWorkflow>>
    try {
      result = await runWorkflow(workflowId, {
        document_uuids: documentUuids,
        model,
        batch_mode: batchMode,
      }, shareToken)
    } catch (err) {
      setRunning(false)
      throw err
    }
    bumpActivitySignal()

    if (result.batch_id) {
      setBatchId(result.batch_id)
      pollBatch(result.batch_id)
      intervalRef.current = setInterval(() => pollBatch(result.batch_id!), 2000)
    } else if (result.session_id) {
      setSessionId(result.session_id)
      poll(result.session_id)
      intervalRef.current = setInterval(() => poll(result.session_id!), 2000)
    } else {
      setRunning(false)
    }
  }, [poll, pollBatch, bumpActivitySignal, shareToken])

  // Stop an in-flight single run. Batch runs are not cancellable yet, so this
  // no-ops when only a batch is active. After the request returns, poll once so
  // the UI flips to "canceled" immediately rather than waiting for the next tick.
  const stop = useCallback(async () => {
    if (!sessionId || batchId) return
    setCancelling(true)
    try {
      await cancelWorkflow(sessionId, shareToken)
      await poll(sessionId)
    } catch {
      // Leave the run as-is on failure; the poller keeps the UI honest.
    } finally {
      setCancelling(false)
    }
  }, [sessionId, batchId, poll, shareToken])

  const loadSession = useCallback(async (sid: string) => {
    stopPolling()
    setSessionId(sid)
    setBatchId(null)
    setBatchStatus(null)
    try {
      const s = await getWorkflowStatus(sid, shareToken)
      setStatus(s)
      const isTerminal = s.status === 'completed' || s.status === 'error' || s.status === 'failed' || s.status === 'canceled'
      const isPaused = s.status === 'pending_approval'
      setRunning(!isTerminal && !isPaused)
      if (!isTerminal) {
        intervalRef.current = setInterval(() => poll(sid), 2000)
      }
    } catch {
      setStatus(null)
      setRunning(false)
    }
  }, [poll, stopPolling, shareToken])

  const reset = useCallback(() => {
    setSessionId(null)
    setBatchId(null)
    setStatus(null)
    setBatchStatus(null)
    setRunning(false)
    setCancelling(false)
    stopPolling()
  }, [stopPolling])

  // Cleanup on unmount
  useEffect(() => {
    return () => stopPolling()
  }, [stopPolling])

  return { sessionId, batchId, status, batchStatus, running, cancelling, start, stop, loadSession, reset }
}
