export type BatchSourceId = 'proposal_1' | 'proposal_2' | 'proposal_3'
export type BatchPhase = 'pilot' | 'batch' | 'retry'
export interface BatchCase {
  id: string; revision: number; module_id: 'batch_processing'; case_sha256: string
  provenance: 'authored_batch_assignment_not_pilot_coverage_or_recovery_evidence'
  notice: string; task: string; instructions: string[]; exclusions: string[]; pilot_limitations: string
  fields: { title: string; meaning: string; comparison: string }[]
  sources: { id: BatchSourceId; filename: string; sha256: string; coverage: string }[]
  pilot_source_ids: BatchSourceId[]; controlled_failure_source_id: 'proposal_2'
  questions: { id: 'pilot_choice' | 'scale_choice' | 'recovery_choice' | 'batch_review'; phase: string; prompt: string }[]
}
export interface BatchIdentity { enrollment_id: string; module_id: 'batch_processing'; course_version: string; manifest_sha256: string }
export interface BatchCapture extends BatchIdentity {
  uuid: string; case: BatchCase; input_snapshot_sha256: string; artifact_id: string; artifact_sha256: string; captured_at: string
  artifact: { uuid: string; title: string; fields: { id: string; title: string; searchphrase: string; is_optional: boolean; enum_values: string[] | null }[] }
  documents: { source_id: BatchSourceId; document_id: string; assigned_filename: string; source_sha256: string; pages: string[]; text: string }[]
  execution_authorized: false; credit_awarded: false
}
export interface BatchItemCheck {
  source_id: BatchSourceId; document_id: string; item_id: string; run_id: string; batch_id: string; status: 'completed' | 'failed'; receipt_sha256: string
  complete_values: boolean; source_supported: boolean
  fields: { field: string; actual_value: unknown; output_present: boolean; output_comparable: boolean; matches_source: boolean; status: string }[]
}
export interface BatchChecks {
  items: BatchItemCheck[]; terminal_coverage_complete: boolean; all_items_completed: boolean; all_values_complete: boolean
  all_values_source_supported: boolean; source_ids: BatchSourceId[]; elapsed_ms: number; usage: null; cost: null
}
export interface BatchItemResult {
  source_id: BatchSourceId; document_id: string; item_id: string; batch_id: string; run_id: string; attempt_kind: BatchPhase
  status: 'completed' | 'failed'; reason: string | null; extraction_started: boolean; started_at: string; finished_at: string
  elapsed_ms: number; usage: null; cost: null; entities: unknown; external_effects: false
}
export interface BatchScope extends BatchIdentity { uuid: string; run_id: string; plan_sha256: string; case_sha256: string; submission: BatchScopeBody; submitted_at: string }
export interface BatchRun extends BatchIdentity {
  run_id: string; run_sha256: string; state: 'prepared' | 'executing' | 'completed' | 'failed' | 'uncertain'; phase: BatchPhase
  batch_id: string; source_ids: BatchSourceId[]; failed_source_id: BatchSourceId | null
  plan_sha256: string; case_sha256: string; input_snapshot: BatchCapture; input_snapshot_id: string; model_names: string[]; prepared_at: string
  parent_run: BatchRun | null; previous_retry: BatchRun | null
  scope_decision_id: string | null; scope_decision_sha256: string | null; scope_decision: BatchScope | null; authorization_sha256: string | null
  result_sha256: string | null; item_events_sha256: string
  item_events: { receipt_sha256: string; receipt: { kind: 'item_started' | 'item_completed'; item_index: number; result?: BatchItemResult } }[]
  result: { status: string; checks?: BatchChecks; item_results?: BatchItemResult[]; reason?: string; completion_mode?: string } | null
  can_save_scope: boolean; can_execute: boolean; can_finalize: boolean; credit_awarded: false; module_completion_eligible: false
}
export interface BatchReconciliation {
  batch_id: string; reconciled_items: BatchItemCheck[]; all_assigned_terminal: boolean; all_assigned_successful: boolean
  all_values_source_supported: boolean; targeted_recovery_supported: boolean
  original_successes_preserved: { document_id: string; receipt_sha256: string }[]; original_failed_document_ids: string[]; retry_document_ids: string[]
}
export interface BatchReview extends BatchIdentity { uuid: string; case: BatchCase; submission: BatchReviewBody; submitted_at: string
  run: BatchRun; retries: BatchRun[]; reconciliation: BatchReconciliation; credit_awarded: false; module_completion_eligible: false }
export interface BatchList extends BatchIdentity {
  case: BatchCase; can_submit: boolean; read_only_reason: string | null
  extractions: { artifact_id: string; title: string }[]; older_extractions_available: boolean
  assigned_sources: { document_id: string; title: string; text: string; processing: boolean }[]
  captures: { input_snapshot_id: string; extraction_name: string; captured_at: string }[]; older_captures_available: boolean
  submissions: { submission_id: string; submitted_at: string; run_id: string; previous_submission_id: string | null }[]; older_submissions_available: boolean
  runs: { run_id: string; state: BatchRun['state']; phase: BatchPhase; input_snapshot_id: string; prepared_at: string }[]; older_runs_available: boolean
}
export type BatchCaptureBody = { request_id: string; artifact_id: string; case_sha256: string; consent: 'capture_batch_extraction_and_complete_sources' }
export type BatchPlanBody = { request_id: string; input_snapshot_id: string; input_snapshot_sha256: string; case_sha256: string; phase: BatchPhase
  parent_run_id: string | null; parent_run_sha256: string | null; failed_source_id: BatchSourceId | null; previous_retry_id: string | null; previous_retry_sha256: string | null; consent: 'prepare_bounded_batch_action' }
export type BatchScopeBody = { request_id: string; run_id: string; plan_sha256: string; case_sha256: string; choice: 'approve' | 'hold'; reason: string; consent: 'save_bounded_batch_scope_decision' }
export type BatchExecuteBody = { run_id: string; plan_sha256: string; scope_decision_id: string; scope_decision_sha256: string; consent: 'execute_approved_bounded_batch_action' }
export type BatchFinalizeBody = { run_id: string; plan_sha256: string; authorization_sha256: string; item_events_sha256: string; consent: 'finalize_saved_batch_results_without_reexecution' }
export type BatchReviewBody = { request_id: string; run_id: string; result_sha256: string; case_sha256: string; retries: { run_id: string; result_sha256: string }[]
  answers: { batch_review: string }; previous_submission_id: string | null; consent: 'save_batch_recovery_interpretation' }
export type BatchRequest = { action: 'capture'; body: BatchCaptureBody } | { action: 'prepare'; body: BatchPlanBody } | { action: 'scope'; body: BatchScopeBody }
  | { action: 'execute'; body: BatchExecuteBody } | { action: 'finalize'; body: BatchFinalizeBody } | { action: 'review'; body: BatchReviewBody }
export type BatchSaved = BatchCapture | BatchRun | BatchReview
export type BatchOrigin = 'capture' | 'run' | 'review'
