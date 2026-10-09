import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { choiceDigest, choiceId, getChoicePreview, getUpgradeChoice, saveUpgradeChoice } from '../../api/courseChoices'
import type { ChoicePreview, UpgradeChoice, UpgradeChoiceRequest } from '../../api/courseChoices'
import type { UpgradePreview } from '../../types/certification'
import { choiceButton, ExplicitCourseSwitch } from './ExplicitCourseSwitch'

const unavailable: Record<string, string> = {
  source_read_only: 'This course is read-only. Refresh your course to review its current status.',
  assessment_unavailable: 'The offered course is not ready for assessed learning yet. Keep learning in your current course.',
  resume_saved_course: 'You already have a saved course in this version. Use Choose a saved course to resume its existing work.',
  selection_busy: 'A course operation or confirmation is still in progress. Refresh your course to check its status first.',
  unfinished_course_work: 'Finish or reconcile the pending course work before switching. Your saved work stays in its original course.',
}

export function OptionalUpgradeChoice({ preview, onRefreshCourse }: { preview: UpgradePreview; onRefreshCourse: () => Promise<void> }) {
  const generation = useRef(0)
  const notice = useRef<HTMLDivElement>(null)
  const [review, setReview] = useState<ChoicePreview | null>(null)
  const [decision, setDecision] = useState<UpgradeChoice | null>(null)
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [activity, setActivity] = useState('')
  const [uncertain, setUncertain] = useState(false)
  const [changed, setChanged] = useState(false)
  const [message, setMessage] = useState('')
  useEffect(() => () => { ++generation.current }, [preview])
  function verify(value: UpgradeChoice, request: UpgradeChoiceRequest) {
    if (value.decision_id !== request.request_id || value.source_enrollment_id !== preview.source.enrollment_id
      || value.target_version !== preview.target.course_version || value.target_manifest_sha256 !== preview.target.manifest_sha256
      || value.preview_sha256 !== request.preview_sha256 || !choiceDigest(value.decision_sha256)
      || value.credit_transferred !== false || value.requires_fresh_activation_check !== true
      || value.activation_request.decision_id !== value.decision_id || !choiceId(value.activation_request.request_id)
      || value.activation_request.consent !== 'activate_optional_upgrade_preserving_original_work_without_credit_transfer') throw new Error('Saved choice changed')
    return value
  }
  async function run(action: 'review' | 'save' | 'check') {
    const token = ++generation.current
    setBusy(true); setMessage('')
    setActivity(action === 'review' ? 'Loading the optional upgrade preservation review…' : action === 'save' ? 'Saving your optional upgrade choice…' : 'Checking the saved optional choice…')
    try {
      if (action === 'review') {
        setReview(null); setDecision(null); setConsent(false); setChanged(false)
        const result = await getChoicePreview(preview.source.enrollment_id, preview.target.course_version)
        if (token !== generation.current) return
        const { comparison, choice } = result
        const request = choice.request
        if (comparison.preview_sha256 !== preview.preview_sha256 || comparison.source.enrollment_id !== preview.source.enrollment_id
          || comparison.target.course_version !== preview.target.course_version || comparison.target.manifest_sha256 !== preview.target.manifest_sha256
          || comparison.policy !== 'optional' || comparison.can_activate !== false
          || request.source_enrollment_id !== preview.source.enrollment_id || request.target_version !== preview.target.course_version
          || !choiceId(request.request_id) || !choiceDigest(request.preview_sha256)
          || request.consent !== 'preserve_original_work_and_require_all_new_outcomes'
          || typeof choice.available !== 'boolean' || typeof choice.recorded !== 'boolean'
          || (choice.available ? choice.reason !== null : !unavailable[choice.reason || ''])
          || choice.recorded !== Boolean(choice.decision)
          || (!choice.recorded && request.preview_sha256 !== comparison.preview_sha256)) throw new ApiError(409, 'Review changed')
        if (choice.decision) setDecision(verify(choice.decision, request))
        setReview(result); setUncertain(false)
        setMessage(choice.available ? choice.recorded ? 'Your original preservation choice is saved. Switching courses is a separate action below.' : 'Review and save your choice below. This does not switch courses.' : unavailable[choice.reason!])
      } else if (review) {
        const result = await (action === 'save' ? saveUpgradeChoice(review.choice.request) : getUpgradeChoice(review.choice.request.request_id))
        if (token !== generation.current) return
        setDecision(verify(result, review.choice.request)); setUncertain(false)
        setMessage('Your preservation choice is saved. Your current course stays selected until you explicitly switch below.')
      }
    } catch (reason) {
      if (token !== generation.current) return
      if (reason instanceof ApiError && reason.status === 409) {
        setChanged(true); setMessage('Your course or saved work changed. Refresh your course and compare again before making a choice.')
      } else if (action === 'check' && reason instanceof ApiError && reason.status === 404) {
        setUncertain(false); setMessage('No saved choice was found. You can explicitly save the original reviewed choice again.')
      } else {
        setUncertain(action !== 'review'); setMessage(action === 'review' ? 'The optional choice could not be reviewed. Keep your current course or try the review again.' : 'The choice could not be confirmed. Check the saved choice before trying again.')
      }
    } finally {
      if (token === generation.current) { setBusy(false); requestAnimationFrame(() => notice.current?.focus()) }
    }
  }
  return <section className="min-w-0 space-y-3 border-t border-gray-200 pt-3 text-sm text-gray-700" aria-label="Optional upgrade choice">
    <div ref={notice} role="status" tabIndex={-1} className="outline-offset-4">{busy ? activity : message}</div>
    {busy && <p>This step does not switch courses or transfer credit. If you close the panel, review your saved choice when you return; switching requires a separate action.</p>}
    {!review && !changed && <button type="button" className={choiceButton} disabled={busy} onClick={() => { void run('review') }}>Review upgrade choice</button>}
    {changed ? <button type="button" className={choiceButton} disabled={busy} onClick={() => { void onRefreshCourse() }}>Refresh my course</button> : review?.choice.available && <>
      {!decision && !uncertain && <>
        <label className="flex min-h-11 items-start gap-3 py-2"><input type="checkbox" className="mt-1 shrink-0" checked={consent} disabled={busy} onChange={event => setConsent(event.target.checked)} /><span>Keep all existing work, XP and certificates in my original course. I understand that I must meet all required outcomes in {preview.target.course_title}; no credit transfers.</span></label>
        <button type="button" className={choiceButton} disabled={!consent || busy} onClick={() => { void run('save') }}>Save my upgrade choice</button>
      </>}
      {uncertain && <button type="button" className={choiceButton} disabled={busy} onClick={() => { void run('check') }}>Check saved choice</button>}
      {decision && <ExplicitCourseSwitch key={decision.activation_request.request_id} request={decision.activation_request} sourceId={preview.source.enrollment_id} targetVersion={preview.target.course_version} targetManifest={preview.target.manifest_sha256} label={`Switch to ${preview.target.course_title}`} onRefreshCourse={onRefreshCourse} />}
    </>}
  </section>
}
