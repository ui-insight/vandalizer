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
  publications?: { revision: string; token: string; published_at: string }[]
  team_id: string | null
  team_revision?: string | null
  can_manage: boolean
  public_sharing_enabled?: boolean
  /** Owner only: each public link's expiry, audience and view record. */
  public_links?: { main: PublicLinkInfo | null; versions: Record<string, PublicLinkInfo | null> }
  revisions: { uuid: string; title: string; created_at: string; warnings: string[]; version?: number }[]
}
const path = (id: string) => `/api/pages/${encodeURIComponent(id)}`
export interface PublicArtifact { title: string; revision: string; version: number; updated_at: string; expires_at?: string | null; audience?: LinkAudience }

export type LinkAudience = 'anyone' | 'signed_in'
/** Settings sent when publishing or changing a public link. */
export interface LinkSettings { expires_at: string | null; audience: LinkAudience; emails: string[] }
export interface PublicLinkInfo {
  expires_at: string | null
  expired: boolean
  audience: LinkAudience
  emails: string[]
  views: { count: number; last_at: string | null }
  viewers: { name: string; email: string; count: number; last_at: string | null }[]
}
export interface LivePublicLink {
  artifact_uuid: string; title: string; kind: 'main' | 'version'; version: number | null; url: string
  expires_at: string | null; expired: boolean; audience: LinkAudience; restricted_to: number
  views: { count: number; last_at: string | null }
}
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
export const saveChatArtifact = (messages: ExportMessage[], requestId: string, source?: { project_uuid?: string; conversation_uuid?: string }) => apiFetch<Artifact & { reused?: boolean }>('/api/pages/from-chat', { method: 'POST', body: JSON.stringify({ messages, request_id: requestId, ...source }) })
export const saveWorkflowArtifact = (sessionId: string) => apiFetch<Artifact>(`${path('from-workflow')}/${encodeURIComponent(sessionId)}`, { method: 'POST' })
export const artifactContentUrl = (id: string, revision: string) => `${path(id)}/revisions/${encodeURIComponent(revision)}/content`
export const publicArtifactContentUrl = (token: string, revision?: string) => `${path('public')}/${encodeURIComponent(token)}/content${revision ? `?revision=${encodeURIComponent(revision)}` : ''}`
export const artifactSource = (id: string, revision: string) => apiFetch<{ title: string; html: string }>(`${path(id)}/revisions/${encodeURIComponent(revision)}/source`)
export const reviseArtifact = (id: string, title: string, html: string, baseRevision: string) => apiFetch<Artifact>(`${path(id)}/revisions`, { method: 'POST', body: JSON.stringify({ title, html, base_revision: baseRevision }) })
export const publishArtifact = (id: string, revision: string, settings?: LinkSettings) => apiFetch<Artifact>(`${path(id)}/publication`, { method: 'PUT', body: JSON.stringify({ revision, ...settings }) })
export const unpublishArtifact = (id: string) => apiFetch(`${path(id)}/publication`, { method: 'DELETE' })
export const publishArtifactVersion = (id: string, revision: string, settings?: LinkSettings) => apiFetch<Artifact>(`${path(id)}/publication`, { method: 'PUT', body: JSON.stringify({ revision, separate_link: true, ...settings }) })
/** Change an existing link: the main link, or `revision`'s version link. */
export const updatePublicLink = (id: string, settings: LinkSettings, revision?: string) => apiFetch<Artifact>(`${path(id)}/publication/settings`, { method: 'PUT', body: JSON.stringify({ ...settings, revision }) })
export const listPublicLinks = () => apiFetch<{ links: LivePublicLink[] }>('/api/pages/public-links')
export const unpublishArtifactVersion = (id: string, revision: string) => apiFetch(`${path(id)}/publication?revision=${encodeURIComponent(revision)}`, { method: 'DELETE' })
export const shareArtifactTeam = (id: string, teamId: string | null, revision?: string) => apiFetch(`${path(id)}/team`, { method: 'PUT', body: JSON.stringify({ team_id: teamId, revision }) })
export const deleteArtifact = (id: string) => apiFetch(path(id), { method: 'DELETE' })
export const renameArtifact = (id: string, title: string) => apiFetch<Artifact>(path(id), { method: 'PATCH', body: JSON.stringify({ title }) })
export const duplicateArtifact = (id: string, requestId: string) => apiFetch<Artifact>(`${path(id)}/duplicate`, { method: 'POST', body: JSON.stringify({ request_id: requestId }) })

/** A block the owner changed in Edit text mode: found again by tag, original text and occurrence. */
export interface PageTextEdit { tag: string; index: number; original: string; text: string }
export const saveTextEdits = (id: string, baseRevision: string, edits: PageTextEdit[]) => apiFetch<Artifact & { version: number; notes: string[] }>(`${path(id)}/text-edits`, { method: 'POST', body: JSON.stringify({ base_revision: baseRevision, edits }) })
