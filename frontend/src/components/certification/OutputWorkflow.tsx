import { CourseRequestStatus } from './CourseRequestStatus'
import { CourseEditorLink } from './CourseEditorLink'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getOutputWork, getOutputCapture, getOutputRun, getOutputInspection, getOutputHandoff, getOutputReview } from '../../api/outputWorkflow'
import type { OutputCase, OutputHandoff, OutputInspection, OutputList, OutputRequest, OutputRun, OutputSaved } from '../../types/outputWorkflow'
import { connectedId as id } from './connectedWorkflowState'
import { sameOutputCase, validOutputRequest, verifyOutputCapture, verifyOutputRun, verifyOutputInspection, verifyOutputHandoff, verifyOutputReview } from './outputWorkflowState'
import { useOutputRequest } from './useOutputRequest'
import { OutputCaptureEvidence, OutputRunEvidence, OutputHandoffEvidence, outputButton as button, outputControl as control } from './OutputWorkflowEvidence'
import { OutputInspectionForm, OutputInterpretationForm, OutputRunActions, newOutputId } from './OutputWorkflowForms'
import { PracticalAssessment } from './PracticalAssessment'
import { SavedAutomaticReviews } from './SavedAutomaticReviews'

type ReadKind = 'capture' | 'run' | 'inspection' | 'handoff' | 'review'
export function OutputWorkflow({ enrollmentId, definition, historyOnly = false }: { enrollmentId: string; definition: OutputCase; historyOnly?: boolean }) {
  const [listing, setListing] = useState<OutputList | null>(null), [error, setError] = useState(''), [reload, setReload] = useState(0)
  useEffect(() => {
    let active = true
    setListing(null); setError('')
    void getOutputWork(enrollmentId).then(value => {
      if (value.enrollment_id !== enrollmentId || value.module_id !== 'output_delivery' || !sameOutputCase(value.case, definition)) throw new Error('Different output assignment')
      if (active) setListing(value)
    }).catch(() => { if (active) setError('The original output assignment could not be loaded. Retry to read the saved course.') })
    return () => { active = false }
  }, [enrollmentId, definition, reload])
  if (!listing) return <section aria-label="Output and delivery assessment">{error ? <><p role="alert" className="text-sm text-red-800">{error}</p><button className={button} onClick={() => setReload(value => value + 1)}>Retry loading output assignment</button></> : <p role="status">Loading output assignment…</p>}</section>
  return <OutputWorkspace key={`${enrollmentId}:${definition.case_sha256}:${historyOnly}`} initial={listing} historyOnly={historyOnly} />
}
function OutputWorkspace({ initial, historyOnly }: { initial: OutputList; historyOnly: boolean }) {
  const [listing, setListing] = useState(initial), [view, setView] = useState<OutputSaved | null>(null)
  const [workflow, setWorkflow] = useState(''), [inspectionRun, setInspectionRun] = useState<OutputRun | null>(null)
  const [selected, setSelected] = useState<{ inspection: OutputInspection; handoff: OutputHandoff; previous: string | null } | null>(null)
  const [interpretation, setInterpretation] = useState(''), [currentRelease, setCurrentRelease] = useState<OutputRun | null>(null)
  const [feedbackId, setFeedbackId] = useState(''), [reference, setReference] = useState(''), [referenceKind, setReferenceKind] = useState<ReadKind>('run')
  const [reading, setReading] = useState(false), [error, setError] = useState('')
  const sequence = useRef(0), focusSaved = useRef(false), savedRef = useRef<HTMLDivElement>(null)
  const inspectionRef = useRef<HTMLDivElement>(null), interpretationRef = useRef<HTMLFormElement>(null), captureRef = useRef<HTMLFormElement>(null)
  const request = useOutputRequest(listing, value => {
    focusSaved.current = true; setView(value); setFeedbackId(''); setInspectionRun(null); setSelected(null); setCurrentRelease(null); void refresh()
  }, !historyOnly)
  const canWrite = !historyOnly && listing.can_submit && !request.blocked
  const locked = reading || request.busy || !!request.pending || request.blocked
  const readLocked = reading || request.busy || !!request.pending
  const run = view && 'input_snapshot' in view ? view : null
  const capture = view && 'artifact' in view ? view : null
  const inspection = view && 'review_sha256' in view ? view : null
  const handoff = view && 'handoff_sha256' in view ? view : null
  const review = view && 'file_review' in view ? view : null
  useEffect(() => { const counter = sequence; return () => { counter.current++ } }, [])
  useLayoutEffect(() => { if (view && focusSaved.current) { focusSaved.current = false; savedRef.current?.focus() } }, [view])
  async function refresh() {
    const token = sequence.current
    try {
      const value = await getOutputWork(listing.enrollment_id)
      if (value.enrollment_id !== listing.enrollment_id || value.manifest_sha256 !== listing.manifest_sha256 || !sameOutputCase(value.case, listing.case)) throw new Error('Different course')
      if (token === sequence.current) setListing({ ...value, case: listing.case })
    } catch { if (token === sequence.current) setError('Saved output choices could not be refreshed. Your open evidence is preserved.') }
  }
  async function open(kind: ReadKind, key: string) {
    if (readLocked || !id(key)) return
    const token = ++sequence.current
    setReading(true); setError(''); setFeedbackId(''); setView(null); setInspectionRun(null); setSelected(null); setCurrentRelease(null)
    try {
      const value = kind === 'capture' ? verifyOutputCapture(await getOutputCapture(listing.enrollment_id, key), listing)
        : kind === 'run' ? verifyOutputRun(await getOutputRun(listing.enrollment_id, key), listing)
          : kind === 'inspection' ? verifyOutputInspection(await getOutputInspection(listing.enrollment_id, key), listing)
            : kind === 'handoff' ? verifyOutputHandoff(await getOutputHandoff(listing.enrollment_id, key), listing)
              : verifyOutputReview(await getOutputReview(listing.enrollment_id, key), listing)
      if (('input_snapshot' in value ? value.run_id : value.uuid) !== key) throw new Error('Different reference')
      if (token === sequence.current) { focusSaved.current = true; setView(value) }
    } catch { if (token === sequence.current) setError('The original saved record could not be opened for this course. Check its reference and try again.') }
    finally { if (token === sequence.current) setReading(false) }
  }
  function send(next: OutputRequest) {
    if (!canWrite || locked) return
    if (!validOutputRequest(next, listing.case)) { setError('Complete the required inspection and explanations. Approval requires opening every file and the bundle, with each file judged usable.'); return }
    setError(''); void request.send(next)
  }
  async function readCurrentRelease(saved: OutputHandoff) {
    if (locked || !canWrite) return
    const token = ++sequence.current
    setReading(true); setError(''); setCurrentRelease(null)
    try {
      const latest = verifyOutputRun(await getOutputRun(listing.enrollment_id, saved.run_id), listing)
      if (latest.result_sha256 !== saved.submission.result_sha256) throw new Error('Different files')
      if (token === sequence.current) setCurrentRelease(latest)
    } catch { if (token === sequence.current) setError('The current release could not be checked. Keep the original failed receipt and try reading again.') }
    finally { if (token === sequence.current) setReading(false) }
  }
  function selectInterpretation(savedInspection: OutputInspection, savedHandoff: OutputHandoff, previous: string | null, answer = '') {
    setSelected({ inspection: savedInspection, handoff: savedHandoff, previous }); setInterpretation(answer.length <= 8000 ? answer : '')
    setView(null); setInspectionRun(null); setFeedbackId(''); requestAnimationFrame(() => interpretationRef.current?.focus())
  }
  async function beginInterpretation(saved: OutputHandoff) {
    if (locked || !canWrite) return
    const token = ++sequence.current
    setReading(true); setError('')
    try {
      const original = verifyOutputInspection(await getOutputInspection(listing.enrollment_id, saved.submission.review_id), listing)
      if (original.review_sha256 !== saved.submission.review_sha256) throw new Error('Different approval')
      if (token === sequence.current) selectInterpretation(original, saved, null)
    } catch { if (token === sequence.current) setError('The original inspection could not be read for this handoff. Preserve the receipt and try again.') }
    finally { if (token === sequence.current) setReading(false) }
  }
  function attempt(saved: OutputInspection) {
    send({ action: 'handoff', body: { request_id: newOutputId(), run_id: saved.run.run_id, result_sha256: saved.submission.result_sha256,
      review_id: saved.uuid, review_sha256: saved.review_sha256, artifacts_sha256: saved.submission.artifacts_sha256,
      destination_id: 'private_training_inbox', action: 'attempt', previous_failed_id: null, previous_failed_sha256: null, consent: 'attempt_approved_private_training_handoff' } })
  }
  function retry(saved: OutputHandoff, latest: OutputRun) {
    const choice = latest.release_decision
    if (!choice || choice.submission.choice !== 'approve') return
    send({ action: 'handoff', body: { request_id: newOutputId(), run_id: saved.run_id, result_sha256: saved.submission.result_sha256,
      review_id: choice.uuid, review_sha256: choice.review_sha256, artifacts_sha256: saved.submission.artifacts_sha256,
      destination_id: 'private_training_inbox', action: 'retry_failed_handoff', previous_failed_id: saved.uuid, previous_failed_sha256: saved.handoff_sha256,
      consent: 'retry_only_failed_private_training_handoff' } })
  }
  return <section aria-label="Output and delivery assessment" className="min-w-0 space-y-4 text-gray-900 [overflow-wrap:anywhere]">
    <h4 className="text-base font-semibold">Generate, inspect and hand off exact files</h4>
    <section aria-label="Output assignment" className="min-w-0 space-y-3 rounded-lg border border-amber-300 bg-amber-50 px-1.5 py-3 sm:p-3 text-sm"><p>{listing.case.notice}</p><p>{listing.case.task}</p>
      <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Output assignment instructions and limits</summary><ol className="list-decimal space-y-2 pl-4">{listing.case.instructions.map(item => <li key={item}>{item}</li>)}</ol><ul className="mt-3 list-disc space-y-2 pl-4">{listing.case.exclusions.map(item => <li key={item}>{item}</li>)}</ul></details>
      <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Read the authored flawed handoff proposal</summary><p>{listing.case.flawed_proposal}</p></details>
    </section>
    {!canWrite && <p className="text-sm text-gray-700">{historyOnly ? 'Original course history is read-only. New work belongs to your selected course.' : listing.read_only_reason || 'New requests are unavailable until the pending state is restored.'}</p>}
    {(error || request.error) && <p role="alert" className="text-sm text-red-800">{request.error || error}</p>}
    <CourseRequestStatus phase={request.phase || (reading ? 'checking' : null)} action={request.pending?.action} />
    <label className="block text-sm">Open saved output work<select className={control} disabled={readLocked} value="" onChange={event => { const [kind, key] = event.target.value.split(':'); void open(kind as ReadKind, key) }}>
      <option value="">Choose a workflow, run, inspection, handoff or review</option>
      {(['submissions', 'handoffs', 'inspections'] as const).flatMap(kind => listing[kind].map((item, index) => <option key={item.submission_id} value={`${kind === 'submissions' ? 'review' : kind === 'handoffs' ? 'handoff' : 'inspection'}:${item.submission_id}`}>{kind === 'submissions' ? 'Outcome review' : kind === 'handoffs' ? 'Handoff' : 'File inspection'} {index + 1} · {item.status || item.choice || item.submission_id.slice(0, 8)}</option>))}
      {listing.runs.map((item, index) => <option key={item.run_id} value={`run:${item.run_id}`}>Generation {index + 1} · {item.state} · {item.run_id.slice(0, 8)}</option>)}
      {listing.captures.map((item, index) => <option key={item.input_snapshot_id} value={`capture:${item.input_snapshot_id}`}>Workflow capture {index + 1} · {item.input_snapshot_id.slice(0, 8)}</option>)}
    </select></label>
    <button className={button} disabled={readLocked} onClick={() => { void refresh() }}>Refresh saved output work</button>
    {(listing.older_captures_available || listing.older_runs_available || listing.older_inspections_available || listing.older_handoffs_available || listing.older_submissions_available) && <p className="text-sm">Only the latest 50 records in each list are shown. Open older work by its saved reference.</p>}
    <details><summary className="min-h-11 cursor-pointer py-2 text-sm">Open a saved output reference</summary><form className="space-y-2" onSubmit={event => { event.preventDefault(); void open(referenceKind, reference) }}>
      <label className="block text-sm">Output record type<select className={control} disabled={readLocked} value={referenceKind} onChange={event => setReferenceKind(event.target.value as ReadKind)}>{['capture', 'run', 'inspection', 'handoff', 'review'].map(kind => <option key={kind} value={kind}>{kind}</option>)}</select></label>
      <label className="block text-sm">Saved output reference<input className={control} disabled={readLocked} value={reference} onChange={event => setReference(event.target.value.trim())} pattern="[a-f0-9]{32}" required /></label><button className={button} disabled={readLocked}>Open output reference</button>
    </form></details>
    {request.pending && <section aria-label="Pending output request" className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 px-1.5 py-3 sm:p-3 text-sm"><p>Your original request is preserved. Checking reads its state without generating, handing off or grading work.</p>
      <button className={button} disabled={request.busy} onClick={() => { void request.check() }}>Check pending output request</button>
      {request.canFinish && <button className={button} disabled={request.busy} onClick={() => { void request.finish() }}>Finish original output request</button>}
      {request.canDiscard && <button className={button} disabled={request.busy} onClick={request.discard}>Discard unclaimed output request</button>}
    </section>}
    {view && <div ref={savedRef} tabIndex={-1} role="region" aria-label="Opened output evidence" className="min-w-0 space-y-3 rounded-lg border border-gray-300 px-1.5 py-3 sm:p-3 outline-offset-4">
      {capture && <><OutputCaptureEvidence capture={capture} />{canWrite && <button className={button} disabled={locked} onClick={() => send({ action: 'prepare', body: { request_id: newOutputId(), input_snapshot_id: capture.uuid, input_snapshot_sha256: capture.input_snapshot_sha256, case_sha256: listing.case.case_sha256, consent: 'prepare_output_workflow_plan' } })}>Prepare this saved output workflow</button>}</>}
      {run && <><OutputRunEvidence run={run} />{canWrite && <OutputRunActions key={run.run_id} run={run} locked={locked} send={send} onInspect={() => { setInspectionRun(run); setView(null); requestAnimationFrame(() => inspectionRef.current?.focus()) }} />}
        {run.handoff_receipt_id && <button className={button} disabled={readLocked} onClick={() => { void open('handoff', run.handoff_receipt_id!) }}>Read this run’s saved handoff receipt</button>}</>}
      {inspection && <><h5 className="text-base font-semibold">Saved file inspection · {inspection.submission.choice}</h5><p className="whitespace-pre-wrap text-sm">{inspection.submission.answers.artifact_review}</p><p className="whitespace-pre-wrap text-sm">{inspection.submission.answers.release_decision}</p>
        {inspection.submission.file_inspections.map(item => <p key={item.sha256} className="text-sm">{item.judgment.replaceAll('_', ' ')}: {item.observations}</p>)}
        <details><summary className="min-h-11 cursor-pointer py-2 text-sm">Inspect the original reviewed files</summary><OutputRunEvidence run={inspection.run} location={{ enrollmentId: listing.enrollment_id, origin: 'inspection', reference: inspection.uuid }} /></details>
        {canWrite && inspection.submission.choice === 'approve' && inspection.run.release_decision?.uuid === inspection.uuid && !inspection.run.handoff_request_id && !inspection.run.handoff_claimed && <><p className="text-sm">Request the contained training handoff of only these approved files. Its first attempt deliberately rejects before copying.</p><button className={button} disabled={locked} onClick={() => attempt(inspection)}>Attempt the approved private handoff</button></>}
        {canWrite && <button className={button} disabled={readLocked} onClick={() => { void open('run', inspection.run.run_id) }}>Read current generation and release choice</button>}
        {inspection.run.handoff_receipt_id && <button className={button} disabled={readLocked} onClick={() => { void open('handoff', inspection.run.handoff_receipt_id!) }}>Read the original handoff receipt</button>}</>}
      {handoff && <><OutputHandoffEvidence handoff={handoff} />{canWrite && <>
        {handoff.status === 'failed' && <><button className={button} disabled={locked} onClick={() => { void readCurrentRelease(handoff) }}>Read current approval before retry</button>
          {currentRelease && <section aria-label="Current handoff approval" className="space-y-2 rounded-lg border border-gray-300 px-1.5 py-3 sm:p-3 text-sm"><p>Current release choice: {currentRelease.release_decision?.submission.choice || 'No saved approval'}. {currentRelease.release_decision?.submission.answers.release_decision}</p>
            {currentRelease.release_decision?.submission.choice === 'approve' && !currentRelease.handoff_claimed && !currentRelease.retry_request_id && currentRelease.handoff_request_id === handoff.uuid ? <button className={button} disabled={locked} onClick={() => retry(handoff, currentRelease)}>Retry only this failed private handoff</button> : <p>A retry is not available under this current choice. Read the run and its original handoff before changing anything.</p>}</section>}</>}
        <button className={button} disabled={locked} onClick={() => { void beginInterpretation(handoff) }}>Explain this actual delivery outcome</button>
      </>}</>}
      {review && <><h5 className="text-base font-semibold">Saved delivery interpretation</h5><p className="whitespace-pre-wrap text-sm">{review.submission.delivery_review}</p>
        <details><summary className="min-h-11 cursor-pointer py-2 text-sm">Read original reviewed files and handoff</summary><OutputRunEvidence run={review.file_review.run} location={{ enrollmentId: listing.enrollment_id, origin: 'review', reference: review.uuid }} /><OutputHandoffEvidence handoff={review.handoff} location={{ enrollmentId: listing.enrollment_id, origin: 'review', reference: review.uuid }} /></details>
        {canWrite && <><button className={button} disabled={locked} onClick={() => selectInterpretation(review.file_review, review.handoff, review.uuid, review.submission.delivery_review)}>Revise this delivery interpretation</button><PracticalAssessment key={review.uuid} enrollmentId={listing.enrollment_id} moduleId="output_delivery" outputReviewSubmissionId={review.uuid} onOpenFeedback={setFeedbackId} /></>}</>}
      <p className="break-all text-xs text-gray-600">Saved reference: {'input_snapshot' in view ? view.run_id : view.uuid}</p>
    </div>}
    {canWrite && <>
      {inspectionRun && <div ref={inspectionRef} role="region" tabIndex={-1} aria-label="Output inspection entry" className="min-w-0 rounded-lg border border-gray-300 px-1.5 py-3 sm:p-3 outline-offset-4"><OutputInspectionForm key={inspectionRun.run_id} run={inspectionRun} locked={locked} send={send} /></div>}
      {selected && <OutputInterpretationForm key={`${selected.handoff.uuid}:${selected.previous || 'original'}`} formRef={interpretationRef}
        inspection={selected.inspection} handoff={selected.handoff} previous={selected.previous} initialAnswer={interpretation} locked={locked} send={send} />}
      <form ref={captureRef} tabIndex={-1} aria-label="Capture output workflow" className="min-w-0 space-y-3 rounded-lg border border-gray-300 px-1.5 py-3 sm:p-3" onSubmit={event => { event.preventDefault(); send({ action: 'capture', body: { request_id: newOutputId(), workflow_id: workflow, case_sha256: listing.case.case_sha256, consent: 'capture_output_workflow_inputs' } }) }}>
        <h5 className="text-base font-semibold">Start or repair a generation</h5><p className="text-sm">Save an owned four-stage workflow: Prompt or Formatter reads Workflow Documents; Document Renderer creates a PDF from Step Input; Formatter independently reads Workflow Documents; Data Export creates CSV from Step Input. Include both file stages in deliverables. Give each file a distinct name. A repaired generation gets its own inspection and approval.</p>
        <label className="block text-sm">Owned output workflow<select className={control} required disabled={locked} value={workflow} onChange={event => setWorkflow(event.target.value)}><option value="">Choose a saved workflow</option>{listing.workflows.map(item => <option key={item.workflow_id} value={item.workflow_id}>{item.name} · version {item.version}</option>)}</select></label>
        {listing.workflows.filter(item => item.workflow_id === workflow).map(item => <CourseEditorLink key={item.workflow_id} kind="workflow" artifactId={item.workflow_id} title={item.name} disabled={locked} />)}
        {listing.older_workflows_available && <p className="text-sm">Only the 50 most recently updated owned workflows are shown.</p>}
        <button className={button} disabled={locked}>Save output workflow and source</button>
      </form>
    </>}
    <SavedAutomaticReviews key={`${listing.enrollment_id}:${feedbackId}`} enrollmentId={listing.enrollment_id} moduleId="output_delivery" initialAttemptId={feedbackId || undefined} workNavigationDisabled={readLocked} onOpenWork={review => { void open('review', review.output_review_submission_id!) }} />
  </section>
}
