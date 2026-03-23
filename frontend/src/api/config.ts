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
}

export function getThemeConfig() {
  return apiFetch<ThemeConfig>('/api/config/theme')
}

export function updateThemeConfig(data: { highlight_color?: string; ui_radius?: string }) {
  return apiFetch<ThemeConfig>('/api/config/theme', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

// Onboarding status

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
  is_certified: boolean
}

export function getOnboardingStatus() {
  return apiFetch<OnboardingStatus>('/api/config/onboarding-status')
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
