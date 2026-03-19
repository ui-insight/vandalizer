import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '../api/extractions'
import type { SearchSet, SearchSetItem } from '../types/workflow'

export function useSearchSets(space?: string) {
  const qc = useQueryClient()
  const queryKey = ['searchSets', space] as const

  const { data: searchSets = [], isLoading: loading } = useQuery<SearchSet[]>({
    queryKey,
    queryFn: () => api.listSearchSets(space),
  })

  const refresh = () => qc.invalidateQueries({ queryKey })

  const createMutation = useMutation({
    mutationFn: (args: { title: string }) =>
      api.createSearchSet({ title: args.title }),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const removeMutation = useMutation({
    mutationFn: (uuid: string) => api.deleteSearchSet(uuid),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const cloneMutation = useMutation({
    mutationFn: (uuid: string) => api.cloneSearchSet(uuid),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const create = async (title: string, _currentSpace: string) =>
    createMutation.mutateAsync({ title })

  const remove = async (uuid: string) => {
    await removeMutation.mutateAsync(uuid)
  }

  const clone = async (uuid: string) =>
    cloneMutation.mutateAsync(uuid)

  return { searchSets, loading, refresh, create, remove, clone }
}

export function useSearchSetItems(searchSetUuid: string | null) {
  const qc = useQueryClient()
  const queryKey = ['searchSetItems', searchSetUuid] as const

  const { data: items = [], isLoading: loading } = useQuery<SearchSetItem[]>({
    queryKey,
    queryFn: () => api.listItems(searchSetUuid!),
    enabled: !!searchSetUuid,
  })

  const refresh = () => qc.invalidateQueries({ queryKey })

  const addMutation = useMutation({
    mutationFn: (searchphrase: string) => api.addItem(searchSetUuid!, { searchphrase }),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const removeMutation = useMutation({
    mutationFn: (itemId: string) => api.deleteItem(itemId),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const updateMutation = useMutation({
    mutationFn: (args: { itemId: string; data: { searchphrase?: string; title?: string; is_optional?: boolean; enum_values?: string[] } }) =>
      api.updateItem(args.itemId, args.data),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const add = async (searchphrase: string) => {
    if (!searchSetUuid) return
    return addMutation.mutateAsync(searchphrase)
  }

  const remove = async (itemId: string) => {
    await removeMutation.mutateAsync(itemId)
  }

  const update = async (itemId: string, data: { searchphrase?: string; title?: string; is_optional?: boolean; enum_values?: string[] }) =>
    updateMutation.mutateAsync({ itemId, data })

  const reorder = async (itemIds: string[]) => {
    if (!searchSetUuid) return
    // Optimistically reorder in cache
    qc.setQueryData<SearchSetItem[]>(queryKey, (old) => {
      if (!old) return old
      const map = new Map(old.map(i => [i.id, i]))
      return itemIds.map(id => map.get(id)).filter(Boolean) as SearchSetItem[]
    })
    await api.reorderItems(searchSetUuid, itemIds)
  }

  return { items, loading, refresh, add, remove, update, reorder }
}
