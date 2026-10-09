import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/certification'
import type { CoursePreparationStatus, CourseSelectionReceipt } from '../../api/certification'
import { CourseSelectionNotice } from './CourseSelectionNotice'

vi.mock('../../api/certification', () => ({ getCourseSelectionStatus: vi.fn(), confirmCourseSelection: vi.fn(), stopCoursePreparation: vi.fn() }))
const receipt: CourseSelectionReceipt = {
  request_id: 'a'.repeat(32), kind: 'optional_upgrade_selection.1', receipt_sha256: 'b'.repeat(64),
  source_enrollment_id: 'c'.repeat(32), target_enrollment_id: 'd'.repeat(32), target_course_version: 'original-choice-version',
  revision: 1, selected_at: '2026-10-07T12:00:00Z', action: 'activate_optional_upgrade',
  credit_transferred: false, histories_preserved: true,
}
const status = { read_only: true as const, current_enrollment_id: receipt.target_enrollment_id, pending: receipt }
const preparation: CoursePreparationStatus = { state: 'preparing', read_only: true, selection_changed: false, credit_changed: false,
  request_id: '1'.repeat(32), preview_sha256: '2'.repeat(64), enrollment_id: receipt.target_enrollment_id,
  course_version: 'saved-course', original_request_id: '3'.repeat(32), write_id: '4'.repeat(32), operation: 'activate_optional_upgrade' }
const stopped = { kind: 'selection_preparation_recovery.1' as const, recovery_id: preparation.request_id,
  enrollment_id: preparation.enrollment_id, original_request_id: preparation.original_request_id,
  original_write_id: preparation.write_id, status: 'preparation_stopped' as const,
  selection_changed: false as const, credit_changed: false as const, assessments_repeated: false as const }
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.getCourseSelectionStatus).mockResolvedValue(status)
  vi.mocked(api.confirmCourseSelection).mockResolvedValue({ confirmed: true, selection_changed: false, receipt })
  vi.mocked(api.stopCoursePreparation).mockResolvedValue(stopped)
})

it('discovers newly interrupted preparation on an explicit refresh even when the enrollment did not change', async () => {
  vi.mocked(api.getCourseSelectionStatus).mockResolvedValueOnce({ read_only: true, current_enrollment_id: preparation.enrollment_id, pending: null })
  const view = render(<CourseSelectionNotice enrollmentId={preparation.enrollment_id} refreshKey={0} onRefreshCourse={vi.fn()} />)
  await waitFor(() => expect(api.getCourseSelectionStatus).toHaveBeenCalledOnce())
  vi.mocked(api.getCourseSelectionStatus).mockResolvedValue({ read_only: true, current_enrollment_id: preparation.enrollment_id, pending: null, preparation })
  view.rerender(<CourseSelectionNotice enrollmentId={preparation.enrollment_id} refreshKey={1} onRefreshCourse={vi.fn()} />)
  await screen.findByRole('button', { name: 'Stop course-change preparation' })
  expect(api.getCourseSelectionStatus).toHaveBeenCalledTimes(2)
  expect(api.stopCoursePreparation).not.toHaveBeenCalled()
})

it('reads on mount and confirms the exact original choice only on a learner click', async () => {
  const refresh = vi.fn().mockResolvedValue(undefined)
  render(<CourseSelectionNotice enrollmentId={receipt.target_enrollment_id} onRefreshCourse={refresh} />)
  const confirm = await screen.findByRole('button', { name: 'Confirm saved course choice' })
  expect(api.confirmCourseSelection).not.toHaveBeenCalled()
  fireEvent.click(confirm)
  expect(await screen.findByRole('status')).toHaveTextContent('saved course choice is confirmed')
  expect(api.confirmCourseSelection).toHaveBeenCalledExactlyOnceWith(receipt)
  expect(refresh).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Refresh my course' }))
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce())
  expect(api.confirmCourseSelection).toHaveBeenCalledTimes(1)
})

it('checks GET status after an uncertain reply and never automatically repeats POST', async () => {
  vi.mocked(api.confirmCourseSelection).mockRejectedValueOnce(new Error('Lost response'))
  render(<CourseSelectionNotice enrollmentId={receipt.target_enrollment_id} onRefreshCourse={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Confirm saved course choice' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('may already have finished')
  expect(screen.queryByRole('button', { name: 'Confirm saved course choice' })).not.toBeInTheDocument()
  vi.mocked(api.getCourseSelectionStatus).mockResolvedValueOnce({ ...status, pending: null })
  fireEvent.click(screen.getByRole('button', { name: 'Refresh switch status' }))
  expect(await screen.findByRole('status')).toHaveTextContent('No course switch is awaiting confirmation')
  expect(api.confirmCourseSelection).toHaveBeenCalledTimes(1)
})

it('can recover the same still-pending receipt after remount without browser storage', async () => {
  const first = render(<CourseSelectionNotice enrollmentId={receipt.target_enrollment_id} onRefreshCourse={vi.fn()} />)
  await screen.findByRole('button', { name: 'Confirm saved course choice' })
  first.unmount()
  render(<CourseSelectionNotice enrollmentId={receipt.target_enrollment_id} onRefreshCourse={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Confirm saved course choice' }))
  await screen.findByRole('status')
  expect(api.confirmCourseSelection).toHaveBeenCalledExactlyOnceWith(receipt)
})

it.each([
  { ...status, read_only: false },
  { ...status, current_enrollment_id: receipt.source_enrollment_id },
  { ...status, pending: { ...receipt, credit_transferred: true } },
  { ...status, pending: { ...receipt, action: 'resume_upgraded_course' } },
  { ...status, pending: { ...receipt, request_id: 'invalid' } },
])('does not offer confirmation for a malformed or mismatched status %#', async invalid => {
  vi.mocked(api.getCourseSelectionStatus).mockResolvedValueOnce(invalid as typeof status)
  render(<CourseSelectionNotice enrollmentId={receipt.target_enrollment_id} onRefreshCourse={vi.fn()} />)
  await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: 'Confirm saved course choice' })).not.toBeInTheDocument()
  expect(api.confirmCourseSelection).not.toHaveBeenCalled()
})

it('ignores a late status from a previous enrollment', async () => {
  let resolve!: (value: typeof status) => void
  vi.mocked(api.getCourseSelectionStatus).mockReturnValueOnce(new Promise(done => { resolve = done }))
  const { rerender } = render(<CourseSelectionNotice enrollmentId={receipt.source_enrollment_id} onRefreshCourse={vi.fn()} />)
  vi.mocked(api.getCourseSelectionStatus).mockResolvedValueOnce({ ...status, pending: null })
  rerender(<CourseSelectionNotice enrollmentId={receipt.target_enrollment_id} onRefreshCourse={vi.fn()} />)
  await act(async () => { resolve(status) })
  expect(screen.queryByRole('region')).not.toBeInTheDocument()
  expect(api.confirmCourseSelection).not.toHaveBeenCalled()
})

it('rejects a confirmation response belonging to another receipt', async () => {
  vi.mocked(api.confirmCourseSelection).mockResolvedValueOnce({ confirmed: true, selection_changed: false,
    receipt: { ...receipt, request_id: 'e'.repeat(32) } })
  render(<CourseSelectionNotice enrollmentId={receipt.target_enrollment_id} onRefreshCourse={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Confirm saved course choice' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})

it.each(['return_to_original_course', 'resume_upgraded_course'] as const)('describes the saved %s without proposing another switch', async action => {
  vi.mocked(api.getCourseSelectionStatus).mockResolvedValueOnce({ ...status, pending: { ...receipt, kind: 'saved_course_selection.1', action } })
  render(<CourseSelectionNotice enrollmentId={receipt.target_enrollment_id} onRefreshCourse={vi.fn()} />)
  await screen.findByRole('button', { name: 'Confirm saved course choice' })
  expect(screen.getByText(/Both courses keep/)).toBeInTheDocument()
  expect(screen.getByText(action === 'return_to_original_course' ? /return to the original course was saved/ : /return to the saved upgrade was saved/)).toBeInTheDocument()
})

it.each(['preparing', 'recovery_pending'] as const)('stops only the reviewed %s preparation after an explicit click', async state => {
  const reviewed = { ...preparation, state }
  vi.mocked(api.getCourseSelectionStatus).mockResolvedValueOnce({ ...status, pending: null, preparation: reviewed })
  render(<CourseSelectionNotice enrollmentId={preparation.enrollment_id} onRefreshCourse={vi.fn()} />)
  const button = await screen.findByRole('button', { name: state === 'preparing' ? 'Stop course-change preparation' : 'Finish stopping preparation' })
  expect(api.stopCoursePreparation).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Confirm saved course choice' })).not.toBeInTheDocument()
  fireEvent.click(button)
  expect(await screen.findByRole('status')).toHaveTextContent('Course-change preparation stopped')
  expect(api.stopCoursePreparation).toHaveBeenCalledExactlyOnceWith(reviewed)
  expect(api.confirmCourseSelection).not.toHaveBeenCalled()
})

it('uses GET after an uncertain stop and discovers the original in-progress recovery after remount', async () => {
  vi.mocked(api.getCourseSelectionStatus).mockResolvedValue({ ...status, pending: null, preparation })
  vi.mocked(api.stopCoursePreparation).mockRejectedValueOnce(new Error('Lost acknowledgement'))
  const first = render(<CourseSelectionNotice enrollmentId={preparation.enrollment_id} onRefreshCourse={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Stop course-change preparation' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: 'Stop course-change preparation' })).not.toBeInTheDocument()
  vi.mocked(api.getCourseSelectionStatus).mockResolvedValue({ ...status, pending: null, preparation: { ...preparation, state: 'recovery_pending' } })
  fireEvent.click(screen.getByRole('button', { name: 'Refresh switch status' }))
  await screen.findByRole('button', { name: 'Finish stopping preparation' })
  expect(api.stopCoursePreparation).toHaveBeenCalledTimes(1)
  first.unmount()
  render(<CourseSelectionNotice enrollmentId={preparation.enrollment_id} onRefreshCourse={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Finish stopping preparation' }))
  await screen.findByRole('status')
  expect(api.stopCoursePreparation).toHaveBeenCalledTimes(2)
  expect(vi.mocked(api.stopCoursePreparation).mock.calls[1][0].request_id).toBe(preparation.request_id)
})

it.each([
  { ...preparation, operation: 'complete_module' }, { ...preparation, enrollment_id: receipt.source_enrollment_id },
  { ...preparation, preview_sha256: 'invalid' }, { ...preparation, credit_changed: true },
])('rejects malformed or unrelated preparation %#', async invalid => {
  vi.mocked(api.getCourseSelectionStatus).mockResolvedValueOnce({ ...status, pending: null, preparation: invalid as CoursePreparationStatus })
  render(<CourseSelectionNotice enrollmentId={preparation.enrollment_id} onRefreshCourse={vi.fn()} />)
  await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: 'Stop course-change preparation' })).not.toBeInTheDocument()
  expect(api.stopCoursePreparation).not.toHaveBeenCalled()
})

it('rejects a stop result for a different worker', async () => {
  vi.mocked(api.getCourseSelectionStatus).mockResolvedValueOnce({ ...status, pending: null, preparation })
  vi.mocked(api.stopCoursePreparation).mockResolvedValueOnce({ ...stopped, original_write_id: '5'.repeat(32) })
  render(<CourseSelectionNotice enrollmentId={preparation.enrollment_id} onRefreshCourse={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Stop course-change preparation' }))
  await screen.findByRole('alert')
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})
