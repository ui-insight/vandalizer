import type { SavedWorkflowDesignCapture } from './certification'

export interface OutputCase {
  id: string; revision: number; module_id: 'output_delivery'; case_sha256: string
  provenance: 'authored_output_handoff_case_not_generation_or_delivery'
  source_filename: string; source_sha256: string; notice: string; task: string; instructions: string[]; exclusions: string[]; flawed_proposal: string
  questions: { id: 'artifact_review' | 'release_decision' | 'delivery_review'; phase: 'after_generation_before_release' | 'after_delivery_attempt'; prompt: string }[]
  artifacts: { id: string; file_type: 'pdf' | 'csv'; purpose: string; required_fields: string[] }[]
  destination: { id: 'private_training_inbox'; audience: 'enrolled_learner_only'; data_scope: 'approved_generated_files_only'; description: string; first_attempt: string; recovery: string }
}
export interface OutputIdentity { enrollment_id: string; module_id: 'output_delivery'; course_version: string; manifest_sha256: string }
export interface OutputCapture extends OutputIdentity {
  uuid: string; case: OutputCase; input_snapshot_sha256: string; artifact_id: string; artifact_sha256: string
  artifact: SavedWorkflowDesignCapture['artifact']; captured_at: string; execution_authorized: false; credit_awarded: false
  documents: { document_id: string; source_sha256: string; text: string }[]
}
export interface OutputFile { step_name: string; filename: string; file_type: string; sha256: string; size_bytes: number
  inspection: { parseable_and_fields_present: boolean; issues: string[]; text: string; pages?: number; headers?: string[]; rows?: string[][]; source_correctness_verified: false; visual_inspection_required: true } }
export interface OutputArtifacts { files: OutputFile[]; download: { filename: string; file_type: string; media_type: string; sha256: string; size_bytes: number }
  artifacts_sha256: string; all_required_files_parseable: boolean; learner_inspection_required: true; release_authorized: false; delivery_confirmed: false; credit_awarded: false }
export interface OutputStage { step_id: string; task_id: string; step_name: string; output_key: string; task_type: 'Prompt' | 'Formatter' | 'DocumentRenderer' | 'DataExport'
  requested_model: string | null; effective_input_sources: string[]; receives_previous_stage: boolean; is_deliverable: boolean }
export interface OutputScope extends OutputIdentity { uuid: string; run_id: string; plan_sha256: string; case_sha256: string; submitted_at: string; submission: OutputScopeBody; decision_sha256?: string }
export interface OutputRun extends OutputIdentity {
  run_id: string; state: 'prepared' | 'executing' | 'completed' | 'failed' | 'uncertain'; plan_sha256: string; case_sha256: string
  input_snapshot_id: string; input_snapshot: OutputCapture; model_names: string[]; stage_plans: OutputStage[]; prepared_at: string
  scope_decision_id: string | null; scope_decision_sha256: string | null; scope_decision: OutputScope | null; authorization_sha256: string | null
  result_sha256: string | null; stage_events_sha256: string
  stage_events: { receipt_sha256: string; receipt: { kind: 'stage_started' | 'stage_completed'; stage_index: number; output_key: string; consumed_context?: unknown; status?: string; result?: Record<string, unknown> } }[]
  result: { status: 'completed' | 'failed' | 'uncertain'; generated_artifacts?: OutputArtifacts; reason?: string; completion_mode?: string; credit_awarded: false } | null
  release_decision: { uuid: string; review_sha256: string; submission: OutputInspectionBody } | null
  handoff_request_id: string | null; retry_request_id: string | null; handoff_receipt_id: string | null; handoff_claimed: boolean
  can_save_scope: boolean; can_execute: boolean; can_finalize: boolean; can_inspect: boolean; credit_awarded: false; module_completion_eligible: false
}
export interface OutputInspection extends OutputIdentity { uuid: string; case: OutputCase; review_sha256: string; submission: OutputInspectionBody; run: OutputRun
  submitted_at: string; previous_release_decision_id: string | null; credit_awarded: false; module_completion_eligible: false }
export interface OutputHandoff extends OutputIdentity { uuid: string; run_id: string; handoff_sha256: string; submission: OutputHandoffBody; submitted_at: string
  status: 'failed' | 'delivered'; reason: string; destination_written: boolean; destination_copy: OutputArtifacts | null; previous_failed_receipt: OutputHandoff | null
  destination: { id: 'private_training_inbox'; audience: 'enrolled_learner_only'; data_scope: 'approved_generated_files_only'; owner_user_id: string }
  external_delivery: false; credit_awarded: false }
export interface OutputReview extends OutputIdentity { uuid: string; case: OutputCase; submission: OutputReviewBody; submitted_at: string
  file_review: OutputInspection; handoff: OutputHandoff; credit_awarded: false; module_completion_eligible: false }
export interface OutputList extends OutputIdentity {
  case: OutputCase; can_submit: boolean; read_only_reason: string | null
  workflows: { workflow_id: string; name: string; version: number }[]; older_workflows_available: boolean
  assigned_sources: { document_id: string; title: string; text: string; processing: boolean }[]
  captures: { input_snapshot_id: string; workflow_name: string; captured_at: string }[]; older_captures_available: boolean
  runs: { run_id: string; workflow_name: string; state: OutputRun['state']; input_snapshot_id: string; prepared_at: string }[]; older_runs_available: boolean
  inspections: OutputSummary[]; handoffs: OutputSummary[]; submissions: OutputSummary[]
  older_inspections_available: boolean; older_handoffs_available: boolean; older_submissions_available: boolean
}
export interface OutputSummary { submission_id: string; submitted_at: string; run_id: string; status: string | null; choice: string | null; previous_submission_id: string | null }
export type OutputCaptureBody = { request_id: string; workflow_id: string; case_sha256: string; consent: 'capture_output_workflow_inputs' }
export type OutputPlanBody = { request_id: string; input_snapshot_id: string; input_snapshot_sha256: string; case_sha256: string; consent: 'prepare_output_workflow_plan' }
export type OutputScopeBody = { request_id: string; run_id: string; plan_sha256: string; case_sha256: string; choice: 'approve' | 'hold'; reason: string; consent: 'save_output_workflow_scope_decision' }
export type OutputExecuteBody = { run_id: string; plan_sha256: string; scope_decision_id: string; scope_decision_sha256: string; consent: 'execute_approved_output_workflow' }
export type OutputFinalizeBody = { run_id: string; plan_sha256: string; authorization_sha256: string; stage_events_sha256: string; consent: 'finalize_saved_output_results_without_reexecution' }
export type OutputInspectionBody = { request_id: string; run_id: string; result_sha256: string; case_sha256: string; artifacts_sha256: string
  file_inspections: { sha256: string; opened: boolean; judgment: 'usable' | 'needs_repair' | 'unresolved'; observations: string }[]
  bundle_sha256: string; bundle_opened: boolean; answers: { artifact_review: string; release_decision: string }; choice: 'approve' | 'hold'
  destination_id: 'private_training_inbox'; audience: 'enrolled_learner_only'; data_scope: 'approved_generated_files_only'; consent: 'save_exact_output_inspection_and_release_choice' }
export type OutputHandoffBody = { request_id: string; run_id: string; result_sha256: string; review_id: string; review_sha256: string; artifacts_sha256: string
  destination_id: 'private_training_inbox'; action: 'attempt' | 'retry_failed_handoff'; previous_failed_id: string | null; previous_failed_sha256: string | null
  consent: 'attempt_approved_private_training_handoff' | 'retry_only_failed_private_training_handoff' }
export type OutputReviewBody = { request_id: string; file_review_id: string; file_review_sha256: string; handoff_id: string; handoff_sha256: string
  case_sha256: string; delivery_review: string; previous_submission_id: string | null; consent: 'save_output_delivery_interpretation' }
export type OutputRequest = { action: 'capture'; body: OutputCaptureBody } | { action: 'prepare'; body: OutputPlanBody }
  | { action: 'scope'; body: OutputScopeBody } | { action: 'execute'; body: OutputExecuteBody } | { action: 'finalize'; body: OutputFinalizeBody }
  | { action: 'inspection'; body: OutputInspectionBody } | { action: 'handoff'; body: OutputHandoffBody } | { action: 'review'; body: OutputReviewBody }
export type OutputSaved = OutputCapture | OutputRun | OutputInspection | OutputHandoff | OutputReview
export type OutputOrigin = 'run' | 'inspection' | 'review' | 'handoff'
