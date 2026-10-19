import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { AutomationsPanel } from './AutomationsPanel'
import { sortAutomations } from './automationList'
import type { Automation } from '../../types/automation'
const mock = vi.hoisted(() => ({
  items: [] as Automation[], error: null as string | null, loading: false, refresh: vi.fn(), open: vi.fn(),
  project: null as string | null, pinned: new Set<string>(), pinsError: null as string | null, pinsLoading: false, refreshPins: vi.fn(),
}))
vi.mock('../../hooks/useAutomationFolderNames', () => ({ useAutomationFolderNames: () => ({ folders: [], loading: false, error: null, refresh: vi.fn() }) }))
vi.mock('../../hooks/useAutomations', () => ({ useAutomations: () => ({ automations: mock.items, loading: mock.loading, error: mock.error, refresh: mock.refresh }) }))
vi.mock('../../contexts/WorkspaceContext', () => ({ useWorkspace: () => ({ openAutomation: mock.open, activeProjectUuid: mock.project, activeProjectTitle: 'Project A', activeProjectRole: 'viewer' }) }))
vi.mock('../../hooks/useWorkflows', () => ({ useWorkflows: () => ({ workflows: [] }) }))
vi.mock('../../hooks/useExtractions', () => ({ useSearchSets: () => ({ searchSets: [] }) }))
vi.mock('../../hooks/useProjectPins', () => ({ useProjectPins: () => ({ idsByType: () => mock.pinned, isPinned: () => false, pin: vi.fn(), unpin: vi.fn(), loading: mock.pinsLoading, error: mock.pinsError, refresh: mock.refreshPins }) }))
vi.mock('../../api/config', () => ({ getFeatureFlags: vi.fn().mockResolvedValue({ m365_enabled: false }) }))
vi.mock('./AutomationsExplainer', () => ({ AutomationsExplainer: () => <div>Create your first automation</div> }))
vi.mock('./AutomationCreationWizard', () => ({ AutomationCreationWizard: () => null }))
const item = (id: string, name: string, trigger_type: Automation['trigger_type'], description = '') => ({ id, name, trigger_type, description, trigger_config: {}, action_type: 'workflow', output_config: {} } as Automation)
beforeEach(() => {
  vi.clearAllMocks(); mock.error = null; mock.loading = false; mock.project = null; mock.pinsError = null; mock.pinsLoading = false; mock.pinned = new Set()
  mock.items = [item('folder', 'Proposal review', 'folder_watch'), item('api', 'Incoming awards', 'api', 'Proposal intake'), item('schedule', 'Weekly proposal', 'schedule'), item('m365', 'Mailbox intake', 'm365_intake')]
})
describe('automation list filtering and recovery', () => {
  it('combines trimmed case-insensitive search with type and clears both filters', () => {
    render(<AutomationsPanel />)
    fireEvent.change(screen.getByRole('textbox', { name: 'Filter automations' }), { target: { value: ' PROPOSAL ' } })
    fireEvent.click(screen.getByRole('button', { name: 'API: 1 automations' }))
    expect(screen.getByRole('button', { name: 'API: 1 automations' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Open automation: Incoming awards' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Open automation: Proposal review' })).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('1 of 4 automations')
    fireEvent.change(screen.getByRole('textbox', { name: 'Filter automations' }), { target: { value: 'absent' } })
    expect(screen.getByText('No matching automations')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(screen.getAllByRole('button', { name: /Open automation:/ })).toHaveLength(4)
    expect(screen.getByRole('textbox', { name: 'Filter automations' })).toHaveValue('')
    fireEvent.click(screen.getByRole('button', { name: 'Open automation: Weekly proposal' }))
    expect(mock.open).toHaveBeenCalledWith('schedule')
  })
  it('keeps existing M365 items filterable when new M365 creation is disabled', () => {
    render(<AutomationsPanel />); fireEvent.click(screen.getByRole('button', { name: 'M365: 1 automations' }))
    expect(screen.getAllByRole('button', { name: /Open automation:/ })).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Open automation: Mailbox intake' })).toBeInTheDocument()
  })
  it('retries an unavailable list without claiming it is empty', () => {
    mock.items = []; mock.error = 'Service unavailable'; render(<AutomationsPanel />)
    expect(screen.getByRole('alert')).toHaveTextContent('Service unavailable')
    expect(screen.queryByText('No automations yet')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry automations' })); expect(mock.refresh).toHaveBeenCalledOnce()
  })
  it('retains loaded rows and filters when refreshing fails', () => {
    const { rerender } = render(<AutomationsPanel />)
    fireEvent.change(screen.getByRole('textbox', { name: 'Filter automations' }), { target: { value: 'awards' } })
    mock.error = 'Refresh failed'; rerender(<AutomationsPanel />)
    expect(screen.getByRole('alert')).toHaveTextContent('previously loaded')
    expect(screen.getByRole('button', { name: 'Open automation: Incoming awards' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Filter automations' })).toHaveValue('awards')
  })
  it('keeps counts and clearing inside the current project scope', () => {
    mock.project = 'project-a'; mock.pinned = new Set(['api', 'schedule']); render(<AutomationsPanel />)
    expect(screen.getByRole('button', { name: 'All: 2 automations' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Folder Watch: 0 automations' }))
    expect(screen.getByText('No matching automations')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(screen.getAllByRole('button', { name: /Open automation:/ })).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Show all' }))
    expect(screen.getByRole('button', { name: 'All: 4 automations' })).toBeInTheDocument()
  })
  it('distinguishes pin loading or failure from an empty project and retries it', () => {
    mock.project = 'project-a'; mock.pinsLoading = true; const { rerender } = render(<AutomationsPanel />)
    expect(screen.getByRole('status', { name: 'Loading automations' })).toBeInTheDocument()
    expect(screen.queryByText('No automations pinned to this project')).not.toBeInTheDocument()
    mock.pinsLoading = false; mock.pinsError = 'Pins unavailable'; rerender(<AutomationsPanel />)
    expect(screen.getByRole('alert')).toHaveTextContent('Pins unavailable')
    expect(screen.queryByText('No automations pinned to this project')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Retry automations' }))
    expect(mock.refreshPins).toHaveBeenCalledOnce()
  })
})

// Automations list: a named status, a sort. Status used to be a bare colored
// dot (#1030).
describe('automation status and sort', () => {
  const auto = (id: string, name: string, overrides: Partial<Automation> = {}): Automation => ({
    id, name, description: null, enabled: true, trigger_type: 'folder_watch', trigger_config: {},
    action_type: 'workflow', action_id: null, action_name: 'Summarize', user_id: 'u', team_id: null,
    shared_with_team: false, output_config: {}, created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z', can_manage: true, ...overrides,
  })
  const rows = () => screen.getAllByRole('button', { name: /^Open automation:/ })
    .map(r => r.getAttribute('aria-label')!.replace('Open automation: ', ''))
  // The whole card, not just its name button.
  const row = (name: string) => screen.getByRole('button', { name: `Open automation: ${name}` }).parentElement!.parentElement!

  beforeEach(() => {
    try { localStorage.clear() } catch { /* jsdom always has it */ }
    mock.items = [
      auto('a', 'Award intake', { updated_at: '2026-03-01T00:00:00Z', created_at: '2026-01-05T00:00:00Z' }),
      auto('b', 'budget check', { enabled: false, updated_at: '2026-05-01T00:00:00Z', created_at: '2026-01-01T00:00:00Z' }),
      auto('c', 'Closeout reminders', { trigger_type: 'schedule', enabled: false, next_run_at: '2026-11-01T15:00:00Z', updated_at: '2026-02-01T00:00:00Z', created_at: '2026-02-01T00:00:00Z' }),
    ]
  })

  it('names every status in text, not only by color', () => {
    render(<AutomationsPanel activeIds={new Set(['a'])} />)
    expect(within(row('Award intake')).getByText('Running')).toBeTruthy()
    expect(within(row('budget check')).getByText('Paused')).toBeTruthy()
    // A paused schedule says Paused once, on the pill — no "Next run" for it.
    expect(within(row('Closeout reminders')).getAllByText('Paused')).toHaveLength(1)
    expect(within(row('Closeout reminders')).queryByText(/Next run/)).toBeNull()
  })

  it('says Active for an automation that is on and idle', () => {
    render(<AutomationsPanel />)
    expect(within(row('Award intake')).getByText('Active')).toBeTruthy()
  })

  it('sorts, defaulting to recently updated, and remembers the choice', () => {
    const { unmount } = render(<AutomationsPanel />)
    expect(rows()).toEqual(['budget check', 'Award intake', 'Closeout reminders'])

    fireEvent.change(screen.getByRole('combobox', { name: 'Sort automations' }), { target: { value: 'name' } })
    expect(rows()).toEqual(['Award intake', 'budget check', 'Closeout reminders'])
    unmount()

    render(<AutomationsPanel />)
    expect(screen.getByRole<HTMLSelectElement>('combobox', { name: 'Sort automations' }).value).toBe('name')
  })
})

describe('sortAutomations', () => {
  const at = (id: string, enabled: boolean, created_at: string) => ({ id, name: id, enabled, created_at, updated_at: created_at } as Automation)
  const list = [at('a', true, '2026-01-05T00:00:00Z'), at('b', false, '2026-01-01T00:00:00Z'), at('c', false, '2026-02-01T00:00:00Z')]

  it('orders by status running, active, paused, then name', () => {
    const sorted = sortAutomations(list, 'status', new Set(['c']))
    expect(sorted.map(a => a.id)).toEqual(['c', 'a', 'b'])
  })

  it('orders newest by creation date and does not mutate the input', () => {
    const before = list.map(a => a.id)
    expect(sortAutomations(list, 'newest').map(a => a.id)).toEqual(['c', 'a', 'b'])
    expect(list.map(a => a.id)).toEqual(before)
  })
})
