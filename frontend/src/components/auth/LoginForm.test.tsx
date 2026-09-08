import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { LoginForm } from './LoginForm'

const mockLogin = vi.fn()

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ login: mockLogin }),
}))

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, ...props }: { children: React.ReactNode; to?: string }) => <a {...props}>{children}</a>,
}))

beforeEach(() => {
  mockLogin.mockReset()
})

describe('LoginForm', () => {
  it('renders email and password fields', () => {
    render(<LoginForm />)
    expect(screen.getByPlaceholderText(/email/i)).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/password/i)).toBeInTheDocument()
  })

  it('calls login with entered credentials on submit', async () => {
    mockLogin.mockResolvedValueOnce(undefined)
    render(<LoginForm />)

    fireEvent.change(screen.getByPlaceholderText(/email/i), { target: { value: 'alice@example.com' } })
    fireEvent.change(screen.getByPlaceholderText(/password/i), { target: { value: 'secret' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(mockLogin).toHaveBeenCalledWith('alice@example.com', 'secret'))
  })

  it('shows loading state while submitting', async () => {
    let resolve!: () => void
    mockLogin.mockReturnValue(new Promise<void>((r) => { resolve = r }))

    render(<LoginForm />)
    fireEvent.change(screen.getByPlaceholderText(/email/i), { target: { value: 'alice@example.com' } })
    fireEvent.change(screen.getByPlaceholderText(/password/i), { target: { value: 'pw' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    expect(screen.getByRole('button', { name: /signing in/i })).toBeDisabled()

    resolve()
    await waitFor(() => expect(screen.getByRole('button', { name: /sign in/i })).not.toBeDisabled())
  })

  it('shows error message when login fails', async () => {
    mockLogin.mockRejectedValueOnce(new Error('Invalid credentials'))
    render(<LoginForm />)

    fireEvent.change(screen.getByPlaceholderText(/email/i), { target: { value: 'alice@example.com' } })
    fireEvent.change(screen.getByPlaceholderText(/password/i), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => expect(screen.getByText('Invalid credentials')).toBeInTheDocument())
  })

  it('clears error on a new submit attempt', async () => {
    mockLogin.mockRejectedValueOnce(new Error('Bad credentials'))
    mockLogin.mockResolvedValueOnce(undefined)
    render(<LoginForm />)

    fireEvent.change(screen.getByPlaceholderText(/email/i), { target: { value: 'alice@example.com' } })
    fireEvent.change(screen.getByPlaceholderText(/password/i), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() => expect(screen.getByText('Bad credentials')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() => expect(screen.queryByText('Bad credentials')).not.toBeInTheDocument())
  })

  // The sign-in page is the first thing a white-labeled deployment shows, so the
  // primary button has to follow the configured brand — background and the
  // runtime-computed contrast colour for the label on it — not Vandalizer's gold.
  it('paints the submit button from the brand tokens, not a hardcoded hex', () => {
    render(<LoginForm />)
    const submit = screen.getByRole('button', { name: /sign in/i })

    expect(submit).toHaveClass('bg-highlight')
    expect(submit).toHaveClass('text-highlight-text')
    expect(submit.className).not.toMatch(/#[0-9a-f]{6}/i)
  })

  // These inputs set focus:outline-none, which suppresses the global
  // :focus-visible outline -- so the ring IS the focus indicator, and it has to
  // be the contrast-corrected token. Painted with the raw brand, a dark brand
  // (#163A64 over near-black) leaves a ~1.3:1 ring: a keyboard user on a
  // white-labelled deployment cannot see where they are. The raw token is
  // correct on the app's light surfaces and wrong here, so this pins the
  // distinction rather than the presence of a class.
  it.each(['email', 'password'])('gives the %s input a focus ring visible on dark', (field) => {
    render(<LoginForm />)
    const input = screen.getByPlaceholderText(new RegExp(field, 'i'))

    expect(input.className).toContain('focus:outline-none')
    expect(input.className).toContain('focus:ring-highlight-on-dark/50')
    expect(input.className).not.toContain('focus:ring-highlight/50')
    expect(input.className).not.toContain('focus:border-highlight/50')
  })
})
