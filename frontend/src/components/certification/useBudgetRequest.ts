import type { CourseRequestPhase } from './CourseRequestStatus'
import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { getBudgetCalculation, getBudgetCapture, getBudgetReview, getBudgetRun, getBudgetScope, saveBudgetWork } from '../../api/budgetWorkflow'
import type { BudgetList, BudgetRequest, BudgetSaved } from '../../types/budgetWorkflow'
import { validBudgetRequest, verifyBudgetResponse, verifyBudgetRun } from './budgetWorkflowState'

export function useBudgetRequest(listing: BudgetList, onSaved: (value: BudgetSaved, action: BudgetRequest['action']) => void, enabled = true) {
  const key = `certification-budget-request:${listing.enrollment_id}:${listing.case.case_sha256}`
  const [pending, setPending] = useState<BudgetRequest | null>(null)
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [blocked, setBlocked] = useState(false)
  const [phase, setPhase] = useState<CourseRequestPhase>(null)
  const [canFinish, setCanFinish] = useState(false), [canDiscard, setCanDiscard] = useState(false)
  const sending = useRef(false), sequence = useRef(0), current = useRef<BudgetRequest | null>(null)
  useEffect(() => {
    if (!enabled) return
    try {
      const value = JSON.parse(sessionStorage.getItem(key) || 'null') as BudgetRequest | null
      if (value && !validBudgetRequest(value, listing.case)) throw new Error('Invalid saved request')
      current.current = value; setPending(value)
    } catch { setBlocked(true); setError('This tab could not restore its pending request. Saved server history remains available. Reload before starting another action.') }
    const counter = sequence
    return () => { counter.current++ }
  }, [key, listing.case, enabled])

  async function act(request?: BudgetRequest, check = false) {
    if (!enabled || sending.current || blocked || (request && current.current) || (!request && !check && !canFinish)) return
    const next = request || current.current
    if (!next || !validBudgetRequest(next, listing.case)) return
    sending.current = true
    const token = ++sequence.current
    let sent = false
    setBusy(true); setPhase(check ? 'checking' : 'sending'); setError(''); setCanFinish(false); setCanDiscard(false)
    try {
      if (!check) { sessionStorage.setItem(key, JSON.stringify(next)); current.current = next; setPending(next) }
      let saved: BudgetSaved
      if (!check) { sent = true; saved = await saveBudgetWork(listing.enrollment_id, next) }
      else if (next.action === 'calculation') saved = await getBudgetCalculation(listing.enrollment_id, next.body.request_id)
      else if (next.action === 'capture') saved = await getBudgetCapture(listing.enrollment_id, next.body.request_id)
      else if (next.action === 'review') saved = await getBudgetReview(listing.enrollment_id, next.body.request_id)
      else {
        if (next.action === 'scope') {
          const scope = await getBudgetScope(listing.enrollment_id, next.body.request_id)
          if (scope.uuid !== next.body.request_id || scope.enrollment_id !== listing.enrollment_id || scope.case_sha256 !== listing.case.case_sha256
            || Object.entries(next.body).some(([field, value]) => scope.submission[field as keyof typeof scope.submission] !== value)) throw new Error('Different scope decision')
        }
        saved = await getBudgetRun(listing.enrollment_id, next.action === 'prepare' ? next.body.request_id : next.body.run_id)
      }
      if (check && next.action === 'execute' && 'state' in saved && saved.state === 'prepared'
        && saved.run_id === next.body.run_id && saved.plan_sha256 === next.body.plan_sha256
        && (saved.scope_decision_id !== next.body.scope_decision_id || saved.scope_decision_sha256 !== next.body.scope_decision_sha256)) {
        verifyBudgetRun(saved, listing)
        if (token !== sequence.current) return
        sessionStorage.removeItem(key); current.current = null; setPending(null)
        setError('This run is still unstarted and its scope choice changed. Inspect the current decision before requesting execution again.')
        onSaved(saved, next.action)
        return
      }
      verifyBudgetResponse(saved, listing, next)
      if (token !== sequence.current) return
      if (check && 'state' in saved && ((next.action === 'execute' && saved.state === 'prepared') || (next.action === 'finalize' && saved.state === 'executing'))) {
        setCanFinish(next.action === 'execute' ? saved.can_execute : saved.can_finalize)
        setError(next.action === 'execute' ? 'The run has not started. Inspect the saved approval, then finish the original request if you still want to run it.' : 'The run has not been finalized. Finish the original request only when every task result is saved.')
        onSaved(saved, next.action)
        return
      }
      sessionStorage.removeItem(key); current.current = null; setPending(null)
      onSaved(saved, next.action)
    } catch (failure) {
      if (token !== sequence.current) return
      if (check && failure instanceof ApiError && failure.status === 404) {
        setCanFinish(true); setCanDiscard(!['execute', 'finalize'].includes(next.action))
        setError('No saved record was found for this request. You can finish the same request with its original details.')
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
  return { pending, busy, phase, error, blocked, canFinish, canDiscard, send: (request: BudgetRequest) => act(request), check: () => act(undefined, true), finish: () => act(), discard }
}
