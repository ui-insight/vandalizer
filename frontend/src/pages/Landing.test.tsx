import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
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
    await waitFor(() => expect(mockGetAuthConfig).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByRole('status')).toBeNull())
    expect(document.querySelector('#landing-login-email')).toBeNull()
    expect(document.querySelector('#landing-register-email')).toBeNull()
  })

  it('shows the password block when the trial system is on, even with password sign-in off', async () => {
    mockGetAuthConfig.mockResolvedValue(config({ trial_system_enabled: true }))
    render(<Landing />)
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
    await waitFor(() => expect(document.querySelector('#landing-login-email')).not.toBeNull())
    expect(document.querySelector('#landing-register-email')).toBeNull()
  })
})

describe('Landing — the link opened before signing in', () => {
  it('is parked when leaving for single sign-on, which returns to "/" without it', async () => {
    sessionStorage.clear()
    mockSearch = { next: '/?kb=kb-1' }
    mockGetAuthConfig.mockResolvedValue({
      auth_methods: ['oauth'],
      oauth_providers: [{ provider: 'saml', display_name: 'University SSO', configured: true }],
    } as AuthConfig)
    render(<Landing />)
    const sso = await screen.findByRole('link', { name: 'University SSO' })
    sso.addEventListener('click', (event) => event.preventDefault())
    sso.click()
    expect(JSON.parse(sessionStorage.getItem('vandalizer:pendingNext')!).path).toBe('/?kb=kb-1')
  })
})
