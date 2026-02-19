import { apiFetch } from './client'

// Types

export interface OfficeStatus {
  connected: boolean
  connected_at: string | null
}

export interface IntakeConfig {
  id: string
  uuid: string
  name: string
  intake_type: string
  enabled: boolean
  mailbox_address: string | null
  folder_path: string | null
  triage_enabled: boolean
  default_workflow: string | null
  created_at: string | null
  updated_at: string | null
}

export interface WorkItem {
  id: string
  uuid: string
  source: string
  status: string
  subject: string | null
  sender_email: string | null
  sender_name: string | null
  received_at: string | null
  triage_category: string | null
  triage_confidence: number | null
  triage_tags: string[]
  triage_summary: string | null
  sensitivity_flags: string[]
  feedback_action: string | null
  created_at: string | null
}

// API functions

export function getOfficeStatus() {
  return apiFetch<OfficeStatus>('/api/office/status')
}

export function listIntakes() {
  return apiFetch<{ intakes: IntakeConfig[] }>('/api/office/intakes')
}

export function createIntake(data: {
  name: string
  intake_type: string
  mailbox_address?: string
  folder_path?: string
  triage_enabled?: boolean
}) {
  return apiFetch<IntakeConfig>('/api/office/intakes', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateIntake(uuid: string, data: { name?: string; enabled?: boolean }) {
  return apiFetch<IntakeConfig>(`/api/office/intakes/${uuid}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteIntake(uuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/office/intakes/${uuid}`, { method: 'DELETE' })
}

export function listWorkItems(status?: string, limit = 50) {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  params.set('limit', String(limit))
  return apiFetch<{ items: WorkItem[] }>(`/api/office/workitems?${params}`)
}

export function approveWorkItem(uuid: string) {
  return apiFetch<WorkItem>(`/api/office/workitems/${uuid}/approve`, { method: 'POST' })
}
