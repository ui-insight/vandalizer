import type { ContextType } from 'react'
import { AuthContext } from '../../contexts/AuthContext'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/budgetWorkflow'
import { ApiError } from '../../api/client'
import type { BudgetCase, BudgetList, BudgetCalculation, BudgetCapture, BudgetRun, BudgetReview, BudgetScope, BudgetRequest, BudgetSaved } from '../../types/budgetWorkflow'
import { BudgetCalculationForm } from './BudgetCalculations'
import { BudgetWorkflow } from './BudgetWorkflow'

vi.mock('../../api/budgetWorkflow', () => ({ getBudgetWork: vi.fn(), getBudgetCalculation: vi.fn(), getBudgetCapture: vi.fn(), getBudgetRun: vi.fn(), getBudgetReview: vi.fn(), getBudgetScope: vi.fn(), saveBudgetWork: vi.fn() }))
vi.mock('./SavedAutomaticReviews', () => ({ SavedAutomaticReviews: () => <p>Saved budget feedback</p> }))
vi.mock('./PracticalAssessment', () => ({ PracticalAssessment: ({ budgetReviewSubmissionId }: { budgetReviewSubmissionId: string }) => <p>Assess budget review {budgetReviewSubmissionId}</p> }))
const definition: BudgetCase = { id: 'budget-case', revision: 1, module_id: 'advanced_nodes', case_sha256: 'a'.repeat(64),
  provenance: 'authored_budget_method_case_not_execution', source_filename: 'budget-justification.pdf', source_sha256: 'b'.repeat(64),
  notice: 'An authored assignment is not learner execution.', task: 'Check source arithmetic and actual workflow dependencies.', intended_output: 'Internal exception memo.',
  instructions: ['Preserve the actual source and calculations.'], exclusions: ['No external sends.'], flawed_proposal: 'Assume all sibling outputs arrive immediately.',
  questions: [{ id: 'method_choice', phase: 'before_execution', prompt: 'Explain your available interpretation and arithmetic methods.' },
    { id: 'calculation_review', phase: 'after_execution', prompt: 'Explain the stored calculations and their limits.' },
    { id: 'dependency_review', phase: 'after_execution', prompt: 'Explain actual branch dependencies.' }] }
const identity = { enrollment_id: 'enrollment', module_id: 'advanced_nodes' as const, course_version: 'draft', manifest_sha256: 'c'.repeat(64) }
const workflowId = 'd'.repeat(24), calculationId = '1'.repeat(32), documentId = '2'.repeat(32)
const calculationIds = ['equipment_subtotal', 'listed_direct_subtotal', 'listed_summary_total'] as const
const key = `certification-budget-request:enrollment:${definition.case_sha256}`
let listing: BudgetList, calculations: Map<string, BudgetCalculation>, captures: Map<string, BudgetCapture>, runs: Map<string, BudgetRun>, reviews: Map<string, BudgetReview>, scopes: Map<string, BudgetScope>

function calculation(requestId = calculationId): BudgetCalculation {
  return { ...identity, uuid: requestId, case: definition, calculation_snapshot_sha256: 'e'.repeat(64), captured_at: '2026-10-06', credit_awarded: false, module_completion_eligible: false,
    document: { document_id: documentId, assigned_filename: definition.source_filename, title: definition.source_filename, source_sha256: definition.source_sha256, text_sha256: 'f'.repeat(64), text: 'Original budget\nEquipment $45000' },
    request: { request_id: requestId, case_sha256: definition.case_sha256, document_id: documentId, previous_snapshot_id: null, consent: 'save_source_bound_budget_calculations',
      records: calculationIds.map(id => ({ id, operation: 'sum', method: 'explicit_learner_arithmetic', unit: 'USD', result: '45001.00', interpretation: 'Addition does not establish policy or common periods.',
        inputs: ['source_a', 'source_b'].map(name => ({ id: name, value: '22500.00', unit: 'USD', source_page: 1, source_quote: 'Equipment $45000', status: 'supported', explanation: 'I checked the source row and amount.' })) })) },
    checks: { all_arithmetic_supported: false, interpretation_review_required: true, notice: 'These additions do not establish institutional policy.',
      checks: calculationIds.map(id => ({ id, state: 'revision_required', recorded_value: '45001.00', computed_value: '45000.00', expression: '22500.00 + 22500.00', interpretation: 'Preserve unresolved period claims.', source_matches: true })) } }
}
function saved(request: BudgetRequest): BudgetSaved {
  if (request.action === 'calculation') {
    const result = calculation(request.body.request_id); result.request = structuredClone(request.body)
    calculations.set(result.uuid, result); listing.calculations.unshift({ calculation_snapshot_id: result.uuid, calculation_snapshot_sha256: result.calculation_snapshot_sha256, captured_at: result.captured_at, all_arithmetic_supported: false, previous_snapshot_id: request.body.previous_snapshot_id }); return result
  }
  if (request.action === 'capture') {
    const result: BudgetCapture = { ...identity, uuid: request.body.request_id, case: definition, input_snapshot_sha256: '3'.repeat(64), artifact_id: workflowId, artifact_sha256: '4'.repeat(64), captured_at: '2026-10-06', method_choice: request.body.method_choice,
      calculation: calculations.get(request.body.calculation_snapshot_id)!, execution_authorized: false, credit_awarded: false,
      artifact: { workflow: { id: workflowId, name: 'My budget workflow', version: 2, input_config: {}, output_config: {}, resource_config: {}, config_override: null },
        steps: ['Review', 'Memo'].map((name, index) => ({ step: { id: String(index), name, data: {}, is_output: index === 1 }, tasks: [{ id: String(index), name: 'Prompt', data: { prompt: name } }] })), referenced_extraction_sets: {} } }
    captures.set(result.uuid, result); listing.captures.unshift({ input_snapshot_id: result.uuid, captured_at: result.captured_at, workflow_name: 'My budget workflow' }); return result
  }
  if (request.action === 'prepare') {
    const result: BudgetRun = { ...identity, run_id: request.body.request_id, state: 'prepared', plan_sha256: '5'.repeat(64), case_sha256: definition.case_sha256, input_snapshot_id: request.body.input_snapshot_id,
      input_snapshot: captures.get(request.body.input_snapshot_id)!, model_names: ['Synthetic model'], prepared_at: '2026-10-06',
      stage_plans: ['Review', 'Memo'].map((name, index) => ({ step_id: String(index), step_name: name, output_key: name, waits_for_previous_stage: index === 1,
        tasks: [{ task_id: String(index), task_type: 'Prompt', model: 'Synthetic model', effective_input_sources: index ? ['step_input', 'workflow_documents'] : ['workflow_documents'] }] })),
      scope_decision_id: null, scope_decision_sha256: null, scope_decision: null, authorization_sha256: null, result_sha256: null, task_events_sha256: '6'.repeat(64), task_events: [], result: null,
      can_save_scope: true, can_execute: false, can_finalize: false, credit_awarded: false, module_completion_eligible: false }
    runs.set(result.run_id, result); listing.runs.unshift({ run_id: result.run_id, state: result.state, prepared_at: result.prepared_at, input_snapshot_id: result.input_snapshot_id, workflow_name: 'My budget workflow' }); return result
  }
  if (request.action === 'review') {
    const result: BudgetReview = { ...identity, uuid: request.body.request_id, case: definition, submission: request.body, submitted_at: '2026-10-06', run: runs.get(request.body.run_id)!, credit_awarded: false, module_completion_eligible: false }
    reviews.set(result.uuid, result); listing.submissions.unshift({ submission_id: result.uuid, submitted_at: result.submitted_at, run_id: result.run.run_id, previous_submission_id: request.body.previous_submission_id }); return result
  }
  const result = structuredClone(runs.get(request.body.run_id)!)
  if (request.action === 'scope') {
    const scope: BudgetScope = { ...identity, uuid: request.body.request_id, run_id: result.run_id, plan_sha256: result.plan_sha256, case_sha256: definition.case_sha256, submitted_at: '2026-10-06', submission: request.body, credit_awarded: false }
    scopes.set(scope.uuid, scope); result.scope_decision = scope; result.scope_decision_id = scope.uuid; result.scope_decision_sha256 = '7'.repeat(64); result.can_execute = request.body.choice === 'approve'
  } else {
    result.state = 'completed'; result.can_execute = result.can_save_scope = result.can_finalize = false; result.authorization_sha256 = '8'.repeat(64); result.result_sha256 = '9'.repeat(64)
    result.task_events = result.stage_plans.flatMap((stage, index) => ['task_started', 'task_completed'].map((kind, offset) => ({ receipt_sha256: 'a'.repeat(64), receipt: { kind: kind as 'task_started' | 'task_completed', sequence: index * 2 + offset, stage_index: index, task_index: 0, task_id: String(index), consumed_context: 'Actual source\nSaved calculations', result: { output: `Actual ${stage.step_name} result` } } })))
    result.result = { status: 'completed', final_output: 'Internal budget memo', credit_awarded: false }
  }
  runs.set(result.run_id, result); return result
}
beforeEach(() => {
  vi.restoreAllMocks(); vi.resetAllMocks(); sessionStorage.clear()
  calculations = new Map([[calculationId, calculation()]]); captures = new Map(); runs = new Map(); reviews = new Map(); scopes = new Map()
  listing = { ...identity, case: definition, can_submit: true, read_only_reason: null,
    workflows: [{ workflow_id: workflowId, name: 'My budget workflow', version: 2 }], older_workflows_available: false,
    calculation_fields: calculationIds.map(id => ({ id, unit: 'USD', operation: 'sum', inputs: ['source_a', 'source_b'].map((name, index) => ({ id: name, label: `Source ${index + 1}`, source_page: 1 })) })),
    assigned_sources: [{ document_id: documentId, title: definition.source_filename, text: 'Original budget text', processing: false }],
    calculations: [{ calculation_snapshot_id: calculationId, calculation_snapshot_sha256: 'e'.repeat(64), captured_at: '2026-10-06', all_arithmetic_supported: false, previous_snapshot_id: null }], older_calculations_available: false,
    captures: [], older_captures_available: false, runs: [], older_runs_available: false, submissions: [], older_submissions_available: false }
  vi.mocked(api.getBudgetWork).mockImplementation(async () => structuredClone(listing))
  vi.mocked(api.getBudgetCalculation).mockImplementation(async (_e, id) => structuredClone(calculations.get(id)!))
  vi.mocked(api.getBudgetCapture).mockImplementation(async (_e, id) => structuredClone(captures.get(id)!))
  vi.mocked(api.getBudgetRun).mockImplementation(async (_e, id) => structuredClone(runs.get(id)!))
  vi.mocked(api.getBudgetReview).mockImplementation(async (_e, id) => structuredClone(reviews.get(id)!))
  vi.mocked(api.getBudgetScope).mockImplementation(async (_e, id) => structuredClone(scopes.get(id)!))
  vi.mocked(api.saveBudgetWork).mockImplementation(async (_e, request) => structuredClone(saved(request)))
})
const props = { enrollmentId: 'enrollment', definition }
async function openCalculation() { fireEvent.change(await screen.findByLabelText('Open saved budget work'), { target: { value: `calculation:${calculationId}` } }); await screen.findByRole('heading', { name: 'Calculation corrections or clarification needed' }) }
async function completeRun(waitForCompletion = true) {
  await openCalculation(); fireEvent.click(screen.getByRole('button', { name: 'Use these saved calculations' }))
  fireEvent.change(screen.getByLabelText('Owned budget workflow'), { target: { value: workflowId } })
  fireEvent.change(screen.getByLabelText(definition.questions[0].prompt), { target: { value: 'Use the available Prompt for interpretation and explicit learner arithmetic for verified source additions.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save workflow and method decision' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Prepare this saved budget workflow' }))
  await screen.findByRole('form', { name: 'Approve budget scope' })
  fireEvent.change(screen.getByLabelText('Budget execution choice'), { target: { value: 'approve' } })
  fireEvent.change(screen.getByLabelText('Explain this scope decision'), { target: { value: 'Only this internal memo using the exact assigned source and calculations.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save budget scope decision' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Run this approved budget workflow' }))
  if (waitForCompletion) await screen.findByRole('heading', { name: 'Run completed' })
}
it('requires explicit saved calculations, method, approval, execution and result review', async () => {
  render(<BudgetWorkflow {...props} />)
  await screen.findByLabelText('Owned budget workflow'); expect(api.saveBudgetWork).not.toHaveBeenCalled()
  await completeRun()
  expect(screen.getByRole('region', { name: 'Opened budget evidence' })).toHaveFocus()
  fireEvent.click(screen.getByRole('button', { name: 'Review this completed budget run' }))
  fireEvent.change(screen.getByLabelText(definition.questions[1].prompt), { target: { value: 'The recorded equipment total is incorrect and needs a linked revision.' } })
  fireEvent.change(screen.getByLabelText(definition.questions[2].prompt), { target: { value: 'The memo waits for the prior completed source review and receives the stored calculations.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save calculation and dependency review' }))
  await screen.findByText(/Assess budget review/)
  expect(vi.mocked(api.saveBudgetWork).mock.calls.map(call => call[1].action)).toEqual(['capture', 'prepare', 'scope', 'execute', 'review'])
})

it.each([
  ['task_execution_unavailable', 'This model operation was unavailable or failed.'],
  ['required_task_result_missing', 'This task did not return a usable result.'],
  ['untrusted provider detail SECRET', 'This task stopped without a completed result.'],
])('explains stopped work without offering implicit rerun or assessment: %s', async (failureKind, message) => {
  vi.mocked(api.saveBudgetWork).mockImplementation(async (_enrollment, request) => {
    const result = saved(request)
    if (request.action === 'execute' && 'state' in result) {
      result.state = 'failed'; result.result = null; result.result_sha256 = null
      const event = result.task_events.at(-1)!
      event.receipt.kind = 'task_failed'; event.receipt.failure_kind = failureKind
      delete event.receipt.result
      runs.set(result.run_id, structuredClone(result))
    }
    return structuredClone(result)
  })
  render(<BudgetWorkflow {...props} />)
  await screen.findByLabelText('Owned budget workflow')
  await completeRun(false)
  await screen.findByRole('heading', { name: 'Run stopped' })
  expect(screen.getByText(message, { exact: false })).toBeInTheDocument()
  expect(screen.getByText(/does not resume or reuse its task outputs automatically/)).toBeInTheDocument()
  expect(screen.queryByText(/SECRET/)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Run this approved budget workflow' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Review this completed budget run' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Finalize saved budget results without rerunning' })).not.toBeInTheDocument()
  expect(vi.mocked(api.saveBudgetWork).mock.calls.map(call => call[1].action)).toEqual(['capture', 'prepare', 'scope', 'execute'])
})
it('saves linked calculation corrections without replacing the original inputs', async () => {
  render(<BudgetWorkflow {...props} />); await openCalculation()
  fireEvent.click(screen.getByRole('button', { name: 'Revise these calculations' }))
  fireEvent.change(screen.getByLabelText('Source 1 amount (USD)'), { target: { value: '22501.00' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save source-bound calculations' }))
  await waitFor(() => expect(api.saveBudgetWork).toHaveBeenCalledTimes(1))
  const request = vi.mocked(api.saveBudgetWork).mock.calls[0][1]
  expect(request.action).toBe('calculation')
  if (request.action === 'calculation') { expect(request.body.previous_snapshot_id).toBe(calculationId); expect(request.body.records[0].inputs[0].value).toBe('22501.00') }
  expect(calculations.get(calculationId)!.request.records[0].inputs[0].value).toBe('22500.00')
})
it('recovers a lost calculation response by reading the original request without another write', async () => {
  vi.mocked(api.saveBudgetWork).mockImplementation(async (_e, request) => { saved(request); throw new ApiError(502, 'Lost response') })
  render(<BudgetWorkflow {...props} />); await openCalculation()
  fireEvent.click(screen.getByRole('button', { name: 'Revise these calculations' }))
  fireEvent.click(screen.getByRole('button', { name: 'Save source-bound calculations' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Check pending budget request' }))
  await waitFor(() => expect(sessionStorage.getItem(key)).toBeNull())
  expect(api.saveBudgetWork).toHaveBeenCalledTimes(1)
})
it('recovers a lost execution response without dispatching again', async () => {
  vi.mocked(api.saveBudgetWork).mockImplementation(async (_e, request) => { const result = saved(request); if (request.action === 'execute') throw new ApiError(502, 'Lost response'); return structuredClone(result) })
  render(<BudgetWorkflow {...props} />)
  await completeRun(false)
  await screen.findByText(/We could not confirm the saved state/)
  const check = screen.getByRole('button', { name: 'Check pending budget request' })
  await waitFor(() => expect(check).toBeEnabled())
  fireEvent.click(check)
  await screen.findByRole('heading', { name: 'Run completed' })
  expect(vi.mocked(api.saveBudgetWork).mock.calls.filter(call => call[1].action === 'execute')).toHaveLength(1)
})
it('opens read-only history without permitting new calculations or assessments', async () => {
  render(<BudgetWorkflow {...props} historyOnly />); await openCalculation()
  expect(screen.queryByRole('button', { name: 'Record new calculations' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Use these saved calculations' })).not.toBeInTheDocument()
  expect(api.saveBudgetWork).not.toHaveBeenCalled()
})
it('blocks new requests when frozen request storage is malformed while preserving history reads', async () => {
  sessionStorage.setItem(key, '{broken')
  render(<BudgetWorkflow {...props} />); await openCalculation()
  expect(screen.getByRole('alert')).toHaveTextContent('could not restore')
  expect(screen.queryByRole('button', { name: 'Record new calculations' })).not.toBeInTheDocument()
  expect(api.saveBudgetWork).not.toHaveBeenCalled()
})
it('rejects a foreign calculation response instead of adopting its answers', async () => {
  vi.mocked(api.getBudgetCalculation).mockResolvedValue({ ...calculation(), enrollment_id: 'foreign' })
  render(<BudgetWorkflow {...props} />)
  fireEvent.change(await screen.findByLabelText('Open saved budget work'), { target: { value: `calculation:${calculationId}` } })
  expect(await screen.findByRole('alert')).toHaveTextContent('could not be opened')
  expect(screen.queryByRole('button', { name: 'Use these saved calculations' })).not.toBeInTheDocument()
})

it('does not send a calculation when this tab cannot preserve its request', async () => {
  render(<BudgetWorkflow {...props} />); await openCalculation()
  fireEvent.click(screen.getByRole('button', { name: 'Revise these calculations' }))
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage unavailable') })
  fireEvent.click(screen.getByRole('button', { name: 'Save source-bound calculations' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('no request was sent')
  expect(api.saveBudgetWork).not.toHaveBeenCalled()
})
it.each(['executing', 'failed', 'uncertain'] as const)('preserves an incomplete %s run without offering completion or execution', async state => {
  vi.mocked(api.saveBudgetWork).mockImplementation(async (_e, request) => {
    const result = saved(request)
    if (request.action === 'execute') {
      const run = result as BudgetRun
      run.state = state; run.task_events = run.task_events.slice(0, 1); run.result = null; run.result_sha256 = null
    }
    return structuredClone(result)
  })
  render(<BudgetWorkflow {...props} />); await completeRun(false)
  await screen.findByText(/An incomplete or unknown result is not a completed memo/)
  expect(screen.queryByRole('button', { name: 'Review this completed budget run' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Finalize saved budget results without rerunning' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Run this approved budget workflow' })).not.toBeInTheDocument()
  expect(vi.mocked(api.saveBudgetWork).mock.calls.filter(call => call[1].action === 'execute')).toHaveLength(1)
})
it('restores the exact unsaved calculation across remount and requires an explicit finish', async () => {
  vi.mocked(api.saveBudgetWork).mockRejectedValue(new ApiError(503, 'Unavailable'))
  const first = render(<BudgetWorkflow {...props} />); await openCalculation()
  fireEvent.click(screen.getByRole('button', { name: 'Revise these calculations' }))
  fireEvent.change(screen.getByLabelText('Source 1 amount (USD)'), { target: { value: '22502.00' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save source-bound calculations' }))
  await screen.findByRole('alert')
  const original = structuredClone(vi.mocked(api.saveBudgetWork).mock.calls[0][1])
  first.unmount()
  vi.mocked(api.getBudgetCalculation).mockRejectedValue(new ApiError(404, 'Missing'))
  render(<BudgetWorkflow {...props} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Check pending budget request' }))
  await screen.findByRole('button', { name: 'Finish original budget request' })
  expect(api.saveBudgetWork).toHaveBeenCalledTimes(1)
  vi.mocked(api.saveBudgetWork).mockImplementation(async (_e, request) => structuredClone(saved(request)))
  fireEvent.click(screen.getByRole('button', { name: 'Finish original budget request' }))
  await screen.findByRole('heading', { name: 'Calculation corrections or clarification needed' })
  expect(api.saveBudgetWork).toHaveBeenLastCalledWith('enrollment', original)
  expect(sessionStorage.getItem(key)).toBeNull()
})


it('keeps budget review drafts with their exact run instead of copying them into another result', async () => {
  const auth = { user: { user_id: 'budget-draft-learner' } } as NonNullable<ContextType<typeof AuthContext>>
  render(<AuthContext.Provider value={auth}><BudgetWorkflow {...props} /></AuthContext.Provider>)
  await completeRun()
  const original = [...runs.values()][0]
  fireEvent.click(screen.getByRole('button', { name: 'Review this completed budget run' }))
  fireEvent.change(screen.getByLabelText(definition.questions[1].prompt), { target: { value: 'My analysis applies only to the first saved calculation run.' } })
  const different = { ...structuredClone(original), run_id: 'f'.repeat(32), result_sha256: 'e'.repeat(64), scope_decision: null }
  runs.set(different.run_id, different)
  listing.runs.unshift({ ...listing.runs[0], run_id: different.run_id })
  fireEvent.click(screen.getByRole('button', { name: 'Refresh saved budget work' }))
  await screen.findByRole('option', { name: /Run 1.*ffffff/ })
  fireEvent.change(screen.getByLabelText('Open saved budget work'), { target: { value: `run:${different.run_id}` } })
  fireEvent.click(await screen.findByRole('button', { name: 'Review this completed budget run' }))
  expect(screen.getByLabelText(definition.questions[1].prompt)).toHaveValue('')
  fireEvent.change(screen.getByLabelText(definition.questions[1].prompt), { target: { value: 'Separate analysis of the second saved result.' } })
  fireEvent.change(screen.getByLabelText('Open saved budget work'), { target: { value: `run:${original.run_id}` } })
  fireEvent.click(await screen.findByRole('button', { name: 'Review this completed budget run' }))
  expect(screen.getByLabelText(definition.questions[1].prompt)).toHaveValue('My analysis applies only to the first saved calculation run.')
  expect(vi.mocked(api.saveBudgetWork).mock.calls.some(([, request]) => request.action === 'review')).toBe(false)
})

it('preserves incomplete calculation fields when the learner closes and reopens the form', async () => {
  const auth = { user: { user_id: 'budget-draft-learner' } } as NonNullable<ContextType<typeof AuthContext>>
  render(<AuthContext.Provider value={auth}><BudgetWorkflow {...props} /></AuthContext.Provider>)
  fireEvent.click(await screen.findByRole('button', { name: 'Record new calculations' }))
  fireEvent.change(screen.getByLabelText('Source 1 amount (USD)'), { target: { value: '123.' } })
  fireEvent.change(screen.getByLabelText('Source quotation for Source 1'), { target: { value: 'Original unfinished source quote' } })
  fireEvent.change(screen.getByLabelText('Explain your check of Source 1'), { target: { value: 'My unfinished explanation' } })
  fireEvent.change(screen.getByLabelText('Explain what these additions establish and what remains unresolved'), { target: { value: 'My unfinished limits explanation' } })
  fireEvent.click(screen.getByRole('button', { name: 'Close calculation form' }))
  fireEvent.click(screen.getByRole('button', { name: 'Record new calculations' }))
  expect(screen.getByLabelText('Source 1 amount (USD)')).toHaveValue('123.')
  expect(screen.getByLabelText('Source quotation for Source 1')).toHaveValue('Original unfinished source quote')
  expect(screen.getByLabelText('Explain your check of Source 1')).toHaveValue('My unfinished explanation')
  expect(screen.getByLabelText('Explain what these additions establish and what remains unresolved')).toHaveValue('My unfinished limits explanation')
  expect(api.saveBudgetWork).not.toHaveBeenCalled()
})
it('keeps calculation sources and saved-revision drafts separate', () => {
  const send = vi.fn(), auth = { user: { user_id: 'budget-draft-learner' } } as NonNullable<ContextType<typeof AuthContext>>
  const choices = { ...listing, assigned_sources: [...listing.assigned_sources, { ...listing.assigned_sources[0], document_id: 'f'.repeat(32), title: 'Second assigned source' }] }
  const node = (original: BudgetCalculation | null = null) => <AuthContext.Provider value={auth}><BudgetCalculationForm listing={choices} original={original} locked={false} onSave={send} /></AuthContext.Provider>
  const view = render(node())
  fireEvent.change(screen.getByLabelText('Assigned source'), { target: { value: documentId } })
  fireEvent.change(screen.getByLabelText('Source 1 amount (USD)'), { target: { value: '111.00' } })
  fireEvent.change(screen.getByLabelText('Assigned source'), { target: { value: 'f'.repeat(32) } })
  expect(screen.getByLabelText('Source 1 amount (USD)')).toHaveValue('')
  fireEvent.change(screen.getByLabelText('Source 1 amount (USD)'), { target: { value: '222.00' } })
  fireEvent.change(screen.getByLabelText('Assigned source'), { target: { value: documentId } })
  expect(screen.getByLabelText('Source 1 amount (USD)')).toHaveValue('111.00')
  const original = calculations.get(calculationId)!
  view.rerender(node(original))
  expect(screen.getByLabelText('Source 1 amount (USD)')).toHaveValue('22500.00')
  fireEvent.change(screen.getByLabelText('Source 1 amount (USD)'), { target: { value: '333.00' } })
  view.rerender(node({ ...original, calculation_snapshot_sha256: 'f'.repeat(64) }))
  expect(screen.getByLabelText('Source 1 amount (USD)')).toHaveValue('22500.00')
  view.rerender(node(original))
  expect(screen.getByLabelText('Source 1 amount (USD)')).toHaveValue('333.00')
  expect(send).not.toHaveBeenCalled()
})
it('binds the budget method explanation to the selected calculation and workflow version', async () => {
  const auth = { user: { user_id: 'budget-draft-learner' } } as NonNullable<ContextType<typeof AuthContext>>
  render(<AuthContext.Provider value={auth}><BudgetWorkflow {...props} /></AuthContext.Provider>)
  await openCalculation(); fireEvent.click(screen.getByRole('button', { name: 'Use these saved calculations' }))
  fireEvent.change(screen.getByLabelText('Owned budget workflow'), { target: { value: workflowId } })
  fireEvent.change(screen.getByLabelText(definition.questions[0].prompt), { target: { value: 'My method for the selected workflow revision and saved calculation.' } })
  listing.workflows[0].version++
  fireEvent.click(screen.getByRole('button', { name: 'Refresh saved budget work' }))
  await screen.findByRole('option', { name: 'My budget workflow · version 3' })
  expect(screen.getByLabelText(definition.questions[0].prompt)).toHaveValue('')
  listing.workflows[0].version--
  fireEvent.click(screen.getByRole('button', { name: 'Refresh saved budget work' }))
  await screen.findByRole('option', { name: 'My budget workflow · version 2' })
  expect(screen.getByLabelText(definition.questions[0].prompt)).toHaveValue('My method for the selected workflow revision and saved calculation.')
  expect(api.saveBudgetWork).not.toHaveBeenCalled()
})
