import { apiFetch } from './client'
import type { Obligation } from './obligations'

/** One fact read from the project's documents, with where it came from. */
export interface SnapshotFact {
  key: string
  label: string
  value: string
  document_uuid: string | null
  document_title: string | null
  page: number | null
  page_approximate: boolean
  quote: string | null
  /** supported = the value is in the quoted passage; anything else is unconfirmed. */
  support: 'supported' | 'unassessed' | 'quote_unsupported' | 'unverified'
}

export type SnapshotDeadline = Obligation & { days_until?: number }

/** Where a project's award stands. Facts are read from its documents; the rest is live. */
export interface AwardSnapshot {
  project: { uuid: string; title: string; state: string }
  status: 'not_built' | 'empty' | 'building' | 'ready' | 'error'
  facts: SnapshotFact[]
  budget_years: SnapshotFact[]
  documents_read: { uuid: string; title: string }[]
  document_count: number
  built_at: string | null
  error: string | null
  out_of_date: boolean
  page_uuid: string | null
  can_manage: boolean
  deadlines: { upcoming: SnapshotDeadline[]; overdue: SnapshotDeadline[]; done: SnapshotDeadline[]; needed: Obligation[] }
  last_run: { title: string | null; type: string; status: string; at: string | null } | null
  pages: { uuid: string; title: string; updated_at: string | null }[]
  generated_at: string
}

export function getAwardSnapshot(projectUuid: string) {
  return apiFetch<AwardSnapshot>(`/api/projects/${encodeURIComponent(projectUuid)}/award-snapshot`)
}

/** Read the facts from the project's documents (Build snapshot / Refresh). */
export function buildAwardSnapshot(projectUuid: string) {
  return apiFetch<AwardSnapshot>(`/api/projects/${encodeURIComponent(projectUuid)}/award-snapshot/build`, { method: 'POST' })
}

/** Save the snapshot as a private project Page (a new revision of the earlier one, if any). */
export function shareAwardSnapshot(projectUuid: string) {
  return apiFetch<{ uuid: string; title: string; revision: string }>(`/api/projects/${encodeURIComponent(projectUuid)}/award-snapshot/page`, { method: 'POST' })
}
