import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '../api/knowledge'
import { listVerifiedItems } from '../api/library'
import type { KnowledgeBase, KBScope } from '../types/knowledge'

/** Legacy hook — returns the flat, unpaginated list. Used by existing components. */
export function useKnowledgeBases() {
  const qc = useQueryClient()
  const queryKey = ['knowledgeBases'] as const

  const { data: knowledgeBases = [], isLoading: loading } = useQuery<KnowledgeBase[]>({
    queryKey,
    queryFn: () => api.listKnowledgeBases(),
  })

  const refresh = () => qc.invalidateQueries({ queryKey })

  const createMutation = useMutation({
    mutationFn: (args: { title: string; description?: string }) =>
      api.createKnowledgeBase(args.title, args.description),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const removeMutation = useMutation({
    mutationFn: (args: { uuid: string; mode?: 'unshare_and_delete' }) =>
      api.deleteKnowledgeBase(args.uuid, args.mode),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const transferMutation = useMutation({
    mutationFn: (uuid: string) => api.transferKnowledgeBaseToTeam(uuid),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const create = async (title: string, description?: string) =>
    createMutation.mutateAsync({ title, description })

  const remove = async (uuid: string, mode?: 'unshare_and_delete') => {
    await removeMutation.mutateAsync({ uuid, mode })
  }

  const transferToTeam = async (uuid: string) => {
    await transferMutation.mutateAsync(uuid)
  }

  return { knowledgeBases, loading, refresh, create, remove, transferToTeam }
}

/** Scoped hook — uses the v2 list endpoint with scope, search, and pagination. */
export function useScopedKnowledgeBases(params?: {
  scope?: KBScope
  search?: string
  skip?: number
  limit?: number
}) {
  const qc = useQueryClient()
  const queryKey = ['knowledgeBases', 'v2', params?.scope, params?.search, params?.skip, params?.limit] as const

  const { data, isLoading: loading, isError: failed } = useQuery({
    queryKey,
    queryFn: () => api.listKnowledgeBasesV2(params),
  })

  const refresh = () => qc.invalidateQueries({ queryKey: ['knowledgeBases'] })

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
    // A failed list has no total; ``total`` then reads 0, which is not a count.
    failed,
    refresh,
    create,
    remove,
    transferToTeam,
    adopt,
    removeRef,
  }
}

export interface KBTabCounts {
  mine: number | null
  team: number | null
  explore: number | null
}

const canonicalUuid = (kb: KnowledgeBase) => (kb.is_reference ? (kb.source_kb_uuid || kb.uuid) : kb.uuid)

/**
 * How many knowledge bases each tab of the KB page holds, for the tab labels.
 * `null` while a count is still loading.
 *
 * My KBs and Team read the list endpoint's `total` through the same queries
 * the tab grids use, so the open tab costs no extra request. Everyone is the
 * catalog's total for knowledge bases, the population its tab browses.
 * `pinned` (canonical KB uuids) is set while the page is scoped to a project:
 * the My KBs and Team grids then show only the pinned KBs, and so do their
 * counts.
 */
export function useKBTabCounts(pinned?: Set<string>): KBTabCounts {
  const mine = useScopedKnowledgeBases({ scope: 'mine' })
  const team = useScopedKnowledgeBases({ scope: 'team' })
  const { data: catalog } = useQuery({
    // Under 'knowledgeBases' so the page's refresh recounts it too.
    queryKey: ['knowledgeBases', 'catalog-count'] as const,
    queryFn: () => listVerifiedItems({ kind: 'knowledge_base', limit: 1 }),
  })

  const count = (list: ReturnType<typeof useScopedKnowledgeBases>) => {
    if (list.loading || list.failed) return null
    return pinned ? list.knowledgeBases.filter(kb => pinned.has(canonicalUuid(kb))).length : list.total
  }

  return { mine: count(mine), team: count(team), explore: catalog?.total ?? null }
}
