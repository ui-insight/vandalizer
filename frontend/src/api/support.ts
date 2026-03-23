import { apiFetch } from './client'
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

export function addAttachment(
  ticketUuid: string,
  filename: string,
  fileData: string,
  fileType?: string,
) {
  return apiFetch<SupportTicket>(`/api/support/tickets/${ticketUuid}/attachments`, {
    method: 'POST',
    body: JSON.stringify({ filename, file_data: fileData, file_type: fileType }),
  })
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

export function getSupportContacts() {
  return apiFetch<{ contacts: SupportContact[] }>('/api/support/contacts')
}
