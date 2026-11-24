import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/admin'
import { CertificationRecoveryReview } from './CertificationRecoveryReview'

vi.mock('../../api/admin', () => ({ getCertificationRecovery: vi.fn(), recoverCertificationCompletion: vi.fn() }))
const item: api.CertificationProgressItem = { user_id: 'learner', enrollment_id: 'enrollment', name: 'Alex', email: null, course_title: 'Enrolled course', level: 'novice', total_xp: 125, modules_completed: 1, modules_total: 11, certified: false, certified_at: null, last_activity_date: null, unlocked: false, updated_at: null }
const review: api.CertificationRecoverySnapshot = { user_id: 'learner', enrollment_id: 'enrollment', course_version: 'course-1', course_title: 'Enrolled course', manifest_sha256: 'a'.repeat(64), selection_revision: 0, review_sha256: 'b'.repeat(64), kind: 'attempt', write_id: null, attempt_id: 'c'.repeat(32), module_id: 'foundations', module_title: 'Foundations', attempt_state: 'evaluating', in_flight: false, can_recover: true, explanation: 'Reconcile the saved submission without regrading.', operation: null, started_at: null, total_xp: 125, certified: false }
const receipt: api.CertificationRecoveryReceipt = { request_id: 'd'.repeat(32), enrollment_id: 'enrollment', status: 'interrupted_before_grade', attempt_id: 'c'.repeat(32), reason: 'Worker interrupted', actor_user_id: 'admin' }
beforeEach(() => { vi.resetAllMocks(); vi.mocked(api.getCertificationRecovery).mockResolvedValue({ review, can_apply: true, history: [] }); vi.mocked(api.recoverCertificationCompletion).mockResolvedValue(receipt) })

it('requires a recorded reason and review confirmation before mutating', async () => {
  render(<CertificationRecoveryReview item={item} onClose={vi.fn()} />)
  const apply = await screen.findByRole('button', { name: 'Apply reviewed recovery' })
  expect(apply).toBeDisabled()
  expect(api.recoverCertificationCompletion).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('Reason for recovery'), { target: { value: 'Worker interrupted' } })
  expect(apply).toBeDisabled()
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(apply)
  await waitFor(() => expect(api.recoverCertificationCompletion).toHaveBeenCalledWith('learner', 'enrollment', { request_id: expect.stringMatching(/^[a-f0-9]{32}$/), review_sha256: review.review_sha256, reason: 'Worker interrupted' }))
  expect(await screen.findByText('The interrupted evaluation ended without an award. The learner can submit a new assessment.')).toBeInTheDocument()
})

it('reuses the exact request, snapshot and reason after an uncertain response', async () => {
  vi.mocked(api.recoverCertificationCompletion).mockRejectedValueOnce(new Error('Response unavailable'))
  render(<CertificationRecoveryReview item={item} onClose={vi.fn()} />)
  await screen.findByRole('button', { name: 'Apply reviewed recovery' })
  fireEvent.change(screen.getByLabelText('Reason for recovery'), { target: { value: 'Worker interrupted' } })
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: 'Apply reviewed recovery' }))
  await screen.findByText('Response unavailable')
  expect(screen.getByLabelText('Reason for recovery')).toBeDisabled()
  fireEvent.click(screen.getByRole('button', { name: 'Retry this recovery' }))
  await waitFor(() => expect(api.recoverCertificationCompletion).toHaveBeenCalledTimes(2))
  const calls = vi.mocked(api.recoverCertificationCompletion).mock.calls
  expect(calls[1]).toEqual(calls[0])
})

it('can resume a durable reviewed request after reopening, without inventing a new action', async () => {
  vi.mocked(api.getCertificationRecovery).mockResolvedValue({ review: { ...review, can_recover: false }, can_apply: true, history: [{ request_id: receipt.request_id, actor_user_id: 'admin', reason: receipt.reason, state: 'started', created_at: '2026-10-05T12:00:00Z', attempt_id: review.attempt_id, write_id: null, review_sha256: review.review_sha256, review, can_resume: true, result: null }] })
  render(<CertificationRecoveryReview item={item} onClose={vi.fn()} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Resume reviewed recovery' }))
  expect(api.recoverCertificationCompletion).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Retry this recovery' }))
  await waitFor(() => expect(api.recoverCertificationCompletion).toHaveBeenCalledWith('learner', 'enrollment', { request_id: receipt.request_id, review_sha256: review.review_sha256, reason: receipt.reason }))
})

it('keeps staff inspection read-only', async () => {
  vi.mocked(api.getCertificationRecovery).mockResolvedValue({ review, can_apply: false, history: [] })
  render(<CertificationRecoveryReview item={item} onClose={vi.fn()} />)
  await screen.findByText('Staff can inspect this state. A full administrator must apply recovery.')
  expect(screen.queryByRole('button', { name: 'Apply reviewed recovery' })).not.toBeInTheDocument()
  expect(api.recoverCertificationCompletion).not.toHaveBeenCalled()
})
