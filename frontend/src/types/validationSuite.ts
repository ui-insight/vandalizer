export type ValidationField = 'Principal Investigator' | 'Total Project Budget' | 'Named Co-PI'
export type ValidationSourceId = 'nsf' | 'nih'
export interface ValidationCase {
  id: string; revision: number; module_id: 'validation_qa'; case_sha256: string
  provenance: 'authored_validation_assignment_not_observed_failure_or_retest'
  notice: string; task: string; instructions: string[]; exclusions: string[]; flawed_proposal: string
  fields: { title: ValidationField; meaning: string; comparison: string }[]
  sources: { id: ValidationSourceId; filename: string; sha256: string; coverage: string }[]
  questions: { id: 'suite_design' | 'repair_review'; phase: string; prompt: string }[]
}
export interface ValidationIdentity { enrollment_id: string; module_id: 'validation_qa'; course_version: string; manifest_sha256: string }
export interface ValidationCapture extends ValidationIdentity {
  uuid: string; case: ValidationCase; input_snapshot_sha256: string; artifact_id: string; artifact_sha256: string; captured_at: string
  artifact: { uuid: string; title: string; fields: { id: string; title: ValidationField; searchphrase: string; is_optional: boolean; enum_values: string[] | null }[] }
  documents: { source_id: ValidationSourceId; document_id: string; assigned_filename: string; source_sha256: string; pages: string[]; text: string }[]
  execution_authorized: false; credit_awarded: false
}
export interface ValidationExpectation { source_id: ValidationSourceId; field: ValidationField; expected_kind: 'value' | 'explicit_absence'; expected_value: string | null
  source_references: { page: number; quote: string }[]; source_reason: string }
export interface ValidationSuiteRecord extends ValidationIdentity {
  uuid: string; case: ValidationCase; submission: ValidationSuiteBody; suite_sha256: string; suite_record_sha256: string; submitted_at: string
  input_snapshot: ValidationCapture; source_correctness_verified: false; execution_authorized: false; credit_awarded: false; module_completion_eligible: false
  test_cases: { source_id: ValidationSourceId; expectations: ValidationExpectation[] }[]
}
export interface ValidationChecks { complete: boolean; source_supported: boolean; observed_semantic_failure: boolean
  cases: { source_id: ValidationSourceId; fields: { field: ValidationField; actual_value: unknown; expected_source_supported: boolean; output_comparable: boolean; matches_source: boolean; matches_learner_expectation: boolean; status: string }[] }[] }
export interface ValidationScope extends ValidationIdentity { uuid: string; run_id: string; plan_sha256: string; case_sha256: string; submission: ValidationScopeBody; submitted_at: string }
export interface ValidationRun extends ValidationIdentity {
  run_id: string; run_sha256: string; state: 'prepared' | 'executing' | 'completed' | 'failed' | 'uncertain'; phase: 'original' | 'retest'
  plan_sha256: string; case_sha256: string; input_snapshot: ValidationCapture; input_snapshot_id: string; suite: ValidationSuiteRecord
  original_run: ValidationRun | null; model_names: string[]; changed_fields: string[]; prepared_at: string
  scope_decision_id: string | null; scope_decision_sha256: string | null; scope_decision: ValidationScope | null; authorization_sha256: string | null
  result_sha256: string | null; case_events_sha256: string
  case_events: { receipt_sha256: string; receipt: { kind: 'case_started' | 'case_completed'; case_index: number; result?: { status: string } } }[]
  result: { status: string; checks?: ValidationChecks; repair_checks?: { repair_requirements_supported: boolean }; reason?: string; completion_mode?: string } | null
  can_save_scope: boolean; can_execute: boolean; can_finalize: boolean; credit_awarded: false; module_completion_eligible: false
}
export interface ValidationReview extends ValidationIdentity { uuid: string; case: ValidationCase; submission: ValidationReviewBody; submitted_at: string
  run: ValidationRun; credit_awarded: false; module_completion_eligible: false }
export interface ValidationList extends ValidationIdentity {
  case: ValidationCase; can_submit: boolean; read_only_reason: string | null
  extractions: { artifact_id: string; title: string }[]; older_extractions_available: boolean
  assigned_sources: { document_id: string; title: string; text: string; processing: boolean }[]
  captures: { input_snapshot_id: string; extraction_name: string; captured_at: string }[]; older_captures_available: boolean
  suites: ValidationSummary[]; older_suites_available: boolean; submissions: ValidationSummary[]; older_submissions_available: boolean
  runs: { run_id: string; state: ValidationRun['state']; phase: 'original' | 'retest'; input_snapshot_id: string; prepared_at: string }[]; older_runs_available: boolean
}
export interface ValidationSummary { submission_id: string; submitted_at: string; run_id: string; previous_submission_id: string | null }
export type ValidationCaptureBody = { request_id: string; artifact_id: string; case_sha256: string; consent: 'capture_validation_extraction_and_complete_sources' }
export type ValidationSuiteBody = { request_id: string; input_snapshot_id: string; input_snapshot_sha256: string; case_sha256: string; expectations: ValidationExpectation[]; suite_design: string; consent: 'save_checked_representative_expectations_before_execution' }
export type ValidationPlanBody = { request_id: string; input_snapshot_id: string; input_snapshot_sha256: string; suite_id: string; suite_record_sha256: string; case_sha256: string
  original_run_id: string | null; original_run_sha256: string | null; consent: 'prepare_complete_validation_suite' }
export type ValidationScopeBody = { request_id: string; run_id: string; plan_sha256: string; case_sha256: string; choice: 'approve' | 'hold'; reason: string; consent: 'save_validation_suite_scope_decision' }
export type ValidationExecuteBody = { run_id: string; plan_sha256: string; scope_decision_id: string; scope_decision_sha256: string; consent: 'execute_approved_complete_validation_suite' }
export type ValidationFinalizeBody = { run_id: string; plan_sha256: string; authorization_sha256: string; case_events_sha256: string; consent: 'finalize_saved_validation_results_without_reexecution' }
export type ValidationReviewBody = { request_id: string; run_id: string; result_sha256: string; case_sha256: string; answers: { repair_review: string }; previous_submission_id: string | null; consent: 'save_validation_repair_interpretation' }
export type ValidationRequest = { action: 'capture'; body: ValidationCaptureBody } | { action: 'suite'; body: ValidationSuiteBody } | { action: 'prepare'; body: ValidationPlanBody }
  | { action: 'scope'; body: ValidationScopeBody } | { action: 'execute'; body: ValidationExecuteBody } | { action: 'finalize'; body: ValidationFinalizeBody } | { action: 'review'; body: ValidationReviewBody }
export type ValidationSaved = ValidationCapture | ValidationSuiteRecord | ValidationRun | ValidationReview
export type ValidationOrigin = 'capture' | 'suite' | 'run' | 'review'
