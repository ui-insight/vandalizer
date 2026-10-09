import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/certification'
import { ApiError } from '../../api/client'
import { ProcessDesign } from './ProcessDesign'
import type { ProcessCaseDefinition, ProcessSubmissionBody, ProcessSubmissionList, SavedProcessSubmission } from '../../types/certification'

vi.mock('../../api/certification', () => ({ getProcessDesigns: vi.fn(), saveProcessDesign: vi.fn(), getProcessDesign: vi.fn() }))
vi.mock('./PracticalAssessment', () => ({ PracticalAssessment: ({ processSubmissionId }: { processSubmissionId: string }) => <div>Assess only design {processSubmissionId}</div> }))
vi.mock('./SavedAutomaticReviews', () => ({ SavedAutomaticReviews: () => <div>Read saved feedback</div> }))
const definition: ProcessCaseDefinition = { id: 'monthly-map', revision: 1, module_id: 'process_mapping', case_sha256: 'a'.repeat(64),
  provenance: 'authored_fictional_design_case_not_execution', notice: 'Fictional case; no personal work is required.', task: 'Choose a method and correct the proposed process.',
  assigned_inputs: [{ id: 'report-a', description: 'Assigned fictional report.' }], intended_output: 'Internal comparison draft.', repetition: 'Monthly review.', authority: 'Reviewer decides before release.',
  exclusions: ['No external sends.'], exception_conditions: ['Missing evidence.'], flawed_proposal: 'Send before asking the reviewer.',
  method_comparisons: [{ id: 'one-off', situation: 'One source-grounded question.' }], method_options: ['chat', 'workflow'],
  questions: [{ id: 'method_choice', outcome_id: 'process_mapping.method_choice', prompt: 'Explain the selected working method.', response_kind: 'method_and_rationale' },
    { id: 'human_checkpoint', outcome_id: 'process_mapping.human_checkpoint', prompt: 'Correct the ordered map and review point.', response_kind: 'ordered_process_map' },
    { id: 'bounded_scope', outcome_id: 'process_mapping.bounded_scope', prompt: 'Define inputs, output and exclusions.', response_kind: 'bounded_task_brief' }] }
const listing: ProcessSubmissionList = { enrollment_id: 'enrollment', module_id: 'process_mapping', course_version: 'course', manifest_sha256: 'b'.repeat(64),
  case: definition, submissions: [], older_submissions_available: false, can_submit: true, read_only_reason: null }
const props = { enrollmentId: 'enrollment', definition }
function receipt(body: ProcessSubmissionBody): SavedProcessSubmission {
  return { uuid: body.request_id, enrollment_id: 'enrollment', module_id: 'process_mapping', course_version: 'course', manifest_sha256: 'b'.repeat(64),
    case: definition, submission: body, submitted_at: '2026-10-06T12:00:00Z', submission_channel: 'authenticated_learner_process_request', credit_awarded: false, module_completion_eligible: false }
}
const answers = { method_choice: 'A bounded workflow fits monthly review.', human_checkpoint: '<b>Reviewer checks evidence before release.</b>', bounded_scope: 'Use only assigned reports; do not send externally.' }
async function fill() {
  fireEvent.change(await screen.findByLabelText('Working method and rationale'), { target: { value: answers.method_choice } })
  fireEvent.change(screen.getByLabelText('Corrected process map'), { target: { value: answers.human_checkpoint } })
  fireEvent.change(screen.getByLabelText('Bounded task brief'), { target: { value: answers.bounded_scope } })
}
beforeEach(() => {
  vi.resetAllMocks(); sessionStorage.clear()
  vi.mocked(api.getProcessDesigns).mockResolvedValue(listing)
  vi.mocked(api.saveProcessDesign).mockImplementation(async (_e, body) => receipt(body))
})

it('shows the fictional task before saving, preserves decisions literally and focuses the saved map', async () => {
  render(<ProcessDesign {...props} />)
  expect(await screen.findByRole('region', { name: 'Assigned process case' })).toHaveTextContent(definition.notice)
  expect(api.saveProcessDesign).not.toHaveBeenCalled()
  await fill(); fireEvent.click(screen.getByRole('button', { name: 'Save my reviewed design' }))
  const saved = await screen.findByRole('region', { name: 'Saved process design' })
  await waitFor(() => expect(saved).toHaveFocus())
  expect(within(saved).getByRole('region', { name: 'Saved corrected process map' })).toHaveTextContent(answers.human_checkpoint)
  expect(within(saved).getByRole('region', { name: 'Saved corrected process map' }).querySelector('b')).toBeNull()
  expect(api.saveProcessDesign).toHaveBeenCalledWith('enrollment', expect.objectContaining({ case_sha256: definition.case_sha256, consent: 'save_reviewed_process_design', answers, previous_submission_id: null }))
  expect(screen.getByText(/Assess only design/)).toBeInTheDocument()
})

it('restores a pending request and recovers only its exact saved answers after remount', async () => {
  let original!: ProcessSubmissionBody
  vi.mocked(api.saveProcessDesign).mockImplementation(async (_e, body) => { original = body; throw new Error('Lost reply') })
  const first = render(<ProcessDesign {...props} />)
  await fill(); fireEvent.click(screen.getByRole('button', { name: 'Save my reviewed design' }))
  await screen.findByRole('alert'); first.unmount()
  render(<ProcessDesign {...props} />)
  expect(await screen.findByLabelText('Corrected process map')).toHaveValue(answers.human_checkpoint)
  expect(screen.getByLabelText('Corrected process map')).toBeDisabled()
  vi.mocked(api.getProcessDesign).mockResolvedValue(receipt(original))
  fireEvent.click(screen.getByRole('button', { name: 'Check saved design' }))
  await screen.findByText('Design saved')
  expect(api.saveProcessDesign).toHaveBeenCalledOnce()
  expect(api.getProcessDesign).toHaveBeenCalledWith('enrollment', original.request_id)
})

it('finishes the same request only after history confirms no receipt', async () => {
  vi.mocked(api.saveProcessDesign).mockRejectedValueOnce(new Error('Lost reply'))
  vi.mocked(api.getProcessDesign).mockRejectedValue(new ApiError(404, 'Not found'))
  render(<ProcessDesign {...props} />)
  await fill(); fireEvent.click(screen.getByRole('button', { name: 'Save my reviewed design' }))
  await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button', { name: 'Check saved design' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Finish original design request' }))
  await screen.findByText('Design saved')
  expect(vi.mocked(api.saveProcessDesign).mock.calls[1]).toEqual(vi.mocked(api.saveProcessDesign).mock.calls[0])
})

it('keeps a rejected unsaved draft editable without awarding or retrying automatically', async () => {
  vi.mocked(api.saveProcessDesign).mockRejectedValueOnce(new ApiError(422, 'Missing answer'))
  render(<ProcessDesign {...props} />)
  await fill(); fireEvent.click(screen.getByRole('button', { name: 'Save my reviewed design' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('not saved')
  expect(screen.getByLabelText('Corrected process map')).toBeEnabled()
  expect(screen.getByLabelText('Corrected process map')).toHaveValue(answers.human_checkpoint)
  expect(api.saveProcessDesign).toHaveBeenCalledOnce()
})

it.each(['enrollment', 'case', 'answers', 'credit', 'manifest'])('rejects a mismatched %s receipt and preserves the request', async change => {
  vi.mocked(api.saveProcessDesign).mockImplementation(async (_e, body) => {
    const value = receipt(body)
    if (change === 'enrollment') value.enrollment_id = 'other-course'
    if (change === 'case') value.case = { ...definition, case_sha256: 'f'.repeat(64) }
    if (change === 'answers') value.submission = { ...body, answers: { ...body.answers, human_checkpoint: 'Different map.' } }
    if (change === 'credit') Object.assign(value, { credit_awarded: true })
    if (change === 'manifest') value.manifest_sha256 = 'f'.repeat(64)
    return value
  })
  render(<ProcessDesign {...props} />)
  await fill(); fireEvent.click(screen.getByRole('button', { name: 'Save my reviewed design' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('could not confirm')
  expect(screen.queryByText('Design saved')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Check saved design' })).toBeEnabled()
})

it('creates a linked revision without mutating the original saved design', async () => {
  render(<ProcessDesign {...props} />)
  await fill(); fireEvent.click(screen.getByRole('button', { name: 'Save my reviewed design' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Revise this design' }))
  expect(screen.getByRole('form', { name: 'Your process design' })).toHaveFocus()
  const original = vi.mocked(api.saveProcessDesign).mock.calls[0][1]
  fireEvent.change(screen.getByLabelText('Corrected process map'), { target: { value: 'A revised map with preserved source references.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save my reviewed design' }))
  await screen.findByText('Design saved')
  const revised = vi.mocked(api.saveProcessDesign).mock.calls[1][1]
  expect(revised.request_id).not.toBe(original.request_id)
  expect(revised.previous_submission_id).toBe(original.request_id)
  expect(original.answers.human_checkpoint).toBe(answers.human_checkpoint)
})

it('restores an unsent draft independently of server history', async () => {
  const first = render(<ProcessDesign {...props} />)
  await fill(); first.unmount()
  render(<ProcessDesign {...props} />)
  expect(await screen.findByLabelText('Corrected process map')).toHaveValue(answers.human_checkpoint)
  expect(api.saveProcessDesign).not.toHaveBeenCalled()
})

it('preserves read-only history even when the server reports a writable selected course', async () => {
  const body: ProcessSubmissionBody = { request_id: 'c'.repeat(32), case_sha256: definition.case_sha256, answers, consent: 'save_reviewed_process_design', previous_submission_id: null }
  vi.mocked(api.getProcessDesigns).mockResolvedValue({ ...listing, submissions: [{ submission_id: body.request_id, submitted_at: '2026-10-06', previous_submission_id: null }] })
  vi.mocked(api.getProcessDesign).mockResolvedValue(receipt(body))
  render(<ProcessDesign {...props} historyOnly />)
  fireEvent.change(await screen.findByLabelText('Saved process design'), { target: { value: body.request_id } })
  await screen.findByText('Design saved')
  expect(screen.queryByRole('button', { name: 'Revise this design' })).not.toBeInTheDocument()
  expect(screen.queryByText(/Assess only design/)).not.toBeInTheDocument()
  expect(screen.queryByRole('form', { name: 'Your process design' })).not.toBeInTheDocument()
  expect(api.saveProcessDesign).not.toHaveBeenCalled()
})

it('rejects a different course listing before offering a save form', async () => {
  vi.mocked(api.getProcessDesigns).mockResolvedValue({ ...listing, enrollment_id: 'different-course' })
  render(<ProcessDesign {...props} />)
  await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: 'Save my reviewed design' })).not.toBeInTheDocument()
})

it('keeps separate authored drafts when leaving for another enrollment and returning', async () => {
  let view = render(<ProcessDesign {...props} />)
  await fill(); view.unmount()
  vi.mocked(api.getProcessDesigns).mockResolvedValue({ ...listing, enrollment_id: 'other-enrollment' })
  view = render(<ProcessDesign {...props} enrollmentId="other-enrollment" />)
  expect(await screen.findByLabelText('Corrected process map')).toHaveValue('')
  fireEvent.change(screen.getByLabelText('Corrected process map'), { target: { value: 'Separate new-course process draft' } })
  view.unmount()
  vi.mocked(api.getProcessDesigns).mockResolvedValue(listing)
  render(<ProcessDesign {...props} />)
  expect(await screen.findByLabelText('Corrected process map')).toHaveValue(answers.human_checkpoint)
  expect(api.saveProcessDesign).not.toHaveBeenCalled()
})
it('shows unavailable draft storage without losing the current process explanation', async () => {
  render(<ProcessDesign {...props} />)
  await screen.findByLabelText('Corrected process map')
  const fail = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Storage blocked') })
  try {
    fireEvent.change(screen.getByLabelText('Corrected process map'), { target: { value: 'My unsaved process explanation remains editable.' } })
    expect(screen.getByLabelText('Corrected process map')).toHaveValue('My unsaved process explanation remains editable.')
    expect(screen.getByRole('status')).toHaveTextContent('Keep this form open')
    expect(api.saveProcessDesign).not.toHaveBeenCalled()
  } finally { fail.mockRestore() }
})


it('distinguishes saving from a read-only recovery check and preserves the original request', async () => {
  let rejectSave!: (error: Error) => void, resolveCheck!: (value: SavedProcessSubmission) => void
  vi.mocked(api.saveProcessDesign).mockImplementation(() => new Promise((_resolve, reject) => { rejectSave = reject }))
  vi.mocked(api.getProcessDesign).mockImplementation(() => new Promise(resolve => { resolveCheck = resolve }))
  render(<ProcessDesign {...props} />); await fill()
  fireEvent.click(screen.getByRole('button', { name: 'Save my reviewed design' }))
  expect(screen.getByText(/Sending the process design request/)).toHaveAttribute('role', 'status')
  expect(screen.getByText(/Closing this panel does not confirm/)).toBeInTheDocument()
  const original = vi.mocked(api.saveProcessDesign).mock.calls[0][1]
  await act(async () => rejectSave(new Error('Lost reply')))
  fireEvent.click(screen.getByRole('button', { name: 'Check saved design' }))
  expect(screen.getByText(/Checking the saved state/)).toHaveAttribute('role', 'status')
  expect(screen.getByText('This check does not start, repeat or grade work.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Check saved design' })).toBeDisabled()
  await act(async () => resolveCheck(receipt(original)))
  expect(await screen.findByText('Design saved')).toBeInTheDocument()
  expect(screen.queryByText(/Checking the saved state/)).not.toBeInTheDocument()
  expect(api.saveProcessDesign).toHaveBeenCalledOnce()
  expect(api.getProcessDesign).toHaveBeenCalledWith('enrollment', original.request_id)
})
