import { apiFetch } from './client'
import type { CompletionResult } from '../types/certification'

export interface CreditTransferRequest {
  request_id: string; source_enrollment_id: string; target_enrollment_id: string; module_id: string; preview_sha256: string
  consent: 'transfer_reviewed_module_credit_preserve_original_no_new_xp_reward'
}
export interface TransferModule {
  module_id: string; title: string; outcome_count: number; eligible: boolean; completed: boolean
  xp_carried: number; xp_earned: 0; reason: string; request?: CreditTransferRequest
}
export interface CreditTransferPreview {
  source_enrollment_id: string; source_course_title: string; target_enrollment_id: string; target_course_title: string
  source_manifest_sha256: string; target_manifest_sha256: string; preview_sha256: string
  read_only: true; credit_transferred: false; xp_earned: 0; explanation: string; modules: TransferModule[]
}
export interface CreditTransferReceipt {
  request: CreditTransferRequest; state: 'evaluating' | 'graded' | 'applied' | 'rejected' | 'failed'
  read_only: true; result: CompletionResult | null
}
export const previewCreditTransfer = (enrollment: string) => apiFetch<CreditTransferPreview>(`/api/certification/credit-transfer-preview?enrollment_id=${encodeURIComponent(enrollment)}`)
export const applyCreditTransfer = (request: CreditTransferRequest) => apiFetch<CompletionResult>('/api/certification/credit-transfers', { method: 'POST', body: JSON.stringify(request) })
export const getCreditTransfer = (id: string) => apiFetch<CreditTransferReceipt>(`/api/certification/credit-transfers/${encodeURIComponent(id)}`)
