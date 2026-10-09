import { CourseRequestStatus } from './CourseRequestStatus'
import { CourseEditorLink } from './CourseEditorLink'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getGovernanceRecord, getGovernanceWork } from '../../api/governanceAssessment'
import type { GovernanceCase, GovernanceKind, GovernanceList, GovernanceRequest, GovernanceView } from '../../types/governanceAssessment'
import { connectedId as id } from './connectedWorkflowState'
import { governanceId as newId, governanceKinds, governanceLabels, sameGovernanceCase, validGovernanceRequest, verifyGovernanceView } from './governanceAssessmentState'
import { useGovernanceRequest } from './useGovernanceRequest'
import { GovernanceEvidence, governanceBox as box, governanceButton as button, governanceControl as control } from './GovernanceEvidence'
import { GovernanceCorrectionForm, GovernanceRepairPlanForm, GovernanceRunActions, GovernanceFindingForm, GovernanceMemoForm, GovernanceReleaseForm,
  GovernanceReviewForm, GovernanceHandoffActions, governancePlan, governanceHandoff } from './GovernanceForms'
import { PracticalAssessment } from './PracticalAssessment'
import { SavedAutomaticReviews } from './SavedAutomaticReviews'

export function GovernanceAssessment({ enrollmentId, definition, historyOnly = false }: { enrollmentId: string; definition: GovernanceCase; historyOnly?: boolean }) {
  const [listing, setListing] = useState<GovernanceList | null>(null), [error, setError] = useState(''), [reload, setReload] = useState(0)
  useEffect(() => {
    let active = true
    setListing(null); setError('')
    void getGovernanceWork(enrollmentId).then(value => {
      if (value.enrollment_id !== enrollmentId || value.module_id !== 'governance' || !sameGovernanceCase(value.case, definition)
        || governanceKinds.some(kind => !value.records[kind] || value.records[kind].items.some(item => item.kind !== kind || !id(item.reference_id)))) throw new Error('Different capstone assignment')
      if (active) setListing(value)
    }).catch(() => { if (active) setError('The original capstone assignment could not be loaded. Retry to read the saved course.') })
    return () => { active = false }
  }, [enrollmentId, definition, reload])
  if (!listing) return <section aria-label="Governance supervision capstone">{error ? <><p role="alert" className="text-sm text-red-800">{error}</p><button className={button} onClick={() => setReload(n => n + 1)}>Retry loading capstone assignment</button></> : <p role="status">Loading capstone assignment…</p>}</section>
  return <GovernanceWorkspace key={`${enrollmentId}:${definition.case_sha256}:${historyOnly}`} initial={listing} historyOnly={historyOnly} />
}
function GovernanceWorkspace({ initial, historyOnly }: { initial: GovernanceList; historyOnly: boolean }) {
  const [listing, setListing] = useState(initial), [view, setView] = useState<GovernanceView | null>(null), [artifact, setArtifact] = useState('')
  const [reading, setReading] = useState(false), [error, setError] = useState(''), [reference, setReference] = useState(''), [referenceKind, setReferenceKind] = useState<GovernanceKind>('run')
  const [feedback, setFeedback] = useState(''), [revise, setRevise] = useState(false)
  const sequence = useRef(0), focusSaved = useRef(false), savedRef = useRef<HTMLDivElement>(null)
  const request = useGovernanceRequest(listing, value => { focusSaved.current = true; setView(value); setRevise(false); setFeedback(''); void refresh() }, !historyOnly)
  const canWrite = !historyOnly && listing.can_submit && !request.blocked
  const locked = reading || request.busy || !!request.pending || request.blocked, readLocked = reading || request.busy || !!request.pending
  useEffect(() => { const counter = sequence; return () => { counter.current++ } }, [])
  useLayoutEffect(() => { if (view && focusSaved.current) { focusSaved.current = false; savedRef.current?.focus() } }, [view])
  async function refresh() {
    const token = sequence.current
    try {
      const value = await getGovernanceWork(listing.enrollment_id)
      if (value.enrollment_id !== listing.enrollment_id || value.manifest_sha256 !== listing.manifest_sha256 || !sameGovernanceCase(value.case, listing.case)) throw new Error('Different course')
      if (token === sequence.current) setListing({ ...value, case: listing.case })
    } catch { if (token === sequence.current) setError('Saved capstone choices could not be refreshed. Your open evidence is preserved.') }
  }
  async function open(kind: GovernanceKind, key: string) {
    if (readLocked || !id(key)) return
    const token = ++sequence.current
    setReading(true); setError(''); setFeedback(''); setView(null); setRevise(false)
    try {
      const value = verifyGovernanceView(await getGovernanceRecord(listing.enrollment_id, kind, key), listing)
      if ((value.kind === 'run' ? value.value.run_id : value.value.uuid) !== key) throw new Error('Different saved reference')
      if (token === sequence.current) { focusSaved.current = true; setView(value) }
    } catch { if (token === sequence.current) setError('The original capstone record could not be opened for this course. Check its reference and try again.') }
    finally { if (token === sequence.current) setReading(false) }
  }
  function send(next: GovernanceRequest) {
    if (!canWrite || locked) return
    if (!validGovernanceRequest(next, listing.case)) { setError('Complete the required source references, choices and explanation before saving.'); return }
    setError(''); void request.send(next)
  }
  const key = view ? `${view.kind}:${view.kind === 'run' ? view.value.run_id : view.value.uuid}` : ''
  return <section aria-label="Governance supervision capstone" className="min-w-0 space-y-4 text-gray-900 [overflow-wrap:anywhere]">
    <h4 className="text-lg font-semibold">Supervise the capstone and own its handoff</h4><p className="text-sm">{listing.case.notice}</p><p>{listing.case.task}</p>
    {!canWrite && <p className="text-sm">{historyOnly ? 'Read-only original course history. Opening evidence and files never executes, delivers or grades work.' : listing.read_only_reason}</p>}
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Capstone instructions and scope limits</summary><ol className="list-decimal space-y-2 pl-5 text-sm">{listing.case.instructions.map(item => <li key={item}>{item}</li>)}</ol><ul className="mt-3 list-disc space-y-2 pl-5 text-sm">{listing.case.exclusions.map(item => <li key={item}>{item}</li>)}</ul></details>
    {error && <p role="alert" className="text-sm text-red-800">{error}</p>}{request.error && <p role="alert" className="text-sm text-red-800">{request.error}</p>}
    <CourseRequestStatus phase={request.phase || (reading ? 'checking' : null)} action={request.pending?.action} />
    {request.pending && <section aria-label="Pending capstone request" className={box}><h5 className="font-semibold">Check your original request</h5><p className="text-sm">Its identity and original details are preserved in this tab. Checking only reads saved state.</p><button className={button} disabled={request.busy} onClick={() => { void request.check() }}>Check pending capstone request</button>{request.canFinish && <button className={button} disabled={request.busy} onClick={() => { void request.finish() }}>Finish original capstone request</button>}{request.canDiscard && <button className={button} disabled={request.busy} onClick={request.discard}>Discard unsaved capstone request</button>}</section>}
    {view && <div ref={savedRef} tabIndex={-1} role="region" aria-label="Opened capstone evidence" className={box}><GovernanceEvidence key={`evidence:${key}`} view={view} />
      {view.kind === 'scope' && <button className={button} disabled={readLocked} onClick={() => { void open('run', view.value.run_id) }}>Read this extraction’s current approval and run state</button>}
      {canWrite && <div key={`actions:${key}`} className="min-w-0 space-y-4">
        {view.kind === 'capture' && <>{listing.records.finding.items.length > 0 && <GovernanceRepairPlanForm capture={view.value} listing={listing} locked={locked} send={send} />}<details open={!listing.records.finding.items.length}><summary className="min-h-11 cursor-pointer py-2 font-semibold">Start an original diagnostic exercise from this capture</summary><GovernanceCorrectionForm capture={view.value} locked={locked} send={send} /></details></>}
        {view.kind === 'correction' && <button className={button} disabled={locked} onClick={() => send(governancePlan(view.value.input_snapshot, view.value))}>Prepare original diagnostic extraction</button>}
        {view.kind === 'run' && <><GovernanceRunActions run={view.value} locked={locked} send={send} />
          {view.value.phase === 'original' && view.value.state === 'completed' && (view.value.result?.checks?.fields.find(f => f.field === 'Funds Obligated to Date')?.status === 'revision_required' && view.value.result.checks.complete
            ? <GovernanceFindingForm run={view.value} locked={locked} send={send} />
            : <p className="text-sm">This result does not establish the required readable funding mismatch. Inspect the saved values and original diagnostic instruction. Missing values and provider failures are unavailable evidence; an already-correct result cannot prove this repair exercise.</p>)}
          {view.value.phase === 'repair' && view.value.state === 'completed' && (view.value.result?.repair_checks?.repair_requirements_supported
            ? <GovernanceMemoForm run={view.value} locked={locked} send={send} />
            : <p className="text-sm">The complete retest does not yet support the repair. Preserve this result, inspect the sources, revise the same funding field and capture another revision against the original finding.</p>)}
        </>}
        {view.kind === 'finding' && <section className={box}><h5 className="font-semibold">Repair the same extraction, then capture it</h5><p className="text-sm">Your finding is saved. Edit the Funds Obligated to Date instruction in <strong>{view.value.run.input_snapshot.artifact.title}</strong>. Keep all six field identities and both assigned records. Then capture that changed revision and select this saved finding to prepare its rerun.</p>{listing.extractions.filter(item => item.artifact_id === view.value.run.input_snapshot.artifact_id).map(item => <CourseEditorLink key={item.artifact_id} kind="extraction" artifactId={item.artifact_id} title={item.title} disabled={locked} />)}<button className={button} disabled={locked} onClick={() => send({ action: 'capture', body: { request_id: newId(), artifact_id: view.value.run.input_snapshot.artifact_id, case_sha256: listing.case.case_sha256, consent: 'capture_governance_extraction_and_complete_sources' } })}>Capture my repaired capstone revision</button></section>}
        {view.kind === 'memo' && <GovernanceReleaseForm memo={view.value} locked={locked} send={send} />}
        {view.kind === 'release' && <><GovernanceHandoffActions release={view.value} listing={listing} locked={locked} send={send} /><button className={button} disabled={readLocked} onClick={() => { void open('memo', view.value.memo.uuid) }}>Open this memo to reconsider release</button></>}
        {view.kind === 'handoff' && (view.value.status === 'failed' ? <section className={box}><p className="text-sm">The original failure is confirmed with no destination write. Retry only this memo under its still-current release approval; a newer hold will block the request.</p><button className={button} disabled={locked} onClick={() => send(governanceHandoff(view.value.release, view.value))}>Retry only this failed private memo handoff</button></section> : <GovernanceReviewForm handoff={view.value} locked={locked} send={send} />)}
        {view.kind === 'review' && <>{revise ? <GovernanceReviewForm handoff={view.value.handoff} previous={view.value} locked={locked} send={send} /> : <button className={button} disabled={locked} onClick={() => setRevise(true)}>Revise supervision explanation and preserve original</button>}
          <PracticalAssessment key={view.value.uuid} enrollmentId={listing.enrollment_id} moduleId="governance" governanceReviewSubmissionId={view.value.uuid} onOpenFeedback={setFeedback} />
        </>}
      </div>}
    </div>}
    {canWrite && <form aria-label="Capture your capstone extraction" className={box} onSubmit={e => { e.preventDefault(); send({ action: 'capture', body: { request_id: newId(), artifact_id: artifact, case_sha256: listing.case.case_sha256, consent: 'capture_governance_extraction_and_complete_sources' } }) }}>
      <h5 className="font-semibold">Capture your owned six-field extraction</h5><p className="text-sm">Create an extraction with exactly the field titles below and provision both assigned sources. The original run uses the disclosed diagnostic flaw; the repair changes that same funding field after your saved finding.</p><p className="text-sm">{listing.case.original_field_flaw}</p>
      <ul className="list-disc space-y-2 pl-5 text-sm">{listing.case.fields.map(field => <li key={field.title}><strong>{field.title}</strong>: {field.meaning}</li>)}</ul>
      <label className="block text-sm">Owned capstone extraction<select className={control} required disabled={locked} value={artifact} onChange={e => setArtifact(e.target.value)}><option value="">Select your extraction</option>{listing.extractions.map(item => <option key={item.artifact_id} value={item.artifact_id}>{item.title}</option>)}</select></label>
      {listing.extractions.filter(item => item.artifact_id === artifact).map(item => <CourseEditorLink key={item.artifact_id} kind="extraction" artifactId={item.artifact_id} title={item.title} disabled={locked} />)}
      {!listing.extractions.length && <p className="text-sm">Create an owned extraction with the six required fields, then refresh your choices.</p>}
      <button className={button} disabled={locked || !id(artifact)}>Capture extraction and both capstone sources</button><button type="button" className={button} disabled={locked} onClick={() => { void refresh() }}>Refresh capstone choices</button>
    </form>}
    <section aria-label="Saved capstone history" className={box}><h5 className="font-semibold">Saved capstone history</h5>
      {governanceKinds.map(kind => <details key={kind} open={kind === 'review'}><summary className="min-h-11 cursor-pointer py-2 font-semibold">{governanceLabels[kind]} · {listing.records[kind].items.length} saved</summary><div className="flex flex-wrap gap-2">{listing.records[kind].items.map((item, i) => <button key={item.reference_id} className={button} disabled={readLocked} onClick={() => { void open(kind, item.reference_id) }}>Open {governanceLabels[kind].toLowerCase()} {i + 1}{item.phase ? ` · ${item.phase}` : ''}{item.state ? ` · ${item.state}` : ''}{item.previous_submission_id ? ' · revised answer' : ''}</button>)}</div>{listing.records[kind].older_available && <p className="text-sm">Only the latest 50 are listed. Open older work by its saved reference.</p>}</details>)}
      <form className="space-y-2" onSubmit={e => { e.preventDefault(); void open(referenceKind, reference) }}><label className="block text-sm">Saved capstone record type<select className={control} value={referenceKind} onChange={e => setReferenceKind(e.target.value as GovernanceKind)}>{governanceKinds.map(kind => <option key={kind} value={kind}>{governanceLabels[kind]}</option>)}</select></label><label className="block text-sm">Saved capstone reference<input className={control} required pattern="[a-f0-9]{32}" value={reference} onChange={e => setReference(e.target.value.trim())} /></label><button className={button} disabled={readLocked || !id(reference)}>Open saved capstone reference</button></form>
    </section>
    <SavedAutomaticReviews key={`${listing.enrollment_id}:${feedback}`} enrollmentId={listing.enrollment_id} moduleId="governance" initialAttemptId={feedback || undefined} workNavigationDisabled={readLocked} onOpenWork={review => { void open('review', review.governance_review_submission_id!) }} />
  </section>
}
