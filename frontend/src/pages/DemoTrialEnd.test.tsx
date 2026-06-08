import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import DemoTrialEnd from './DemoTrialEnd'
import type { TrialEndInfo } from '../types/demo'

const mockGetTrialEndInfo = vi.fn()
const mockRequestTrialExtension = vi.fn()
const mockRefreshUser = vi.fn()
const mockNavigate = vi.fn()

vi.mock('@tanstack/react-router', () => ({
  useSearch: () => ({ token: 'tok123' }),
  useNavigate: () => mockNavigate,
  Link: ({ children, ...props }: { children: React.ReactNode; to?: string }) => <a {...props}>{children}</a>,
}))

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({ refreshUser: mockRefreshUser }),
}))

vi.mock('../api/demo', () => ({
  getTrialEndInfo: (token: string) => mockGetTrialEndInfo(token),
  requestTrialExtension: (token: string, notes?: Record<string, unknown>) =>
    mockRequestTrialExtension(token, notes),
}))

vi.mock('../components/layout/Footer', () => ({ Footer: () => <footer /> }))

function info(overrides: Partial<TrialEndInfo> = {}): TrialEndInfo {
  return {
    name: 'Sam',
    organization: 'Test Org',
    engagement: 'low',
    extensions_used: 0,
    max_extensions: 2,
    can_self_extend: true,
    already_extended: false,
    ...overrides,
  }
}

beforeEach(() => {
  mockGetTrialEndInfo.mockReset()
  mockRequestTrialExtension.mockReset()
  mockRefreshUser.mockReset()
  mockNavigate.mockReset()
})

describe('DemoTrialEnd', () => {
  it('low-engagement: shows one-click renewal and extends on click', async () => {
    mockGetTrialEndInfo.mockResolvedValueOnce(info({ engagement: 'low' }))
    mockRequestTrialExtension.mockResolvedValueOnce({ ok: true, message: 'ok', expires_at: null })

    render(<DemoTrialEnd />)

    const btn = await screen.findByRole('button', { name: /keep my trial going/i })
    fireEvent.click(btn)

    await waitFor(() => expect(mockRequestTrialExtension).toHaveBeenCalledWith('tok123', undefined))
    expect(await screen.findByText(/you're back in/i)).toBeInTheDocument()
  })

  it('engaged: shows the notes form, not the one-click button', async () => {
    mockGetTrialEndInfo.mockResolvedValueOnce(info({ engagement: 'engaged' }))

    render(<DemoTrialEnd />)

    expect(await screen.findByText(/tell us a little about how it's going/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /keep my trial going/i })).not.toBeInTheDocument()
  })

  it('cap reached: shows the contact CTA instead of a renew option', async () => {
    mockGetTrialEndInfo.mockResolvedValueOnce(
      info({ can_self_extend: false, extensions_used: 2, already_extended: true }),
    )

    render(<DemoTrialEnd />)

    expect(await screen.findByText(/let's keep this going/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /get in touch/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /keep my trial going/i })).not.toBeInTheDocument()
  })

  it('invalid token: shows an error state', async () => {
    mockGetTrialEndInfo.mockRejectedValueOnce(new Error('nope'))

    render(<DemoTrialEnd />)

    expect(await screen.findByText(/invalid link/i)).toBeInTheDocument()
  })
})
