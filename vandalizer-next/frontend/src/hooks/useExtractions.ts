import { useCallback, useEffect, useState } from 'react'
import * as api from '../api/extractions'
import type { SearchSet, SearchSetItem } from '../types/workflow'

export function useSearchSets(space?: string) {
  const [searchSets, setSearchSets] = useState<SearchSet[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listSearchSets(space)
      setSearchSets(data)
    } finally {
      setLoading(false)
    }
  }, [space])

  useEffect(() => { refresh() }, [refresh])

  const create = async (title: string, currentSpace: string) => {
    const ss = await api.createSearchSet({ title, space: currentSpace })
    setSearchSets(prev => [...prev, ss])
    return ss
  }

  const remove = async (uuid: string) => {
    await api.deleteSearchSet(uuid)
    setSearchSets(prev => prev.filter(s => s.uuid !== uuid))
  }

  const clone = async (uuid: string) => {
    const ss = await api.cloneSearchSet(uuid)
    setSearchSets(prev => [...prev, ss])
    return ss
  }

  return { searchSets, loading, refresh, create, remove, clone }
}

export function useSearchSetItems(searchSetUuid: string | null) {
  const [items, setItems] = useState<SearchSetItem[]>([])
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    if (!searchSetUuid) { setItems([]); return }
    setLoading(true)
    try {
      const data = await api.listItems(searchSetUuid)
      setItems(data)
    } finally {
      setLoading(false)
    }
  }, [searchSetUuid])

  useEffect(() => { refresh() }, [refresh])

  const add = async (searchphrase: string) => {
    if (!searchSetUuid) return
    const item = await api.addItem(searchSetUuid, { searchphrase })
    setItems(prev => [...prev, item])
    return item
  }

  const remove = async (itemId: string) => {
    await api.deleteItem(itemId)
    setItems(prev => prev.filter(i => i.id !== itemId))
  }

  return { items, loading, refresh, add, remove }
}
