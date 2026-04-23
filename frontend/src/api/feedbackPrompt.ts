import { apiFetch } from './client'

export interface PendingPrompt {
  slug: string
  question_text: string
  subject: string
  stage: string
  ticket_uuid: string | null
}

export interface ShowPromptResult {
  ticket_uuid: string
  response_uuid: string
}

export interface PromptStats {
  shown: number
  responded: number
  dismissed: number
  response_rate: number
}

export interface PromptOverview {
  slug: string
  stage: string
  subject: string
  question_text: string
  enabled: boolean
  priority: number
  trigger_rules: Record<string, unknown>
  stats: PromptStats
}

export function getPendingPrompt() {
  return apiFetch<{ prompt: PendingPrompt | null }>('/api/feedback/prompts/pending')
}

export function showPrompt(slug: string) {
  return apiFetch<ShowPromptResult>(`/api/feedback/prompts/${slug}/show`, {
    method: 'POST',
  })
}

export function dismissPrompt(slug: string) {
  return apiFetch<{ ok: boolean }>(`/api/feedback/prompts/${slug}/dismiss`, {
    method: 'POST',
  })
}

export function getAdminPromptOverview() {
  return apiFetch<PromptOverview[]>('/api/feedback/prompts/admin/overview')
}

export function adminUpdatePrompt(slug: string, updates: Record<string, unknown>) {
  return apiFetch<PromptOverview>(`/api/feedback/prompts/admin/${slug}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  })
}
