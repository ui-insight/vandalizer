import { apiFetch } from './client'

// Version / update check

export interface VersionStatus {
  current: string
  latest: string | null
  update_available: boolean
  released_at: string | null
  release_url: string | null
  check_disabled: boolean
}

export function getVersionStatus() {
  return apiFetch<VersionStatus>('/api/admin/system/version')
}

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
  is_staff: boolean
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

// Team Detail

export interface TeamDetailMember {
  user_id: string
  name: string | null
  email: string | null
  role: string
  tokens_total: number
  workflows_run: number
  conversations: number
  last_active: string | null
}

export interface TeamDetailResponse {
  team_id: string
  name: string
  uuid: string
  tokens_in: number
  tokens_out: number
  workflows_started: number
  workflows_completed: number
  workflows_failed: number
  conversations: number
  active_users: number
  document_count: number
  timeseries: TimeseriesDayItem[]
  previous_period: UsageStats
  members: TeamDetailMember[]
  recent_workflows: WorkflowEventItem[]
}

export function getTeamDetail(teamId: string, days: number = 30) {
  return apiFetch<TeamDetailResponse>(`/api/admin/teams/${teamId}/detail?days=${days}`)
}

// User Detail

export interface UserDetailResponse {
  user_id: string
  name: string | null
  email: string | null
  is_admin: boolean
  is_staff: boolean
  is_examiner: boolean
  tokens_in: number
  tokens_out: number
  workflows_started: number
  workflows_completed: number
  workflows_failed: number
  conversations: number
  document_count: number
  timeseries: TimeseriesDayItem[]
  previous_period: UsageStats
  recent_workflows: WorkflowEventItem[]
}

export function getUserDetail(userId: string, days: number = 30) {
  return apiFetch<UserDetailResponse>(`/api/admin/users/${encodeURIComponent(userId)}/detail?days=${days}`)
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

export interface M365Config {
  enabled: boolean
  client_id: string
  client_secret: string
  tenant_id: string
}

export interface SystemConfigData {
  extraction_config: Record<string, unknown>
  quality_config: Record<string, unknown>
  auth_methods: string[]
  oauth_providers: Record<string, unknown>[]
  available_models: { name: string; tag: string; external: boolean; thinking: boolean; endpoint?: string; api_protocol?: string; api_key?: string; speed?: string; tier?: string; privacy?: string; supports_structured?: boolean; multimodal?: boolean; supports_pdf?: boolean }[]
  default_model: string
  ocr_endpoint: string
  ocr_api_key: string
  llm_endpoint: string
  highlight_color: string
  ui_radius: string
  default_team_id: string
  m365_config: M365Config
}

export function getSystemConfig() {
  return apiFetch<SystemConfigData>('/api/admin/config')
}

export function updateSystemConfig(data: { extraction_config?: Record<string, unknown>; quality_config?: Record<string, unknown>; ocr_endpoint?: string; ocr_api_key?: string; llm_endpoint?: string; default_team_id?: string; support_contacts?: { user_id: string; email: string; name: string }[] }) {
  return apiFetch<{ status: string }>('/api/admin/config', { method: 'PUT', body: JSON.stringify(data) })
}

export function getM365Config() {
  return apiFetch<M365Config>('/api/admin/config/m365')
}

export function updateM365Config(data: Partial<M365Config>) {
  return apiFetch<M365Config>('/api/admin/config/m365', { method: 'PUT', body: JSON.stringify(data) })
}

// Admin Team Management

export interface AdminTeamItem {
  team_id: string
  uuid: string
  name: string
  owner_user_id: string
  member_count: number
  is_default: boolean
}

export interface IsolatedUserItem {
  user_id: string
  name: string | null
  email: string | null
}

export function adminListAllTeams() {
  return apiFetch<AdminTeamItem[]>('/api/admin/teams/all')
}

export function adminCreateTeam(name: string) {
  return apiFetch<AdminTeamItem>('/api/admin/teams/create', { method: 'POST', body: JSON.stringify({ name }) })
}

export function adminAddUserToTeam(teamUuid: string, userId: string, role: string = 'member') {
  return apiFetch<{ ok: boolean }>(`/api/admin/teams/${teamUuid}/members`, {
    method: 'POST',
    body: JSON.stringify({ user_id: userId, role }),
  })
}

export function adminRemoveUserFromTeam(teamUuid: string, userId: string) {
  return apiFetch<{ ok: boolean }>(`/api/admin/teams/${teamUuid}/members/${encodeURIComponent(userId)}`, { method: 'DELETE' })
}

export function getIsolatedUsers() {
  return apiFetch<IsolatedUserItem[]>('/api/admin/users/isolated')
}

export function updateUserRoles(userId: string, roles: { is_admin?: boolean; is_staff?: boolean; is_examiner?: boolean }) {
  return apiFetch<{ ok: boolean }>(`/api/admin/users/${encodeURIComponent(userId)}/roles`, {
    method: 'PUT',
    body: JSON.stringify(roles),
  })
}

// Models

export function addModel(data: { name: string; tag: string; external?: boolean; thinking?: boolean; endpoint?: string; api_protocol?: string; api_key?: string; speed?: string; tier?: string; privacy?: string; supports_structured?: boolean; multimodal?: boolean; supports_pdf?: boolean }) {
  return apiFetch<{ status: string; models: SystemConfigData['available_models'] }>('/api/admin/config/models', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateModel(index: number, data: { name: string; tag: string; external?: boolean; thinking?: boolean; endpoint?: string; api_protocol?: string; api_key?: string; speed?: string; tier?: string; privacy?: string; supports_structured?: boolean; multimodal?: boolean; supports_pdf?: boolean }) {
  return apiFetch<{ status: string; models: SystemConfigData['available_models'] }>(`/api/admin/config/models/${index}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function deleteModel(index: number) {
  return apiFetch<{ status: string; default_model?: string }>(`/api/admin/config/models/${index}`, { method: 'DELETE' })
}

export function setDefaultModel(name: string) {
  return apiFetch<{ status: string; default_model: string }>('/api/admin/config/models/default', {
    method: 'PUT',
    body: JSON.stringify({ name }),
  })
}

// Test connectivity

export function testOcr() {
  return apiFetch<{ status: string; status_code: number; message: string }>('/api/admin/config/test-ocr', { method: 'POST' })
}

export function testModel(index: number) {
  return apiFetch<{ status: string; model: string; message: string }>(`/api/admin/config/test-model/${index}`, { method: 'POST' })
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

// Quality Alerts

export interface QualityAlert {
  uuid: string
  alert_type: 'regression' | 'stale' | 'config_changed'
  item_kind: string
  item_id: string
  item_name: string
  severity: 'info' | 'warning' | 'critical'
  message: string
  previous_score: number | null
  current_score: number | null
  previous_tier: string | null
  current_tier: string | null
  acknowledged: boolean
  created_at: string | null
}

export function getQualityAlerts(limit = 50, acknowledged = false) {
  return apiFetch<{ alerts: QualityAlert[] }>(`/api/admin/quality/alerts?limit=${limit}&acknowledged=${acknowledged}`)
}

export function acknowledgeAlert(uuid: string) {
  return apiFetch<{ ok: boolean }>(`/api/admin/quality/alerts/${uuid}/acknowledge`, { method: 'POST' })
}

// Quality Items (per-item drill-down)

export interface QualityItem {
  item_kind: string
  item_id: string
  display_name: string
  quality_score: number | null
  quality_tier: string | null
  last_validated_at: string | null
  validation_run_count: number
  trend: 'up' | 'down' | 'flat'
  stale: boolean
}

export interface QualityItemDetail {
  item_kind: string
  item_id: string
  history: {
    uuid: string
    score: number
    accuracy: number | null
    consistency: number | null
    grade: string | null
    model: string | null
    created_at: string
  }[]
  model_comparison: {
    model: string
    avg_score: number
    run_count: number
  }[]
}

export function getQualityItems(sort = 'score', order = 'asc', limit = 100) {
  return apiFetch<{ items: QualityItem[] }>(`/api/admin/quality/items?sort=${sort}&order=${order}&limit=${limit}`)
}

export function getQualityItemDetail(itemKind: string, itemId: string) {
  return apiFetch<QualityItemDetail>(`/api/admin/quality/items/${itemKind}/${itemId}`)
}
