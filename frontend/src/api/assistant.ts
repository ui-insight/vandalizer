import { apiFetch } from './client'

export interface AssistantCapability {
  id: string
  label: string
  description: string
  /** The person's own choice, kept while an admin limit hides it. */
  enabled: boolean
  /** False when an administrator switched it off for everyone. */
  allowed: boolean
  /** False when the deployment has not set it up (web search with no provider). */
  available: boolean
  /** What chat actually has right now. */
  active: boolean
}

export interface AssistantPage {
  capabilities: AssistantCapability[]
  always_on: { id: string; label: string; description: string }[]
  can_set_limits: boolean
}

export function getAssistantCapabilities() {
  return apiFetch<AssistantPage>('/api/assistant/capabilities')
}

/** A person's own switch for one capability. */
export function setAssistantCapability(id: string, on: boolean) {
  return apiFetch<AssistantPage>(`/api/assistant/capabilities/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify({ on }) })
}

/** Admin only: whether one capability is allowed for everyone on this deployment. */
export function setAssistantCapabilityLimit(id: string, on: boolean) {
  return apiFetch<AssistantPage>(`/api/assistant/capabilities/${encodeURIComponent(id)}/limit`, { method: 'PUT', body: JSON.stringify({ on }) })
}
