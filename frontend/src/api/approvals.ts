import { apiFetch } from './client'

export interface ApprovalRequest {
  uuid: string
  workflow_result_id: string
  workflow_id: string
  step_index: number
  step_name: string
  data_for_review: Record<string, unknown>
  review_instructions: string
  status: string
  assigned_to_user_ids: string[]
  reviewer_user_id: string | null
  reviewer_comments: string
  decision_at: string | null
  created_at: string | null
}

export function listApprovals(
  status?: string,
): Promise<{ approvals: ApprovalRequest[] }> {
  const qs = status ? `?status=${status}` : ''
  return apiFetch(`/api/approvals/${qs}`)
}

export function getApprovalCount(): Promise<{ count: number }> {
  return apiFetch('/api/approvals/count')
}

export function getApproval(uuid: string): Promise<ApprovalRequest> {
  return apiFetch(`/api/approvals/${uuid}`)
}

export function approveRequest(
  uuid: string,
  comments: string = '',
): Promise<{ detail: string }> {
  return apiFetch(`/api/approvals/${uuid}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ comments }),
  })
}

export function rejectRequest(
  uuid: string,
  comments: string = '',
): Promise<{ detail: string }> {
  return apiFetch(`/api/approvals/${uuid}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ comments }),
  })
}
