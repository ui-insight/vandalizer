import { apiFetch } from './client'
import type { Automation, RunNowResponse, AutomationRunStatus } from '../types/automation'

export function listAutomations() {
  return apiFetch<Automation[]>('/api/automations')
}

export function getAutomation(id: string) {
  return apiFetch<Automation>(`/api/automations/${id}`)
}

export function createAutomation(data: { name: string; description?: string; trigger_type?: string; trigger_config?: Record<string, unknown>; action_type?: string; action_id?: string; shared_with_team?: boolean }) {
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

export interface CompletedAutomation {
  id: string
  name: string
  status: 'completed' | 'failed'
  documents: { uuid: string; title: string }[]
}

export function getActiveAutomations() {
  return apiFetch<{
    active_automation_ids: string[]
    recently_completed: CompletedAutomation[]
  }>('/api/automations/active')
}

/** Run an automation once, now, through its real pipeline (outputs fire). */
export function runAutomationNow(id: string, documentUuids?: string[]) {
  return apiFetch<RunNowResponse>(`/api/automations/${id}/run-now`, {
    method: 'POST',
    body: JSON.stringify(documentUuids && documentUuids.length ? { document_uuids: documentUuids } : {}),
  })
}

export function getAutomationRun(id: string, triggerEventId: string) {
  return apiFetch<AutomationRunStatus>(`/api/automations/${id}/runs/${triggerEventId}`)
}
