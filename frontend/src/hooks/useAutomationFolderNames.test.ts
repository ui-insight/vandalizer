import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { useAutomationFolderNames } from './useAutomationFolderNames'
import { listAllFolders, type FolderSummary } from '../api/folders'
const scope = vi.hoisted(() => ({ team: 'A' }))
vi.mock('./useTeams', () => ({ useTeams: () => ({ currentTeam: { uuid: scope.team } }) }))
vi.mock('../api/folders', () => ({ listAllFolders: vi.fn() }))
beforeEach(() => { scope.team = 'A'; vi.mocked(listAllFolders).mockReset() })
it('does not let an old team folder response overwrite the current names', async () => {
  let finish!: (value: FolderSummary[]) => void
  vi.mocked(listAllFolders).mockReturnValueOnce(new Promise(r => { finish = r })).mockResolvedValueOnce([{ uuid: 'b', path: 'B folder' } as FolderSummary])
  const { result, rerender } = renderHook(() => useAutomationFolderNames())
  scope.team = 'B'; rerender()
  await waitFor(() => expect(result.current.folders[0]?.uuid).toBe('b'))
  await act(async () => finish([{ uuid: 'a', path: 'A folder' } as FolderSummary]))
  expect(result.current.folders.map(f => f.uuid)).toEqual(['b'])
})
it('exposes a folder-name failure and retries it', async () => {
  vi.mocked(listAllFolders).mockRejectedValueOnce(new Error('Folder list unavailable')).mockResolvedValueOnce([{ uuid: 'a', path: 'Incoming' } as FolderSummary])
  const { result } = renderHook(() => useAutomationFolderNames())
  await waitFor(() => expect(result.current.error).toBe('Folder list unavailable'))
  await act(async () => { await result.current.refresh() })
  expect(result.current.error).toBeNull(); expect(result.current.folders[0].path).toBe('Incoming')
})
