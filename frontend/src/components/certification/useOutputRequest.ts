import type { CourseRequestPhase } from './CourseRequestStatus'
import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { getOutputCapture, getOutputInspection, getOutputHandoff, getOutputReview, getOutputRun, getOutputScope, saveOutputWork } from '../../api/outputWorkflow'
import type { OutputList, OutputRequest, OutputSaved } from '../../types/outputWorkflow'
import { validOutputRequest, verifyOutputResponse, verifyOutputRun } from './outputWorkflowState'

export function useOutputRequest(listing: OutputList, onSaved: (value: OutputSaved, action: OutputRequest['action']) => void, enabled = true) {
  const key = `certification-output-request:${listing.enrollment_id}:${listing.case.case_sha256}`
  const [pending, setPending] = useState<OutputRequest | null>(null)
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [blocked, setBlocked] = useState(false)
  const [phase, setPhase] = useState<CourseRequestPhase>(null)
  const [canFinish, setCanFinish] = useState(false), [canDiscard, setCanDiscard] = useState(false)
  const sending = useRef(false), sequence = useRef(0), current = useRef<OutputRequest | null>(null)
  useEffect(() => {
    if (!enabled) return
    try {
      const value = JSON.parse(sessionStorage.getItem(key) || 'null') as OutputRequest | null
      if (value && !validOutputRequest(value, listing.case)) throw new Error('Invalid saved request')
      current.current = value; setPending(value)
    } catch { setBlocked(true); setError('This tab could not restore its pending request. Saved server history remains available. Reload before starting another action.') }
    const counter = sequence
    return () => { counter.current++ }
  }, [key, listing.case, enabled])

  async function act(request?: OutputRequest, check = false) {
    if (!enabled || sending.current || blocked || (request && current.current) || (!request && !check && !canFinish)) return
    const next = request || current.current
    if (!next || !validOutputRequest(next, listing.case)) return
    sending.current = true
    const token = ++sequence.current
    let sent = false
    setBusy(true); setPhase(check ? 'checking' : 'sending'); setError(''); setCanFinish(false); setCanDiscard(false)
    try {
      if (!check) { sessionStorage.setItem(key, JSON.stringify(next)); current.current = next; setPending(next) }
      let saved: OutputSaved
      if (!check) { sent = true; saved = await saveOutputWork(listing.enrollment_id, next) }
      else if (next.action === 'capture') saved = await getOutputCapture(listing.enrollment_id, next.body.request_id)
      else if (next.action === 'inspection') saved = await getOutputInspection(listing.enrollment_id, next.body.request_id)
      else if (next.action === 'handoff') saved = await getOutputHandoff(listing.enrollment_id, next.body.request_id)
      else if (next.action === 'review') saved = await getOutputReview(listing.enrollment_id, next.body.request_id)
      else {
        if (next.action === 'scope') {
          const scope = await getOutputScope(listing.enrollment_id, next.body.request_id)
          if (scope.uuid !== next.body.request_id || scope.enrollment_id !== listing.enrollment_id || scope.case_sha256 !== listing.case.case_sha256
            || Object.entries(next.body).some(([field, value]) => scope.submission[field as keyof typeof scope.submission] !== value)) throw new Error('Different scope decision')
        }
        saved = await getOutputRun(listing.enrollment_id, next.action === 'prepare' ? next.body.request_id : next.body.run_id)
      }
      if (check && next.action === 'execute' && 'state' in saved && saved.state === 'prepared'
        && saved.run_id === next.body.run_id && saved.plan_sha256 === next.body.plan_sha256
        && (saved.scope_decision_id !== next.body.scope_decision_id || saved.scope_decision_sha256 !== next.body.scope_decision_sha256)) {
        verifyOutputRun(saved, listing)
        if (token !== sequence.current) return
        sessionStorage.removeItem(key); current.current = null; setPending(null)
        setError('This run is still unstarted and its scope choice changed. Inspect the current decision before requesting execution again.')
        onSaved(saved, next.action)
        return
      }
      verifyOutputResponse(saved, listing, next)
      if (token !== sequence.current) return
      if (check && 'state' in saved && ((next.action === 'execute' && saved.state === 'prepared') || (next.action === 'finalize' && saved.state === 'executing'))) {
        setCanFinish(next.action === 'execute' ? saved.can_execute : saved.can_finalize)
        setError(next.action === 'execute' ? 'The run has not started. Inspect the saved approval, then finish the original request if you still want to run it.' : 'The run has not been finalized. Finish the original request only when every stage result is saved.')
        onSaved(saved, next.action)
        return
      }
      sessionStorage.removeItem(key); current.current = null; setPending(null)
      onSaved(saved, next.action)
    } catch (failure) {
      if (token !== sequence.current) return
      if (check && failure instanceof ApiError && failure.status === 404) {
        if (next.action === 'handoff') {
          // A missing receipt can follow a durable claim. Never discard that
          // identity until a read proves this request did not claim the action.
          try {
            const run = verifyOutputRun(await getOutputRun(listing.enrollment_id, next.body.run_id), listing)
            if (token !== sequence.current) return
            const claimed = next.body.action === 'attempt' ? run.handoff_request_id : run.retry_request_id
            const originalClaim = claimed === next.body.request_id
            setCanDiscard(!originalClaim)
            setCanFinish(originalClaim || !claimed && !run.handoff_claimed && run.release_decision?.uuid === next.body.review_id && run.release_decision.review_sha256 === next.body.review_sha256)
            setError(originalClaim ? 'The original handoff is claimed but its receipt is not yet saved. Finish only this original request; do not regenerate files.' : 'No receipt exists for this request. Inspect the current release and original handoff before continuing; this unclaimed request can be discarded.')
          } catch { if (token === sequence.current) setError('The handoff receipt and claim could not both be checked. Keep the original request and try reading again.') }
        } else {
          setCanFinish(true); setCanDiscard(!['execute', 'finalize'].includes(next.action))
          setError('No saved record was found for this request. You can finish the same request with its original details.')
        }
      } else if (sent && failure instanceof ApiError && failure.status === 422) {
        sessionStorage.removeItem(key); current.current = null; setPending(null)
        setError('The request was rejected before saving. Check the required fields and try again.')
      } else if (!check && !sent) setError('This tab could not preserve the request. Allow session storage before continuing; no request was sent.')
      else setError(`${failure instanceof ApiError && failure.status === 409 ? failure.message + '. ' : ''}We could not confirm the saved state. Check the pending request before making changes. Checking never runs or grades work.`)
    } finally { sending.current = false; if (token === sequence.current) { setBusy(false); setPhase(null) } }
  }
  function discard() {
    if (!canDiscard || sending.current) return
    try { sessionStorage.removeItem(key); current.current = null; setPending(null); setCanDiscard(false); setCanFinish(false); setError('') }
    catch { setError('The tab could not clear its unsaved request. Reload before changing the request.') }
  }
  return { pending, busy, phase, error, blocked, canFinish, canDiscard, send: (request: OutputRequest) => act(request), check: () => act(undefined, true), finish: () => act(), discard }
}
