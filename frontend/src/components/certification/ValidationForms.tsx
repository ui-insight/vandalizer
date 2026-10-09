import { useCourseScopeDraft } from '../../hooks/useCourseScopeDraft'
import type { Ref } from 'react'
import { draftStrings, useCourseDraft } from '../../hooks/useCourseDraft'
import { CourseDraftNotice } from './CourseDraftNotice'
import type { ValidationCapture, ValidationExpectation, ValidationRequest, ValidationRun } from '../../types/validationSuite'
import { ValidationRunEvidence, validationButton as button, validationControl as control } from './ValidationEvidence'
export const newValidationId = () => crypto.randomUUID().replaceAll('-', '')
const box = 'min-w-0 space-y-3 rounded-lg border border-gray-300 px-[6px] py-3 sm:p-3'
export function ValidationExpectationsForm({ capture, locked, send }: { capture: ValidationCapture; locked: boolean; send: (r: ValidationRequest) => void }) {
  const initial: { expectations: ValidationExpectation[]; design: string } = {
    expectations: capture.case.sources.flatMap(source => capture.case.fields.map(field => ({ source_id: source.id, field: field.title, expected_kind: 'value', expected_value: '', source_references: [{ page: 1, quote: '' }], source_reason: '' }))), design: '',
  }
  function validDraft(value: unknown): value is typeof initial {
    if (!value || typeof value !== 'object') return false
    const draft = value as typeof initial
    return typeof draft.design === 'string' && draft.design.length <= 8000 && Array.isArray(draft.expectations)
      && draft.expectations.length === initial.expectations.length && draft.expectations.every((item, index) => {
        const expected = initial.expectations[index]
        return item?.source_id === expected.source_id && item.field === expected.field
          && ['value', 'explicit_absence'].includes(item.expected_kind)
          && (item.expected_value === null || typeof item.expected_value === 'string' && item.expected_value.length <= 1000)
          && typeof item.source_reason === 'string' && item.source_reason.length <= 3000
          && Array.isArray(item.source_references) && item.source_references.length === 1
          && Number.isFinite(item.source_references[0]?.page)
          && typeof item.source_references[0]?.quote === 'string' && item.source_references[0].quote.length <= 2000
      })
  }
  const [{ expectations, design }, setDraft, status] = useCourseDraft(
    ['validation-expectations', capture.enrollment_id, capture.manifest_sha256, capture.uuid, capture.input_snapshot_sha256, capture.case.case_sha256], initial, validDraft)
  const update = (index: number, value: Partial<ValidationExpectation>) => setDraft(draft => ({ ...draft, expectations: draft.expectations.map((e, i) => i === index ? { ...e, ...value } : e) }))
  return <form aria-label="Save representative test expectations" className={box} onSubmit={e => { e.preventDefault(); send({ action: 'suite', body: { request_id: newValidationId(), input_snapshot_id: capture.uuid, input_snapshot_sha256: capture.input_snapshot_sha256, case_sha256: capture.case.case_sha256, expectations, suite_design: design, consent: 'save_checked_representative_expectations_before_execution' } }) }}>
    <h5 className="text-base font-semibold">Save your expectations before running</h5><p className="text-sm">Read both complete PDFs. For each field, enter the source-supported value or explicit absence, a page quote, and why that evidence supports your choice. Saving does not approve execution or mark your answers correct.</p>
    {expectations.map((item, i) => <fieldset key={`${item.source_id}:${item.field}`} disabled={locked} className={box}><legend className="px-1 text-sm font-semibold">{item.source_id.toUpperCase()} · {item.field}</legend>
      <label className="block text-sm">Expectation type<select className={control} value={item.expected_kind} onChange={e => update(i, { expected_kind: e.target.value as ValidationExpectation['expected_kind'], expected_value: e.target.value === 'explicit_absence' ? null : '' })}><option value="value">Known value</option><option value="explicit_absence">Explicit absence</option></select></label>
      {item.expected_kind === 'value' && <label className="block text-sm">Expected value<input className={control} required maxLength={1000} value={item.expected_value || ''} onChange={e => update(i, { expected_value: e.target.value })} /></label>}
      <label className="block text-sm">Source page<input type="number" min={1} max={capture.documents.find(s => s.source_id === item.source_id)?.pages.length} required className={control} value={item.source_references[0].page} onChange={e => update(i, { source_references: [{ ...item.source_references[0], page: Number(e.target.value) }] })} /></label>
      <label className="block text-sm">Exact source quote<textarea className={control} rows={3} required minLength={3} maxLength={2000} value={item.source_references[0].quote} onChange={e => update(i, { source_references: [{ ...item.source_references[0], quote: e.target.value }] })} /></label>
      <label className="block text-sm">Why this source supports the value or absence<textarea className={control} rows={3} required minLength={20} maxLength={3000} value={item.source_reason} onChange={e => update(i, { source_reason: e.target.value })} /></label>
    </fieldset>)}
    <label className="block text-sm">{capture.case.questions.find(q => q.id === 'suite_design')?.prompt}<textarea className={control} rows={5} required minLength={40} maxLength={8000} disabled={locked} value={design} onChange={e => setDraft(draft => ({ ...draft, design: e.target.value }))} /></label>
    <CourseDraftNotice status={status} />
    <button className={button} disabled={locked}>Save complete test expectations</button>
  </form>
}
export function ValidationRunActions({ run, locked, send }: { run: ValidationRun; locked: boolean; send: (r: ValidationRequest) => void }) {
  const { choice, setChoice, reason, setReason, status } = useCourseScopeDraft('validation-scope', run)
  return <section className="min-w-0 space-y-3">
    {run.can_save_scope && <form aria-label="Approve complete validation suite" className={box} onSubmit={e => { e.preventDefault(); send({ action: 'scope', body: { request_id: newValidationId(), run_id: run.run_id, plan_sha256: run.plan_sha256, case_sha256: run.case_sha256, choice, reason, consent: 'save_validation_suite_scope_decision' } }) }}>
      <h5 className="text-base font-semibold">Approve or hold this complete suite</h5><p className="text-sm">Inspect this exact revision, both full sources, all expectations and models. Approval permits internal extraction for both cases and may incur model usage. It does not award credit or authorize external actions.</p>
      <label className="block text-sm">Scope choice<select disabled={locked} className={control} value={choice} onChange={e => setChoice(e.target.value as 'approve' | 'hold')}><option value="hold">Hold · do not run</option><option value="approve">Approve this exact suite</option></select></label>
      <label className="block text-sm">Why this scope is appropriate<textarea required minLength={10} maxLength={4000} disabled={locked} className={control} value={reason} onChange={e => setReason(e.target.value)} /></label><CourseDraftNotice status={status} /><button className={button} disabled={locked}>Save suite scope choice</button>
    </form>}
    {run.can_execute && <button className={button} disabled={locked} onClick={() => send({ action: 'execute', body: { run_id: run.run_id, plan_sha256: run.plan_sha256, scope_decision_id: run.scope_decision_id!, scope_decision_sha256: run.scope_decision_sha256!, consent: 'execute_approved_complete_validation_suite' } })}>Run both approved validation cases</button>}
    {run.can_finalize && <div className="space-y-2"><p className="text-sm">Both complete case results are saved, but the final receipt is missing. Finalization reconstructs it without repeating extraction.</p><button className={button} disabled={locked} onClick={() => send({ action: 'finalize', body: { run_id: run.run_id, plan_sha256: run.plan_sha256, authorization_sha256: run.authorization_sha256!, case_events_sha256: run.case_events_sha256, consent: 'finalize_saved_validation_results_without_reexecution' } })}>Finalize saved validation results</button></div>}
  </section>
}

export function ValidationInterpretationForm({ run, previous, initialAnswer, locked, send, formRef }: {
  run: ValidationRun; previous: string | null; initialAnswer: string; locked: boolean; send: (r: ValidationRequest) => void; formRef?: Ref<HTMLFormElement>
}) {
  const [{ answer }, setDraft, status] = useCourseDraft(
    ['validation-interpretation', run.enrollment_id, run.manifest_sha256, run.run_id, run.result_sha256, run.case_sha256, previous],
    { answer: initialAnswer }, draftStrings(['answer'], 8000))
  return <form ref={formRef} tabIndex={-1} aria-label="Save validation repair interpretation" className={box} onSubmit={e => { e.preventDefault(); send({ action: 'review', body: {
    request_id: newValidationId(), run_id: run.run_id, result_sha256: run.result_sha256!, case_sha256: run.case_sha256,
    answers: { repair_review: answer }, previous_submission_id: previous, consent: 'save_validation_repair_interpretation' } }) }}>
    <ValidationRunEvidence run={run} />
    <label className="block text-sm">{run.input_snapshot.case.questions.find(q => q.id === 'repair_review')?.prompt}<textarea className={control} rows={7} required maxLength={8000} disabled={locked} value={answer} onChange={e => setDraft({ answer: e.target.value })} /></label>
    <CourseDraftNotice status={status} />
    <button className={button} disabled={locked}>Save repair interpretation</button>
  </form>
}
