import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { AssistantPage } from '../api/assistant'

vi.mock('../components/layout/PageLayout', () => ({ PageLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))
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

  it('locks a capability an administrator turned off and ties the reason to the switch', async () => {
    render(<Assistant />)
    const locked = await screen.findByRole('switch', { name: 'Workflows' })
    expect(locked).toBeDisabled()
    expect(locked).toHaveAttribute('aria-checked', 'false')
    expect(locked).toHaveAccessibleDescription('Turned off for everyone by an administrator.')
    expect(screen.getByText('Read your files')).toBeTruthy()
    expect(screen.queryByText('Allowed for everyone')).toBeNull()
  })

  it('lets an administrator turn a limit back on for everyone', async () => {
    vi.mocked(getAssistantCapabilities).mockResolvedValue(page({ can_set_limits: true }))
    render(<Assistant />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Allow Workflows for everyone' }))
    await waitFor(() => expect(setAssistantCapabilityLimit).toHaveBeenCalledExactlyOnceWith('workflows', true))
    expect(setAssistantCapability).not.toHaveBeenCalled()
  })

  it('reloads what is saved when a change could not be confirmed', async () => {
    vi.mocked(setAssistantCapability).mockRejectedValue(new Error('offline'))
    render(<Assistant />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Search the web' }))
    expect(await screen.findByText(/Could not confirm that change/)).toBeTruthy()
    await waitFor(() => expect(getAssistantCapabilities).toHaveBeenCalledTimes(2))
  })
})
