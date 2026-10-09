import { CourseRequestStatus } from './CourseRequestStatus'
import { CourseEditorLink } from './CourseEditorLink'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getBatchWork, getBatchCapture, getBatchRun, getBatchReview } from '../../api/batchAssessment'
import type { BatchCase, BatchList, BatchRequest, BatchRun, BatchSaved, BatchCapture, BatchPhase, BatchSourceId } from '../../types/batchAssessment'
import { connectedId as id } from './connectedWorkflowState'
import { sameBatchCase, validBatchRequest, verifyBatchCapture, verifyBatchRun, verifyBatchReview } from './batchAssessmentState'
import { useBatchRequest } from './useBatchRequest'
import { BatchCaptureEvidence, BatchRunEvidence, batchButton as button, batchControl as control } from './BatchEvidence'
import { BatchRunActions, BatchInterpretationForm, newBatchId } from './BatchForms'
import { PracticalAssessment } from './PracticalAssessment'
import { SavedAutomaticReviews } from './SavedAutomaticReviews'

type ReadKind = 'capture' | 'run' | 'review'
const box = 'min-w-0 space-y-3 rounded-lg border border-gray-300 px-[6px] py-3 sm:p-3'
export function BatchAssessment({ enrollmentId, definition, historyOnly = false }: { enrollmentId: string; definition: BatchCase; historyOnly?: boolean }) {
  const [listing, setListing] = useState<BatchList | null>(null), [error, setError] = useState(''), [reload, setReload] = useState(0)
  useEffect(() => {
    let active = true
    setListing(null); setError('')
    void getBatchWork(enrollmentId).then(value => {
      if (value.enrollment_id !== enrollmentId || value.module_id !== 'batch_processing' || !sameBatchCase(value.case, definition)) throw new Error('Different batch assignment')
      if (active) setListing(value)
    }).catch(() => { if (active) setError('The original batch assignment could not be loaded. Retry to read the saved course.') })
    return () => { active = false }
  }, [enrollmentId, definition, reload])
  if (!listing) return <section aria-label="Bounded batch assessment">{error ? <><p role="alert" className="text-sm text-red-800">{error}</p><button className={button} onClick={() => setReload(v => v + 1)}>Retry loading batch assignment</button></> : <p role="status">Loading batch assignment…</p>}</section>
  return <BatchWorkspace key={`${enrollmentId}:${definition.case_sha256}:${historyOnly}`} initial={listing} historyOnly={historyOnly} />
}
function BatchWorkspace({ initial, historyOnly }: { initial: BatchList; historyOnly: boolean }) {
  const [listing, setListing] = useState(initial), [view, setView] = useState<BatchSaved | null>(null), [artifact, setArtifact] = useState('')
  const [interpretation, setInterpretation] = useState<{ original: BatchRun; retries: BatchRun[]; previous: string | null; answer: string } | null>(null)
  const [feedbackId, setFeedbackId] = useState(''), [reference, setReference] = useState(''), [referenceKind, setReferenceKind] = useState<ReadKind>('run')
  const [reading, setReading] = useState(false), [error, setError] = useState('')
  const sequence = useRef(0), focusSaved = useRef(false), savedRef = useRef<HTMLDivElement>(null), reviewRef = useRef<HTMLDivElement>(null)
  const request = useBatchRequest(listing, value => { focusSaved.current = true; setView(value); setInterpretation(null); setFeedbackId(''); void refresh() }, !historyOnly)
  const canWrite = !historyOnly && listing.can_submit && !request.blocked
  const locked = reading || request.busy || !!request.pending || request.blocked
  const readLocked = reading || request.busy || !!request.pending
  const capture = view && 'artifact' in view ? view : null, run = view && 'state' in view ? view : null, review = view && 'run' in view ? view : null
  useEffect(() => { const counter = sequence; return () => { counter.current++ } }, [])
  useLayoutEffect(() => { if (view && focusSaved.current) { focusSaved.current = false; savedRef.current?.focus() } }, [view])
  async function refresh() {
    const token = sequence.current
    try {
      const value = await getBatchWork(listing.enrollment_id)
      if (value.enrollment_id !== listing.enrollment_id || value.manifest_sha256 !== listing.manifest_sha256 || !sameBatchCase(value.case, listing.case)) throw new Error('Different course')
      if (token === sequence.current) setListing({ ...value, case: listing.case })
    } catch { if (token === sequence.current) setError('Saved batch choices could not be refreshed. Your open evidence is preserved.') }
  }
  async function open(kind: ReadKind, key: string) {
    if (readLocked || !id(key)) return
    const token = ++sequence.current
    setReading(true); setError(''); setFeedbackId(''); setView(null); setInterpretation(null)
    try {
      const value = kind === 'capture' ? verifyBatchCapture(await getBatchCapture(listing.enrollment_id, key), listing)
        : kind === 'run' ? verifyBatchRun(await getBatchRun(listing.enrollment_id, key), listing) : verifyBatchReview(await getBatchReview(listing.enrollment_id, key), listing)
      if (('state' in value ? value.run_id : value.uuid) !== key) throw new Error('Different reference')
      if (token === sequence.current) { focusSaved.current = true; setView(value) }
    } catch { if (token === sequence.current) setError('The original saved record could not be opened for this course. Check its reference and try again.') }
    finally { if (token === sequence.current) setReading(false) }
  }
  function send(next: BatchRequest) {
    if (!canWrite || locked) return
    if (!validBatchRequest(next, listing.case)) { setError('Complete the required scope and explanation before saving.'); return }
    setError(''); void request.send(next)
  }
  function prepare(input: BatchCapture, phase: BatchPhase, parent: BatchRun | null = null, source: BatchSourceId | null = null, previous: BatchRun | null = null) {
    send({ action: 'prepare', body: { request_id: newBatchId(), input_snapshot_id: input.uuid, input_snapshot_sha256: input.input_snapshot_sha256,
      case_sha256: listing.case.case_sha256, phase, parent_run_id: parent?.run_id || null, parent_run_sha256: parent?.run_sha256 || null,
      failed_source_id: source, previous_retry_id: previous?.run_id || null, previous_retry_sha256: previous?.run_sha256 || null, consent: 'prepare_bounded_batch_action' } })
  }
  function beginReview(original: BatchRun, retries: BatchRun[], previous: string | null = null, answer = '') {
    setInterpretation({ original, retries, previous, answer }); setView(null); setFeedbackId(''); requestAnimationFrame(() => reviewRef.current?.focus())
  }
  return <section aria-label="Bounded batch assessment" className="min-w-0 space-y-4 text-gray-900 [overflow-wrap:anywhere]">
    <h4 className="text-lg font-semibold">Checked pilot, complete inventory and targeted recovery</h4><p className="text-sm">{listing.case.notice}</p><p>{listing.case.task}</p>
    {!canWrite && <p className="text-sm">{historyOnly ? 'Read-only original course history. Opening evidence and PDFs never runs or grades work.' : listing.read_only_reason}</p>}
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Assignment instructions and pilot limitations</summary><ol className="list-decimal space-y-2 pl-5 text-sm">{listing.case.instructions.map(item => <li key={item}>{item}</li>)}</ol><p className="mt-3 text-sm">{listing.case.pilot_limitations}</p><ul className="mt-3 list-disc space-y-2 pl-5 text-sm">{listing.case.exclusions.map(item => <li key={item}>{item}</li>)}</ul></details>
    {error && <p role="alert" className="text-sm text-red-800">{error}</p>}{request.error && <p role="alert" className="text-sm text-red-800">{request.error}</p>}
    <CourseRequestStatus phase={request.phase || (reading ? 'checking' : null)} action={request.pending?.action} />
    {request.pending && <section aria-label="Pending batch request" className={box}><h5 className="font-semibold">Check your original request</h5><p className="text-sm">Its identity and original details are preserved in this tab. Checking only reads saved state.</p><button className={button} disabled={request.busy} onClick={() => { void request.check() }}>Check pending batch request</button>{request.canFinish && <button className={button} disabled={request.busy} onClick={() => { void request.finish() }}>Finish original batch request</button>}{request.canDiscard && <button className={button} disabled={request.busy} onClick={request.discard}>Discard unsaved batch request</button>}</section>}
    {view && <div ref={savedRef} tabIndex={-1} aria-label="Opened batch evidence" role="region" className={box}>
      {capture && <><BatchCaptureEvidence capture={capture} />{canWrite && <button className={button} disabled={locked} onClick={() => prepare(capture, 'pilot')}>Prepare two-document pilot</button>}</>}
      {run && <><BatchRunEvidence run={run} />{canWrite && <BatchRunActions key={run.run_id} run={run} locked={locked} send={send} />}
        {canWrite && run.phase === 'pilot' && run.state === 'completed' && (run.result?.checks?.all_values_source_supported
          ? <button className={button} disabled={locked} onClick={() => prepare(run.input_snapshot, 'batch', run)}>Prepare three-document batch from this pilot</button>
          : <p className="text-sm">This pilot does not support scaling. Inspect its actual outputs, repair the owned extraction if needed, then capture and approve a new pilot. This earlier result stays preserved.</p>)}
        {canWrite && run.phase === 'batch' && run.state === 'completed' && run.result?.item_results?.filter(item => item.status === 'failed').map(item => <button key={item.source_id} className={button} disabled={locked} onClick={() => prepare(run.input_snapshot, 'retry', run, item.source_id)}>Prepare retry only for {item.source_id.replace('_', ' ')}</button>)}
        {canWrite && run.phase === 'retry' && run.state === 'completed' && run.parent_run && <>
          {run.result?.item_results?.[0].status === 'failed' && <button className={button} disabled={locked} onClick={() => prepare(run.input_snapshot, 'retry', run.parent_run, run.failed_source_id, run)}>Prepare another attempt of this confirmed failed item</button>}
          <button className={button} disabled={locked} onClick={() => beginReview(run.parent_run!, [run])}>Reconcile inventory and explain recovery</button>
        </>}
      </>}
      {review && <><h5 className="font-semibold">Saved batch interpretation</h5><p className="whitespace-pre-wrap text-sm">{review.submission.answers.batch_review}</p>
        <p className="text-sm">Assigned terminal coverage: {review.reconciliation.all_assigned_terminal ? 'complete' : 'incomplete'}. Usable recovery: {review.reconciliation.targeted_recovery_supported ? 'source-supported' : 'unresolved'}. {review.reconciliation.original_successes_preserved.length} original successful receipts preserved.</p>
        {review.submission.previous_submission_id && <p className="break-all text-sm">Original answer: {review.submission.previous_submission_id}</p>}
        <BatchRunEvidence run={review.run} location={{ enrollmentId: listing.enrollment_id, origin: 'review', reference: review.uuid }} />
        {review.retries.map(retry => <details key={retry.run_id}><summary className="min-h-11 cursor-pointer py-2 font-semibold">Preserved retry: {retry.failed_source_id?.replace('_', ' ')}</summary><BatchRunEvidence run={retry} location={{ enrollmentId: listing.enrollment_id, origin: 'review', reference: review.uuid }} /></details>)}
        {canWrite && <><button className={button} disabled={locked} onClick={() => beginReview(review.run, review.retries, review.uuid, review.submission.answers.batch_review)}>Revise interpretation and preserve original</button><PracticalAssessment key={review.uuid} enrollmentId={listing.enrollment_id} moduleId="batch_processing" batchReviewSubmissionId={review.uuid} onOpenFeedback={setFeedbackId} /></>}
      </>}
    </div>}
    {interpretation && canWrite && <div ref={reviewRef} tabIndex={-1}><BatchInterpretationForm key={interpretation.previous || interpretation.retries[0].run_id} listing={listing} original={interpretation.original} initialRetries={interpretation.retries} initialAnswer={interpretation.answer} previous={interpretation.previous} locked={locked} send={send} /></div>}
    {canWrite && <form aria-label="Capture batch extraction" className={box} onSubmit={e => { e.preventDefault(); send({ action: 'capture', body: { request_id: newBatchId(), artifact_id: artifact, case_sha256: listing.case.case_sha256, consent: 'capture_batch_extraction_and_complete_sources' } }) }}>
      <h5 className="font-semibold">Capture your owned extraction</h5><p className="text-sm">Create an extraction with exactly the five field titles below and provision all three course documents. Capturing preserves the complete sources and exact instructions before you approve any work.</p>
      <ul className="list-disc space-y-2 pl-5 text-sm">{listing.case.fields.map(field => <li key={field.title}><strong>{field.title}</strong>: {field.meaning}</li>)}</ul>
      <label className="block text-sm">Owned extraction<select className={control} value={artifact} disabled={locked} required onChange={e => setArtifact(e.target.value)}><option value="">Select an extraction</option>{listing.extractions.map(item => <option key={item.artifact_id} value={item.artifact_id}>{item.title}</option>)}</select></label>
      {listing.extractions.filter(item => item.artifact_id === artifact).map(item => <CourseEditorLink key={item.artifact_id} kind="extraction" artifactId={item.artifact_id} title={item.title} disabled={locked} />)}
      {!listing.extractions.length && <p className="text-sm">No owned extraction is available. Create one with the required fields, then refresh choices.</p>}
      <button className={button} disabled={locked || !id(artifact)}>Capture extraction and three sources</button><button type="button" className={button} disabled={locked} onClick={() => { void refresh() }}>Refresh batch choices</button>
    </form>}
    <section aria-label="Saved batch history" className={box}><h5 className="font-semibold">Saved batch history</h5>
      {listing.captures.map((item, i) => <button key={item.input_snapshot_id} className={button} disabled={readLocked} onClick={() => { void open('capture', item.input_snapshot_id) }}>Open capture {i + 1}: {item.extraction_name}</button>)}
      {listing.runs.map((item, i) => <button key={item.run_id} className={button} disabled={readLocked} onClick={() => { void open('run', item.run_id) }}>Open {item.phase} run {i + 1}: {item.state}</button>)}
      {listing.submissions.map((item, i) => <button key={item.submission_id} className={button} disabled={readLocked} onClick={() => { void open('review', item.submission_id) }}>Open batch interpretation {i + 1}{item.previous_submission_id ? ' · revised answer' : ''}</button>)}
      {['captures', 'runs', 'submissions'].some(key => listing[`older_${key}_available` as keyof BatchList] === true) && <p className="text-sm">Only the latest 50 of each record type are listed. Open an older record by its saved reference.</p>}
      <form className="space-y-2" onSubmit={e => { e.preventDefault(); void open(referenceKind, reference) }}><label className="block text-sm">Saved record type<select className={control} value={referenceKind} onChange={e => setReferenceKind(e.target.value as ReadKind)}><option value="run">Run</option><option value="capture">Capture</option><option value="review">Batch interpretation</option></select></label><label className="block text-sm">Saved batch reference<input className={control} value={reference} onChange={e => setReference(e.target.value.trim())} pattern="[a-f0-9]{32}" required /></label><button className={button} disabled={readLocked || !id(reference)}>Open saved batch reference</button></form>
    </section>
    <SavedAutomaticReviews key={`${listing.enrollment_id}:${feedbackId}`} enrollmentId={listing.enrollment_id} moduleId="batch_processing" initialAttemptId={feedbackId || undefined} workNavigationDisabled={readLocked} onOpenWork={review => { void open('review', review.batch_review_submission_id!) }} />
  </section>
}
