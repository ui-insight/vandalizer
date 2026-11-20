import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/certification'
import { ApiError } from '../../api/client'
import { PracticalReview } from './PracticalReview'
import type { PracticalDecisionBody, PracticalDecisionContext, PracticalDecisionPrompt, SavedPracticalDecision } from '../../types/certification'

vi.mock('../../api/certification', () => ({ getPracticalRuns: vi.fn(), getPracticalDecisionContext: vi.fn(), submitPracticalDecision: vi.fn(), getPracticalDecision: vi.fn(), getPracticalExecution: vi.fn(), executePracticalRun: vi.fn(), getAutomaticReviews: vi.fn(), getAutomaticReview: vi.fn() }))
const runId = 'a'.repeat(32)
const prompt: PracticalDecisionPrompt = { id: 'scope_review', revision: 1, module_id: 'foundations', outcome_id: 'foundations.scoped_proposal',
  phase: 'before_execution', question: 'Does this saved source and extraction match the assigned task?', choices: { approve: 'Ready to run', revise: 'Needs correction' }, required_fields: [], prompt_sha256: 'b'.repeat(64) }
const context: PracticalDecisionContext = { enrollment_id: 'enrollment', module_id: 'foundations', prompt, run_id: runId, run_state: 'prepared', can_submit: true,
  lab_folder_id: 'training-folder', artifact: { title: 'Saved NSF extraction', fields: [{ searchphrase: 'PI Name', is_optional: false }] },
  documents: [{ document_id: 'source', title: 'Assigned proposal', text: 'PI Name: Jane. This is the saved source.' }], result: null, latest_decision: null }
const props = { enrollmentId: 'enrollment', moduleId: 'foundations', prompts: [prompt] }
function receipt(body: PracticalDecisionBody): SavedPracticalDecision {
  return { uuid: body.request_id, enrollment_id: 'enrollment', module_id: 'foundations', run_id: runId, prompt_id: prompt.id,
    prompt_sha256: prompt.prompt_sha256, submitted_at: '2026-10-05T12:00:00Z', submission: body, credit_awarded: false }
}
async function openRun() {
  fireEvent.change(await screen.findByLabelText('Saved run'), { target: { value: runId } })
  await screen.findByText('Saved NSF extraction')
}
function answer() {
  fireEvent.click(screen.getByLabelText('Ready to run'))
  fireEvent.change(screen.getByLabelText('Explain your decision'), { target: { value: 'I checked the assigned source and saved fields.' } })
}
beforeEach(() => {
  vi.resetAllMocks(); sessionStorage.clear()
  vi.mocked(api.getPracticalRuns).mockResolvedValue({ runs: [{ run_id: runId, state: 'prepared' }], older_runs_available: false })
  vi.mocked(api.getPracticalDecisionContext).mockResolvedValue(context)
  vi.mocked(api.submitPracticalDecision).mockImplementation(async (_enrollment, _module, _prompt, body) => receipt(body))
})

it('shows saved evidence and saves only the explicit learner decision', async () => {
  render(<PracticalReview {...props} />)
  await openRun(); answer()
  expect(api.submitPracticalDecision).not.toHaveBeenCalled()
  expect(screen.getByText('PI Name: Jane. This is the saved source.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Save my decision' }))
  expect(await screen.findByText('Decision saved')).toBeInTheDocument()
  expect(api.submitPracticalDecision).toHaveBeenCalledWith('enrollment', 'foundations', 'scope_review', expect.objectContaining({ run_id: runId, choice: 'approve', prompt_sha256: prompt.prompt_sha256 }))
  expect(screen.getByText(/It does not start a run or award a grade/)).toBeInTheDocument()
})

it('recovers a lost response after remount by reading the original receipt without sending again', async () => {
  let original!: PracticalDecisionBody
  vi.mocked(api.submitPracticalDecision).mockImplementation(async (_e, _m, _p, body) => { original = body; throw new Error('Lost response') })
  vi.mocked(api.getPracticalDecision).mockImplementation(async () => receipt(original))
  const first = render(<PracticalReview {...props} />)
  await openRun(); answer()
  fireEvent.click(screen.getByRole('button', { name: 'Save my decision' }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('Needs correction')).toBeDisabled()
  first.unmount()
  render(<PracticalReview {...props} />)
  await openRun()
  expect(api.submitPracticalDecision).toHaveBeenCalledOnce()
  expect(api.getPracticalDecision).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Check saved decision' }))
  await screen.findByText('Decision saved')
  expect(api.getPracticalDecision).toHaveBeenCalledWith(original.request_id)
  expect(api.submitPracticalDecision).toHaveBeenCalledOnce()
})

it('retries exactly the original request when history confirms no receipt exists', async () => {
  vi.mocked(api.submitPracticalDecision).mockRejectedValueOnce(new Error('Network failure'))
  vi.mocked(api.getPracticalDecision).mockRejectedValue(new ApiError(404, 'Not found'))
  render(<PracticalReview {...props} />)
  await openRun(); answer()
  fireEvent.click(screen.getByRole('button', { name: 'Save my decision' }))
  await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button', { name: 'Check saved decision' }))
  const retry = await screen.findByRole('button', { name: 'Retry original decision' })
  expect(api.submitPracticalDecision).toHaveBeenCalledOnce()
  expect(screen.getByLabelText('Needs correction')).toBeDisabled()
  fireEvent.click(retry)
  await screen.findByText('Decision saved')
  const calls = vi.mocked(api.submitPracticalDecision).mock.calls
  expect(calls[1]).toEqual(calls[0])
})

it('keeps a draft editable after a definite validation rejection', async () => {
  vi.mocked(api.submitPracticalDecision).mockRejectedValueOnce(new ApiError(422, 'Each source check must cite the saved assigned document'))
  render(<PracticalReview {...props} />)
  await openRun(); answer()
  fireEvent.click(screen.getByRole('button', { name: 'Save my decision' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Your decision was not saved')
  expect(screen.getByLabelText('Needs correction')).toBeEnabled()
  fireEvent.click(screen.getByLabelText('Needs correction'))
  fireEvent.click(screen.getByRole('button', { name: 'Save my decision' }))
  await screen.findByText('Decision saved')
  const calls = vi.mocked(api.submitPracticalDecision).mock.calls
  expect(calls[0][3].request_id).not.toEqual(calls[1][3].request_id)
})

it('does not transmit if session storage cannot preserve the request', async () => {
  const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Blocked') })
  render(<PracticalReview {...props} />)
  await openRun(); answer()
  fireEvent.click(screen.getByRole('button', { name: 'Save my decision' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('could not preserve')
  expect(api.submitPracticalDecision).not.toHaveBeenCalled()
  storage.mockRestore()
})

it('rejects context for a different course instead of presenting its source or form', async () => {
  vi.mocked(api.getPracticalDecisionContext).mockResolvedValue({ ...context, enrollment_id: 'other' })
  render(<PracticalReview {...props} />)
  fireEvent.change(await screen.findByLabelText('Saved run'), { target: { value: runId } })
  expect(await screen.findByRole('alert')).toHaveTextContent('different course requirements')
  expect(screen.queryByText('Saved NSF extraction')).not.toBeInTheDocument()
})

it('offers honest unresolved value checks and keeps failed or unfinished runs read only', async () => {
  const values = { ...prompt, id: 'value_review', phase: 'after_execution' as const, required_fields: ['PI Name'] }
  vi.mocked(api.getPracticalDecisionContext).mockResolvedValue({ ...context, prompt: values, can_submit: false, run_state: 'executing' })
  render(<PracticalReview {...props} prompts={[values]} />)
  await openRun()
  expect(screen.getByLabelText('Source check')).toHaveValue('unresolved')
  expect(screen.getByLabelText('Source check')).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Save my decision' })).toBeDisabled()
  expect(screen.getByText(/Value review becomes available after/)).toBeInTheDocument()
})

it('preserves unsent edits instead of replacing them with previously saved history', async () => {
  const first = render(<PracticalReview {...props} />)
  await openRun(); answer(); first.unmount()
  const previous = receipt({ request_id: 'c'.repeat(32), run_id: runId, prompt_sha256: prompt.prompt_sha256, choice: 'revise', reason: 'Earlier saved explanation.', value_checks: [] })
  vi.mocked(api.getPracticalDecisionContext).mockResolvedValue({ ...context, latest_decision: previous })
  render(<PracticalReview {...props} />)
  await openRun()
  expect(screen.getByLabelText('Ready to run')).toBeChecked()
  expect(screen.getByLabelText('Explain your decision')).toHaveValue('I checked the assigned source and saved fields.')
  expect(within(screen.getByLabelText('Saved practical decision')).getByText('Earlier saved explanation.')).toBeInTheDocument()
})

it('isolates browser drafts by run and prompt revision', async () => {
  const first = render(<PracticalReview {...props} />)
  await openRun(); answer(); first.unmount()
  const next = { ...prompt, prompt_sha256: 'd'.repeat(64) }
  vi.mocked(api.getPracticalDecisionContext).mockResolvedValue({ ...context, prompt: next })
  render(<PracticalReview {...props} prompts={[next]} />)
  await openRun()
  expect(screen.getByLabelText('Ready to run')).not.toBeChecked()
  expect(screen.getByLabelText('Explain your decision')).toHaveValue('')
})

it('does not dispatch again when receipt lookup itself is unavailable', async () => {
  vi.mocked(api.submitPracticalDecision).mockRejectedValueOnce(new Error('Lost response'))
  vi.mocked(api.getPracticalDecision).mockRejectedValue(new ApiError(503, 'Unavailable'))
  render(<PracticalReview {...props} />)
  await openRun(); answer()
  fireEvent.click(screen.getByRole('button', { name: 'Save my decision' }))
  await screen.findByRole('alert')
  fireEvent.click(screen.getByRole('button', { name: 'Check saved decision' }))
  await waitFor(() => expect(api.getPracticalDecision).toHaveBeenCalledOnce())
  expect(api.submitPracticalDecision).toHaveBeenCalledOnce()
})

it('keeps a context error visible when a slower run-list refresh succeeds', async () => {
  let resolveRuns!: (value: Awaited<ReturnType<typeof api.getPracticalRuns>>) => void
  render(<PracticalReview {...props} />)
  await openRun()
  vi.mocked(api.getPracticalRuns).mockReturnValueOnce(new Promise(resolve => { resolveRuns = resolve }))
  vi.mocked(api.getPracticalDecisionContext).mockRejectedValueOnce(new Error('Context unavailable'))
  fireEvent.click(screen.getByRole('button', { name: 'Reload saved runs' }))
  await screen.findByRole('alert')
  resolveRuns({ runs: [{ run_id: runId, state: 'prepared' }], older_runs_available: false })
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('could not be opened'))
})

const proposal = { case: { task: 'Extract the required values from the assigned NSF proposal in your saved lab.' },
  proposal_sha256: 'e'.repeat(64), original_source_id: 'unrelated',
  source_options: [{ id: 'unrelated', title: 'NIH unrelated proposal.pdf' }, { id: 'source', title: 'Assigned NSF proposal.pdf' }] }

it('requires an explicit proposal source and preserves the correction in saved history', async () => {
  vi.mocked(api.getPracticalDecisionContext).mockResolvedValue({ ...context, scope_proposal: proposal })
  render(<PracticalReview {...props} />)
  await openRun(); answer()
  const selection = screen.getByLabelText('Source I would authorize')
  expect(selection).toHaveValue('')
  expect(selection).toBeRequired()
  expect(screen.getByLabelText('Original scope proposal')).toHaveTextContent('NIH unrelated proposal.pdf')
  fireEvent.click(screen.getByRole('button', { name: 'Save my decision' }))
  expect(api.submitPracticalDecision).not.toHaveBeenCalled()
  fireEvent.change(selection, { target: { value: 'source' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save my decision' }))
  await screen.findByText('Decision saved')
  expect(api.submitPracticalDecision).toHaveBeenCalledWith('enrollment', 'foundations', 'scope_review',
    expect.objectContaining({ proposal_selection: { proposal_sha256: proposal.proposal_sha256, source_id: 'source' } }))
  expect(screen.getByLabelText('Saved practical decision')).toHaveTextContent('Your recorded source: Assigned NSF proposal.pdf')
})

it('restores an unconfirmed source correction and rejects a receipt with a different selection', async () => {
  vi.mocked(api.getPracticalDecisionContext).mockResolvedValue({ ...context, scope_proposal: proposal })
  let original!: PracticalDecisionBody
  vi.mocked(api.submitPracticalDecision).mockImplementation(async (_e, _m, _p, body) => { original = body; throw new Error('Lost response') })
  const first = render(<PracticalReview {...props} />)
  await openRun(); answer()
  fireEvent.change(screen.getByLabelText('Source I would authorize'), { target: { value: 'source' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save my decision' }))
  await screen.findByRole('alert'); first.unmount()
  render(<PracticalReview {...props} />)
  await openRun()
  expect(screen.getByLabelText('Source I would authorize')).toHaveValue('source')
  expect(screen.getByLabelText('Source I would authorize')).toBeDisabled()
  vi.mocked(api.getPracticalDecision).mockResolvedValue(receipt({ ...original,
    proposal_selection: { proposal_sha256: proposal.proposal_sha256, source_id: 'unrelated' } }))
  fireEvent.click(screen.getByRole('button', { name: 'Check saved decision' }))
  await screen.findByRole('alert')
  expect(screen.queryByText('Decision saved')).not.toBeInTheDocument()
  expect(api.submitPracticalDecision).toHaveBeenCalledOnce()
  vi.mocked(api.getPracticalDecision).mockResolvedValue(receipt(original))
  fireEvent.click(screen.getByRole('button', { name: 'Check saved decision' }))
  await screen.findByText('Decision saved')
  expect(api.submitPracticalDecision).toHaveBeenCalledOnce()
})

it('hands execution results to the mounted value review with keyboard focus', async () => {
  const warnings = vi.spyOn(console, 'error')
  const valuePrompt: PracticalDecisionPrompt = { ...prompt, id: 'value_review', phase: 'after_execution', question: 'Check saved values', prompt_sha256: 'c'.repeat(64) }
  vi.mocked(api.getPracticalDecisionContext).mockImplementation(async (_e, _m, id) => ({ ...context, prompt: id === valuePrompt.id ? valuePrompt : prompt }))
  vi.mocked(api.getPracticalExecution).mockResolvedValue({ enrollment_id: 'enrollment', module_id: 'foundations', course_version: 'course', manifest_sha256: 'd'.repeat(64), input_snapshot_id: runId, run_id: runId,
    state: 'completed', plan_sha256: 'e'.repeat(64), scope_decision_id: 'f'.repeat(32), scope_decision_sha256: 'a'.repeat(64), model_names: ['configured-model'], can_execute: false,
    blocked_reason: null, started_at: null, finished_at: null, documents_executed: 1, result_available: true, credit_awarded: false, module_completion_eligible: false })
  render(<PracticalReview {...props} prompts={[prompt, valuePrompt]} prepareEnabled />)
  await openRun()
  fireEvent.click(screen.getByRole('button', { name: 'Check execution status' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Review saved values' }))
  await screen.findByRole('group', { name: 'Check saved values' })
  await waitFor(() => expect(screen.getByRole('region', { name: 'Saved source and learner review' })).toHaveFocus())
  expect(screen.getByLabelText('Review stage')).toHaveValue('value_review')
  expect(api.executePracticalRun).not.toHaveBeenCalled()
  expect(warnings.mock.calls.flat().some(value => String(value).includes('same key'))).toBe(false)
  warnings.mockRestore()
})

it('shows owned historical work without preparation, execution, assessment or decision writes', async () => {
  const reason = 'This is saved history from a different course.'
  vi.mocked(api.getPracticalRuns).mockResolvedValue({ enrollment_id: props.enrollmentId, module_id: props.moduleId,
    runs: [{ run_id: runId, state: 'prepared' }], older_runs_available: false, read_only_reason: reason })
  vi.mocked(api.getPracticalDecisionContext).mockResolvedValue({ ...context, can_submit: false, read_only_reason: reason })
  render(<PracticalReview {...props} prepareEnabled />)
  await openRun()
  expect(screen.getByRole('button', { name: 'Save my decision' })).toBeDisabled()
  expect(screen.getByLabelText('Explain your decision')).toBeDisabled()
  expect(screen.queryByRole('region', { name: 'Prepare a practical run' })).not.toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Execute saved practical run' })).not.toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Request automatic assessment' })).not.toBeInTheDocument()
  expect(screen.getByText('PI Name: Jane. This is the saved source.')).toBeInTheDocument()
  expect(api.submitPracticalDecision).not.toHaveBeenCalled()
})
it('does not enable action controls for a mismatched run-list enrollment', async () => {
  vi.mocked(api.getPracticalRuns).mockResolvedValue({ enrollment_id: 'different-course', module_id: props.moduleId,
    runs: [{ run_id: runId, state: 'prepared' }], older_runs_available: false })
  render(<PracticalReview {...props} prepareEnabled />)
  expect(await screen.findByRole('alert')).toHaveTextContent('different course requirements')
  expect(screen.queryByRole('region', { name: 'Prepare a practical run' })).not.toBeInTheDocument()
})

it('keeps history-only browsing read-only even for the selected writable course', async () => {
  render(<PracticalReview {...props} prepareEnabled historyOnly />)
  await openRun()
  expect(screen.getByRole('button', { name: 'Save my decision' })).toBeDisabled()
  expect(screen.getByLabelText('Explain your decision')).toBeDisabled()
  expect(screen.queryByRole('region', { name: 'Prepare a practical run' })).not.toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Execute saved practical run' })).not.toBeInTheDocument()
  expect(api.submitPracticalDecision).not.toHaveBeenCalled()
})

function repairContext(): PracticalDecisionContext {
  return { ...context, documents: context.documents.map(document => ({ ...document })), module_id: 'extraction_engine',
    prompt: { ...prompt, module_id: 'extraction_engine', outcome_id: 'extraction_engine.field_semantics' },
    artifact: { title: 'Revised NIH fields', fields: [{ title: 'Postdoctoral Fellow Name', searchphrase: 'Leave absent when only TBD is listed.', is_optional: true, enum_values: [] },
      { title: 'Human Subjects', searchphrase: 'Whether human subjects are explicitly reported.', is_optional: false, enum_values: ['Yes', 'No'] }] },
    repair_case: { repair_case_sha256: 'f'.repeat(64), source_document_id: 'source', case: {
      module_id: 'extraction_engine', task: 'Repair the fields and verify the actual revised output against the assigned source.',
      baseline: { provenance: 'authored_flawed_example_not_an_execution', notice: 'This authored flawed example is not an execution or your saved work.',
        fields: [{ title: 'Postdoctoral Fellow Name', searchphrase: 'Supply a plausible name when no person is listed.', is_optional: false, enum_values: [] }],
        output: { 'Postdoctoral Fellow Name': '<b>Invented person</b>' } } } } }
}
it('shows the current assignment before preparation and the captured assignment after selecting a run', async () => {
  const value = repairContext()
  vi.mocked(api.getPracticalDecisionContext).mockResolvedValue(value)
  render(<PracticalReview enrollmentId="enrollment" moduleId="extraction_engine" prompts={[value.prompt]}
    repairAssignment={{ ...value.repair_case!.case, task: 'Current assignment before preparation' }} />)
  expect(screen.getByText('Current assignment before preparation')).toBeInTheDocument()
  expect(api.getPracticalDecisionContext).not.toHaveBeenCalled()
  await openRepair()
  expect(screen.queryByText('Current assignment before preparation')).not.toBeInTheDocument()
  expect(screen.getByText(value.repair_case!.case.task)).toBeInTheDocument()
})

it('does not substitute the current assignment for original course history', async () => {
  const value = repairContext()
  render(<PracticalReview enrollmentId="enrollment" moduleId="extraction_engine" prompts={[value.prompt]}
    repairAssignment={value.repair_case!.case} historyOnly />)
  await screen.findByLabelText('Saved run')
  expect(screen.queryByRole('region', { name: 'Authored repair example' })).not.toBeInTheDocument()
})
function renderRepair(value = repairContext(), historyOnly = false) {
  vi.mocked(api.getPracticalDecisionContext).mockResolvedValue(value)
  vi.mocked(api.submitPracticalDecision).mockImplementation(async (_e, _m, _p, body) => ({ ...receipt(body), module_id: 'extraction_engine' }))
  return render(<PracticalReview enrollmentId="enrollment" moduleId="extraction_engine" prompts={[value.prompt]} historyOnly={historyOnly} />)
}
async function openRepair() {
  fireEvent.change(await screen.findByLabelText('Saved run'), { target: { value: runId } })
  await screen.findByText('Revised NIH fields')
}

it('distinguishes the authored example from revised fields and binds the saved decision', async () => {
  renderRepair(); await openRepair()
  const example = screen.getByRole('region', { name: 'Authored repair example' })
  expect(within(example).getByText('This authored flawed example is not an execution or your saved work.')).toBeInTheDocument()
  fireEvent.click(within(example).getByText('Inspect the original flawed example'))
  expect(within(example).getByText('Authored flawed value: <b>Invented person</b>').querySelector('b')).toBeNull()
  expect(screen.getByText('Optional: Yes')).toBeInTheDocument()
  expect(screen.getByText('Allowed categories: Yes, No')).toBeInTheDocument()
  answer(); fireEvent.click(screen.getByRole('button', { name: 'Save my decision' }))
  await screen.findByText('Decision saved')
  expect(api.submitPracticalDecision).toHaveBeenCalledWith('enrollment', 'extraction_engine', prompt.id,
    expect.objectContaining({ repair_case_sha256: 'f'.repeat(64), choice: 'approve' }))
  expect(screen.getByLabelText('Saved practical decision')).toHaveFocus()
})

it.each(['missing', 'wrong_module', 'wrong_source', 'wrong_provenance', 'invalid_hash'])('rejects a %s repair example before displaying its form', async change => {
  const value = repairContext()
  if (change === 'missing') value.repair_case = null
  else if (change === 'wrong_module') Object.assign(value.repair_case!.case, { module_id: 'foundations' })
  else if (change === 'wrong_source') value.repair_case!.source_document_id = 'unrelated'
  else if (change === 'wrong_provenance') Object.assign(value.repair_case!.case.baseline, { provenance: 'actual_execution' })
  else value.repair_case!.repair_case_sha256 = 'invalid'
  renderRepair(value)
  fireEvent.change(await screen.findByLabelText('Saved run'), { target: { value: runId } })
  expect(await screen.findByRole('alert')).toHaveTextContent('different course requirements')
  expect(screen.queryByText('Revised NIH fields')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Save my decision' })).not.toBeInTheDocument()
})

it('does not accept a receipt that silently drops the repair binding', async () => {
  renderRepair()
  vi.mocked(api.submitPracticalDecision).mockImplementation(async (_e, _m, _p, body) => ({ ...receipt(body), module_id: 'extraction_engine',
    submission: { ...body, repair_case_sha256: null } }))
  await openRepair(); answer(); fireEvent.click(screen.getByRole('button', { name: 'Save my decision' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('could not confirm')
  expect(screen.queryByText('Decision saved')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Check saved decision' })).toBeEnabled()
})

it('preserves the exact repair binding when recovering a lost response', async () => {
  const value = repairContext()
  const first = renderRepair(value)
  let original!: PracticalDecisionBody
  vi.mocked(api.submitPracticalDecision).mockImplementation(async (_e, _m, _p, body) => { original = body; throw new Error('Lost reply') })
  await openRepair(); answer(); fireEvent.click(screen.getByRole('button', { name: 'Save my decision' }))
  await screen.findByRole('alert'); first.unmount()
  renderRepair(value)
  vi.mocked(api.getPracticalDecision).mockResolvedValue({ ...receipt(original), module_id: 'extraction_engine' })
  await openRepair(); fireEvent.click(screen.getByRole('button', { name: 'Check saved decision' }))
  await screen.findByText('Decision saved')
  expect(api.submitPracticalDecision).toHaveBeenCalledOnce()
  expect(original.repair_case_sha256).toBe(value.repair_case!.repair_case_sha256)
})

it('shows supported absence accurately in read-only repair history', async () => {
  const value = repairContext()
  value.prompt = { ...value.prompt, phase: 'after_execution', required_fields: ['Postdoctoral Fellow Name'] }
  value.run_state = 'completed'; value.can_submit = true
  value.documents[0].text = 'TBD Postdoctoral Fellow'
  value.latest_decision = { ...receipt({ request_id: 'd'.repeat(32), run_id: runId, prompt_sha256: prompt.prompt_sha256,
    choice: 'approve', reason: 'The source identifies no named postdoc.', repair_case_sha256: value.repair_case!.repair_case_sha256,
    value_checks: [{ field: 'Postdoctoral Fellow Name', decision: 'supported', checked_value: '', source_document_id: 'source',
      source_quote: 'TBD Postdoctoral Fellow', reason: 'TBD is a placeholder; no person is named.' }] }), module_id: 'extraction_engine' }
  renderRepair(value, true); await openRepair()
  fireEvent.click(screen.getByText('Saved source checks'))
  expect(screen.getByText('Checked value: Empty value (recorded as supported absence)')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Save my decision' })).toBeDisabled()
  expect(api.submitPracticalDecision).not.toHaveBeenCalled()
})

it('preserves the original practical choice while another enrollment keeps a separate draft', async () => {
  let view = render(<PracticalReview {...props} />)
  await openRun(); answer(); view.unmount()
  vi.mocked(api.getPracticalDecisionContext).mockResolvedValue({ ...context, enrollment_id: 'other-enrollment' })
  view = render(<PracticalReview {...props} enrollmentId="other-enrollment" />)
  await openRun()
  expect(screen.getByLabelText('Ready to run')).not.toBeChecked()
  expect(screen.getByLabelText('Explain your decision')).toHaveValue('')
  fireEvent.change(screen.getByLabelText('Explain your decision'), { target: { value: 'Separate explanation in the other course' } })
  view.unmount()
  vi.mocked(api.getPracticalDecisionContext).mockResolvedValue(context)
  render(<PracticalReview {...props} />)
  await openRun()
  expect(screen.getByLabelText('Ready to run')).toBeChecked()
  expect(screen.getByLabelText('Explain your decision')).toHaveValue('I checked the assigned source and saved fields.')
  expect(api.submitPracticalDecision).not.toHaveBeenCalled()
})


it.each([401, 422, 503])('keeps the original pending decision locked after a %s read failure', async status => {
  vi.mocked(api.submitPracticalDecision).mockRejectedValueOnce(new Error('Network failure'))
  vi.mocked(api.getPracticalDecision).mockRejectedValue(new ApiError(status, 'Read failed'))
  render(<PracticalReview {...props} />)
  await openRun(); answer()
  fireEvent.click(screen.getByRole('button', { name: 'Save my decision' }))
  await screen.findByRole('alert')
  const before = sessionStorage.getItem(`certification-decision:enrollment:${runId}:${prompt.prompt_sha256}`)
  fireEvent.click(screen.getByRole('button', { name: 'Check saved decision' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Check saved decision' })).toBeEnabled())
  expect(screen.getByLabelText('Needs correction')).toBeDisabled()
  expect(sessionStorage.getItem(`certification-decision:enrollment:${runId}:${prompt.prompt_sha256}`)).toBe(before)
  expect(screen.queryByRole('button', { name: 'Retry original decision' })).not.toBeInTheDocument()
  expect(api.submitPracticalDecision).toHaveBeenCalledOnce()
})

it.each(['found', 'missing'] as const)('can check an uncertain %s decision after its run becomes read-only', async state => {
  let original!: PracticalDecisionBody
  vi.mocked(api.submitPracticalDecision).mockImplementation(async (_e, _m, _p, body) => { original = body; throw new Error('Lost response') })
  const first = render(<PracticalReview {...props} />)
  await openRun(); answer()
  fireEvent.click(screen.getByRole('button', { name: 'Save my decision' }))
  await screen.findByRole('alert')
  first.unmount()
  vi.mocked(api.getPracticalDecisionContext).mockResolvedValue({ ...context, can_submit: false, read_only_reason: 'This run has already left preparation.' })
  if (state === 'found') vi.mocked(api.getPracticalDecision).mockResolvedValue(receipt(original))
  else vi.mocked(api.getPracticalDecision).mockRejectedValue(new ApiError(404, 'Missing'))
  render(<PracticalReview {...props} />)
  await openRun()
  const check = screen.getByRole('button', { name: 'Check saved decision' })
  expect(check).toBeEnabled()
  fireEvent.click(check)
  if (state === 'found') await screen.findByText('Decision saved')
  else expect(await screen.findByRole('alert')).toHaveTextContent('no longer accepts decision changes')
  expect(screen.getByLabelText('Needs correction')).toBeDisabled()
  expect(screen.queryByRole('button', { name: 'Retry original decision' })).not.toBeInTheDocument()
  expect(api.submitPracticalDecision).toHaveBeenCalledOnce()
})

it('refuses a direct form submit when the saved run no longer accepts decisions', async () => {
  vi.mocked(api.getPracticalDecisionContext).mockResolvedValue({ ...context, can_submit: false, read_only_reason: 'This run has already left preparation.' })
  render(<PracticalReview {...props} />)
  await openRun()
  fireEvent.submit(screen.getByRole('button', { name: 'Save my decision' }).closest('form')!)
  expect(api.submitPracticalDecision).not.toHaveBeenCalled()
})

it('opens the run from saved assessment feedback at the values review without writing', async () => {
  const valuePrompt: PracticalDecisionPrompt = { ...prompt, id: 'value_review', phase: 'after_execution' }
  const assessment = { attempt_id: 'c'.repeat(32), enrollment_id: 'enrollment', module_id: 'foundations', run_id: runId,
    course_version: 'draft', manifest_sha256: 'd'.repeat(64), prepared_at: '2026-10-09', finished_at: null, parent_attempt_id: null,
    status: 'revision_required' as const, assessment_kind: 'practical_review_draft' as const, credit_awarded: false as const,
    module_completion_eligible: false as const, staff_review_required: false as const, can_request_review: false as const,
    can_retry_review: false as const, outcomes: [] }
  vi.mocked(api.getAutomaticReviews).mockResolvedValue({ enrollment_id: 'enrollment', module_id: 'foundations', attempts: [assessment], older_attempts_available: false })
  vi.mocked(api.getAutomaticReview).mockResolvedValue(assessment)
  vi.mocked(api.getPracticalDecisionContext).mockResolvedValue({ ...context, prompt: valuePrompt, run_state: 'completed' })
  render(<PracticalReview {...props} prompts={[prompt, valuePrompt]} />)
  await screen.findByLabelText('Saved run')
  fireEvent.click(screen.getByRole('button', { name: 'View saved assessments' }))
  fireEvent.click(await screen.findByRole('button', { name: /Assessment 1/ }))
  fireEvent.click(await screen.findByRole('button', { name: 'Open saved work to review' }))
  await waitFor(() => expect(screen.getByRole('region', { name: 'Saved source and learner review' })).toHaveFocus())
  expect(api.getPracticalDecisionContext).toHaveBeenCalledWith('enrollment', 'foundations', 'value_review', runId)
  expect(screen.getByLabelText('Review stage')).toHaveValue('value_review')
  expect(api.submitPracticalDecision).not.toHaveBeenCalled()
  expect(api.executePracticalRun).not.toHaveBeenCalled()
})
