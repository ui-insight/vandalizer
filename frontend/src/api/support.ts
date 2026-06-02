import { apiFetch, ApiError, rawFetch } from './client'
import type { SupportTicket, SupportTicketSummary, SupportContact } from '../types/support'

export async function createTicket(
  subject: string,
  message: string,
  priority = 'normal',
  files: File[] = [],
) {
  const form = new FormData()
  form.append('subject', subject)
  form.append('message', message)
  form.append('priority', priority)
  for (const f of files) form.append('files', f)

  const res = await rawFetch('/api/support/tickets', {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Failed to create ticket' }))
    throw new ApiError(res.status, body.detail || 'Failed to create ticket')
  }
  return res.json() as Promise<SupportTicket>
}

export function listTickets(
  status?: string,
  limit = 50,
  offset = 0,
  scope?: 'mine',
  tag?: string,
  category?: string,
  search?: string,
  priority?: string,
) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  if (scope) params.set('scope', scope)
  if (tag) params.set('tag', tag)
  if (category) params.set('category', category)
  if (search) params.set('search', search)
  if (priority) params.set('priority', priority)
  return apiFetch<{ tickets: SupportTicketSummary[] }>(
    `/api/support/tickets?${params}`,
  )
}

export function getTicket(ticketUuid: string) {
  return apiFetch<SupportTicket>(`/api/support/tickets/${ticketUuid}`)
}

export function addMessage(
  ticketUuid: string,
  content: string,
  options: { isInternalNote?: boolean } = {},
) {
  return apiFetch<SupportTicket>(`/api/support/tickets/${ticketUuid}/messages`, {
    method: 'POST',
    body: JSON.stringify({
      content,
      is_internal_note: options.isInternalNote ?? false,
    }),
  })
}

export function editMessage(
  ticketUuid: string,
  messageUuid: string,
  content: string,
) {
  return apiFetch<SupportTicket>(
    `/api/support/tickets/${ticketUuid}/messages/${messageUuid}`,
    {
      method: 'PATCH',
      body: JSON.stringify({ content }),
    },
  )
}

export async function addAttachment(
  ticketUuid: string,
  files: File | File[],
) {
  const list = Array.isArray(files) ? files : [files]
  if (list.length === 0) throw new ApiError(400, 'No files provided')
  const form = new FormData()
  for (const f of list) form.append('files', f)

  const res = await rawFetch(`/api/support/tickets/${ticketUuid}/attachments`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Upload failed' }))
    throw new ApiError(res.status, body.detail || 'Upload failed')
  }
  return res.json() as Promise<SupportTicket>
}

export function deleteAttachment(ticketUuid: string, attachmentUuid: string) {
  return apiFetch<SupportTicket>(
    `/api/support/tickets/${ticketUuid}/attachments/${attachmentUuid}`,
    { method: 'DELETE' },
  )
}

export function updateTicket(
  ticketUuid: string,
  updates: { status?: string; priority?: string; assigned_to?: string; tags?: string[] },
) {
  return apiFetch<SupportTicket>(`/api/support/tickets/${ticketUuid}`, {
    method: 'PATCH',
    body: JSON.stringify(updates),
  })
}

export function markTicketRead(ticketUuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/support/tickets/${ticketUuid}/read`, {
    method: 'POST',
  })
}

export function getTicketStats() {
  return apiFetch<{ total: number; open: number; in_progress: number; closed: number }>('/api/support/stats')
}

export function getSupportContacts() {
  return apiFetch<{ contacts: SupportContact[] }>('/api/support/contacts')
}

export function listAllTags() {
  return apiFetch<{ tags: string[] }>('/api/support/tags')
}

export function addWatcher(ticketUuid: string, email: string) {
  return apiFetch<SupportTicket>(`/api/support/tickets/${ticketUuid}/watchers`, {
    method: 'POST',
    body: JSON.stringify({ email }),
  })
}

export function removeWatcher(ticketUuid: string, watcherUserId: string) {
  return apiFetch<SupportTicket>(
    `/api/support/tickets/${ticketUuid}/watchers/${encodeURIComponent(watcherUserId)}`,
    { method: 'DELETE' },
  )
}
