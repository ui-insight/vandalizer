import { CourseRequestStatus, type CourseRequestPhase } from './CourseRequestStatus'
import { useCourseDraft, draftStrings } from '../../hooks/useCourseDraft'
import { CourseDraftNotice } from './CourseDraftNotice'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getWorkflowDesign, getWorkflowDesigns, approveWorkflowDesign } from '../../api/certification'
import { ApiError } from '../../api/client'
import type { WorkflowDesignCaseDefinition, WorkflowDesignSubmissionBody, WorkflowDesignList, SavedWorkflowDesignSubmission, SavedWorkflowDesignCapture } from '../../types/certification'
import { PracticalAssessment } from './PracticalAssessment'
import { SavedAutomaticReviews } from './SavedAutomaticReviews'
import { WorkflowDesignCapture, WorkflowSnapshot, validCapture } from './WorkflowDesignCapture'

const button = 'min-h-11 min-w-0 max-w-full rounded-lg border border-gray-300 bg-white px-2 py-2 text-left text-sm font-medium text-gray-900 [overflow-wrap:anywhere] disabled:opacity-50'
const control = 'mt-1 block min-h-11 w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2 text-sm text-gray-900'
const labels: Record<string, string> = { data_flow: 'Trace the saved data flow', approval_boundary: 'Correction and approval boundary', reviewable_design: 'Evidence and review path' }
const validId = (value: string) => /^[a-f0-9]{32}$/.test(value)
function validCase(value: WorkflowDesignCaseDefinition, expected: WorkflowDesignCaseDefinition) {
  return value.module_id === 'workflow_design' && value.provenance === 'authored_workflow_design_case_not_execution'
    && /^[a-f0-9]{64}$/.test(value.case_sha256) && value.case_sha256 === expected.case_sha256
    && value.questions.length === 3 && new Set(value.questions.map(item => item.id)).size === 3
    && value.questions.every(item => Object.hasOwn(labels, item.id))
}
function validBody(value: WorkflowDesignSubmissionBody | null, definition: WorkflowDesignCaseDefinition): value is WorkflowDesignSubmissionBody {
  return !!value && validId(value.request_id) && validId(value.input_snapshot_id) && /^[a-f0-9]{64}$/.test(value.input_snapshot_sha256) && value.case_sha256 === definition.case_sha256
    && value.consent === 'approve_saved_workflow_design_for_assessment' && (value.previous_submission_id === null || validId(value.previous_submission_id))
    && !!value.answers && Object.keys(value.answers).length === 3
    && definition.questions.every(question => typeof value.answers[question.id] === 'string' && value.answers[question.id].length <= 12000)
}

export function WorkflowDesign({ enrollmentId, definition, historyOnly = false }: {
  enrollmentId: string; definition: WorkflowDesignCaseDefinition; historyOnly?: boolean
}) {
  const [phase, setPhase] = useState<CourseRequestPhase>('checking')
  const key = `certification-workflow-approval-request:${enrollmentId}:${definition.case_sha256}`
  const [capturePending, setCapturePending] = useState(false)
  const [captured, setCaptured] = useState<SavedWorkflowDesignCapture | null>(null)
  const [listing, setListing] = useState<WorkflowDesignList | null>(null)
  const [initialAnswers, setInitialAnswers] = useState<Record<string, string>>({})
  const [previous, setPrevious] = useState<string | null>(null)
  const [pending, setPending] = useState<WorkflowDesignSubmissionBody | null>(null)
  const [canResend, setCanResend] = useState(false)
  const [selected, setSelected] = useState<SavedWorkflowDesignSubmission | null>(null)
  const [reference, setReference] = useState('')
  const [feedbackId, setFeedbackId] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [restoreFailed, setRestoreFailed] = useState(false)
  const sequence = useRef(0), sending = useRef(false), focusSaved = useRef(false), focusForm = useRef(false)
  const savedRef = useRef<HTMLDivElement>(null), formRef = useRef<HTMLFormElement>(null)
  const emptyAnswers = Object.fromEntries(definition.questions.map(question => [question.id, '']))
  const [authoredAnswers, setAuthoredAnswers, draftStatus] = useCourseDraft(['workflow-design-approval', enrollmentId,
    listing?.manifest_sha256 || null, definition.case_sha256, pending?.input_snapshot_id || captured?.uuid || null,
    pending?.input_snapshot_sha256 || captured?.input_snapshot_sha256 || null, previous],
  { ...emptyAnswers, ...initialAnswers }, draftStrings(definition.questions.map(question => question.id)))
  const answers = pending?.answers || authoredAnswers
  const canWrite = !historyOnly && !restoreFailed && listing?.can_submit === true
  useEffect(() => {
    let active = true
    const requestCounter = sequence
    sequence.current++
    setPhase('checking'); setBusy(true)
    void getWorkflowDesigns(enrollmentId).then(value => {
      if (!active) return
      if (value.enrollment_id !== enrollmentId || value.module_id !== 'workflow_design' || !validCase(value.case, definition)
        || !/^[a-f0-9]{64}$/.test(value.manifest_sha256)
        || value.submissions.some(item => !validId(item.submission_id))) throw new Error('Different course requirements')
      setListing(value)
      if (!historyOnly) {
        try {
          const stored = JSON.parse(sessionStorage.getItem(key) || 'null') as WorkflowDesignSubmissionBody | null
          if (stored && !validBody(stored, definition)) throw new Error('Invalid saved request')
          if (stored) { setPending(stored); setInitialAnswers(stored.answers); setPrevious(stored.previous_submission_id) }

        } catch { setRestoreFailed(true); setError('This tab could not restore its saved draft. Your server history is still available. Reload before saving if an earlier request was interrupted.') }
      }
    }).catch(() => { if (active) setError('The original workflow assignment could not be loaded for this course. Reload the module to try again.') })
      .finally(() => { if (active) setBusy(false) })
    return () => { active = false; requestCounter.current++ }
  }, [enrollmentId, definition, historyOnly, key])
  useLayoutEffect(() => {
    if (selected && focusSaved.current) { focusSaved.current = false; savedRef.current?.focus() }
    if (!selected && focusForm.current) { focusForm.current = false; formRef.current?.focus() }
  }, [selected])

  function verify(value: SavedWorkflowDesignSubmission, id: string, expected?: WorkflowDesignSubmissionBody) {
    if (value.uuid !== id || value.enrollment_id !== enrollmentId || value.module_id !== 'workflow_design'
      || value.course_version !== listing?.course_version || value.manifest_sha256 !== listing?.manifest_sha256
      || !validCase(value.input_snapshot.case, definition) || !validBody(value.submission, definition) || value.submission.request_id !== id
      || value.execution_authorized !== false || value.submission.input_snapshot_id !== value.input_snapshot.uuid
      || !validCapture({ ...value.input_snapshot, input_snapshot_sha256: value.submission.input_snapshot_sha256 }, listing!, value.input_snapshot.uuid)
      || value.submission_channel !== 'authenticated_learner_workflow_design_request' || value.credit_awarded !== false || value.module_completion_eligible !== false
      || (expected && (value.submission.input_snapshot_id !== expected.input_snapshot_id || value.submission.input_snapshot_sha256 !== expected.input_snapshot_sha256
        || value.submission.previous_submission_id !== expected.previous_submission_id
        || definition.questions.some(question => value.submission.answers[question.id] !== expected.answers[question.id])))) throw new Error('Different saved design')
    return value
  }
  function accept(value: SavedWorkflowDesignSubmission, clearPending = false) {
    if (clearPending) {
      sessionStorage.removeItem(key); setAuthoredAnswers(emptyAnswers)
      setPending(null); setCanResend(false)
    }
    setFeedbackId(''); focusSaved.current = true; setSelected(value)
    setListing(current => current ? { ...current, submissions: [{ submission_id: value.uuid, submitted_at: value.submitted_at,
      previous_submission_id: value.submission.previous_submission_id, input_snapshot_id: value.submission.input_snapshot_id, workflow_name: value.input_snapshot.artifact.workflow.name }, ...current.submissions.filter(item => item.submission_id !== value.uuid)].slice(0, 50) } : current)
  }
  async function inspect(id: string) {
    if (!id || pending || sending.current) return
    const token = ++sequence.current
    setPhase('checking'); setBusy(true); setError(''); setSelected(null); setFeedbackId('')
    try {
      const value = verify(await getWorkflowDesign(enrollmentId, id), id)
      if (token === sequence.current) accept(value)
    } catch { if (token === sequence.current) setError('This saved design could not be opened for the original course. Check its reference and try again.') }
    finally { if (token === sequence.current) setBusy(false) }
  }
  async function save(check = false) {
    if (sending.current || !canWrite || capturePending || (!pending && !captured) || (pending && !check && !canResend)) return
    sending.current = true
    const token = ++sequence.current
    let sent = false
    setPhase(check ? 'checking' : 'sending'); setBusy(true); setError(''); setCanResend(false)
    try {
      const body = pending || { request_id: crypto.randomUUID().replaceAll('-', ''), case_sha256: definition.case_sha256,
        input_snapshot_id: captured!.uuid, input_snapshot_sha256: captured!.input_snapshot_sha256,
        consent: 'approve_saved_workflow_design_for_assessment' as const, previous_submission_id: previous,
        answers: Object.fromEntries(definition.questions.map(question => [question.id, answers[question.id] || ''])) }
      if (!validBody(body, definition)) throw new Error('Invalid draft')
      if (!check) { sessionStorage.setItem(key, JSON.stringify(body)); setPending(body); sent = true }
      const value = verify(await (check ? getWorkflowDesign(enrollmentId, body.request_id) : approveWorkflowDesign(enrollmentId, body)), body.request_id, body)
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
  function revise(value?: SavedWorkflowDesignSubmission) {
    if (!canWrite || pending) return
    if (value) setCaptured({ ...value.input_snapshot, input_snapshot_sha256: value.submission.input_snapshot_sha256 })
    const next = value ? value.submission.answers : Object.fromEntries(definition.questions.map(question => [question.id, '']))
    const ancestor = value?.uuid || null
    setInitialAnswers(next); setPrevious(ancestor); setFeedbackId(''); focusForm.current = true; setSelected(null)
  }
  function edit(id: string, value: string) {
    const next = { ...answers, [id]: value }
    setAuthoredAnswers(next)
  }
  return <section aria-label="Workflow design assessment" className="min-w-0 space-y-4 [overflow-wrap:anywhere]">
    <h4 className="text-base font-semibold text-gray-900">Inspect and approve your workflow design</h4>
    {listing && <WorkflowBrief definition={selected?.input_snapshot.case || listing.case} />}
    <CourseRequestStatus phase={busy ? phase : null} action="approval" />
    {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
    {listing && (!canWrite || historyOnly) && <p className="text-sm text-gray-700">{historyOnly ? 'Original workflow history is read-only. New work belongs to your selected course.' : listing.read_only_reason}</p>}
    {listing && <>
      {listing.submissions.length ? <label className="block text-sm text-gray-900">Saved workflow approval<select className={control} disabled={busy || !!pending || capturePending} value={selected?.uuid || ''} onChange={event => { void inspect(event.target.value) }}>
        <option value="">Choose saved work</option>{listing.submissions.map((item, index) => <option key={item.submission_id} value={item.submission_id}>Design {index + 1} · {item.submission_id.slice(0, 8)}{item.previous_submission_id ? ' · revision' : ''}</option>)}
      </select></label> : <p className="text-sm text-gray-700">No workflow approvals are saved yet.</p>}
      {listing.older_submissions_available && <p className="text-sm text-gray-700">Showing the 50 most recent designs. Open older work by its full reference.</p>}
      <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-gray-900">Open a workflow approval by reference</summary>
        <form className="space-y-2" onSubmit={event => { event.preventDefault(); void inspect(reference.trim()) }}>
          <label className="block text-sm text-gray-900">Full workflow approval reference<input className={control} value={reference} onChange={event => setReference(event.target.value)} required pattern="[a-f0-9]{32}" disabled={busy || !!pending || capturePending} /></label>
          <button className={button} disabled={busy || !!pending || capturePending}>Open original approval</button>
        </form>
      </details>
    </>}
    {canWrite && !selected && !pending && listing && <>
      <button type="button" className={button} onClick={() => { void getWorkflowDesigns(enrollmentId).then(value => {
        if (value.enrollment_id !== enrollmentId || value.manifest_sha256 !== listing.manifest_sha256 || !validCase(value.case, definition)) throw new Error('Different course')
        setListing(value)
      }).catch(() => setError('Workflow choices could not be refreshed. Your saved capture is preserved.')) }}>Refresh saved workflow choices</button>
      <WorkflowDesignCapture listing={listing} captured={captured} onCaptured={value => { setCaptured(value); setPrevious(null); setInitialAnswers({}) }} onPendingChange={setCapturePending} />
    </>}
    {captured && !selected && <WorkflowSnapshot value={captured} />}
    {canWrite && !selected && (captured || pending) && <form ref={formRef} tabIndex={-1} aria-label="Your workflow design decisions" className="min-w-0 space-y-4 outline-offset-4" onSubmit={event => { event.preventDefault(); void save() }}>
      <p className="text-sm text-gray-700">The agent may help draft. Review and correct the design before saving your decisions. Saving preserves your work; it does not run a workflow, assess competence or award credit.</p>
      {previous && <p className="text-sm text-gray-700">This saves a new revision and preserves the original design.</p>}
      {definition.questions.map(question => <div key={question.id} className="space-y-2">
        <label htmlFor={`workflow-design-${question.id}`} className="block text-sm font-semibold text-gray-900">{labels[question.id]}</label>
        <p id={`workflow-design-help-${question.id}`} className="text-sm text-gray-700">{question.prompt}</p>
        <textarea id={`workflow-design-${question.id}`} aria-describedby={`workflow-design-help-${question.id}`} className={`${control} min-h-36`} rows={6} maxLength={12000} required disabled={busy || !!pending || capturePending} value={answers[question.id] || ''} onChange={event => edit(question.id, event.target.value)} />
      </div>)}
      <CourseDraftNotice status={draftStatus} />
      {!pending && <button className={button} disabled={busy || capturePending}>Approve this saved revision</button>}
    </form>}
    {pending && canWrite && <div className="space-y-2">
      <p className="text-sm text-gray-700">Your original answers and request are preserved in this tab. Check the saved state before making changes.</p>
      <button type="button" className={button} disabled={busy} onClick={() => { void save(true) }}>Check saved approval</button>
      {canResend && <button type="button" className={button} disabled={busy} onClick={() => { void save() }}>Finish original approval request</button>}
    </div>}
    {selected && <div ref={savedRef} tabIndex={-1} role="region" aria-label="Saved workflow approval" className="min-w-0 space-y-4 border-t border-gray-200 pt-4 outline-offset-4">
      <h5 className="text-base font-semibold text-gray-900">Design saved</h5>
      <p className="text-sm text-gray-700">These are your original saved decisions. They have not been replaced by later revisions or course changes.</p>
      <WorkflowSnapshot value={selected.input_snapshot} />
      {selected.input_snapshot.case.questions.map(question => <div key={question.id} className="space-y-2">
        <h6 className="text-sm font-semibold text-gray-900">{labels[question.id]}</h6>
        <pre tabIndex={0} role="region" aria-label={`Saved ${labels[question.id].toLowerCase()}`} className="max-h-96 min-w-0 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-gray-50 p-2 font-sans text-sm text-gray-900">{selected.submission.answers[question.id]}</pre>
      </div>)}
      <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-gray-900">Workflow approval references</summary><p className="break-all text-sm text-gray-700">{selected.uuid}</p>
        {selected.submission.previous_submission_id && <p className="break-all text-sm text-gray-700">Original design: {selected.submission.previous_submission_id}</p>}
      </details>
      {canWrite && <><button type="button" className={button} disabled={busy} onClick={() => revise(selected)}>Revise these decisions</button>
        <button type="button" className={button} disabled={busy} onClick={() => revise()}>Start a separate approval</button>
        <PracticalAssessment key={selected.uuid} enrollmentId={enrollmentId} moduleId="workflow_design" workflowDesignSubmissionId={selected.uuid} onOpenFeedback={setFeedbackId} />
      </>}
    </div>}
    {listing && <SavedAutomaticReviews key={`${enrollmentId}:${feedbackId}`} enrollmentId={enrollmentId} moduleId="workflow_design" initialAttemptId={feedbackId || undefined} workNavigationDisabled={busy || !!pending || capturePending} onOpenWork={review => { void inspect(review.workflow_design_submission_id!) }} />}
  </section>
}

function WorkflowBrief({ definition }: { definition: WorkflowDesignCaseDefinition }) {
  return <section aria-label="Assigned workflow design case" className="min-w-0 space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-2 text-sm text-gray-900 sm:p-4">
    <h5 className="font-semibold">Your monthly-review workflow assignment</h5><p>{definition.notice}</p><p>{definition.task}</p>
    <p><strong>Intended result: </strong>{definition.intended_output}</p>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inputs and design instructions</summary>
      <ul className="space-y-2">{definition.assigned_inputs.map(item => <li key={item.id}><strong>{item.id}: </strong>{item.description}</li>)}</ul>
      <ol className="mt-3 list-decimal space-y-2 pl-4">{definition.configuration_instructions.map(item => <li key={item}>{item}</li>)}</ol>
    </details>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inspect the flawed workflow proposal</summary><p>{definition.flawed_proposal}</p></details>
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Read the supplied process map</summary><p>{definition.supplied_map.method_and_rationale}</p><p className="mt-3">{definition.supplied_map.ordered_process_map}</p><p className="mt-3">{definition.supplied_map.bounded_task_brief}</p></details>
  </section>
}
