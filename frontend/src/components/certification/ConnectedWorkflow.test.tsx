import type { ContextType } from 'react'
import { AuthContext } from '../../contexts/AuthContext'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/connectedWorkflow'
import { ApiError } from '../../api/client'
import type { ConnectedCapture, ConnectedCase, ConnectedList, ConnectedRequest, ConnectedReview, ConnectedRun, ConnectedSaved, ConnectedScope } from '../../types/connectedWorkflow'
import { ConnectedComparisonForm } from './ConnectedComparisonForm'
import { ConnectedWorkflow } from './ConnectedWorkflow'

vi.mock('../../api/connectedWorkflow', () => ({ getConnectedWork: vi.fn(), getConnectedCapture: vi.fn(), getConnectedRun: vi.fn(), getConnectedReview: vi.fn(), getConnectedScope: vi.fn(), saveConnectedWork: vi.fn() }))
vi.mock('./SavedAutomaticReviews', () => ({ SavedAutomaticReviews: () => <p>Saved feedback reader</p> }))
vi.mock('./PracticalAssessment', () => ({ PracticalAssessment: () => <p>Explicit assessment action</p> }))
const definition: ConnectedCase = { id: 'case', revision: 2, module_id: 'multi_step', case_sha256: 'a'.repeat(64),
  provenance: 'authored_connected_workflow_case_not_execution', source_filename: 'subaward-agreement.pdf', source_sha256: 'b'.repeat(64),
  notice: 'The authored example is not a learner execution.', task: 'Inspect the original chain and correct its saved connection.', intended_output: 'Internal draft with supported facts.',
  instructions: ['Run original and corrected revisions.'], exclusions: ['No external release.'],
  flawed_example: { notice: 'Authored example only.', routing: 'Wrong connection.', analysis: 'Source bounds matter.', final_summary: 'An unsupported summary.' },
  questions: [{ id: 'scope_approval', phase: 'before_execution', prompt: 'Approve only the exact revision and source.' },
    { id: 'connection_repair', phase: 'after_execution', prompt: 'Compare both actual results.' }, { id: 'source_review', phase: 'after_execution', prompt: 'Separate supported facts from interpretation.' }] }
const identity = { enrollment_id: 'enrollment', module_id: 'multi_step' as const, course_version: 'draft', manifest_sha256: 'c'.repeat(64) }
const workflowId = 'd'.repeat(24)
let listing: ConnectedList, captures: Map<string, ConnectedCapture>, runs: Map<string, ConnectedRun>, reviews: Map<string, ConnectedReview>, scopes: Map<string, ConnectedScope>
const key = `certification-connected-request:enrollment:${definition.case_sha256}`
function saved(request: ConnectedRequest): ConnectedSaved {
  const body = request.body
  if (request.action === 'capture') {
    const result: ConnectedCapture = { ...identity, uuid: request.body.request_id, case: definition, input_snapshot_sha256: 'e'.repeat(64), artifact_id: workflowId, artifact_sha256: 'f'.repeat(64),
      captured_at: '2026-10-06', execution_authorized: false, credit_awarded: false,
      artifact: { workflow: { id: workflowId, name: 'My chain', version: 2, input_config: {}, output_config: {}, resource_config: {}, config_override: null },
        steps: ['Extraction', 'Prompt', 'Formatter'].map((name, index) => ({ step: { id: String(index), name: name + ' stage', is_output: index === 2, data: {} }, tasks: [{ id: String(index), name, data: { input_sources: [index ? 'step_input' : 'workflow_documents'] } }] })), referenced_extraction_sets: {} },
      documents: [{ document_id: '1'.repeat(32), assigned_filename: definition.source_filename, title: definition.source_filename, source_sha256: definition.source_sha256, text_sha256: '2'.repeat(64), text: 'Original assigned source text.' }] }
    captures.set(result.uuid, result); listing.captures.unshift({ input_snapshot_id: result.uuid, captured_at: result.captured_at, workflow_name: 'My chain' }); return result
  }
  if (request.action === 'prepare') {
    const result: ConnectedRun = { ...identity, run_id: request.body.request_id, state: 'prepared', plan_sha256: '3'.repeat(64), case_sha256: definition.case_sha256,
      input_snapshot_id: request.body.input_snapshot_id, input_snapshot: captures.get(request.body.input_snapshot_id)!, model_names: ['Synthetic model'], prepared_at: '2026-10-06',
      stage_plans: ['Extraction', 'Prompt', 'Formatter'].map((name, index) => ({ step_id: String(index), task_id: String(index), step_name: name + ' stage', task_type: name as 'Extraction' | 'Prompt' | 'Formatter', effective_input_sources: [index ? 'step_input' : 'workflow_documents'], receives_previous_stage: index > 0, model_names: ['Synthetic model'], output_key: name })),
      scope_decision_id: null, scope_decision_sha256: null, scope_decision: null, authorization_sha256: null, result_sha256: null, stage_events_sha256: '4'.repeat(64),
      stage_events: [], result: null, can_save_scope: true, can_execute: false, can_finalize: false, credit_awarded: false, module_completion_eligible: false }
    runs.set(result.run_id, result); listing.runs.unshift({ run_id: result.run_id, state: result.state, prepared_at: result.prepared_at, input_snapshot_id: result.input_snapshot_id, workflow_name: 'My chain' }); return result
  }
  if (request.action === 'review') {
    const result: ConnectedReview = { ...identity, uuid: request.body.request_id, case: definition, submission: request.body, submitted_at: '2026-10-06', original_run: runs.get(request.body.original_run_id)!, corrected_run: runs.get(request.body.corrected_run_id)!,
      comparison: { configuration_changed: true, original_formatter_rereads_source: true, corrected_formatter_receives_reasoning: true }, credit_awarded: false, module_completion_eligible: false }
    reviews.set(result.uuid, result); listing.submissions.unshift({ submission_id: result.uuid, submitted_at: result.submitted_at, previous_submission_id: request.body.previous_submission_id, original_run_id: result.original_run.run_id, corrected_run_id: result.corrected_run.run_id }); return result
  }
  const result = structuredClone(runs.get('run_id' in body ? body.run_id : '')!)
  if (request.action === 'scope') {
    const scope: ConnectedScope = { ...identity, uuid: request.body.request_id, run_id: request.body.run_id, plan_sha256: result.plan_sha256, case_sha256: definition.case_sha256, submitted_at: '2026-10-06', submission: request.body, credit_awarded: false }
    scopes.set(scope.uuid, scope); result.scope_decision = scope; result.scope_decision_id = scope.uuid; result.scope_decision_sha256 = '5'.repeat(64); result.can_execute = scope.submission.choice === 'approve'
  } else {
    result.state = 'completed'; result.can_execute = result.can_save_scope = result.can_finalize = false; result.authorization_sha256 = '6'.repeat(64); result.result_sha256 = '7'.repeat(64)
    result.result = { status: 'completed', final_output: 'Actual saved final result.', credit_awarded: false }
    result.stage_events = result.stage_plans.flatMap((stage, index) => [{ receipt_sha256: '8'.repeat(64), receipt: { kind: 'stage_started' as const, stage_index: index, output_key: stage.output_key, consumed_context: { kind: 'combined_context', value: 'Actual stage input.\nSecond source line.' } } }, { receipt_sha256: '9'.repeat(64), receipt: { kind: 'stage_completed' as const, stage_index: index, output_key: stage.output_key, status: 'completed' as const, result: { output: 'Actual stage result.' } } }])
  }
  runs.set(result.run_id, result); return result
}
function seedRun() {
  const capture = saved({ action: 'capture', body: { request_id: crypto.randomUUID().replaceAll('-', ''), workflow_id: workflowId, case_sha256: definition.case_sha256, consent: 'capture_connected_workflow_inputs' } }) as ConnectedCapture
  return saved({ action: 'prepare', body: { request_id: crypto.randomUUID().replaceAll('-', ''), input_snapshot_id: capture.uuid, input_snapshot_sha256: capture.input_snapshot_sha256, case_sha256: definition.case_sha256, consent: 'prepare_connected_workflow_plan' } }) as ConnectedRun
}
function approve(run: ConnectedRun) {
  return saved({ action: 'scope', body: { request_id: 'a'.repeat(32), run_id: run.run_id, plan_sha256: run.plan_sha256, case_sha256: definition.case_sha256, choice: 'approve', reason: 'Only the saved revision and assigned source.', consent: 'save_connected_workflow_scope_decision' } }) as ConnectedRun
}
function execution(run: ConnectedRun): ConnectedRequest {
  return { action: 'execute', body: { run_id: run.run_id, plan_sha256: run.plan_sha256, scope_decision_id: run.scope_decision_id!, scope_decision_sha256: run.scope_decision_sha256!, consent: 'execute_approved_connected_workflow' } }
}
beforeEach(() => {
  vi.restoreAllMocks(); vi.resetAllMocks(); sessionStorage.clear()
  captures = new Map(); runs = new Map(); reviews = new Map(); scopes = new Map()
  listing = { ...identity, case: definition, can_submit: true, read_only_reason: null, workflows: [{ workflow_id: workflowId, name: 'My chain', version: 2 }], older_workflows_available: false,
    captures: [], older_captures_available: false, runs: [], older_runs_available: false, submissions: [], older_submissions_available: false }
  vi.mocked(api.getConnectedWork).mockImplementation(async () => structuredClone(listing))
  vi.mocked(api.getConnectedCapture).mockImplementation(async (_e, id) => structuredClone(captures.get(id)!))
  vi.mocked(api.getConnectedRun).mockImplementation(async (_e, id) => structuredClone(runs.get(id)!))
  vi.mocked(api.getConnectedReview).mockImplementation(async (_e, id) => structuredClone(reviews.get(id)!))
  vi.mocked(api.getConnectedScope).mockImplementation(async (_e, id) => structuredClone(scopes.get(id)!))
  vi.mocked(api.saveConnectedWork).mockImplementation(async (_e, request) => structuredClone(saved(request)))
})
const props = { enrollmentId: 'enrollment', definition }
async function captureAndPrepare() {
  fireEvent.change(await screen.findByLabelText('Saved workflow'), { target: { value: workflowId } })
  fireEvent.click(screen.getByRole('button', { name: 'Capture selected workflow and source' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Prepare this captured revision' }))
  await screen.findByRole('form', { name: 'Approve or hold connected run' })
}
async function completeRun() {
  await captureAndPrepare()
  fireEvent.change(screen.getByLabelText('Scope choice'), { target: { value: 'approve' } })
  fireEvent.change(screen.getByLabelText('Explain your scope choice'), { target: { value: 'Only the saved revision on the assigned source.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save scope choice' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Run this approved revision' }))
  await screen.findByRole('heading', { name: 'Run completed' })
}
it('requires separate explicit capture, preparation, approval, execution and comparison actions', async () => {
  render(<ConnectedWorkflow {...props} />)
  await screen.findByLabelText('Saved workflow'); expect(api.saveConnectedWork).not.toHaveBeenCalled()
  await completeRun()
  fireEvent.click(screen.getByRole('button', { name: 'Use as original run' }))
  await completeRun()
  fireEvent.click(screen.getByRole('button', { name: 'Use as corrected run' }))
  fireEvent.change(screen.getByLabelText(/Compare the connection repair/), { target: { value: 'I inspected and compared both actual runs.' } })
  fireEvent.change(screen.getByLabelText(/Check facts and interpretation/), { target: { value: 'The source supports the facts but not institutional compliance.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save comparison and source review' }))
  await screen.findByRole('heading', { name: 'Comparison saved' })
  expect(vi.mocked(api.saveConnectedWork).mock.calls.map(call => call[1].action)).toEqual(['capture', 'prepare', 'scope', 'execute', 'capture', 'prepare', 'scope', 'execute', 'review'])
  expect(screen.getByText('Explicit assessment action')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Revise comparison answers' }))
  expect(screen.getByRole('form', { name: 'Compare actual connected runs' })).toHaveFocus()
  fireEvent.change(screen.getByLabelText(/Check facts and interpretation/), { target: { value: 'Revised check of the same preserved source and runs.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save comparison and source review' }))
  await screen.findByRole('heading', { name: 'Comparison saved' })
  const last = vi.mocked(api.saveConnectedWork).mock.calls.at(-1)![1]
  expect(last.action === 'review' && last.body.previous_submission_id).toEqual([...reviews.keys()][0])
})
it.each(['capture', 'execute'] as const)('recovers a lost %s reply across remount with a GET only', async action => {
  const first = render(<ConnectedWorkflow {...props} />)
  if (action === 'execute') {
    await captureAndPrepare()
    fireEvent.change(screen.getByLabelText('Scope choice'), { target: { value: 'approve' } })
    fireEvent.change(screen.getByLabelText('Explain your scope choice'), { target: { value: 'Only this exact revision and assigned source.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save scope choice' }))
    await screen.findByRole('button', { name: 'Run this approved revision' })
  } else fireEvent.change(await screen.findByLabelText('Saved workflow'), { target: { value: workflowId } })
  vi.mocked(api.saveConnectedWork).mockImplementationOnce(async (_e, request) => { saved(request); throw new Error('Lost reply') })
  fireEvent.click(screen.getByRole('button', { name: action === 'execute' ? 'Run this approved revision' : 'Capture selected workflow and source' }))
  await screen.findByRole('alert'); const count = vi.mocked(api.saveConnectedWork).mock.calls.length
  first.unmount(); render(<ConnectedWorkflow {...props} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Check pending request' }))
  await waitFor(() => expect(screen.queryByRole('region', { name: 'Pending connected request' })).not.toBeInTheDocument())
  expect(api.saveConnectedWork).toHaveBeenCalledTimes(count)
  expect(sessionStorage.getItem(key)).toBeNull()
})
it('keeps an unstarted execution pending until explicit finish after a read', async () => {
  const run = approve(seedRun()), request = execution(run)
  sessionStorage.setItem(key, JSON.stringify(request))
  render(<ConnectedWorkflow {...props} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Check pending request' }))
  await screen.findByRole('button', { name: 'Finish original request' })
  expect(api.saveConnectedWork).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Finish original request' }))
  await screen.findByRole('heading', { name: 'Run completed' })
  expect(api.saveConnectedWork).toHaveBeenCalledWith('enrollment', request)
})
it('clears an unstarted stale execution request after a newer hold without dispatch', async () => {
  const run = approve(seedRun()), request = execution(run)
  saved({ action: 'scope', body: { ...run.scope_decision!.submission, request_id: 'b'.repeat(32), choice: 'hold' } })
  sessionStorage.setItem(key, JSON.stringify(request))
  render(<ConnectedWorkflow {...props} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Check pending request' }))
  await screen.findByText(/scope choice changed/)
  expect(sessionStorage.getItem(key)).toBeNull(); expect(api.saveConnectedWork).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Run this approved revision' })).not.toBeInTheDocument()
})
it('reads original course history despite a pending request in the active tab', async () => {
  const run = approve(seedRun())
  sessionStorage.setItem(key, JSON.stringify(execution(run)))
  render(<ConnectedWorkflow {...props} historyOnly />)
  fireEvent.change(await screen.findByLabelText('Open saved connected work'), { target: { value: 'run:' + run.run_id } })
  await screen.findByRole('heading', { name: 'Prepared · not run' })
  expect(screen.queryByRole('button', { name: 'Run this approved revision' })).not.toBeInTheDocument()
  expect(screen.queryByRole('form', { name: 'Capture connected revision' })).not.toBeInTheDocument()
  expect(api.saveConnectedWork).not.toHaveBeenCalled()
})
it('offers explicit finalization of all saved results without executing again', async () => {
  const approved = approve(seedRun())
  const run = saved(execution(approved)) as ConnectedRun
  run.state = 'executing'; run.result = null; run.result_sha256 = null; run.can_finalize = true
  runs.set(run.run_id, run)
  render(<ConnectedWorkflow {...props} />)
  fireEvent.change(await screen.findByLabelText('Open saved connected work'), { target: { value: 'run:' + run.run_id } })
  fireEvent.click(await screen.findByRole('button', { name: 'Finalize saved results' }))
  await screen.findByRole('heading', { name: 'Run completed' })
  expect(api.saveConnectedWork).toHaveBeenCalledOnce()
  expect(api.saveConnectedWork).toHaveBeenCalledWith('enrollment', { action: 'finalize', body: {
    run_id: run.run_id, plan_sha256: run.plan_sha256, authorization_sha256: run.authorization_sha256,
    stage_events_sha256: run.stage_events_sha256, consent: 'finalize_saved_connected_results_without_reexecution' } })
})
it('renders actual input and output text directly while keeping the full evidence available', async () => {
  const run = saved(execution(approve(seedRun()))) as ConnectedRun
  render(<ConnectedWorkflow {...props} />)
  fireEvent.change(await screen.findByLabelText('Open saved connected work'), { target: { value: 'run:' + run.run_id } })
  fireEvent.click(await screen.findByText('Inspect actual input for stage 3'))
  expect(screen.getByRole('region', { name: 'Actual input for stage 3' }).textContent).toBe('Actual stage input.\nSecond source line.')
  fireEvent.click(screen.getByText('Inspect actual result for stage 3'))
  expect(screen.getByRole('region', { name: 'Actual result for stage 3' }).textContent).toBe('Actual stage result.')
  expect(screen.getAllByText('Result evidence and source details')).toHaveLength(3)
  expect(api.saveConnectedWork).not.toHaveBeenCalled()
})
it.each(['failed', 'uncertain', 'executing'] as const)('preserves the completed prefix of a %s run without offering completion or replay', async state => {
  const run = saved(execution(approve(seedRun()))) as ConnectedRun
  run.state = state
  run.stage_events = run.stage_events.slice(0, 3)
  run.result = state === 'executing' ? null : { status: state, credit_awarded: false }
  run.result_sha256 = state === 'executing' ? null : run.result_sha256
  runs.set(run.run_id, run)
  render(<ConnectedWorkflow {...props} />)
  fireEvent.change(await screen.findByLabelText('Open saved connected work'), { target: { value: 'run:' + run.run_id } })
  fireEvent.click(await screen.findByText('Inspect actual result for stage 1'))
  expect(screen.getByRole('region', { name: 'Actual result for stage 1' })).toHaveTextContent('Actual stage result.')
  expect(screen.getByText('Started · no saved result')).toBeInTheDocument()
  expect(screen.getByText('Not started')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Run this approved revision' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Finalize saved results' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Use as corrected run' })).not.toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Saved final output' })).not.toBeInTheDocument()
  expect(api.saveConnectedWork).not.toHaveBeenCalled()
})
it('keeps server history readable when tab request recovery is malformed', async () => {
  const run = seedRun()
  sessionStorage.setItem(key, JSON.stringify({ action: 'execute', body: { consent: 'execute_approved_connected_workflow' } }))
  render(<ConnectedWorkflow {...props} />)
  await screen.findByText(/could not restore its pending request/)
  fireEvent.change(screen.getByLabelText('Open saved connected work'), { target: { value: 'run:' + run.run_id } })
  await screen.findByRole('heading', { name: 'Prepared · not run' })
  expect(screen.queryByRole('form', { name: 'Capture connected revision' })).not.toBeInTheDocument()
  expect(api.saveConnectedWork).not.toHaveBeenCalled()
})
it('shows saved evidence with all mutation controls hidden when delivery is disabled', async () => {
  const run = approve(seedRun())
  listing.can_submit = false; listing.read_only_reason = 'This course is preserved history.'
  render(<ConnectedWorkflow {...props} />)
  fireEvent.change(await screen.findByLabelText('Open saved connected work'), { target: { value: 'run:' + run.run_id } })
  await screen.findByRole('heading', { name: 'Prepared · not run' })
  expect(screen.queryByRole('form', { name: 'Approve or hold connected run' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Run this approved revision' })).not.toBeInTheDocument()
  expect(api.saveConnectedWork).not.toHaveBeenCalled()
})
it('requires durable request storage before sending a capture', async () => {
  render(<ConnectedWorkflow {...props} />)
  fireEvent.change(await screen.findByLabelText('Saved workflow'), { target: { value: workflowId } })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Unavailable') })
  fireEvent.click(screen.getByRole('button', { name: 'Capture selected workflow and source' }))
  await screen.findByText(/no request was sent/)
  expect(api.saveConnectedWork).not.toHaveBeenCalled()
})
it('allows clearing a confirmed unsaved preparation without losing earlier evidence', async () => {
  const run = seedRun()
  sessionStorage.setItem(key, JSON.stringify({ action: 'prepare', body: { request_id: 'f'.repeat(32), input_snapshot_id: run.input_snapshot_id, input_snapshot_sha256: run.input_snapshot.input_snapshot_sha256, case_sha256: definition.case_sha256, consent: 'prepare_connected_workflow_plan' } }))
  vi.mocked(api.getConnectedRun).mockRejectedValue(new ApiError(404, 'Missing'))
  render(<ConnectedWorkflow {...props} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Check pending request' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Clear confirmed unsaved request' }))
  expect(sessionStorage.getItem(key)).toBeNull(); expect(api.saveConnectedWork).not.toHaveBeenCalled()
  expect(captures.size).toBe(1)
})
it.each(['course', 'capture', 'credit', 'source'] as const)('rejects a capture response with a changed %s binding', async problem => {
  vi.mocked(api.saveConnectedWork).mockImplementationOnce(async (_e, request) => {
    const value = structuredClone(saved(request)) as ConnectedCapture
    if (problem === 'course') value.enrollment_id = 'foreign'
    else if (problem === 'capture') value.uuid = '0'.repeat(32)
    else if (problem === 'credit') Object.assign(value, { credit_awarded: true })
    else value.documents[0].source_sha256 = '0'.repeat(64)
    return value
  })
  render(<ConnectedWorkflow {...props} />)
  fireEvent.change(await screen.findByLabelText('Saved workflow'), { target: { value: workflowId } })
  fireEvent.click(screen.getByRole('button', { name: 'Capture selected workflow and source' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: 'Prepare this captured revision' })).not.toBeInTheDocument()
  expect(sessionStorage.getItem(key)).not.toBeNull()
})


it('restores an unsubmitted connected approval for the exact run without executing or saving it', async () => {
  const run = seedRun()
  const auth = { user: { user_id: 'connected-draft-learner' } } as NonNullable<ContextType<typeof AuthContext>>
  const node = <AuthContext.Provider value={auth}><ConnectedWorkflow {...props} /></AuthContext.Provider>
  let view = render(node)
  fireEvent.change(await screen.findByLabelText('Open saved connected work'), { target: { value: `run:${run.run_id}` } })
  await screen.findByRole('form', { name: 'Approve or hold connected run' })
  fireEvent.change(screen.getByLabelText('Scope choice'), { target: { value: 'approve' } })
  fireEvent.change(screen.getByLabelText('Explain your scope choice'), { target: { value: 'My original scope decision for this one preserved plan.' } })
  view.unmount()
  view = render(node)
  fireEvent.change(await screen.findByLabelText('Open saved connected work'), { target: { value: `run:${run.run_id}` } })
  await screen.findByRole('form', { name: 'Approve or hold connected run' })
  expect(screen.getByLabelText('Scope choice')).toHaveValue('approve')
  expect(screen.getByLabelText('Explain your scope choice')).toHaveValue('My original scope decision for this one preserved plan.')
  expect(screen.queryByRole('button', { name: 'Run this approved revision' })).not.toBeInTheDocument()
  expect(api.saveConnectedWork).not.toHaveBeenCalled()
  view.unmount()
  runs.set(run.run_id, { ...run, plan_sha256: 'e'.repeat(64) })
  render(node)
  fireEvent.change(await screen.findByLabelText('Open saved connected work'), { target: { value: `run:${run.run_id}` } })
  await screen.findByRole('form', { name: 'Approve or hold connected run' })
  expect(screen.getByLabelText('Scope choice')).toHaveValue('')
  expect(screen.getByLabelText('Explain your scope choice')).toHaveValue('')
  expect(api.saveConnectedWork).not.toHaveBeenCalled()
})

it.each(['original', 'corrected', 'result', 'revision', 'manifest', 'user'])('keeps comparison drafts isolated by %s and restores the original pair', binding => {
  const original = saved(execution(approve(seedRun()))) as ConnectedRun
  const corrected = saved(execution(approve(seedRun()))) as ConnectedRun
  const send = vi.fn()
  const node = (first = original, second = corrected, previous: string | null = null, course = listing, user = 'comparison-learner') =>
    <AuthContext.Provider value={{ user: { user_id: user } } as NonNullable<ContextType<typeof AuthContext>>}><ConnectedComparisonForm listing={course} original={first} corrected={second} previous={previous} initialAnswers={{ connection_repair: '', source_review: '' }} locked={false} send={send} /></AuthContext.Provider>
  let view = render(node())
  fireEvent.change(screen.getByLabelText(/Compare the connection repair/), { target: { value: 'My original comparison of these two exact results.' } })
  const first = structuredClone(original), second = structuredClone(corrected), course = structuredClone(listing)
  if (binding === 'original') first.run_id = 'f'.repeat(32)
  if (binding === 'corrected') second.run_id = 'f'.repeat(32)
  if (binding === 'result') second.result_sha256 = 'f'.repeat(64)
  if (binding === 'manifest') course.manifest_sha256 = 'f'.repeat(64)
  view.rerender(node(first, second, binding === 'revision' ? 'e'.repeat(32) : null, course, binding === 'user' ? 'other-learner' : 'comparison-learner'))
  expect(screen.getByLabelText(/Compare the connection repair/)).toHaveValue('')
  view.unmount(); view = render(node())
  expect(screen.getByLabelText(/Compare the connection repair/)).toHaveValue('My original comparison of these two exact results.')
  expect(send).not.toHaveBeenCalled()
})
