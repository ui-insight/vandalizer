import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
const reset = vi.fn(), forgot = vi.fn()
let token: string | undefined = 'test-token'
vi.mock('@tanstack/react-router', () => ({ useSearch: () => ({ token }), Link: ({ children }: { children: ReactNode }) => <a>{children}</a> }))
vi.mock('../components/layout/AuthLayout', () => ({ AuthLayout: ({ children }: { children: ReactNode }) => <main>{children}</main> }))
vi.mock('../api/auth', () => ({ resetPassword: (...args: unknown[]) => reset(...args), forgotPassword: (...args: unknown[]) => forgot(...args) }))
import ResetPassword from './ResetPassword'
beforeEach(() => { vi.clearAllMocks(); token = 'test-token' })
describe('password recovery', () => {
  it('serializes a reset, retains failed entries, and exposes a new-link route', async () => {
    let reject!: (reason: Error) => void
    reset.mockImplementationOnce(() => new Promise((_, r) => { reject = r })).mockResolvedValue({ ok: true })
    render(<ResetPassword />)
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'NewPassword42' } })
    fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'NewPassword42' } })
    const form = screen.getByRole('button', { name: 'Reset Password' }).closest('form')!
    fireEvent.submit(form); fireEvent.submit(form)
    expect(reset).toHaveBeenCalledTimes(1)
    expect(screen.getByLabelText('New password')).toBeDisabled()
    reject(new Error('Invalid or expired reset link'))
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid or expired')
    expect(screen.getByLabelText('New password')).toHaveValue('NewPassword42')
    expect(screen.getByText('Request a new reset link')).toBeInTheDocument()
    fireEvent.submit(form)
    await screen.findByText('Password reset!')
    expect(reset).toHaveBeenLastCalledWith('test-token', 'NewPassword42')
  })
  it('prevents duplicate email requests and retains the address for retry', async () => {
    token = undefined
    let reject!: (reason: Error) => void
    forgot.mockImplementationOnce(() => new Promise((_, r) => { reject = r })).mockResolvedValue({ ok: true })
    render(<ResetPassword />)
    fireEvent.change(screen.getByLabelText('Email address'), { target: { value: 'research@example.test' } })
    const form = screen.getByRole('button', { name: 'Send Reset Link' }).closest('form')!
    fireEvent.submit(form); fireEvent.submit(form)
    expect(forgot).toHaveBeenCalledTimes(1)
    reject(new Error('Temporarily unavailable'))
    await screen.findByRole('alert')
    expect(screen.getByLabelText('Email address')).toHaveValue('research@example.test')
    fireEvent.submit(form)
    await waitFor(() => expect(screen.getByText('Check your email')).toBeInTheDocument())
  })
})
