import { StrictMode } from 'react'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { ExaminerValidationDrawer } from './ExaminerValidationDrawer'
import { claimVerificationRequest, releaseVerificationRequest, setExaminerAdditions } from '../../api/library'
import type { VerificationRequest } from '../../types/library'

vi.mock('focus-trap-react', () => ({ FocusTrap: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('../../api/library', () => ({ claimVerificationRequest: vi.fn(), releaseVerificationRequest: vi.fn(), setExaminerAdditions: vi.fn() }))
const request = { uuid: 'request-1', item_kind: 'workflow' } as VerificationRequest
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(claimVerificationRequest).mockResolvedValue({ ok: true, claimed_at: '' })
  vi.mocked(releaseVerificationRequest).mockResolvedValue({ ok: true })
  vi.mocked(setExaminerAdditions).mockResolvedValue({ ok: true })
})
function setup(req = request) {
  const onClose = vi.fn(), onSaved = vi.fn()
  return { ...render(<StrictMode><ExaminerValidationDrawer request={req} currentUserId="reviewer" onClose={onClose} onSaved={onSaved} /></StrictMode>), onClose, onSaved }
}
it('requires a confirmed claim, retries failure, and releases it on unmount', async () => {
  vi.mocked(claimVerificationRequest).mockRejectedValueOnce(new Error('Claim denied'))
  const { unmount } = setup()
  expect(screen.getByRole('button', { name: 'Save additions' })).toBeDisabled()
  fireEvent.click(await screen.findByRole('button', { name: 'Retry claim' }))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save additions' })).toBeEnabled())
  expect(setExaminerAdditions).not.toHaveBeenCalled()
  unmount()
  await waitFor(() => expect(releaseVerificationRequest).toHaveBeenCalledOnce())
})
it('releases a claim that completes after the drawer was closed', async () => {
  let accept!: (value: { ok: boolean; claimed_at: string }) => void
  vi.mocked(claimVerificationRequest).mockImplementation(() => new Promise(resolve => { accept = resolve }))
  const { unmount } = setup()
  await waitFor(() => expect(claimVerificationRequest).toHaveBeenCalledOnce())
  unmount()
  await act(async () => accept({ ok: true, claimed_at: '' }))
  await waitFor(() => expect(releaseVerificationRequest).toHaveBeenCalledOnce())
})
it('retains a failed draft and blocks duplicate writes or dismissal while saving', async () => {
  let reject!: (error: Error) => void
  vi.mocked(setExaminerAdditions).mockImplementationOnce(() => new Promise((_, no) => { reject = no }))
  const { onClose, onSaved } = setup()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save additions' })).toBeEnabled())
  fireEvent.click(screen.getByRole('button', { name: 'Add regression input' }))
  fireEvent.change(screen.getByLabelText('Regression input 1'), { target: { value: 'Check sponsor deadline' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save additions' }))
  fireEvent.keyDown(document, { key: 'Escape' })
  fireEvent.click(screen.getByRole('button', { name: 'Saving…' }))
  expect(onClose).not.toHaveBeenCalled()
  expect(setExaminerAdditions).toHaveBeenCalledOnce()
  await act(async () => reject(new Error('Save unavailable')))
  expect(screen.getByRole('alert')).toHaveTextContent('Save unavailable')
  expect(screen.getByLabelText('Regression input 1')).toHaveValue('Check sponsor deadline')
  fireEvent.click(screen.getByRole('button', { name: 'Save additions' }))
  await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
  expect(onClose).toHaveBeenCalledOnce()
})
it('keeps another reviewer’s workshop read-only without claiming or saving', () => {
  setup({ ...request, claimed_by_user_id: 'other-reviewer' })
  expect(screen.getByRole('button', { name: 'Save additions' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Add regression input' })).toBeDisabled()
  expect(claimVerificationRequest).not.toHaveBeenCalled()
})
