import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '../api/workflows'
import type { Workflow } from '../types/workflow'

export function useWorkflows(space?: string) {
  const qc = useQueryClient()
  const queryKey = ['workflows', space] as const

  const { data: workflows = [], isLoading: loading } = useQuery<Workflow[]>({
    queryKey,
    queryFn: () => api.listWorkflows(space),
  })

  const refresh = () => qc.invalidateQueries({ queryKey })

  const createMutation = useMutation({
    mutationFn: (args: { name: string; space?: string }) =>
      api.createWorkflow({ name: args.name, space: args.space }),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const removeMutation = useMutation({
    mutationFn: (id: string) => api.deleteWorkflow(id),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const duplicateMutation = useMutation({
    mutationFn: (id: string) => api.duplicateWorkflow(id),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const create = async (name: string, currentSpace?: string) => {
    return createMutation.mutateAsync({ name, space: currentSpace })
  }

  const remove = async (id: string) => {
    await removeMutation.mutateAsync(id)
  }

  const duplicate = async (id: string) => {
    return duplicateMutation.mutateAsync(id)
  }

  return { workflows, loading, refresh, create, remove, duplicate }
}
