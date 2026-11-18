import { renderHook, waitFor, act } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { WorkspaceProvider, useWorkspace } from './WorkspaceContext'

// Campus Services wanted to link from SharePoint to a knowledge base. The
// server refuses a knowledge base that isn't shared with the opener, but the
// page said nothing and opened an ordinary chat, so the answers that followed
// quietly didn't use it.

const mocks = vi.hoisted(() => ({
  search: {} as Record<string, string>,
  toast: vi.fn(),
  getKnowledgeBase: vi.fn(),
  resolveTitles: vi.fn(),
}))
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => vi.fn(), useSearch: () => mocks.search }))
vi.mock('../hooks/useTeams', () => ({ useTeams: () => ({ currentTeam: { uuid: 'team-1' }, loading: false }) }))
vi.mock('./ToastContext', () => ({ useToast: () => ({ toast: mocks.toast }) }))
vi.mock('../api/documents', () => ({ resolveTitles: mocks.resolveTitles }))
vi.mock('../api/knowledge', () => ({ getKnowledgeBase: mocks.getKnowledgeBase }))
vi.mock('../api/projects', () => ({ getProject: vi.fn() }))

const setup = () => renderHook(() => useWorkspace(), { wrapper: WorkspaceProvider })
const notFound = () => new ApiError(404, 'Knowledge base not found')

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  vi.clearAllMocks()
  mocks.search = {}
  mocks.resolveTitles.mockResolvedValue({ documents: [], folders: [] })
})

it('says so when the one knowledge base in a link is not shared with the opener', async () => {
  mocks.search = { kb: 'kb-private' }
  mocks.getKnowledgeBase.mockRejectedValue(notFound())
  const { result } = setup()
  await waitFor(() => expect(mocks.toast).toHaveBeenCalled())
  const [message, type] = mocks.toast.mock.calls[0]
  expect(message).toContain('knowledge base in this link isn’t shared with you')
  // An error toast stays until dismissed; an info toast is gone in 4 seconds.
  expect(type).toBe('error')
  expect(result.current.activeKBs).toEqual([])
})

it('does not blame sharing when the link could not be checked', async () => {
  mocks.search = { kb: 'kb-1' }
  mocks.getKnowledgeBase.mockRejectedValue(new ApiError(0, 'Network error'))
  setup()
  await waitFor(() => expect(mocks.toast).toHaveBeenCalled())
  expect(mocks.toast.mock.calls[0][0]).not.toContain('shared')
})

it('attaches a shared knowledge base without a warning', async () => {
  mocks.search = { kb: 'kb-1' }
  mocks.getKnowledgeBase.mockResolvedValue({ uuid: 'kb-1', title: 'Campus Services' })
  const { result } = setup()
  await waitFor(() => expect(result.current.activeKBs).toEqual([{ uuid: 'kb-1', title: 'Campus Services' }]))
  expect(mocks.toast).not.toHaveBeenCalled()
})

it('says so when an attached knowledge base is no longer available on return', async () => {
  mocks.getKnowledgeBase.mockResolvedValue({ uuid: 'kb-1', title: 'Campus Services' })
  const first = setup()
  act(() => first.result.current.activateKB('kb-1', 'Campus Services'))
  await waitFor(() => expect(first.result.current.activeKBs).toHaveLength(1))
  first.unmount()

  mocks.getKnowledgeBase.mockRejectedValue(notFound())
  const { result } = setup()
  await waitFor(() => expect(mocks.toast).toHaveBeenCalled())
  expect(mocks.toast.mock.calls[0][0]).toContain('no longer available to you')
  expect(result.current.activeKBs).toEqual([])
})
