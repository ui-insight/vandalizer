import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { BrowserDiscovery } from './BrowserDiscovery'
import { browserConnection, type BrowserConnection } from '../../lib/browserSetup'

vi.mock('../../lib/browserSetup', () => ({ browserConnection: vi.fn() }))

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  vi.mocked(browserConnection).mockResolvedValue('not-installed')
})
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers() })

it('offers a quiet, optional introduction when the extension is absent', async () => {
  render(<BrowserDiscovery />)
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  expect(await screen.findByRole('complementary', { name: 'Optional browser feature' })).toBeVisible()
  expect(screen.getByRole('link', { name: 'Learn more about browser access' })).toHaveAttribute('href', '/assistant#browser-setup')
  expect(screen.queryByText('Set up browser')).not.toBeInTheDocument()
})

it('never flashes an installation prompt while checking an already connected browser', async () => {
  let resolve!: (value: BrowserConnection) => void
  vi.mocked(browserConnection).mockReturnValue(new Promise(done => { resolve = done }))
  const view = render(<BrowserDiscovery />)
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  await act(async () => { resolve('connected') })
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()

  // A later missed handshake must not advertise setup all over again.
  view.unmount()
  vi.mocked(browserConnection).mockResolvedValue('not-installed')
  render(<BrowserDiscovery />)
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  expect(browserConnection).toHaveBeenCalledTimes(1)
})

it('remembers dismissal after remounting without changing browser access', async () => {
  const view = render(<BrowserDiscovery />)
  fireEvent.click(await screen.findByRole('button', { name: 'Dismiss browser suggestion' }))
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  view.unmount()
  render(<BrowserDiscovery />)
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  expect(browserConnection).toHaveBeenCalledTimes(1)
})

it('offers connection rather than installation for an installed extension', async () => {
  vi.mocked(browserConnection).mockResolvedValue('installed')
  render(<BrowserDiscovery />)
  expect(await screen.findByRole('link', { name: 'Connect your browser to this site' })).toHaveTextContent('Connect this site')
  expect(screen.queryByText('Learn more')).not.toBeInTheDocument()
})

it('retires the suggestion when returning from connecting the extension', async () => {
  render(<BrowserDiscovery />)
  await screen.findByRole('complementary')
  vi.mocked(browserConnection).mockResolvedValue('connected')
  fireEvent.focus(window)
  await waitFor(() => expect(screen.queryByRole('complementary')).not.toBeInTheDocument())
})

it('detects connection while the chat page stays open', async () => {
  vi.useFakeTimers()
  render(<BrowserDiscovery />)
  await act(async () => { await Promise.resolve() })
  expect(screen.getByRole('complementary')).toBeVisible()
  vi.mocked(browserConnection).mockResolvedValue('connected')
  await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  await act(async () => { await vi.advanceTimersByTimeAsync(15000) })
  expect(browserConnection).toHaveBeenCalledTimes(2)
})

it('honors dismissal in another tab', async () => {
  render(<BrowserDiscovery />)
  await screen.findByRole('complementary')
  fireEvent(window, new StorageEvent('storage', { key: 'vandalizer:home:hide-browser-suggestion', newValue: '1' }))
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
})

it('can dismiss for this visit when browser storage is blocked', async () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Blocked') })
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Blocked') })
  render(<BrowserDiscovery />)
  fireEvent.click(await screen.findByRole('button', { name: 'Dismiss browser suggestion' }))
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
})

it('does not turn a failed connection check into an install suggestion', async () => {
  vi.mocked(browserConnection).mockRejectedValue(new Error('Unavailable'))
  render(<BrowserDiscovery />)
  await act(async () => { await Promise.resolve() })
  expect(screen.queryByRole('complementary')).not.toBeInTheDocument()
  vi.mocked(browserConnection).mockResolvedValue('not-installed')
  fireEvent.focus(window)
  expect(await screen.findByRole('complementary')).toBeVisible()
})
