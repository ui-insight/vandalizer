import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, fireEvent } from '@testing-library/react'
import { BrowserSetup } from './BrowserSetup'
import { browserConnection } from '../../lib/browserSetup'
import type { AssistantCapability } from '../../api/assistant'

vi.mock('../../lib/browserSetup', () => ({ browserConnection: vi.fn(), browserStoreUrl: '' }))
beforeEach(() => { sessionStorage.clear(); history.replaceState(null, '', '#browser-setup'); vi.mocked(browserConnection).mockResolvedValue('not-installed') })
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('starts with one download action and keeps later instructions out of the way', async () => {
  render(<BrowserSetup />)
  expect(await screen.findByText('Browser not connected')).toBeVisible()
  expect(screen.getByRole('link', { name: 'Download extension' })).toHaveAttribute('download')
  expect(screen.queryByText('Load unpacked')).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Add Skill to Library' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Try a Skill' })).toBeDisabled()
})

it('moves through install instructions and focuses the new heading', async () => {
  render(<BrowserSetup />)
  await screen.findByText('Browser not connected')
  fireEvent.click(screen.getByRole('button', { name: 'I’ve unzipped it' }))
  expect(screen.getByRole('heading', { name: 'Add it to Chrome' })).toHaveFocus()
  expect(screen.getByText('Load unpacked')).toBeVisible()
  expect(screen.getByText('chrome://extensions')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'I’ve added the extension' }))
  expect(screen.getByRole('heading', { name: 'Connect this Vandalizer site' })).toHaveFocus()
  expect(screen.queryByRole('link', { name: 'Add Skill to Library' })).not.toBeInTheDocument()
  expect(sessionStorage.getItem('vandalizer-browser-setup-step')).toBe('2')
})

it('copies the selected browser address and handles clipboard denial', async () => {
  const writeText = vi.fn().mockResolvedValue(undefined)
  vi.stubGlobal('navigator', { ...navigator, userAgent: '', clipboard: { writeText } })
  render(<BrowserSetup />)
  await screen.findByText('Browser not connected')
  fireEvent.click(screen.getByRole('button', { name: 'I’ve unzipped it' }))
  fireEvent.click(screen.getByRole('radio', { name: 'Edge' }))
  fireEvent.click(screen.getByRole('button', { name: 'Copy extensions address' }))
  expect(await screen.findByText('Copied. Paste it into a new tab’s address bar.')).toBeVisible()
  expect(writeText).toHaveBeenCalledWith('edge://extensions')
  writeText.mockRejectedValue(new Error('Denied'))
  fireEvent.click(screen.getByRole('button', { name: 'Copy extensions address' }))
  expect(await screen.findByText('Select the address above and copy it manually.')).toBeVisible()
  vi.unstubAllGlobals()
})

it('resumes the install step after reloading the app', async () => {
  sessionStorage.setItem('vandalizer-browser-setup-step', '1')
  render(<BrowserSetup />)
  expect(await screen.findByRole('heading', { name: 'Add it to Chrome' })).toBeVisible()
})

it('skips installation when the extension is detected', async () => {
  vi.mocked(browserConnection).mockResolvedValue('installed')
  render(<BrowserSetup />)
  expect(await screen.findByText('Extension installed · ready to connect')).toBeVisible()
  expect(screen.getByRole('heading', { name: 'Connect this Vandalizer site' })).toBeVisible()
  expect(screen.queryByRole('link', { name: 'Download extension' })).not.toBeInTheDocument()
})

it('advances to the regular Library Skill on connection, without a reload', async () => {
  vi.mocked(browserConnection).mockResolvedValue('installed')
  render(<BrowserSetup />)
  await screen.findByText('Extension installed · ready to connect')
  vi.mocked(browserConnection).mockResolvedValue('connected')
  fireEvent.focus(window)
  expect(await screen.findByRole('heading', { name: 'Your browser is ready' })).toBeVisible()
  expect(screen.getByRole('link', { name: 'Add Skill to Library' })).toHaveAttribute('href', '/?tab=library&browserSkill=demo')
  expect(screen.getByText(/This is a regular Library Skill/)).toBeVisible()
  expect(screen.queryByText('Load unpacked')).not.toBeInTheDocument()
})

it('does not mistake an attempted connection for success', async () => {
  render(<BrowserSetup />)
  await screen.findByText('Browser not connected')
  fireEvent.click(screen.getByRole('button', { name: 'Already installed? Connect it' }))
  fireEvent.click(screen.getByRole('button', { name: 'Check again' }))
  expect(await screen.findByText(/No connection yet/)).toBeVisible()
  expect(screen.queryByRole('link', { name: 'Add Skill to Library' })).not.toBeInTheDocument()
})

it('returns to connection help if the extension disconnects', async () => {
  vi.mocked(browserConnection).mockResolvedValue('connected')
  render(<BrowserSetup />)
  await screen.findByRole('heading', { name: 'Your browser is ready' })
  vi.mocked(browserConnection).mockResolvedValue('not-installed')
  fireEvent.focus(window)
  fireEvent.click(await screen.findByRole('button', { name: 'Set up browser' }))
  await waitFor(() => expect(screen.queryByRole('link', { name: 'Add Skill to Library' })).not.toBeInTheDocument())
  expect(screen.getByRole('heading', { name: 'Connect this Vandalizer site' })).toBeVisible()
})

const capability: AssistantCapability = { id: 'browser', label: 'Use your browser', description: '', enabled: false, allowed: true, available: true, active: false }

it('routes an off capability through the existing enable action', async () => {
  vi.mocked(browserConnection).mockResolvedValue('connected')
  const onEnable = vi.fn()
  render(<BrowserSetup capability={capability} onEnable={onEnable} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Turn on Use your browser' }))
  expect(onEnable).toHaveBeenCalledOnce()
  expect(screen.getByText('Turn on “Use your browser” to use browser Skills.')).toBeVisible()
})

it('explains an administrator block without offering to bypass it', async () => {
  vi.mocked(browserConnection).mockResolvedValue('connected')
  render(<BrowserSetup capability={{ ...capability, allowed: false }} onEnable={vi.fn()} />)
  expect(await screen.findByText('Your administrator has turned off browser access.')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Turn on Use your browser' })).not.toBeInTheDocument()
})

it('keeps returning connected users out of the wizard until they choose a Skill', async () => {
  vi.mocked(browserConnection).mockResolvedValue('connected')
  render(<BrowserSetup />)
  await screen.findByText('Browser connected')
  expect(screen.queryByRole('list', { name: 'Browser setup progress' })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'Add Skill to Library' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Try a Skill' }))
  expect(screen.getByRole('link', { name: 'Add Skill to Library' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Close guide' }))
  expect(screen.getByRole('region', { name: 'Your browser is ready' })).toHaveFocus()
})
it('keeps setup optional on the general Assistant settings page', async () => {
  history.replaceState(null, '', '/assistant')
  render(<BrowserSetup />)
  expect(await screen.findByRole('button', { name: 'Set up browser' })).toBeVisible()
  expect(screen.queryByRole('link', { name: 'Download extension' })).not.toBeInTheDocument()
})
it('shows administrator restrictions before installation', async () => {
  render(<BrowserSetup capability={{ ...capability, allowed: false }} />)
  expect(await screen.findByText('Your administrator has turned off browser access.')).toBeVisible()
})
