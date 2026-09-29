import { useCallback } from 'react'
import { useAuth } from './useAuth'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '../api/knowledge'
import type { KnowledgeBase, KBScope } from '../types/knowledge'

/** Legacy hook — returns the flat, unpaginated list. Used by existing components. */
export function useKnowledgeBases() {
  const qc = useQueryClient()
  const { user } = useAuth()
  const queryKey = ['knowledgeBases', user?.user_id, user?.current_team, 'legacy'] as const

  const { data: knowledgeBases = [], isLoading: loading, error } = useQuery<KnowledgeBase[]>({
    queryKey,
    queryFn: () => api.listKnowledgeBases(),
    enabled: !!user,
  })

  const refresh = useCallback(() => qc.invalidateQueries({ queryKey: ['knowledgeBases'] }), [qc])

  const createMutation = useMutation({
    mutationFn: (args: { title: string; description?: string }) =>
      api.createKnowledgeBase(args.title, args.description),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['knowledgeBases'] }),
  })

  const removeMutation = useMutation({
    mutationFn: (args: { uuid: string; mode?: 'unshare_and_delete' }) =>
      api.deleteKnowledgeBase(args.uuid, args.mode),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['knowledgeBases'] }),
  })

  const transferMutation = useMutation({
    mutationFn: (uuid: string) => api.transferKnowledgeBaseToTeam(uuid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['knowledgeBases'] }),
  })

  const create = async (title: string, description?: string) =>
    createMutation.mutateAsync({ title, description })

  const remove = async (uuid: string, mode?: 'unshare_and_delete') => {
    await removeMutation.mutateAsync({ uuid, mode })
  }

  const transferToTeam = async (uuid: string) => {
    await transferMutation.mutateAsync(uuid)
  }

  return { knowledgeBases, loading, error, refresh, create, remove, transferToTeam }
}

/** Scoped hook — uses the v2 list endpoint with scope, search, and pagination. */
export function useScopedKnowledgeBases(params?: {
  scope?: KBScope
  search?: string
  skip?: number
  limit?: number
}) {
  const qc = useQueryClient()
  const { user } = useAuth()
  const queryKey = ['knowledgeBases', user?.user_id, user?.current_team, 'v2', params?.scope, params?.search, params?.skip, params?.limit] as const

  const { data, isLoading: loading, error } = useQuery({
    queryKey,
    queryFn: async () => {
      if (params?.skip !== undefined || params?.limit !== undefined) return api.listKnowledgeBasesV2(params)
      // Local sorting and project filtering must include more than the first page.
      const first = await api.listKnowledgeBasesV2({ ...params, limit: 200 })
      const items = [...first.items]
      while (items.length < first.total) {
        const page = await api.listKnowledgeBasesV2({ ...params, skip: items.length, limit: 200 })
        if (!page.items.length) break
        items.push(...page.items)
      }
      return { ...first, items }
    },
    refetchInterval: query => query.state.data?.items.some(kb => kb.status === 'building') ? 5000 : false,
    enabled: !!user,
  })

  const refresh = useCallback(() => qc.invalidateQueries({ queryKey: ['knowledgeBases'] }), [qc])

  const createMutation = useMutation({
    mutationFn: (args: { title: string; description?: string }) =>
      api.createKnowledgeBase(args.title, args.description),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['knowledgeBases'] }),
  })

  const removeMutation = useMutation({
    mutationFn: (args: { uuid: string; mode?: 'unshare_and_delete' }) =>
      api.deleteKnowledgeBase(args.uuid, args.mode),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['knowledgeBases'] }),
  })

  const transferMutation = useMutation({
    mutationFn: (uuid: string) => api.transferKnowledgeBaseToTeam(uuid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['knowledgeBases'] }),
  })

  const adoptMutation = useMutation({
    mutationFn: (args: { uuid: string; note?: string }) =>
      api.adoptKnowledgeBase(args.uuid, args.note),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['knowledgeBases'] }),
  })

  const removeRefMutation = useMutation({
    mutationFn: (refUuid: string) => api.removeKBReference(refUuid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['knowledgeBases'] }),
  })

  const create = async (title: string, description?: string) =>
    createMutation.mutateAsync({ title, description })

  const remove = async (uuid: string, mode?: 'unshare_and_delete') => {
    await removeMutation.mutateAsync({ uuid, mode })
  }

  const transferToTeam = async (uuid: string) => {
    await transferMutation.mutateAsync(uuid)
  }

  const adopt = async (uuid: string, note?: string) =>
    adoptMutation.mutateAsync({ uuid, note })

  const removeRef = async (refUuid: string) => {
    await removeRefMutation.mutateAsync(refUuid)
  }

  return {
    knowledgeBases: data?.items ?? [],
    total: data?.total ?? 0,
    loading,
    error,
    refresh,
    create,
    remove,
    transferToTeam,
    adopt,
    removeRef,
  }
}
