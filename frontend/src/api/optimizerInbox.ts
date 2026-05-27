import { apiFetch } from './client'
import type { ApplyPreview } from './knowledge'

/** Per-surface inbox entry returned by ``/api/optimizer/inbox``.
 *  Same shape across KB/extraction/workflow so the inbox UI is one table. */
export interface OptimizerInboxItem {
  surface: 'kb' | 'extraction' | 'workflow'
  run_uuid: string
  item_id: string
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  completed_at: string | null
  score: number | null
  baseline_score: number | null
  trigger:
    | 'cross_field_failure'
    | 'chat_feedback_threshold'
    | 'quality_alert'
    | null
  trigger_detail: Record<string, unknown>
  tied_with_baseline: boolean
  apply_preview: ApplyPreview | null
  applied_at: string | null
  reverted_at: string | null
  link: string
}

export interface OptimizerInboxResponse {
  items: OptimizerInboxItem[]
  counts: {
    total: number
    pending_review: number
    in_flight: number
    applied: number
  }
  lookback_days: number
}

/** Phase 6: unified inbox of shadow optimizer candidates across all surfaces. */
export function getOptimizerInbox() {
  return apiFetch<OptimizerInboxResponse>('/api/optimizer/inbox')
}
