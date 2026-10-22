import { apiFetch } from './client'

/** One place a claim comes from: a document, a page, the exact passage. */
export interface ObligationSource {
  document_uuid: string
  document_title: string
  page: number | null
  quote: string
  role: string
}

/** A deadline, required piece of material or sponsor limit from a project's documents (#999). */
export interface Obligation {
  uuid: string
  project_uuid: string
  project_title: string | null
  kind: 'deadline' | 'required_material' | 'limit'
  title: string
  deadline_type: string | null
  due_at: string | null
  due_text: string | null
  limit_value: number | null
  observed_value: number | null
  unit: string | null
  in_conflict: boolean
  sources: ObligationSource[]
  status: 'open' | 'done' | 'superseded'
  supersedes: string | null
  superseded_by: string | null
  /** Hidden from this user's Home; teammates still see it. */
  dismissed: boolean
}

export function getInbox(includeDismissed = false) {
  return apiFetch<{ items: Obligation[]; inbox_hidden: boolean }>(
    `/api/obligations${includeDismissed ? '?include_dismissed=true' : ''}`,
  )
}

export function setObligationDone(uuid: string, done: boolean) {
  return apiFetch<Obligation>(`/api/obligations/${uuid}/done`, { method: 'POST', body: JSON.stringify({ done }) })
}

export function setObligationDismissed(uuid: string, dismissed: boolean) {
  return apiFetch<Obligation>(`/api/obligations/${uuid}/dismiss`, { method: 'POST', body: JSON.stringify({ dismissed }) })
}

export function setInboxHidden(inboxHidden: boolean) {
  return apiFetch<{ inbox_hidden: boolean }>('/api/obligations/home-settings', {
    method: 'PUT',
    body: JSON.stringify({ inbox_hidden: inboxHidden }),
  })
}
