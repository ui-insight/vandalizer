import { apiFetch, ApiError, csrfHeaders } from './client'
import type { SupportTicket, SupportTicketSummary, SupportContact } from '../types/support'

export function createTicket(subject: string, message: string, priority = 'normal') {
  return apiFetch<SupportTicket>('/api/support/tickets', {
    method: 'POST',
    body: JSON.stringify({ subject, message, priority }),
  })
}

export function listTickets(status?: string, limit = 50, offset = 0) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return apiFetch<{ tickets: SupportTicketSummary[] }>(
    `/api/support/tickets?${params}`,
  )
}

export function getTicket(ticketUuid: string) {
  return apiFetch<SupportTicket>(`/api/support/tickets/${ticketUuid}`)
}

export function addMessage(ticketUuid: string, content: string) {
  return apiFetch<SupportTicket>(`/api/support/tickets/${ticketUuid}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
}

export async function addAttachment(
  ticketUuid: string,
  file: File,
) {
  const form = new FormData()
  form.append('file', file)

  const res = await fetch(`/api/support/tickets/${ticketUuid}/attachments`, {
    method: 'POST',
    credentials: 'include',
    headers: csrfHeaders(),
    body: form,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: 'Upload failed' }))
    throw new ApiError(res.status, body.detail || 'Upload failed')
  }
  return res.json() as Promise<SupportTicket>
}

export function updateTicket(
  ticketUuid: string,
  updates: { status?: string; priority?: string; assigned_to?: string },
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
