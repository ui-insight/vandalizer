import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { AssistantPage } from '../api/assistant'

vi.mock('../components/layout/PageLayout', () => ({ PageLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))
vi.mock('../components/assistant/CoreSkillsSection', () => ({ CoreSkillsSection: () => null }))
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

})
