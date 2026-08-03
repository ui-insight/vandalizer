import { apiFetch } from './client'

export async function submitRating(data: {
  pdf_title: string
  rating: number
  comment?: string
  result_json?: Record<string, unknown>
  search_set_uuid?: string
}): Promise<{ complete: boolean }> {
  return apiFetch('/api/feedback/submit_rating', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function submitChatFeedback(data: {
  conversation_uuid?: string
  message_index?: number
  rating: 'up' | 'down'
  comment?: string
}): Promise<{ complete: boolean }> {
  return apiFetch('/api/feedback/chat', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// Free-form positive / idea feedback that is NOT a support ticket — it never
// enters the triage queue. Backs the support-panel "something that's working"
// affordance.
export async function submitProductFeedback(data: {
  message: string
  sentiment?: 'positive' | 'idea'
  source?: string
  feature?: string
}): Promise<{ complete: boolean }> {
  return apiFetch('/api/feedback/product', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export type PositiveFeedbackItem = {
  source: 'chat' | 'extraction' | 'product'
  sentiment: string
  message: string | null
  feature: string | null
  user_id: string | null
  created_at: string | null
}

export type PositiveFeedbackStats = {
  by_source: { chat: number; extraction: number; product: number }
  thumbs_up_rate: number | null
  positive_last_7_days: number
}

export function listPositiveFeedback(
  source?: 'chat' | 'extraction' | 'product',
  limit = 50,
): Promise<{ items: PositiveFeedbackItem[]; count: number }> {
  const params = new URLSearchParams()
  params.set('limit', String(limit))
  if (source) params.set('source', source)
  return apiFetch(`/api/feedback/admin/positive?${params}`)
}

export function getPositiveFeedbackStats(): Promise<PositiveFeedbackStats> {
  return apiFetch('/api/feedback/admin/stats')
}
