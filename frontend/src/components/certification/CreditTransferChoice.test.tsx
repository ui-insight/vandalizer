import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import * as api from '../../api/creditTransfer'
import type { CompletionResult } from '../../types/certification'
import { CreditTransferChoice } from './CreditTransferChoice'

vi.mock('../../api/creditTransfer', () => ({ previewCreditTransfer: vi.fn(), applyCreditTransfer: vi.fn(), getCreditTransfer: vi.fn() }))
const target = 'a'.repeat(32), source = 'b'.repeat(32), hash = 'c'.repeat(64)
const request: api.CreditTransferRequest = { request_id: 'd'.repeat(32), source_enrollment_id: source,
  target_enrollment_id: target, module_id: 'ai_literacy', preview_sha256: hash,
  consent: 'transfer_reviewed_module_credit_preserve_original_no_new_xp_reward' }
const preview: api.CreditTransferPreview = { source_enrollment_id: source, source_course_title: 'Original course',
  target_enrollment_id: target, target_course_title: 'Upgraded course', source_manifest_sha256: hash,
  target_manifest_sha256: hash, preview_sha256: hash, read_only: true, credit_transferred: false, xp_earned: 0,
  explanation: 'Original credit is preserved; carried XP is not a new reward.',
  modules: [{ module_id: 'ai_literacy', title: 'AI Literacy', outcome_count: 3, eligible: true,
    completed: false, xp_carried: 100, xp_earned: 0, reason: 'Every required outcome has original evidence.', request }] }
const result = { attempt_id: request.request_id, enrollment_id: target, module_id: 'ai_literacy', manifest_sha256: hash,
  source_enrollment_id: source, credit_origin: 'transferred', xp_earned: 0, xp_carried: 100 } as CompletionResult

beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear()
  vi.mocked(api.previewCreditTransfer).mockResolvedValue(structuredClone(preview))
  vi.mocked(api.applyCreditTransfer).mockResolvedValue(result)
  vi.mocked(api.getCreditTransfer).mockResolvedValue({ request, state: 'applied', read_only: true, result })
})
async function choose() {
  fireEvent.click(screen.getByRole('button', { name: 'Review credit eligibility' }))
  fireEvent.click(await screen.findByRole('button', { name: 'Review transfer: AI Literacy' }))
}
async function consentAndSend() {
  await choose()
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: 'Transfer reviewed credit' }))
}

it('requires separate explicit consent and identifies carried credit without a new reward', async () => {
  const refresh = vi.fn().mockResolvedValue(undefined)
  render(<CreditTransferChoice enrollmentId={target} onRefreshCourse={refresh} />)
  expect(api.previewCreditTransfer).not.toHaveBeenCalled()
  await choose()
  expect(screen.getByRole('button', { name: 'Transfer reviewed credit' })).toBeDisabled()
  expect(api.applyCreditTransfer).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: 'Transfer reviewed credit' }))
  await screen.findByText(/100 XP carried into this course and 0 new XP earned/)
  expect(api.applyCreditTransfer).toHaveBeenCalledExactlyOnceWith(request)
  expect(refresh).toHaveBeenCalledOnce()
  expect(localStorage.getItem(`certification-credit-transfer:${target}`)).toBeNull()
})

it('checks the saved result after a lost response without resubmitting the write', async () => {
  vi.mocked(api.applyCreditTransfer).mockRejectedValueOnce(new Error('Lost response'))
  render(<CreditTransferChoice enrollmentId={target} onRefreshCourse={vi.fn()} />)
  await consentAndSend()
  fireEvent.click(await screen.findByRole('button', { name: 'Check saved transfer' }))
  await screen.findByText(/credit recorded/)
  expect(api.applyCreditTransfer).toHaveBeenCalledOnce()
  expect(api.getCreditTransfer).toHaveBeenCalledExactlyOnceWith(request.request_id)
})

it('restores an uncertain original request after reopening without performing a write on mount', async () => {
  localStorage.setItem(`certification-credit-transfer:${target}`, JSON.stringify({ request, manifest: hash, title: 'AI Literacy', xp: 100 }))
  render(<CreditTransferChoice enrollmentId={target} onRefreshCourse={vi.fn()} />)
  expect(api.applyCreditTransfer).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Check saved transfer' }))
  await screen.findByText(/credit recorded/)
  expect(api.applyCreditTransfer).not.toHaveBeenCalled()
})

it('keeps successful credit distinct from a failed course refresh', async () => {
  render(<CreditTransferChoice enrollmentId={target} onRefreshCourse={vi.fn().mockRejectedValue(new Error('Offline'))} />)
  await consentAndSend()
  await screen.findByText(/The transfer was saved. Refresh the course/)
  expect(screen.queryByRole('button', { name: 'Transfer reviewed credit' })).toBeNull()
  expect(api.applyCreditTransfer).toHaveBeenCalledOnce()
})

it('does not submit when the browser cannot preserve the original request', async () => {
  render(<CreditTransferChoice enrollmentId={target} onRefreshCourse={vi.fn()} />)
  await choose()
  const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Unavailable') })
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: 'Transfer reviewed credit' }))
  await screen.findByText(/No transfer was sent/)
  expect(api.applyCreditTransfer).not.toHaveBeenCalled()
  storage.mockRestore()
})

it('does not accept another course receipt or claim an XP award as a transfer', async () => {
  vi.mocked(api.applyCreditTransfer).mockResolvedValue({ ...result, xp_earned: 100 })
  const refresh = vi.fn()
  render(<CreditTransferChoice enrollmentId={target} onRefreshCourse={refresh} />)
  await consentAndSend()
  await screen.findByRole('button', { name: 'Check saved transfer' })
  expect(refresh).not.toHaveBeenCalled()
  expect(screen.queryByText(/credit recorded/)).toBeNull()
})

it('fences a late reply after leaving this enrollment', async () => {
  let finish!: (value: CompletionResult) => void
  vi.mocked(api.applyCreditTransfer).mockReturnValue(new Promise(resolve => { finish = resolve }))
  const refresh = vi.fn()
  const view = render(<CreditTransferChoice enrollmentId={target} onRefreshCourse={refresh} />)
  await consentAndSend()
  await waitFor(() => expect(api.applyCreditTransfer).toHaveBeenCalledOnce())
  view.unmount()
  await act(async () => finish(result))
  expect(refresh).not.toHaveBeenCalled()
  expect(localStorage.getItem(`certification-credit-transfer:${target}`)).not.toBeNull()
})
