import { act, renderHook } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { useOpenActivity } from './useOpenActivity'
import { getActivity } from '../api/activity'

const mocks = vi.hoisted(() => ({
  setActiveRightTab: vi.fn(), setLoadConversationId: vi.fn(),
  closeWorkflow: vi.fn(), closeExtraction: vi.fn(), closeAutomation: vi.fn(), toast: vi.fn(),
}))
vi.mock('../contexts/WorkspaceContext', () => ({ useWorkspace: () => mocks }))
vi.mock('../contexts/ToastContext', () => ({ useToast: () => ({ toast: mocks.toast }) }))
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => vi.fn() }))
vi.mock('../api/activity', () => ({ getActivity: vi.fn() }))
beforeEach(() => vi.clearAllMocks())

it('loads the exact saved conversation identified by an activity', async () => {
  vi.mocked(getActivity).mockResolvedValue({ activity: { id: 'activity-id', type: 'conversation', conversation_id: 'original-chat' } } as Awaited<ReturnType<typeof getActivity>>)
  const { result } = renderHook(() => useOpenActivity())
  await act(async () => { await result.current.openActivityById('activity-id') })
  expect(getActivity).toHaveBeenCalledWith('activity-id')
  expect(mocks.setLoadConversationId).toHaveBeenCalledWith('original-chat')
  expect(mocks.setActiveRightTab).toHaveBeenCalledWith('assistant')
  expect(mocks.closeWorkflow).toHaveBeenCalledOnce()
})

it('reports an unavailable activity without opening a different chat', async () => {
  vi.mocked(getActivity).mockRejectedValue(new Error('Activity not found'))
  const { result } = renderHook(() => useOpenActivity())
  await act(async () => { await result.current.openActivityById('deleted') })
  expect(mocks.toast).toHaveBeenCalledWith('Activity not found', 'error')
  expect(mocks.setLoadConversationId).not.toHaveBeenCalled()
})
