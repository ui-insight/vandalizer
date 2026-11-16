import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { BrowserActivity } from './BrowserActivity'
import { focusBrowserTab } from '../../lib/browserSetup'
const send = vi.hoisted(() => vi.fn())
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ sendChatMessage: send }) }))
vi.mock('../../lib/browserSetup', () => ({ focusBrowserTab: vi.fn() }))
afterEach(() => { cleanup(); vi.clearAllMocks() })
it.each([{ login_required: true }, { error: 'unapproved_site' }])('offers working tab and continue for %j', async result => {
  vi.mocked(focusBrowserTab).mockResolvedValue({ ok: true })
  render(<BrowserActivity result={{ ...result, page: { url: 'https://portal.example.edu/awards' } }} />)
  expect(screen.getByText('Read-only browser · portal.example.edu')).toBeVisible()
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
  expect(await screen.findByRole('status')).toHaveTextContent('Reconnect in Assistant settings')
})
