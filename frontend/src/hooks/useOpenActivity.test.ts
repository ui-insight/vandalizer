import { act, renderHook } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { useOpenActivity } from './useOpenActivity'
import { getActivity } from '../api/activity'

const mocks = vi.hoisted(() => ({
  focusChat: vi.fn(), setLoadConversationId: vi.fn(),
  openWorkflow: vi.fn(), navigate: vi.fn(), closeWorkflow: vi.fn(), closeExtraction: vi.fn(), closeAutomation: vi.fn(), toast: vi.fn(),
}))
vi.mock('../contexts/WorkspaceContext', () => ({ useWorkspace: () => mocks }))
vi.mock('../contexts/ToastContext', () => ({ useToast: () => ({ toast: mocks.toast }) }))
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => mocks.navigate }))
vi.mock('../api/activity', () => ({ getActivity: vi.fn() }))
beforeEach(() => vi.clearAllMocks())

it('loads the exact saved conversation identified by an activity', async () => {
  vi.mocked(getActivity).mockResolvedValue({ activity: { id: 'activity-id', type: 'conversation', conversation_id: 'original-chat' } } as Awaited<ReturnType<typeof getActivity>>)
  const { result } = renderHook(() => useOpenActivity())
  await act(async () => { await result.current.openActivityById('activity-id') })
  expect(getActivity).toHaveBeenCalledWith('activity-id')
  expect(mocks.setLoadConversationId).toHaveBeenCalledWith('original-chat')
  expect(mocks.focusChat).toHaveBeenCalledOnce()
  expect(mocks.closeWorkflow).toHaveBeenCalledOnce()
})

it('reports an unavailable activity without opening a different chat', async () => {
  vi.mocked(getActivity).mockRejectedValue(new Error('Activity not found'))
  const { result } = renderHook(() => useOpenActivity())
  await act(async () => { await result.current.openActivityById('deleted') })
  expect(mocks.toast).toHaveBeenCalledWith('Activity not found', 'error')
  expect(mocks.setLoadConversationId).not.toHaveBeenCalled()
})

it.each(['failed', 'canceled', 'completed'] as const)('opens the %s run instead of an obsolete approval marker', status => {
  const { result } = renderHook(() => useOpenActivity())
  act(() => result.current.openActivity({ id: 'activity-1', title: 'Review', type: 'workflow_run', status, workflow_id: 'wf-1', workflow_session_id: 'session-1', conversation_id: null, search_set_uuid: null, started_at: null, finished_at: null, last_updated_at: null, error: '', tokens_input: 0, tokens_output: 0, message_count: 0, result_snapshot: {}, meta_summary: { pending_review_uuid: 'old-review' } }))
  expect(mocks.openWorkflow).toHaveBeenCalledWith('wf-1', 'session-1')
  expect(mocks.navigate).not.toHaveBeenCalled()
})
