import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/courseChoices'
import { ApiError } from '../../api/client'
import type { UpgradePreview } from '../../types/certification'
import { OptionalUpgradeChoice } from './OptionalUpgradeChoice'
import { SavedCourseChoices } from './SavedCourseChoices'

vi.mock('../../api/courseChoices', async original => ({ ...await original<typeof api>(), getChoicePreview: vi.fn(), saveUpgradeChoice: vi.fn(), getUpgradeChoice: vi.fn(), activateUpgrade: vi.fn(), getActivation: vi.fn(), getSavedCourseOptions: vi.fn(), getSavedChoicePreview: vi.fn(), selectSavedCourse: vi.fn(), getSavedSelection: vi.fn() }))
const source = 'a'.repeat(32), target = 'b'.repeat(32), manifest = 'c'.repeat(64), hash = 'd'.repeat(64)
const preview: UpgradePreview = { policy: 'optional', can_activate: false, preview_sha256: hash,
  source: { enrollment_id: source, course_version: 'original', course_title: 'Original course', provenance: 'legacy_version_unknown', total_xp: 125, certified: false, credential_preserved: false, completed_modules: [], has_saved_place: true },
  target: { course_version: 'upgraded', course_title: 'Agentic course', manifest_sha256: manifest, required_outcome_count: 3, transferred_outcome_count: 0, modules: [] }, saved_work: [], work_in_flight: false, unfinished_answers: true, credential_needs_preservation: false }
const request: api.UpgradeChoiceRequest = { request_id: 'e'.repeat(32), source_enrollment_id: source, target_version: 'upgraded', preview_sha256: hash, consent: 'preserve_original_work_and_require_all_new_outcomes' }
const decision: api.UpgradeChoice = { decision_id: request.request_id, source_enrollment_id: source, target_version: 'upgraded', target_manifest_sha256: manifest, preview_sha256: hash, decision_sha256: 'f'.repeat(64), accepted_at: '2026-10-07T12:00:00Z', credit_transferred: false, requires_fresh_activation_check: true,
  activation_request: { request_id: '1'.repeat(32), decision_id: request.request_id, consent: 'activate_optional_upgrade_preserving_original_work_without_credit_transfer' } }
const choicePreview: api.ChoicePreview = { comparison: preview, choice: { available: true, reason: null, recorded: false, request, decision: null } }
const result: api.SelectionResult = { current_enrollment_id: target, confirmation_pending: false,
  receipt: { request_id: decision.activation_request.request_id, kind: 'optional_upgrade_selection.1', receipt_sha256: hash, source_enrollment_id: source, target_enrollment_id: target, target_course_version: 'upgraded', target_manifest_sha256: manifest, revision: 1, selected_at: '2026-10-07T12:00:00Z', action: 'activate_optional_upgrade', credit_transferred: false, histories_preserved: true } }
const item: api.SavedCourseOption = { activation_id: decision.activation_request.request_id, action: 'return_to_original_course', enrollment_id: source, course_version: 'original', course_title: 'Original course', definition_available: true }
const saved: api.SavedChoicePreview = { request: { request_id: '2'.repeat(32), activation_id: item.activation_id, action: item.action, preview_sha256: hash, consent: 'select_saved_course_preserving_both_histories_and_credit' },
  preview: { schema_version: 1, activation_id: item.activation_id, action: item.action, read_only: true, can_activate: false, credit_transferred: false, selection_revision: 1, preservation_policy: 'keep_both_existing_enrollments_and_original_workspace_references', state_sha256: hash, preview_sha256: hash,
    source: { enrollment_id: target, course_version: 'upgraded', course_title: 'Agentic course', manifest_sha256: manifest, total_xp: 35, completed_modules: 1, credential_id: null, has_saved_place: true, record_counts: {} },
    target: { enrollment_id: source, course_version: 'original', course_title: 'Original course', manifest_sha256: hash, total_xp: 125, completed_modules: 2, credential_id: '3'.repeat(32), has_saved_place: true, record_counts: {} } } }
const returned: api.SelectionResult = { current_enrollment_id: source, confirmation_pending: false, receipt: { ...result.receipt, request_id: saved.request.request_id, source_enrollment_id: target, target_enrollment_id: source, kind: 'saved_course_selection.1', action: item.action, target_course_version: 'original', target_manifest_sha256: hash } }
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.getChoicePreview).mockResolvedValue(choicePreview)
  vi.mocked(api.saveUpgradeChoice).mockResolvedValue(decision)
  vi.mocked(api.getUpgradeChoice).mockResolvedValue(decision)
  vi.mocked(api.activateUpgrade).mockResolvedValue(result)
  vi.mocked(api.getActivation).mockResolvedValue({ ...result, request: decision.activation_request, source_enrollment_id: source, state: 'applied', read_only: true })
  vi.mocked(api.getSavedCourseOptions).mockResolvedValue({ current_enrollment_id: target, read_only: true, courses: [item], next_cursor: null })
  vi.mocked(api.getSavedChoicePreview).mockResolvedValue(saved)
  vi.mocked(api.selectSavedCourse).mockResolvedValue(returned)
  vi.mocked(api.getSavedSelection).mockResolvedValue({ ...returned, request: saved.request, source_enrollment_id: target, state: 'applied', read_only: true })
})
async function chooseUpgrade() {
  fireEvent.click(screen.getByRole('button', { name: 'Review upgrade choice' }))
  const save = await screen.findByRole('button', { name: 'Save my upgrade choice' })
  expect(save).toBeDisabled()
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(save)
  return screen.findByRole('button', { name: 'Switch to Agentic course' })
}
async function reviewSaved() {
  fireEvent.click(screen.getByRole('button', { name: 'Choose a saved course' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Review Original course' }))
  await screen.findByRole('region', { name: 'Saved course preservation review' })
  expect(screen.getByRole('button', { name: 'Return to original course' })).toBeDisabled()
  fireEvent.click(screen.getByRole('checkbox'))
}
it('requires preservation consent and a separate switch, then explicit course refresh', async () => {
  const refresh = vi.fn().mockResolvedValue(undefined)
  render(<OptionalUpgradeChoice preview={preview} onRefreshCourse={refresh} />)
  expect(api.getChoicePreview).not.toHaveBeenCalled()
  const button = await chooseUpgrade()
  expect(api.saveUpgradeChoice).toHaveBeenCalledExactlyOnceWith(request)
  expect(api.activateUpgrade).not.toHaveBeenCalled()
  fireEvent.click(button)
  await screen.findByText(/course choice has a saved receipt/)
  expect(api.activateUpgrade).toHaveBeenCalledExactlyOnceWith(decision.activation_request)
  expect(refresh).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Refresh my course' }))
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce())
})
it('recovers a lost choice reply using GET without accepting or switching again', async () => {
  vi.mocked(api.saveUpgradeChoice).mockRejectedValueOnce(new Error('Lost reply'))
  render(<OptionalUpgradeChoice preview={preview} onRefreshCourse={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Review upgrade choice' }))
  fireEvent.click(await screen.findByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: 'Save my upgrade choice' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Check saved choice' }))
  await screen.findByRole('button', { name: 'Switch to Agentic course' })
  expect(api.getUpgradeChoice).toHaveBeenCalledExactlyOnceWith(request.request_id)
  expect(api.saveUpgradeChoice).toHaveBeenCalledOnce()
  expect(api.activateUpgrade).not.toHaveBeenCalled()
})
it('recovers the original recorded choice when a harmless guard rotation changed the public preview hash', async () => {
  vi.mocked(api.getChoicePreview).mockResolvedValue({ comparison: { ...preview, preview_sha256: '0'.repeat(64) }, choice: { ...choicePreview.choice, recorded: true, decision } })
  render(<OptionalUpgradeChoice preview={{ ...preview, preview_sha256: '0'.repeat(64) }} onRefreshCourse={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Review upgrade choice' }))
  await screen.findByRole('button', { name: 'Switch to Agentic course' })
  expect(api.saveUpgradeChoice).not.toHaveBeenCalled()
  expect(api.activateUpgrade).not.toHaveBeenCalled()
})
it.each(['assessment_unavailable', 'resume_saved_course', 'selection_busy', 'unfinished_course_work'])('never offers a write for %s', async reason => {
  vi.mocked(api.getChoicePreview).mockResolvedValue({ ...choicePreview, choice: { ...choicePreview.choice, available: false, reason } })
  render(<OptionalUpgradeChoice preview={preview} onRefreshCourse={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Review upgrade choice' }))
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Review upgrade choice' })).toBeNull())
  expect(screen.queryByRole('checkbox')).toBeNull()
  expect(api.activateUpgrade).not.toHaveBeenCalled()
})
it.each(['source', 'manifest', 'request'])('rejects a rebound saved decision %s', async field => {
  const wrong = structuredClone(decision)
  if (field === 'source') wrong.source_enrollment_id = target
  if (field === 'manifest') wrong.target_manifest_sha256 = hash
  if (field === 'request') wrong.activation_request.decision_id = target
  vi.mocked(api.saveUpgradeChoice).mockResolvedValue(wrong)
  render(<OptionalUpgradeChoice preview={preview} onRefreshCourse={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Review upgrade choice' }))
  fireEvent.click(await screen.findByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: 'Save my upgrade choice' }))
  await screen.findByRole('button', { name: 'Check saved choice' })
  expect(api.activateUpgrade).not.toHaveBeenCalled()
})
it('checks an uncertain switch and treats its old receipt as history rather than selecting its target again', async () => {
  vi.mocked(api.activateUpgrade).mockRejectedValueOnce(new Error('Lost response'))
  vi.mocked(api.getActivation).mockResolvedValue({ ...result, current_enrollment_id: source, request: decision.activation_request, source_enrollment_id: source, state: 'applied', read_only: true })
  render(<OptionalUpgradeChoice preview={preview} onRefreshCourse={vi.fn()} />)
  fireEvent.click(await chooseUpgrade())
  fireEvent.click(await screen.findByRole('button', { name: 'Check saved switch' }))
  await screen.findByText(/load your current selection/)
  expect(api.activateUpgrade).toHaveBeenCalledOnce()
  expect(screen.queryByRole('button', { name: 'Switch to Agentic course' })).toBeNull()
})
it('requires a GET not-found result before explicitly retrying the identical original request', async () => {
  vi.mocked(api.activateUpgrade).mockRejectedValueOnce(new Error('Never delivered'))
  vi.mocked(api.getActivation).mockRejectedValueOnce(new ApiError(404, 'Missing'))
  render(<OptionalUpgradeChoice preview={preview} onRefreshCourse={vi.fn()} />)
  fireEvent.click(await chooseUpgrade())
  await screen.findByRole('button', { name: 'Check saved switch' })
  expect(screen.queryByRole('button', { name: 'Switch to Agentic course' })).toBeNull()
  fireEvent.click(await screen.findByRole('button', { name: 'Check saved switch' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Switch to Agentic course' }))
  await screen.findByText(/course choice has a saved receipt/)
  expect(vi.mocked(api.activateUpgrade).mock.calls).toEqual([[decision.activation_request], [decision.activation_request]])
})
it('shows both retained histories and does not lose uncertain state when consent is toggled', async () => {
  vi.mocked(api.selectSavedCourse).mockRejectedValueOnce(new Error('Lost reply'))
  render(<SavedCourseChoices enrollmentId={target} onRefreshCourse={vi.fn()} />)
  await reviewSaved()
  expect(screen.getByText('35 XP · Completed modules: 1')).toBeInTheDocument()
  expect(screen.getByText('125 XP · Completed modules: 2')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Return to original course' }))
  await screen.findByRole('button', { name: 'Check saved switch' })
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('checkbox'))
  expect(screen.queryByRole('button', { name: 'Return to original course' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Check saved switch' }))
  await screen.findByText(/course choice has a saved receipt/)
  expect(api.selectSavedCourse).toHaveBeenCalledExactlyOnceWith(saved.request)
  expect(api.getSavedSelection).toHaveBeenCalledExactlyOnceWith(saved.request.request_id)
})
it('blocks a stale saved-course preview before consent or switching', async () => {
  vi.mocked(api.getSavedChoicePreview).mockRejectedValueOnce(new ApiError(409, 'New work'))
  render(<SavedCourseChoices enrollmentId={target} onRefreshCourse={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Choose a saved course' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Review Original course' }))
  await screen.findByText(/course or saved work changed/)
  expect(screen.queryByRole('checkbox')).toBeNull()
  expect(api.selectSavedCourse).not.toHaveBeenCalled()
})
it('ignores a late save response after leaving the reviewed choice', async () => {
  let finish!: (value: api.UpgradeChoice) => void
  vi.mocked(api.saveUpgradeChoice).mockReturnValue(new Promise(resolve => { finish = resolve }))
  const view = render(<OptionalUpgradeChoice preview={preview} onRefreshCourse={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Review upgrade choice' }))
  fireEvent.click(await screen.findByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: 'Save my upgrade choice' }))
  view.unmount()
  await act(async () => finish(decision))
  expect(api.activateUpgrade).not.toHaveBeenCalled()
})


it('labels a pending preservation save separately from a pending switch and its read-only recovery', async () => {
  let finishChoice!: (value: api.UpgradeChoice) => void, rejectSwitch!: (error: Error) => void
  let finishRead!: (value: Awaited<ReturnType<typeof api.getActivation>>) => void
  vi.mocked(api.saveUpgradeChoice).mockReturnValue(new Promise(resolve => { finishChoice = resolve }))
  vi.mocked(api.activateUpgrade).mockReturnValue(new Promise((_resolve, reject) => { rejectSwitch = reject }))
  vi.mocked(api.getActivation).mockReturnValue(new Promise(resolve => { finishRead = resolve }))
  render(<OptionalUpgradeChoice preview={preview} onRefreshCourse={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Review upgrade choice' }))
  fireEvent.click(await screen.findByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: 'Save my upgrade choice' }))
  expect(screen.getByText('Saving your optional upgrade choice…')).toHaveAttribute('role', 'status')
  expect(screen.getByText(/This step does not switch courses or transfer credit/)).toBeInTheDocument()
  expect(api.activateUpgrade).not.toHaveBeenCalled()
  await act(async () => finishChoice(decision))
  fireEvent.click(await screen.findByRole('button', { name: 'Switch to Agentic course' }))
  expect(screen.getByText('Sending your course switch and waiting for its saved receipt…')).toHaveAttribute('role', 'status')
  expect(screen.getByText(/Closing this panel does not cancel or confirm the switch/)).toBeInTheDocument()
  await act(async () => rejectSwitch(new Error('Lost response')))
  fireEvent.click(screen.getByRole('button', { name: 'Check saved switch' }))
  expect(screen.getByText('Checking the saved course switch…')).toHaveAttribute('role', 'status')
  await act(async () => finishRead({ ...result, request: decision.activation_request, source_enrollment_id: source, state: 'applied', read_only: true }))
  expect(await screen.findByText(/course choice has a saved receipt/)).toBeInTheDocument()
  expect(api.saveUpgradeChoice).toHaveBeenCalledOnce()
  expect(api.activateUpgrade).toHaveBeenCalledOnce()
  expect(api.getActivation).toHaveBeenCalledOnce()
})
