import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { CertificationsTab } from './CertificationsTab'
import type { CertificationProgressItem } from '../../api/admin'

const mockGetCertificationProgressList = vi.fn()
const mockSetCertificationUnlock = vi.fn()
const mockToast = vi.fn()

vi.mock('../../api/admin', () => ({
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
  streak_days: 3,
  last_activity_date: '2026-01-01',
  unlocked: false,
  updated_at: null,
}

beforeEach(() => {
  mockGetCertificationProgressList.mockReset().mockResolvedValue({ items: [item], total: 1, capped: false })
  mockSetCertificationUnlock.mockReset()
  mockToast.mockReset()
})

describe('CertificationsTab — success', () => {
  it('renders the progress list on success', async () => {
    render(<CertificationsTab />)
    await waitFor(() => expect(screen.getByText('Target User')).toBeInTheDocument())
    expect(screen.getByText('2/5')).toBeInTheDocument()
  })
})

describe('CertificationsTab — unlock toggle', () => {
  it('calls the API with the negated unlocked flag', async () => {
    mockSetCertificationUnlock.mockResolvedValue({ user_id: 'user-1', unlocked: true })
    render(<CertificationsTab />)
    await waitFor(() => expect(screen.getByText('Target User')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Unlock' }))
    await waitFor(() => expect(mockSetCertificationUnlock).toHaveBeenCalledWith('user-1', true))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Unlocked' })).toBeInTheDocument())
  })

  it('does not leave the row flipped and surfaces an error on a rejected unlock (regression for plan 004)', async () => {
    mockSetCertificationUnlock.mockRejectedValue(new Error('Server rejected the change'))
    render(<CertificationsTab />)
    await waitFor(() => expect(screen.getByText('Target User')).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Unlock' }))
    await waitFor(() => expect(mockSetCertificationUnlock).toHaveBeenCalledWith('user-1', true))
    await waitFor(() => expect(mockToast).toHaveBeenCalledWith(
      expect.stringContaining('Failed to unlock certification for Target User'),
      'error',
    ))
    // Row must still read "Unlock" (not flipped to "Unlocked") since the write failed.
    expect(screen.getByRole('button', { name: 'Unlock' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Unlocked' })).not.toBeInTheDocument()
  })
})

describe('CertificationsTab — truncation notice (plan 012)', () => {
  it('renders a truncation notice when the API reports capped: true', async () => {
    mockGetCertificationProgressList.mockResolvedValue({ items: [item], total: 5000, capped: true })
    render(<CertificationsTab />)
    await waitFor(() => expect(screen.getByText('Target User')).toBeInTheDocument())
    expect(screen.getByText(/this list is truncated/i)).toBeInTheDocument()
  })

  it('does not render a truncation notice when the API reports capped: false', async () => {
    mockGetCertificationProgressList.mockResolvedValue({ items: [item], total: 1, capped: false })
    render(<CertificationsTab />)
    await waitFor(() => expect(screen.getByText('Target User')).toBeInTheDocument())
    expect(screen.queryByText(/this list is truncated/i)).not.toBeInTheDocument()
  })
})
