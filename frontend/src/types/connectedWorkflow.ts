import type { SavedWorkflowDesignCapture } from './certification'

export interface ConnectedCase {
  id: string; revision: number; module_id: 'multi_step'; case_sha256: string
  provenance: 'authored_connected_workflow_case_not_execution'
  source_filename: string; source_sha256: string; notice: string; task: string; intended_output: string
  instructions: string[]; exclusions: string[]
  flawed_example: { notice: string; routing: string; analysis: string; final_summary: string }
  questions: { id: 'scope_approval' | 'connection_repair' | 'source_review'; phase: 'before_execution' | 'after_execution'; prompt: string }[]
  controlled_failure_practice?: { provenance: 'authored_training_stop_configuration_not_execution'; failure_stage: 'reason'
    failure_boundary: 'before_reasoning_provider_after_preserved_extraction'; notice: string; question: string
    retry_policy: 'new_separately_approved_internal_run_only'; assessment_policy: 'deterministic_stage_and_recovery_choice_no_prose_credit' }
}
export interface ConnectedIdentity {
  enrollment_id: string; module_id: 'multi_step'; course_version: string; manifest_sha256: string
}
export interface ConnectedCapture extends ConnectedIdentity {
  uuid: string; case: ConnectedCase; input_snapshot_sha256: string; artifact_id: string; artifact_sha256: string
  artifact: SavedWorkflowDesignCapture['artifact']; captured_at: string
  documents: { document_id: string; assigned_filename: string; title: string; source_sha256: string; text_sha256: string; text: string }[]
  execution_authorized: false; credit_awarded: false
}
export interface ConnectedStage {
  step_id: string; task_id: string; step_name: string; task_type: 'Extraction' | 'Prompt' | 'Formatter'
  effective_input_sources: string[]; receives_previous_stage: boolean; model_names: string[]; output_key: string
}
export interface ConnectedScope extends ConnectedIdentity {
  uuid: string; run_id: string; plan_sha256: string; case_sha256: string; submitted_at: string
  submission: ConnectedScopeBody; decision_sha256?: string; credit_awarded: false
}
export interface ConnectedRun extends ConnectedIdentity {
  execution_purpose?: 'complete_internal_chain' | 'controlled_failure_rehearsal'
  approval_question?: ConnectedCase['questions'][number]
  run_id: string; state: 'prepared' | 'executing' | 'completed' | 'failed' | 'uncertain'; plan_sha256: string
  case_sha256: string; input_snapshot_id: string; input_snapshot: ConnectedCapture; model_names: string[]
  prepared_at: string; stage_plans: ConnectedStage[]; scope_decision_id: string | null; scope_decision_sha256: string | null
  scope_decision: ConnectedScope | null; authorization_sha256: string | null; result_sha256: string | null
  stage_events_sha256: string
  stage_events: { receipt_sha256: string; receipt: { kind: 'stage_started' | 'stage_completed'; stage_index: number
    output_key: string; status?: 'completed' | 'failed'; consumed_context?: Record<string, unknown>; result?: Record<string, unknown> } }[]
  result: { status: string; final_output?: string | Record<string, unknown>; reason?: string; completion_mode?: string
    execution_finished_at?: string | null; receipt_finalized_at?: string; credit_awarded: false } | null
  can_save_scope: boolean; can_execute: boolean; can_finalize: boolean; credit_awarded: false; module_completion_eligible: false
}
export interface ConnectedReview extends ConnectedIdentity {
  uuid: string; case: ConnectedCase; submission: ConnectedReviewBody; submitted_at: string
  original_run: ConnectedRun; corrected_run: ConnectedRun
  comparison: { configuration_changed: boolean; original_formatter_rereads_source: boolean; corrected_formatter_receives_reasoning: boolean }
  credit_awarded: false; module_completion_eligible: false
}
export interface ConnectedList extends ConnectedIdentity {
  recovery_submissions?: { submission_id: string; run_id: string; submitted_at: string; previous_submission_id: string | null; choices_supported: boolean }[]
  older_recovery_submissions_available?: boolean
  case: ConnectedCase; can_submit: boolean; read_only_reason: string | null
  workflows: { workflow_id: string; name: string; version: number }[]; older_workflows_available: boolean
  captures: { input_snapshot_id: string; captured_at: string; workflow_name: string }[]; older_captures_available: boolean
  runs: { run_id: string; state: ConnectedRun['state']; prepared_at: string; input_snapshot_id: string; workflow_name: string }[]; older_runs_available: boolean
  submissions: { submission_id: string; submitted_at: string; previous_submission_id: string | null; original_run_id: string; corrected_run_id: string }[]
  older_submissions_available: boolean
}
export type ConnectedCaptureBody = { request_id: string; workflow_id: string; case_sha256: string; consent: 'capture_connected_workflow_inputs' }
export type ConnectedPlanBody = { request_id: string; input_snapshot_id: string; input_snapshot_sha256: string; case_sha256: string; consent: 'prepare_connected_workflow_plan' | 'prepare_controlled_failure_rehearsal' }
export type ConnectedScopeBody = { request_id: string; run_id: string; plan_sha256: string; case_sha256: string; choice: 'approve' | 'hold'; reason: string; consent: 'save_connected_workflow_scope_decision' }
export type ConnectedExecuteBody = { run_id: string; plan_sha256: string; scope_decision_id: string; scope_decision_sha256: string; consent: 'execute_approved_connected_workflow' }
export type ConnectedFinalizeBody = { run_id: string; plan_sha256: string; authorization_sha256: string; stage_events_sha256: string; consent: 'finalize_saved_connected_results_without_reexecution' }
export type ConnectedReviewBody = { request_id: string; original_run_id: string; original_result_sha256: string; corrected_run_id: string; corrected_result_sha256: string
  case_sha256: string; answers: { connection_repair: string; source_review: string }; previous_submission_id: string | null; consent: 'save_connected_workflow_result_review' }
export type ConnectedRecoveryBody = { request_id: string; run_id: string; result_sha256: string; stage_events_sha256: string; case_sha256: string
  failed_stage: 'extract' | 'reason' | 'format' | 'unknown'; preserve: 'keep_original_run_and_completed_outputs' | 'replace_original_history' | 'partial_is_complete'
  next_action: 'prepare_separate_bounded_run' | 'resume_in_place' | 'restart_all_writes' | 'publish_partial'
  explanation: string; previous_submission_id: string | null; consent: 'save_my_actual_stopped_run_recovery_choices' }
export interface ConnectedRecoveryDecision extends ConnectedIdentity {
  uuid: string; case: ConnectedCase; submission: ConnectedRecoveryBody; question: string; submitted_at: string; stopped_run: ConnectedRun
  checks: { checks: { id: string; supported: boolean; feedback: string }[]; choices_supported: boolean; explanation_quality_assessed: false
    execution_authorized: false; credit_awarded: false; module_completion_eligible: false; successful_extraction_receipt_sha256: string
    failed_stage_start_sha256: string; controlled_rejection_receipt_sha256: string }
  credit_awarded: false; module_completion_eligible: false
}
export type ConnectedRequest = { action: 'capture'; body: ConnectedCaptureBody } | { action: 'prepare'; body: ConnectedPlanBody }
  | { action: 'scope'; body: ConnectedScopeBody } | { action: 'execute'; body: ConnectedExecuteBody }
  | { action: 'finalize'; body: ConnectedFinalizeBody } | { action: 'review'; body: ConnectedReviewBody } | { action: 'recovery'; body: ConnectedRecoveryBody }
export type ConnectedSaved = ConnectedCapture | ConnectedRun | ConnectedReview | ConnectedRecoveryDecision
