import { CourseRequestStatus, type CourseRequestPhase } from './CourseRequestStatus'
import { CourseDraftNotice } from './CourseDraftNotice'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getProcessDesign, getProcessDesigns, saveProcessDesign } from '../../api/certification'
import { ApiError } from '../../api/client'
import type { ProcessCaseDefinition, ProcessSubmissionBody, ProcessSubmissionList, SavedProcessSubmission } from '../../types/certification'
import { PracticalAssessment } from './PracticalAssessment'
import { SavedAutomaticReviews } from './SavedAutomaticReviews'

const button = 'min-h-11 min-w-0 max-w-full rounded-lg border border-gray-300 bg-white px-2 py-2 text-left text-sm font-medium text-gray-900 [overflow-wrap:anywhere] disabled:opacity-50'
const control = 'mt-1 block min-h-11 w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900'
const labels: Record<string, string> = { method_choice: 'Working method and rationale', human_checkpoint: 'Corrected process map', bounded_scope: 'Bounded task brief' }
const validId = (value: string) => /^[a-f0-9]{32}$/.test(value)
function validCase(value: ProcessCaseDefinition, expected: ProcessCaseDefinition) {
  return value.module_id === 'process_mapping' && value.provenance === 'authored_fictional_design_case_not_execution'
    && /^[a-f0-9]{64}$/.test(value.case_sha256) && value.case_sha256 === expected.case_sha256
    && value.questions.length === 3 && new Set(value.questions.map(item => item.id)).size === 3
    && value.questions.every(item => Object.hasOwn(labels, item.id))
}
function validBody(value: ProcessSubmissionBody | null, definition: ProcessCaseDefinition): value is ProcessSubmissionBody {
  return !!value && validId(value.request_id) && value.case_sha256 === definition.case_sha256
    && value.consent === 'save_reviewed_process_design' && (value.previous_submission_id === null || validId(value.previous_submission_id))
    && !!value.answers && Object.keys(value.answers).length === 3
    && definition.questions.every(question => typeof value.answers[question.id] === 'string' && value.answers[question.id].length <= 12000)
}

export function ProcessDesign({ enrollmentId, definition, historyOnly = false }: {
  enrollmentId: string; definition: ProcessCaseDefinition; historyOnly?: boolean
}) {
  const [phase, setPhase] = useState<CourseRequestPhase>('checking')
  const key = `certification-process-request:${enrollmentId}:${definition.case_sha256}`
  const draftKey = `certification-process-draft:${enrollmentId}:${definition.case_sha256}`
  const [listing, setListing] = useState<ProcessSubmissionList | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [previous, setPrevious] = useState<string | null>(null)
  const [pending, setPending] = useState<ProcessSubmissionBody | null>(null)
  const [canResend, setCanResend] = useState(false)
  const [selected, setSelected] = useState<SavedProcessSubmission | null>(null)
  const [reference, setReference] = useState('')
  const [feedbackId, setFeedbackId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [restoreFailed, setRestoreFailed] = useState(false)
  const [draftStatus, setDraftStatus] = useState<'empty' | 'stored' | 'unavailable'>('empty')
  const sequence = useRef(0), sending = useRef(false), focusSaved = useRef(false), focusForm = useRef(false)
  const savedRef = useRef<HTMLDivElement>(null), formRef = useRef<HTMLFormElement>(null)
  const canWrite = !historyOnly && !restoreFailed && listing?.can_submit === true
  useEffect(() => {
    let active = true
    const requestCounter = sequence
    sequence.current++
    setPhase('checking'); setBusy(true)
    void getProcessDesigns(enrollmentId).then(value => {
      if (!active) return
      if (value.enrollment_id !== enrollmentId || value.module_id !== 'process_mapping' || !validCase(value.case, definition)
        || !/^[a-f0-9]{64}$/.test(value.manifest_sha256)
        || value.submissions.some(item => !validId(item.submission_id))) throw new Error('Different course requirements')
      setListing(value)
      if (!historyOnly) {
        try {
          const stored = JSON.parse(sessionStorage.getItem(key) || 'null') as ProcessSubmissionBody | null
          if (stored && !validBody(stored, definition)) throw new Error('Invalid saved request')
          if (stored) { setPending(stored); setAnswers(stored.answers); setPrevious(stored.previous_submission_id) }
          else {
            const draft = JSON.parse(sessionStorage.getItem(draftKey) || 'null')
            if (draft?.answers && definition.questions.every(question => typeof draft.answers[question.id] === 'string')) {
              setDraftStatus('stored'); setAnswers(draft.answers); setPrevious(validId(draft.previous || '') ? draft.previous : null)
            }
          }
        } catch { setRestoreFailed(true); setError('This tab could not restore its saved draft. Your server history is still available. Reload before saving if an earlier request was interrupted.') }
      }
    }).catch(() => { if (active) setError('The original process assignment could not be loaded for this course. Reload the module to try again.') })
      .finally(() => { if (active) setBusy(false) })
    return () => { active = false; requestCounter.current++ }
  }, [enrollmentId, definition, historyOnly, key, draftKey])
  useLayoutEffect(() => {
    if (selected && focusSaved.current) { focusSaved.current = false; savedRef.current?.focus() }
    if (!selected && focusForm.current) { focusForm.current = false; formRef.current?.focus() }
  }, [selected])

  function verify(value: SavedProcessSubmission, id: string, expected?: ProcessSubmissionBody) {
    if (value.uuid !== id || value.enrollment_id !== enrollmentId || value.module_id !== 'process_mapping'
      || value.course_version !== listing?.course_version || value.manifest_sha256 !== listing?.manifest_sha256
      || !validCase(value.case, definition) || !validBody(value.submission, definition) || value.submission.request_id !== id
      || value.submission_channel !== 'authenticated_learner_process_request' || value.credit_awarded !== false || value.module_completion_eligible !== false
      || (expected && (value.submission.previous_submission_id !== expected.previous_submission_id
        || definition.questions.some(question => value.submission.answers[question.id] !== expected.answers[question.id])))) throw new Error('Different saved design')
    return value
  }
  function accept(value: SavedProcessSubmission, clearPending = false) {
    if (clearPending) {
      sessionStorage.removeItem(key); sessionStorage.removeItem(draftKey)
      setPending(null); setCanResend(false)
    }
    setFeedbackId(''); focusSaved.current = true; setSelected(value)
    setListing(current => current ? { ...current, submissions: [{ submission_id: value.uuid, submitted_at: value.submitted_at,
      previous_submission_id: value.submission.previous_submission_id }, ...current.submissions.filter(item => item.submission_id !== value.uuid)].slice(0, 50) } : current)
  }
  async function inspect(id: string) {
    if (!id || pending || sending.current) return
    const token = ++sequence.current
    setPhase('checking'); setBusy(true); setError(''); setSelected(null); setFeedbackId('')
    try {
      const value = verify(await getProcessDesign(enrollmentId, id), id)
      if (token === sequence.current) accept(value)
    } catch { if (token === sequence.current) setError('This saved design could not be opened for the original course. Check its reference and try again.') }
    finally { if (token === sequence.current) setBusy(false) }
  }
  async function save(check = false) {
    if (sending.current || !canWrite || (pending && !check && !canResend)) return
    sending.current = true
    const token = ++sequence.current
    let sent = false
    setPhase(check ? 'checking' : 'sending'); setBusy(true); setError(''); setCanResend(false)
    try {
      const body = pending || { request_id: crypto.randomUUID().replaceAll('-', ''), case_sha256: definition.case_sha256,
        consent: 'save_reviewed_process_design' as const, previous_submission_id: previous,
        answers: Object.fromEntries(definition.questions.map(question => [question.id, answers[question.id] || ''])) }
      if (!validBody(body, definition)) throw new Error('Invalid draft')
      if (!check) { sessionStorage.setItem(key, JSON.stringify(body)); setPending(body); sent = true }
      const value = verify(await (check ? getProcessDesign(enrollmentId, body.request_id) : saveProcessDesign(enrollmentId, body)), body.request_id, body)
      if (token === sequence.current) accept(value, true)
    } catch (failure) {
      if (token !== sequence.current) return
      if (check && failure instanceof ApiError && failure.status === 404) {
        setCanResend(true); setError('No design is saved for this reference yet. Finish the same request to preserve its original answers.')
      } else if (sent && failure instanceof ApiError && failure.status === 422) {
        sessionStorage.removeItem(key); setPending(null); setError('The design was not saved. Check all three answers and try again.')
      } else if (!check && !sent) setError('This tab could not preserve the request. Allow session storage before saving; no request was sent.')
      else setError('We could not confirm the saved design. Check its saved state before editing or sending again.')
    } finally { sending.current = false; if (token === sequence.current) setBusy(false) }
  }
  function revise(value?: SavedProcessSubmission) {
    if (!canWrite || pending) return
    const next = value ? value.submission.answers : Object.fromEntries(definition.questions.map(question => [question.id, '']))
    const ancestor = value?.uuid || null
    setAnswers(next); setPrevious(ancestor); setFeedbackId(''); focusForm.current = true; setSelected(null)
    try { sessionStorage.setItem(draftKey, JSON.stringify({ answers: next, previous: ancestor })); setDraftStatus('stored') } catch { setDraftStatus('unavailable') }
  }
  function edit(id: string, value: string) {
    const next = { ...answers, [id]: value }
    setAnswers(next)
    try { sessionStorage.setItem(draftKey, JSON.stringify({ answers: next, previous })); setDraftStatus('stored') } catch { setDraftStatus('unavailable') }
  }
  return <section aria-label="Process design assessment" className="min-w-0 space-y-4 [overflow-wrap:anywhere]">
    <h4 className="text-base font-semibold text-gray-900">Design a bounded process</h4>
    {listing && <ProcessBrief definition={selected?.case || listing.case} />}
    <CourseRequestStatus phase={busy ? phase : null} action="design" />
    {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
    {listing && (!canWrite || historyOnly) && <p className="text-sm text-gray-700">{historyOnly ? 'Original process history is read-only. New work belongs to your selected course.' : listing.read_only_reason}</p>}
    {listing && <>
      {listing.submissions.length ? <label className="block text-sm text-gray-900">Saved process design<select className={control} disabled={busy || !!pending} value={selected?.uuid || ''} onChange={event => { void inspect(event.target.value) }}>
        <option value="">Choose saved work</option>{listing.submissions.map((item, index) => <option key={item.submission_id} value={item.submission_id}>Design {index + 1} · {item.submission_id.slice(0, 8)}{item.previous_submission_id ? ' · revision' : ''}</option>)}
      </select></label> : <p className="text-sm text-gray-700">No process designs are saved yet.</p>}
      {listing.older_submissions_available && <p className="text-sm text-gray-700">Showing the 50 most recent designs. Open older work by its full reference.</p>}
      <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-gray-900">Open a process design by reference</summary>
        <form className="space-y-2" onSubmit={event => { event.preventDefault(); void inspect(reference.trim()) }}>
          <label className="block text-sm text-gray-900">Full process reference<input className={control} value={reference} onChange={event => setReference(event.target.value)} required pattern="[a-f0-9]{32}" disabled={busy || !!pending} /></label>
          <button className={button} disabled={busy || !!pending}>Open original design</button>
        </form>
      </details>
    </>}
    {canWrite && !selected && <form ref={formRef} tabIndex={-1} aria-label="Your process design" className="min-w-0 space-y-4 outline-offset-4" onSubmit={event => { event.preventDefault(); void save() }}>
      <p className="text-sm text-gray-700">The agent may help draft. Review and correct the design before saving your decisions. Saving preserves your work; it does not run a workflow, assess competence or award credit.</p>
      {previous && <p className="text-sm text-gray-700">This saves a new revision and preserves the original design.</p>}
      {definition.questions.map(question => <div key={question.id} className="space-y-2">
        <label htmlFor={`process-${question.id}`} className="block text-sm font-semibold text-gray-900">{labels[question.id]}</label>
        <p id={`process-help-${question.id}`} className="text-sm text-gray-700">{question.prompt}</p>
        <textarea id={`process-${question.id}`} aria-describedby={`process-help-${question.id}`} className={`${control} min-h-36`} rows={6} maxLength={12000} required disabled={busy || !!pending} value={answers[question.id] || ''} onChange={event => edit(question.id, event.target.value)} />
      </div>)}
      <CourseDraftNotice status={draftStatus} />
      {!pending && <button className={button} disabled={busy}>Save my reviewed design</button>}
    </form>}
    {pending && canWrite && <div className="space-y-2">
      <p className="text-sm text-gray-700">Your original answers and request are preserved in this tab. Check the saved state before making changes.</p>
      <button type="button" className={button} disabled={busy} onClick={() => { void save(true) }}>Check saved design</button>
      {canResend && <button type="button" className={button} disabled={busy} onClick={() => { void save() }}>Finish original design request</button>}
    </div>}
    {selected && <div ref={savedRef} tabIndex={-1} role="region" aria-label="Saved process design" className="min-w-0 space-y-4 border-t border-gray-200 pt-4 outline-offset-4">
      <h5 className="text-base font-semibold text-gray-900">Design saved</h5>
      <p className="text-sm text-gray-700">These are your original saved decisions. They have not been replaced by later revisions or course changes.</p>
      {selected.case.questions.map(question => <div key={question.id} className="space-y-2">
        <h6 className="text-sm font-semibold text-gray-900">{labels[question.id]}</h6>
        <pre tabIndex={0} role="region" aria-label={`Saved ${labels[question.id].toLowerCase()}`} className="max-h-96 min-w-0 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-gray-50 p-2 font-sans text-sm text-gray-900">{selected.submission.answers[question.id]}</pre>
      </div>)}
      <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-gray-900">Process design references</summary><p className="break-all text-sm text-gray-700">{selected.uuid}</p>
        {selected.submission.previous_submission_id && <p className="break-all text-sm text-gray-700">Original design: {selected.submission.previous_submission_id}</p>}
      </details>
      {canWrite && <><button type="button" className={button} disabled={busy} onClick={() => revise(selected)}>Revise this design</button>
        <button type="button" className={button} disabled={busy} onClick={() => revise()}>Start a separate design</button>
        <PracticalAssessment key={selected.uuid} enrollmentId={enrollmentId} moduleId="process_mapping" processSubmissionId={selected.uuid} onOpenFeedback={setFeedbackId} />
      </>}
    </div>}
    {listing && <SavedAutomaticReviews key={`${enrollmentId}:${feedbackId}`} enrollmentId={enrollmentId} moduleId="process_mapping" initialAttemptId={feedbackId || undefined} workNavigationDisabled={busy || !!pending} onOpenWork={review => { void inspect(review.process_submission_id!) }} />}
  </section>
}

function ProcessBrief({ definition }: { definition: ProcessCaseDefinition }) {
  return <section aria-label="Assigned process case" className="min-w-0 space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-2 text-sm text-gray-900 sm:p-4">
    <h5 className="font-semibold">Your fictional monthly-review assignment</h5>
    <p>{definition.notice}</p><p>{definition.task}</p>
    <p><strong>Intended result: </strong>{definition.intended_output}</p>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inputs, scope and review responsibilities</summary>
      <ul className="space-y-3">{definition.assigned_inputs.map(item => <li key={item.id}><strong>{item.id}: </strong>{item.description}</li>)}</ul>
      <p className="mt-3">{definition.repetition}</p><p className="mt-3">{definition.authority}</p>
      <h6 className="mt-3 font-semibold">Excluded work</h6><ul className="list-disc space-y-2 pl-4">{definition.exclusions.map(item => <li key={item}>{item}</li>)}</ul>
      <h6 className="mt-3 font-semibold">Reasons to stop or flag an item</h6><ul className="list-disc space-y-2 pl-4">{definition.exception_conditions.map(item => <li key={item}>{item}</li>)}</ul>
    </details>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inspect the flawed proposal</summary><p>{definition.flawed_proposal}</p></details>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Compare the three working-method situations</summary><ol className="list-decimal space-y-3 pl-4">{definition.method_comparisons.map(item => <li key={item.id}>{item.situation}</li>)}</ol></details>
  </section>
}
