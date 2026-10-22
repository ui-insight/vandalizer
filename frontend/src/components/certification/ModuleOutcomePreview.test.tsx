import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ModuleOutcomePreview } from './ModuleOutcomePreview'
import { getModuleReadiness, type ModuleReadinessResult, type AssessmentSelection } from '../../api/moduleReadiness'
import { getAutomaticReviews, getSavedScenarioHistory } from '../../api/certification'

vi.mock('../../api/certification', () => ({ getAutomaticReviews: vi.fn(), getSavedScenarioHistory: vi.fn() }))
vi.mock('../../api/moduleReadiness', async original => ({ ...await original<typeof import('../../api/moduleReadiness')>(), getModuleReadiness: vi.fn() }))
const identity = { enrollment_id: 'owned', course_version: 'draft', manifest_sha256: 'a'.repeat(64) }
const review = '1'.repeat(32), scenario = '2'.repeat(32), failedScenario = '3'.repeat(32)
function result(selection: AssessmentSelection = {}): ModuleReadinessResult {
  const outcomes: ModuleReadinessResult['outcomes'] = [
    { outcome_id: 'governance.review', statement: 'Inspect the complete evidence.', method: 'structured_review', state: selection.review ? 'supported' : 'selection_required', attempt_id: selection.review || null },
    { outcome_id: 'governance.recognition', statement: 'Recognize an unsupported claim.', method: 'scenario_choice', state: selection.scenario ? selection.scenario === failedScenario ? 'revision_required' : 'supported' : 'selection_required', attempt_id: selection.scenario || null },
  ]
  const status = selection.scenario === failedScenario ? 'revision_required' : selection.review && selection.scenario ? 'requirements_supported' : 'selection_required'
  return { ...identity, module_id: 'governance', contract_sha256: 'b'.repeat(64), rubric_id: 'draft-rubric', assessment_kind: 'module_readiness_draft', status,
    all_required_outcomes_supported: status === 'requirements_supported', outcomes,
    selected_receipts: [ ...(selection.review ? [{ kind: 'automatic_review' as const, attempt_id: selection.review, record_sha256: 'c'.repeat(64), result_sha256: 'd'.repeat(64) }] : []),
      ...(selection.scenario ? [{ kind: 'scenario_recognition' as const, attempt_id: selection.scenario, record_sha256: 'e'.repeat(64), result_sha256: 'f'.repeat(64) }] : []) ],
    read_only: true, credit_awarded: false, module_completion_eligible: false, staff_review_required: false }
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(getModuleReadiness).mockImplementation(async (_e, _m, selection) => result(selection))
  vi.mocked(getAutomaticReviews).mockResolvedValue({ enrollment_id: 'owned', module_id: 'governance', older_attempts_available: false, attempts: [
    { attempt_id: review, enrollment_id: 'owned', module_id: 'governance', run_id: null, parent_attempt_id: null, status: 'requirements_supported', prepared_at: '2026-10-07T12:00:00Z', finished_at: null },
  ] })
  vi.mocked(getSavedScenarioHistory).mockResolvedValue({ enrollment_id: 'owned', module_id: 'governance', bank_sha256: 'e'.repeat(64), read_only: true, older_attempts_available: true,
    attempts: [{ attempt_id: scenario, submitted_at: '2026-10-07T12:00:00Z', passed: true }, { attempt_id: failedScenario, submitted_at: '2026-10-06T12:00:00Z', passed: false }] })
})
async function open() {
  fireEvent.click(screen.getByRole('button', { name: 'Choose saved assessments' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Check selected assessments' })).toBeEnabled())
}
it('loads only on request and leaves both required evidence choices empty', async () => {
  render(<ModuleOutcomePreview identity={identity} moduleId="governance" />)
  expect(getModuleReadiness).not.toHaveBeenCalled()
  await open()
  expect(screen.getByRole('combobox', { name: 'Automatic assessment' })).toHaveValue('')
  expect(screen.getByRole('combobox', { name: 'Scenario assessment' })).toHaveValue('')
  expect(screen.getAllByText('Select saved evidence')).toHaveLength(2)
  expect(getModuleReadiness).toHaveBeenCalledExactlyOnceWith('owned', 'governance')
})
it('uses the explicitly selected failed original despite a newer pass, and clears results when selection changes', async () => {
  render(<ModuleOutcomePreview identity={identity} moduleId="governance" />)
  await open()
  fireEvent.change(screen.getByRole('combobox', { name: 'Automatic assessment' }), { target: { value: review } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Scenario assessment' }), { target: { value: failedScenario } })
  expect(screen.getByText(/^Selected scenario assessment:/)).toHaveTextContent('Revision needed')
  fireEvent.click(screen.getByRole('button', { name: 'Check selected assessments' }))
  await screen.findByRole('heading', { name: 'Revision needed' })
  expect(getModuleReadiness).toHaveBeenLastCalledWith('owned', 'governance', { review, scenario: failedScenario })
  expect(screen.getByRole('region', { name: 'Module outcome result' })).toHaveFocus()
  fireEvent.change(screen.getByRole('combobox', { name: 'Scenario assessment' }), { target: { value: scenario } })
  expect(screen.queryByRole('heading', { name: 'Revision needed' })).not.toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'All draft outcomes supported' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Check selected assessments' }))
  await screen.findByRole('heading', { name: 'All draft outcomes supported' })
  expect(screen.getByText(/This check has not awarded credit/)).toBeInTheDocument()
})
it('does not turn a missing scenario selection into a complete result', async () => {
  render(<ModuleOutcomePreview identity={identity} moduleId="governance" />)
  await open()
  fireEvent.change(screen.getByRole('combobox', { name: 'Automatic assessment' }), { target: { value: review } })
  fireEvent.click(screen.getByRole('button', { name: 'Check selected assessments' }))
  await screen.findByRole('heading', { name: 'Select saved evidence' })
  expect(screen.getByText('Supported by selected evidence')).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'All draft outcomes supported' })).not.toBeInTheDocument()
})
it.each(['assessment_pending', 'grading_unavailable'] as const)('keeps technical assessment state explicit: %s', async state => {
  render(<ModuleOutcomePreview identity={identity} moduleId="governance" />)
  await open()
  fireEvent.change(screen.getByRole('combobox', { name: 'Automatic assessment' }), { target: { value: review } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Scenario assessment' }), { target: { value: scenario } })
  const pending = result({ review, scenario })
  pending.outcomes[0].state = state
  pending.status = state
  pending.all_required_outcomes_supported = false
  if (state === 'assessment_pending') pending.selected_receipts[0].result_sha256 = null
  vi.mocked(getModuleReadiness).mockResolvedValueOnce(pending)
  fireEvent.click(screen.getByRole('button', { name: 'Check selected assessments' }))
  await screen.findByRole('heading', { name: state === 'assessment_pending' ? 'Assessment pending' : 'Assessment unavailable' })
  expect(screen.queryByRole('heading', { name: 'All draft outcomes supported' })).not.toBeInTheDocument()
  expect(getModuleReadiness).toHaveBeenCalledTimes(2)
})
it('supports an exact older reference when discovery fails without retrying any assessment', async () => {
  vi.mocked(getAutomaticReviews).mockRejectedValue(new Error('unavailable'))
  render(<ModuleOutcomePreview identity={identity} moduleId="governance" />)
  await open()
  expect(screen.getByRole('alert')).toHaveTextContent('Some saved choices could not be loaded')
  fireEvent.change(screen.getByLabelText('Automatic assessment reference'), { target: { value: 'short' } })
  expect(screen.getByRole('button', { name: 'Check selected assessments' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Automatic assessment reference'), { target: { value: review } })
  fireEvent.click(screen.getByRole('button', { name: 'Check selected assessments' }))
  await screen.findByRole('heading', { name: 'Select saved evidence' })
  expect(getModuleReadiness).toHaveBeenLastCalledWith('owned', 'governance', { review })
})
it('discards an in-flight response after closing and after changing enrollment', async () => {
  const view = render(<ModuleOutcomePreview identity={identity} moduleId="governance" />)
  await open()
  let resolve!: (value: ModuleReadinessResult) => void
  vi.mocked(getModuleReadiness).mockReturnValueOnce(new Promise(done => { resolve = done }))
  fireEvent.click(screen.getByRole('button', { name: 'Check selected assessments' }))
  fireEvent.click(screen.getByRole('button', { name: 'Close outcome preview' }))
  view.rerender(<ModuleOutcomePreview identity={{ ...identity, enrollment_id: 'another' }} moduleId="governance" />)
  resolve(result())
  await waitFor(() => expect(screen.getByRole('button', { name: 'Choose saved assessments' })).toBeEnabled())
  expect(screen.queryByRole('region', { name: 'Module outcome result' })).not.toBeInTheDocument()
})
it.each(['enrollment', 'manifest', 'contract', 'missing_outcome', 'contradiction', 'wrong_selection', 'credit'])('rejects inconsistent saved results: %s', async change => {
  render(<ModuleOutcomePreview identity={identity} moduleId="governance" />)
  await open()
  const invalid = result()
  if (change === 'enrollment') invalid.enrollment_id = 'another'
  if (change === 'manifest') invalid.manifest_sha256 = 'different'
  if (change === 'contract') invalid.contract_sha256 = '0'.repeat(64)
  if (change === 'missing_outcome') invalid.outcomes.pop()
  if (change === 'contradiction') invalid.all_required_outcomes_supported = true
  if (change === 'wrong_selection') invalid.outcomes[0].attempt_id = review
  if (change === 'credit') Object.assign(invalid, { credit_awarded: true })
  vi.mocked(getModuleReadiness).mockResolvedValueOnce(invalid)
  fireEvent.click(screen.getByRole('button', { name: 'Check selected assessments' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('heading', { name: 'All draft outcomes supported' })).not.toBeInTheDocument()
  expect(getModuleReadiness).toHaveBeenCalledTimes(2)
})

async function passingSelection() {
  await open()
  fireEvent.change(screen.getByRole('combobox', { name: 'Automatic assessment' }), { target: { value: review } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Scenario assessment' }), { target: { value: scenario } })
  fireEvent.click(screen.getByRole('button', { name: 'Check selected assessments' }))
  await screen.findByRole('heading', { name: /All .* outcomes supported/ })
}
it('keeps a draft preview read-only even when all selected outcomes pass', async () => {
  render(<ModuleOutcomePreview identity={identity} moduleId="governance" />)
  await passingSelection()
  expect(screen.queryByRole('button', { name: 'Complete module with selected evidence' })).toBeNull()
})
it('requires checking and a separate completion action', async () => {
  const complete = vi.fn().mockResolvedValue(undefined)
  render(<ModuleOutcomePreview identity={identity} moduleId="governance" onComplete={complete} />)
  await passingSelection()
  expect(complete).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Complete module with selected evidence' }))
  await waitFor(() => expect(complete).toHaveBeenCalledWith({ review_attempt_id: review, scenario_attempt_id: scenario }))
})
it('blocks a new completion while an earlier request awaits confirmation', async () => {
  const complete = vi.fn()
  render(<ModuleOutcomePreview identity={identity} moduleId="governance" onComplete={complete} completionPending />)
  await passingSelection()
  expect(screen.getByRole('button', { name: 'Complete module with selected evidence' })).toBeDisabled()
  expect(complete).not.toHaveBeenCalled()
})
it('removes completion eligibility immediately when selected evidence changes', async () => {
  render(<ModuleOutcomePreview identity={identity} moduleId="governance" onComplete={vi.fn()} />)
  await passingSelection()
  fireEvent.change(screen.getByRole('combobox', { name: 'Scenario assessment' }), { target: { value: failedScenario } })
  expect(screen.queryByRole('button', { name: 'Complete module with selected evidence' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Check selected assessments' }))
  await screen.findByRole('heading', { name: 'Revision needed' })
  expect(screen.getByRole('button', { name: 'Complete module with selected evidence' })).toBeDisabled()
})
it('keeps confirmed completion separate from a failed progress refresh', async () => {
  render(<ModuleOutcomePreview identity={identity} moduleId="governance" onComplete={vi.fn()} progressRefreshPending />)
  await passingSelection()
  expect(screen.getByRole('button', { name: 'Complete module with selected evidence' })).toBeDisabled()
  expect(screen.getByText('Completion is saved. Use the progress refresh notice to update your course status.')).toBeInTheDocument()
  expect(screen.queryByText(/Retry it from the pending completion notice/)).toBeNull()
})
