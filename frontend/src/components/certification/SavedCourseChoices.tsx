import { useEffect, useId, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { choiceDigest, choiceId, getSavedChoicePreview, getSavedCourseOptions } from '../../api/courseChoices'
import type { SavedChoicePreview, SavedCourseOption } from '../../api/courseChoices'
import { choiceButton, ExplicitCourseSwitch } from './ExplicitCourseSwitch'
import { CreditTransferChoice } from './CreditTransferChoice'

export function SavedCourseChoices({ enrollmentId, onRefreshCourse }: { enrollmentId: string; onRefreshCourse: () => Promise<void> }) {
  const heading = useId()
  const generation = useRef(0)
  const notice = useRef<HTMLDivElement>(null)
  const [courses, setCourses] = useState<SavedCourseOption[] | null>(null)
  const [cursor, setCursor] = useState<string | null>(null)
  const [review, setReview] = useState<SavedChoicePreview | null>(null)
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [changed, setChanged] = useState(false)
  useEffect(() => () => { ++generation.current }, [enrollmentId])
  async function load(item?: SavedCourseOption, more = false) {
    const token = ++generation.current
    setBusy(true); setMessage(''); setReview(null); setConsent(false); setChanged(false)
    try {
      if (item) {
        const result = await getSavedChoicePreview(item)
        if (token !== generation.current) return
        const { preview: value, request } = result
        if (value.source.enrollment_id !== enrollmentId || value.target.enrollment_id !== item.enrollment_id
          || value.target.course_version !== item.course_version || value.activation_id !== item.activation_id || value.action !== item.action
          || value.read_only !== true || value.can_activate !== false || value.credit_transferred !== false
          || value.preservation_policy !== 'keep_both_existing_enrollments_and_original_workspace_references'
          || !choiceDigest(value.preview_sha256) || !choiceDigest(value.state_sha256)
          || !choiceDigest(value.target.manifest_sha256) || !choiceDigest(value.source.manifest_sha256)
          || request.activation_id !== item.activation_id || request.action !== item.action || request.preview_sha256 !== value.preview_sha256
          || !choiceId(request.request_id) || request.consent !== 'select_saved_course_preserving_both_histories_and_credit') throw new Error('Saved course preview changed')
        setReview(result)
      } else {
        const result = await getSavedCourseOptions(more && cursor ? cursor : undefined)
        if (token !== generation.current) return
        if (result.current_enrollment_id !== enrollmentId || result.read_only !== true
          || (result.next_cursor !== null && !/^[a-f0-9]{24}$/.test(result.next_cursor))
          || result.courses.some(course => !choiceId(course.activation_id) || !choiceId(course.enrollment_id)
            || course.enrollment_id === enrollmentId || !['return_to_original_course', 'resume_upgraded_course'].includes(course.action))) throw new ApiError(409, 'Selection changed')
        setCourses(previous => more ? [...(previous || []), ...result.courses] : result.courses)
        setCursor(result.next_cursor)
      }
    } catch (reason) {
      if (token !== generation.current) return
      const stale = reason instanceof ApiError && reason.status === 409
      setChanged(stale)
      setMessage(stale ? 'Your course or saved work changed. Refresh your course before reviewing a saved choice again.' : 'The saved course choice could not be loaded. Your current work remains preserved; try reviewing again.')
    } finally {
      if (token === generation.current) { setBusy(false); requestAnimationFrame(() => notice.current?.focus()) }
    }
  }
  async function refresh() {
    ++generation.current; setReview(null); setCourses(null); setCursor(null); setConsent(false); setMessage(''); setChanged(false)
    await onRefreshCourse()
  }
  return <section aria-labelledby={heading} className="my-4 min-w-0 space-y-3 rounded-lg border border-gray-200 bg-white p-2 text-sm text-gray-700 [overflow-wrap:anywhere] sm:p-4">
    <h3 id={heading} className="font-semibold text-gray-900">Continue a saved course</h3>
    <p>You can return to the original course or resume its upgrade. Each keeps its own work, XP, reading place and certificates.</p>
    <button type="button" className={choiceButton} disabled={busy} onClick={() => { void load() }}>{courses ? 'Reload saved choices' : 'Choose a saved course'}</button>
    <div ref={notice} role="status" tabIndex={-1} className="outline-offset-4">{busy ? 'Loading saved course choices…' : message}</div>
    {changed && <button type="button" className={choiceButton} onClick={() => { void refresh() }}>Refresh my course</button>}
    {!changed && courses?.length === 0 && !cursor && <p>No paired saved course is available for your current selection.</p>}
    {!changed && courses && <ul className="space-y-3">{courses.map(item => <li key={`${item.activation_id}:${item.action}`} className="min-w-0 border-t border-gray-200 pt-3">
      <p className="font-semibold text-gray-900">{item.course_title}</p>
      <p>Course version: {item.course_version}</p>
      <p>{item.action === 'return_to_original_course' ? 'Return to your original course' : 'Resume your upgraded course'}</p>
      {item.definition_available ? <button type="button" className={`${choiceButton} mt-2`} disabled={busy} onClick={() => { void load(item) }}>Review {item.course_title}</button> : <p>This course definition is unavailable. Its saved work remains preserved.</p>}
    </li>)}</ul>}
    {!changed && cursor && <button type="button" className={choiceButton} disabled={busy} onClick={() => { void load(undefined, true) }}>Load more saved choices</button>}
    {!changed && courses?.some(item => item.action === 'return_to_original_course') && <CreditTransferChoice key={enrollmentId} enrollmentId={enrollmentId} onRefreshCourse={onRefreshCourse} />}
    {review && !changed && <section aria-label="Saved course preservation review" className="min-w-0 space-y-3 border-t border-gray-300 pt-3">
      <h4 className="font-semibold text-gray-900">Both courses keep their saved work</h4>
      {(['source', 'target'] as const).map(key => { const item = review.preview[key]; return <div key={key} className="space-y-1">
        <h5 className="font-semibold text-gray-900">{key === 'source' ? 'Current course' : 'Course to continue'}: {item.course_title}</h5>
        <p>Course version: {item.course_version}</p>
        <p>{item.total_xp} XP · Completed modules: {item.completed_modules}</p>
        {item.has_saved_place && <p>Your reading place stays saved here.</p>}
        {item.credential_id && <p>Your original certificate stays available in certificate history.</p>}
      </div> })}
      <p>Nothing is copied, reset, reassessed or rerun. Existing workspace references stay with their original course.</p>
      <label className="flex min-h-11 items-start gap-3 py-2"><input type="checkbox" className="mt-1 shrink-0" checked={consent} onChange={event => setConsent(event.target.checked)} /><span>Keep both courses’ histories and credit, and continue the saved course shown above.</span></label>
      <ExplicitCourseSwitch enabled={consent} key={review.request.request_id} request={review.request} sourceId={enrollmentId} targetVersion={review.preview.target.course_version} targetManifest={review.preview.target.manifest_sha256} targetId={review.preview.target.enrollment_id} label={review.preview.action === 'return_to_original_course' ? 'Return to original course' : 'Resume upgraded course'} onRefreshCourse={refresh} />
    </section>}
  </section>
}
