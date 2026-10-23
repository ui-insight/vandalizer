import type { ContextType, ReactNode } from 'react'
import { AuthContext } from '../../contexts/AuthContext'
import { OutputInspectionForm, OutputInterpretationForm } from './OutputWorkflowForms'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/outputWorkflow'
import { ApiError } from '../../api/client'
import type { OutputArtifacts, OutputCase, OutputCapture, OutputHandoff, OutputInspection, OutputList, OutputRequest, OutputReview, OutputRun, OutputSaved, OutputScope } from '../../types/outputWorkflow'
import { OutputWorkflow } from './OutputWorkflow'

vi.mock('../../api/outputWorkflow', () => ({ getOutputWork: vi.fn(), getOutputCapture: vi.fn(), getOutputRun: vi.fn(), getOutputInspection: vi.fn(), getOutputHandoff: vi.fn(), getOutputReview: vi.fn(), getOutputScope: vi.fn(), saveOutputWork: vi.fn(), getOutputFile: vi.fn() }))
vi.mock('./SavedAutomaticReviews', () => ({ SavedAutomaticReviews: () => <p>Saved output feedback</p> }))
vi.mock('./PracticalAssessment', () => ({ PracticalAssessment: ({ outputReviewSubmissionId }: { outputReviewSubmissionId: string }) => <p>Assess output review {outputReviewSubmissionId}</p> }))
const definition: OutputCase = { id: 'output-case', revision: 1, module_id: 'output_delivery', case_sha256: 'a'.repeat(64), source_sha256: 'b'.repeat(64),
  provenance: 'authored_output_handoff_case_not_generation_or_delivery', source_filename: 'progress-report.pdf', notice: 'Authored training destination; no external send.',
  task: 'Inspect actual files and recover a failed private handoff.', instructions: ['Open every file.'], exclusions: ['No external delivery.'], flawed_proposal: 'Assume generation proves delivery.',
  questions: [{ id: 'artifact_review', phase: 'after_generation_before_release', prompt: 'Compare the actual files and original source.' },
    { id: 'release_decision', phase: 'after_generation_before_release', prompt: 'Explain the exact release audience and scope.' },
    { id: 'delivery_review', phase: 'after_delivery_attempt', prompt: 'Explain what the actual delivery receipts establish.' }],
  artifacts: [{ id: 'report', file_type: 'pdf', purpose: 'Readable report', required_fields: ['Reporting Period'] }, { id: 'summary', file_type: 'csv', purpose: 'Tabular summary', required_fields: ['Reporting Period'] }],
  destination: { id: 'private_training_inbox', audience: 'enrolled_learner_only', data_scope: 'approved_generated_files_only', description: 'A private learner-only training copy.', first_attempt: 'controlled_rejection_before_destination_write', recovery: 'explicit_retry_same_approved_bytes_after_failed_receipt' } }
const identity = { enrollment_id: 'enrollment', module_id: 'output_delivery' as const, course_version: 'draft', manifest_sha256: 'c'.repeat(64) }
const workflowId = 'd'.repeat(24), key = `certification-output-request:enrollment:${definition.case_sha256}`
const props = { enrollmentId: identity.enrollment_id, definition }
let listing: OutputList, captures: Map<string, OutputCapture>, runs: Map<string, OutputRun>, inspections: Map<string, OutputInspection>, handoffs: Map<string, OutputHandoff>, reviews: Map<string, OutputReview>, scopes: Map<string, OutputScope>
function artifacts(): OutputArtifacts {
  return { artifacts_sha256: 'e'.repeat(64), files: ['pdf', 'csv'].map((kind, index) => ({ step_name: `file-${index}`, filename: `progress.${kind}`, file_type: kind, sha256: String(index + 1).repeat(64), size_bytes: 100,
    inspection: { parseable_and_fields_present: true, issues: [], text: 'Reporting Period: original Year 2; USD 135500 spent.', source_correctness_verified: false, visual_inspection_required: true } })),
    download: { filename: 'progress-deliverables.zip', file_type: 'zip', media_type: 'application/zip', sha256: '3'.repeat(64), size_bytes: 200 },
    all_required_files_parseable: true, learner_inspection_required: true, release_authorized: false, delivery_confirmed: false, credit_awarded: false }
}
function saved(request: OutputRequest): OutputSaved {
  if (request.action === 'capture') {
    const result: OutputCapture = { ...identity, uuid: request.body.request_id, case: definition, input_snapshot_sha256: '4'.repeat(64), artifact_id: workflowId, artifact_sha256: '5'.repeat(64), captured_at: '2026-10-07', execution_authorized: false, credit_awarded: false,
      documents: [{ document_id: '6'.repeat(32), source_sha256: definition.source_sha256, text: 'Original progress source.' }],
      artifact: { workflow: { id: workflowId, name: 'My output workflow', version: 1, input_config: {}, output_config: {}, resource_config: {}, config_override: null },
        steps: ['Report', 'PDF', 'Summary', 'CSV'].map((name, index) => ({ step: { id: String(index), name, data: {}, is_output: index % 2 === 1 }, tasks: [{ id: String(index), name: ['Prompt', 'DocumentRenderer', 'Formatter', 'DataExport'][index], data: {} }] })), referenced_extraction_sets: {} } }
    captures.set(result.uuid, result); listing.captures.unshift({ input_snapshot_id: result.uuid, captured_at: result.captured_at, workflow_name: 'My output workflow' }); return result
  }
  if (request.action === 'prepare') {
    const result: OutputRun = { ...identity, run_id: request.body.request_id, state: 'prepared', plan_sha256: '7'.repeat(64), case_sha256: definition.case_sha256,
      input_snapshot_id: request.body.input_snapshot_id, input_snapshot: captures.get(request.body.input_snapshot_id)!, model_names: ['Synthetic model'], prepared_at: '2026-10-07',
      stage_plans: ['Report', 'PDF', 'Summary', 'CSV'].map((name, index) => ({ step_id: String(index), task_id: String(index), step_name: name, output_key: name, task_type: (['Prompt', 'DocumentRenderer', 'Formatter', 'DataExport'] as const)[index], requested_model: index % 2 === 0 ? 'Synthetic model' : null, effective_input_sources: [index % 2 ? 'step_input' : 'workflow_documents'], receives_previous_stage: index % 2 === 1, is_deliverable: index % 2 === 1 })),
      scope_decision_id: null, scope_decision_sha256: null, scope_decision: null, authorization_sha256: null, result_sha256: null, stage_events_sha256: '8'.repeat(64), stage_events: [], result: null,
      release_decision: null, handoff_request_id: null, retry_request_id: null, handoff_receipt_id: null, handoff_claimed: false,
      can_save_scope: true, can_execute: false, can_finalize: false, can_inspect: false, credit_awarded: false, module_completion_eligible: false }
    runs.set(result.run_id, result); listing.runs.unshift({ run_id: result.run_id, state: result.state, input_snapshot_id: result.input_snapshot_id, prepared_at: result.prepared_at, workflow_name: 'My output workflow' }); return result
  }
  if (request.action === 'inspection') {
    const run = structuredClone(runs.get(request.body.run_id)!)
    run.release_decision = { uuid: request.body.request_id, review_sha256: '9'.repeat(64), submission: request.body }; runs.set(run.run_id, run)
    const result: OutputInspection = { ...identity, uuid: request.body.request_id, case: definition, review_sha256: '9'.repeat(64), submission: request.body, run, submitted_at: '2026-10-07', previous_release_decision_id: null, credit_awarded: false, module_completion_eligible: false }
    inspections.set(result.uuid, result); listing.inspections.unshift({ submission_id: result.uuid, submitted_at: result.submitted_at, run_id: run.run_id, status: null, choice: request.body.choice, previous_submission_id: null }); return result
  }
  if (request.action === 'handoff') {
    const delivered = request.body.action === 'retry_failed_handoff', run = structuredClone(runs.get(request.body.run_id)!)
    const result: OutputHandoff = { ...identity, uuid: request.body.request_id, run_id: run.run_id, handoff_sha256: (delivered ? 'b' : 'a').repeat(64), submission: request.body, submitted_at: '2026-10-07',
      status: delivered ? 'delivered' : 'failed', reason: delivered ? 'private_training_copy_saved' : 'controlled_training_rejection_before_write', destination_written: delivered,
      destination_copy: delivered ? artifacts() : null, previous_failed_receipt: delivered ? handoffs.get(request.body.previous_failed_id!)! : null,
      destination: { id: 'private_training_inbox', audience: 'enrolled_learner_only', data_scope: 'approved_generated_files_only', owner_user_id: 'learner' }, external_delivery: false, credit_awarded: false }
    run.handoff_claimed = delivered; run.can_inspect = !delivered; run.handoff_receipt_id = result.uuid
    if (delivered) run.retry_request_id = result.uuid; else run.handoff_request_id = result.uuid
    runs.set(run.run_id, run); handoffs.set(result.uuid, result); listing.handoffs.unshift({ submission_id: result.uuid, submitted_at: result.submitted_at, run_id: run.run_id, status: result.status, choice: null, previous_submission_id: null }); return result
  }
  if (request.action === 'review') {
    const result: OutputReview = { ...identity, uuid: request.body.request_id, case: definition, submission: request.body, submitted_at: '2026-10-07',
      file_review: inspections.get(request.body.file_review_id)!, handoff: handoffs.get(request.body.handoff_id)!, credit_awarded: false, module_completion_eligible: false }
    reviews.set(result.uuid, result); listing.submissions.unshift({ submission_id: result.uuid, submitted_at: result.submitted_at, run_id: result.handoff.run_id, status: null, choice: null, previous_submission_id: request.body.previous_submission_id }); return result
  }
  const result = structuredClone(runs.get(request.body.run_id)!)
  if (request.action === 'scope') {
    const scope: OutputScope = { ...identity, uuid: request.body.request_id, run_id: result.run_id, plan_sha256: result.plan_sha256, case_sha256: definition.case_sha256, submitted_at: '2026-10-07', submission: request.body }
    scopes.set(scope.uuid, scope); result.scope_decision = scope; result.scope_decision_id = scope.uuid; result.scope_decision_sha256 = 'b'.repeat(64); result.can_execute = request.body.choice === 'approve'
  } else {
    result.state = 'completed'; result.can_execute = result.can_save_scope = result.can_finalize = false; result.can_inspect = true; result.authorization_sha256 = 'c'.repeat(64); result.result_sha256 = 'd'.repeat(64)
    result.stage_events = result.stage_plans.flatMap((stage, index) => ['stage_started', 'stage_completed'].map(kind => ({ receipt_sha256: 'e'.repeat(64), receipt: { kind: kind as 'stage_started' | 'stage_completed', stage_index: index, output_key: stage.output_key, status: 'completed', consumed_context: 'Original source or previous result', result: { output: 'Actual saved result' } } })))
    result.result = { status: 'completed', generated_artifacts: artifacts(), credit_awarded: false }
  }
  runs.set(result.run_id, result); return result
}
beforeEach(() => {
  vi.restoreAllMocks(); vi.resetAllMocks(); sessionStorage.clear()
  captures = new Map(); runs = new Map(); inspections = new Map(); handoffs = new Map(); reviews = new Map(); scopes = new Map()
  listing = { ...identity, case: definition, can_submit: true, read_only_reason: null, workflows: [{ workflow_id: workflowId, name: 'My output workflow', version: 1 }], older_workflows_available: false,
    assigned_sources: [], captures: [], runs: [], inspections: [], handoffs: [], submissions: [], older_captures_available: false, older_runs_available: false, older_inspections_available: false, older_handoffs_available: false, older_submissions_available: false }
  vi.mocked(api.getOutputWork).mockImplementation(async () => structuredClone(listing))
  function read<T>(values: Map<string, T>) { return async (_enrollment: string, key: string) => {
    const value = values.get(key)
    if (!value) throw new ApiError(404, 'Not found')
    return structuredClone(value)
  } }
  vi.mocked(api.getOutputCapture).mockImplementation(read(captures))
  vi.mocked(api.getOutputRun).mockImplementation(read(runs))
  vi.mocked(api.getOutputInspection).mockImplementation(read(inspections))
  vi.mocked(api.getOutputHandoff).mockImplementation(read(handoffs))
  vi.mocked(api.getOutputReview).mockImplementation(read(reviews))
  vi.mocked(api.getOutputScope).mockImplementation(read(scopes))
  vi.mocked(api.saveOutputWork).mockImplementation(async (_e, request) => structuredClone(saved(request)))
})
async function completeRun(wait = true) {
  fireEvent.change(await screen.findByLabelText('Owned output workflow'), { target: { value: workflowId } })
  fireEvent.click(screen.getByRole('button', { name: 'Save output workflow and source' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Prepare this saved output workflow' }))
  await screen.findByRole('form', { name: 'Approve output generation' })
  fireEvent.change(screen.getByLabelText('Generation choice'), { target: { value: 'approve' } })
  fireEvent.change(screen.getByLabelText('Explain this generation decision'), { target: { value: 'Approve only these exact internal file generation settings.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save generation scope decision' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Generate these approved files' }))
  if (wait) await screen.findByRole('heading', { name: 'Files generated · handoff is separate' })
}
async function inspect(choice = 'approve') {
  fireEvent.click(await screen.findByRole('button', { name: 'Inspect these files and choose release scope' }))
  for (const kind of ['pdf', 'csv']) {
    fireEvent.click(screen.getByLabelText(`I opened progress.${kind} and inspected its actual contents.`))
    fireEvent.change(screen.getByLabelText(`Usability of progress.${kind}`), { target: { value: 'usable' } })
    fireEvent.change(screen.getByLabelText(`What you checked in progress.${kind}`), { target: { value: 'Checked the period, amounts and source references.' } })
  }
  fireEvent.click(screen.getByLabelText('I opened the actual ZIP bundle and checked every member.'))
  for (const question of definition.questions.slice(0, 2)) fireEvent.change(screen.getByLabelText(question.prompt), { target: { value: 'Checked the exact files, original source, private destination and learner-only scope.' } })
  fireEvent.change(screen.getByLabelText('Release choice'), { target: { value: choice } })
  fireEvent.click(screen.getByRole('button', { name: 'Save inspection and release choice' }))
  await screen.findByRole('heading', { name: `Saved file inspection · ${choice}` })
}
async function deliver(wait = true) {
  fireEvent.click(screen.getByRole('button', { name: 'Attempt the approved private handoff' }))
  await screen.findByRole('heading', { name: 'Controlled training handoff failed' })
  fireEvent.click(screen.getByRole('button', { name: 'Read current approval before retry' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Retry only this failed private handoff' }))
  if (wait) await screen.findByRole('heading', { name: 'Private training copy confirmed' })
}
it('requires separate generation, file inspection, release approval, targeted handoff retry and outcome review', async () => {
  render(<OutputWorkflow {...props} />); await completeRun(); await inspect(); await deliver()
  fireEvent.click(screen.getByRole('button', { name: 'Explain this actual delivery outcome' }))
  fireEvent.change(await screen.findByLabelText(definition.questions[2].prompt), { target: { value: 'The actual failed handoff was retried once; generation was preserved, and only my private copy is confirmed.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save delivery interpretation' }))
  await screen.findByText(/Assess output review/)
  expect(screen.getByRole('region', { name: 'Opened output evidence' })).toHaveFocus()
  expect(vi.mocked(api.saveOutputWork).mock.calls.map(call => call[1].action)).toEqual(['capture', 'prepare', 'scope', 'execute', 'inspection', 'handoff', 'handoff', 'review'])
})
it('holds files without making a handoff available', async () => {
  render(<OutputWorkflow {...props} />); await completeRun(); await inspect('hold')
  expect(screen.queryByRole('button', { name: 'Attempt the approved private handoff' })).not.toBeInTheDocument()
  expect(handoffs.size).toBe(0)
})
it('recovers a lost generation reply by GET without another generation call', async () => {
  vi.mocked(api.saveOutputWork).mockImplementation(async (_e, request) => { const result = saved(request); if (request.action === 'execute') throw new ApiError(502, 'Lost reply'); return structuredClone(result) })
  render(<OutputWorkflow {...props} />); await completeRun(false)
  await screen.findByText(/We could not confirm the saved state/)
  const check = screen.getByRole('button', { name: 'Check pending output request' }); await waitFor(() => expect(check).toBeEnabled()); fireEvent.click(check)
  await screen.findByRole('heading', { name: 'Files generated · handoff is separate' })
  expect(vi.mocked(api.saveOutputWork).mock.calls.filter(call => call[1].action === 'execute')).toHaveLength(1)
})
it('recovers a lost successful handoff reply without another copy or generation', async () => {
  vi.mocked(api.saveOutputWork).mockImplementation(async (_e, request) => { const result = saved(request); if (request.action === 'handoff' && request.body.action === 'retry_failed_handoff') throw new ApiError(502, 'Lost reply'); return structuredClone(result) })
  render(<OutputWorkflow {...props} />); await completeRun(); await inspect(); await deliver(false)
  await screen.findByText(/We could not confirm the saved state/)
  const check = screen.getByRole('button', { name: 'Check pending output request' }); await waitFor(() => expect(check).toBeEnabled()); fireEvent.click(check)
  await screen.findByRole('heading', { name: 'Private training copy confirmed' })
  expect(vi.mocked(api.saveOutputWork).mock.calls.filter(call => call[1].action === 'handoff')).toHaveLength(2)
  expect(sessionStorage.getItem(key)).toBeNull()
})
it('keeps a claimed handoff identity when the receipt is missing, and only finishes the original request', async () => {
  render(<OutputWorkflow {...props} />); await completeRun(); await inspect()
  vi.mocked(api.saveOutputWork).mockImplementationOnce(async (_e, request) => {
    if (request.action !== 'handoff') throw new Error('Expected handoff')
    const run = runs.get(request.body.run_id)!; run.handoff_request_id = request.body.request_id; run.handoff_claimed = true
    throw new ApiError(502, 'Claim saved; receipt interrupted')
  })
  fireEvent.click(screen.getByRole('button', { name: 'Attempt the approved private handoff' }))
  await screen.findByText(/We could not confirm the saved state/)
  const original = JSON.parse(sessionStorage.getItem(key)!)
  const check = screen.getByRole('button', { name: 'Check pending output request' }); await waitFor(() => expect(check).toBeEnabled()); fireEvent.click(check)
  await screen.findByText(/original handoff is claimed/)
  expect(screen.queryByRole('button', { name: 'Discard unclaimed output request' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Finish original output request' }))
  await screen.findByRole('heading', { name: 'Controlled training handoff failed' })
  expect(vi.mocked(api.saveOutputWork).mock.calls.at(-1)![1]).toEqual(original)
})
it('opens history read-only even when a pending request exists in this tab', async () => {
  sessionStorage.setItem(key, '{broken')
  render(<OutputWorkflow {...props} historyOnly />)
  await screen.findByLabelText('Open saved output work')
  expect(screen.queryByRole('form', { name: 'Capture output workflow' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Check pending output request' })).not.toBeInTheDocument()
  expect(api.saveOutputWork).not.toHaveBeenCalled()
})
it('blocks new actions for malformed pending storage but allows saved history reads', async () => {
  sessionStorage.setItem(key, '{broken')
  render(<OutputWorkflow {...props} />)
  await screen.findByText(/could not restore its pending request/)
  expect(screen.getByLabelText('Open saved output work')).toBeEnabled()
  expect(screen.queryByRole('form', { name: 'Capture output workflow' })).not.toBeInTheDocument()
})
it('does not send any request when session storage cannot preserve it', async () => {
  render(<OutputWorkflow {...props} />)
  fireEvent.change(await screen.findByLabelText('Owned output workflow'), { target: { value: workflowId } })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage unavailable') })
  fireEvent.click(screen.getByRole('button', { name: 'Save output workflow and source' }))
  await screen.findByText(/no request was sent/)
  expect(api.saveOutputWork).not.toHaveBeenCalled()
})
it('rejects a response from another enrollment instead of adopting it', async () => {
  vi.mocked(api.saveOutputWork).mockImplementation(async (_e, request) => ({ ...saved(request), enrollment_id: 'foreign' }))
  render(<OutputWorkflow {...props} />)
  fireEvent.change(await screen.findByLabelText('Owned output workflow'), { target: { value: workflowId } })
  fireEvent.click(screen.getByRole('button', { name: 'Save output workflow and source' }))
  await screen.findByText(/We could not confirm the saved state/)
  expect(screen.queryByRole('button', { name: 'Prepare this saved output workflow' })).not.toBeInTheDocument()
})

function draftAuth(child: ReactNode, user = 'draft-learner') {
  return <AuthContext.Provider value={{ user: { user_id: user } } as NonNullable<ContextType<typeof AuthContext>>}>{child}</AuthContext.Provider>
}
it.each(['user', 'manifest', 'bundle', 'file'])('isolates output inspection when %s changes and restores the original draft', async binding => {
  const parent = render(<OutputWorkflow {...props} />)
  await completeRun()
  const original = structuredClone([...runs.values()][0])
  parent.unmount()
  const send = vi.fn()
  const node = (run = original, user = 'draft-learner') => draftAuth(<OutputInspectionForm run={run} locked={false} send={send} />, user)
  const view = render(node())
  fireEvent.change(screen.getByLabelText('What you checked in progress.pdf'), { target: { value: 'My original exact file observation.' } })
  fireEvent.click(screen.getByLabelText('I opened the actual ZIP bundle and checked every member.'))
  const changed = structuredClone(original)
  if (binding === 'manifest') changed.manifest_sha256 = 'f'.repeat(64)
  if (binding === 'bundle') changed.result!.generated_artifacts!.download.sha256 = 'f'.repeat(64)
  if (binding === 'file') changed.result!.generated_artifacts!.files[0].sha256 = 'f'.repeat(64)
  view.rerender(node(changed, binding === 'user' ? 'second-learner' : 'draft-learner'))
  expect(screen.getByLabelText('What you checked in progress.pdf')).toHaveValue('')
  expect(screen.getByLabelText('I opened the actual ZIP bundle and checked every member.')).not.toBeChecked()
  expect(screen.getByLabelText('Release choice')).toHaveValue('hold')
  view.rerender(node())
  expect(screen.getByLabelText('What you checked in progress.pdf')).toHaveValue('My original exact file observation.')
  expect(screen.getByLabelText('I opened the actual ZIP bundle and checked every member.')).toBeChecked()
  expect(send).not.toHaveBeenCalled()
})

it('restores delivery drafts only for the exact handoff, approval and revision', async () => {
  const parent = render(<OutputWorkflow {...props} />)
  await completeRun(); await inspect(); await deliver()
  const inspection = structuredClone([...inspections.values()][0]), handoff = structuredClone([...handoffs.values()][1])
  parent.unmount()
  const send = vi.fn()
  const node = (previous: string | null = null, receipt = handoff, approval = inspection) => draftAuth(<OutputInterpretationForm inspection={approval} handoff={receipt} previous={previous} initialAnswer={previous ? 'Saved original explanation' : ''} locked={false} send={send} />)
  let view = render(node())
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Original delivery draft' } })
  view.rerender(node('previous-review'))
  expect(screen.getByRole('textbox')).toHaveValue('Saved original explanation')
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Revised delivery draft' } })
  view.rerender(node())
  expect(screen.getByRole('textbox')).toHaveValue('Original delivery draft')
  view.rerender(node(null, { ...handoff, handoff_sha256: 'f'.repeat(64) }))
  expect(screen.getByRole('textbox')).toHaveValue('')
  view.rerender(node(null, handoff, { ...inspection, review_sha256: 'f'.repeat(64) }))
  expect(screen.getByRole('textbox')).toHaveValue('')
  view.unmount(); view = render(node('previous-review'))
  expect(screen.getByRole('textbox')).toHaveValue('Revised delivery draft')
  expect(send).not.toHaveBeenCalled()
  fireEvent.submit(screen.getByRole('form', { name: 'Explain delivery outcome' }))
  expect(send).toHaveBeenCalledWith(expect.objectContaining({ action: 'review', body: expect.objectContaining({ delivery_review: 'Revised delivery draft', previous_submission_id: 'previous-review', handoff_sha256: handoff.handoff_sha256, file_review_sha256: inspection.review_sha256 }) }))
})
it('retains output inspection edits and explains unavailable storage', async () => {
  const parent = render(<OutputWorkflow {...props} />)
  await completeRun()
  const run = structuredClone([...runs.values()][0]); parent.unmount()
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage blocked') })
  const send = vi.fn()
  render(draftAuth(<OutputInspectionForm run={run} locked={false} send={send} />))
  fireEvent.change(screen.getByLabelText('What you checked in progress.pdf'), { target: { value: 'Retain this file observation' } })
  expect(screen.getByLabelText('What you checked in progress.pdf')).toHaveValue('Retain this file observation')
  expect(screen.getByRole('status')).toHaveTextContent('Keep this form open')
  expect(send).not.toHaveBeenCalled()
})
