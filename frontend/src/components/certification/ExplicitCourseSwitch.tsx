import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { activateUpgrade, choiceDigest, choiceId, getActivation, getSavedSelection, selectSavedCourse } from '../../api/courseChoices'
import type { ActivationRequest, SavedChoiceRequest, SelectionResult } from '../../api/courseChoices'

export const choiceButton = 'min-h-11 min-w-0 max-w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-left text-sm font-medium text-gray-900 [overflow-wrap:anywhere] disabled:opacity-50'

export function ExplicitCourseSwitch({ request, sourceId, targetVersion, targetManifest, targetId, label, enabled = true, onRefreshCourse }: {
  request: ActivationRequest | SavedChoiceRequest; sourceId: string; targetVersion: string; targetManifest: string
  targetId?: string; label: string; enabled?: boolean; onRefreshCourse: () => Promise<void>
}) {
  const generation = useRef(0)
  const notice = useRef<HTMLDivElement>(null)
  const [phase, setPhase] = useState<'ready' | 'uncertain' | 'prepared' | 'changed' | 'saved'>('ready')
  const [busy, setBusy] = useState(false)
  const [activity, setActivity] = useState('')
  const [message, setMessage] = useState('')
  useEffect(() => () => { ++generation.current }, [request.request_id])
  const upgrade = 'decision_id' in request
  function verify(result: SelectionResult) {
    const receipt = result.receipt
    if (!receipt || receipt.request_id !== request.request_id || receipt.source_enrollment_id !== sourceId
      || receipt.target_course_version !== targetVersion || receipt.target_manifest_sha256 !== targetManifest
      || !choiceId(receipt.target_enrollment_id) || (targetId && receipt.target_enrollment_id !== targetId)
      || !choiceDigest(receipt.receipt_sha256) || receipt.histories_preserved !== true || receipt.credit_transferred !== false
      || receipt.kind !== (upgrade ? 'optional_upgrade_selection.1' : 'saved_course_selection.1')
      || receipt.action !== (upgrade ? 'activate_optional_upgrade' : request.action)
      || typeof result.confirmation_pending !== 'boolean'
      || !(result.current_enrollment_id === null || choiceId(result.current_enrollment_id))) throw new Error('Course receipt changed')
    setPhase('saved')
    setMessage(result.confirmation_pending ? 'Your course choice was saved and needs confirmation. Refresh your course to finish confirming it.'
      : 'Your course choice has a saved receipt. Refresh your course to load your current selection and continue learning.')
  }
  async function run(read: boolean) {
    const token = ++generation.current
    setBusy(true); setMessage('')
    setActivity(read ? 'Checking the saved course switch…' : 'Sending your course switch and waiting for its saved receipt…')
    try {
      if (read) {
        const result = await (upgrade ? getActivation(request.request_id) : getSavedSelection(request.request_id))
        if (token !== generation.current) return
        const original = result.request
        if (result.read_only !== true || result.source_enrollment_id !== sourceId
          || Object.keys(original).length !== Object.keys(request).length
          || Object.entries(request).some(([key, value]) => original[key as keyof typeof original] !== value)) throw new Error('Original request changed')
        if (result.state === 'applied' && result.receipt) verify({ ...result, receipt: result.receipt })
        else if (result.state === 'prepared' && result.receipt === null) {
          setPhase('prepared'); setMessage('Your original switch is prepared. You can retry that same choice, or refresh your course to check whether it needs confirmation or preparation recovery.')
        } else throw new Error('Unknown switch state')
      } else {
        const result = await (upgrade ? activateUpgrade(request) : selectSavedCourse(request))
        if (token !== generation.current) return
        verify(result)
      }
    } catch (reason) {
      if (token !== generation.current) return
      if (read && reason instanceof ApiError && reason.status === 404) {
        setPhase('ready'); setMessage('No saved switch was found. You can retry the original choice explicitly.')
      } else if (reason instanceof ApiError && reason.status === 409) {
        setPhase('changed'); setMessage('Your course or saved work changed. Refresh your course and review the choice again, or resolve any course preparation shown there.')
      } else {
        setPhase('uncertain'); setMessage('The switch could not be confirmed. Check its saved result before trying again. Your original work remains preserved.')
      }
    } finally {
      if (token === generation.current) { setBusy(false); requestAnimationFrame(() => notice.current?.focus()) }
    }
  }
  return <div className="space-y-3 text-sm text-gray-700">
    <div ref={notice} tabIndex={-1} role="status" className="outline-offset-4">{busy ? activity : message}</div>
    {busy && <p>Closing this panel does not cancel or confirm the switch. Reopen your course to check its current selection and any pending confirmation. Both courses keep their saved work.</p>}
    {(phase === 'ready' || phase === 'prepared') && <button type="button" disabled={busy || !enabled} className={choiceButton} onClick={() => { void run(false) }}>{phase === 'prepared' ? 'Retry original course switch' : label}</button>}
    {phase === 'uncertain' && <button type="button" disabled={busy} className={choiceButton} onClick={() => { void run(true) }}>Check saved switch</button>}
    {['prepared', 'changed', 'saved'].includes(phase) && <button type="button" disabled={busy} className={choiceButton} onClick={() => { void onRefreshCourse() }}>Refresh my course</button>}
  </div>
}
