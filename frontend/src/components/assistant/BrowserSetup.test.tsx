import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react'
import { BrowserSetup } from './BrowserSetup'
import { browserConnection } from '../../lib/browserSetup'
vi.mock('../../lib/browserSetup', () => ({ browserConnection: vi.fn(), browserStoreUrl: '' }))
afterEach(cleanup)
it.each([
  ['not-installed', 'Not detected · Install or connect the extension'],
  ['installed', 'Installed · Connect this site'],
  ['connected', `Connected to ${location.origin}`],
] as const)('explains the %s state and the demo', async (state, text) => {
  vi.mocked(browserConnection).mockResolvedValue(state)
  render(<BrowserSetup />)
  expect(await screen.findByText(text)).toBeVisible()
  expect(screen.getByRole('link', { name: 'Add example Skill' })).toHaveAttribute('href', '/?tab=library&browserSkill=demo')
  if (state !== 'connected') {
    expect(screen.getByRole('link', { name: 'Download Vandalizer Browser' })).toHaveAttribute('download')
    expect(screen.getByText('Load unpacked')).toBeVisible()
    expect(screen.getByText('edge://extensions')).toBeVisible()
  }
})
it('notices connection on return without a reload', async () => {
  vi.mocked(browserConnection).mockResolvedValue('installed')
  render(<BrowserSetup />)
  await screen.findByText('Installed · Connect this site')
  vi.mocked(browserConnection).mockResolvedValue('connected')
  fireEvent.focus(window)
  await waitFor(() => expect(screen.getByText(`Connected to ${location.origin}`)).toBeVisible())
})
