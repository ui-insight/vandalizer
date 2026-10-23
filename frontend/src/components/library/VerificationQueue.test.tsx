import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { VerificationQueue } from './VerificationQueue'
import { listVerificationQueue, myVerificationRequests, updateVerificationStatus } from '../../api/library'
import type { VerificationRequest } from '../../types/library'

let examiner = false
const navigate = vi.fn()
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => navigate }))
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: { user_id: 'author', is_examiner: examiner } }) }))
vi.mock('../../api/library', () => ({ listVerificationQueue: vi.fn(), myVerificationRequests: vi.fn(), updateVerificationStatus: vi.fn() }))
vi.mock('./ExaminerValidationDrawer', () => ({ ExaminerValidationDrawer: () => null }))
const request = { id: 'request-1', uuid: 'request-1', item_kind: 'knowledge_base', item_id: 'kb-1', item_name: 'Sponsor policy', status: 'returned', reviewer_notes: 'Add a deadline example and resubmit.' } as VerificationRequest
beforeEach(() => {
  examiner = false
  vi.clearAllMocks()
  vi.mocked(myVerificationRequests).mockResolvedValue({ requests: [request] })
  vi.mocked(listVerificationQueue).mockResolvedValue({ requests: [{ ...request, status: 'submitted' }] })
})
it('loads only the author’s own requests and exposes feedback without examiner actions', async () => {
  render(<VerificationQueue />)
  expect(await screen.findByText('Reviewer: Add a deadline example and resubmit.')).toBeVisible()
  expect(listVerificationQueue).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: 'Requests' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Review' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Workshop' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Open item' }))
  expect(navigate).toHaveBeenCalledWith({ to: '/', search: expect.objectContaining({ kb: 'kb-1', workflow: undefined, project: undefined }) })
})
it('requires useful feedback before sending back and preserves it after a failed decision', async () => {
  examiner = true
  vi.mocked(updateVerificationStatus).mockRejectedValue(new Error('Review unavailable'))
  render(<VerificationQueue />)
  fireEvent.click(await screen.findByRole('button', { name: 'Review' }))
  fireEvent.click(screen.getByRole('button', { name: 'Send back' }))
  expect(updateVerificationStatus).not.toHaveBeenCalled()
  const notes = screen.getByRole('textbox', { name: 'Review notes for Sponsor policy' })
  fireEvent.change(notes, { target: { value: 'Add a deadline example.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Send back' }))
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Review unavailable'))
  expect(notes).toHaveValue('Add a deadline example.')
})
