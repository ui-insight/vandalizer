import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { UnverifiedEmailAction } from './UnverifiedEmailAction'

const mockResend = vi.fn()

vi.mock('../../api/demo', () => ({
  resendVerificationEmail: (...args: unknown[]) => mockResend(...args),
}))

beforeEach(() => {
  mockResend.mockReset()
})

describe('UnverifiedEmailAction', () => {
  it('offers a resend and no Retry', () => {
    render(<UnverifiedEmailAction />)
    expect(screen.getByRole('button', { name: 'Resend link' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument()
  })

  it('confirms the email was sent', async () => {
    mockResend.mockResolvedValue({ ok: true, already_verified: false })
    render(<UnverifiedEmailAction />)

    fireEvent.click(screen.getByRole('button', { name: 'Resend link' }))

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Check your inbox'))
    expect(screen.queryByRole('button', { name: 'Resend link' })).not.toBeInTheDocument()
  })

  it('names the administrator when the email cannot be sent', async () => {
    mockResend.mockResolvedValue({ ok: false, already_verified: false })
    render(<UnverifiedEmailAction />)

    fireEvent.click(screen.getByRole('button', { name: 'Resend link' }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('contact your administrator'))
    // Still there to try again.
    expect(screen.getByRole('button', { name: 'Resend link' })).toBeInTheDocument()
  })

  it('names the administrator when the request itself fails', async () => {
    mockResend.mockRejectedValue(new Error('network'))
    render(<UnverifiedEmailAction />)

    fireEvent.click(screen.getByRole('button', { name: 'Resend link' }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('contact your administrator'))
  })

  it('says so when the address is already confirmed', async () => {
    mockResend.mockResolvedValue({ ok: true, already_verified: true })
    render(<UnverifiedEmailAction />)

    fireEvent.click(screen.getByRole('button', { name: 'Resend link' }))

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('Your email is confirmed'))
  })
})
