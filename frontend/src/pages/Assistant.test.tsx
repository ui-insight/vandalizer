import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { AssistantPage } from '../api/assistant'

vi.mock('../components/layout/PageLayout', () => ({ PageLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))
vi.mock('../api/assistant', () => ({
  getAssistantCapabilities: vi.fn(),
  setAssistantCapabilities: vi.fn(),
  setAssistantCapabilityLimits: vi.fn(),
}))

import Assistant from './Assistant'
import { getAssistantCapabilities, setAssistantCapabilities, setAssistantCapabilityLimits } from '../api/assistant'

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
  vi.mocked(setAssistantCapabilities).mockResolvedValue(page())
  vi.mocked(setAssistantCapabilityLimits).mockResolvedValue(page({ can_set_limits: true }))
})

describe('Assistant page', () => {
  it('turns one capability off and keeps the others as they were', async () => {
    render(<Assistant />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Search the web: on' }))
    // Pages was already off, and the admin-limited Workflows keeps the person's own "on".
    await waitFor(() => expect(setAssistantCapabilities).toHaveBeenCalledWith(['web_search', 'pages']))
  })

  it('locks a capability an administrator turned off and says why', async () => {
    render(<Assistant />)
    const locked = await screen.findByRole('switch', { name: 'Workflows: off' })
    expect(locked).toBeDisabled()
    expect(screen.getByText('Turned off for everyone by an administrator.')).toBeTruthy()
    expect(screen.getByText('Read your files')).toBeTruthy()
    expect(screen.queryByText('Allowed for everyone')).toBeNull()
  })

  it('lets an administrator set the limit for everyone', async () => {
    vi.mocked(getAssistantCapabilities).mockResolvedValue(page({ can_set_limits: true }))
    render(<Assistant />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Allow Workflows for everyone: off' }))
    await waitFor(() => expect(setAssistantCapabilityLimits).toHaveBeenCalledWith([]))
    expect(setAssistantCapabilities).not.toHaveBeenCalled()
  })

  it('says so when a change could not be saved', async () => {
    vi.mocked(setAssistantCapabilities).mockRejectedValue(new Error('offline'))
    render(<Assistant />)
    fireEvent.click(await screen.findByRole('switch', { name: 'Search the web: on' }))
    expect(await screen.findByText('Could not save that change. Nothing was changed; try again.')).toBeTruthy()
  })
})
