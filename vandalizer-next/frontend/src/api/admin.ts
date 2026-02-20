import { apiFetch } from './client'

// Usage

export interface UsageStats {
  conversations: number
  search_runs: number
  workflows_started: number
  workflows_completed: number
  workflows_failed: number
  tokens_in: number
  tokens_out: number
  active_users: number
  active_teams: number
}

export function getUsageStats(days: number = 30) {
  return apiFetch<UsageStats>(`/api/admin/usage?days=${days}`)
}

// Users

export interface UserLeaderboardItem {
  user_id: string
  name: string | null
  email: string | null
  tokens_total: number
  workflows_run: number
  last_active: string | null
}

export function getUserLeaderboard() {
  return apiFetch<UserLeaderboardItem[]>('/api/admin/users')
}

// Teams

export interface TeamLeaderboardItem {
  team_id: string
  name: string
  uuid: string
  tokens_total: number
  workflows_completed: number
  active_users: number
  avg_latency_ms: number | null
}

export function getTeamLeaderboard() {
  return apiFetch<TeamLeaderboardItem[]>('/api/admin/teams')
}

// Workflows

export interface WorkflowEventItem {
  id: string
  status: string
  title: string | null
  user_id: string
  team_id: string | null
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  tokens_in: number
  tokens_out: number
  steps_completed: number
  steps_total: number
}

export interface PaginatedWorkflows {
  items: WorkflowEventItem[]
  total: number
  page: number
  pages: number
}

export function getWorkflowEvents(page: number = 1, status?: string) {
  let url = `/api/admin/workflows?page=${page}&per_page=50`
  if (status) url += `&status=${encodeURIComponent(status)}`
  return apiFetch<PaginatedWorkflows>(url)
}

// Config

export interface SystemConfigData {
  extraction_config: Record<string, unknown>
  auth_methods: string[]
  oauth_providers: Record<string, unknown>[]
  available_models: { name: string; tag: string; external: boolean; thinking: boolean; endpoint?: string; api_protocol?: string; api_key?: string }[]
  ocr_endpoint: string
  llm_endpoint: string
  highlight_color: string
  ui_radius: string
}

export function getSystemConfig() {
  return apiFetch<SystemConfigData>('/api/admin/config')
}

export function updateSystemConfig(data: { extraction_config?: Record<string, unknown>; ocr_endpoint?: string; llm_endpoint?: string }) {
  return apiFetch<{ status: string }>('/api/admin/config', { method: 'PUT', body: JSON.stringify(data) })
}

// Models

export function addModel(data: { name: string; tag: string; external?: boolean; thinking?: boolean; endpoint?: string; api_protocol?: string; api_key?: string }) {
  return apiFetch<{ status: string; models: SystemConfigData['available_models'] }>('/api/admin/config/models', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateModel(index: number, data: { name: string; tag: string; external?: boolean; thinking?: boolean; endpoint?: string; api_protocol?: string; api_key?: string }) {
  return apiFetch<{ status: string; models: SystemConfigData['available_models'] }>(`/api/admin/config/models/${index}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function deleteModel(index: number) {
  return apiFetch<{ status: string }>(`/api/admin/config/models/${index}`, { method: 'DELETE' })
}

// Auth

export function addOAuthProvider(data: Record<string, string>) {
  return apiFetch<{ status: string }>('/api/admin/config/auth/providers', { method: 'POST', body: JSON.stringify(data) })
}

export function updateOAuthProvider(index: number, data: Record<string, string>) {
  return apiFetch<{ status: string }>(`/api/admin/config/auth/providers/${index}`, { method: 'PUT', body: JSON.stringify(data) })
}

export function deleteOAuthProvider(index: number) {
  return apiFetch<{ status: string }>(`/api/admin/config/auth/providers/${index}`, { method: 'DELETE' })
}

export function updateAuthMethods(methods: string[]) {
  return apiFetch<{ status: string }>('/api/admin/config/auth/methods', { method: 'PUT', body: JSON.stringify({ methods }) })
}
