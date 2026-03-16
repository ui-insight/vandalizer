import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '../api/knowledge'
import type { KnowledgeBase } from '../types/knowledge'

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
    mutationFn: (uuid: string) => api.deleteKnowledgeBase(uuid),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const create = async (title: string, description?: string) =>
    createMutation.mutateAsync({ title, description })

  const remove = async (uuid: string) => {
    await removeMutation.mutateAsync(uuid)
  }

  return { knowledgeBases, loading, refresh, create, remove }
}
