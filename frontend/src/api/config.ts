import { apiFetch } from './client'
import type { ModelInfo, UserConfig } from '../types/workflow'

export function getModels() {
  return apiFetch<ModelInfo[]>('/api/config/models')
}

export function getUserConfig() {
  return apiFetch<UserConfig>('/api/config/user')
}

export function updateUserConfig(data: { model?: string; temperature?: number; top_p?: number }) {
  return apiFetch<UserConfig>('/api/config/user', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

// Theme

export interface ThemeConfig {
  highlight_color: string
  highlight_text_color: string
  highlight_complement: string
  ui_radius: string
  org_name: string
  app_name: string
  logo_data_url: string
  icon_data_url: string
  icon_hide_in_nav?: boolean
}

export function getThemeConfig() {
  return apiFetch<ThemeConfig>('/api/config/theme')
}

// Version / deployment

export interface VersionInfo {
  version: string
  environment: string
  deployment_label: string
}

export function getVersionInfo() {
  return apiFetch<VersionInfo>('/api/config/version')
}

export function updateThemeConfig(data: {
  highlight_color?: string
  ui_radius?: string
  org_name?: string
  app_name?: string
  logo_data_url?: string
  icon_data_url?: string
  icon_hide_in_nav?: boolean
}) {
  return apiFetch<ThemeConfig>('/api/config/theme', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

// Onboarding status

export interface RecentActivityItem {
  id: string
  type: string
  title: string
  relative_time: string
  status: string
  item_kind?: string | null
  item_id?: string | null
  pending_review?: boolean
}

export interface ActiveAlertItem {
  message: string
  severity: string
  item_name: string
  uuid?: string | null
  item_kind?: 'search_set' | 'workflow' | 'knowledge_base' | null
  item_id?: string | null
  alert_type?: string | null
  previous_score?: number | null
  current_score?: number | null
  created_at?: string | null
  review_state?: 'new' | 'in_review' | 'acknowledged'
}

export type MaturityStage = 'newcomer' | 'explorer' | 'practitioner' | 'builder' | 'architect'

export interface OnboardingStatus {
  has_documents: boolean
  has_workflows: boolean
  has_run_workflow: boolean
  has_extraction_sets: boolean
  has_library_items: boolean
  has_pinned_item: boolean
  has_favorited_item: boolean
  has_team_members: boolean
  has_automations: boolean
  has_enabled_automation: boolean
  has_knowledge_base: boolean
  has_ready_knowledge_base: boolean
  has_chatted_with_docs: boolean
  has_conversations: boolean
  first_session_completed: boolean
  is_certified: boolean
  suggestion_pills: string[]
  has_only_onboarding_docs: boolean
  top_extraction_set_name: string | null
  top_workflow_name: string | null
  recent_documents?: { uuid: string; title: string }[]
  recent_activity: RecentActivityItem[]
  active_alerts: ActiveAlertItem[]
  maturity_stage: MaturityStage
  unprocessed_doc_count: number
  daily_guidance: string | null
  since_last_visit: string | null
}

export function getOnboardingStatus() {
  return apiFetch<OnboardingStatus>('/api/config/onboarding-status')
}

export function markFirstSessionComplete() {
  return apiFetch<void>('/api/config/first-session-complete', { method: 'POST' })
}

// Automation stats

export interface AutomationStats {
  total_workflows: number
  passive_workflows: number
  watched_folders: number
  runs_today: number
  runs_today_success: number
  runs_today_failed: number
  runs_this_week: number
  recent_runs: {
    id: string
    workflow_id: string | null
    status: string
    trigger_type: string
    is_passive: boolean
    started_at: string | null
    steps_completed: number
    steps_total: number
  }[]
}

export function getAutomationStats() {
  return apiFetch<AutomationStats>('/api/config/automation-stats')
}

// Feature flags

export interface FeatureFlags {
  m365_enabled: boolean
  compliance_enabled?: boolean
  // True only on the fleet collector instance — gates the admin Telemetry tab.
  telemetry_collector_enabled?: boolean
}

export function getFeatureFlags() {
  return apiFetch<FeatureFlags>('/api/config/features')
}


export interface HomeEvaluation {
  uuid: string
  created_at: string | null
  score: number | null
  model: string | null
  source: string | null
  num_test_cases: number
  num_runs: number
  checks_failed: number
  num_checks: number
  accuracy: number | null
  consistency: number | null
  model_settings?: Record<string, unknown> | null
  result_snapshot: Record<string, unknown>
  extraction_config: Record<string, unknown> | null
  score_breakdown: Record<string, unknown> | null
}

export function getHomeAlertEvidence(uuid: string) {
  return apiFetch<{ runs: HomeEvaluation[]; linked_run: boolean }>(`/api/config/home-alerts/${encodeURIComponent(uuid)}/evidence`)
}

export function reviewHomeAlert(uuid: string, state: NonNullable<ActiveAlertItem['review_state']>) {
  return apiFetch<ActiveAlertItem>(`/api/config/home-alerts/${encodeURIComponent(uuid)}`, {
    method: 'PATCH', body: JSON.stringify({ state }),
  })
}
