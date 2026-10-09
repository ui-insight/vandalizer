import { CourseRequestStatus } from './CourseRequestStatus'
import { CourseEditorLink } from './CourseEditorLink'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getValidationWork, getValidationCapture, getValidationSuite, getValidationRun, getValidationReview } from '../../api/validationSuite'
import type { ValidationCase, ValidationList, ValidationRequest, ValidationRun, ValidationSaved, ValidationSuiteRecord, ValidationCapture } from '../../types/validationSuite'
import { connectedId as id } from './connectedWorkflowState'
import { sameValidationCase, validValidationRequest, verifyValidationCapture, verifyValidationSuite, verifyValidationRun, verifyValidationReview } from './validationSuiteState'
import { useValidationRequest } from './useValidationRequest'
import { ValidationCaptureEvidence, ValidationSuiteEvidence, ValidationRunEvidence, validationButton as button, validationControl as control } from './ValidationEvidence'
import { ValidationExpectationsForm, ValidationRunActions, ValidationInterpretationForm, newValidationId } from './ValidationForms'
import { PracticalAssessment } from './PracticalAssessment'
import { SavedAutomaticReviews } from './SavedAutomaticReviews'

type ReadKind = 'capture' | 'suite' | 'run' | 'review'
const box = 'min-w-0 space-y-3 rounded-lg border border-gray-300 px-[6px] py-3 sm:p-3'
export function ValidationSuite({ enrollmentId, definition, historyOnly = false }: { enrollmentId: string; definition: ValidationCase; historyOnly?: boolean }) {
  const [listing, setListing] = useState<ValidationList | null>(null), [error, setError] = useState(''), [reload, setReload] = useState(0)
  useEffect(() => {
    let active = true
    setListing(null); setError('')
    void getValidationWork(enrollmentId).then(value => {
      if (value.enrollment_id !== enrollmentId || value.module_id !== 'validation_qa' || !sameValidationCase(value.case, definition)) throw new Error('Different validation assignment')
      if (active) setListing(value)
    }).catch(() => { if (active) setError('The original validation assignment could not be loaded. Retry to read the saved course.') })
    return () => { active = false }
  }, [enrollmentId, definition, reload])
  if (!listing) return <section aria-label="Representative validation assessment">{error ? <><p role="alert" className="text-sm text-red-800">{error}</p><button className={button} onClick={() => setReload(v => v + 1)}>Retry loading validation assignment</button></> : <p role="status">Loading validation assignment…</p>}</section>
  return <ValidationWorkspace key={`${enrollmentId}:${definition.case_sha256}:${historyOnly}`} initial={listing} historyOnly={historyOnly} />
}
function ValidationWorkspace({ initial, historyOnly }: { initial: ValidationList; historyOnly: boolean }) {
  const [listing, setListing] = useState(initial), [view, setView] = useState<ValidationSaved | null>(null)
  const [artifact, setArtifact] = useState(''), [original, setOriginal] = useState<ValidationRun | null>(null)
  const [reviewRun, setReviewRun] = useState<ValidationRun | null>(null), [previous, setPrevious] = useState<string | null>(null), [answer, setAnswer] = useState('')
  const [feedbackId, setFeedbackId] = useState(''), [reference, setReference] = useState(''), [referenceKind, setReferenceKind] = useState<ReadKind>('run')
  const [reading, setReading] = useState(false), [error, setError] = useState('')
  const sequence = useRef(0), focusSaved = useRef(false), savedRef = useRef<HTMLDivElement>(null), reviewRef = useRef<HTMLFormElement>(null), captureRef = useRef<HTMLFormElement>(null)
  const request = useValidationRequest(listing, value => { focusSaved.current = true; setView(value); setReviewRun(null); setFeedbackId(''); void refresh() }, !historyOnly)
  const canWrite = !historyOnly && listing.can_submit && !request.blocked
  const locked = reading || request.busy || !!request.pending || request.blocked
  const readLocked = reading || request.busy || !!request.pending
  const capture = view && 'artifact' in view ? view : null
  const suite = view && 'suite_sha256' in view ? view : null
  const run = view && 'state' in view ? view : null
  const review = view && 'run' in view ? view : null
  useEffect(() => { const counter = sequence; return () => { counter.current++ } }, [])
  useLayoutEffect(() => { if (view && focusSaved.current) { focusSaved.current = false; savedRef.current?.focus() } }, [view])
  async function refresh() {
    const token = sequence.current
    try {
      const value = await getValidationWork(listing.enrollment_id)
      if (value.enrollment_id !== listing.enrollment_id || value.manifest_sha256 !== listing.manifest_sha256 || !sameValidationCase(value.case, listing.case)) throw new Error('Different course')
      if (token === sequence.current) setListing({ ...value, case: listing.case })
    } catch { if (token === sequence.current) setError('Saved validation choices could not be refreshed. Your open evidence is preserved.') }
  }
  async function open(kind: ReadKind, key: string) {
    if (readLocked || !id(key)) return
    const token = ++sequence.current
    setReading(true); setError(''); setFeedbackId(''); setView(null); setReviewRun(null)
    try {
      const value = kind === 'capture' ? verifyValidationCapture(await getValidationCapture(listing.enrollment_id, key), listing)
        : kind === 'suite' ? verifyValidationSuite(await getValidationSuite(listing.enrollment_id, key), listing)
          : kind === 'run' ? verifyValidationRun(await getValidationRun(listing.enrollment_id, key), listing)
            : verifyValidationReview(await getValidationReview(listing.enrollment_id, key), listing)
      if (('state' in value ? value.run_id : value.uuid) !== key) throw new Error('Different reference')
      if (token === sequence.current) { focusSaved.current = true; setView(value) }
    } catch { if (token === sequence.current) setError('The original saved record could not be opened for this course. Check its reference and try again.') }
    finally { if (token === sequence.current) setReading(false) }
  }
  function send(next: ValidationRequest) {
    if (!canWrite || locked) return
    if (!validValidationRequest(next, listing.case)) { setError('Complete every required source expectation and explanation before saving.'); return }
    setError(''); void request.send(next)
  }
  function prepare(input: ValidationCapture, savedSuite: ValidationSuiteRecord, failure: ValidationRun | null = null) {
    send({ action: 'prepare', body: { request_id: newValidationId(), input_snapshot_id: input.uuid, input_snapshot_sha256: input.input_snapshot_sha256,
      suite_id: savedSuite.uuid, suite_record_sha256: savedSuite.suite_record_sha256, case_sha256: listing.case.case_sha256,
      original_run_id: failure?.run_id || null, original_run_sha256: failure?.run_sha256 || null, consent: 'prepare_complete_validation_suite' } })
  }
  function beginReview(saved: ValidationRun, parent: string | null = null, text = '') {
    setReviewRun(saved); setPrevious(parent); setAnswer(text); setView(null); setFeedbackId(''); requestAnimationFrame(() => reviewRef.current?.focus())
  }
  return <section aria-label="Representative validation assessment" className="min-w-0 space-y-4 text-gray-900 [overflow-wrap:anywhere]">
    <h4 className="text-lg font-semibold">Representative tests and repair</h4><p className="text-sm">{listing.case.notice}</p><p>{listing.case.task}</p>
    {!canWrite && <p className="text-sm">{historyOnly ? 'Read-only original course history. Opening evidence and PDFs never runs or grades work.' : listing.read_only_reason}</p>}
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Assignment instructions and deliberate flaw</summary><ol className="list-decimal space-y-2 pl-5 text-sm">{listing.case.instructions.map(item => <li key={item}>{item}</li>)}</ol><p className="mt-3 text-sm">{listing.case.flawed_proposal}</p><ul className="mt-3 list-disc space-y-2 pl-5 text-sm">{listing.case.exclusions.map(item => <li key={item}>{item}</li>)}</ul></details>
    {error && <p role="alert" className="text-sm text-red-800">{error}</p>}{request.error && <p role="alert" className="text-sm text-red-800">{request.error}</p>}
    <CourseRequestStatus phase={request.phase || (reading ? 'checking' : null)} action={request.pending?.action} />
    {request.pending && <section aria-label="Pending validation request" className={box}><h5 className="font-semibold">Check your original request</h5><p className="text-sm">Its identity and original details are preserved in this tab. Checking only reads saved state.</p><button className={button} disabled={request.busy} onClick={() => { void request.check() }}>Check pending validation request</button>{request.canFinish && <button className={button} disabled={request.busy} onClick={() => { void request.finish() }}>Finish original validation request</button>}{request.canDiscard && <button className={button} disabled={request.busy} onClick={request.discard}>Discard unsaved validation request</button>}</section>}
    {view && <div ref={savedRef} tabIndex={-1} aria-label="Opened validation evidence" role="region" className={box}>
      {capture && <><ValidationCaptureEvidence capture={capture} />{canWrite && (original ? <><p className="text-sm">Retest the selected original failure using its complete unchanged suite.</p><button className={button} disabled={locked || capture.artifact_id !== original.input_snapshot.artifact_id || capture.artifact_sha256 === original.input_snapshot.artifact_sha256} onClick={() => prepare(capture, original.suite, original)}>Prepare complete repaired retest</button></> : <ValidationExpectationsForm key={capture.uuid} capture={capture} locked={locked} send={send} />)}</>}
      {suite && <><ValidationCaptureEvidence capture={suite.input_snapshot} location={{ enrollmentId: listing.enrollment_id, origin: 'suite', reference: suite.uuid }} /><ValidationSuiteEvidence suite={suite} />{canWrite && <button className={button} disabled={locked} onClick={() => prepare(suite.input_snapshot, suite)}>Prepare original complete suite</button>}</>}
      {run && <><ValidationRunEvidence run={run} />{canWrite && <ValidationRunActions key={run.run_id} run={run} locked={locked} send={send} />}
        {canWrite && run.phase === 'original' && run.state === 'completed' && run.result?.checks?.complete && run.result.checks.observed_semantic_failure && <button className={button} disabled={locked} onClick={() => { setOriginal(run); setArtifact(run.input_snapshot.artifact_id); setView(null); requestAnimationFrame(() => captureRef.current?.focus()) }}>Use this original failure for repair</button>}
        {canWrite && run.phase === 'original' && run.state === 'completed' && run.result?.checks?.complete && !run.result.checks.observed_semantic_failure && <p className="text-sm">No actual source mismatch was observed. This run cannot establish the repair outcome. Inspect the deliberate flaw and your original field instructions before creating another original suite.</p>}
        {canWrite && run.phase === 'retest' && run.state === 'completed' && <button className={button} disabled={locked} onClick={() => beginReview(run)}>Explain the repair and complete retest</button>}
      </>}
      {review && <><h5 className="font-semibold">Saved repair interpretation</h5><p className="whitespace-pre-wrap text-sm">{review.submission.answers.repair_review}</p>{review.submission.previous_submission_id && <p className="break-all text-sm">Original answer: {review.submission.previous_submission_id}</p>}<ValidationRunEvidence run={review.run} location={{ enrollmentId: listing.enrollment_id, origin: 'review', reference: review.uuid }} />
        {canWrite && <><button className={button} disabled={locked} onClick={() => beginReview(review.run, review.uuid, review.submission.answers.repair_review)}>Revise interpretation and preserve original</button><PracticalAssessment key={review.uuid} enrollmentId={listing.enrollment_id} moduleId="validation_qa" validationReviewSubmissionId={review.uuid} onOpenFeedback={setFeedbackId} /></>}
      </>}
    </div>}
    {reviewRun && canWrite && <ValidationInterpretationForm key={`${reviewRun.run_id}:${previous || 'original'}`} formRef={reviewRef} run={reviewRun} previous={previous} initialAnswer={answer} locked={locked} send={send} />}
    {canWrite && <form ref={captureRef} tabIndex={-1} aria-label="Capture validation extraction" className={box} onSubmit={e => { e.preventDefault(); send({ action: 'capture', body: { request_id: newValidationId(), artifact_id: artifact, case_sha256: listing.case.case_sha256, consent: 'capture_validation_extraction_and_complete_sources' } }) }}>
      <h5 className="font-semibold">{original ? 'Capture the repaired revision' : 'Capture your original extraction'}</h5>
      <p className="text-sm">{original ? 'Edit the failed field in the same owned extraction, then capture its corrected revision here. The original run and all six expectations will remain unchanged.' : 'Create an extraction with exactly the three field titles in the assignment, including the deliberate original budget flaw. Provision both course documents, then capture the owned extraction and complete PDFs here.'}</p>
      {original && <><p className="break-all text-sm">Selected original failure: {original.run_id}</p><button type="button" className={button} disabled={locked} onClick={() => setOriginal(null)}>Return to a new original suite</button></>}
      <label className="block text-sm">Owned extraction<select className={control} value={artifact} disabled={locked || !!original} required onChange={e => setArtifact(e.target.value)}><option value="">Select an extraction</option>{listing.extractions.map(item => <option key={item.artifact_id} value={item.artifact_id}>{item.title}</option>)}</select></label>
      {listing.extractions.filter(item => item.artifact_id === artifact).map(item => <CourseEditorLink key={item.artifact_id} kind="extraction" artifactId={item.artifact_id} title={item.title} disabled={locked} />)}
      {!listing.extractions.length && <p className="text-sm">No owned extraction is available. Create one with the required fields, then refresh choices.</p>}
      <button className={button} disabled={locked || !id(artifact)}>Capture extraction and both sources</button><button type="button" className={button} disabled={locked} onClick={() => { void refresh() }}>Refresh validation choices</button>
    </form>}
    <section aria-label="Saved validation history" className={box}><h5 className="font-semibold">Saved validation history</h5>
      {listing.captures.map((item, i) => <button key={item.input_snapshot_id} className={button} disabled={readLocked} onClick={() => { void open('capture', item.input_snapshot_id) }}>Open capture {i + 1}: {item.extraction_name}</button>)}
      {listing.suites.map((item, i) => <button key={item.submission_id} className={button} disabled={readLocked} onClick={() => { void open('suite', item.submission_id) }}>Open saved expectations {i + 1}</button>)}
      {listing.runs.map((item, i) => <button key={item.run_id} className={button} disabled={readLocked} onClick={() => { void open('run', item.run_id) }}>Open {item.phase} run {i + 1}: {item.state}</button>)}
      {listing.submissions.map((item, i) => <button key={item.submission_id} className={button} disabled={readLocked} onClick={() => { void open('review', item.submission_id) }}>Open repair interpretation {i + 1}{item.previous_submission_id ? ' · revised answer' : ''}</button>)}
      {['captures', 'suites', 'runs', 'submissions'].some(key => listing[`older_${key}_available` as keyof ValidationList] === true) && <p className="text-sm">Only the latest 50 of each record type are listed. Open an older record by its saved reference.</p>}
      <form className="space-y-2" onSubmit={e => { e.preventDefault(); void open(referenceKind, reference) }}><label className="block text-sm">Saved record type<select className={control} value={referenceKind} onChange={e => setReferenceKind(e.target.value as ReadKind)}><option value="run">Run</option><option value="capture">Capture</option><option value="suite">Expectations</option><option value="review">Repair interpretation</option></select></label><label className="block text-sm">Saved validation reference<input className={control} value={reference} onChange={e => setReference(e.target.value.trim())} pattern="[a-f0-9]{32}" required /></label><button className={button} disabled={readLocked || !id(reference)}>Open saved validation reference</button></form>
    </section>
    <SavedAutomaticReviews key={`${listing.enrollment_id}:${feedbackId}`} enrollmentId={listing.enrollment_id} moduleId="validation_qa" initialAttemptId={feedbackId || undefined} workNavigationDisabled={readLocked} onOpenWork={review => { void open('review', review.validation_review_submission_id!) }} />
  </section>
}
