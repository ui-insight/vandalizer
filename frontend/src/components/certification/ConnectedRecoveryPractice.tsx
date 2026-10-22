import { useCourseDraft } from '../../hooks/useCourseDraft'
import { CourseDraftNotice } from './CourseDraftNotice'
import { useId, useState } from 'react'
import type { ConnectedRecoveryBody, ConnectedRecoveryDecision, ConnectedRequest, ConnectedRun } from '../../types/connectedWorkflow'
import { ConnectedRunEvidence, EvidenceText, connectedButton as button, connectedControl as control } from './ConnectedWorkflowEvidence'

const stageChoices = [
  ['extract', 'Extraction'], ['reason', 'Reasoning'], ['format', 'Formatter'],
  ['unknown', 'No confirmed failure; the outcome is unknown'],
] as const
const preserveChoices = [
  ['keep_original_run_and_completed_outputs', 'Original run, successful output and failed-stage evidence'],
  ['replace_original_history', 'Replace the original history with the next run'],
  ['partial_is_complete', 'Keep only the successful extraction as the completed deliverable'],
] as const
const actionChoices = [
  ['resume_in_place', 'Resume Reasoning in place in this screen'],
  ['prepare_separate_bounded_run', 'Prepare and separately approve a new internal run'],
  ['restart_all_writes', 'Restart all stages, including any completed external writes'],
  ['publish_partial', 'Release the successful prefix as the finished result'],
] as const

function RecoveryChoices({ question, choices, value, disabled, onChange }: { question: string; choices: readonly (readonly [string, string])[]; value: string; disabled: boolean; onChange: (value: string) => void }) {
  const name = useId()
  return <fieldset disabled={disabled} className="min-w-0 space-y-2">
    <legend className="mb-2 font-semibold">{question}</legend>
    {choices.map(([choice, label]) => <label key={choice} className="flex min-h-11 cursor-pointer items-start gap-2 rounded-md border border-gray-300 p-2 focus-within:ring-2 focus-within:ring-purple-700 focus-within:ring-offset-2">
      <input type="radio" name={name} required value={choice} checked={value === choice} onChange={() => onChange(choice)} className="mt-0.5 h-6 w-6 shrink-0 accent-purple-700" />
      <span className="min-w-0 break-words">{label}</span>
    </label>)}
  </fieldset>
}

export function ConnectedRecoveryForm({ run, previous, disabled, send }: { run: ConnectedRun; previous?: ConnectedRecoveryDecision; disabled: boolean; send: (request: ConnectedRequest) => void }) {
  type Draft = { stage: string; preserve: string; action: string; explanation: string }
  const [draft, setDraft, status] = useCourseDraft<Draft>(['connected-recovery', run.enrollment_id, run.manifest_sha256, run.run_id,
    run.result_sha256, run.stage_events_sha256, run.case_sha256, previous?.uuid || null], {
    stage: previous?.submission.failed_stage || '', preserve: previous?.submission.preserve || '',
    action: previous?.submission.next_action || '', explanation: previous?.submission.explanation || '',
  }, (value): value is Draft => {
    if (!value || typeof value !== 'object') return false
    const saved = value as Draft
    return ['', ...stageChoices.map(([id]) => id)].includes(saved.stage)
      && ['', ...preserveChoices.map(([id]) => id)].includes(saved.preserve)
      && ['', ...actionChoices.map(([id]) => id)].includes(saved.action)
      && typeof saved.explanation === 'string' && saved.explanation.length <= 8000
  })
  const { stage, preserve, action, explanation } = draft
  return <form aria-label="Inspect your stopped run and choose recovery" className="min-w-0 space-y-3 rounded-lg border border-gray-300 px-[6px] py-3 text-sm text-gray-900 sm:p-3" onSubmit={event => { event.preventDefault(); send({ action: 'recovery', body: {
    request_id: crypto.randomUUID().replaceAll('-', ''), run_id: run.run_id, result_sha256: run.result_sha256!, stage_events_sha256: run.stage_events_sha256,
    case_sha256: run.case_sha256, failed_stage: stage as ConnectedRecoveryBody['failed_stage'], preserve: preserve as ConnectedRecoveryBody['preserve'],
    next_action: action as ConnectedRecoveryBody['next_action'], explanation, previous_submission_id: previous?.uuid || null, consent: 'save_my_actual_stopped_run_recovery_choices' } }) }}>
    <h5 className="text-base font-semibold">Choose recovery from your actual saved evidence</h5><p>{run.input_snapshot.case.controlled_failure_practice?.question}</p>
    <p>Feedback checks your three choices against this run. Your explanation is preserved; these checks do not assess its quality or award module completion.</p>
    <RecoveryChoices question="First failed stage" choices={stageChoices} value={stage} disabled={disabled} onChange={value => setDraft(current => ({ ...current, stage: value }))} />
    <RecoveryChoices question="What work should remain intact?" choices={preserveChoices} value={preserve} disabled={disabled} onChange={value => setDraft(current => ({ ...current, preserve: value }))} />
    <RecoveryChoices question="Supported next action" choices={actionChoices} value={action} disabled={disabled} onChange={value => setDraft(current => ({ ...current, action: value }))} />
    <label className="block">Explain the evidence and recovery limits<textarea className={`${control} min-h-32`} required minLength={40} maxLength={8000} value={explanation} disabled={disabled} onChange={e => setDraft(current => ({ ...current, explanation: e.target.value }))} /></label>
    <CourseDraftNotice status={status} /><button className={button} disabled={disabled || !stage || !preserve || !action || explanation.trim().length < 40}>{previous ? 'Save revised recovery choices' : 'Save my recovery choices'}</button>
  </form>
}

export function ConnectedRecoveryEvidence({ saved, canWrite, disabled, send }: { saved: ConnectedRecoveryDecision; canWrite: boolean; disabled: boolean; send: (request: ConnectedRequest) => void }) {
  const [revising, setRevising] = useState(false)
  const snapshot = saved.stopped_run.input_snapshot
  return <section aria-label="Saved stopped-run recovery choices" className="min-w-0 space-y-3 text-sm text-gray-900">
    <h5 className="text-base font-semibold">{saved.checks.choices_supported ? 'Recovery choices match this saved run' : 'Reconsider the unsupported recovery choices'}</h5>
    <p>These are checks of your choices against actual stage evidence. They do not assess explanation quality, authorize another execution or award credit.</p>
    {saved.checks.checks.map(check => <div key={check.id} className="space-y-1 border-t border-gray-200 pt-2"><p className="font-semibold">{check.supported ? 'Supported' : 'Revise'} · {check.id.replaceAll('_', ' ')}</p><p>{check.feedback}</p></div>)}
    <EvidenceText label="Your saved recovery explanation" value={saved.submission.explanation} />
    <p className="break-all">Recovery choice reference: {saved.uuid}</p>{saved.submission.previous_submission_id && <p className="break-all">Earlier answer retained: {saved.submission.previous_submission_id}</p>}
    <details><summary className="min-h-11 cursor-pointer py-2 font-semibold">Inspect the original stopped run and successful extraction</summary><ConnectedRunEvidence run={saved.stopped_run} /></details>
    {canWrite && <>{revising ? <ConnectedRecoveryForm run={saved.stopped_run} previous={saved} disabled={disabled} send={send} /> : <button className={button} disabled={disabled} onClick={() => setRevising(true)}>Revise recovery choices and preserve original</button>}
      {saved.checks.choices_supported && <section className="space-y-2"><p>A new plan keeps the stopped run intact. It recomputes this bounded internal chain only after another scope inspection and approval; it does not resume the failed run.</p><button className={button} disabled={disabled} onClick={() => send({ action: 'prepare', body: { request_id: crypto.randomUUID().replaceAll('-', ''), input_snapshot_id: snapshot.uuid, input_snapshot_sha256: snapshot.input_snapshot_sha256, case_sha256: snapshot.case.case_sha256, consent: 'prepare_connected_workflow_plan' } })}>Prepare separate internal run for fresh approval</button></section>}
    </>}
  </section>
}
