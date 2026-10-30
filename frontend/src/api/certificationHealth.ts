import { apiFetch } from './client'

export interface CertificationHealthRow {
  source: 'enrollments' | 'module_completions' | 'automatic_reviews' | 'lab_runs' | 'client_journey'
  course_version: string | null
  manifest_sha256: string | null
  state: string
  provenance: string | null
  count: number
}
type CourseKey = { course_version: string | null; manifest_sha256: string | null; course_title: string | null }
export interface CertificationJourneySuccessCourse extends CourseKey {
  started: number
  active: number
  completed: number
  transferred: number
  inactive: number
  activity_unknown: number
  staff_grading_corrections: number
  grading_questions_opened: number
  resumes_restored: number
  resumes_unavailable: number
  /** Rates are null below min_rate_denominator. */
  completion_rate: number | null
  inactive_share: number | null
  resume_success_rate: number | null
}
export interface CertificationJourneySuccess {
  inactive_after_days: number
  min_rate_denominator: number
  journey_window_days: number
  courses: CertificationJourneySuccessCourse[]
  bridge: { legacy_learners: number; upgraded_learners: number; uptake_rate: number | null; targets: (CourseKey & { learners: number })[] }
}
export interface CertificationHealthReport {
  read_only: true
  scope: 'all_retained_records'
  started_at: string
  observed_at: string
  rows: CertificationHealthRow[]
  journey?: { window_days: number; window_started_at: string; window_ended_at: string; source: 'client_observation'; rows: CertificationHealthRow[] }
  journey_success?: CertificationJourneySuccess
  unavailable_metrics: string[]
}
export const getCertificationHealth = () => apiFetch<CertificationHealthReport>('/api/admin/certifications/health')
