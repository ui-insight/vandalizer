import { CourseRequestStatus } from './CourseRequestStatus'
import { ConnectedComparisonForm, connectedAnswerLabels as answerLabels } from './ConnectedComparisonForm'
import { useCourseDraft } from '../../hooks/useCourseDraft'
import { CourseDraftNotice } from './CourseDraftNotice'
import { CourseEditorLink } from './CourseEditorLink'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getConnectedCapture, getConnectedReview, getConnectedRun, getConnectedWork, getConnectedRecoveryDecision } from '../../api/connectedWorkflow'
import type { ConnectedCase, ConnectedList, ConnectedRequest, ConnectedReview, ConnectedRun, ConnectedSaved } from '../../types/connectedWorkflow'
import { connectedId, connectedDigest, sameConnectedCase, verifyConnectedCapture, verifyConnectedReview, verifyConnectedRun, verifyConnectedRecovery } from './connectedWorkflowState'
import { ConnectedRecoveryForm, ConnectedRecoveryEvidence } from './ConnectedRecoveryPractice'
import { ConnectedCaptureEvidence, ConnectedRunEvidence, EvidenceText, connectedButton as button, connectedControl as control } from './ConnectedWorkflowEvidence'
import { useConnectedRequest } from './useConnectedRequest'
import { PracticalAssessment } from './PracticalAssessment'
import { SavedAutomaticReviews } from './SavedAutomaticReviews'

const newId = () => crypto.randomUUID().replaceAll('-', '')
export function ConnectedWorkflow({ enrollmentId, definition, historyOnly = false }: { enrollmentId: string; definition: ConnectedCase; historyOnly?: boolean }) {
  const [listing, setListing] = useState<ConnectedList | null>(null), [error, setError] = useState(''), [reload, setReload] = useState(0)
  useEffect(() => {
    let active = true
    setListing(null); setError('')
    void getConnectedWork(enrollmentId).then(value => {
      if (value.enrollment_id !== enrollmentId || value.module_id !== 'multi_step' || !connectedDigest(value.manifest_sha256)
        || !sameConnectedCase(value.case, definition)) throw new Error('Different connected course')
      if (active) setListing(value)
    }).catch(() => { if (active) setError('The original connected-workflow assignment could not be loaded. Retry to read the saved course.') })
    return () => { active = false }
  }, [enrollmentId, definition, reload])
  if (!listing) return <section aria-label="Connected workflow assessment">{error ? <><p role="alert" className="text-sm text-red-800">{error}</p><button className={button} onClick={() => setReload(value => value + 1)}>Retry loading assignment</button></> : <p role="status">Loading connected-workflow assignment…</p>}</section>
  return <ConnectedWorkspace key={`${enrollmentId}:${definition.case_sha256}:${historyOnly}`} initial={listing} historyOnly={historyOnly} />
}

function ConnectedWorkspace({ initial, historyOnly }: { initial: ConnectedList; historyOnly: boolean }) {
  const [listing, setListing] = useState(initial)
  const [view, setView] = useState<ConnectedSaved | null>(null), [workflow, setWorkflow] = useState('')
  const [original, setOriginal] = useState<ConnectedRun | null>(null), [corrected, setCorrected] = useState<ConnectedRun | null>(null)
  const [answers, setAnswers] = useState({ connection_repair: '', source_review: '' }), [previous, setPrevious] = useState<string | null>(null)
  const [feedbackId, setFeedbackId] = useState(''), [reference, setReference] = useState(''), [referenceKind, setReferenceKind] = useState('run')
  const [reading, setReading] = useState(false), [error, setError] = useState('')
  const sequence = useRef(0), focusSaved = useRef(false), savedRef = useRef<HTMLDivElement>(null)
  const focusComparison = useRef(false), comparisonRef = useRef<HTMLFormElement>(null)
  const request = useConnectedRequest(listing, value => { focusSaved.current = true; setView(value); setFeedbackId(''); void refresh() }, !historyOnly)
  const canWrite = !historyOnly && listing.can_submit && !request.blocked
  const locked = reading || request.busy || !!request.pending || request.blocked
  const readLocked = reading || request.busy || !!request.pending
  const run = view && 'run_id' in view ? view : null
  const review = view && 'original_run' in view ? view : null
  const capture = view && 'documents' in view ? view : null
  const recovery = view && 'stopped_run' in view ? view : null
  useEffect(() => { const counter = sequence; return () => { counter.current++ } }, [])
  useLayoutEffect(() => {
    if (view && focusSaved.current) { focusSaved.current = false; savedRef.current?.focus() }
    if (!view && focusComparison.current) { focusComparison.current = false; comparisonRef.current?.focus() }
  }, [view])
  async function refresh() {
    const token = sequence.current
    try {
      const value = await getConnectedWork(listing.enrollment_id)
      if (value.enrollment_id !== listing.enrollment_id || value.manifest_sha256 !== listing.manifest_sha256 || !sameConnectedCase(value.case, listing.case)) throw new Error('Different course')
      if (token === sequence.current) setListing({ ...value, case: listing.case })
    } catch { if (token === sequence.current) setError('Saved choices could not be refreshed. Your open evidence is preserved.') }
  }
  async function open(kind: string, id: string) {
    if (readLocked || !connectedId(id)) return
    const token = ++sequence.current
    setReading(true); setError(''); setFeedbackId(''); setView(null)
    try {
      const value = kind === 'capture' ? verifyConnectedCapture(await getConnectedCapture(listing.enrollment_id, id), listing)
        : kind === 'review' ? verifyConnectedReview(await getConnectedReview(listing.enrollment_id, id), listing)
          : kind === 'recovery' ? verifyConnectedRecovery(await getConnectedRecoveryDecision(listing.enrollment_id, id), listing)
          : verifyConnectedRun(await getConnectedRun(listing.enrollment_id, id), listing)
      if (('run_id' in value ? value.run_id : value.uuid) !== id) throw new Error('Different saved reference')
      if (token === sequence.current) { focusSaved.current = true; setView(value) }
    } catch { if (token === sequence.current) setError('The original saved record could not be opened for this course. Check its reference and try again.') }
    finally { if (token === sequence.current) setReading(false) }
  }
  function send(next: ConnectedRequest) { if (canWrite && !locked) void request.send(next) }
  function revise(saved: ConnectedReview) {
    focusComparison.current = true
    setOriginal(saved.original_run); setCorrected(saved.corrected_run); setAnswers(saved.submission.answers); setPrevious(saved.uuid); setView(null); setFeedbackId('')
  }
  return <section aria-label="Connected workflow assessment" className="min-w-0 space-y-4 [overflow-wrap:anywhere]">
    <h4 className="text-base font-semibold text-gray-900">Run, inspect and repair a connected workflow</h4>
    <section aria-label="Connected workflow assignment" className="min-w-0 space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-gray-900">
      <p>{listing.case.notice}</p><p>{listing.case.task}</p><p><strong>Intended result: </strong>{listing.case.intended_output}</p>
      <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Assignment instructions and limits</summary><ol className="list-decimal space-y-2 pl-4">{listing.case.instructions.map(item => <li key={item}>{item}</li>)}</ol><ul className="mt-3 list-disc space-y-2 pl-4">{listing.case.exclusions.map(item => <li key={item}>{item}</li>)}</ul></details>
      <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Read the authored flawed example</summary><p>{listing.case.flawed_example.notice}</p><p className="mt-2">{listing.case.flawed_example.routing}</p><p className="mt-2">{listing.case.flawed_example.analysis}</p><p className="mt-2">{listing.case.flawed_example.final_summary}</p></details>
    </section>
    {!canWrite && <p className="text-sm text-gray-700">{historyOnly ? 'Original course history is read-only. New work belongs to your selected course.' : listing.read_only_reason || 'New requests are unavailable until the pending state can be restored.'}</p>}
    {(error || request.error) && <p role="alert" className="text-sm text-red-800">{request.error || error}</p>}
    <CourseRequestStatus phase={request.phase || (reading ? 'checking' : null)} action={request.pending?.action} />
    <label className="block text-sm text-gray-900">Open saved connected work<select className={control} disabled={readLocked} value="" onChange={event => { const [kind, id] = event.target.value.split(':'); void open(kind, id) }}>
      <option value="">Choose a capture, run or comparison</option>
      {listing.submissions.map((item, index) => <option key={item.submission_id} value={`review:${item.submission_id}`}>Comparison {index + 1} · {item.submission_id.slice(0, 8)}</option>)}
      {(listing.recovery_submissions || []).map((item, index) => <option key={item.submission_id} value={`recovery:${item.submission_id}`}>Recovery choices {index + 1} · {item.submission_id.slice(0, 8)}</option>)}
      {listing.runs.map((item, index) => <option key={item.run_id} value={`run:${item.run_id}`}>Run {index + 1} · {item.state} · {item.run_id.slice(0, 8)}</option>)}
      {listing.captures.map((item, index) => <option key={item.input_snapshot_id} value={`capture:${item.input_snapshot_id}`}>Capture {index + 1} · {item.input_snapshot_id.slice(0, 8)}</option>)}
    </select></label>
    <button className={button} disabled={readLocked} onClick={() => { void refresh() }}>Refresh saved choices</button>
    <details><summary className="min-h-11 cursor-pointer py-2 text-sm text-gray-900">Open older evidence by reference</summary>
      <p className="text-sm text-gray-700">Each list shows up to 50 records. Your original reference can open older saved evidence.</p>
      <form className="space-y-2" onSubmit={event => { event.preventDefault(); void open(referenceKind, reference.trim()) }}>
        <label className="block text-sm text-gray-900">Evidence type<select className={control} value={referenceKind} disabled={readLocked} onChange={event => setReferenceKind(event.target.value)}><option value="run">Run</option><option value="capture">Capture</option><option value="review">Comparison</option><option value="recovery">Recovery choices</option></select></label>
        <label className="block text-sm text-gray-900">Full evidence reference<input className={control} value={reference} disabled={readLocked} pattern="[a-f0-9]{32}" required onChange={event => setReference(event.target.value)} /></label><button className={button} disabled={readLocked}>Open original evidence</button>
      </form>
    </details>
    {request.pending && !historyOnly && <section aria-label="Pending connected request" className="space-y-2 rounded-lg border border-amber-300 p-3 text-sm text-gray-900">
      <p>The original {request.pending.action} request is preserved in this tab. Check its saved state before editing or sending again.</p>
      <button className={button} disabled={request.busy || reading} onClick={() => { void request.check() }}>Check pending request</button>
      {canWrite && request.canFinish && <button className={button} disabled={request.busy || reading} onClick={() => { void request.finish() }}>Finish original request</button>}
      {canWrite && request.canDiscard && <button className={button} disabled={request.busy || reading} onClick={request.discard}>Clear confirmed unsaved request</button>}
    </section>}
    {canWrite && <form aria-label="Capture connected revision" className="space-y-3 border-t border-gray-200 pt-4" onSubmit={event => { event.preventDefault(); send({ action: 'capture', body: { request_id: newId(), workflow_id: workflow, case_sha256: listing.case.case_sha256, consent: 'capture_connected_workflow_inputs' } }) }}>
      <h5 className="text-base font-semibold text-gray-900">1. Capture your saved workflow</h5>
      <p className="text-sm text-gray-700">Prepare the assigned three-stage workflow in chat or the editor, then return here. Capture saves its configuration and assigned source; execution requires a separate approval.</p>
      <label className="block text-sm text-gray-900">Saved workflow<select className={control} required disabled={locked} value={workflow} onChange={event => setWorkflow(event.target.value)}><option value="">Choose your workflow</option>{listing.workflows.map(item => <option key={item.workflow_id} value={item.workflow_id}>{item.name} · revision {item.version}</option>)}{workflow && !listing.workflows.some(item => item.workflow_id === workflow) && <option value={workflow}>Workflow by reference</option>}</select></label>
      {listing.workflows.filter(item => item.workflow_id === workflow).map(item => <CourseEditorLink key={item.workflow_id} kind="workflow" artifactId={item.workflow_id} title={item.name} disabled={locked} />)}
      {!listing.workflows.length && <p className="text-sm text-gray-700">Save a workflow in your workspace, then refresh the choices.</p>}
      {listing.older_workflows_available && <label className="block text-sm text-gray-900">Older workflow reference<input className={control} pattern="[a-f0-9]{24}" value={workflow} disabled={locked} onChange={event => setWorkflow(event.target.value)} /></label>}
      <button className={button} disabled={locked || !workflow}>Capture selected workflow and source</button>
    </form>}
    {view && <div ref={savedRef} tabIndex={-1} role="region" aria-label="Opened connected evidence" className="min-w-0 space-y-4 outline-offset-4">
      {capture && <><ConnectedCaptureEvidence capture={capture} />{canWrite && <><button className={button} disabled={locked} onClick={() => send({ action: 'prepare', body: { request_id: newId(), input_snapshot_id: capture.uuid, input_snapshot_sha256: capture.input_snapshot_sha256, case_sha256: listing.case.case_sha256, consent: 'prepare_connected_workflow_plan' } })}>Prepare this captured revision</button>
        {listing.case.controlled_failure_practice && <section className="space-y-2 rounded-lg border border-amber-300 p-3 text-sm text-gray-900"><h5 className="font-semibold">Practice recovery with your own saved work</h5><p>{listing.case.controlled_failure_practice.notice}</p><button className={button} disabled={locked} onClick={() => send({ action: 'prepare', body: { request_id: newId(), input_snapshot_id: capture.uuid, input_snapshot_sha256: capture.input_snapshot_sha256, case_sha256: listing.case.case_sha256, consent: 'prepare_controlled_failure_rehearsal' } })}>Prepare disclosed stopped-run rehearsal</button></section>}
      </>}</>}
      {run && <><ConnectedRunEvidence run={run} />
        {canWrite && run.can_save_scope && <ScopeForm key={run.run_id + ':' + run.scope_decision_id} run={run} question={run.approval_question?.prompt || listing.case.questions.find(item => item.id === 'scope_approval')!.prompt} disabled={locked} send={send} />}
        {canWrite && run.can_execute && <section className="space-y-2"><p className="text-sm text-gray-700">{run.execution_purpose === 'controlled_failure_rehearsal' ? 'This approved rehearsal calls the extraction model and may incur usage. It then saves a disclosed rejection before reasoning dispatch; no final draft is produced.' : 'Run the exact approved revision on its saved assigned source. This starts model calls and may incur usage. It produces an internal draft.'}</p><button className={button} disabled={locked} onClick={() => send({ action: 'execute', body: { run_id: run.run_id, plan_sha256: run.plan_sha256, scope_decision_id: run.scope_decision_id!, scope_decision_sha256: run.scope_decision_sha256!, consent: 'execute_approved_connected_workflow' } })}>{run.execution_purpose === 'controlled_failure_rehearsal' ? 'Run approved stopped-run rehearsal' : 'Run this approved revision'}</button></section>}
        {canWrite && run.execution_purpose === 'controlled_failure_rehearsal' && run.state === 'failed' && run.result?.reason === 'controlled_training_rejection_before_reasoning_provider' && <ConnectedRecoveryForm key={`recovery:${run.run_id}`} run={run} disabled={locked} send={send} />}
        {canWrite && run.can_finalize && <section className="space-y-2"><p className="text-sm text-gray-700">Every stage result is saved. Finalize the receipt without calling providers again.</p><button className={button} disabled={locked} onClick={() => send({ action: 'finalize', body: { run_id: run.run_id, plan_sha256: run.plan_sha256, authorization_sha256: run.authorization_sha256!, stage_events_sha256: run.stage_events_sha256, consent: 'finalize_saved_connected_results_without_reexecution' } })}>Finalize saved results</button></section>}
        {canWrite && run.state === 'completed' && <div className="flex flex-wrap gap-2"><button className={button} disabled={locked} onClick={() => { setOriginal(run); setPrevious(null) }}>Use as original run</button><button className={button} disabled={locked} onClick={() => { setCorrected(run); setPrevious(null) }}>Use as corrected run</button></div>}
      </>}
      {recovery && <ConnectedRecoveryEvidence key={recovery.uuid} saved={recovery} canWrite={canWrite} disabled={locked} send={send} />}
      {review && <><h5 className="text-base font-semibold text-gray-900">Comparison saved</h5><p className="text-sm text-gray-700">Both executions and your original answers are preserved with this review.</p>
        <details><summary className="min-h-11 cursor-pointer py-2 text-sm font-semibold">Inspect original run</summary><ConnectedRunEvidence run={review.original_run} /></details>
        <details><summary className="min-h-11 cursor-pointer py-2 text-sm font-semibold">Inspect corrected run</summary><ConnectedRunEvidence run={review.corrected_run} /></details>
        {Object.entries(answerLabels).map(([id, label]) => <div key={id} className="space-y-2"><h6 className="text-sm font-semibold text-gray-900">{label}</h6><EvidenceText label={`Saved ${label.toLowerCase()}`} value={review.submission.answers[id as keyof typeof answers]} /></div>)}
        <p className="break-all text-sm text-gray-700">Comparison reference: {review.uuid}</p>
        {canWrite && <><button className={button} disabled={locked} onClick={() => revise(review)}>Revise comparison answers</button><PracticalAssessment key={review.uuid} enrollmentId={listing.enrollment_id} moduleId="multi_step" connectedReviewSubmissionId={review.uuid} onOpenFeedback={setFeedbackId} /></>}
      </>}
    </div>}
    {canWrite && !review && <ConnectedComparisonForm formRef={comparisonRef} listing={listing} original={original} corrected={corrected} previous={previous}
      initialAnswers={previous ? answers : { connection_repair: '', source_review: '' }} locked={locked} send={send} />}
    <SavedAutomaticReviews key={`${listing.enrollment_id}:${feedbackId}`} enrollmentId={listing.enrollment_id} moduleId="multi_step" initialAttemptId={feedbackId || undefined} workNavigationDisabled={readLocked} onOpenWork={review => { void open('review', review.connected_review_submission_id!) }} />
  </section>
}

function ScopeForm({ run, question, disabled, send }: { run: ConnectedRun; question: string; disabled: boolean; send: (next: ConnectedRequest) => void }) {
  type ScopeDraft = { choice: '' | 'approve' | 'hold'; reason: string }
  const valid = (value: unknown): value is ScopeDraft => !!value && typeof value === 'object'
    && ['', 'approve', 'hold'].includes((value as ScopeDraft).choice)
    && typeof (value as ScopeDraft).reason === 'string' && (value as ScopeDraft).reason.length <= 4000
  const [{ choice, reason }, setDraft, status] = useCourseDraft<ScopeDraft>(
    ['connected-scope', run.enrollment_id, run.manifest_sha256, run.run_id, run.plan_sha256, run.case_sha256, run.scope_decision_id, run.scope_decision_sha256],
    { choice: '', reason: '' }, valid)
  const setChoice = (choice: ScopeDraft['choice']) => setDraft(draft => ({ ...draft, choice }))
  const setReason = (reason: string) => setDraft(draft => ({ ...draft, reason }))
  return <form aria-label="Approve or hold connected run" className="space-y-3 rounded-lg border border-gray-200 p-3" onSubmit={event => { event.preventDefault(); send({ action: 'scope', body: { request_id: newId(), run_id: run.run_id, plan_sha256: run.plan_sha256, case_sha256: run.case_sha256, choice: choice as 'approve' | 'hold', reason, consent: 'save_connected_workflow_scope_decision' } }) }}>
    <h5 className="text-base font-semibold text-gray-900">Inspect the plan and choose its scope</h5><p className="text-sm text-gray-700">{question}</p>
    <label className="block text-sm text-gray-900">Scope choice<select className={control} required disabled={disabled} value={choice} onChange={event => setChoice(event.target.value as typeof choice)}><option value="">Choose approve or hold</option><option value="approve">Approve this revision and assigned source</option><option value="hold">Hold this run</option></select></label>
    <label className="block text-sm text-gray-900">Explain your scope choice<textarea className={`${control} min-h-28`} rows={4} required minLength={10} maxLength={4000} disabled={disabled} value={reason} onChange={event => setReason(event.target.value)} /></label>
    <CourseDraftNotice status={status} />
    <button className={button} disabled={disabled || !choice || reason.trim().length < 10}>Save scope choice</button>
  </form>
}
