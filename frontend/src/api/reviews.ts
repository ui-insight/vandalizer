import { apiFetch } from './client'

export type ReviewStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'expired'
  | 'escalated'

export type ArtifactKind =
  | 'text'
  | 'markdown'
  | 'json'
  | 'extraction_table'
  | 'document_render'
  | 'unknown'

export type AssigneeRole = 'specific_users' | 'workflow_owner' | 'team_admins'

export type TimeoutAction = 'none' | 'approve' | 'reject' | 'escalate'

export interface ReviewSummary {
  uuid: string
  workflow_id: string
  workflow_name: string
  step_name: string
  status: ReviewStatus
  assigned_to_user_ids: string[]
  assignee_role: AssigneeRole
  requester_user_id: string | null
  team_id: string | null
  expires_at: string | null
  created_at: string | null
  decision_at: string | null
  escalated_at: string | null
}

export interface SourceDocRef {
  uuid: string
  title: string
}

export interface RequesterRef {
  user_id: string
  name: string | null
  email: string | null
}

export interface ReviewDetail extends ReviewSummary {
  step_index: number
  review_instructions: string
  artifact_kind: ArtifactKind
  data_for_review: Record<string, unknown> | { value: unknown }
  edited_artifact: Record<string, unknown> | null
  timeout_action: TimeoutAction
  escalation_user_ids: string[]
  reviewer_user_id: string | null
  reviewer_comments: string
  expired_at: string | null
  source_docs: SourceDocRef[]
  requester: RequesterRef | null
}

export function listMyReviews(status?: string): Promise<{ reviews: ReviewSummary[] }> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ''
  return apiFetch(`/api/reviews${qs}`)
}

export function listTeamReviews(teamId?: string, status?: string): Promise<{ reviews: ReviewSummary[] }> {
  const params = new URLSearchParams()
  if (teamId) params.set('team_id', teamId)
  if (status) params.set('status', status)
  const qs = params.toString() ? `?${params}` : ''
  return apiFetch(`/api/reviews/team${qs}`)
}

export function getMyReviewCount(): Promise<{ count: number }> {
  return apiFetch('/api/reviews/count')
}

export function getReview(uuid: string): Promise<ReviewDetail> {
  return apiFetch(`/api/reviews/${uuid}`)
}

export function approveReview(
  uuid: string,
  body: { comments?: string; edited_artifact?: Record<string, unknown> | null } = {},
): Promise<{ detail: string }> {
  return apiFetch(`/api/reviews/${uuid}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      comments: body.comments ?? '',
      edited_artifact: body.edited_artifact ?? null,
    }),
  })
}

export function rejectReview(
  uuid: string,
  comments: string = '',
): Promise<{ detail: string }> {
  return apiFetch(`/api/reviews/${uuid}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ comments }),
  })
}
