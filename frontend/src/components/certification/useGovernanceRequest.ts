import type { CourseRequestPhase } from './CourseRequestStatus'
import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { getGovernanceRecord, governanceActionKind, saveGovernanceWork } from '../../api/governanceAssessment'
import type { GovernanceList, GovernanceRequest, GovernanceView } from '../../types/governanceAssessment'
import { validGovernanceRequest, verifyGovernanceResponse, verifyGovernanceView } from './governanceAssessmentState'

export function useGovernanceRequest(listing: GovernanceList, onSaved: (value: GovernanceView) => void, enabled = true) {
  const key = `certification-governance-request:${listing.enrollment_id}:${listing.case.case_sha256}`
  const [pending, setPending] = useState<GovernanceRequest | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [blocked, setBlocked] = useState(false), [canFinish, setCanFinish] = useState(false), [canDiscard, setCanDiscard] = useState(false)
  const [phase, setPhase] = useState<CourseRequestPhase>(null)
  const sending = useRef(false), sequence = useRef(0), current = useRef<GovernanceRequest | null>(null)
  useEffect(() => {
    if (!enabled) return
    try {
      const value = JSON.parse(sessionStorage.getItem(key) || 'null') as GovernanceRequest | null
      if (value && !validGovernanceRequest(value, listing.case)) throw new Error('Invalid saved request')
      current.current = value; setPending(value)
    } catch { setBlocked(true); setError('This tab could not restore its pending capstone request. Server history remains available. Reload before starting another action.') }
    const counter = sequence
    return () => { counter.current++ }
  }, [key, listing.case, enabled])
  async function act(request?: GovernanceRequest, check = false) {
    if (!enabled || sending.current || blocked || request && current.current || !request && !check && !canFinish) return
    const next = request || current.current
    if (!next || !validGovernanceRequest(next, listing.case)) return
    sending.current = true
    const token = ++sequence.current
    let sent = false
    setBusy(true); setPhase(check ? 'checking' : 'sending'); setError(''); setCanFinish(false); setCanDiscard(false)
    try {
      if (!check) { sessionStorage.setItem(key, JSON.stringify(next)); current.current = next; setPending(next) }
      const value = check ? await getGovernanceRecord(listing.enrollment_id, governanceActionKind(next.action), 'request_id' in next.body ? next.body.request_id : next.body.run_id)
        : await (async () => { sent = true; return saveGovernanceWork(listing.enrollment_id, next) })()
      if (check && next.action === 'execute' && value.kind === 'run' && value.value.state === 'prepared'
        && value.value.run_id === next.body.run_id && value.value.plan_sha256 === next.body.plan_sha256
        && (value.value.scope_decision_id !== next.body.scope_decision_id || value.value.scope_decision_sha256 !== next.body.scope_decision_sha256)) {
        verifyGovernanceView(value, listing)
        if (token !== sequence.current) return
        sessionStorage.removeItem(key); current.current = null; setPending(null)
        setError('This extraction is still unstarted and its approval changed. Inspect the current choice before requesting execution again.'); onSaved(value); return
      }
      verifyGovernanceResponse(value, listing, next)
      if (token !== sequence.current) return
      if (check && value.kind === 'run' && (next.action === 'execute' && value.value.state === 'prepared' || next.action === 'finalize' && value.value.state === 'executing')) {
        setCanFinish(next.action === 'execute' ? value.value.can_execute : value.value.can_finalize)
        setError('The original action has not finished. Inspect the saved approval and evidence before explicitly finishing this same request.'); onSaved(value); return
      }
      sessionStorage.removeItem(key); current.current = null; setPending(null); onSaved(value)
    } catch (failure) {
      if (token !== sequence.current) return
      if (check && failure instanceof ApiError && failure.status === 404) {
        setCanFinish(true); setCanDiscard(!['execute', 'finalize'].includes(next.action)); setError('No saved record was found. You may finish the same request with its original details.')
      } else if (sent && failure instanceof ApiError && failure.status === 422) {
        sessionStorage.removeItem(key); current.current = null; setPending(null); setError('The request was rejected before saving. Check the required fields and try again.')
      } else if (!check && !sent) setError('This tab could not preserve the request. Allow session storage before continuing; no request was sent.')
      else setError(`${failure instanceof ApiError && failure.status === 409 ? failure.message + '. ' : ''}We could not confirm the saved state. Check the original pending request before making changes; checking only reads saved work.`)
    } finally { sending.current = false; if (token === sequence.current) { setBusy(false); setPhase(null) } }
  }
  function discard() {
    if (!canDiscard || sending.current) return
    try { sessionStorage.removeItem(key); current.current = null; setPending(null); setCanDiscard(false); setCanFinish(false); setError('') }
    catch { setError('This tab could not clear the unsaved request. Reload before changing it.') }
  }
  return { pending, busy, phase, error, blocked, canFinish, canDiscard, send: (request: GovernanceRequest) => act(request), check: () => act(undefined, true), finish: () => act(), discard }
}
