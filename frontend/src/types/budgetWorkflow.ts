import type { SavedWorkflowDesignCapture } from './certification'
import type { ConnectedRun } from './connectedWorkflow'

export interface BudgetCase {
  id: string; revision: number; module_id: 'advanced_nodes'; case_sha256: string
  provenance: 'authored_budget_method_case_not_execution'
  source_filename: string; source_sha256: string; notice: string; task: string; intended_output: string
  instructions: string[]; exclusions: string[]; flawed_proposal: string
  questions: { id: 'method_choice' | 'calculation_review' | 'dependency_review'; phase: 'before_execution' | 'after_execution'; prompt: string }[]
}
export interface BudgetIdentity { enrollment_id: string; module_id: 'advanced_nodes'; course_version: string; manifest_sha256: string }
export type CalculationId = 'equipment_subtotal' | 'listed_direct_subtotal' | 'listed_summary_total'
export interface BudgetOperand { id: string; value: string | null; unit: 'USD'; source_page: number; source_quote: string; status: 'supported' | 'unresolved'; explanation: string }
export interface BudgetCalculationRecord {
  id: CalculationId; operation: 'sum'; method: 'recorded_deterministic_arithmetic' | 'explicit_learner_arithmetic'
  inputs: BudgetOperand[]; result: string | null; unit: 'USD'; interpretation: string
}
export type BudgetCalculationBody = { request_id: string; case_sha256: string; document_id: string; records: BudgetCalculationRecord[]
  previous_snapshot_id: string | null; consent: 'save_source_bound_budget_calculations' }
export interface BudgetCalculation extends BudgetIdentity {
  uuid: string; case: BudgetCase; calculation_snapshot_sha256: string; captured_at: string; request: BudgetCalculationBody
  document: { document_id: string; assigned_filename: string; title: string; source_sha256: string; text_sha256: string; text: string }
  checks: { all_arithmetic_supported: boolean; interpretation_review_required: true; notice: string
    checks: { id: CalculationId; state: 'supported' | 'revision_required' | 'unresolved'; recorded_value: string | null; computed_value: string | null; expression: string; interpretation: string; source_matches: boolean }[] }
  credit_awarded: false; module_completion_eligible: false
}
export interface BudgetCapture extends BudgetIdentity {
  uuid: string; case: BudgetCase; input_snapshot_sha256: string; artifact_id: string; artifact_sha256: string
  artifact: SavedWorkflowDesignCapture['artifact']; captured_at: string; method_choice: string; calculation: BudgetCalculation
  execution_authorized: false; credit_awarded: false
}
export interface BudgetStage { step_id: string; step_name: string; output_key: string; waits_for_previous_stage: boolean
  tasks: { task_id: string; task_type: 'Prompt' | 'Formatter'; model: string; effective_input_sources: string[] }[] }
export interface BudgetScope extends BudgetIdentity { uuid: string; run_id: string; plan_sha256: string; case_sha256: string; submitted_at: string
  submission: BudgetScopeBody; decision_sha256?: string; credit_awarded: false }
export interface BudgetRun extends BudgetIdentity {
  run_id: string; state: ConnectedRun['state']; plan_sha256: string; case_sha256: string; input_snapshot_id: string; input_snapshot: BudgetCapture
  model_names: string[]; prepared_at: string; stage_plans: BudgetStage[]; scope_decision_id: string | null; scope_decision_sha256: string | null
  scope_decision: BudgetScope | null; authorization_sha256: string | null; result_sha256: string | null; task_events_sha256: string
  task_events: { receipt_sha256: string; receipt: { kind: 'task_started' | 'task_completed' | 'task_failed'; sequence: number
    stage_index: number; task_index: number; task_id: string; consumed_context?: unknown; result?: Record<string, unknown>; failure_kind?: string } }[]
  result: ConnectedRun['result']; can_save_scope: boolean; can_execute: boolean; can_finalize: boolean
  credit_awarded: false; module_completion_eligible: false
}
export interface BudgetReview extends BudgetIdentity { uuid: string; case: BudgetCase; submission: BudgetReviewBody; submitted_at: string
  run: BudgetRun; credit_awarded: false; module_completion_eligible: false }
export interface BudgetList extends BudgetIdentity {
  case: BudgetCase; can_submit: boolean; read_only_reason: string | null
  calculation_fields: { id: CalculationId; unit: 'USD'; operation: 'sum'; inputs: { id: string; label: string; source_page: number }[] }[]
  assigned_sources: { document_id: string; title: string; text: string; processing: boolean }[]
  workflows: { workflow_id: string; name: string; version: number }[]; older_workflows_available: boolean
  calculations: { calculation_snapshot_id: string; calculation_snapshot_sha256: string; captured_at: string; all_arithmetic_supported: boolean; previous_snapshot_id: string | null }[]
  older_calculations_available: boolean
  captures: { input_snapshot_id: string; captured_at: string; workflow_name: string }[]; older_captures_available: boolean
  runs: { run_id: string; state: BudgetRun['state']; prepared_at: string; input_snapshot_id: string; workflow_name: string }[]; older_runs_available: boolean
  submissions: { submission_id: string; submitted_at: string; previous_submission_id: string | null; run_id: string }[]; older_submissions_available: boolean
}
export type BudgetCaptureBody = { request_id: string; workflow_id: string; calculation_snapshot_id: string; calculation_snapshot_sha256: string
  case_sha256: string; method_choice: string; consent: 'capture_budget_workflow_and_method' }
export type BudgetPlanBody = { request_id: string; input_snapshot_id: string; input_snapshot_sha256: string; case_sha256: string; consent: 'prepare_budget_workflow_plan' }
export type BudgetScopeBody = { request_id: string; run_id: string; plan_sha256: string; case_sha256: string; choice: 'approve' | 'hold'; reason: string; consent: 'save_budget_workflow_scope_decision' }
export type BudgetExecuteBody = { run_id: string; plan_sha256: string; scope_decision_id: string; scope_decision_sha256: string; consent: 'execute_approved_budget_workflow' }
export type BudgetFinalizeBody = { run_id: string; plan_sha256: string; authorization_sha256: string; task_events_sha256: string; consent: 'finalize_saved_budget_results_without_reexecution' }
export type BudgetReviewBody = { request_id: string; run_id: string; result_sha256: string; case_sha256: string
  answers: { calculation_review: string; dependency_review: string }; previous_submission_id: string | null; consent: 'save_budget_calculation_and_dependency_review' }
export type BudgetRequest = { action: 'calculation'; body: BudgetCalculationBody } | { action: 'capture'; body: BudgetCaptureBody }
  | { action: 'prepare'; body: BudgetPlanBody } | { action: 'scope'; body: BudgetScopeBody } | { action: 'execute'; body: BudgetExecuteBody }
  | { action: 'finalize'; body: BudgetFinalizeBody } | { action: 'review'; body: BudgetReviewBody }
export type BudgetSaved = BudgetCalculation | BudgetCapture | BudgetRun | BudgetReview
