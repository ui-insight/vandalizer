import { useBatchInterpretationDraft } from './useBatchInterpretationDraft'
import { CourseDraftNotice } from './CourseDraftNotice'
import { useCourseScopeDraft } from '../../hooks/useCourseScopeDraft'
import { useState } from 'react'
import { getBatchRun } from '../../api/batchAssessment'
import type { BatchList, BatchRequest, BatchRun } from '../../types/batchAssessment'
import { connectedId as id } from './connectedWorkflowState'
import { verifyBatchRun } from './batchAssessmentState'
import { BatchRunEvidence, batchButton as button, batchControl as control, batchPhaseLabel } from './BatchEvidence'
export const newBatchId = () => crypto.randomUUID().replaceAll('-', '')
const box = 'min-w-0 space-y-3 rounded-lg border border-gray-300 px-[6px] py-3 sm:p-3'
export function BatchRunActions({ run, locked, send }: { run: BatchRun; locked: boolean; send: (r: BatchRequest) => void }) {
  const { choice, setChoice, reason, setReason, status } = useCourseScopeDraft('batch-scope', run)
  const question = { pilot: 'pilot_choice', batch: 'scale_choice', retry: 'recovery_choice' }[run.phase]
  return <section className="min-w-0 space-y-3">
    {run.can_save_scope && <form aria-label="Approve bounded batch action" className={box} onSubmit={e => { e.preventDefault(); send({ action: 'scope', body: { request_id: newBatchId(), run_id: run.run_id, plan_sha256: run.plan_sha256, case_sha256: run.case_sha256, choice, reason, consent: 'save_bounded_batch_scope_decision' } }) }}>
      <h5 className="text-base font-semibold">Approve or hold: {batchPhaseLabel[run.phase]}</h5><p className="text-sm">Inspect the exact sources, revision and model above. Approval permits only this displayed internal action and may incur model usage. It does not award credit or authorize external effects.</p>
      <label className="block text-sm">Scope choice<select disabled={locked} className={control} value={choice} onChange={e => setChoice(e.target.value as 'approve' | 'hold')}><option value="hold">Hold · do not run</option><option value="approve">Approve this exact action</option></select></label>
      <label className="block text-sm">{run.input_snapshot.case.questions.find(q => q.id === question)?.prompt}<textarea required minLength={10} maxLength={4000} rows={5} disabled={locked} className={control} value={reason} onChange={e => setReason(e.target.value)} /></label><CourseDraftNotice status={status} /><button className={button} disabled={locked}>Save batch scope choice</button>
    </form>}
    {run.can_execute && <button className={button} disabled={locked} onClick={() => send({ action: 'execute', body: { run_id: run.run_id, plan_sha256: run.plan_sha256, scope_decision_id: run.scope_decision_id!, scope_decision_sha256: run.scope_decision_sha256!, consent: 'execute_approved_bounded_batch_action' } })}>Run approved {run.phase === 'retry' ? 'failed item' : run.phase}</button>}
    {run.can_finalize && <div className="space-y-2"><p className="text-sm">Every selected item has a terminal receipt, but the final inventory receipt is missing. Finalization preserves failures and does not repeat extraction.</p><button className={button} disabled={locked} onClick={() => send({ action: 'finalize', body: { run_id: run.run_id, plan_sha256: run.plan_sha256, authorization_sha256: run.authorization_sha256!, item_events_sha256: run.item_events_sha256, consent: 'finalize_saved_batch_results_without_reexecution' } })}>Finalize saved batch inventory</button></div>}
  </section>
}
export function BatchInterpretationForm({ listing, original, initialRetries, initialAnswer = '', previous = null, locked, send }: {
  listing: BatchList; original: BatchRun; initialRetries: BatchRun[]; initialAnswer?: string; previous?: string | null; locked: boolean; send: (r: BatchRequest) => void
}) {
  const { draft, setDraft, status, retries, restoring, restoreError, reread, clearReferences } = useBatchInterpretationDraft(listing, original, initialRetries, initialAnswer, previous)
  const { answer, reference } = draft
  const setAnswer = (answer: string) => setDraft(value => ({ ...value, answer }))
  const setReference = (reference: string) => setDraft(value => ({ ...value, reference }))
  const [reading, setReading] = useState(false), [error, setError] = useState('')
  async function include() {
    if (reading || restoring || restoreError || locked || !id(reference)) return
    setReading(true); setError('')
    try {
      const retry = verifyBatchRun(await getBatchRun(listing.enrollment_id, reference), listing)
      if (retry.run_id !== reference || retry.phase !== 'retry' || retry.state !== 'completed' || retry.parent_run?.run_sha256 !== original.run_sha256) throw new Error('Different retry')
      const next = [...retries.filter(item => item.failed_source_id !== retry.failed_source_id), retry]
      setDraft(value => ({ ...value, reference: '', retries: next.map(item => ({ run_id: item.run_id, result_sha256: item.result_sha256! })) }))
    } catch { setError('This is not a complete saved retry for the original batch. Check the original receipt and reference.') }
    finally { setReading(false) }
  }
  return <section className={box} aria-label="Batch recovery interpretation">
    <BatchRunEvidence run={original} />
    <h5 className="font-semibold">Selected recovery receipts</h5>
    {restoring && <p role="status" className="text-sm">Reading the selected saved retry receipts…</p>}
    {restoreError && <div className="space-y-2"><p role="alert" className="text-sm text-red-800">{restoreError}</p><button type="button" className={button} disabled={locked || restoring} onClick={reread}>Read selected retry receipts again</button><button type="button" className={button} disabled={locked || restoring} onClick={clearReferences}>Clear selected retry references and keep my explanation</button></div>}
    {retries.map(retry => <details key={retry.run_id}><summary className="min-h-11 cursor-pointer py-2">{retry.failed_source_id?.replace('_', ' ')} · {retry.result?.checks?.all_values_source_supported ? 'Source-supported recovery' : 'Unresolved recovery'}</summary><BatchRunEvidence run={retry} /></details>)}
    <p className="text-sm">If more than one original item failed, include its own latest saved retry. Selecting a receipt reads existing work; it never reruns an item.</p>
    <form className="space-y-2" onSubmit={e => { e.preventDefault(); void include() }}><label className="block text-sm">Additional saved retry reference<input className={control} disabled={locked || reading || restoring || !!restoreError} value={reference} onChange={e => setReference(e.target.value.trim())} pattern="[a-f0-9]{32}" required /></label><button className={button} disabled={locked || reading || restoring || !!restoreError || !id(reference)}>Read and include saved retry</button></form>
    {error && <p role="alert" className="text-sm text-red-800">{error}</p>}
    <form aria-label="Save batch recovery interpretation" className="space-y-3" onSubmit={e => { e.preventDefault(); if (locked || reading || restoring || restoreError || !retries.length) return; send({ action: 'review', body: { request_id: newBatchId(), run_id: original.run_id, result_sha256: original.result_sha256!, case_sha256: listing.case.case_sha256,
      retries: retries.map(r => ({ run_id: r.run_id, result_sha256: r.result_sha256! })), answers: { batch_review: answer }, previous_submission_id: previous, consent: 'save_batch_recovery_interpretation' } }) }}>
      <label className="block text-sm">{listing.case.questions.find(q => q.id === 'batch_review')?.prompt}<textarea className={control} rows={7} required maxLength={8000} disabled={locked || reading || restoring || !!restoreError} value={answer} onChange={e => setAnswer(e.target.value)} /></label><CourseDraftNotice status={status} /><button className={button} disabled={locked || reading || restoring || !!restoreError || !retries.length}>Save batch interpretation</button>
    </form>
  </section>
}
