import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import Landing from './Landing'
import type { AuthConfig } from '../api/auth'

// The trial signup IS the landing page's register form (the /demo waitlist
// form is gone). These pin the two ways that form went missing on a trial
// deployment: password sign-in switched off in Admin → Config hid the whole
// auth block, and the /demo CTA opened the block in login mode.

let mockSearch: Record<string, string | undefined> = {}
const mockGetAuthConfig = vi.fn<() => Promise<AuthConfig>>()

vi.mock('@tanstack/react-router', () => ({
  useSearch: () => mockSearch,
  Link: ({ children, ...props }: { children: React.ReactNode; to?: string }) => <a {...props}>{children}</a>,
  Navigate: () => <div data-testid="navigate" />,
}))

vi.mock('../hooks/useAuth', () => ({
  useAuth: () => ({
    user: null,
    loading: false,
    demoExpired: false,
    demoFeedbackToken: null,
    login: vi.fn(),
    register: vi.fn(),
  }),
}))

vi.mock('../contexts/BrandingContext', () => ({
  useBranding: () => ({ orgName: 'Vandalizer', appName: 'Vandalizer', logoDarkUrl: '/logo.svg' }),
}))

vi.mock('../api/auth', () => ({
  getAuthConfig: () => mockGetAuthConfig(),
}))

vi.mock('../components/shared/PanelFocusTrap', () => ({ FocusTrap: ({ children }: { children: React.ReactNode }) => <>{children}</> }))

vi.mock('../components/layout/Footer', () => ({ Footer: () => <footer /> }))

function config(overrides: Partial<AuthConfig> = {}): AuthConfig {
  return { auth_methods: [], oauth_providers: [], ...overrides }
}

describe('Landing — trial signup form', () => {
  beforeEach(() => {
    mockSearch = {}
    mockGetAuthConfig.mockReset()
  })

  it('hides the password block when password sign-in is off and the trial system is off', async () => {
    mockGetAuthConfig.mockResolvedValue(config({ trial_system_enabled: false }))
    render(<Landing />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(mockGetAuthConfig).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByRole('status')).toBeNull())
    expect(document.querySelector('#landing-login-email')).toBeNull()
    expect(document.querySelector('#landing-register-email')).toBeNull()
  })

  it('shows the password block when the trial system is on, even with password sign-in off', async () => {
    mockGetAuthConfig.mockResolvedValue(config({ trial_system_enabled: true }))
    render(<Landing />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(document.querySelector('#landing-login-email')).not.toBeNull())
    expect(screen.getByRole('button', { name: 'Create account' })).toBeInTheDocument()
  })

  it('opens in register mode when the URL carries register=1', async () => {
    mockSearch = { register: '1' }
    mockGetAuthConfig.mockResolvedValue(config({ auth_methods: ['password'] }))
    render(<Landing />)
    await waitFor(() => expect(document.querySelector('#landing-register-email')).not.toBeNull())
    expect(document.querySelector('#landing-login-email')).toBeNull()
  })

  it('opens in login mode by default', async () => {
    mockGetAuthConfig.mockResolvedValue(config({ auth_methods: ['password'] }))
    render(<Landing />)
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(document.querySelector('#landing-login-email')).not.toBeNull())
    expect(document.querySelector('#landing-register-email')).toBeNull()
  })
})


describe('Landing — Request a walkthrough form (support ticket: "[object Object]")', () => {
  const fill = (email: string) => {
    fireEvent.change(document.querySelector('#demo-name')!, { target: { value: 'QA test' } })
    fireEvent.change(document.querySelector('#demo-email')!, { target: { value: email } })
    fireEvent.change(document.querySelector('#demo-institution')!, { target: { value: 'QA test' } })
    fireEvent.change(document.querySelector('#demo-role')!, { target: { value: 'research_admin' } })
    fireEvent.submit(document.querySelector('#demo-email')!.closest('form')!)
  }
  const EMAIL_HELP = 'Please enter a valid email address (like name@university.edu).'

  beforeEach(() => {
    mockSearch = {}
    mockGetAuthConfig.mockReset()
    mockGetAuthConfig.mockResolvedValue(config())
    vi.unstubAllGlobals()
  })

  it('tells the visitor what is wrong with "a@b" next to the email field, without sending it', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<Landing />)
    fill('a@b')
    const message = await screen.findByText(EMAIL_HELP)
    expect(message.id).toBe('demo-email-error')
    const input = document.querySelector('#demo-email')!
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(input).toHaveAttribute('aria-describedby', 'demo-email-error')
    expect(fetchMock).not.toHaveBeenCalled()
    // Fixing the address clears the message.
    fireEvent.change(input, { target: { value: 'qa@university.edu' } })
    expect(screen.queryByText(EMAIL_HELP)).toBeNull()
  })

  it('reads a field rejection from the server instead of printing "[object Object]"', async () => {
    // An address that passes the check here but the server still refuses.
    const rejected = { detail: [{ type: 'value_error', loc: ['body', 'email'], msg: 'Value error, Not a valid email address', input: 'x' }] }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => rejected }))
    render(<Landing />)
    fill('qa@university.edu')
    expect(await screen.findByText(EMAIL_HELP)).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('[object Object]')
  })

  it('names another rejected field, and shows a plain server message as written', async () => {
    const tooLong = { detail: [{ type: 'string_too_long', loc: ['body', 'institution'], msg: 'String should have at most 300 characters' }] }
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: false, status: 422, json: async () => tooLong })
      .mockResolvedValueOnce({ ok: false, status: 503, json: async () => ({ detail: 'Demo requests are temporarily unavailable. Please email us directly.' }) })
    vi.stubGlobal('fetch', fetchMock)
    render(<Landing />)
    fill('qa@university.edu')
    expect(await screen.findByText('Please check your institution, then try again.')).toBeInTheDocument()
    fill('qa@university.edu')
    expect(await screen.findByText('Demo requests are temporarily unavailable. Please email us directly.')).toBeInTheDocument()
    expect(document.body.textContent).not.toContain('[object Object]')
  })
})
