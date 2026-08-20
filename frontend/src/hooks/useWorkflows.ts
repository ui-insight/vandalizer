import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '../api/workflows'
import type { Workflow } from '../types/workflow'

/** The list API's ceiling; also our default, since callers here list to pick. */
const MAX_PAGE = 500

export interface UseWorkflowsOptions {
  /** Server-side name filter, applied across every visible workflow. */
  search?: string
  skip?: number
  limit?: number
}

export function useWorkflows(options: UseWorkflowsOptions = {}) {
  const { search, skip = 0, limit = MAX_PAGE } = options
  const qc = useQueryClient()
  // Paging/search are part of the key so switching pages refetches rather than
  // serving the previous page's rows; mutations invalidate the whole prefix.
  const queryKey = ['workflows', { search: search ?? '', skip, limit }] as const
  const invalidate = () => qc.invalidateQueries({ queryKey: ['workflows'] })

  const { data, isLoading: loading } = useQuery<api.WorkflowPage>({
    queryKey,
    queryFn: () => api.listWorkflows({ search, skip, limit }),
  })
  const workflows: Workflow[] = data?.items ?? []
  const total = data?.total ?? 0
  // True when the server holds matches this page does not contain — the state
  // that used to be silent, so a missing workflow read as a deleted one.
  const hasMore = skip + workflows.length < total

  const refresh = () => invalidate()

  const createMutation = useMutation({
    mutationFn: (args: { name: string }) =>
      api.createWorkflow({ name: args.name }),
    onSuccess: () => invalidate(),
  })

  const removeMutation = useMutation({
    mutationFn: (id: string) => api.deleteWorkflow(id),
    onSuccess: () => invalidate(),
  })

  const duplicateMutation = useMutation({
    mutationFn: (id: string) => api.duplicateWorkflow(id),
    onSuccess: () => invalidate(),
  })

  const removeFromTeamMutation = useMutation({
    mutationFn: (id: string) => api.removeWorkflowFromTeam(id),
    onSuccess: () => invalidate(),
  })

  const importMutation = useMutation({
    mutationFn: (file: File) => api.importWorkflow(file),
    onSuccess: () => invalidate(),
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

  const removeFromTeam = async (id: string) => {
    return removeFromTeamMutation.mutateAsync(id)
  }

  const importFromFile = async (file: File) => {
    return importMutation.mutateAsync(file)
  }

  return { workflows, total, hasMore, loading, refresh, create, remove, duplicate, removeFromTeam, importFromFile }
}
