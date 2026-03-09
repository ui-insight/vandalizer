import { useCallback, useEffect, useRef, useState } from 'react'
import { getBatchStatus, getWorkflowStatus, runWorkflow } from '../api/workflows'
import type { BatchStatus } from '../api/workflows'
import { useWorkspace } from '../contexts/WorkspaceContext'
import type { WorkflowStatus } from '../types/workflow'

export function useWorkflowRunner() {
  const { bumpActivitySignal } = useWorkspace()
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [batchId, setBatchId] = useState<string | null>(null)
  const [status, setStatus] = useState<WorkflowStatus | null>(null)
  const [batchStatus, setBatchStatus] = useState<BatchStatus | null>(null)
  const [running, setRunning] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  const poll = useCallback(async (sid: string) => {
    try {
      const s = await getWorkflowStatus(sid)
      setStatus(s)
      if (s.status === 'completed' || s.status === 'error' || s.status === 'failed') {
        setRunning(false)
        stopPolling()
      }
    } catch {
      // Keep polling on transient errors
    }
  }, [stopPolling])

  const pollBatch = useCallback(async (bid: string) => {
    try {
      const s = await getBatchStatus(bid)
      setBatchStatus(s)
      if (s.status === 'completed' || s.status === 'failed') {
        setRunning(false)
        stopPolling()
      }
    } catch {
      // Keep polling on transient errors
    }
  }, [stopPolling])

  const start = useCallback(async (workflowId: string, documentUuids: string[], model?: string, batchMode?: boolean) => {
    setRunning(true)
    setStatus(null)
    setBatchStatus(null)
    setBatchId(null)
    setSessionId(null)

    const result = await runWorkflow(workflowId, {
      document_uuids: documentUuids,
      model,
      batch_mode: batchMode,
    })
    bumpActivitySignal()

    if (result.batch_id) {
      setBatchId(result.batch_id)
      pollBatch(result.batch_id)
      intervalRef.current = setInterval(() => pollBatch(result.batch_id!), 2000)
    } else if (result.session_id) {
      setSessionId(result.session_id)
      poll(result.session_id)
      intervalRef.current = setInterval(() => poll(result.session_id!), 2000)
    }
  }, [poll, pollBatch, bumpActivitySignal])

  const reset = useCallback(() => {
    setSessionId(null)
    setBatchId(null)
    setStatus(null)
    setBatchStatus(null)
    setRunning(false)
    stopPolling()
  }, [stopPolling])

  // Cleanup on unmount
  useEffect(() => {
    return () => stopPolling()
  }, [stopPolling])

  return { sessionId, batchId, status, batchStatus, running, start, reset }
}
