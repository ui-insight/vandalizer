import { useCallback, useEffect, useRef, useState } from 'react'
import { getWorkflowStatus, runWorkflow } from '../api/workflows'
import type { WorkflowStatus } from '../types/workflow'

export function useWorkflowRunner() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [status, setStatus] = useState<WorkflowStatus | null>(null)
  const [running, setRunning] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const poll = useCallback(async (sid: string) => {
    try {
      const s = await getWorkflowStatus(sid)
      setStatus(s)
      if (s.status === 'completed' || s.status === 'error' || s.status === 'failed') {
        setRunning(false)
        if (intervalRef.current) {
          clearInterval(intervalRef.current)
          intervalRef.current = null
        }
      }
    } catch {
      // Keep polling on transient errors
    }
  }, [])

  const start = useCallback(async (workflowId: string, documentUuids: string[], model?: string) => {
    setRunning(true)
    setStatus(null)
    const { session_id } = await runWorkflow(workflowId, { document_uuids: documentUuids, model })
    setSessionId(session_id)
    // Start polling
    intervalRef.current = setInterval(() => poll(session_id), 1500)
    // Initial poll
    poll(session_id)
  }, [poll])

  const reset = useCallback(() => {
    setSessionId(null)
    setStatus(null)
    setRunning(false)
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  return { sessionId, status, running, start, reset }
}
