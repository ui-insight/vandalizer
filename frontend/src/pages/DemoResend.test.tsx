import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import DemoResend from './DemoResend'
import type { ResendResult } from '../api/demo'

const mockResend = vi.fn()
const mockNavigate = vi.fn((_props?: { to?: string; search?: unknown }) => null)

vi.mock('@tanstack/react-router', () => ({
  useParams: () => ({ uuid: 'app123' }),
  Link: ({ children, ...props }: { children: React.ReactNode; to?: string }) => <a {...props}>{children}</a>,
  Navigate: (props: { to?: string }) => mockNavigate(props),
}))

vi.mock('../api/demo', () => ({
  resendCredentials: (uuid: string) => mockResend(uuid),
}))

vi.mock('../components/layout/Footer', () => ({ Footer: () => <footer /> }))

function result(overrides: Partial<ResendResult> = {}): ResendResult {
  return { ok: true, status: 'sent', message: 'ok', email: 'sam@example.com', ...overrides }
}

beforeEach(() => {
  mockResend.mockReset()
  mockNavigate.mockReset()
  mockNavigate.mockReturnValue(null)
})

describe('DemoResend', () => {
  it('active trial: confirms a fresh sign-in link was emailed', async () => {
    mockResend.mockResolvedValueOnce(result({ status: 'sent' }))
    render(<DemoResend />)
    expect(await screen.findByText(/check your inbox/i)).toBeInTheDocument()
    expect(screen.getByText(/sam@example.com/)).toBeInTheDocument()
  })

  it('waitlisted: explains there is nothing to sign into yet', async () => {
    mockResend.mockResolvedValueOnce(result({ status: 'pending', ok: false }))
    render(<DemoResend />)
    expect(await screen.findByText(/on the waitlist/i)).toBeInTheDocument()
  })

  it('expired: redirects to the renewal screen with the token', async () => {
    mockResend.mockResolvedValueOnce(
      result({ status: 'expired', ok: false, feedback_token: 'renew_tok' }),
    )
    render(<DemoResend />)
    await screen.findByRole('navigation')
    expect(mockNavigate).toHaveBeenCalledWith(
      expect.objectContaining({ search: { token: 'renew_tok' } }),
    )
  })
})
