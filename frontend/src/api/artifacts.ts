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
  revisions: { uuid: string; title: string; created_at: string; warnings: string[]; version?: number }[]
  /** Owner only: whether public-link viewers may ask questions, and how the owner is named. */
  public_questions?: boolean
  sharing_contact?: { hide_owner_name?: boolean; contact_label?: string }
  open_questions?: number
  /** Viewers only: "Shared by Jane Doe, University of Idaho Office of Sponsored Programs". */
  shared_by?: string | null
  /** Answers the owner chose to show under this version. */
  notes?: PageNote[]
}
const path = (id: string) => `/api/pages/${encodeURIComponent(id)}`
export interface PublicArtifact {
  title: string; revision: string; version: number; updated_at: string
  shared_by?: string | null; questions_enabled?: boolean; notes?: PageNote[]
}
export interface PageNote { about: string | null; question: string; answer: string; answered_at: string }
export interface PageAnchor { id: string; label: string }
export interface PageQuestion {
  uuid: string; artifact_uuid: string; revision: string; version: number | null
  anchor_id: string | null; anchor_label: string | null; message: string
  status: 'open' | 'answered' | 'closed'; created_at: string
  answer: { text: string; answered_at: string; show_on_page: boolean } | null
  /** Owner view only. */
  asker?: { kind: 'user' | 'public'; name: string | null; email: string | null }
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
export const publishArtifact = (id: string, revision: string) => apiFetch<Artifact>(`${path(id)}/publication`, { method: 'PUT', body: JSON.stringify({ revision }) })
export const unpublishArtifact = (id: string) => apiFetch(`${path(id)}/publication`, { method: 'DELETE' })
export const publishArtifactVersion = (id: string, revision: string) => apiFetch<Artifact>(`${path(id)}/publication`, { method: 'PUT', body: JSON.stringify({ revision, separate_link: true }) })
export const unpublishArtifactVersion = (id: string, revision: string) => apiFetch(`${path(id)}/publication?revision=${encodeURIComponent(revision)}`, { method: 'DELETE' })
export const shareArtifactTeam = (id: string, teamId: string | null, revision?: string) => apiFetch(`${path(id)}/team`, { method: 'PUT', body: JSON.stringify({ team_id: teamId, revision }) })
export const deleteArtifact = (id: string) => apiFetch(path(id), { method: 'DELETE' })
export const renameArtifact = (id: string, title: string) => apiFetch<Artifact>(path(id), { method: 'PATCH', body: JSON.stringify({ title }) })
export const duplicateArtifact = (id: string, requestId: string) => apiFetch<Artifact>(`${path(id)}/duplicate`, { method: 'POST', body: JSON.stringify({ request_id: requestId }) })

// Questions and flags from viewers to the owner (services/page_feedback.py).
export const questionAnchors = (id: string, revision?: string) => apiFetch<{ anchors: PageAnchor[] }>(`${path(id)}/questions/anchors${revision ? `?revision=${encodeURIComponent(revision)}` : ''}`)
export const publicQuestionAnchors = (token: string) => apiFetch<{ anchors: PageAnchor[] }>(`${path('public')}/${encodeURIComponent(token)}/questions/anchors`)
export const askQuestion = (id: string, body: { message: string; anchor_id?: string | null; revision?: string }) => apiFetch<PageQuestion>(`${path(id)}/questions`, { method: 'POST', body: JSON.stringify(body) })
export const askPublicQuestion = (token: string, body: { message: string; anchor_id?: string | null; email: string; name?: string; website?: string }) => apiFetch<{ ok: boolean }>(`${path('public')}/${encodeURIComponent(token)}/questions`, { method: 'POST', body: JSON.stringify(body) })
export const myQuestions = (id: string) => apiFetch<PageQuestion[]>(`${path(id)}/questions/mine`)
export const listQuestions = (id: string) => apiFetch<PageQuestion[]>(`${path(id)}/questions`)
export const answerQuestion = (id: string, question: string, text: string, showOnPage: boolean) => apiFetch<PageQuestion>(`${path(id)}/questions/${encodeURIComponent(question)}/answer`, { method: 'POST', body: JSON.stringify({ text, show_on_page: showOnPage }) })
export const closeQuestion = (id: string, question: string) => apiFetch(`${path(id)}/questions/${encodeURIComponent(question)}/close`, { method: 'POST' })
export const updateQuestionSettings = (id: string, body: { public_questions?: boolean; hide_owner_name?: boolean; contact_label?: string }) => apiFetch<{ public_questions: boolean; sharing_contact: { hide_owner_name?: boolean; contact_label?: string }; shared_by: string | null }>(`${path(id)}/question-settings`, { method: 'PATCH', body: JSON.stringify(body) })
