import { apiFetch } from './client'
import type { ChatMessage, UrlAttachment, FileAttachment, StreamChunk } from '../types/chat'

export async function streamChat(
  message: string,
  documentUuids: string[],
  activityId?: string | null,
  currentSpaceId?: string | null,
  onChunk?: (chunk: StreamChunk) => void,
  model?: string,
): Promise<{ conversationUuid: string; activityId: string }> {
  const res = await fetch('/api/chat', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      document_uuids: documentUuids,
      activity_id: activityId || null,
      current_space_id: currentSpaceId || null,
      ...(model ? { model } : {}),
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
  currentSpaceId?: string | null,
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
      current_space_id: currentSpaceId || null,
    }),
  })
}

export async function addDocument(
  files: File[],
  currentActivityId?: string | null,
  currentSpaceId?: string | null,
) {
  const formData = new FormData()
  files.forEach((f) => formData.append('files', f))
  if (currentActivityId) formData.append('current_activity_id', currentActivityId)
  if (currentSpaceId) formData.append('current_space_id', currentSpaceId)

  const res = await fetch('/api/chat/add-document', {
    method: 'POST',
    credentials: 'include',
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

export function getHistory(conversationUuid: string) {
  return apiFetch<{
    messages: ChatMessage[]
    url_attachments: UrlAttachment[]
    file_attachments: FileAttachment[]
  }>(`/api/chat/history/${conversationUuid}`)
}

export function deleteHistory(conversationUuid: string) {
  return apiFetch<{ success: boolean }>(`/api/chat/history/${conversationUuid}`, {
    method: 'DELETE',
  })
}
