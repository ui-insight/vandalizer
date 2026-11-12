import { ApiError } from '../api/client'
import { useCallback, useEffect, useRef, useState } from 'react'
import { getActiveKBValidationTask, getKBValidationTask, runKBValidationAsync, type KBValidationMode, type KBValidationResult, type KBValidationTaskStatus } from '../api/knowledge'

type Job = { id: string; kbUuid: string; mode: KBValidationMode; queryUuids?: string[]; skipJudge?: boolean; acknowledged: boolean }
export type ValidationProgress = { phase: 'restoring' | 'starting' | 'queued' | 'running' | 'retrying' | 'connection' | 'unknown' | 'failed' | 'completed'; message: string; delayed?: boolean }

/** Restore server-owned task state before allowing a new check. */
export function useKBValidationRun(kbUuid: string, onCompleted: (uuid: string, result: KBValidationResult) => void) {
  const [job, setJob] = useState<Job | null>(null)
  const jobRef = useRef<Job | null>(null)
  const completedRef = useRef(onCompleted)
  const [restoring, setRestoring] = useState(true)
  const restoringRef = useRef(true)
  const [progress, setProgress] = useState<ValidationProgress | null>({ phase: 'restoring', message: 'Checking for an unfinished validation…' })
  const [retryKey, setRetryKey] = useState(0)
  const [restoreKey, setRestoreKey] = useState(0)
  useEffect(() => { completedRef.current = onCompleted }, [onCompleted])

  const acceptTerminal = useCallback((out: KBValidationTaskStatus) => {
    if (out.status === 'completed' && out.run_uuid && out.result) {
      jobRef.current = null
      setJob(null)
      setProgress({ phase: 'completed', message: 'Check complete. The saved results are shown below.' })
      completedRef.current(out.run_uuid, out.result)
      return true
    }
    if (out.status === 'failed') {
      jobRef.current = null
      setJob(null)
      setProgress({ phase: 'failed', message: out.message || 'This check failed. Review your questions and sources, then start a new check.' })
      return true
    }
    return false
  }, [])

  useEffect(() => {
    let cancelled = false
    restoringRef.current = true
    if (jobRef.current?.kbUuid !== kbUuid) { jobRef.current = null; setJob(null) }
    setRestoring(true)
    void getActiveKBValidationTask(kbUuid).then(out => {
      if (cancelled) return
      if (out.task && !acceptTerminal(out.task)) {
        const next: Job = { id: out.task.task_id, kbUuid, mode: out.task.options.mode || 'judge', queryUuids: out.task.options.query_uuids, skipJudge: out.task.options.skip_judge, acknowledged: true }
        jobRef.current = next
        setJob(next)
        setProgress({ phase: 'queued', message: 'Resuming your existing check…' })
      } else if (!out.task) {
        jobRef.current = null
        setJob(null)
        setProgress(null)
      }
      restoringRef.current = false
      setRestoring(false)
    }).catch(() => {
      if (!cancelled) setProgress({ phase: 'connection', message: 'We could not check for unfinished validations. Reconnect before starting another check.' })
    })
    return () => { cancelled = true }
  }, [kbUuid, restoreKey, acceptTerminal])

  const start = useCallback((mode: KBValidationMode, queryUuids?: string[]) => {
    if (jobRef.current || restoringRef.current) return
    const next = { id: crypto.randomUUID(), kbUuid, mode, queryUuids, acknowledged: false }
    jobRef.current = next
    setProgress({ phase: 'starting', message: 'Submitting this check…' })
    setJob(next)
  }, [kbUuid])
  const retry = useCallback(() => {
    if (jobRef.current) setRetryKey(k => k + 1)
    else setRestoreKey(k => k + 1)
  }, [])

  useEffect(() => {
    if (!job || job.kbUuid !== kbUuid) return
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = async () => {
      try {
        const out = await getKBValidationTask(kbUuid, job.id)
        if (cancelled) return
        if (out.task_id !== job.id) throw new Error('Mismatched task response')
        if (acceptTerminal(out)) return
        setProgress({ phase: out.status === 'completed' ? 'unknown' : out.status,
          message: out.message || 'Waiting for the saved result…', delayed: out.delayed })
      } catch {
        if (cancelled) return
        setProgress({ phase: 'connection', message: 'Status is temporarily unavailable. This check may still be running. Reconnecting will check the same task.' })
      }
      if (!cancelled) timer = setTimeout(() => void poll(), 4000)
    }
    const resume = async () => {
      if (!job.acknowledged) {
        try {
          const out = await runKBValidationAsync(kbUuid, { mode: job.mode, ...(job.queryUuids ? { query_uuids: job.queryUuids } : {}), request_id: job.id })
          if (cancelled) return
          if (out.resumed && out.task_id !== job.id) {
            const next: Job = { id: out.task_id, kbUuid, mode: out.options?.mode || 'judge', queryUuids: out.options?.query_uuids, skipJudge: out.options?.skip_judge, acknowledged: true }
            jobRef.current = next
            setJob(next)
            setProgress({ phase: 'queued', message: 'Another window already started a check. Resuming that check…' })
            return
          }
          if (out.task_id !== job.id) throw new Error('Mismatched task response')
          job.acknowledged = true
        } catch (error) {
          if (cancelled) return
          if (error instanceof ApiError && [400, 422].includes(error.status)) {
            jobRef.current = null
            setJob(null)
            setProgress({ phase: 'failed', message: error.message })
            return
          }
          setProgress({ phase: 'connection', message: 'The start response was not received. Reconnect to recover this same check without submitting a duplicate.' })
          return
        }
      }
      if (!cancelled) await poll()
    }
    void resume()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [job, kbUuid, retryKey, acceptTerminal])

  return { start, retry, running: restoring || job !== null, progress, activeOptions: job ? { mode: job.mode, query_uuids: job.queryUuids, skip_judge: job.skipJudge } : undefined }
}
