import { apiFetch, csrfHeaders } from './client'
import type { ChatMessage, UrlAttachment, FileAttachment, StreamChunk } from '../types/chat'

export async function streamChat(
  message: string,
  documentUuids: string[],
  activityId?: string | null,
  onChunk?: (chunk: StreamChunk) => void,
  model?: string,
  knowledgeBaseUuid?: string,
  includeOnboardingContext?: boolean,
  folderUuids?: string[],
  isFirstSession?: boolean,
): Promise<{ conversationUuid: string; activityId: string }> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    credentials: 'include',
    headers: csrfHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      message,
      document_uuids: documentUuids,
      activity_id: activityId || null,
      knowledge_base_uuid: knowledgeBaseUuid || null,
      ...(model ? { model } : {}),
      ...(includeOnboardingContext ? { include_onboarding_context: true } : {}),
      ...(folderUuids?.length ? { folder_uuids: folderUuids } : {}),
      ...(isFirstSession ? { is_first_session: true } : {}),
    }),
  })

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Chat request failed' }))
    throw new Error(body.detail || 'Chat request failed')
  }

  const conversationUuid = res.headers.get('X-Conversation-UUID') || ''
  const returnedActivityId = res.headers.get('X-Activity-ID') || ''

  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response stream')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (!line.trim()) continue
      try {
        const chunk: StreamChunk = JSON.parse(line)
        onChunk?.(chunk)
      } catch {
        // skip malformed lines
      }
    }
  }

  // Process remaining buffer
  if (buffer.trim()) {
    try {
      const chunk: StreamChunk = JSON.parse(buffer)
      onChunk?.(chunk)
    } catch {
      // skip
    }
  }

  return { conversationUuid, activityId: returnedActivityId }
}

export function addLink(
  link: string,
  currentActivityId?: string | null,
) {
  return apiFetch<{
    success: boolean
    conversation_uuid: string
    attachment_id: string
    title: string
    content_preview: string
    activity_id: string
    attachment: Record<string, unknown>
  }>('/api/chat/add-link', {
    method: 'POST',
    body: JSON.stringify({
      link,
      current_activity_id: currentActivityId || null,
    }),
  })
}

export async function addDocument(
  files: File[],
  currentActivityId?: string | null,
) {
  const formData = new FormData()
  files.forEach((f) => formData.append('files', f))
  if (currentActivityId) formData.append('current_activity_id', currentActivityId)

  const res = await fetch('/api/chat/add-document', {
    method: 'POST',
    credentials: 'include',
    headers: csrfHeaders(),
    body: formData,
  })

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Upload failed' }))
    throw new Error(body.detail || 'Upload failed')
  }

  return res.json()
}

export function removeDocument(attachmentId: string) {
  return apiFetch<{ success: boolean }>(`/api/chat/remove-document/${attachmentId}`, {
    method: 'DELETE',
  })
}

export function removeLink(attachmentId: string) {
  return apiFetch<{ success: boolean }>(`/api/chat/remove-link/${attachmentId}`, {
    method: 'DELETE',
  })
}

export interface ConversationSummary {
  uuid: string
  title: string
  message_count: number
  created_at: string | null
  updated_at: string | null
}

export function listConversations(limit: number = 50) {
  return apiFetch<ConversationSummary[]>(`/api/chat/conversations?limit=${limit}`)
}

export function getHistory(conversationUuid: string) {
  return apiFetch<{
    messages: ChatMessage[]
    url_attachments: UrlAttachment[]
    file_attachments: FileAttachment[]
    context_mode?: 'full' | 'truncated' | 'compacted'
    context_cutoff_index?: number
    compact_summary?: string | null
  }>(`/api/chat/history/${conversationUuid}`)
}

export function deleteHistory(conversationUuid: string) {
  return apiFetch<{ success: boolean }>(`/api/chat/history/${conversationUuid}`, {
    method: 'DELETE',
  })
}

export function truncateContext(conversationUuid: string, cutoffIndex?: number) {
  return apiFetch<{ success: boolean; context_mode: string; context_cutoff_index: number }>(
    '/api/chat/truncate',
    {
      method: 'POST',
      body: JSON.stringify({
        conversation_uuid: conversationUuid,
        ...(cutoffIndex != null ? { cutoff_index: cutoffIndex } : {}),
      }),
    },
  )
}

export function compactContext(conversationUuid: string) {
  return apiFetch<{ success: boolean; context_mode: string; context_cutoff_index: number; summary: string }>(
    '/api/chat/compact',
    {
      method: 'POST',
      body: JSON.stringify({ conversation_uuid: conversationUuid }),
    },
  )
}

export function clearContext(conversationUuid: string) {
  return apiFetch<{ success: boolean; context_mode: string; context_cutoff_index: number }>(
    '/api/chat/clear-context',
    {
      method: 'POST',
      body: JSON.stringify({ conversation_uuid: conversationUuid }),
    },
  )
}
