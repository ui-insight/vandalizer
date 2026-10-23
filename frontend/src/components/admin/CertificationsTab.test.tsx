import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { CertificationsTab } from './CertificationsTab'
import type { CertificationProgressItem } from '../../api/admin'

const mockGetCertificationProgressList = vi.fn()
const mockSetCertificationUnlock = vi.fn()
const mockGetCertificationProgressDetail = vi.fn()
const mockToast = vi.fn()

vi.mock('../../api/admin', () => ({
  getCertificationProgressDetail: (...args: unknown[]) => mockGetCertificationProgressDetail(...args),
  getCertificationProgressList: (...args: unknown[]) => mockGetCertificationProgressList(...args),
  setCertificationUnlock: (...args: unknown[]) => mockSetCertificationUnlock(...args),
}))

vi.mock('../../contexts/ToastContext', () => ({
  useToast: () => ({ toast: mockToast }),
}))

const item: CertificationProgressItem = {
  user_id: 'user-1',
  name: 'Target User',
  email: 'target@example.com',
  level: 'novice',
  total_xp: 100,
  modules_completed: 2,
  modules_total: 5,
  certified: false,
  certified_at: null,
  last_activity_date: '2026-01-01',
  unlocked: false,
  updated_at: null,
}

beforeEach(() => {
  mockGetCertificationProgressList.mockReset().mockResolvedValue({ items: [item], total: 1, capped: false })
  mockSetCertificationUnlock.mockReset()
  mockGetCertificationProgressDetail.mockReset()
  mockToast.mockReset()
})

it('does not offer a staff prerequisite override for a course with flexible study order', async () => {
  mockGetCertificationProgressList.mockResolvedValue({ items: [{ ...item, enrollment_id: 'flexible-course',
    course_title: 'Agentic certification', course_version: 'v5', learning_order: 'any_order',
    progression_policy_id: 'required-outcomes-flexible-order.1', can_unlock: false }], total: 1, capped: false })
  render(<CertificationsTab />)
  expect(await screen.findByText('Any study order')).toBeInTheDocument()
  expect(screen.getByText('All required outcomes still apply.')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Unlock prerequisites/ })).toBeNull()
  expect(mockSetCertificationUnlock).not.toHaveBeenCalled()
})

describe('CertificationsTab — success', () => {
  it('renders the progress list on success', async () => {
    render(<CertificationsTab />)
    await waitFor(() => expect(screen.getByText('Target User')).toBeInTheDocument())
    expect(screen.getByText('2/5')).toBeInTheDocument()
  })
})

describe('CertificationsTab — unlock toggle', () => {
  it('requires a reason before recording the access change', async () => {
    mockSetCertificationUnlock.mockResolvedValue({ user_id: 'user-1', unlocked: true })
    render(<CertificationsTab />)
    await waitFor(() => expect(screen.getByText('Target User')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Unlock prerequisites for Target User' }))
    expect(mockSetCertificationUnlock).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Save access change' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Reason for access change'), { target: { value: 'Restore requested course access' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save access change' }))
    await waitFor(() => expect(mockSetCertificationUnlock).toHaveBeenCalledWith('user-1', {
      unlocked: true, reason: 'Restore requested course access', request_id: expect.stringMatching(/^[a-f0-9]{32}$/),
    }, undefined))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Re-lock prerequisites for Target User' })).toBeInTheDocument())
  })

  it('does not leave the row flipped and surfaces an error on a rejected unlock (regression for plan 004)', async () => {
    mockSetCertificationUnlock.mockRejectedValue(new Error('Server rejected the change'))
    render(<CertificationsTab />)
    await waitFor(() => expect(screen.getByText('Target User')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Unlock prerequisites for Target User' }))
    fireEvent.change(screen.getByLabelText('Reason for access change'), { target: { value: 'Restore requested course access' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save access change' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Server rejected the change')
    // Row must still read "Unlock" (not flipped to "Unlocked") since the write failed.
    expect(screen.getByRole('button', { name: 'Unlock prerequisites for Target User' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Re-lock prerequisites for Target User' })).not.toBeInTheDocument()
  })
})

describe('CertificationsTab — server pagination', () => {
  it('offers the next page when more records exist', async () => {
    mockGetCertificationProgressList.mockResolvedValue({ items: [item], total: 5000, capped: true })
    render(<CertificationsTab />)
    await waitFor(() => expect(screen.getByText('Target User')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Next page' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }))
    await waitFor(() => expect(mockGetCertificationProgressList).toHaveBeenCalledWith(100, 100, ''))
  })

  it('disables the next page after the final record', async () => {
    mockGetCertificationProgressList.mockResolvedValue({ items: [item], total: 1, capped: false })
    render(<CertificationsTab />)
    await waitFor(() => expect(screen.getByText('Target User')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled()
  })
})

it('retries an uncertain access change with its original reason and identity', async () => {
  mockSetCertificationUnlock.mockRejectedValueOnce(new Error('Response unavailable')).mockResolvedValueOnce({ user_id: 'user-1', unlocked: true })
  render(<CertificationsTab />)
  fireEvent.click(await screen.findByRole('button', { name: 'Unlock prerequisites for Target User' }))
  fireEvent.change(screen.getByLabelText('Reason for access change'), { target: { value: 'Restore requested course access' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save access change' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Response unavailable')
  expect(screen.getByLabelText('Reason for access change')).toBeDisabled()
  const first = mockSetCertificationUnlock.mock.calls[0]
  fireEvent.click(screen.getByRole('button', { name: 'Retry same access change' }))
  await waitFor(() => expect(mockSetCertificationUnlock).toHaveBeenCalledTimes(2))
  expect(mockSetCertificationUnlock.mock.calls[1]).toEqual(first)
  expect(await screen.findByRole('button', { name: 'Re-lock prerequisites for Target User' })).toBeInTheDocument()
  await waitFor(() => expect(screen.getByRole('button', { name: 'Re-lock prerequisites for Target User' })).toHaveFocus())
})

it('closing an unsubmitted access change writes nothing and restores focus', async () => {
  render(<CertificationsTab />)
  const trigger = await screen.findByRole('button', { name: 'Unlock prerequisites for Target User' })
  fireEvent.click(trigger)
  fireEvent.change(screen.getByLabelText('Reason for access change'), { target: { value: 'An optional reason draft' } })
  fireEvent.click(screen.getByRole('button', { name: 'Close access change' }))
  expect(mockSetCertificationUnlock).not.toHaveBeenCalled()
  await waitFor(() => expect(trigger).toHaveFocus())
})

it('pins an unlock to the selected enrollment and leaves preserved history read-only', async () => {
  mockGetCertificationProgressList.mockResolvedValue({ items: [
    { ...item, progress_id: 'old-progress', enrollment_id: 'old-enrollment', course_title: 'Previous course', course_version: 'old', is_active: false, can_unlock: false },
    { ...item, progress_id: 'new-progress', enrollment_id: 'new-enrollment', course_title: 'Selected course', course_version: 'new', is_active: true, can_unlock: true },
  ], total: 2, capped: false })
  mockSetCertificationUnlock.mockResolvedValue({ user_id: item.user_id, unlocked: true })
  render(<CertificationsTab />)
  const buttons = await screen.findAllByRole('button', { name: /^Unlock prerequisites for Target User/ })
  expect(buttons[0]).toBeDisabled()
  expect(buttons[1]).toBeEnabled()
  fireEvent.click(buttons[1])
  fireEvent.change(screen.getByLabelText('Reason for access change'), { target: { value: 'Restore requested course access' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save access change' }))
  await waitFor(() => expect(mockSetCertificationUnlock).toHaveBeenCalledWith('user-1', {
    unlocked: true, reason: 'Restore requested course access', request_id: expect.stringMatching(/^[a-f0-9]{32}$/),
  }, 'new-enrollment'))
  expect(screen.getByRole('button', { name: 'Unlock prerequisites for Target User — Previous course' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Re-lock prerequisites for Target User — Selected course' })).toBeEnabled()
})

it('opens the exact enrollment in a read-only status view and returns focus on close', async () => {
  const enrolled = { ...item, progress_id: 'p1', enrollment_id: 'e1', course_version: 'v5', course_title: 'Original course' }
  mockGetCertificationProgressList.mockResolvedValue({ items: [enrolled], total: 1, capped: false })
  mockGetCertificationProgressDetail.mockResolvedValue({ ...enrolled, modules: {}, support_summary: null })
  render(<CertificationsTab />)
  const open = await screen.findByRole('button', { name: 'View learning status for Target User — Original course' })
  fireEvent.click(open)
  expect(await screen.findByText('Saved learning details are unavailable. No assessment or reading position is inferred.')).toBeInTheDocument()
  expect(mockGetCertificationProgressDetail).toHaveBeenCalledWith('user-1', 'e1')
  fireEvent.click(screen.getByRole('button', { name: 'Close status' }))
  await waitFor(() => expect(open).toHaveFocus())
  expect(mockSetCertificationUnlock).not.toHaveBeenCalled()
})

 it('searches all server records and resets pagination', async () => {
  mockGetCertificationProgressList.mockResolvedValue({ items: [item], total: 501, capped: true })
  render(<CertificationsTab />)
  fireEvent.click(await screen.findByRole('button', { name: 'Next page' }))
  await waitFor(() => expect(mockGetCertificationProgressList).toHaveBeenCalledWith(100, 100, ''))
  await waitFor(() => expect(screen.getByRole('button', { name: 'Search all records' })).toBeEnabled())
  fireEvent.change(screen.getByPlaceholderText('Search users or courses...'), { target: { value: 'Preserved course' } })
  fireEvent.click(screen.getByRole('button', { name: 'Search all records' }))
  await waitFor(() => expect(mockGetCertificationProgressList).toHaveBeenCalledWith(100, 0, 'Preserved course'))
})
