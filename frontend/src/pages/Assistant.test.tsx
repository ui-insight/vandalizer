import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { AssistantPage } from '../api/assistant'

vi.mock('../components/layout/PageLayout', () => ({ PageLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))
vi.mock('../components/assistant/CoreSkillsSection', () => ({ CoreSkillsSection: () => null }))
const confirm = vi.fn()
vi.mock('../components/shared/useConfirm', () => ({ useConfirm: () => confirm }))
vi.mock('../api/assistant', () => ({
  getAssistantCapabilities: vi.fn(),
  setAssistantCapability: vi.fn(),
  setAssistantCapabilityLimit: vi.fn(),
}))

import Assistant from './Assistant'
import { getAssistantCapabilities, setAssistantCapability, setAssistantCapabilityLimit } from '../api/assistant'

function page(overrides: Partial<AssistantPage> = {}): AssistantPage {
  const row = (id: string, label: string, extra = {}) => ({
    id, label, description: `${label} description`, enabled: true, allowed: true, available: true, active: true, ...extra,
  })
  return {
    capabilities: [
      row('web_search', 'Search the web'),
      row('pages', 'Pages', { enabled: false, active: false }),
      row('workflows', 'Workflows', { allowed: false, active: false }),
    ],
    always_on: [{ id: 'files', label: 'Read your files', description: 'Reads files.' }],
    can_set_limits: false,
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  confirm.mockResolvedValue(true)
  vi.mocked(getAssistantCapabilities).mockResolvedValue(page())
  vi.mocked(setAssistantCapability).mockResolvedValue(page())
  vi.mocked(setAssistantCapabilityLimit).mockResolvedValue(page({ can_set_limits: true }))
})

describe('Assistant settings page', () => {
  it('turns one capability off by sending only that switch', async () => {
    render(<Assistant />)
    const web = await screen.findByRole('switch', { name: 'Search the web' })
    expect(web).toHaveAttribute('aria-checked', 'true')
    fireEvent.click(web)
    await waitFor(() => expect(setAssistantCapability).toHaveBeenCalledExactlyOnceWith('web_search', false))
    // Still focusable while saving and afterwards: it is never disabled by a save.
    expect(web).not.toBeDisabled()
  })

  it('separates the saved choice from the administrator block and explains both', async () => {
    render(<Assistant />)
    const locked = await screen.findByRole('switch', { name: 'Workflows' })
    expect(locked).not.toBeDisabled()
    expect(locked).toHaveAttribute('aria-checked', 'true')
    expect(locked).toHaveAccessibleDescription(/Currently blocked for all users by an administrator/)
    // A saved On that is not in effect is captioned, not shown as live.
    expect(screen.getByText('Blocked')).toBeTruthy()
    fireEvent.click(locked)
    await waitFor(() => expect(setAssistantCapability).toHaveBeenCalledWith('workflows', false))
    expect(screen.getByText('Read your files')).toBeTruthy()
    expect(screen.queryByText('Settings for all users — administrators')).toBeNull()
  })

  it('lets an administrator turn a limit back on for everyone', async () => {
    vi.mocked(getAssistantCapabilities).mockResolvedValue(page({ can_set_limits: true }))
    render(<Assistant />)
    fireEvent.click(await screen.findByText('Settings for all users — administrators'))
    fireEvent.click(screen.getByRole('switch', { name: 'Allow Workflows for everyone' }))
    await waitFor(() => expect(setAssistantCapabilityLimit).toHaveBeenCalledExactlyOnceWith('workflows', true))
    expect(setAssistantCapability).not.toHaveBeenCalled()
  })

  it('reloads what is saved when a change could not be confirmed', async () => {
    vi.mocked(setAssistantCapability).mockRejectedValue(new Error('offline'))
    render(<Assistant />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Search the web' }))
    expect(await screen.findByText(/The change was not saved/)).toBeTruthy()
    await waitFor(() => expect(getAssistantCapabilities).toHaveBeenCalledTimes(2))
  })
  it('marks stale values unconfirmed when both the write and refresh fail', async () => {
    vi.mocked(getAssistantCapabilities).mockResolvedValueOnce(page()).mockRejectedValue(new Error('offline'))
    vi.mocked(setAssistantCapability).mockRejectedValue(new Error('offline'))
    render(<Assistant />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Search the web' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('couldn’t confirm your saved settings')
    expect(screen.getByRole('switch', { name: 'Search the web' })).toHaveAttribute('aria-disabled', 'true')
    expect(screen.getByRole('button', { name: 'Refresh settings' })).toBeEnabled()
    expect(screen.queryByText(/switches below show what is saved/)).toBeNull()
  })

  it('asks before saving your own switch, and says it only changes your chats', async () => {
    render(<Assistant />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Search the web' }))
    await waitFor(() => expect(setAssistantCapability).toHaveBeenCalled())
    expect(confirm).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({
      title: 'Turn off “Search the web”?',
      message: 'Are you sure you want to turn this off? This changes your own chats only, starting with your next message.',
      confirmLabel: 'Turn off',
    }))
  })

  it('saves nothing when the confirmation is cancelled', async () => {
    confirm.mockResolvedValue(false)
    render(<Assistant />)
    const web = await screen.findByRole('switch', { name: 'Search the web' })
    fireEvent.click(web)
    await waitFor(() => expect(confirm).toHaveBeenCalled())
    expect(setAssistantCapability).not.toHaveBeenCalled()
    expect(web).toHaveAttribute('aria-checked', 'true')
    expect(screen.queryByText(/^Saved\./)).toBeNull()
  })

  it('tells an administrator the change is for all users, and cancelling leaves it', async () => {
    vi.mocked(getAssistantCapabilities).mockResolvedValue(page({ can_set_limits: true }))
    confirm.mockResolvedValue(false)
    render(<Assistant />)
    fireEvent.click(await screen.findByText('Settings for all users — administrators'))
    fireEvent.click(screen.getByRole('switch', { name: 'Allow Search the web for everyone' }))
    await waitFor(() => expect(confirm).toHaveBeenCalled())
    expect(confirm).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Block “Search the web” for all users?',
      message: expect.stringMatching(/^This will change it for all users\./),
      confirmLabel: 'Block for all users',
      destructive: true,
    }))
    expect(setAssistantCapabilityLimit).not.toHaveBeenCalled()
  })

  it('says when turning your own switch on will not take effect yet', async () => {
    vi.mocked(getAssistantCapabilities).mockResolvedValue(page({
      capabilities: [{ id: 'workflows', label: 'Workflows', description: 'd', enabled: false, allowed: false, available: true, active: false }],
    }))
    render(<Assistant />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Workflows' }))
    await waitFor(() => expect(confirm).toHaveBeenCalled())
    expect(confirm.mock.calls[0][0].message).toContain('An administrator has blocked it for all users')
  })

  it('does not refresh behind an open confirmation, so the save that follows is not left loading', async () => {
    let answer: (ok: boolean) => void = () => {}
    confirm.mockImplementation(() => new Promise<boolean>(resolve => { answer = resolve }))
    render(<Assistant />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Search the web' }))
    await waitFor(() => expect(confirm).toHaveBeenCalled())

    // Coming back to the window normally refreshes the saved settings.
    fireEvent.focus(window)
    expect(getAssistantCapabilities).toHaveBeenCalledTimes(1)

    answer(true)
    expect(await screen.findByText(/^Saved\. Search the web/)).toBeTruthy()
    expect(screen.getByRole('switch', { name: 'Search the web' })).not.toHaveAttribute('aria-disabled')

    // With no dialog open, focus refreshes again.
    fireEvent.focus(window)
    await waitFor(() => expect(getAssistantCapabilities).toHaveBeenCalledTimes(2))
  })

  it('saves nothing when the confirmation is answered after leaving the page', async () => {
    let answer: (ok: boolean) => void = () => {}
    confirm.mockImplementation(() => new Promise<boolean>(resolve => { answer = resolve }))
    const { unmount } = render(<Assistant />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Search the web' }))
    await waitFor(() => expect(confirm).toHaveBeenCalled())
    unmount()
    answer(true)
    await Promise.resolve()
    await Promise.resolve()
    expect(setAssistantCapability).not.toHaveBeenCalled()
  })

  it('tells an administrator when allowing a feature that is not set up changes nothing yet', async () => {
    vi.mocked(getAssistantCapabilities).mockResolvedValue(page({
      can_set_limits: true,
      capabilities: [{ id: 'web_search', label: 'Search the web', description: 'd', enabled: true, allowed: false, available: false, active: false }],
    }))
    render(<Assistant />)
    fireEvent.click(await screen.findByText('Settings for all users — administrators'))
    fireEvent.click(screen.getByRole('switch', { name: 'Allow Search the web for everyone' }))
    await waitFor(() => expect(confirm).toHaveBeenCalled())
    expect(confirm.mock.calls[0][0].message).toContain('It isn’t set up on this site yet')
  })

  it('says when your own switch is for a feature that is not set up', async () => {
    vi.mocked(getAssistantCapabilities).mockResolvedValue(page({
      capabilities: [{ id: 'web_search', label: 'Search the web', description: 'd', enabled: false, allowed: true, available: false, active: false }],
    }))
    render(<Assistant />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Search the web' }))
    await waitFor(() => expect(confirm).toHaveBeenCalled())
    expect(confirm.mock.calls[0][0].message).toContain('It isn’t set up on this site yet')
  })
})
