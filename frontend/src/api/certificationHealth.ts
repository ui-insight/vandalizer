import { apiFetch } from './client'

export interface CertificationHealthRow {
  source: 'enrollments' | 'module_completions' | 'automatic_reviews' | 'lab_runs' | 'client_journey'
  course_version: string | null
  manifest_sha256: string | null
  state: string
  provenance: string | null
  count: number
}
export interface CertificationHealthReport {
  read_only: true
  scope: 'all_retained_records'
  started_at: string
  observed_at: string
  rows: CertificationHealthRow[]
  journey?: { window_days: number; window_started_at: string; window_ended_at: string; source: 'client_observation'; rows: CertificationHealthRow[] }
  unavailable_metrics: string[]
}
export const getCertificationHealth = () => apiFetch<CertificationHealthReport>('/api/admin/certifications/health')
