/** Automations list: search like the other list pages, a named status, a sort.
 *  Status used to be a bare colored dot, and search a corner "Filter..." box. */
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Automation } from '../../types/automation'

const automations: Automation[] = []
vi.mock('../../hooks/useAutomations', () => ({
  useAutomations: () => ({ automations, loading: false, refresh: vi.fn() }),
}))
vi.mock('../../hooks/useWorkflows', () => ({ useWorkflows: () => ({ workflows: [] }) }))
vi.mock('../../hooks/useExtractions', () => ({ useSearchSets: () => ({ searchSets: [] }) }))
vi.mock('../../hooks/useProjectPins', () => ({
  useProjectPins: () => ({ idsByType: () => new Set(), isPinned: () => false, pin: vi.fn(), unpin: vi.fn() }),
}))
vi.mock('../../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({
    openAutomation: vi.fn(), openAutomationId: 'x', activeProjectUuid: null,
    activeProjectTitle: null, activeProjectRole: null,
  }),
}))
vi.mock('../../api/config', () => ({ getFeatureFlags: () => Promise.resolve({ m365_enabled: false }) }))

import { AutomationsPanel } from './AutomationsPanel'
import { sortAutomations } from './automationList'

const auto = (id: string, name: string, overrides: Partial<Automation> = {}): Automation => ({
  id, name, description: null, enabled: true, trigger_type: 'folder_watch', trigger_config: {},
  action_type: 'workflow', action_id: null, action_name: 'Summarize', user_id: 'u', team_id: null,
  shared_with_team: false, output_config: {}, created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z', can_manage: true, ...overrides,
})

const rows = () => screen.getAllByRole('button', { name: /^Open automation:/ })
  .map(r => r.getAttribute('aria-label')!.replace('Open automation: ', ''))

beforeEach(() => {
  try { localStorage.clear() } catch { /* jsdom always has it */ }
  automations.splice(0, automations.length,
    auto('a', 'Award intake', { updated_at: '2026-03-01T00:00:00Z', created_at: '2026-01-05T00:00:00Z' }),
    auto('b', 'budget check', { enabled: false, updated_at: '2026-05-01T00:00:00Z', created_at: '2026-01-01T00:00:00Z' }),
    auto('c', 'Closeout reminders', { trigger_type: 'schedule', enabled: false, next_run_at: '2026-11-01T15:00:00Z', updated_at: '2026-02-01T00:00:00Z', created_at: '2026-02-01T00:00:00Z' }),
  )
})

describe('AutomationsPanel', () => {
  it('names every status in text, not only by color', () => {
    render(<AutomationsPanel activeIds={new Set(['a'])} />)
    const row = (name: string) => screen.getByRole('button', { name: new RegExp(`^Open automation: ${name}`) })
    expect(within(row('Award intake')).getByText('Running')).toBeTruthy()
    expect(within(row('budget check')).getByText('Paused')).toBeTruthy()
    // A paused schedule says Paused once, on the pill — no "Next run" for it.
    expect(within(row('Closeout reminders')).getAllByText('Paused')).toHaveLength(1)
    expect(within(row('Closeout reminders')).queryByText(/Next run/)).toBeNull()
  })

  it('says Active for an automation that is on and idle', () => {
    render(<AutomationsPanel />)
    expect(within(screen.getByRole('button', { name: /^Open automation: Award intake/ })).getByText('Active')).toBeTruthy()
  })

  it('searches with the same full-width Search bar as Knowledge Bases', async () => {
    vi.useFakeTimers()
    try {
      render(<AutomationsPanel />)
      expect(screen.queryByPlaceholderText('Filter...')).toBeNull()
      fireEvent.change(screen.getByRole('searchbox', { name: 'Search...' }), { target: { value: 'budget' } })
      await act(async () => { vi.advanceTimersByTime(350) })
      expect(rows()).toEqual(['budget check (Paused)'])
    } finally {
      vi.useRealTimers()
    }
  })

  it('sorts, defaulting to recently updated, and remembers the choice', () => {
    const { unmount } = render(<AutomationsPanel />)
    expect(rows()).toEqual(['budget check (Paused)', 'Award intake (Active)', 'Closeout reminders (Paused)'])

    fireEvent.change(screen.getByRole('combobox', { name: 'Sort automations' }), { target: { value: 'name' } })
    expect(rows()).toEqual(['Award intake (Active)', 'budget check (Paused)', 'Closeout reminders (Paused)'])
    unmount()

    render(<AutomationsPanel />)
    expect(screen.getByRole<HTMLSelectElement>('combobox', { name: 'Sort automations' }).value).toBe('name')
  })
})

describe('sortAutomations', () => {
  it('orders by status running, active, paused, then name', () => {
    const sorted = sortAutomations(automations, 'status', new Set(['c']))
    expect(sorted.map(a => a.id)).toEqual(['c', 'a', 'b'])
  })

  it('orders newest by creation date and does not mutate the input', () => {
    const before = automations.map(a => a.id)
    expect(sortAutomations(automations, 'newest').map(a => a.id)).toEqual(['c', 'a', 'b'])
    expect(automations.map(a => a.id)).toEqual(before)
  })
})
