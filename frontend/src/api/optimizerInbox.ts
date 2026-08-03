import { apiFetch } from './client'
import type { ApplyPreview } from './knowledge'

export type OptimizerSurface = 'kb' | 'extraction' | 'workflow'

/** Row categories the backend computes so the UI groups without re-deriving. */
export type OptimizerInboxCategory =
  | 'needs_review'
  | 'no_change'
  | 'applied'
  | 'failed'
  | 'in_flight'
  | 'cancelled'
  | 'dismissed'

/** Per-surface inbox entry returned by ``/api/optimizer/inbox``.
 *  Same shape across KB/extraction/workflow so the inbox UI is one table. */
export interface OptimizerInboxItem {
  surface: OptimizerSurface
  run_uuid: string
  item_id: string
  /** Display name of the tuned KB / extraction set / workflow. */
  item_name: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  category: OptimizerInboxCategory
  started_at: string | null
  completed_at: string | null
  score: number | null
  baseline_score: number | null
  /** Null for runs the user launched themselves. */
  trigger:
    | 'cross_field_failure'
    | 'chat_feedback_threshold'
    | 'quality_alert'
    | null
  trigger_detail: Record<string, unknown>
  tied_with_baseline: boolean
  apply_preview: ApplyPreview | null
  suggestion_count: number
  applied_at: string | null
  reverted_at: string | null
  /** True when this run's winning config is the item's live config. */
  is_live: boolean
  /** False for view-only access — Apply and Dismiss are hidden. */
  can_manage: boolean
  dismissed_at: string | null
  error_message: string | null
  error_code: string | null
  error_context: Record<string, unknown> | null
  stopped_reason: string | null
  phase: string | null
  progress_message: string | null
  judge_model: string | null
  overfitting_warning: boolean
  /** Deep link to the tuned item in the workspace. */
  link: string
}

export interface OptimizerInboxCounts {
  total: number
  needs_review: number
  failed: number
  in_flight: number
  applied: number
  no_change: number
  dismissed: number
  /** Alias of needs_review, kept for the original client contract. */
  pending_review: number
}

export interface OptimizerInboxResponse {
  items: OptimizerInboxItem[]
  counts: OptimizerInboxCounts
  lookback_days: number
}

/** Unified inbox of tuning suggestions (and tuning failures) across surfaces. */
export function getOptimizerInbox(opts?: { includeDismissed?: boolean; days?: number }) {
  const params = new URLSearchParams()
  if (opts?.includeDismissed) params.set('include_dismissed', 'true')
  if (opts?.days) params.set('days', String(opts.days))
  const qs = params.toString()
  return apiFetch<OptimizerInboxResponse>(`/api/optimizer/inbox${qs ? `?${qs}` : ''}`)
}

/** Badge counts only — cheap enough to fetch from always-mounted chrome. */
export function getOptimizerInboxCount() {
  return apiFetch<OptimizerInboxCounts>('/api/optimizer/inbox/count')
}

export function dismissOptimizerCandidate(surface: OptimizerSurface, runUuid: string) {
  return apiFetch<{ ok: boolean; dismissed_at: string | null }>(
    `/api/optimizer/inbox/${surface}/${runUuid}/dismiss`,
    { method: 'POST' },
  )
}

export function restoreOptimizerCandidate(surface: OptimizerSurface, runUuid: string) {
  return apiFetch<{ ok: boolean }>(
    `/api/optimizer/inbox/${surface}/${runUuid}/restore`,
    { method: 'POST' },
  )
}
