import { useCallback, useEffect, useState } from 'react'
import * as api from '../api/library'
import type { Library, LibraryItem, LibraryFolder } from '../types/library'

export function useLibraries(teamId?: string) {
  const [libraries, setLibraries] = useState<Library[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.listLibraries(teamId)
      setLibraries(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load libraries')
    } finally {
      setLoading(false)
    }
  }, [teamId])

  useEffect(() => { refresh() }, [refresh])

  return { libraries, loading, error, refresh }
}

export function useLibraryItems(libraryId: string | null, filters?: { kind?: string; folder?: string; search?: string }) {
  const [items, setItems] = useState<LibraryItem[]>([])
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    if (!libraryId) {
      setItems([])
      return
    }
    setLoading(true)
    try {
      const data = await api.listItems(libraryId, filters)
      setItems(data)
    } finally {
      setLoading(false)
    }
  }, [libraryId, filters?.kind, filters?.folder, filters?.search])

  useEffect(() => { refresh() }, [refresh])

  const add = async (data: { item_id: string; kind: string; note?: string; tags?: string[]; folder?: string }) => {
    if (!libraryId) return
    const item = await api.addItem(libraryId, data)
    setItems(prev => [...prev, item])
    return item
  }

  const remove = async (itemId: string) => {
    if (!libraryId) return
    await api.removeItem(libraryId, itemId)
    setItems(prev => prev.filter(i => i.id !== itemId))
  }

  const update = async (itemId: string, data: { note?: string; tags?: string[]; pinned?: boolean; favorited?: boolean }) => {
    const updated = await api.updateItem(itemId, data)
    setItems(prev => prev.map(i => i.id === itemId ? updated : i))
    return updated
  }

  return { items, loading, refresh, add, remove, update }
}

export function useLibraryFolders(scope: string, teamId?: string) {
  const [folders, setFolders] = useState<LibraryFolder[]>([])

  const create = async (name: string, parentId?: string) => {
    const folder = await api.createFolder({ name, parent_id: parentId, scope, team_id: teamId })
    setFolders(prev => [...prev, folder])
    return folder
  }

  const rename = async (uuid: string, name: string) => {
    const updated = await api.renameFolder(uuid, name)
    setFolders(prev => prev.map(f => f.uuid === uuid ? updated : f))
    return updated
  }

  const remove = async (uuid: string) => {
    await api.deleteFolder(uuid)
    setFolders(prev => prev.filter(f => f.uuid !== uuid))
  }

  const moveItemsToFolder = async (itemIds: string[], folderUuid: string | null) => {
    await api.moveItems(itemIds, folderUuid)
  }

  return { folders, create, rename, remove, moveItems: moveItemsToFolder }
}
