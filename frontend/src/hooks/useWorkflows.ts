import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '../api/workflows'
import type { Workflow } from '../types/workflow'

export function useWorkflows() {
  const qc = useQueryClient()
  const queryKey = ['workflows'] as const

  const { data: workflows = [], isLoading: loading } = useQuery<Workflow[]>({
    queryKey,
    queryFn: () => api.listWorkflows(),
  })

  const refresh = () => qc.invalidateQueries({ queryKey })

  const createMutation = useMutation({
    mutationFn: (args: { name: string }) =>
      api.createWorkflow({ name: args.name }),
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

  const importMutation = useMutation({
    mutationFn: (file: File) => api.importWorkflow(file),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const create = async (name: string) => {
    return createMutation.mutateAsync({ name })
  }

  const remove = async (id: string) => {
    await removeMutation.mutateAsync(id)
  }

  const duplicate = async (id: string) => {
    return duplicateMutation.mutateAsync(id)
  }

  const importFromFile = async (file: File) => {
    return importMutation.mutateAsync(file)
  }

  return { workflows, loading, refresh, create, remove, duplicate, importFromFile }
}
