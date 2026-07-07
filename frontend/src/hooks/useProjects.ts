import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import * as api from '../api/projects'
import type { Project, ProjectOverview, ProjectPin, ProjectState } from '../types/project'

type ProjectUpdate = { title?: string; description?: string; state?: ProjectState }

/** The pins (workflows/extractions/etc.) attached to a project. */
export function useProjectPins(uuid: string | null | undefined) {
  const { data: pins = [], isLoading: loading } = useQuery<ProjectPin[]>({
    queryKey: ['project', uuid, 'pins'],
    queryFn: () => api.listProjectPins(uuid as string),
    enabled: !!uuid,
  })
  return { pins, loading }
}

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

  const duplicateMutation = useMutation({
    mutationFn: (uuid: string) => api.duplicateProject(uuid),
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

  const duplicate = (uuid: string) => duplicateMutation.mutateAsync(uuid)

  const update = (uuid: string, data: ProjectUpdate) =>
    updateMutation.mutateAsync({ uuid, data })

  return { projects, loading, create, remove, duplicate, update }
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
