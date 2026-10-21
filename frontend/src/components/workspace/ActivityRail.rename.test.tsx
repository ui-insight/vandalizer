import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ActivityEvent } from '../../types/chat'

const refresh = vi.fn()
const toast = vi.fn()
const renameActivity = vi.fn()

const chat = (overrides: Partial<ActivityEvent> = {}): ActivityEvent => ({
  id: 'chat-1', type: 'conversation', status: 'completed',
  title: 'add PAPPG.pdf and nih-r01-neuroscience.pdf to the',
  conversation_id: 'conv-1', search_set_uuid: null, workflow_id: null, workflow_session_id: null,
  started_at: '2026-10-13T00:00:00Z', finished_at: '2026-10-13T00:00:00Z', last_updated_at: '2026-10-13T00:00:00Z',
  error: '', tokens_input: 0, tokens_output: 0, message_count: 2, result_snapshot: {},
  meta_summary: { description_generated: true }, ...overrides,
})
let activities: ActivityEvent[] = []
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
    activitySignal: 0, currentConversationUuid: null, openWorkflowId: null, openExtractionId: null,
  }),
}))
vi.mock('../../hooks/useOpenActivity', () => ({
  pendingReviewUuid: () => null,
  useOpenActivity: () => ({ openActivity: vi.fn() }),
}))
vi.mock('../../contexts/ToastContext', () => ({ useToast: () => ({ toast }) }))
vi.mock('../shared/useConfirm', () => ({ useConfirm: () => vi.fn() }))
vi.mock('../../contexts/CertificationPanelContext', () => ({
  useCertificationPanel: () => ({ openPanel: vi.fn(), ...certification }),
}))

import { ActivityRail } from './ActivityRail'

beforeEach(() => {
  vi.clearAllMocks()
  activities = [chat()]
  certification = { progress: null, course: null }
})

function startRename() {
  fireEvent.click(screen.getByRole('button', { name: /^Rename chat:/ }))
  return screen.getByLabelText('Chat name') as HTMLInputElement
}

describe('renaming a chat in the activity list (ticket)', () => {
  it('saves the new name and refreshes the list', async () => {
    renameActivity.mockResolvedValue({ activity: chat({ title: 'PAPPG and NIH R01 KB' }) })
    render(<ActivityRail />)
    const input = startRename()
    expect(input.value).toBe('add PAPPG.pdf and nih-r01-neuroscience.pdf to the')
    fireEvent.change(input, { target: { value: '  PAPPG and NIH R01 KB ' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(renameActivity).toHaveBeenCalledWith('chat-1', 'PAPPG and NIH R01 KB'))
    await waitFor(() => expect(refresh).toHaveBeenCalled())
    expect(screen.queryByLabelText('Chat name')).not.toBeInTheDocument()
  })

  it('Escape cancels without saving', () => {
    render(<ActivityRail />)
    const input = startRename()
    fireEvent.change(input, { target: { value: 'Something else' } })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(renameActivity).not.toHaveBeenCalled()
    expect(screen.queryByLabelText('Chat name')).not.toBeInTheDocument()
  })

  it('an empty or unchanged name is not saved', () => {
    render(<ActivityRail />)
    let input = startRename()
    fireEvent.submit(input.closest('form')!)
    input = startRename()
    fireEvent.change(input, { target: { value: '   ' } })
    fireEvent.submit(input.closest('form')!)
    expect(renameActivity).not.toHaveBeenCalled()
  })

  it('reports a failed rename and keeps the box open', async () => {
    renameActivity.mockRejectedValue(new Error('Keep chat names to 120 characters or fewer.'))
    render(<ActivityRail />)
    const input = startRename()
    fireEvent.change(input, { target: { value: 'New name' } })
    fireEvent.submit(input.closest('form')!)
    await waitFor(() => expect(toast).toHaveBeenCalledWith('Keep chat names to 120 characters or fewer.', 'error'))
    expect(screen.getByLabelText('Chat name')).toBeInTheDocument()
  })

  it('only chats can be renamed', () => {
    activities = [chat({ id: 'run-1', type: 'workflow_run', title: 'Workflow: NOA', conversation_id: null })]
    render(<ActivityRail />)
    expect(screen.queryByRole('button', { name: /^Rename chat:/ })).not.toBeInTheDocument()
  })
})

describe('certified label', () => {
  const certified = { certified: true, level: 'architect', total_xp: 1850, modules: {} }
  it('names an outcome-based course by its own title', () => {
    certification = { progress: certified, course: { course_title: 'Vandalizer 5.0 certification', credential_scope: { promise: 'Supervise a bounded task.' } } }
    render(<ActivityRail />)
    expect(screen.getByRole('button', { name: 'Open certification' })).toHaveAttribute('title', 'Vandalizer 5.0 certification')
    expect(screen.queryByText('Vandal Workflow Architect')).not.toBeInTheDocument()
  })
  it('keeps the legacy title for the legacy course', () => {
    certification = { progress: certified, course: { course_title: 'Vandal Workflow Architect — current course', credential_scope: null } }
    render(<ActivityRail />)
    expect(screen.getByRole('button', { name: 'Open certification' })).toHaveAttribute('title', 'Vandal Workflow Architect')
  })
})
