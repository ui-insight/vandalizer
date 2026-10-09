import { apiFetch } from './client'
import type { CourseSelectionReceipt } from './certification'
import type { UpgradePreview } from '../types/certification'

export interface UpgradeChoiceRequest {
  request_id: string; source_enrollment_id: string; target_version: string; preview_sha256: string
  consent: 'preserve_original_work_and_require_all_new_outcomes'
}
export interface ActivationRequest {
  request_id: string; decision_id: string
  consent: 'activate_optional_upgrade_preserving_original_work_without_credit_transfer'
}
export interface UpgradeChoice {
  decision_id: string; source_enrollment_id: string; target_version: string; target_manifest_sha256: string
  preview_sha256: string; decision_sha256: string; accepted_at: string
  credit_transferred: false; requires_fresh_activation_check: true; activation_request: ActivationRequest
}
export interface ChoicePreview {
  comparison: UpgradePreview
  choice: { available: boolean; reason: string | null; recorded: boolean; request: UpgradeChoiceRequest; decision: UpgradeChoice | null }
}
export type SavedAction = 'return_to_original_course' | 'resume_upgraded_course'
export interface SavedChoiceRequest {
  request_id: string; activation_id: string; action: SavedAction; preview_sha256: string
  consent: 'select_saved_course_preserving_both_histories_and_credit'
}
export interface SavedCourseOption {
  activation_id: string; action: SavedAction; enrollment_id: string; course_version: string
  course_title: string; definition_available: boolean
}
export interface SavedCourseSummary {
  enrollment_id: string; course_version: string; course_title: string; manifest_sha256: string
  total_xp: number; completed_modules: number; credential_id: string | null; has_saved_place: boolean
  record_counts: Record<string, number>
}
export interface SavedChoicePreview {
  request: SavedChoiceRequest
  preview: { schema_version: 1; activation_id: string; action: SavedAction; read_only: true; can_activate: false
    credit_transferred: false; selection_revision: number; source: SavedCourseSummary; target: SavedCourseSummary
    preservation_policy: 'keep_both_existing_enrollments_and_original_workspace_references'
    state_sha256: string; preview_sha256: string }
}
export interface SelectionResult {
  receipt: CourseSelectionReceipt; current_enrollment_id: string | null; confirmation_pending: boolean
}
export interface SelectionRead extends Omit<SelectionResult, 'receipt'> {
  request: ActivationRequest | SavedChoiceRequest; source_enrollment_id: string; state: 'prepared' | 'applied'
  read_only: true; receipt: CourseSelectionReceipt | null
}
const root = '/api/certification'
const post = <T,>(path: string, body: unknown) => apiFetch<T>(root + path, { method: 'POST', body: JSON.stringify(body) })
export const getChoicePreview = (enrollment: string, target: string) => apiFetch<ChoicePreview>(`${root}/upgrade-choice-preview?enrollment_id=${encodeURIComponent(enrollment)}&target_version=${encodeURIComponent(target)}`)
export const saveUpgradeChoice = (body: UpgradeChoiceRequest) => post<UpgradeChoice>('/upgrade-choices', body)
export const getUpgradeChoice = (id: string) => apiFetch<UpgradeChoice>(`${root}/upgrade-choices/${encodeURIComponent(id)}`)
export const activateUpgrade = (body: ActivationRequest) => post<SelectionResult>('/upgrade-activations', body)
export const getActivation = (id: string) => apiFetch<SelectionRead>(`${root}/upgrade-activations/${encodeURIComponent(id)}`)
export const getSavedCourseOptions = (cursor?: string) => apiFetch<{ current_enrollment_id: string | null; courses: SavedCourseOption[]; read_only: true; next_cursor: string | null }>(`${root}/saved-course-options${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`)
export const getSavedChoicePreview = (item: SavedCourseOption) => apiFetch<SavedChoicePreview>(`${root}/saved-course-preview?activation_id=${encodeURIComponent(item.activation_id)}&action=${item.action}`)
export const selectSavedCourse = (body: SavedChoiceRequest) => post<SelectionResult>('/saved-course-selections', body)
export const getSavedSelection = (id: string) => apiFetch<SelectionRead>(`${root}/saved-course-selections/${encodeURIComponent(id)}`)

export const choiceId = (value: string) => /^[a-f0-9]{32}$/.test(value)
export const choiceDigest = (value: string) => /^[a-f0-9]{64}$/.test(value)
