import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from '../api/library'
import type { Library, LibraryItem, LibraryFolder } from '../types/library'

/** Keep errors and rows in their own scope; late reads/writes cannot switch it. */
function useScopedList<T>(key: string | null, fetchRows: () => Promise<T[]>) {
  const [snapshot, setSnapshot] = useState<{ key: string | null; rows: T[]; error: string | null; loading: boolean }>({ key: null, rows: [], error: null, loading: false })
  const version = useRef(0)
  const currentKey = useRef(key)
  currentKey.current = key
  const refresh = useCallback(async () => {
    if (key !== currentKey.current) return
    const request = ++version.current
    if (key === null) { setSnapshot({ key, rows: [], error: null, loading: false }); return }
    setSnapshot(previous => ({ key, rows: previous.key === key ? previous.rows : [], error: null, loading: true }))
    try {
      const rows = await fetchRows()
      if (request === version.current) setSnapshot({ key, rows, error: null, loading: false })
    } catch (reason) {
      if (request === version.current) setSnapshot(previous => ({ ...previous, key, error: reason instanceof Error ? reason.message : 'Could not load this list.', loading: false }))
    }
  }, [key, fetchRows])
  const invalidate = useCallback(() => { version.current++ }, [])
  useEffect(() => { void refresh(); return invalidate }, [refresh, invalidate])
  // A mutation can change only the scope its action originally belonged to.
  const changeRows = (change: (rows: T[]) => T[]) => {
    if (currentKey.current !== key) return
    version.current++
    setSnapshot(previous => previous.key === key ? { ...previous, rows: change(previous.rows), loading: false } : previous)
  }
  return {
    rows: snapshot.key === key ? snapshot.rows : [],
    error: snapshot.key === key ? snapshot.error : null,
    loading: key !== null && (snapshot.key !== key || snapshot.loading),
    refresh, changeRows,
  }
}

export function useLibraries(teamId?: string) {
  const fetchRows = useCallback(() => api.listLibraries(teamId), [teamId])
  const { rows: libraries, ...state } = useScopedList<Library>(teamId ?? 'personal', fetchRows)
  return { libraries, ...state }
}

export function useLibraryItems(libraryId: string | null, filters?: { kind?: string; folder?: string; search?: string }) {
  const kind = filters?.kind, folder = filters?.folder, search = filters?.search
  const key = libraryId ? JSON.stringify([libraryId, kind, folder, search]) : null
  const fetchRows = useCallback(() => libraryId ? api.listItems(libraryId, { kind, folder, search }) : Promise.resolve([]), [libraryId, kind, folder, search])
  const { rows: items, changeRows, ...state } = useScopedList<LibraryItem>(key, fetchRows)
  const add = async (data: { item_id: string; kind: string; note?: string; tags?: string[]; folder?: string }) => {
    if (!libraryId) return
    const item = await api.addItem(libraryId, data)
    await state.refresh()
    return item
  }
  const remove = async (itemId: string, opts?: { deleteUnderlying?: boolean }) => {
    if (!libraryId) return
    await api.removeItem(libraryId, itemId, opts)
    changeRows(rows => rows.filter(i => i.id !== itemId))
  }
  const update = async (itemId: string, data: { note?: string; tags?: string[]; pinned?: boolean; favorited?: boolean }) => {
    const updated = await api.updateItem(itemId, data)
    changeRows(rows => rows.map(i => i.id === itemId ? updated : i))
    return updated
  }
  return { items, ...state, add, remove, update }
}

export function useLibraryFolders(scope: string, teamId?: string) {
  const fetchRows = useCallback(() => api.listFolders(scope, teamId), [scope, teamId])
  const { rows: folders, changeRows, ...state } = useScopedList<LibraryFolder>(JSON.stringify([scope, teamId]), fetchRows)
  const create = async (name: string, parentId?: string) => {
    const folder = await api.createFolder({ name, parent_id: parentId, scope, team_id: teamId })
    changeRows(rows => [...rows, folder])
    return folder
  }
  const rename = async (uuid: string, name: string) => {
    const updated = await api.renameFolder(uuid, name)
    changeRows(rows => rows.map(f => f.uuid === uuid ? updated : f))
    return updated
  }
  const remove = async (uuid: string) => {
    await api.deleteFolder(uuid)
    changeRows(rows => rows.filter(f => f.uuid !== uuid))
  }
  return { folders, ...state, create, rename, remove, moveItems: api.moveItems }
}
