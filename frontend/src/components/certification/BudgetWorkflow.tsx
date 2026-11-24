import { CourseRequestStatus } from './CourseRequestStatus'
import { useCourseDraft, draftStrings } from '../../hooks/useCourseDraft'
import { BudgetReviewForm } from './BudgetReviewForm'
import { CourseDraftNotice } from './CourseDraftNotice'
import { useCourseScopeDraft } from '../../hooks/useCourseScopeDraft'
import { CourseEditorLink } from './CourseEditorLink'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getBudgetWork, getBudgetCalculation, getBudgetCapture, getBudgetRun, getBudgetReview } from '../../api/budgetWorkflow'
import type { BudgetCase, BudgetList, BudgetSaved, BudgetCalculation, BudgetCapture, BudgetRun, BudgetReview, BudgetRequest } from '../../types/budgetWorkflow'
import { connectedId as id, connectedDigest as digest } from './connectedWorkflowState'
import { sameBudgetCase, verifyBudgetCalculation, verifyBudgetCapture, verifyBudgetRun, verifyBudgetReview, validBudgetRequest } from './budgetWorkflowState'
import { useBudgetRequest } from './useBudgetRequest'
import { BudgetCalculationForm, BudgetCalculationEvidence } from './BudgetCalculations'
import { BudgetCaptureEvidence, BudgetRunEvidence } from './BudgetWorkflowEvidence'
import { connectedButton as button, connectedControl as control } from './ConnectedWorkflowEvidence'
import { PracticalAssessment } from './PracticalAssessment'
import { SavedAutomaticReviews } from './SavedAutomaticReviews'

const newId = () => crypto.randomUUID().replaceAll('-', '')
export function BudgetWorkflow({ enrollmentId, definition, historyOnly = false }: { enrollmentId: string; definition: BudgetCase; historyOnly?: boolean }) {
  const [listing, setListing] = useState<BudgetList | null>(null), [error, setError] = useState(''), [reload, setReload] = useState(0)
  useEffect(() => {
    let active = true
    setListing(null); setError('')
    void getBudgetWork(enrollmentId).then(value => {
      if (value.enrollment_id !== enrollmentId || !digest(value.manifest_sha256) || !sameBudgetCase(value.case, definition)
        || value.calculation_fields.length !== 3 || value.module_id !== 'advanced_nodes') throw new Error('Different budget assignment')
      if (active) setListing(value)
    }).catch(() => { if (active) setError('The original budget assignment could not be loaded. Retry to read the saved course.') })
    return () => { active = false }
  }, [enrollmentId, definition, reload])
  if (!listing) return <section aria-label="Budget workflow assessment">{error ? <><p role="alert" className="text-sm text-red-800">{error}</p><button className={button} onClick={() => setReload(value => value + 1)}>Retry loading budget assignment</button></> : <p role="status">Loading budget assignment…</p>}</section>
  return <BudgetWorkspace key={`${enrollmentId}:${definition.case_sha256}:${historyOnly}`} initial={listing} historyOnly={historyOnly} />
}

function BudgetWorkspace({ initial, historyOnly }: { initial: BudgetList; historyOnly: boolean }) {
  const [listing, setListing] = useState(initial), [view, setView] = useState<BudgetSaved | null>(null)
  const [calculation, setCalculation] = useState<BudgetCalculation | null>(null), [editing, setEditing] = useState(false)
  const [workflow, setWorkflow] = useState(''), [selectedRun, setSelectedRun] = useState<BudgetRun | null>(null)
  const [answers, setAnswers] = useState({ calculation_review: '', dependency_review: '' }), [previous, setPrevious] = useState<string | null>(null)
  const [feedbackId, setFeedbackId] = useState(''), [reference, setReference] = useState(''), [referenceKind, setReferenceKind] = useState('run')
  const [reading, setReading] = useState(false), [error, setError] = useState('')
  const sequence = useRef(0), savedRef = useRef<HTMLDivElement>(null), focusSaved = useRef(false)
  const calculationRef = useRef<HTMLDivElement>(null), captureRef = useRef<HTMLFormElement>(null), reviewRef = useRef<HTMLFormElement>(null)
  const [methodDraft, setMethodDraft, methodStatus] = useCourseDraft(['budget-method', listing.enrollment_id, listing.manifest_sha256, listing.case.case_sha256, calculation?.uuid || null, calculation?.calculation_snapshot_sha256 || null, workflow, String(listing.workflows.find(item => item.workflow_id === workflow)?.version || '')], { method: '' }, draftStrings(['method'], 8000))
  const method = methodDraft.method
  const request = useBudgetRequest(listing, value => { focusSaved.current = true; setView(value); setFeedbackId(''); setEditing(false); void refresh() }, !historyOnly)
  const canWrite = !historyOnly && listing.can_submit && !request.blocked
  const locked = reading || request.busy || !!request.pending || request.blocked
  const readLocked = reading || request.busy || !!request.pending
  const run = view && 'run_id' in view ? view as BudgetRun : null
  const review = view && 'run' in view ? view as BudgetReview : null
  const capture = view && 'method_choice' in view ? view as BudgetCapture : null
  const savedCalculation = view && 'checks' in view ? view as BudgetCalculation : null
  useEffect(() => { const counter = sequence; return () => { counter.current++ } }, [])
  useLayoutEffect(() => { if (view && focusSaved.current) { focusSaved.current = false; savedRef.current?.focus() } }, [view])
  async function refresh() {
    const token = sequence.current
    try {
      const value = await getBudgetWork(listing.enrollment_id)
      if (value.enrollment_id !== listing.enrollment_id || value.manifest_sha256 !== listing.manifest_sha256 || !sameBudgetCase(value.case, listing.case)) throw new Error('Different course')
      if (token === sequence.current) setListing({ ...value, case: listing.case })
    } catch { if (token === sequence.current) setError('Saved choices could not be refreshed. Your open evidence is preserved.') }
  }
  async function open(kind: string, referenceId: string) {
    if (readLocked || !id(referenceId)) return
    const token = ++sequence.current
    setReading(true); setError(''); setFeedbackId(''); setView(null)
    try {
      const value = kind === 'calculation' ? verifyBudgetCalculation(await getBudgetCalculation(listing.enrollment_id, referenceId), listing)
        : kind === 'capture' ? verifyBudgetCapture(await getBudgetCapture(listing.enrollment_id, referenceId), listing)
          : kind === 'review' ? verifyBudgetReview(await getBudgetReview(listing.enrollment_id, referenceId), listing)
            : verifyBudgetRun(await getBudgetRun(listing.enrollment_id, referenceId), listing)
      if (('run_id' in value ? value.run_id : value.uuid) !== referenceId) throw new Error('Different reference')
      if (token === sequence.current) { focusSaved.current = true; setView(value); setEditing(false) }
    } catch { if (token === sequence.current) setError('The original saved record could not be opened for this course. Check its reference and try again.') }
    finally { if (token === sequence.current) setReading(false) }
  }
  function send(next: BudgetRequest) {
    if (!canWrite || locked) return
    if (!validBudgetRequest(next, listing.case)) { setError('Check the required explanations, source quotes and amount format before saving.'); return }
    setError(''); void request.send(next)
  }
  function revise(saved: BudgetReview) {
    setSelectedRun(saved.run); setPrevious(saved.uuid); setAnswers(saved.submission.answers); setView(null); setFeedbackId(''); requestAnimationFrame(() => reviewRef.current?.focus())
  }
  return <section aria-label="Budget workflow assessment" className="min-w-0 space-y-4 text-gray-900 [overflow-wrap:anywhere]">
    <h4 className="text-base font-semibold">Choose methods, check arithmetic and inspect dependencies</h4>
    <section aria-label="Budget assignment" className="min-w-0 space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm">
      <p>{listing.case.notice}</p><p>{listing.case.task}</p><p><strong>Intended result: </strong>{listing.case.intended_output}</p>
      <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Budget assignment instructions and limits</summary><ol className="list-decimal space-y-2 pl-4">{listing.case.instructions.map(item => <li key={item}>{item}</li>)}</ol><ul className="mt-3 list-disc space-y-2 pl-4">{listing.case.exclusions.map(item => <li key={item}>{item}</li>)}</ul></details>
      <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Read the authored flawed proposal</summary><p>{listing.case.flawed_proposal}</p></details>
    </section>
    {!canWrite && <p className="text-sm text-gray-700">{historyOnly ? 'Original course history is read-only. New work belongs to your selected course.' : listing.read_only_reason || 'New requests are unavailable until the pending state is restored.'}</p>}
    {(error || request.error) && <p role="alert" className="text-sm text-red-800">{request.error || error}</p>}
    <CourseRequestStatus phase={request.phase || (reading ? 'checking' : null)} action={request.pending?.action} />
    <label className="block text-sm">Open saved budget work<select className={control} disabled={readLocked} value="" onChange={event => { const [kind, key] = event.target.value.split(':'); void open(kind, key) }}>
      <option value="">Choose calculations, a workflow, a run or a review</option>
      {listing.submissions.map((item, index) => <option key={item.submission_id} value={`review:${item.submission_id}`}>Review {index + 1} · {item.submission_id.slice(0, 8)}</option>)}
      {listing.runs.map((item, index) => <option key={item.run_id} value={`run:${item.run_id}`}>Run {index + 1} · {item.state} · {item.run_id.slice(0, 8)}</option>)}
      {listing.captures.map((item, index) => <option key={item.input_snapshot_id} value={`capture:${item.input_snapshot_id}`}>Workflow capture {index + 1} · {item.input_snapshot_id.slice(0, 8)}</option>)}
      {listing.calculations.map((item, index) => <option key={item.calculation_snapshot_id} value={`calculation:${item.calculation_snapshot_id}`}>Calculations {index + 1} · {item.all_arithmetic_supported ? 'additions supported' : 'review needed'} · {item.calculation_snapshot_id.slice(0, 8)}</option>)}
    </select></label>
    <button className={button} disabled={readLocked} onClick={() => { void refresh() }}>Refresh saved budget work</button>
    {(listing.older_calculations_available || listing.older_captures_available || listing.older_runs_available || listing.older_submissions_available) && <p className="text-sm text-gray-700">Only the latest 50 records in each list are shown. Open older work using its saved reference.</p>}
    <details><summary className="min-h-11 cursor-pointer py-2 text-sm">Open a saved budget reference</summary><form className="space-y-2" onSubmit={event => { event.preventDefault(); void open(referenceKind, reference) }}>
      <label className="block text-sm">Record type<select className={control} disabled={readLocked} value={referenceKind} onChange={event => setReferenceKind(event.target.value)}>{['calculation', 'capture', 'run', 'review'].map(kind => <option key={kind} value={kind}>{kind}</option>)}</select></label>
      <label className="block text-sm">Saved reference<input className={control} value={reference} disabled={readLocked} onChange={event => setReference(event.target.value.trim())} pattern="[a-f0-9]{32}" required /></label><button className={button} disabled={readLocked}>Open budget reference</button>
    </form></details>
    {request.pending && <section aria-label="Pending budget request" className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm">
      <p>Your original request is preserved. Checking reads its saved state without running or grading work.</p><button className={button} disabled={request.busy} onClick={() => { void request.check() }}>Check pending budget request</button>
      {request.canFinish && <button className={button} disabled={request.busy} onClick={() => { void request.finish() }}>Finish original budget request</button>}
      {request.canDiscard && <button className={button} disabled={request.busy} onClick={request.discard}>Discard unsaved budget request</button>}
    </section>}
    {view && <div ref={savedRef} tabIndex={-1} role="region" aria-label="Opened budget evidence" className="min-w-0 space-y-3 rounded-lg border border-gray-300 p-3 outline-offset-4">
      {savedCalculation && <><BudgetCalculationEvidence calculation={savedCalculation} />{canWrite && <div className="flex flex-wrap gap-2"><button className={button} disabled={locked} onClick={() => { setCalculation(savedCalculation); setEditing(false); requestAnimationFrame(() => captureRef.current?.focus()) }}>Use these saved calculations</button><button className={button} disabled={locked} onClick={() => { setCalculation(savedCalculation); setEditing(true); requestAnimationFrame(() => calculationRef.current?.focus()) }}>Revise these calculations</button></div>}</>}
      {capture && <><BudgetCaptureEvidence capture={capture} />{canWrite && <button className={button} disabled={locked} onClick={() => send({ action: 'prepare', body: { request_id: newId(), input_snapshot_id: capture.uuid, input_snapshot_sha256: capture.input_snapshot_sha256, case_sha256: listing.case.case_sha256, consent: 'prepare_budget_workflow_plan' } })}>Prepare this saved budget workflow</button>}</>}
      {run && <><BudgetRunEvidence run={run} />{canWrite && <BudgetRunActions key={run.run_id} run={run} locked={locked} send={send} onReview={() => { setSelectedRun(run); setPrevious(null); setView(null); requestAnimationFrame(() => reviewRef.current?.focus()) }} />}</>}
      {review && <><h5 className="text-base font-semibold">Saved calculation and dependency review</h5><p className="text-sm whitespace-pre-wrap">{review.submission.answers.calculation_review}</p><p className="text-sm whitespace-pre-wrap">{review.submission.answers.dependency_review}</p><details><summary className="min-h-11 cursor-pointer py-2 text-sm">Inspect the reviewed budget run</summary><BudgetRunEvidence run={review.run} /></details>{canWrite && <><button className={button} disabled={locked} onClick={() => revise(review)}>Revise this budget review</button><PracticalAssessment key={review.uuid} enrollmentId={listing.enrollment_id} moduleId="advanced_nodes" budgetReviewSubmissionId={review.uuid} onOpenFeedback={setFeedbackId} /></>}</>}
      <p className="break-all text-xs text-gray-600">Saved reference: {'run_id' in view ? view.run_id : view.uuid}</p>
    </div>}
    {canWrite && <>
      <button className={button} disabled={locked} onClick={() => { setCalculation(null); setEditing(!editing || !!calculation); requestAnimationFrame(() => calculationRef.current?.focus()) }}>{editing && !calculation ? 'Close calculation form' : 'Record new calculations'}</button>
      {editing && <div ref={calculationRef} tabIndex={-1} role="region" aria-label="Calculation entry" className="min-w-0 outline-offset-4"><BudgetCalculationForm key={calculation?.uuid || 'new'} listing={listing} original={calculation} locked={locked} onSave={send} /></div>}
      <form ref={captureRef} tabIndex={-1} aria-label="Capture budget workflow" className="min-w-0 space-y-3 rounded-lg border border-gray-300 p-3" onSubmit={event => { event.preventDefault(); if (calculation) send({ action: 'capture', body: { request_id: newId(), workflow_id: workflow, calculation_snapshot_id: calculation.uuid, calculation_snapshot_sha256: calculation.calculation_snapshot_sha256, case_sha256: listing.case.case_sha256, method_choice: method, consent: 'capture_budget_workflow_and_method' } }) }}>
        <h5 className="text-base font-semibold">2. Choose and explain your workflow</h5><p className="text-sm text-gray-700">Open saved calculations and choose “Use these saved calculations” first. In your workflow, place one source-review Prompt (or two independent Prompts in the same step) before one Prompt or Formatter for the internal memo. The memo needs previous step output and workflow documents. Code access is not required.</p>
        <p className="text-sm">Selected calculation record: {calculation?.uuid.slice(0, 8) || 'None selected'}</p>
        <label className="block text-sm">Owned budget workflow<select className={control} required value={workflow} disabled={locked} onChange={event => setWorkflow(event.target.value)}><option value="">Choose a saved workflow</option>{listing.workflows.map(item => <option key={item.workflow_id} value={item.workflow_id}>{item.name} · version {item.version}</option>)}</select></label>
        {listing.workflows.filter(item => item.workflow_id === workflow).map(item => <CourseEditorLink key={item.workflow_id} kind="workflow" artifactId={item.workflow_id} title={item.name} disabled={locked} />)}
        {listing.older_workflows_available && <p className="text-sm">Only your 50 most recently updated workflows are shown.</p>}
        <label className="block text-sm">{listing.case.questions.find(question => question.id === 'method_choice')?.prompt}<textarea className={`${control} min-h-36`} rows={6} minLength={30} maxLength={8000} required disabled={locked || !calculation || !workflow} value={method} onChange={event => setMethodDraft({ method: event.target.value })} /></label>
        <CourseDraftNotice status={methodStatus} />
        <button className={button} disabled={locked || !calculation}>Save workflow and method decision</button>
      </form>
      {selectedRun && <BudgetReviewForm key={`${selectedRun.run_id}:${previous || 'original'}`} formRef={reviewRef} run={selectedRun} previous={previous}
        initialAnswers={previous ? answers : { calculation_review: '', dependency_review: '' }} locked={locked} send={send} />}

    </>}
    <SavedAutomaticReviews key={`${listing.enrollment_id}:${feedbackId}`} enrollmentId={listing.enrollment_id} moduleId="advanced_nodes" initialAttemptId={feedbackId || undefined} workNavigationDisabled={readLocked} onOpenWork={review => { void open('review', review.budget_review_submission_id!) }} />
  </section>
}

function BudgetRunActions({ run, locked, send, onReview }: { run: BudgetRun; locked: boolean; send: (request: BudgetRequest) => void; onReview: () => void }) {
  const { choice, setChoice, reason, setReason, status } = useCourseScopeDraft('budget-scope', run)
  return <div className="space-y-3">
    {run.scope_decision && <p className="text-sm">Saved scope choice: {run.scope_decision.submission.choice}. {run.scope_decision.submission.reason}</p>}
    {run.can_save_scope && <form aria-label="Approve budget scope" className="space-y-3" onSubmit={event => { event.preventDefault(); send({ action: 'scope', body: { request_id: newId(), run_id: run.run_id, plan_sha256: run.plan_sha256, case_sha256: run.case_sha256, choice, reason, consent: 'save_budget_workflow_scope_decision' } }) }}>
      <p className="text-sm">Inspect the saved source, calculations, task inputs and models. Approval permits only this internal memo run and may incur model usage.</p>
      <label className="block text-sm">Budget execution choice<select className={control} value={choice} disabled={locked} onChange={event => setChoice(event.target.value as typeof choice)}><option value="hold">Hold for correction</option><option value="approve">Approve this exact internal run</option></select></label>
      <label className="block text-sm">Explain this scope decision<textarea className={control} rows={3} required minLength={10} maxLength={4000} disabled={locked} value={reason} onChange={event => setReason(event.target.value)} /></label><CourseDraftNotice status={status} /><button className={button} disabled={locked}>Save budget scope decision</button>
    </form>}
    {run.can_execute && <button className={button} disabled={locked} onClick={() => send({ action: 'execute', body: { run_id: run.run_id, plan_sha256: run.plan_sha256, scope_decision_id: run.scope_decision_id!, scope_decision_sha256: run.scope_decision_sha256!, consent: 'execute_approved_budget_workflow' } })}>Run this approved budget workflow</button>}
    {run.can_finalize && <button className={button} disabled={locked} onClick={() => send({ action: 'finalize', body: { run_id: run.run_id, plan_sha256: run.plan_sha256, authorization_sha256: run.authorization_sha256!, task_events_sha256: run.task_events_sha256, consent: 'finalize_saved_budget_results_without_reexecution' } })}>Finalize saved budget results without rerunning</button>}
    {run.state === 'completed' && <button className={button} disabled={locked} onClick={onReview}>Review this completed budget run</button>}
  </div>
}
