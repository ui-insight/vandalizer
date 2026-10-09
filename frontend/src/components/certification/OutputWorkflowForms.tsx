import { CourseDraftNotice } from './CourseDraftNotice'
import { useCourseScopeDraft } from '../../hooks/useCourseScopeDraft'
import type { Ref } from 'react'
import { draftStrings, useCourseDraft } from '../../hooks/useCourseDraft'
import type { OutputInspectionBody, OutputRequest, OutputRun, OutputInspection, OutputHandoff } from '../../types/outputWorkflow'
import { OutputRunEvidence, OutputHandoffEvidence, outputButton as button, outputControl as control } from './OutputWorkflowEvidence'
export const newOutputId = () => crypto.randomUUID().replaceAll('-', '')

export function OutputRunActions({ run, locked, send, onInspect }: { run: OutputRun; locked: boolean; send: (request: OutputRequest) => void; onInspect: () => void }) {
  const { choice, setChoice, reason, setReason, status } = useCourseScopeDraft('output-scope', run)
  return <div className="space-y-3">
    {run.scope_decision && <p className="text-sm">Saved generation choice: {run.scope_decision.submission.choice}. {run.scope_decision.submission.reason}</p>}
    {run.can_save_scope && <form aria-label="Approve output generation" className="space-y-3" onSubmit={event => { event.preventDefault(); send({ action: 'scope', body: { request_id: newOutputId(), run_id: run.run_id, plan_sha256: run.plan_sha256, case_sha256: run.case_sha256, choice, reason, consent: 'save_output_workflow_scope_decision' } }) }}>
      <p className="text-sm">Inspect the saved source, all four stages, inputs and models. This approval permits internal file generation only and may incur model usage. Release approval comes after file inspection.</p>
      <label className="block text-sm">Generation choice<select className={control} value={choice} disabled={locked} onChange={event => setChoice(event.target.value as typeof choice)}><option value="hold">Hold for correction</option><option value="approve">Approve this exact internal generation</option></select></label>
      <label className="block text-sm">Explain this generation decision<textarea className={control} rows={3} required minLength={10} maxLength={4000} disabled={locked} value={reason} onChange={event => setReason(event.target.value)} /></label>
      <CourseDraftNotice status={status} /><button className={button} disabled={locked}>Save generation scope decision</button>
    </form>}
    {run.can_execute && <button className={button} disabled={locked} onClick={() => send({ action: 'execute', body: { run_id: run.run_id, plan_sha256: run.plan_sha256, scope_decision_id: run.scope_decision_id!, scope_decision_sha256: run.scope_decision_sha256!, consent: 'execute_approved_output_workflow' } })}>Generate these approved files</button>}
    {run.can_finalize && <button className={button} disabled={locked} onClick={() => send({ action: 'finalize', body: { run_id: run.run_id, plan_sha256: run.plan_sha256, authorization_sha256: run.authorization_sha256!, stage_events_sha256: run.stage_events_sha256, consent: 'finalize_saved_output_results_without_reexecution' } })}>Finalize saved files without regenerating</button>}
    {run.can_inspect && <button className={button} disabled={locked} onClick={onInspect}>Inspect these files and choose release scope</button>}
    {run.handoff_claimed && <p className="text-sm">A handoff has been claimed for this run. Read its original receipt before taking another action.</p>}
  </div>
}

export function OutputInspectionForm({ run, locked, send }: { run: OutputRun; locked: boolean; send: (request: OutputRequest) => void }) {
  const artifacts = run.result!.generated_artifacts!
  type Draft = Pick<OutputInspectionBody, 'file_inspections' | 'bundle_opened' | 'answers' | 'choice'>
  const [body, change, status] = useCourseDraft<Draft>([
    'output-inspection', run.enrollment_id, run.manifest_sha256, run.run_id, run.result_sha256, run.case_sha256,
    artifacts.artifacts_sha256, artifacts.download.sha256, ...artifacts.files.map(file => file.sha256),
    run.release_decision?.uuid || null, run.release_decision?.review_sha256 || null,
  ], { file_inspections: artifacts.files.map(file => ({ sha256: file.sha256, opened: false, judgment: 'unresolved', observations: '' })),
    bundle_opened: false, answers: { artifact_review: '', release_decision: '' }, choice: 'hold' },
  (value): value is Draft => {
    if (!value || typeof value !== 'object') return false
    const saved = value as Draft
    return Array.isArray(saved.file_inspections) && saved.file_inspections.length === artifacts.files.length
      && saved.file_inspections.every((file, index) => !!file && file.sha256 === artifacts.files[index].sha256
        && typeof file.observations === 'string' && file.observations.length <= 8000 && typeof file.opened === 'boolean'
        && ['usable', 'needs_repair', 'unresolved'].includes(file.judgment))
      && draftStrings(['artifact_review', 'release_decision'], 8000)(saved.answers)
      && typeof saved.bundle_opened === 'boolean' && ['approve', 'hold'].includes(saved.choice)
  })
  return <form aria-label="Inspect files and approve release" className="min-w-0 space-y-4" onSubmit={event => { event.preventDefault(); send({ action: 'inspection', body: { file_inspections: body.file_inspections, answers: body.answers, choice: body.choice, bundle_opened: body.bundle_opened, request_id: newOutputId(), run_id: run.run_id, result_sha256: run.result_sha256!, case_sha256: run.case_sha256, artifacts_sha256: artifacts.artifacts_sha256, bundle_sha256: artifacts.download.sha256, destination_id: 'private_training_inbox', audience: 'enrolled_learner_only', data_scope: 'approved_generated_files_only', consent: 'save_exact_output_inspection_and_release_choice' } }) }}>
    <h5 className="text-base font-semibold">Review these exact files before release</h5>
    <OutputRunEvidence run={run} />
    {artifacts.files.map((file, index) => { const check = body.file_inspections[index]; const update = (patch: Partial<typeof check>) => change({ ...body, file_inspections: body.file_inspections.map((value, position) => position === index ? { ...value, ...patch } : value) }); return <fieldset key={file.sha256} className="min-w-0 space-y-3 rounded-lg border border-gray-300 px-1.5 py-3 sm:p-3">
      <legend className="max-w-full px-1 text-sm font-semibold">Your inspection of {file.filename}</legend>
      <label className="flex min-h-11 items-start gap-3 py-2 text-sm"><input className="mt-0.5 h-6 w-6 shrink-0" type="checkbox" disabled={locked} checked={check.opened} onChange={event => update({ opened: event.target.checked })} />I opened {file.filename} and inspected its actual contents.</label>
      <label className="block text-sm">Usability of {file.filename}<select className={control} disabled={locked} value={check.judgment} onChange={event => update({ judgment: event.target.value as typeof check.judgment })}><option value="unresolved">Not resolved yet</option><option value="needs_repair">Needs repair</option><option value="usable">Usable after inspection</option></select></label>
      <label className="block text-sm">What you checked in {file.filename}<textarea className={`${control} min-h-28`} rows={4} required minLength={10} maxLength={8000} disabled={locked} value={check.observations} onChange={event => update({ observations: event.target.value })} /></label>
    </fieldset> })}
    <label className="flex min-h-11 items-start gap-3 py-2 text-sm"><input className="mt-0.5 h-6 w-6 shrink-0" type="checkbox" disabled={locked} checked={body.bundle_opened} onChange={event => change({ ...body, bundle_opened: event.target.checked })} />I opened the actual ZIP bundle and checked every member.</label>
    {run.input_snapshot.case.questions.filter(question => question.phase === 'after_generation_before_release').map(question => <label key={question.id} className="block text-sm">{question.prompt}<textarea className={`${control} min-h-36`} rows={6} required minLength={10} maxLength={8000} disabled={locked} value={body.answers[question.id as keyof typeof body.answers]} onChange={event => change({ ...body, answers: { ...body.answers, [question.id]: event.target.value } })} /></label>)}
    <section className="space-y-2 rounded-lg border border-amber-300 bg-amber-50 px-1.5 py-3 sm:p-3 text-sm"><p><strong>Destination:</strong> Your private training inbox.</p><p><strong>Audience:</strong> You alone. <strong>Data scope:</strong> Only these exact generated files.</p><p>{run.input_snapshot.case.destination.description}</p><p>The first authorized training attempt deliberately fails before copying. This choice does not send anything; you will explicitly request the handoff next.</p></section>
    <label className="block text-sm">Release choice<select className={control} disabled={locked} value={body.choice} onChange={event => change({ ...body, choice: event.target.value as typeof body.choice })}><option value="hold">Hold for correction</option><option value="approve" disabled={!artifacts.all_required_files_parseable}>Approve private-inbox release</option></select></label>
    <CourseDraftNotice status={status} /><button className={button} disabled={locked}>Save inspection and release choice</button>
  </form>
}


export function OutputInterpretationForm({ inspection, handoff, previous, initialAnswer, locked, send, formRef }: {
  inspection: OutputInspection; handoff: OutputHandoff; previous: string | null; initialAnswer: string;
  locked: boolean; send: (request: OutputRequest) => void; formRef?: Ref<HTMLFormElement>;
}) {
  const [draft, setDraft, status] = useCourseDraft(['output-interpretation', inspection.enrollment_id, inspection.manifest_sha256,
    inspection.uuid, inspection.review_sha256, handoff.uuid, handoff.handoff_sha256, inspection.case.case_sha256, previous],
  { answer: initialAnswer }, draftStrings(['answer'], 8000))
  return <form ref={formRef} tabIndex={-1} aria-label="Explain delivery outcome" className="min-w-0 space-y-3 rounded-lg border border-gray-300 px-1.5 py-3 sm:p-3" onSubmit={event => {
    event.preventDefault(); send({ action: 'review', body: { request_id: newOutputId(), file_review_id: inspection.uuid, file_review_sha256: inspection.review_sha256,
      handoff_id: handoff.uuid, handoff_sha256: handoff.handoff_sha256, case_sha256: inspection.case.case_sha256, delivery_review: draft.answer,
      previous_submission_id: previous, consent: 'save_output_delivery_interpretation' } })
  }}>
    <h5 className="text-base font-semibold">Explain the evidence of delivery</h5><p className="text-sm">{previous ? 'This creates a linked revision and preserves your original answer.' : 'Your answer stays bound to this exact handoff and file approval.'}</p>
    <OutputHandoffEvidence handoff={handoff} />
    <label className="block text-sm">{inspection.case.questions.find(question => question.id === 'delivery_review')?.prompt}<textarea className={`${control} min-h-36`} rows={6} required minLength={10} maxLength={8000} disabled={locked} value={draft.answer} onChange={event => setDraft({ answer: event.target.value })} /></label>
    <CourseDraftNotice status={status} /><button className={button} disabled={locked}>Save delivery interpretation</button>
  </form>
}
