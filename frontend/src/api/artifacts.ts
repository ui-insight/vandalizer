import { apiFetch } from './client'
import type { ExportMessage } from './chat'

export interface Artifact {
  uuid: string
  created_at?: string
  updated_at?: string
  source?: { kind: string; conversation_uuid?: string; workflow_id?: string; session_id?: string; project_uuid?: string }
  title: string
  latest_revision: string
  published_revision: string | null
  public_token?: string | null
  team_id: string | null
  team_revision?: string | null
  can_manage: boolean
  public_sharing_enabled?: boolean
  revisions: { uuid: string; title: string; created_at: string; warnings: string[]; version?: number }[]
}
const path = (id: string) => `/api/pages/${encodeURIComponent(id)}`
export interface PublicArtifact { title: string; revision: string; version: number; updated_at: string }
export interface ArtifactPageResult { items: Artifact[]; total: number; page: number; page_size: number }
export const browseArtifacts = (params: { search?: string; sort?: string; page?: number; project_uuid?: string }) => {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value !== undefined) query.set(key, String(value))
  return apiFetch<ArtifactPageResult>(`/api/pages/browse?${query}`)
}
export const listArtifacts = () => apiFetch<Artifact[]>('/api/pages')
export const getArtifact = (id: string) => apiFetch<Artifact>(path(id))
export const getPublicArtifact = (token: string) => apiFetch<PublicArtifact>(`${path('public')}/${encodeURIComponent(token)}`)
export const createArtifact = (title: string, html: string, requestId: string, projectUuid?: string) => apiFetch<Artifact>('/api/pages', { method: 'POST', body: JSON.stringify({ title, html, request_id: requestId, project_uuid: projectUuid }) })
export const saveChatArtifact = (messages: ExportMessage[], requestId: string, source?: { project_uuid?: string; conversation_uuid?: string }) => apiFetch<Artifact>('/api/pages/from-chat', { method: 'POST', body: JSON.stringify({ messages, request_id: requestId, ...source }) })
export const saveWorkflowArtifact = (sessionId: string) => apiFetch<Artifact>(`${path('from-workflow')}/${encodeURIComponent(sessionId)}`, { method: 'POST' })
export const artifactContentUrl = (id: string, revision: string) => `${path(id)}/revisions/${encodeURIComponent(revision)}/content`
export const publicArtifactContentUrl = (token: string, revision?: string) => `${path('public')}/${encodeURIComponent(token)}/content${revision ? `?revision=${encodeURIComponent(revision)}` : ''}`
export const artifactSource = (id: string, revision: string) => apiFetch<{ title: string; html: string }>(`${path(id)}/revisions/${encodeURIComponent(revision)}/source`)
export const reviseArtifact = (id: string, title: string, html: string, baseRevision: string) => apiFetch<Artifact>(`${path(id)}/revisions`, { method: 'POST', body: JSON.stringify({ title, html, base_revision: baseRevision }) })
export const publishArtifact = (id: string, revision: string) => apiFetch<Artifact>(`${path(id)}/publication`, { method: 'PUT', body: JSON.stringify({ revision }) })
export const unpublishArtifact = (id: string) => apiFetch(`${path(id)}/publication`, { method: 'DELETE' })
export const shareArtifactTeam = (id: string, teamId: string | null, revision?: string) => apiFetch(`${path(id)}/team`, { method: 'PUT', body: JSON.stringify({ team_id: teamId, revision }) })
export const deleteArtifact = (id: string) => apiFetch(path(id), { method: 'DELETE' })
