import { apiFetch } from './client'
import type { Automation } from '../types/automation'

export function listAutomations(space?: string) {
  const params = space ? `?space=${encodeURIComponent(space)}` : ''
  return apiFetch<Automation[]>(`/api/automations${params}`)
}

export function getAutomation(id: string) {
  return apiFetch<Automation>(`/api/automations/${id}`)
}

export function createAutomation(data: { name: string; space?: string; description?: string; trigger_type?: string; action_type?: string; action_id?: string; shared_with_team?: boolean }) {
  return apiFetch<Automation>('/api/automations', { method: 'POST', body: JSON.stringify(data) })
}

export function updateAutomation(id: string, data: {
  name?: string
  description?: string
  enabled?: boolean
  trigger_type?: string
  trigger_config?: Record<string, unknown>
  action_type?: string
  action_id?: string
  shared_with_team?: boolean
  output_config?: Record<string, unknown>
}) {
  return apiFetch<Automation>(`/api/automations/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
}

export function deleteAutomation(id: string) {
  return apiFetch<{ ok: boolean }>(`/api/automations/${id}`, { method: 'DELETE' })
}

export function getActiveAutomations() {
  return apiFetch<{ active_automation_ids: string[] }>('/api/automations/active')
}
