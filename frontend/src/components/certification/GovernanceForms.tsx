import { useCourseScopeDraft } from '../../hooks/useCourseScopeDraft'
import { useEffect, useRef, useState } from 'react'
import { draftStrings, useCourseDraft } from '../../hooks/useCourseDraft'
import { CourseDraftNotice } from './CourseDraftNotice'
import type { ReactNode } from 'react'
import { getGovernanceRecord } from '../../api/governanceAssessment'
import type { GovernanceCapture, GovernanceCorrection, GovernanceFinding, GovernanceList, GovernanceRun, GovernanceMemo, GovernanceRelease, GovernanceHandoff, GovernanceReview, GovernanceRequest } from '../../types/governanceAssessment'
import { governanceId as newId, verifyGovernanceView } from './governanceAssessmentState'
import { governanceBox as box, governanceButton as button, governanceControl as control } from './GovernanceEvidence'
type Send = (request: GovernanceRequest) => void
type Common = { locked: boolean; send: Send }
const question = (definition: GovernanceList['case'], id: string) => definition.questions.find(q => q.id === id)?.prompt
function Answer({ label, value, onChange, disabled, min = 40, max = 8000, rows = 5 }: { label: ReactNode; value: string; onChange: (s: string) => void; disabled: boolean; min?: number; max?: number; rows?: number }) {
  return <label className="block space-y-1 text-sm"><span>{label}</span><textarea className={control} required minLength={min} maxLength={max} rows={rows} disabled={disabled} value={value} onChange={e => onChange(e.target.value)} /></label>
}
export function governancePlan(capture: GovernanceCapture, correction: GovernanceCorrection, finding: GovernanceFinding | null = null): GovernanceRequest {
  return { action: 'prepare', body: { request_id: newId(), input_snapshot_id: capture.uuid, input_snapshot_sha256: capture.input_snapshot_sha256,
    scope_correction_id: correction.uuid, scope_correction_sha256: correction.record_sha256, case_sha256: capture.case.case_sha256,
    source_finding_id: finding?.uuid || null, source_finding_sha256: finding?.record_sha256 || null,
    consent: finding ? 'prepare_repaired_bounded_capstone_extraction' : 'prepare_original_bounded_capstone_extraction' } }
}
export function GovernanceCorrectionForm({ capture, locked, send }: Common & { capture: GovernanceCapture }) {
  const [{ reason }, setDraft, status] = useCourseDraft(
    ['governance-correction', capture.enrollment_id, capture.manifest_sha256, capture.uuid, capture.input_snapshot_sha256, capture.case.case_sha256],
    { reason: '' }, draftStrings(['reason'], 8000))
  const setReason = (reason: string) => setDraft({ reason })
  return <form aria-label="Correct the proposed capstone scope" className={box} onSubmit={e => { e.preventDefault(); send({ action: 'correction', body: {
    request_id: newId(), input_snapshot_id: capture.uuid, input_snapshot_sha256: capture.input_snapshot_sha256, case_sha256: capture.case.case_sha256,
    choice: 'reject_broad_proposal', source_document_ids: capture.documents.map(s => s.document_id), destination_id: 'private_training_inbox', audience: 'enrolled_learner_only', ongoing_automation: 'keep_disabled', reason,
    consent: 'save_my_corrected_capstone_scope_without_execution' } }) }}>
    <h5 className="font-semibold">Correct the agent’s scope before the original run</h5><p className="text-sm">Flawed proposal: {capture.case.flawed_proposal}</p>
    <p className="text-sm">Your saved correction will limit the work to the two exact assigned records and your learner-only private inbox. Broad sharing, sponsor sends and recurring actions remain disabled. This step does not run extraction.</p>
    <Answer label={question(capture.case, 'scope_correction')} value={reason} onChange={setReason} disabled={locked} />
    <CourseDraftNotice status={status} />
    <button className={button} disabled={locked}>Save my corrected capstone scope</button>
  </form>
}
export function GovernanceRepairPlanForm({ capture, listing, locked, send }: Common & { capture: GovernanceCapture; listing: GovernanceList }) {
  const [reference, setReference] = useState(''), [reading, setReading] = useState(false), [error, setError] = useState('')
  const active = useRef(true), sending = useRef(false)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  async function prepare() {
    if (locked || sending.current || !reference) return
    sending.current = true; setReading(true); setError('')
    try {
      const finding = verifyGovernanceView(await getGovernanceRecord(listing.enrollment_id, 'finding', reference), listing)
      if (finding.kind !== 'finding' || finding.value.uuid !== reference || finding.value.run.input_snapshot.artifact_id !== capture.artifact_id) throw new Error('Different original extraction')
      if (active.current) send(governancePlan(capture, finding.value.run.scope_correction, finding.value))
    } catch { if (active.current) setError('The original finding could not be read for this owned extraction. Inspect its saved reference before preparing the repair.') }
    finally { sending.current = false; if (active.current) setReading(false) }
  }
  return <form aria-label="Prepare the changed capstone revision" className={box} onSubmit={e => { e.preventDefault(); void prepare() }}>
    <h5 className="font-semibold">Use this capture for a repaired run</h5><p className="text-sm">First save your original source finding, edit the same funding field in your extraction, then capture that changed revision. This plan keeps both original sources and the original models. Preparation does not run it.</p>
    <label className="block text-sm">Your saved original source finding<select className={control} required disabled={locked || reading} value={reference} onChange={e => setReference(e.target.value)}><option value="">Select the original finding</option>{listing.records.finding.items.map((item, i) => <option key={item.reference_id} value={item.reference_id}>Source finding {i + 1} · {item.saved_at}</option>)}</select></label>
    {error && <p role="alert" className="text-sm text-red-800">{error}</p>}<button className={button} disabled={locked || reading || !reference}>{reading ? 'Reading original finding…' : 'Prepare this repaired complete extraction'}</button>
  </form>
}
export function GovernanceRunActions({ run, locked, send }: Common & { run: GovernanceRun }) {
  const { choice, setChoice, reason, setReason, status } = useCourseScopeDraft('governance-scope', run)
  return <div className="min-w-0 space-y-3">
    {run.can_save_scope && <form aria-label="Approve or hold the exact capstone extraction" className={box} onSubmit={e => { e.preventDefault(); send({ action: 'scope', body: { request_id: newId(), run_id: run.run_id, plan_sha256: run.plan_sha256,
      case_sha256: run.case_sha256, choice, reason, consent: 'save_bounded_governance_execution_decision' } }) }}>
      <h5 className="font-semibold">Approve or hold this exact {run.phase === 'original' ? 'original diagnostic run' : 'repaired complete run'}</h5><p className="text-sm">{run.approval_question.prompt}</p>
      <label className="block text-sm">Execution choice<select className={control} disabled={locked} value={choice} onChange={e => setChoice(e.target.value as 'approve' | 'hold')}><option value="hold">Hold · do not run</option><option value="approve">Approve this exact extraction</option></select></label>
      <Answer label="Explain your execution scope choice" value={reason} onChange={setReason} disabled={locked} min={10} max={4000} />
      <CourseDraftNotice status={status} /><button className={button} disabled={locked}>Save capstone execution choice</button>
    </form>}
    {run.can_execute && <button className={button} disabled={locked} onClick={() => send({ action: 'execute', body: { run_id: run.run_id, plan_sha256: run.plan_sha256,
      scope_decision_id: run.scope_decision_id!, scope_decision_sha256: run.scope_decision_sha256!, consent: 'execute_approved_bounded_capstone_extraction' } })}>Run approved {run.phase === 'original' ? 'original diagnostic extraction' : 'repaired complete extraction'}</button>}
    {run.can_finalize && <div className="space-y-2"><p className="text-sm">The complete extraction output was saved, but its final receipt is missing. Finalization uses that saved output without another model call.</p><button className={button} disabled={locked} onClick={() => send({ action: 'finalize', body: { run_id: run.run_id, plan_sha256: run.plan_sha256, authorization_sha256: run.authorization_sha256!, extraction_events_sha256: run.extraction_events_sha256, consent: 'finalize_saved_governance_results_without_reexecution' } })}>Finalize saved capstone extraction</button></div>}
  </div>
}
export function GovernanceFindingForm({ run, locked, send }: Common & { run: GovernanceRun }) {
  const initial = { value: '', explanation: '', award: '', amendment: '', awardPage: 1, amendmentPage: 1 }
  function validFinding(value: unknown): value is typeof initial {
    if (!value || typeof value !== 'object') return false
    const draft = value as typeof initial
    return draftStrings(['value', 'award', 'amendment'], 2000)({ value: draft.value, award: draft.award, amendment: draft.amendment })
      && typeof draft.explanation === 'string' && draft.explanation.length <= 8000
      && Number.isFinite(draft.awardPage) && Number.isFinite(draft.amendmentPage)
  }
  const [{ value, explanation, award, amendment, awardPage, amendmentPage }, setDraft, status] = useCourseDraft(
    ['governance-finding', run.enrollment_id, run.manifest_sha256, run.run_id, run.result_sha256, run.case_sha256], initial, validFinding)
  const setValue = (value: string) => setDraft(draft => ({ ...draft, value }))
  const setExplanation = (explanation: string) => setDraft(draft => ({ ...draft, explanation }))
  const setAward = (award: string) => setDraft(draft => ({ ...draft, award }))
  const setAmendment = (amendment: string) => setDraft(draft => ({ ...draft, amendment }))
  const setAwardPage = (awardPage: number) => setDraft(draft => ({ ...draft, awardPage }))
  const setAmendmentPage = (amendmentPage: number) => setDraft(draft => ({ ...draft, amendmentPage }))
  return <form aria-label="Record the original source finding" className={box} onSubmit={e => { e.preventDefault(); send({ action: 'finding', body: {
    request_id: newId(), run_id: run.run_id, result_sha256: run.result_sha256!, case_sha256: run.case_sha256, field: 'Funds Obligated to Date', observed_value: value,
    source_references: [{ source_id: 'award', page: awardPage, quote: award }, { source_id: 'amendment', page: amendmentPage, quote: amendment }], explanation, consent: 'save_my_original_source_finding_before_repair' } }) }}>
    <h5 className="font-semibold">Save your source finding before editing</h5><p className="text-sm">{question(run.input_snapshot.case, 'source_review')}</p>
    <label className="block text-sm">Actual unsupported Funds Obligated to Date value<input className={control} required maxLength={2000} disabled={locked} value={value} onChange={e => setValue(e.target.value)} /></label>
    <label className="block text-sm">Award notice page<input className={control} type="number" required min={1} max={100} disabled={locked} value={awardPage} onChange={e => setAwardPage(Number(e.target.value))} /></label>
    <Answer label="Exact award notice page quote" value={award} onChange={setAward} disabled={locked} min={10} max={2000} rows={3} />
    <label className="block text-sm">Issued amendment page<input className={control} type="number" required min={1} max={100} disabled={locked} value={amendmentPage} onChange={e => setAmendmentPage(Number(e.target.value))} /></label>
    <Answer label="Exact issued amendment page quote" value={amendment} onChange={setAmendment} disabled={locked} min={10} max={2000} rows={3} />
    <Answer label="Explain the actual mismatch and the instruction change you will test" value={explanation} onChange={setExplanation} disabled={locked} />
    <CourseDraftNotice status={status} />
    <button className={button} disabled={locked}>Save my original capstone source finding</button>
  </form>
}
export function GovernanceMemoForm({ run, locked, send }: Common & { run: GovernanceRun }) {
  const [{ use, inputs, limits, route }, setDraft, status] = useCourseDraft(
    ['governance-memo', run.enrollment_id, run.manifest_sha256, run.run_id, run.result_sha256, run.case_sha256],
    { use: '', inputs: '', limits: '', route: '' }, draftStrings(['use', 'inputs', 'limits', 'route'], 5000))
  const setUse = (use: string) => setDraft(draft => ({ ...draft, use }))
  const setInputs = (inputs: string) => setDraft(draft => ({ ...draft, inputs }))
  const setLimits = (limits: string) => setDraft(draft => ({ ...draft, limits }))
  const setRoute = (route: string) => setDraft(draft => ({ ...draft, route }))
  return <form aria-label="Write the accountable capstone memo" className={box} onSubmit={e => { e.preventDefault(); send({ action: 'memo', body: {
    request_id: newId(), run_id: run.run_id, result_sha256: run.result_sha256!, case_sha256: run.case_sha256, owner_user_id: run.scope_correction.user_id,
    intended_use: use, supported_inputs: inputs, limitations: limits, review_route: route, consent: 'save_checked_capstone_memo_without_release' } }) }}>
    <h5 className="font-semibold">Write the accountable handoff memo</h5><p className="text-sm">You are the responsible training owner. The memo will include the six actual checked values and exact source/revision references. Describe its use and limits; saving it does not release or deliver it.</p>
    <Answer label="Intended use" value={use} onChange={setUse} disabled={locked} min={20} max={5000} />
    <Answer label="Supported inputs and source scope" value={inputs} onChange={setInputs} disabled={locked} min={20} max={5000} />
    <Answer label="Known limitations" value={limits} onChange={setLimits} disabled={locked} min={20} max={5000} />
    <Answer label="Change and review route · distinguish real-world review roles from certification staff" value={route} onChange={setRoute} disabled={locked} min={20} max={5000} />
    <CourseDraftNotice status={status} />
    <button className={button} disabled={locked}>Save checked accountable memo</button>
  </form>
}
export function GovernanceReleaseForm({ memo, locked, send }: Common & { memo: GovernanceMemo }) {
  type ReleaseDraft = { opened: boolean; choice: 'approve' | 'hold'; reason: string }
  const validRelease = (value: unknown): value is ReleaseDraft => !!value && typeof value === 'object'
    && typeof (value as ReleaseDraft).opened === 'boolean' && ['approve', 'hold'].includes((value as ReleaseDraft).choice)
    && typeof (value as ReleaseDraft).reason === 'string' && (value as ReleaseDraft).reason.length <= 8000
  const [{ opened, choice, reason }, setDraft, status] = useCourseDraft<ReleaseDraft>(
    ['governance-release', memo.enrollment_id, memo.manifest_sha256, memo.uuid, memo.record_sha256, memo.file.sha256, memo.case.case_sha256],
    { opened: false, choice: 'hold', reason: '' }, validRelease)
  const setOpened = (opened: boolean) => setDraft(draft => ({ ...draft, opened }))
  const setChoice = (choice: ReleaseDraft['choice']) => setDraft(draft => ({ ...draft, choice }))
  const setReason = (reason: string) => setDraft(draft => ({ ...draft, reason }))
  return <form aria-label="Inspect and decide capstone memo release" className={box} onSubmit={e => { e.preventDefault(); send({ action: 'release', body: {
    request_id: newId(), run_id: memo.run_id, case_sha256: memo.case.case_sha256, memo_id: memo.uuid, memo_sha256: memo.record_sha256, file_sha256: memo.file.sha256,
    opened, choice, reason, destination_id: 'private_training_inbox', audience: 'enrolled_learner_only', consent: 'save_my_exact_capstone_memo_release_choice' } }) }}>
    <h5 className="font-semibold">Inspect exact bytes, then approve or hold</h5><p className="text-sm">Download and inspect the actual JSON memo above. Approval covers only these bytes and your private training inbox. Opening acknowledgement alone does not prove source correctness or sound reasoning.</p>
    <label className="flex min-h-11 items-start gap-2 py-2 text-sm"><input className="mt-1 h-6 w-6 shrink-0" type="checkbox" disabled={locked} checked={opened} onChange={e => setOpened(e.target.checked)} />I opened and inspected this exact downloaded memo.</label>
    <label className="block text-sm">Memo release choice<select className={control} disabled={locked} value={choice} onChange={e => setChoice(e.target.value as 'approve' | 'hold')}><option value="hold">Hold · do not deliver</option><option value="approve">Approve learner-only private handoff</option></select></label>
    <Answer label={question(memo.case, 'release_review')} value={reason} onChange={setReason} disabled={locked} />
    <CourseDraftNotice status={status} />
    <button className={button} disabled={locked || choice === 'approve' && !opened}>Save my exact memo release choice</button>
  </form>
}
export function governanceHandoff(release: GovernanceRelease, previous: GovernanceHandoff | null = null): GovernanceRequest {
  return { action: 'handoff', body: { request_id: newId(), run_id: release.run_id, case_sha256: release.case.case_sha256,
    memo_id: release.memo.uuid, memo_sha256: release.memo.record_sha256, file_sha256: release.memo.file.sha256, release_id: release.uuid, release_sha256: release.record_sha256,
    destination_id: 'private_training_inbox', action: previous ? 'retry_failed_handoff' : 'attempt', previous_failed_id: previous?.uuid || null,
    previous_failed_sha256: previous?.record_sha256 || null, consent: previous ? 'retry_only_failed_private_capstone_handoff' : 'attempt_approved_private_capstone_handoff' } }
}
export function GovernanceReviewForm({ handoff, previous, locked, send }: Common & { handoff: GovernanceHandoff; previous?: GovernanceReview }) {
  const [{ answer }, setDraft, status] = useCourseDraft(
    ['governance-review', handoff.enrollment_id, handoff.manifest_sha256, handoff.uuid, handoff.record_sha256, previous?.uuid || null],
    { answer: previous?.submission.final_supervision || '' }, draftStrings(['answer'], 8000))
  const setAnswer = (answer: string) => setDraft({ answer })
  return <form aria-label="Explain your complete capstone supervision" className={box} onSubmit={e => { e.preventDefault(); send({ action: 'review', body: {
    request_id: newId(), run_id: handoff.run_id, case_sha256: handoff.case.case_sha256, handoff_id: handoff.uuid, handoff_sha256: handoff.record_sha256,
    final_supervision: answer, previous_submission_id: previous?.uuid || null, consent: 'save_my_capstone_supervision_interpretation' } }) }}>
    <h5 className="font-semibold">{previous ? 'Revise your explanation and preserve the original' : 'Explain the complete supervision chain'}</h5>
    <Answer label={question(handoff.case, 'final_supervision')} value={answer} onChange={setAnswer} disabled={locked} rows={8} />
    <CourseDraftNotice status={status} />
    <button className={button} disabled={locked}>{previous ? 'Save revised capstone interpretation' : 'Save my capstone supervision interpretation'}</button>
  </form>
}
export function GovernanceHandoffActions({ release, listing, locked, send }: Common & { release: GovernanceRelease; listing: GovernanceList }) {
  const receipts = listing.records.handoff.items.filter(item => item.memo_id === release.memo.uuid)
  const [reference, setReference] = useState(''), [reading, setReading] = useState(false), [error, setError] = useState('')
  const active = useRef(true), sending = useRef(false)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  async function retry() {
    if (locked || sending.current || !reference) return
    sending.current = true; setReading(true); setError('')
    try {
      const original = verifyGovernanceView(await getGovernanceRecord(listing.enrollment_id, 'handoff', reference), listing)
      if (original.kind !== 'handoff' || original.value.uuid !== reference || original.value.status !== 'failed' || original.value.submission.memo_sha256 !== release.memo.record_sha256) throw new Error('Different confirmed failure')
      if (active.current) send(governanceHandoff(release, original.value))
    } catch { if (active.current) setError('Read the original confirmed no-write failure for this exact memo before retrying it.') }
    finally { sending.current = false; if (active.current) setReading(false) }
  }
  if (release.submission.choice !== 'approve') return <p className="text-sm">This release is held. Open the memo to save a new release choice after addressing your concern.</p>
  if (receipts.some(item => item.state === 'delivered')) return <p className="text-sm">This memo already has a confirmed private copy. Open its saved handoff receipt to continue; do not send it again.</p>
  return <section aria-label="Explicit private capstone handoff" className={box}><h5 className="font-semibold">Private training handoff</h5>
    {!receipts.length && <><p className="text-sm">The first approved attempt is deliberately rejected before any private copy is written. You will inspect that receipt before requesting a same-bytes retry.</p><button className={button} disabled={locked || reading} onClick={() => send(governanceHandoff(release))}>Attempt approved private memo handoff</button></>}
    <form className="space-y-3" onSubmit={e => { e.preventDefault(); void retry() }}><p className="text-sm">If this memo has a confirmed first no-write failure, read that receipt and explicitly retry only the same approved bytes. A newer hold still blocks retry.</p>
      <label className="block text-sm">Original failed handoff reference<input className={control} disabled={locked || reading} required pattern="[a-f0-9]{32}" value={reference} onChange={e => setReference(e.target.value.trim())} list={`governance-failures-${release.uuid}`} /></label>
      <datalist id={`governance-failures-${release.uuid}`}>{receipts.filter(item => item.state === 'failed').map(item => <option key={item.reference_id} value={item.reference_id}>Confirmed no-write failure</option>)}</datalist>
      {error && <p role="alert" className="text-sm text-red-800">{error}</p>}<button className={button} disabled={locked || reading || !reference}>{reading ? 'Reading original failure…' : 'Retry confirmed failure with this exact release'}</button>
    </form>
  </section>
}
