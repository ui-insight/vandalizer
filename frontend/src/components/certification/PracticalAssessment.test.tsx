import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/certification'
import { ApiError } from '../../api/client'
import type { SavedAutomaticReview } from '../../types/certification'
import { PracticalAssessment } from './PracticalAssessment'
vi.mock('../../api/certification', () => ({ getAutomaticReview: vi.fn(), requestAutomaticReview: vi.fn(), retryAutomaticReview: vi.fn(), requestProcessReview: vi.fn(), retryProcessReview: vi.fn(), requestWorkflowDesignReview: vi.fn(), retryWorkflowDesignReview: vi.fn(), requestConnectedReview: vi.fn(), retryConnectedReview: vi.fn(), requestBudgetReview: vi.fn(), retryBudgetReview: vi.fn(), requestOutputReview: vi.fn(), retryOutputReview: vi.fn(), requestValidationReview: vi.fn(), retryValidationReview: vi.fn(), requestBatchReview: vi.fn(), retryBatchReview: vi.fn(), requestGovernanceReview: vi.fn(), retryGovernanceReview: vi.fn() }))
const props = { enrollmentId: 'enrollment', moduleId: 'foundations', runId: 'b'.repeat(32), onOpenFeedback: vi.fn() }
const key = `certification-assessment:enrollment:${props.runId}`
function receipt(id: string, parent: string | null = null): SavedAutomaticReview {
  return { attempt_id: id, enrollment_id: props.enrollmentId, module_id: props.moduleId, run_id: props.runId,
    course_version: 'draft', manifest_sha256: 'c'.repeat(64), prepared_at: '2026-10-06', finished_at: null, parent_attempt_id: parent,
    status: 'revision_required', assessment_kind: 'practical_review_draft', credit_awarded: false, module_completion_eligible: false,
    staff_review_required: false, can_request_review: false, can_retry_review: false, outcomes: [] }
}
beforeEach(() => {
  vi.restoreAllMocks(); vi.resetAllMocks(); sessionStorage.clear()
  vi.mocked(api.requestAutomaticReview).mockImplementation(async (_e, _r, id) => receipt(id))
  vi.mocked(api.retryAutomaticReview).mockImplementation(async (_e, parent, id) => receipt(id, parent))
})
async function submit() {
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('region', { name: 'Requested assessment status' })
}
it('requests only on explicit action, preserves its identity and opens feedback separately', async () => {
  render(<PracticalAssessment {...props} />)
  expect(api.requestAutomaticReview).not.toHaveBeenCalled(); expect(api.getAutomaticReview).not.toHaveBeenCalled()
  await submit()
  const id = vi.mocked(api.requestAutomaticReview).mock.calls[0][2]
  expect(api.requestAutomaticReview).toHaveBeenCalledWith('enrollment', props.runId, id)
  expect(JSON.parse(sessionStorage.getItem(key)!)).toEqual({ request_id: id, parent_attempt_id: null })
  await waitFor(() => expect(screen.getByRole('region', { name: 'Requested assessment status' })).toHaveFocus())
  expect(props.onOpenFeedback).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Open saved feedback' }))
  expect(props.onOpenFeedback).toHaveBeenCalledWith(id)
})
it('recovers a lost response across remount using a read only', async () => {
  let id = ''
  vi.mocked(api.requestAutomaticReview).mockImplementation(async (_e, _r, value) => { id = value; throw new Error('Lost response') })
  const first = render(<PracticalAssessment {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' })); await screen.findByRole('alert'); first.unmount()
  vi.mocked(api.getAutomaticReview).mockImplementation(async () => receipt(id))
  render(<PracticalAssessment {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' }))
  await screen.findByRole('heading', { name: 'Revision needed' })
  expect(api.requestAutomaticReview).toHaveBeenCalledOnce()
  expect(api.getAutomaticReview).toHaveBeenCalledWith('enrollment', id)
})
it.each(['prepared', 'evaluating'] as const)('reads %s without dispatch and finishes only on another explicit action', async status => {
  const id = 'a'.repeat(32)
  sessionStorage.setItem(key, JSON.stringify({ request_id: id, parent_attempt_id: null }))
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...receipt(id), status })
  render(<PracticalAssessment {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' }))
  await screen.findByRole('button', { name: 'Finish requested assessment' })
  expect(api.requestAutomaticReview).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Finish requested assessment' }))
  await screen.findByRole('heading', { name: 'Revision needed' })
  expect(api.requestAutomaticReview).toHaveBeenCalledWith('enrollment', props.runId, id)
})
it('can finish the same reference after a confirmed missing receipt, without a new request on the read', async () => {
  const id = 'a'.repeat(32)
  sessionStorage.setItem(key, JSON.stringify({ request_id: id, parent_attempt_id: null }))
  vi.mocked(api.getAutomaticReview).mockRejectedValue(new ApiError(404, 'Missing receipt'))
  render(<PracticalAssessment {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' }))
  await screen.findByRole('button', { name: 'Finish requested assessment' })
  expect(api.requestAutomaticReview).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Finish requested assessment' }))
  await screen.findByRole('heading', { name: 'Revision needed' })
  expect(api.requestAutomaticReview).toHaveBeenCalledWith('enrollment', props.runId, id)
})
it('blocks finishing or replacing an unconfirmed request when history is unavailable', async () => {
  sessionStorage.setItem(key, JSON.stringify({ request_id: 'a'.repeat(32), parent_attempt_id: null }))
  vi.mocked(api.getAutomaticReview).mockRejectedValue(new ApiError(503, 'Unavailable'))
  render(<PracticalAssessment {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' })); await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: 'Finish requested assessment' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Assess saved work automatically' })).not.toBeInTheDocument()
  expect(api.requestAutomaticReview).not.toHaveBeenCalled(); expect(api.retryAutomaticReview).not.toHaveBeenCalled()
})
it('makes a technical retry with a new identity and preserves the original parent after response loss', async () => {
  vi.mocked(api.requestAutomaticReview).mockImplementation(async (_e, _r, id) => ({ ...receipt(id), status: 'grading_unavailable' }))
  vi.mocked(api.retryAutomaticReview).mockRejectedValue(new Error('Lost retry response'))
  const first = render(<PracticalAssessment {...props} />); await submit()
  const parent = vi.mocked(api.requestAutomaticReview).mock.calls[0][2]
  fireEvent.click(screen.getByRole('button', { name: 'Retry the original assessment' })); await screen.findByRole('alert')
  const pending = JSON.parse(sessionStorage.getItem(key)!)
  expect(pending.parent_attempt_id).toBe(parent); expect(pending.request_id).not.toBe(parent)
  expect(api.retryAutomaticReview).toHaveBeenCalledWith('enrollment', parent, pending.request_id)
  first.unmount(); vi.mocked(api.getAutomaticReview).mockResolvedValue(receipt(pending.request_id, parent))
  render(<PracticalAssessment {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' })); await screen.findByRole('heading', { name: 'Revision needed' })
  expect(api.retryAutomaticReview).toHaveBeenCalledOnce()
})
it('creates a separate new assessment for revised saved work', async () => {
  render(<PracticalAssessment {...props} />); await submit()
  const original = vi.mocked(api.requestAutomaticReview).mock.calls[0][2]
  fireEvent.click(screen.getByRole('button', { name: 'Assess revised saved work' }))
  await waitFor(() => expect(api.requestAutomaticReview).toHaveBeenCalledTimes(2))
  const next = vi.mocked(api.requestAutomaticReview).mock.calls[1][2]
  expect(next).not.toBe(original)
  expect(JSON.parse(sessionStorage.getItem(key)!)).toEqual({ request_id: next, parent_attempt_id: null })
  expect(api.retryAutomaticReview).not.toHaveBeenCalled()
})
it('does not send when browser storage is unavailable', async () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage disabled') })
  render(<PracticalAssessment {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('no assessment request was sent')
  expect(api.requestAutomaticReview).not.toHaveBeenCalled()
})
it.each([{ enrollment_id: 'foreign' }, { run_id: 'f'.repeat(32) }, { parent_attempt_id: 'f'.repeat(32) }, { staff_review_required: true }, { credit_awarded: true }])('rejects incompatible receipt %j', async change => {
  vi.mocked(api.requestAutomaticReview).mockImplementation(async (_e, _r, id) => ({ ...receipt(id), ...change }) as SavedAutomaticReview)
  render(<PracticalAssessment {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' })); await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: 'Open saved feedback' })).not.toBeInTheDocument()
  expect(sessionStorage.getItem(key)).not.toBeNull()
})
it('ignores a late response after leaving the run', async () => {
  let finish!: (value: SavedAutomaticReview) => void
  vi.mocked(api.requestAutomaticReview).mockReturnValue(new Promise(resolve => { finish = resolve }))
  const view = render(<PracticalAssessment {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  const id = vi.mocked(api.requestAutomaticReview).mock.calls[0][2]
  view.unmount(); await act(async () => finish(receipt(id)))
  expect(props.onOpenFeedback).not.toHaveBeenCalled()
})

const processId = 'e'.repeat(32)
function processReceipt(id: string, parent: string | null = null): SavedAutomaticReview {
  return { ...receipt(id, parent), module_id: 'process_mapping', run_id: null, process_submission_id: processId, assessment_kind: 'process_design_review_draft' }
}
it('assesses the exact saved process design without using a run endpoint', async () => {
  vi.mocked(api.requestProcessReview).mockImplementation(async (_e, _s, id) => processReceipt(id))
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="process_mapping" processSubmissionId={processId} onOpenFeedback={vi.fn()} />)
  await submit()
  expect(api.requestProcessReview).toHaveBeenCalledWith('enrollment', processId, expect.stringMatching(/^[a-f0-9]{32}$/))
  expect(api.requestAutomaticReview).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Assess revised saved work' })).not.toBeInTheDocument()
  expect(screen.getByText(/It does not execute a workflow/)).toBeInTheDocument()
})
it('rejects a process assessment linked to another design', async () => {
  vi.mocked(api.requestProcessReview).mockImplementation(async (_e, _s, id) => ({ ...processReceipt(id), process_submission_id: 'f'.repeat(32) }))
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="process_mapping" processSubmissionId={processId} onOpenFeedback={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('region', { name: 'Requested assessment status' })).not.toBeInTheDocument()
})
it('recovers a lost process assessment then explicitly retries its original technical failure', async () => {
  let id = ''
  vi.mocked(api.requestProcessReview).mockImplementation(async (_e, _s, value) => { id = value; throw new Error('Lost reply') })
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="process_mapping" processSubmissionId={processId} onOpenFeedback={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...processReceipt(id), status: 'grading_unavailable' })
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' }))
  await screen.findByRole('heading', { name: 'Assessment unavailable' })
  vi.mocked(api.retryProcessReview).mockImplementation(async (_e, parent, child) => processReceipt(child, parent))
  fireEvent.click(screen.getByRole('button', { name: 'Retry the original assessment' }))
  await screen.findByRole('heading', { name: 'Revision needed' })
  expect(api.requestProcessReview).toHaveBeenCalledOnce()
  expect(api.retryProcessReview).toHaveBeenCalledWith('enrollment', id, expect.any(String))
  expect(api.retryAutomaticReview).not.toHaveBeenCalled()
})

const workflowId = 'e'.repeat(32)
const connectedId = 'f'.repeat(32)
function connectedReceipt(id: string, parent: string | null = null): SavedAutomaticReview {
  return { ...receipt(id, parent), module_id: 'multi_step', connected_review_submission_id: connectedId, assessment_kind: 'connected_workflow_review_draft' }
}
it('assesses a saved connected comparison without requesting another workflow execution', async () => {
  vi.mocked(api.requestConnectedReview).mockImplementation(async (_e, _s, id) => connectedReceipt(id))
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="multi_step" connectedReviewSubmissionId={connectedId} onOpenFeedback={vi.fn()} />)
  await submit()
  expect(api.requestConnectedReview).toHaveBeenCalledWith('enrollment', connectedId, expect.stringMatching(/^[a-f0-9]{32}$/))
  expect(api.requestAutomaticReview).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Assess revised saved work' })).not.toBeInTheDocument()
})
it('rejects connected feedback that belongs to another comparison', async () => {
  vi.mocked(api.requestConnectedReview).mockImplementation(async (_e, _s, id) => ({ ...connectedReceipt(id), connected_review_submission_id: 'a'.repeat(32) }))
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="multi_step" connectedReviewSubmissionId={connectedId} onOpenFeedback={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('region', { name: 'Requested assessment status' })).not.toBeInTheDocument()
})
it('recovers a lost connected assessment and explicitly retries only the saved technical failure', async () => {
  let id = ''
  vi.mocked(api.requestConnectedReview).mockImplementation(async (_e, _s, value) => { id = value; throw new Error('Lost reply') })
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="multi_step" connectedReviewSubmissionId={connectedId} onOpenFeedback={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...connectedReceipt(id), status: 'grading_unavailable' })
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' }))
  await screen.findByRole('heading', { name: 'Assessment unavailable' })
  vi.mocked(api.retryConnectedReview).mockImplementation(async (_e, parent, child) => connectedReceipt(child, parent))
  fireEvent.click(screen.getByRole('button', { name: 'Retry the original assessment' }))
  await screen.findByRole('heading', { name: 'Revision needed' })
  expect(api.requestConnectedReview).toHaveBeenCalledOnce()
  expect(api.retryConnectedReview).toHaveBeenCalledWith('enrollment', id, expect.any(String))
  expect(api.retryAutomaticReview).not.toHaveBeenCalled()
})
function workflowReceipt(id: string, parent: string | null = null): SavedAutomaticReview {
  return { ...receipt(id, parent), module_id: 'workflow_design', run_id: null, workflow_design_submission_id: workflowId, assessment_kind: 'workflow_design_review_draft' }
}
it('assesses the exact saved workflow approval without using a run endpoint', async () => {
  vi.mocked(api.requestWorkflowDesignReview).mockImplementation(async (_e, _s, id) => workflowReceipt(id))
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="workflow_design" workflowDesignSubmissionId={workflowId} onOpenFeedback={vi.fn()} />)
  await submit()
  expect(api.requestWorkflowDesignReview).toHaveBeenCalledWith('enrollment', workflowId, expect.stringMatching(/^[a-f0-9]{32}$/))
  expect(api.requestAutomaticReview).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Assess revised saved work' })).not.toBeInTheDocument()
  expect(screen.getByText(/It does not run the workflow or release anything/)).toBeInTheDocument()
})
it('rejects a workflow assessment linked to another design', async () => {
  vi.mocked(api.requestWorkflowDesignReview).mockImplementation(async (_e, _s, id) => ({ ...workflowReceipt(id), workflow_design_submission_id: 'f'.repeat(32) }))
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="workflow_design" workflowDesignSubmissionId={workflowId} onOpenFeedback={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('region', { name: 'Requested assessment status' })).not.toBeInTheDocument()
})
it('recovers a lost workflow assessment then explicitly retries its original technical failure', async () => {
  let id = ''
  vi.mocked(api.requestWorkflowDesignReview).mockImplementation(async (_e, _s, value) => { id = value; throw new Error('Lost reply') })
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="workflow_design" workflowDesignSubmissionId={workflowId} onOpenFeedback={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...workflowReceipt(id), status: 'grading_unavailable' })
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' }))
  await screen.findByRole('heading', { name: 'Assessment unavailable' })
  vi.mocked(api.retryWorkflowDesignReview).mockImplementation(async (_e, parent, child) => workflowReceipt(child, parent))
  fireEvent.click(screen.getByRole('button', { name: 'Retry the original assessment' }))
  await screen.findByRole('heading', { name: 'Revision needed' })
  expect(api.requestWorkflowDesignReview).toHaveBeenCalledOnce()
  expect(api.retryWorkflowDesignReview).toHaveBeenCalledWith('enrollment', id, expect.any(String))
  expect(api.retryAutomaticReview).not.toHaveBeenCalled()
})

const budgetId = 'f'.repeat(32)
function budgetReceipt(id: string, parent: string | null = null): SavedAutomaticReview {
  return { ...receipt(id, parent), module_id: 'advanced_nodes', budget_review_submission_id: budgetId, assessment_kind: 'budget_workflow_review_draft' }
}
it('assesses a saved budget calculation and dependency review without requesting another workflow execution', async () => {
  vi.mocked(api.requestBudgetReview).mockImplementation(async (_e, _s, id) => budgetReceipt(id))
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="advanced_nodes" budgetReviewSubmissionId={budgetId} onOpenFeedback={vi.fn()} />)
  await submit()
  expect(api.requestBudgetReview).toHaveBeenCalledWith('enrollment', budgetId, expect.stringMatching(/^[a-f0-9]{32}$/))
  expect(api.requestAutomaticReview).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Assess revised saved work' })).not.toBeInTheDocument()
})
it('rejects budget feedback that belongs to another calculation and dependency review', async () => {
  vi.mocked(api.requestBudgetReview).mockImplementation(async (_e, _s, id) => ({ ...budgetReceipt(id), budget_review_submission_id: 'a'.repeat(32) }))
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="advanced_nodes" budgetReviewSubmissionId={budgetId} onOpenFeedback={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('region', { name: 'Requested assessment status' })).not.toBeInTheDocument()
})
it('recovers a lost budget assessment and explicitly retries only the saved technical failure', async () => {
  let id = ''
  vi.mocked(api.requestBudgetReview).mockImplementation(async (_e, _s, value) => { id = value; throw new Error('Lost reply') })
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="advanced_nodes" budgetReviewSubmissionId={budgetId} onOpenFeedback={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...budgetReceipt(id), status: 'grading_unavailable' })
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' }))
  await screen.findByRole('heading', { name: 'Assessment unavailable' })
  vi.mocked(api.retryBudgetReview).mockImplementation(async (_e, parent, child) => budgetReceipt(child, parent))
  fireEvent.click(screen.getByRole('button', { name: 'Retry the original assessment' }))
  await screen.findByRole('heading', { name: 'Revision needed' })
  expect(api.requestBudgetReview).toHaveBeenCalledOnce()
  expect(api.retryBudgetReview).toHaveBeenCalledWith('enrollment', id, expect.any(String))
  expect(api.retryAutomaticReview).not.toHaveBeenCalled()
})

const outputId = 'f'.repeat(32)
function outputReceipt(id: string, parent: string | null = null): SavedAutomaticReview {
  return { ...receipt(id, parent), module_id: 'output_delivery', output_review_submission_id: outputId, assessment_kind: 'output_workflow_review_draft' }
}
it('assesses a saved output file and handoff review without requesting another workflow execution', async () => {
  vi.mocked(api.requestOutputReview).mockImplementation(async (_e, _s, id) => outputReceipt(id))
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="output_delivery" outputReviewSubmissionId={outputId} onOpenFeedback={vi.fn()} />)
  await submit()
  expect(api.requestOutputReview).toHaveBeenCalledWith('enrollment', outputId, expect.stringMatching(/^[a-f0-9]{32}$/))
  expect(api.requestAutomaticReview).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Assess revised saved work' })).not.toBeInTheDocument()
})
it('rejects output feedback that belongs to another file and handoff review', async () => {
  vi.mocked(api.requestOutputReview).mockImplementation(async (_e, _s, id) => ({ ...outputReceipt(id), output_review_submission_id: 'a'.repeat(32) }))
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="output_delivery" outputReviewSubmissionId={outputId} onOpenFeedback={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('region', { name: 'Requested assessment status' })).not.toBeInTheDocument()
})
it('recovers a lost output assessment and explicitly retries only the saved technical failure', async () => {
  let id = ''
  vi.mocked(api.requestOutputReview).mockImplementation(async (_e, _s, value) => { id = value; throw new Error('Lost reply') })
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="output_delivery" outputReviewSubmissionId={outputId} onOpenFeedback={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...outputReceipt(id), status: 'grading_unavailable' })
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' }))
  await screen.findByRole('heading', { name: 'Assessment unavailable' })
  vi.mocked(api.retryOutputReview).mockImplementation(async (_e, parent, child) => outputReceipt(child, parent))
  fireEvent.click(screen.getByRole('button', { name: 'Retry the original assessment' }))
  await screen.findByRole('heading', { name: 'Revision needed' })
  expect(api.requestOutputReview).toHaveBeenCalledOnce()
  expect(api.retryOutputReview).toHaveBeenCalledWith('enrollment', id, expect.any(String))
  expect(api.retryAutomaticReview).not.toHaveBeenCalled()
})

const validationId = 'f'.repeat(32)
function validationReceipt(id: string, parent: string | null = null): SavedAutomaticReview {
  return { ...receipt(id, parent), module_id: 'validation_qa', validation_review_submission_id: validationId, assessment_kind: 'validation_suite_review_draft' }
}
it('assesses a saved validation repair review without requesting another workflow execution', async () => {
  vi.mocked(api.requestValidationReview).mockImplementation(async (_e, _s, id) => validationReceipt(id))
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="validation_qa" validationReviewSubmissionId={validationId} onOpenFeedback={vi.fn()} />)
  await submit()
  expect(api.requestValidationReview).toHaveBeenCalledWith('enrollment', validationId, expect.stringMatching(/^[a-f0-9]{32}$/))
  expect(api.requestAutomaticReview).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Assess revised saved work' })).not.toBeInTheDocument()
})
it('rejects validation feedback that belongs to another source and retest review', async () => {
  vi.mocked(api.requestValidationReview).mockImplementation(async (_e, _s, id) => ({ ...validationReceipt(id), validation_review_submission_id: 'a'.repeat(32) }))
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="validation_qa" validationReviewSubmissionId={validationId} onOpenFeedback={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('region', { name: 'Requested assessment status' })).not.toBeInTheDocument()
})
it('recovers a lost validation assessment and explicitly retries only the saved technical failure', async () => {
  let id = ''
  vi.mocked(api.requestValidationReview).mockImplementation(async (_e, _s, value) => { id = value; throw new Error('Lost reply') })
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="validation_qa" validationReviewSubmissionId={validationId} onOpenFeedback={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...validationReceipt(id), status: 'grading_unavailable' })
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' }))
  await screen.findByRole('heading', { name: 'Assessment unavailable' })
  vi.mocked(api.retryValidationReview).mockImplementation(async (_e, parent, child) => validationReceipt(child, parent))
  fireEvent.click(screen.getByRole('button', { name: 'Retry the original assessment' }))
  await screen.findByRole('heading', { name: 'Revision needed' })
  expect(api.requestValidationReview).toHaveBeenCalledOnce()
  expect(api.retryValidationReview).toHaveBeenCalledWith('enrollment', id, expect.any(String))
  expect(api.retryAutomaticReview).not.toHaveBeenCalled()
})

const batchId = '9'.repeat(32)
function batchReceipt(id: string, parent: string | null = null): SavedAutomaticReview {
  return { ...receipt(id, parent), module_id: 'batch_processing', batch_review_submission_id: batchId, assessment_kind: 'bounded_batch_review_draft' }
}
it('assesses a saved batch repair review without requesting another workflow execution', async () => {
  vi.mocked(api.requestBatchReview).mockImplementation(async (_e, _s, id) => batchReceipt(id))
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="batch_processing" batchReviewSubmissionId={batchId} onOpenFeedback={vi.fn()} />)
  await submit()
  expect(api.requestBatchReview).toHaveBeenCalledWith('enrollment', batchId, expect.stringMatching(/^[a-f0-9]{32}$/))
  expect(api.requestAutomaticReview).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Assess revised saved work' })).not.toBeInTheDocument()
})
it('rejects batch feedback that belongs to another source and retest review', async () => {
  vi.mocked(api.requestBatchReview).mockImplementation(async (_e, _s, id) => ({ ...batchReceipt(id), batch_review_submission_id: 'a'.repeat(32) }))
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="batch_processing" batchReviewSubmissionId={batchId} onOpenFeedback={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('region', { name: 'Requested assessment status' })).not.toBeInTheDocument()
})
it('recovers a lost batch assessment and explicitly retries only the saved technical failure', async () => {
  let id = ''
  vi.mocked(api.requestBatchReview).mockImplementation(async (_e, _s, value) => { id = value; throw new Error('Lost reply') })
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="batch_processing" batchReviewSubmissionId={batchId} onOpenFeedback={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...batchReceipt(id), status: 'grading_unavailable' })
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' }))
  await screen.findByRole('heading', { name: 'Assessment unavailable' })
  vi.mocked(api.retryBatchReview).mockImplementation(async (_e, parent, child) => batchReceipt(child, parent))
  fireEvent.click(screen.getByRole('button', { name: 'Retry the original assessment' }))
  await screen.findByRole('heading', { name: 'Revision needed' })
  expect(api.requestBatchReview).toHaveBeenCalledOnce()
  expect(api.retryBatchReview).toHaveBeenCalledWith('enrollment', id, expect.any(String))
  expect(api.retryAutomaticReview).not.toHaveBeenCalled()
})

const governanceId = '9'.repeat(32)
function governanceReceipt(id: string, parent: string | null = null): SavedAutomaticReview {
  return { ...receipt(id, parent), module_id: 'governance', governance_review_submission_id: governanceId, assessment_kind: 'governance_capstone_review_draft' }
}
it('assesses a saved capstone supervision review without requesting another workflow execution', async () => {
  vi.mocked(api.requestGovernanceReview).mockImplementation(async (_e, _s, id) => governanceReceipt(id))
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="governance" governanceReviewSubmissionId={governanceId} onOpenFeedback={vi.fn()} />)
  await submit()
  expect(api.requestGovernanceReview).toHaveBeenCalledWith('enrollment', governanceId, expect.stringMatching(/^[a-f0-9]{32}$/))
  expect(api.requestAutomaticReview).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Assess revised saved work' })).not.toBeInTheDocument()
})
it('rejects capstone feedback that belongs to another source and retest review', async () => {
  vi.mocked(api.requestGovernanceReview).mockImplementation(async (_e, _s, id) => ({ ...governanceReceipt(id), governance_review_submission_id: 'a'.repeat(32) }))
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="governance" governanceReviewSubmissionId={governanceId} onOpenFeedback={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('region', { name: 'Requested assessment status' })).not.toBeInTheDocument()
})
it('recovers a lost capstone assessment and explicitly retries only the saved technical failure', async () => {
  let id = ''
  vi.mocked(api.requestGovernanceReview).mockImplementation(async (_e, _s, value) => { id = value; throw new Error('Lost reply') })
  render(<PracticalAssessment enrollmentId="enrollment" moduleId="governance" governanceReviewSubmissionId={governanceId} onOpenFeedback={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...governanceReceipt(id), status: 'grading_unavailable' })
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' }))
  await screen.findByRole('heading', { name: 'Assessment unavailable' })
  vi.mocked(api.retryGovernanceReview).mockImplementation(async (_e, parent, child) => governanceReceipt(child, parent))
  fireEvent.click(screen.getByRole('button', { name: 'Retry the original assessment' }))
  await screen.findByRole('heading', { name: 'Revision needed' })
  expect(api.requestGovernanceReview).toHaveBeenCalledOnce()
  expect(api.retryGovernanceReview).toHaveBeenCalledWith('enrollment', id, expect.any(String))
  expect(api.retryAutomaticReview).not.toHaveBeenCalled()
})

function duplicateReview(id: string) {
  const error = new ApiError(409, 'This saved work already has an assessment request')
  error.code = 'CERTIFICATION_REVIEW_EXISTS'; error.existingReviewId = id
  return error
}
it('recovers another tab assessment through an explicit verified read without dispatching twice', async () => {
  const original = 'd'.repeat(32)
  vi.mocked(api.requestAutomaticReview).mockRejectedValue(duplicateReview(original))
  const view = render(<PracticalAssessment {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('no additional assessment was started')
  expect(api.getAutomaticReview).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Finish requested assessment' })).not.toBeInTheDocument()
  expect(JSON.parse(sessionStorage.getItem(key)!)).toEqual({ request_id: original, parent_attempt_id: null })
  view.unmount()
  vi.mocked(api.getAutomaticReview).mockResolvedValue(receipt(original))
  render(<PracticalAssessment {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' }))
  await screen.findByRole('heading', { name: 'Revision needed' })
  expect(api.getAutomaticReview).toHaveBeenCalledWith('enrollment', original)
  expect(api.requestAutomaticReview).toHaveBeenCalledOnce()
})
it.each([{ enrollment_id: 'foreign' }, { run_id: 'f'.repeat(32) }, { parent_attempt_id: 'e'.repeat(32) }])('rejects an incompatible original assessment after conflict %j', async change => {
  const original = 'd'.repeat(32)
  vi.mocked(api.requestAutomaticReview).mockRejectedValue(duplicateReview(original))
  vi.mocked(api.getAutomaticReview).mockResolvedValue({ ...receipt(original), ...change })
  render(<PracticalAssessment {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' }))
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('could not confirm'))
  expect(screen.queryByRole('button', { name: 'Open saved feedback' })).not.toBeInTheDocument()
  expect(api.requestAutomaticReview).toHaveBeenCalledOnce()
})
it('keeps the original parent when another tab already requested the technical retry', async () => {
  const child = 'd'.repeat(32)
  vi.mocked(api.requestAutomaticReview).mockImplementation(async (_e, _r, id) => ({ ...receipt(id), status: 'grading_unavailable' }))
  vi.mocked(api.retryAutomaticReview).mockRejectedValue(duplicateReview(child))
  render(<PracticalAssessment {...props} />); await submit()
  const parent = vi.mocked(api.requestAutomaticReview).mock.calls[0][2]
  fireEvent.click(screen.getByRole('button', { name: 'Retry the original assessment' }))
  await screen.findByRole('alert')
  expect(JSON.parse(sessionStorage.getItem(key)!)).toEqual({ request_id: child, parent_attempt_id: parent })
  vi.mocked(api.getAutomaticReview).mockResolvedValue(receipt(child, parent))
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' }))
  await screen.findByRole('heading', { name: 'Revision needed' })
  expect(api.retryAutomaticReview).toHaveBeenCalledOnce()
})
it('keeps conflict recovery usable when storage becomes unavailable after sending', async () => {
  vi.mocked(api.requestAutomaticReview).mockImplementation(async () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage lost') })
    throw duplicateReview('d'.repeat(32))
  })
  vi.mocked(api.getAutomaticReview).mockResolvedValue(receipt('d'.repeat(32)))
  render(<PracticalAssessment {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('could not preserve its reference for reopening')
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' }))
  await screen.findByRole('heading', { name: 'Revision needed' })
  expect(api.requestAutomaticReview).toHaveBeenCalledOnce()
})

it('distinguishes an explicit assessment request from its later read-only status check', async () => {
  let resolve!: (value: SavedAutomaticReview) => void
  vi.mocked(api.requestAutomaticReview).mockReturnValue(new Promise(done => { resolve = done }))
  render(<PracticalAssessment {...props} />)
  fireEvent.click(screen.getByRole('button', { name: 'Assess saved work automatically' }))
  expect(screen.getByRole('status')).toHaveTextContent('Requesting automatic assessment')
  const id = vi.mocked(api.requestAutomaticReview).mock.calls[0][2]
  await act(async () => resolve(receipt(id)))
  vi.mocked(api.getAutomaticReview).mockReturnValue(new Promise(done => { resolve = done }))
  fireEvent.click(screen.getByRole('button', { name: 'Check saved assessment' }))
  expect(screen.getByRole('status')).toHaveTextContent('Checking the saved assessment')
  expect(api.requestAutomaticReview).toHaveBeenCalledOnce()
  await act(async () => resolve(receipt(id)))
})
