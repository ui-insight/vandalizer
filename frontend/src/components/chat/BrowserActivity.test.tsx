import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { BrowserActivity } from './BrowserActivity'
import { focusBrowserTab } from '../../lib/browserSetup'
import { detectBrowserExtension } from '../../lib/browserExtension'
const send = vi.hoisted(() => vi.fn())
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ sendChatMessage: send }) }))
vi.mock('../../lib/browserSetup', () => ({ focusBrowserTab: vi.fn() }))
vi.mock('../../lib/browserExtension', () => ({ detectBrowserExtension: vi.fn(), RELAY_PING_TIMEOUT_MS: 2000 }))
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
  expect(send).toHaveBeenCalledWith('I have finished signing in in the working tab. Continue what you were doing; read the current page first.')
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
it('checks the connection before continuing and preserves the manually selected section', async () => {
  vi.mocked(detectBrowserExtension).mockResolvedValueOnce(false).mockResolvedValueOnce(true)
  render(<BrowserActivity result={{ error: 'browser_not_connected' }} />)
  expect(screen.getByRole('link', { name: 'Open browser settings' })).toHaveAttribute('href', '/assistant#browser-setup')
  expect(screen.queryByRole('button', { name: 'Open working tab' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Continue browser task' }))
  expect(await screen.findByRole('status')).toHaveTextContent('did not answer')
  expect(send).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Continue browser task' }))
  await screen.findByRole('button', { name: 'Request sent' })
  expect(send).toHaveBeenCalledWith(expect.stringContaining('Read the current working tab first'))
})
it('offers a manual read for an embedded form and attachment instructions for a PDF', () => {
  const { rerender } = render(<BrowserActivity result={{ page: { unread_frames: 1 } }} />)
  fireEvent.click(screen.getByRole('button', { name: 'Read current page' }))
  expect(send).toHaveBeenCalledWith(expect.stringContaining('Keep the current page open'))
  rerender(<BrowserActivity result={{ error: 'pdf_viewer' }} />)
  expect(screen.getByText('Attach the PDF to read it')).toBeVisible()
  expect(screen.getByText(/Add a source → Add Document/)).toBeVisible()
})
it('does not offer a retry that would bypass a refused write', () => {
  render(<BrowserActivity result={{ error: 'blocked_write_action' }} />)
  expect(screen.getByText('Action blocked · read-only')).toBeVisible()
  expect(screen.queryByRole('button', { name: /Continue|Retry|Ask for/ })).not.toBeInTheDocument()
})
it('says the browser is not used on Vandalizer itself, with nothing to approve or retry', () => {
  render(<BrowserActivity result={{ error: 'vandalizer_itself', site: 'vandalizer.example.edu', message: 'Chat’s browser can’t be used on Vandalizer itself, so nothing was opened.', hint: 'Tell the person plainly. Do not ask for approval.' }} />)
  expect(screen.getByText('Not available on Vandalizer itself')).toBeVisible()
  // The card's own wording (browserMessages.ts), not the tool's message.
  expect(screen.getByText('Chat’s browser can’t be used on Vandalizer itself, so chat did not open or read it.')).toBeVisible()
  expect(screen.queryByText(/Do not ask for approval/)).not.toBeInTheDocument()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})
it.each([
  ['Continue after sign-in', { login_required: true }],
  ['Check page and continue', { error: 'unapproved_site' }],
  ['Ask for site access', { error: 'site_not_allowed' }],
  ['Continue browser task', { error: 'no_open_page' }],
])('"%s" never mentions a Skill, since the chat may have none selected', (label, result) => {
  render(<BrowserActivity result={result} />)
  fireEvent.click(screen.getByRole('button', { name: label }))
  expect(send).toHaveBeenCalledOnce()
  expect(send.mock.calls[0][0]).not.toMatch(/skill/i)
})


it('shows the cleanup result and omits controls for a closed working tab', () => {
  render(<BrowserActivity result={{ ok: true, working_tab: 'closed' }} />)
  expect(screen.getByText('Working tab closed')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Open working tab' })).not.toBeInTheDocument()
})
