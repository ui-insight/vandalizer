import type { ContextType } from 'react'
import { AuthContext } from '../../contexts/AuthContext'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/certification'
import { ApiError } from '../../api/client'
import { WorkflowDesign } from './WorkflowDesign'
import type { WorkflowDesignCaseDefinition, WorkflowDesignList, WorkflowDesignCaptureBody, SavedWorkflowDesignCapture, WorkflowDesignSubmissionBody, SavedWorkflowDesignSubmission } from '../../types/certification'

vi.mock('../../api/certification', () => ({ getWorkflowDesigns: vi.fn(), captureWorkflowDesign: vi.fn(), getWorkflowDesignCapture: vi.fn(), approveWorkflowDesign: vi.fn(), getWorkflowDesign: vi.fn() }))
vi.mock('./PracticalAssessment', () => ({ PracticalAssessment: ({ workflowDesignSubmissionId }: { workflowDesignSubmissionId: string }) => <div>Assess approved design {workflowDesignSubmissionId}</div> }))
vi.mock('./SavedAutomaticReviews', () => ({ SavedAutomaticReviews: () => <div>Read saved feedback</div> }))
const definition: WorkflowDesignCaseDefinition = { id: 'workflow-case', revision: 1, module_id: 'workflow_design', case_sha256: 'a'.repeat(64),
  provenance: 'authored_workflow_design_case_not_execution', notice: 'Fictional design, not execution.', task: 'Inspect the saved configuration and correct its boundary.',
  assigned_inputs: [{ id: 'report-a', description: 'A fictional assigned report.' }], intended_output: 'Internal draft.', exclusions: ['No sending.'],
  supplied_map: { id: 'example', provenance: 'authored_example_not_learner_work', method_and_rationale: 'A bounded workflow.', ordered_process_map: 'Sources → internal draft → human review.', bounded_task_brief: 'Only assigned sources; stop on unsupported claims.' },
  flawed_proposal: 'Send the report before review.', configuration_instructions: ['Inspect the saved settings.'],
  questions: [{ id: 'data_flow', outcome_id: 'workflow_design.data_flow', prompt: 'Trace actual input and output settings.', response_kind: 'trace_saved_configuration' },
    { id: 'approval_boundary', outcome_id: 'workflow_design.approval_boundary', prompt: 'Explain the correction before approval.', response_kind: 'correct_then_approve_design' },
    { id: 'reviewable_design', outcome_id: 'workflow_design.reviewable_design', prompt: 'Explain the review and stop path.', response_kind: 'explain_review_and_stop_path' }] }
const listing: WorkflowDesignList = { enrollment_id: 'enrollment', module_id: 'workflow_design', course_version: 'draft', manifest_sha256: 'b'.repeat(64), case: definition,
  submissions: [], older_submissions_available: false, workflows: [{ workflow_id: 'c'.repeat(24), name: 'My comparison', version: 1 }], older_workflows_available: false,
  process_choices: [], older_process_choices_available: false, can_submit: true, read_only_reason: null }
const props = { enrollmentId: 'enrollment', definition }
let currentCapture: SavedWorkflowDesignCapture
function captured(body: WorkflowDesignCaptureBody): SavedWorkflowDesignCapture {
  return { uuid: body.request_id, enrollment_id: 'enrollment', module_id: 'workflow_design', course_version: 'draft', manifest_sha256: listing.manifest_sha256,
    input_snapshot_sha256: 'd'.repeat(64), artifact_id: body.workflow_id, artifact_sha256: 'e'.repeat(64), request: body, case: definition,
    handoff: { kind: 'supplied_example', supplied_map: definition.supplied_map },
    artifact: { workflow: { id: body.workflow_id, name: 'My comparison', version: 1, input_config: {}, output_config: {}, resource_config: {}, config_override: null },
      steps: [{ step: { id: 'step', name: 'Compare', is_output: true, data: {} }, tasks: [{ id: 'task', name: 'Prompt', data: { prompt: '<b>Preserve unresolved evidence</b>', input_sources: ['workflow_documents'] } }] }], referenced_extraction_sets: {} },
    credit_awarded: false, module_completion_eligible: false, execution_status: 'not_started' }
}
function approved(body: WorkflowDesignSubmissionBody): SavedWorkflowDesignSubmission {
  return { uuid: body.request_id, enrollment_id: 'enrollment', module_id: 'workflow_design', course_version: 'draft', manifest_sha256: listing.manifest_sha256,
    input_snapshot: currentCapture, submission: body, submitted_at: '2026-10-06', submission_channel: 'authenticated_learner_workflow_design_request',
    credit_awarded: false, module_completion_eligible: false, execution_authorized: false }
}
async function capture() {
  fireEvent.change(await screen.findByLabelText('Saved workflow'), { target: { value: 'c'.repeat(24) } })
  fireEvent.click(screen.getByRole('button', { name: 'Capture selected revision' }))
  await screen.findByRole('region', { name: 'Captured workflow configuration' })
}
async function fill() {
  fireEvent.change(await screen.findByLabelText('Trace the saved data flow'), { target: { value: 'The saved prompt consumes workflow documents.' } })
  fireEvent.change(screen.getByLabelText('Correction and approval boundary'), { target: { value: '<b>No external release is approved.</b>' } })
  fireEvent.change(screen.getByLabelText('Evidence and review path'), { target: { value: 'Preserve evidence and unresolved issues for review.' } })
}
beforeEach(() => {
  vi.resetAllMocks(); sessionStorage.clear()
  vi.mocked(api.getWorkflowDesigns).mockResolvedValue(structuredClone(listing))
  vi.mocked(api.captureWorkflowDesign).mockImplementation(async (_e, body) => { currentCapture = captured(body); return currentCapture })
  vi.mocked(api.getWorkflowDesignCapture).mockImplementation(async () => currentCapture)
  vi.mocked(api.approveWorkflowDesign).mockImplementation(async (_e, body) => approved(body))
})

it('requires capture before approval and preserves literal settings and decisions', async () => {
  render(<WorkflowDesign {...props} />)
  await screen.findByRole('region', { name: 'Assigned workflow design case' })
  expect(screen.queryByRole('button', { name: 'Approve this saved revision' })).not.toBeInTheDocument()
  await capture()
  const settings = screen.getByRole('region', { name: 'Captured settings for Compare', hidden: true })
  expect(settings).toHaveTextContent('<b>Preserve unresolved evidence</b>'); expect(settings.querySelector('b')).toBeNull()
  await fill(); fireEvent.click(screen.getByRole('button', { name: 'Approve this saved revision' }))
  const receipt = await screen.findByRole('region', { name: 'Saved workflow approval' })
  await waitFor(() => expect(receipt).toHaveFocus())
  expect(within(receipt).getByRole('region', { name: 'Saved correction and approval boundary' })).toHaveTextContent('<b>No external release is approved.</b>')
  expect(api.approveWorkflowDesign).toHaveBeenCalledWith('enrollment', expect.objectContaining({ input_snapshot_id: currentCapture.uuid, input_snapshot_sha256: currentCapture.input_snapshot_sha256, consent: 'approve_saved_workflow_design_for_assessment' }))
})
it('links the selected owned workflow without capturing or approving it', async () => {
  render(<WorkflowDesign {...props} />)
  fireEvent.change(await screen.findByLabelText('Saved workflow'), { target: { value: 'c'.repeat(24) } })
  const link = screen.getByRole('link', { name: 'Open selected workflow in a new tab' })
  expect(new URL(link.getAttribute('href')!, 'https://local.invalid').searchParams.get('workflow')).toBe('c'.repeat(24))
  expect(api.captureWorkflowDesign).not.toHaveBeenCalled()
  expect(api.approveWorkflowDesign).not.toHaveBeenCalled()
})
it('recovers a lost capture using GET without a second POST', async () => {
  vi.mocked(api.captureWorkflowDesign).mockImplementation(async (_e, body) => { currentCapture = captured(body); throw new Error('Lost response') })
  render(<WorkflowDesign {...props} />)
  fireEvent.change(await screen.findByLabelText('Saved workflow'), { target: { value: 'c'.repeat(24) } })
  fireEvent.click(screen.getByRole('button', { name: 'Capture selected revision' })); await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button', { name: 'Check saved capture' }))
  await screen.findByRole('region', { name: 'Captured workflow configuration' })
  expect(api.captureWorkflowDesign).toHaveBeenCalledOnce(); expect(api.getWorkflowDesignCapture).toHaveBeenCalledWith('enrollment', currentCapture.uuid)
})
it('blocks approval of an older capture while a newer capture is unresolved', async () => {
  render(<WorkflowDesign {...props} />); await capture(); await fill()
  vi.mocked(api.captureWorkflowDesign).mockRejectedValueOnce(new Error('Lost response'))
  fireEvent.click(screen.getByRole('button', { name: 'Capture selected revision' })); await screen.findByRole('alert')
  expect(screen.getByRole('button', { name: 'Approve this saved revision' })).toBeDisabled(); expect(api.approveWorkflowDesign).not.toHaveBeenCalled()
})
it('can capture an older workflow and map by reference without an invalid required selection', async () => {
  vi.mocked(api.getWorkflowDesigns).mockResolvedValue({ ...listing, older_workflows_available: true, older_process_choices_available: true })
  vi.mocked(api.captureWorkflowDesign).mockImplementation(async (_e, body) => {
    currentCapture = { ...captured(body), handoff: { kind: 'owned_saved_process_submission' } }
    return currentCapture
  })
  render(<WorkflowDesign {...props} />)
  fireEvent.change(await screen.findByLabelText('Older workflow reference'), { target: { value: 'f'.repeat(24) } })
  fireEvent.change(screen.getByLabelText('Older process map reference'), { target: { value: 'e'.repeat(32) } })
  expect((screen.getByLabelText('Saved workflow') as HTMLSelectElement).checkValidity()).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: 'Capture selected revision' }))
  await screen.findByRole('region', { name: 'Captured workflow configuration' })
  expect(api.captureWorkflowDesign).toHaveBeenCalledWith('enrollment', expect.objectContaining({ workflow_id: 'f'.repeat(24), handoff: 'owned_saved_process_submission', process_submission_id: 'e'.repeat(32) }))
})
it('recovers a lost approval across remount without recollecting or resubmitting', async () => {
  let saved: SavedWorkflowDesignSubmission
  vi.mocked(api.approveWorkflowDesign).mockImplementation(async (_e, body) => { saved = approved(body); throw new Error('Lost reply') })
  vi.mocked(api.getWorkflowDesign).mockImplementation(async () => saved!)
  const first = render(<WorkflowDesign {...props} />); await capture(); await fill()
  fireEvent.click(screen.getByRole('button', { name: 'Approve this saved revision' })); await screen.findByRole('alert'); first.unmount()
  render(<WorkflowDesign {...props} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Check saved approval' })); await screen.findByRole('region', { name: 'Saved workflow approval' })
  expect(api.approveWorkflowDesign).toHaveBeenCalledOnce(); expect(api.captureWorkflowDesign).toHaveBeenCalledOnce()
})
it.each(['snapshot', 'execution', 'manifest', 'answer'])('rejects a mismatched %s approval receipt', async change => {
  vi.mocked(api.approveWorkflowDesign).mockImplementation(async (_e, body) => {
    const result = structuredClone(approved(body))
    if (change === 'snapshot') result.submission.input_snapshot_id = 'f'.repeat(32)
    else if (change === 'execution') Object.assign(result, { execution_authorized: true })
    else if (change === 'manifest') result.manifest_sha256 = 'f'.repeat(64)
    else result.submission.answers.data_flow = 'Different answer'
    return result
  })
  render(<WorkflowDesign {...props} />); await capture(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Approve this saved revision' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('could not confirm')
  expect(screen.queryByRole('region', { name: 'Saved workflow approval' })).not.toBeInTheDocument()
})
it('keeps original history read-only even if the listing says writable', async () => {
  currentCapture = captured({ request_id: 'a'.repeat(32), workflow_id: 'c'.repeat(24), case_sha256: definition.case_sha256, handoff: 'supplied_example', process_submission_id: null, consent: 'capture_saved_workflow_design' })
  const body: WorkflowDesignSubmissionBody = { request_id: 'b'.repeat(32), input_snapshot_id: currentCapture.uuid, input_snapshot_sha256: currentCapture.input_snapshot_sha256, case_sha256: definition.case_sha256,
    answers: { data_flow: 'Original data flow', approval_boundary: 'No external action', reviewable_design: 'Preserve sources' }, previous_submission_id: null, consent: 'approve_saved_workflow_design_for_assessment' }
  const saved = approved(body)
  vi.mocked(api.getWorkflowDesigns).mockResolvedValue({ ...listing, submissions: [{ submission_id: saved.uuid, submitted_at: saved.submitted_at, previous_submission_id: null, input_snapshot_id: currentCapture.uuid, workflow_name: 'My comparison' }] })
  vi.mocked(api.getWorkflowDesign).mockResolvedValue(saved)
  render(<WorkflowDesign {...props} historyOnly />)
  fireEvent.change(await screen.findByLabelText('Saved workflow approval'), { target: { value: saved.uuid } }); await screen.findByRole('region', { name: 'Saved workflow approval' })
  expect(screen.queryByRole('button', { name: 'Capture selected revision' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Revise these decisions' })).not.toBeInTheDocument()
  expect(screen.queryByText(/Assess approved design/)).not.toBeInTheDocument()
  expect(api.captureWorkflowDesign).not.toHaveBeenCalled(); expect(api.approveWorkflowDesign).not.toHaveBeenCalled()
})
it('finishes only the original approval after confirmed absence', async () => {
  let savedBody: WorkflowDesignSubmissionBody
  vi.mocked(api.approveWorkflowDesign).mockImplementationOnce(async (_e, body) => { savedBody = body; throw new Error('Unconfirmed') }).mockImplementation(async (_e, body) => approved(body))
  vi.mocked(api.getWorkflowDesign).mockRejectedValue(new ApiError(404, 'Not saved'))
  render(<WorkflowDesign {...props} />); await capture(); await fill()
  fireEvent.click(screen.getByRole('button', { name: 'Approve this saved revision' })); await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button', { name: 'Check saved approval' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Finish original approval request' })); await screen.findByRole('region', { name: 'Saved workflow approval' })
  expect(vi.mocked(api.approveWorkflowDesign).mock.calls[1][1]).toEqual(savedBody!)
})

it('does not carry approval explanations into a newly captured workflow revision', async () => {
  const auth = { user: { user_id: 'workflow-draft-learner' } } as NonNullable<ContextType<typeof AuthContext>>
  const node = <AuthContext.Provider value={auth}><WorkflowDesign {...props} /></AuthContext.Provider>
  let view = render(node)
  await capture(); await fill()
  const firstId = currentCapture.uuid
  view.unmount(); view = render(node)
  expect(await screen.findByLabelText('Trace the saved data flow')).toHaveValue('The saved prompt consumes workflow documents.')
  await capture()
  expect(currentCapture.uuid).not.toBe(firstId)
  expect(screen.getByLabelText('Trace the saved data flow')).toHaveValue('')
  expect(screen.getByLabelText('Correction and approval boundary')).toHaveValue('')
  expect(api.approveWorkflowDesign).not.toHaveBeenCalled()
})

it('restores an unfinished linked revision after reopening its original saved approval', async () => {
  const auth = { user: { user_id: 'workflow-revision-learner' } } as NonNullable<ContextType<typeof AuthContext>>
  const node = <AuthContext.Provider value={auth}><WorkflowDesign {...props} /></AuthContext.Provider>
  let view = render(node)
  await capture(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Approve this saved revision' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Revise these decisions' }))
  const body = structuredClone(vi.mocked(api.approveWorkflowDesign).mock.calls[0][1]), receipt = approved(body)
  fireEvent.change(screen.getByLabelText('Trace the saved data flow'), { target: { value: 'My unfinished linked revision of this original saved design.' } })
  view.unmount()
  vi.mocked(api.getWorkflowDesigns).mockResolvedValue({ ...listing, submissions: [{ submission_id: receipt.uuid, submitted_at: receipt.submitted_at, previous_submission_id: null, input_snapshot_id: currentCapture.uuid, workflow_name: 'My comparison' }] })
  vi.mocked(api.getWorkflowDesign).mockResolvedValue(receipt)
  view = render(node)
  fireEvent.change(await screen.findByLabelText('Saved workflow approval'), { target: { value: receipt.uuid } })
  fireEvent.click(await screen.findByRole('button', { name: 'Revise these decisions' }))
  expect(screen.getByLabelText('Trace the saved data flow')).toHaveValue('My unfinished linked revision of this original saved design.')
  expect(receipt.submission.answers.data_flow).toBe('The saved prompt consumes workflow documents.')
  expect(api.approveWorkflowDesign).toHaveBeenCalledTimes(1)
})


it('distinguishes capture and approval writes from their saved-state recovery checks', async () => {
  let rejectCapture!: (error: Error) => void, resolveCapture!: (value: SavedWorkflowDesignCapture) => void
  let rejectApproval!: (error: Error) => void, resolveApproval!: (value: SavedWorkflowDesignSubmission) => void
  vi.mocked(api.captureWorkflowDesign).mockImplementation((_e, body) => {
    currentCapture = captured(body)
    return new Promise((_resolve, reject) => { rejectCapture = reject })
  })
  vi.mocked(api.getWorkflowDesignCapture).mockImplementation(() => new Promise(resolve => { resolveCapture = resolve }))
  vi.mocked(api.approveWorkflowDesign).mockImplementation(() => new Promise((_resolve, reject) => { rejectApproval = reject }))
  vi.mocked(api.getWorkflowDesign).mockImplementation(() => new Promise(resolve => { resolveApproval = resolve }))
  render(<WorkflowDesign {...props} />)
  fireEvent.change(await screen.findByLabelText('Saved workflow'), { target: { value: 'c'.repeat(24) } })
  fireEvent.click(screen.getByRole('button', { name: 'Capture selected revision' }))
  expect(screen.getByText(/Sending the input capture request/)).toHaveAttribute('role', 'status')
  await act(async () => rejectCapture(new Error('Lost reply')))
  fireEvent.click(screen.getByRole('button', { name: 'Check saved capture' }))
  expect(screen.getByText(/Checking the saved state/)).toHaveAttribute('role', 'status')
  await act(async () => resolveCapture(currentCapture))
  await fill(); fireEvent.click(screen.getByRole('button', { name: 'Approve this saved revision' }))
  expect(screen.getByText(/Sending the workflow approval request/)).toHaveAttribute('role', 'status')
  const original = vi.mocked(api.approveWorkflowDesign).mock.calls[0][1]
  await act(async () => rejectApproval(new Error('Lost reply')))
  fireEvent.click(screen.getByRole('button', { name: 'Check saved approval' }))
  expect(screen.getByText(/Checking the saved state/)).toHaveAttribute('role', 'status')
  expect(screen.getByText('This check does not start, repeat or grade work.')).toBeInTheDocument()
  await act(async () => resolveApproval(approved(original)))
  expect(await screen.findByRole('region', { name: 'Saved workflow approval' })).toBeInTheDocument()
  expect(screen.queryByText(/Checking the saved state/)).not.toBeInTheDocument()
  expect(api.captureWorkflowDesign).toHaveBeenCalledOnce()
  expect(api.approveWorkflowDesign).toHaveBeenCalledOnce()
})
