import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/certification'
import { ApiError } from '../../api/client'
import type { UpgradeOptions, UpgradePreview } from '../../types/certification'
import { UpgradeComparison } from './UpgradeComparison'

vi.mock('../../api/certification', () => ({ getUpgradeOptions: vi.fn(), getUpgradePreview: vi.fn() }))
const options: UpgradeOptions = { enrollment_id: 'source', policy: 'optional', can_activate: false, courses: [{ course_version: 'target', course_title: 'V5 course', manifest_sha256: 'b'.repeat(64), description: 'Source review and supervision', required_outcome_count: 3 }] }
const preview: UpgradePreview = {
  policy: 'optional', can_activate: false, preview_sha256: 'a'.repeat(64),
  source: { enrollment_id: 'source', course_version: 'old', course_title: 'Original course', provenance: 'legacy_version_unknown', total_xp: 125, certified: false, credential_preserved: false, completed_modules: [{ module_id: 'foundations', title: 'Foundations', completed_at: '2025-01-01', xp_earned: 125, stars: 1 }], has_saved_place: true },
  target: { course_version: 'target', course_title: 'V5 course', manifest_sha256: 'b'.repeat(64), required_outcome_count: 3, transferred_outcome_count: 0, modules: [{ module_id: 'foundations', title: 'Foundations', outcomes: [{ outcome_id: 'scope', statement: 'Review the assigned source and scope.', disposition: 'requires_assessment', reason: 'No confirmed equivalence.' }] }] },
  saved_work: [{ kind: 'saved_lab_runs', label: 'Saved lab runs', count: 1 }], work_in_flight: true, unfinished_answers: true, credential_needs_preservation: false,
}
beforeEach(() => { vi.resetAllMocks(); vi.mocked(api.getUpgradeOptions).mockResolvedValue(options); vi.mocked(api.getUpgradePreview).mockResolvedValue(preview) })
async function openComparison() {
  fireEvent.click(screen.getByRole('button', { name: 'Compare course versions' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Compare V5 course' }))
}

it('loads only on request and shows preserved credit separately from unverified transfer', async () => {
  render(<UpgradeComparison enrollmentId="source" onRefreshCourse={vi.fn()} />)
  expect(api.getUpgradeOptions).not.toHaveBeenCalled()
  await openComparison()
  expect(await screen.findByText('Your course comparison')).toBeInTheDocument()
  expect(screen.getByText('Original course · 125 XP earned')).toBeInTheDocument()
  expect(screen.getByText('3 required outcomes · 0 confirmed for transfer')).toBeInTheDocument()
  expect(screen.getByText(/earlier course version was not recorded/)).toBeInTheDocument()
  expect(screen.getByText(/A course operation is still in progress/)).toBeInTheDocument()
  expect(screen.getByText(/unfinished reflection answers/)).toBeInTheDocument()
  expect(api.getUpgradePreview).toHaveBeenCalledWith('source', 'target')
  expect(screen.queryByRole('button', { name: /Activate|Switch|Start new course/ })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Close comparison' }))
  expect(screen.queryByLabelText('Course version comparison')).not.toBeInTheDocument()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Compare course versions' })).toHaveFocus())
  expect(api.getUpgradePreview).toHaveBeenCalledOnce()
})

it('explains an empty offer list without offering a draft or implying lost progress', async () => {
  vi.mocked(api.getUpgradeOptions).mockResolvedValue({ ...options, courses: [] })
  render(<UpgradeComparison enrollmentId="source" onRefreshCourse={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Compare course versions' }))
  expect(await screen.findByText(/No other course version is currently offered/)).toBeInTheDocument()
  expect(api.getUpgradePreview).not.toHaveBeenCalled()
})

it.each(['source', 'target', 'digest'])('rejects a mismatched %s preview', async mismatch => {
  const wrong = structuredClone(preview)
  if (mismatch === 'source') wrong.source.enrollment_id = 'someone-else'
  if (mismatch === 'target') wrong.target.course_version = 'unoffered'
  if (mismatch === 'digest') wrong.target.manifest_sha256 = 'c'.repeat(64)
  vi.mocked(api.getUpgradePreview).mockResolvedValue(wrong)
  render(<UpgradeComparison enrollmentId="source" onRefreshCourse={vi.fn()} />)
  await openComparison()
  expect(await screen.findByRole('alert')).toHaveTextContent('comparison could not be loaded')
  expect(screen.queryByLabelText('Course version comparison')).not.toBeInTheDocument()
})

it('ignores a late comparison after the learner keeps their current course', async () => {
  let finish!: (result: UpgradePreview) => void
  vi.mocked(api.getUpgradePreview).mockReturnValue(new Promise(resolve => { finish = resolve }))
  render(<UpgradeComparison enrollmentId="source" onRefreshCourse={vi.fn()} />)
  await openComparison()
  fireEvent.click(screen.getByRole('button', { name: 'Close course options' }))
  await act(async () => finish(preview))
  expect(screen.queryByLabelText('Course version comparison')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Compare course versions' })).toBeInTheDocument()
})

it('clears old evidence after a failed refresh and requires a current comparison', async () => {
  render(<UpgradeComparison enrollmentId="source" onRefreshCourse={vi.fn()} />)
  await openComparison()
  await screen.findByLabelText('Course version comparison')
  vi.mocked(api.getUpgradePreview).mockRejectedValueOnce(new Error('Offline'))
  fireEvent.click(screen.getByRole('button', { name: 'Compare V5 course' }))
  await screen.findByRole('alert')
  expect(screen.queryByLabelText('Course version comparison')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Retry comparison' }))
  await waitFor(() => expect(api.getUpgradeOptions).toHaveBeenCalledTimes(2))
})

it('offers a course refresh for changed enrollment or work instead of silently comparing another course', async () => {
  const refresh = vi.fn().mockResolvedValue(undefined)
  vi.mocked(api.getUpgradePreview).mockRejectedValueOnce(new ApiError(409, 'Changed'))
  render(<UpgradeComparison enrollmentId="source" onRefreshCourse={refresh} />)
  await openComparison()
  expect(await screen.findByRole('alert')).toHaveTextContent('course or saved work changed')
  fireEvent.click(screen.getByRole('button', { name: 'Refresh my course' }))
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce())
  expect(api.getUpgradePreview).toHaveBeenCalledOnce()
  expect(screen.queryByLabelText('Course version comparison')).not.toBeInTheDocument()
})

it('keeps a preserved original certificate distinct from target requirements', async () => {
  vi.mocked(api.getUpgradePreview).mockResolvedValue({ ...preview, source: { ...preview.source, certified: true, credential_preserved: true } })
  render(<UpgradeComparison enrollmentId="source" onRefreshCourse={vi.fn()} />)
  await openComparison()
  expect(await screen.findByText(/original earned certificate remains available/)).toHaveTextContent('does not become a certificate for the other course')
  expect(screen.getByText('3 required outcomes · 0 confirmed for transfer')).toBeInTheDocument()
})

const preservation = {
  policy: 'retain_with_original_enrollment' as const, source_enrollment_id: 'source', read_only: true as const, can_activate: false as const, credit_transferred: false as const,
  reconciliation_required_count: 1, plan_sha256: 'f'.repeat(64), entries: [{ kind: 'saved_lab_runs', label: 'Lab run', record_id: '1'.repeat(32), module_id: 'foundations', module_title: 'Original Foundations', state: 'uncertain',
    proposed_action: 'reconcile_operation' as const, reconciliation_required: true, explanation: 'Resolve the original run and any external effects before a switch. Do not rerun it to discover whether it finished.' }],
}
it('explains unresolved saved work without starting another operation or offering activation', async () => {
  vi.mocked(api.getUpgradePreview).mockResolvedValue({ ...preview, work_in_flight: false, preservation_plan: preservation })
  render(<UpgradeComparison enrollmentId="source" onRefreshCourse={vi.fn()} />)
  await openComparison()
  fireEvent.click(await screen.findByText('Saved work preservation plan'))
  expect(screen.getByText(/1 saved operations need resolution/)).toBeInTheDocument()
  expect(screen.getByText('Lab run · Original Foundations')).toBeInTheDocument()
  expect(screen.getByText(preservation.entries[0].explanation)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Activate|Switch|Retry run/ })).toBeNull()
})
it.each(['source', 'count', 'action'])('rejects inconsistent preservation plan %s', async reason => {
  const plan = structuredClone(preservation)
  if (reason === 'source') plan.source_enrollment_id = 'foreign'
  if (reason === 'count') plan.reconciliation_required_count = 0
  if (reason === 'action') plan.entries[0].reconciliation_required = false
  vi.mocked(api.getUpgradePreview).mockResolvedValue({ ...preview, preservation_plan: plan })
  render(<UpgradeComparison enrollmentId="source" onRefreshCourse={vi.fn()} />)
  await openComparison()
  expect(await screen.findByRole('alert')).toHaveTextContent('comparison could not be loaded')
  expect(screen.queryByLabelText('Course version comparison')).toBeNull()
})
