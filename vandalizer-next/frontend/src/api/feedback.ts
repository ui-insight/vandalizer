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
