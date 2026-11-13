import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { WorkspaceProvider, useWorkspace } from './WorkspaceContext'

const mocks = vi.hoisted(() => ({
  search: {} as Record<string, string>,
  team: { uuid: 'team-1' } as { uuid: string } | null,
  resolveTitles: vi.fn(),
}))
vi.mock('@tanstack/react-router', () => ({ useNavigate: () => vi.fn(), useSearch: () => mocks.search }))
vi.mock('../hooks/useTeams', () => ({ useTeams: () => ({ currentTeam: mocks.team, loading: false }) }))
vi.mock('./ToastContext', () => ({ useToast: () => ({ toast: vi.fn() }) }))
vi.mock('../api/documents', () => ({ resolveTitles: mocks.resolveTitles }))

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
