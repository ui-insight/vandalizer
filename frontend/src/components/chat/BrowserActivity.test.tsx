import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { BrowserActivity } from './BrowserActivity'
import { focusBrowserTab } from '../../lib/browserSetup'
const send = vi.hoisted(() => vi.fn())
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ sendChatMessage: send }) }))
vi.mock('../../lib/browserSetup', () => ({ focusBrowserTab: vi.fn() }))
afterEach(() => { cleanup(); vi.clearAllMocks() })
it('offers working tab and continue for a sign-in pause', async () => {
  const result = { login_required: true }
  vi.mocked(focusBrowserTab).mockResolvedValue({ ok: true })
  render(<BrowserActivity result={{ ...result, page: { url: 'https://portal.example.edu/awards' } }} />)
  expect(screen.getByText('Sign in to continue')).toBeVisible()
  expect(screen.getByText('portal.example.edu')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Open working tab' }))
  expect(focusBrowserTab).toHaveBeenCalledOnce()
  fireEvent.click(screen.getByRole('button', { name: 'Continue after sign-in' }))
  expect(send).toHaveBeenCalledWith(expect.stringContaining('read the current page first'))
})
it('explains focus failure and shows no continue action on an ordinary page', async () => {
  vi.mocked(focusBrowserTab).mockResolvedValue({ error: 'no_open_page' })
  render(<BrowserActivity result={{ page: { url: 'https://portal.example.edu/' } }} />)
  expect(screen.queryByRole('button', { name: 'Continue after sign-in' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Open working tab' }))
  expect(await screen.findByRole('status')).toHaveTextContent('The working tab has closed')
})

it.each(['unapproved_site', 'site_not_allowed'])('does not claim sign-in for %s', error => {
  render(<BrowserActivity result={{ error, site: 'portal.example.edu' }} />)
  expect(screen.getByText('Site permission needed')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Continue after sign-in' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: error === 'unapproved_site' ? 'Check page and continue' : 'Ask for site access' }))
  expect(send).toHaveBeenCalledWith(expect.stringContaining('browser_open'))
  if (error === 'unapproved_site') expect(send).toHaveBeenCalledWith(expect.stringContaining('read the current working tab again'))
  expect(send.mock.calls[0][0]).not.toContain('I have finished signing in')
  expect(screen.getByRole('button', { name: 'Request sent' })).toBeDisabled()
})
it('routes a missing connection to settings', () => {
  render(<BrowserActivity result={{ error: 'browser_not_connected' }} />)
  expect(screen.getByRole('link', { name: 'Open browser settings' })).toHaveAttribute('href', '/assistant#browser-setup')
  expect(screen.queryByRole('button', { name: 'Open working tab' })).not.toBeInTheDocument()
})
it('does not offer a retry that would bypass a refused write', () => {
  render(<BrowserActivity result={{ error: 'blocked_write_action' }} />)
  expect(screen.getByText('Action blocked · read-only')).toBeVisible()
  expect(screen.queryByRole('button', { name: /Continue|Retry|Ask for/ })).not.toBeInTheDocument()
})
