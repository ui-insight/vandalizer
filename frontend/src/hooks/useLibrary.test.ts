import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useLibraries, useLibraryItems, useLibraryFolders } from './useLibrary'
import * as api from '../api/library'
import type { LibraryItem, LibraryFolder } from '../types/library'
vi.mock('../api/library', () => ({ listLibraries: vi.fn(), listItems: vi.fn(), listFolders: vi.fn(), updateItem: vi.fn(), createFolder: vi.fn(), renameFolder: vi.fn(), deleteFolder: vi.fn(), removeItem: vi.fn(), moveItems: vi.fn() }))
const item = { id: 'one', name: 'Proposal', pinned: false } as LibraryItem
const folder = { uuid: 'folder-one', name: 'Proposals' } as LibraryFolder
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r }); return { promise, resolve } }
beforeEach(() => { vi.resetAllMocks(); vi.mocked(api.listItems).mockResolvedValue([item]); vi.mocked(api.listFolders).mockResolvedValue([folder]); vi.mocked(api.listLibraries).mockResolvedValue([]) })

describe('Library list recovery', () => {
  it('shows failures and keeps loaded items for retry', async () => {
    const { result } = renderHook(() => useLibraryItems('mine'))
    await waitFor(() => expect(result.current.items).toHaveLength(1))
    vi.mocked(api.listItems).mockRejectedValueOnce(new Error('Offline'))
    await act(async () => { await result.current.refresh() })
    expect(result.current.error).toBe('Offline')
    expect(result.current.items).toEqual([item])
    await act(async () => { await result.current.refresh() })
    expect(result.current.error).toBeNull()
  })
  it('ignores a slower old search and clears rows while a different query loads', async () => {
    const old = deferred<LibraryItem[]>()
    vi.mocked(api.listItems).mockReturnValueOnce(old.promise).mockResolvedValueOnce([{ ...item, id: 'new' }])
    const { result, rerender } = renderHook(({ search }) => useLibraryItems('mine', { search }), { initialProps: { search: 'old' } })
    rerender({ search: 'new' })
    await waitFor(() => expect(result.current.items[0]?.id).toBe('new'))
    await act(async () => { old.resolve([{ ...item, id: 'old' }]) })
    expect(result.current.items[0].id).toBe('new')
  })
  it('cannot apply a late mutation to another library or let an older read undo it', async () => {
    const update = deferred<LibraryItem>(), stale = deferred<LibraryItem[]>()
    const { result, rerender } = renderHook(({ id }) => useLibraryItems(id), { initialProps: { id: 'mine' } })
    await waitFor(() => expect(result.current.items).toHaveLength(1))
    vi.mocked(api.listItems).mockReturnValueOnce(stale.promise)
    act(() => { void result.current.refresh() })
    vi.mocked(api.updateItem).mockResolvedValueOnce({ ...item, pinned: true })
    await act(async () => { await result.current.update('one', { pinned: true }) })
    await act(async () => { stale.resolve([item]) })
    expect(result.current.items[0].pinned).toBe(true)
    vi.mocked(api.updateItem).mockReturnValueOnce(update.promise)
    act(() => { void result.current.update('one', { pinned: false }) })
    vi.mocked(api.listItems).mockResolvedValueOnce([{ ...item, id: 'team-item' }])
    rerender({ id: 'team' })
    await waitFor(() => expect(result.current.items[0]?.id).toBe('team-item'))
    await act(async () => { update.resolve(item) })
    expect(result.current.items[0].id).toBe('team-item')
  })
  it('shows initial folder failure without pretending there are no folders', async () => {
    vi.mocked(api.listFolders).mockRejectedValueOnce(new Error('Folders offline'))
    const { result } = renderHook(() => useLibraryFolders('personal'))
    await waitFor(() => expect(result.current.error).toBe('Folders offline'))
    expect(result.current.loading).toBe(false)
    await act(async () => { await result.current.refresh() })
    expect(result.current.folders).toEqual([folder])
  })
  it('ignores old team library and folder reads', async () => {
    const oldLibraries = deferred<Awaited<ReturnType<typeof api.listLibraries>>>(), oldFolders = deferred<LibraryFolder[]>()
    vi.mocked(api.listLibraries).mockReturnValueOnce(oldLibraries.promise)
    vi.mocked(api.listFolders).mockReturnValueOnce(oldFolders.promise).mockResolvedValueOnce([{ ...folder, uuid: 'new-folder' }])
    const { result, rerender } = renderHook(({ team }) => ({ libraries: useLibraries(team), folders: useLibraryFolders('team', team) }), { initialProps: { team: 'old' } })
    rerender({ team: 'new' })
    await waitFor(() => expect(result.current.folders.folders[0]?.uuid).toBe('new-folder'))
    await act(async () => { oldLibraries.resolve([]); oldFolders.resolve([folder]) })
    expect(result.current.folders.folders[0].uuid).toBe('new-folder')
    expect(result.current.libraries.loading).toBe(false)
  })
  it('does not add an old scope folder after switching scope', async () => {
    const created = deferred<LibraryFolder>()
    vi.mocked(api.createFolder).mockReturnValueOnce(created.promise)
    const { result, rerender } = renderHook(({ scope }) => useLibraryFolders(scope), { initialProps: { scope: 'personal' } })
    await waitFor(() => expect(result.current.folders).toHaveLength(1))
    act(() => { void result.current.create('New') })
    vi.mocked(api.listFolders).mockResolvedValueOnce([])
    rerender({ scope: 'team' })
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => { created.resolve({ ...folder, uuid: 'created' }) })
    expect(result.current.folders).toEqual([])
  })
})
