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

// Timeseries

export interface TimeseriesDayItem {
  date: string
  conversations: number
  search_runs: number
  workflows_started: number
  workflows_completed: number
  workflows_failed: number
  tokens_in: number
  tokens_out: number
  active_users: number
}

export interface TimeseriesResponse {
  days: TimeseriesDayItem[]
  previous_period: UsageStats
}

export function getUsageTimeseries(days: number = 30) {
  return apiFetch<TimeseriesResponse>(`/api/admin/usage/timeseries?days=${days}`)
}

// Users

export interface UserLeaderboardItem {
  user_id: string
  name: string | null
  email: string | null
  is_admin: boolean
  is_examiner: boolean
  tokens_total: number
  workflows_run: number
  conversations: number
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
  member_count: number
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
  user_name: string | null
  user_email: string | null
  team_id: string | null
  team_name: string | null
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  tokens_in: number
  tokens_out: number
  steps_completed: number
  steps_total: number
  error: string | null
}

export interface WorkflowSummaryStats {
  total: number
  completed: number
  failed: number
  running: number
  success_rate: number
  avg_duration_ms: number | null
  total_tokens: number
}

export interface PaginatedWorkflows {
  items: WorkflowEventItem[]
  total: number
  page: number
  pages: number
  summary: WorkflowSummaryStats | null
}

export function getWorkflowEvents(page: number = 1, status?: string, search?: string) {
  let url = `/api/admin/workflows?page=${page}&per_page=50`
  if (status) url += `&status=${encodeURIComponent(status)}`
  if (search) url += `&search=${encodeURIComponent(search)}`
  return apiFetch<PaginatedWorkflows>(url)
}

// Config

export interface SystemConfigData {
  extraction_config: Record<string, unknown>
  quality_config: Record<string, unknown>
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

export function updateSystemConfig(data: { extraction_config?: Record<string, unknown>; quality_config?: Record<string, unknown>; ocr_endpoint?: string; llm_endpoint?: string }) {
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

// Quality

export interface QualitySummary {
  avg_score: number
  total_runs: number
  items_validated: number
  total_verified: number
  items_below_threshold: number
}

export interface QualityTimelinePoint {
  date: string
  avg_score: number
  run_count: number
  items_validated: number
}

export interface RegressionResult {
  total_items: number
  succeeded: number
  failed: number
  results: {
    item_id: string
    kind: string
    name: string
    score: number | null
    grade: string | null
    prev_score: number | null
    delta: number | null
    status: string
  }[]
}

export function getQualitySummary() {
  return apiFetch<QualitySummary>('/api/admin/quality/summary')
}

export function getQualityTimeline(days = 90, itemKind?: string) {
  let url = `/api/admin/quality/timeline?days=${days}`
  if (itemKind) url += `&item_kind=${encodeURIComponent(itemKind)}`
  return apiFetch<{ timeline: QualityTimelinePoint[] }>(url)
}

export function runRegressionSuite(model?: string) {
  const params = model ? `?model=${encodeURIComponent(model)}` : ''
  return apiFetch<RegressionResult>(`/api/admin/quality/regression-suite${params}`, { method: 'POST' })
}
