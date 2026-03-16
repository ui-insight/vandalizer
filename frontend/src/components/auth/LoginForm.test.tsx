import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { LoginForm } from './LoginForm'

const mockLogin = vi.fn()

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ login: mockLogin }),
}))

beforeEach(() => {
  mockLogin.mockReset()
})

describe('LoginForm', () => {
  it('renders username and password fields', () => {
    render(<LoginForm />)
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
  })

  it('calls login with entered credentials on submit', async () => {
    mockLogin.mockResolvedValueOnce(undefined)
    render(<LoginForm />)

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'secret' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(mockLogin).toHaveBeenCalledWith('alice', 'secret'))
  })

  it('shows loading state while submitting', async () => {
    let resolve!: () => void
    mockLogin.mockReturnValue(new Promise<void>((r) => { resolve = r }))

    render(<LoginForm />)
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(screen.getByRole('button', { name: /signing in/i })).toBeDisabled()

    resolve()
    await waitFor(() => expect(screen.getByRole('button', { name: /sign in/i })).not.toBeDisabled())
  })

  it('shows error message when login fails', async () => {
    mockLogin.mockRejectedValueOnce(new Error('Invalid credentials'))
    render(<LoginForm />)

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(screen.getByText('Invalid credentials')).toBeInTheDocument())
  })

  it('clears error on a new submit attempt', async () => {
    mockLogin.mockRejectedValueOnce(new Error('Bad credentials'))
    mockLogin.mockResolvedValueOnce(undefined)
    render(<LoginForm />)

    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: 'alice' } })
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() => expect(screen.getByText('Bad credentials')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() => expect(screen.queryByText('Bad credentials')).not.toBeInTheDocument())
  })
})
