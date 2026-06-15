import { apiFetch } from './client'
import type {
  Project,
  ProjectOverview,
  ProjectState,
  ProjectMember,
  ProjectInviteLink,
  ProjectInviteInfo,
  ProjectPin,
} from '../types/project'

export function listProjects() {
  return apiFetch<Project[]>('/api/projects')
}

export function createProject(data: { title: string; description?: string }) {
  return apiFetch<Project>('/api/projects', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function getProject(uuid: string) {
  return apiFetch<ProjectOverview>(`/api/projects/${uuid}`)
}

export function getProjectDocuments(uuid: string) {
  return apiFetch<{ document_uuids: string[] }>(`/api/projects/${uuid}/documents`)
}

export function updateProject(
  uuid: string,
  data: { title?: string; description?: string; state?: ProjectState },
) {
  return apiFetch<Project>(`/api/projects/${uuid}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteProject(uuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/projects/${uuid}`, { method: 'DELETE' })
}

export function shareProjectWithTeam(uuid: string) {
  return apiFetch<Project>(`/api/projects/${uuid}/share-with-team`, { method: 'POST' })
}

// --- Pins ---

export function listProjectPins(uuid: string) {
  return apiFetch<ProjectPin[]>(`/api/projects/${uuid}/pins`)
}

export function addProjectPin(uuid: string, data: { pin_type: string; target_id: string }) {
  return apiFetch<{ ok: boolean }>(`/api/projects/${uuid}/pins`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function removeProjectPin(uuid: string, pinType: string, targetId: string) {
  const qs = new URLSearchParams({ pin_type: pinType, target_id: targetId }).toString()
  return apiFetch<{ ok: boolean }>(`/api/projects/${uuid}/pins?${qs}`, { method: 'DELETE' })
}

// --- Sharing ---

export function createProjectInviteLink(uuid: string, data?: { role?: string }) {
  return apiFetch<ProjectInviteLink>(`/api/projects/${uuid}/invite-link`, {
    method: 'POST',
    body: JSON.stringify(data ?? {}),
  })
}

export function listProjectInviteLinks(uuid: string) {
  return apiFetch<ProjectInviteLink[]>(`/api/projects/${uuid}/invite-links`)
}

export function revokeProjectInviteLink(token: string) {
  return apiFetch<{ ok: boolean }>(`/api/projects/invite-link/${token}`, { method: 'DELETE' })
}

export function getProjectInviteInfo(token: string) {
  return apiFetch<ProjectInviteInfo>(`/api/projects/join/info/${token}`)
}

export function acceptProjectInvite(token: string) {
  return apiFetch<Project>(`/api/projects/join/accept/${token}`, { method: 'POST' })
}

export function listProjectMembers(uuid: string) {
  return apiFetch<ProjectMember[]>(`/api/projects/${uuid}/members`)
}

export function removeProjectMember(uuid: string, memberUserId: string) {
  return apiFetch<{ ok: boolean }>(`/api/projects/${uuid}/members/${memberUserId}`, { method: 'DELETE' })
}
