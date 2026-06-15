import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '../api/projects'
import type { Project, ProjectOverview, ProjectState } from '../types/project'

type ProjectUpdate = { title?: string; description?: string; state?: ProjectState }

export function useProjects() {
  const qc = useQueryClient()
  const queryKey = ['projects'] as const

  const { data: projects = [], isLoading: loading } = useQuery<Project[]>({
    queryKey,
    queryFn: () => api.listProjects(),
  })

  const createMutation = useMutation({
    mutationFn: (args: { title: string; description?: string }) =>
      api.createProject(args),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const removeMutation = useMutation({
    mutationFn: (uuid: string) => api.deleteProject(uuid),
    onSuccess: () => qc.invalidateQueries({ queryKey }),
  })

  const updateMutation = useMutation({
    mutationFn: ({ uuid, data }: { uuid: string; data: ProjectUpdate }) =>
      api.updateProject(uuid, data),
    onSuccess: (_res, { uuid }) => {
      qc.invalidateQueries({ queryKey })
      qc.invalidateQueries({ queryKey: ['project', uuid] })
    },
  })

  const create = (title: string, description?: string) =>
    createMutation.mutateAsync({ title, description })

  const remove = (uuid: string) => removeMutation.mutateAsync(uuid)

  const update = (uuid: string, data: ProjectUpdate) =>
    updateMutation.mutateAsync({ uuid, data })

  return { projects, loading, create, remove, update }
}

export function useProject(uuid: string) {
  const qc = useQueryClient()
  const queryKey = ['project', uuid] as const

  const { data: project, isLoading: loading } = useQuery<ProjectOverview>({
    queryKey,
    queryFn: () => api.getProject(uuid),
    enabled: !!uuid,
  })

  const updateMutation = useMutation({
    mutationFn: (data: { title?: string; description?: string; state?: ProjectState }) =>
      api.updateProject(uuid, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey })
      qc.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  const update = (data: { title?: string; description?: string; state?: ProjectState }) =>
    updateMutation.mutateAsync(data)

  return { project, loading, update }
}
