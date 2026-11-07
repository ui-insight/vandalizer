import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ActivityEvent } from '../../types/chat'

const refresh = vi.fn()
const toast = vi.fn()
const renameActivity = vi.fn()
const openActivity = vi.fn()

const chat = (overrides: Partial<ActivityEvent> = {}): ActivityEvent => ({
  id: 'chat-1', type: 'conversation', status: 'completed',
  title: 'add PAPPG.pdf and nih-r01-neuroscience.pdf to the',
  conversation_id: 'conv-1', search_set_uuid: null, workflow_id: null, workflow_session_id: null,
  started_at: '2026-10-13T00:00:00Z', finished_at: '2026-10-13T00:00:00Z', last_updated_at: '2026-10-13T00:00:00Z',
  error: '', tokens_input: 0, tokens_output: 0, message_count: 2, result_snapshot: {},
  meta_summary: { description_generated: true }, ...overrides,
})
let activities: ActivityEvent[] = []
let currentConversationUuid: string | null = null
let certification: Record<string, unknown> = { progress: null, course: null }

vi.mock('@tanstack/react-router', () => ({ useNavigate: () => vi.fn() }))
vi.mock('../../hooks/useActivities', () => ({
  useActivities: () => ({ activities, loading: false, error: null, refresh, staleThresholdMinutes: 30 }),
}))
vi.mock('../../hooks/useMyReviewCount', () => ({ useMyReviewCount: () => ({ count: 0 }) }))
vi.mock('../../api/activity', () => ({
  deleteActivity: vi.fn(),
  renameActivity: (...args: unknown[]) => renameActivity(...args),
}))
vi.mock('../../contexts/WorkspaceContext', () => ({
  useWorkspace: () => ({
    railDocked: false, toggleRailDocked: vi.fn(), triggerNewChat: vi.fn(), focusChat: vi.fn(),
    activitySignal: 0, currentConversationUuid, openWorkflowId: null, openExtractionId: null,
  }),
}))
vi.mock('../../hooks/useOpenActivity', () => ({
  pendingReviewUuid: () => null,
  useOpenActivity: () => ({ openActivity }),
}))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast }) }))
vi.mock('../shared/useConfirm', () => ({ useConfirm: () => vi.fn() }))
vi.mock('../../contexts/CertificationPanelContext', () => ({
  useCertificationPanel: () => ({ openPanel: vi.fn(), ...certification }),
}))

import { ActivityRail } from './ActivityRail'

const run = (overrides: Partial<ActivityEvent> = {}): ActivityEvent => chat({
  id: 'run-1', type: 'search_set_run', title: 'NSF Subaward UI-BSU-2024-0847 Extraction',
  conversation_id: null, search_set_uuid: 'ss-1', message_count: 0,
  started_at: '2026-10-13T10:42:00Z', meta_summary: {}, ...overrides,
})

beforeEach(() => {
  vi.clearAllMocks()
  currentConversationUuid = null
  certification = { progress: null, course: null }
  activities = [
    run({ id: 'run-2', type: 'workflow_run', title: 'Subaward Review Summary v2', source_conversation_id: 'conv-1',
      document_titles: ['NIFA.pdf'], started_at: '2026-10-13T11:05:00Z' }),
    run({ id: 'run-1', source_conversation_id: 'conv-1', document_titles: ['subaward-agreement.pdf'] }),
    run({ id: 'run-3', status: 'failed', source_conversation_id: 'conv-1',
      error: 'failed: name already exists\nTraceback (most recent call last): a very long trace' }),
    run({ id: 'editor-run', title: 'Budget Extraction', document_titles: ['budget.xlsx'] }),
    chat({ title: 'Full Life Cycle Test' }),
  ]
})

describe("activity list groups a chat's runs under it (ticket)", () => {
  it('keeps history behind one expand control when docked and restores titles when expanded', () => {
    const expand = vi.fn()
    const view = render(<ActivityRail forceDocked onExpand={expand} />)
    expect(screen.getByRole('button', { name: 'New chat' })).toBeInTheDocument()
    expect(screen.queryByText('Full Life Cycle Test')).not.toBeInTheDocument()
    expect(screen.queryByText('Budget Extraction')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Expand activity' }))
    expect(expand).toHaveBeenCalledOnce()
    view.rerender(<ActivityRail forceExpanded />)
    expect(screen.getByText('Full Life Cycle Test')).toBeInTheDocument()
    expect(screen.getByText('Budget Extraction')).toBeInTheDocument()
  })

  it('shows the chat with its run count and hides its runs until expanded', () => {
    render(<ActivityRail />)

    const toggle = screen.getByRole('button', { name: 'Show 3 runs from Full Life Cycle Test' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('group', { name: 'Runs from Full Life Cycle Test' })).not.toBeInTheDocument()

    fireEvent.click(toggle)
    const runs = within(screen.getByRole('group', { name: 'Runs from Full Life Cycle Test' }))
    expect(runs.getByText('Subaward Review Summary v2')).toBeInTheDocument()
    expect(runs.getByText(/Workflow · NIFA\.pdf/)).toBeInTheDocument()
    expect(runs.getByText(/Extraction · subaward-agreement\.pdf/)).toBeInTheDocument()
    expect(runs.queryByText('Budget Extraction')).not.toBeInTheDocument()
  })

  it('opens the chat in use with its runs showing, above the runs it started', () => {
    currentConversationUuid = 'conv-1'
    render(<ActivityRail />)

    expect(screen.getByRole('button', { name: 'Hide 3 runs from Full Life Cycle Test' })).toBeInTheDocument()
    const opens = screen.getAllByRole('button', { name: /^Open / }).map(b => b.getAttribute('aria-label'))
    expect(opens[0]).toMatch(/^Open Full Life Cycle Test/)
  })

  it('shows a recent editor run above 42 older conversations after a fresh mount', () => {
    const editorRun = run({ id: 'editor-run', type: 'workflow_run', title: 'Subaward report', workflow_id: 'wf-1', workflow_session_id: 'session-1' })
    activities = [...Array.from({ length: 42 }, (_, i) => chat({ id: `chat-${i}`, conversation_id: `conv-${i}`, title: `Conversation ${i}` })), editorRun]
    render(<ActivityRail />)
    const opens = screen.getAllByRole('button', { name: /^Open (Workflow|Conversation)/ })
    expect(opens[0]).toHaveAccessibleName('Open Workflow Subaward report: Completed')
    expect(screen.queryByRole('button', { name: /Other runs/ })).not.toBeInTheDocument()
    fireEvent.click(opens[0])
    expect(openActivity).toHaveBeenCalledWith(editorRun)
  })

  it('shows one line of a long error and the rest on Details', () => {
    currentConversationUuid = 'conv-1'
    render(<ActivityRail />)

    expect(screen.getByText('failed: name already exists')).toBeInTheDocument()
    expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Details' }))
    expect(screen.getByText(/Traceback \(most recent call last\)/)).toBeInTheDocument()
  })
})

describe('activity attention filters', () => {
  it('finds a failed child without losing its parent chat, then restores the full history', () => {
    render(<ActivityRail />)
    fireEvent.click(screen.getByRole('button', { name: /^Issues/ }))
    const runs = within(screen.getByRole('group', { name: 'Runs from Full Life Cycle Test' }))
    expect(runs.getByRole('button', { name: /: Failed$/ })).toBeInTheDocument()
    expect(runs.queryByText('Subaward Review Summary v2')).not.toBeInTheDocument()
    expect(screen.queryByText('Budget Extraction')).not.toBeInTheDocument()
    expect(screen.getByText('1 of 3 linked runs')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show all 3 runs from Full Life Cycle Test' }))
    expect(screen.getByText('Budget Extraction')).toBeInTheDocument()
    expect(screen.getByText('Subaward Review Summary v2')).toBeInTheDocument()
  })

  it('opens the issues filter from a docked badge and includes timeouts', () => {
    activities.push(run({ id: 'stale', status: 'running', title: 'Stalled run' }))
    const expand = vi.fn()
    const view = render(<ActivityRail forceDocked onExpand={expand} />)
    fireEvent.click(screen.getByRole('button', { name: '2 activities with issues' }))
    expect(expand).toHaveBeenCalledOnce()
    view.rerender(<ActivityRail forceExpanded />)
    expect(screen.getByRole('button', { name: /^Issues/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Open Extraction Stalled run: Timed out' })).toBeInTheDocument()
  })

  it('keeps only fresh running and queued work in progress', () => {
    const now = new Date().toISOString()
    activities = [
      run({ id: 'fresh', title: 'Working now', status: 'running', last_updated_at: now }),
      run({ id: 'queued', title: 'Next up', status: 'queued', last_updated_at: now }),
      run({ id: 'stale', title: 'Stalled', status: 'running' }),
      run({ id: 'done', title: 'Finished', status: 'completed' }),
    ]
    render(<ActivityRail />)
    fireEvent.click(screen.getByRole('button', { name: 'In progress 2' }))
    expect(screen.getByText('Working now')).toBeInTheDocument()
    expect(screen.getByText('Next up')).toBeInTheDocument()
    expect(screen.queryByText('Stalled')).not.toBeInTheDocument()
    expect(screen.queryByText('Finished')).not.toBeInTheDocument()
  })

  it('marks the open conversation and shows an empty filter without hiding navigation', () => {
    currentConversationUuid = 'conv-1'
    render(<ActivityRail />)
    expect(screen.getByRole('button', { name: /^Open Full Life Cycle Test/ })).toHaveAttribute('aria-current', 'true')
    fireEvent.click(screen.getByRole('button', { name: /^In progress/ }))
    expect(screen.getByText('Nothing in progress')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New chat' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'View all activity' }))
    expect(screen.getByText('Full Life Cycle Test')).toBeInTheDocument()
  })
})
