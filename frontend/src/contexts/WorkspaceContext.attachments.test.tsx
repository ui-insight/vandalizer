import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { WorkspaceProvider, useWorkspace } from './WorkspaceContext'

const mocks = vi.hoisted(() => ({
  search: {} as Record<string, string>,
  team: { uuid: 'team-1' } as { uuid: string } | null,
  resolveTitles: vi.fn(),
  getProject: vi.fn(),
}))
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => vi.fn(), useSearch: () => mocks.search }))
vi.mock('../hooks/useTeams', () => ({ useTeams: () => ({ currentTeam: mocks.team, loading: false }) }))
vi.mock('./ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../api/documents', () => ({ resolveTitles: mocks.resolveTitles }))
vi.mock('../api/projects', () => ({ getProject: mocks.getProject }))

const setup = () => renderHook(() => useWorkspace(), { wrapper: WorkspaceProvider })

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  vi.clearAllMocks()
  mocks.search = {}
  mocks.team = { uuid: 'team-1' }
  mocks.resolveTitles.mockResolvedValue({ documents: [{ uuid: 'budget', title: 'NIH_R01_Budget_Clean.xlsx' }], folders: [] })
})

function attachBudget(result: ReturnType<typeof setup>['result']) {
  act(() => {
    result.current.setSelectedDocUuids(['budget'])
    result.current.setSelectedDocNames({ budget: 'NIH_R01_Budget_Clean.xlsx' })
  })
}

// Support ticket: opening Assistant settings from the chat toolbar and coming
// back kept the typed message but dropped the selected file.
it('keeps the selected file when the workspace is left and opened again', async () => {
  const first = setup()
  attachBudget(first.result)
  first.unmount()

  const { result } = setup()
  await waitFor(() => expect(result.current.selectedDocUuids).toEqual(['budget']))
  expect(result.current.selectedDocNames).toEqual({ budget: 'NIH_R01_Budget_Clean.xlsx' })
  expect(mocks.resolveTitles).toHaveBeenCalledWith(['budget'], [])
})

it('drops files that no longer resolve, and forgets a cleared attachment', async () => {
  const first = setup()
  act(() => first.result.current.setSelectedDocUuids(['budget', 'deleted']))
  first.unmount()

  const second = setup()
  await waitFor(() => expect(second.result.current.selectedDocUuids).toEqual(['budget']))
  act(() => second.result.current.triggerNewChat())
  second.unmount()

  const { result } = setup()
  await act(async () => {})
  expect(result.current.selectedDocUuids).toEqual([])
  expect(mocks.resolveTitles).toHaveBeenCalledTimes(1)
})

it('does not carry an attachment into another team', async () => {
  const first = setup()
  attachBudget(first.result)
  first.unmount()

  mocks.team = { uuid: 'team-2' }
  const { result } = setup()
  await act(async () => {})
  expect(result.current.selectedDocUuids).toEqual([])
  expect(mocks.resolveTitles).not.toHaveBeenCalled()
})

it('lets a chat link set up its own attachment instead', async () => {
  const first = setup()
  attachBudget(first.result)
  first.unmount()

  mocks.search = { docs: 'other' }
  mocks.resolveTitles.mockResolvedValue({ documents: [{ uuid: 'other', title: 'Other.pdf' }], folders: [] })
  const { result } = setup()
  await waitFor(() => expect(result.current.selectedDocUuids).toEqual(['other']))
  // (The mocked router never clears the link's params, so the link resolves
  // repeatedly here; what matters is that the stored file was never restored.)
  expect(mocks.resolveTitles).not.toHaveBeenCalledWith(['budget'], [])
})

const stored = () => JSON.parse(sessionStorage.getItem('vandalizer:chat-attachments') || 'null')
const deferred = <T,>() => {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

it('re-applies the unsent attachment over the reopened conversation\'s saved scope', async () => {
  const first = setup()
  act(() => first.result.current.setCurrentConversationUuid('convo-1'))
  attachBudget(first.result)
  expect(stored().conversation).toBe('convo-1')
  first.unmount()

  const { result } = setup()
  await waitFor(() => expect(result.current.selectedDocUuids).toEqual(['budget']))
  // The chat then reloads convo-1, whose saved scope predates the attachment.
  act(() => {
    result.current.setSelectedDocUuids([])
    result.current.reapplyRestoredAttachments('convo-1')
  })
  expect(result.current.selectedDocUuids).toEqual(['budget'])
  // Only once: opening the conversation again later uses its own scope.
  act(() => {
    result.current.setSelectedDocUuids([])
    result.current.reapplyRestoredAttachments('convo-1')
  })
  expect(result.current.selectedDocUuids).toEqual([])
})

it('waits for a stored project to load before restoring or rewriting the attachment', async () => {
  localStorage.setItem('workspace:project', 'p1')
  sessionStorage.setItem('vandalizer:chat-attachments', JSON.stringify({ team: 'team-1', project: 'p1', conversation: null, documents: ['budget'], folders: [] }))
  const project = deferred<unknown>()
  mocks.getProject.mockReturnValue(project.promise)

  const { result } = setup()
  await act(async () => {})
  // Project still loading: nothing restored, and storage keeps the project.
  expect(mocks.resolveTitles).not.toHaveBeenCalled()
  expect(stored().project).toBe('p1')

  await act(async () => project.resolve({ uuid: 'p1', title: 'P1', root_folder_uuid: 'root', team_id: 'team-1', role: 'editor' }))
  await waitFor(() => expect(result.current.selectedDocUuids).toEqual(['budget']))
  expect(result.current.activeProjectUuid).toBe('p1')
  expect(stored().project).toBe('p1')
})

it('never restores a project\'s files into Home when the project fails to load', async () => {
  localStorage.setItem('workspace:project', 'p1')
  sessionStorage.setItem('vandalizer:chat-attachments', JSON.stringify({ team: 'team-1', project: 'p1', conversation: null, documents: ['budget'], folders: [] }))
  mocks.getProject.mockRejectedValue(new Error('gone'))

  const { result } = setup()
  await waitFor(() => expect(localStorage.getItem('workspace:project')).toBeNull())
  await act(async () => {})
  expect(result.current.activeProjectUuid).toBeNull()
  expect(result.current.selectedDocUuids).toEqual([])
  expect(mocks.resolveTitles).not.toHaveBeenCalled()
})

it('New chat during the restore wins', async () => {
  const first = setup()
  attachBudget(first.result)
  first.unmount()

  const titles = deferred<unknown>()
  mocks.resolveTitles.mockReturnValue(titles.promise)
  const { result } = setup()
  await waitFor(() => expect(mocks.resolveTitles).toHaveBeenCalled())
  act(() => result.current.triggerNewChat())
  await act(async () => titles.resolve({ documents: [{ uuid: 'budget', title: 'NIH_R01_Budget_Clean.xlsx' }], folders: [] }))
  expect(result.current.selectedDocUuids).toEqual([])
  expect(stored()).toBeNull()
})
