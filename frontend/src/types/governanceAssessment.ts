export type GovernanceSourceId = 'award' | 'amendment'
export interface GovernanceCase {
  id: string; revision: number; module_id: 'governance'; case_sha256: string
  provenance: 'authored_supervision_case_not_learner_approval_or_delivery'; task_as_of: string
  task: string; notice: string; instructions: string[]; exclusions: string[]; flawed_proposal: string; original_field_flaw: string
  fields: { title: string; meaning: string; comparison: string }[]
  sources: { id: GovernanceSourceId; filename: string; sha256: string; coverage: string }[]
  questions: { id: 'scope_correction' | 'source_review' | 'release_review' | 'final_supervision'; phase: string; prompt: string }[]
}
export interface GovernanceIdentity { enrollment_id: string; module_id: 'governance'; course_version: string; manifest_sha256: string }
export interface GovernanceCapture extends GovernanceIdentity {
  uuid: string; case: GovernanceCase; input_snapshot_sha256: string; artifact_id: string; artifact_sha256: string; captured_at: string
  artifact: { uuid: string; title: string; fields: { id: string; title: string; searchphrase: string; is_optional: boolean; enum_values: string[] | null }[] }
  documents: { source_id: GovernanceSourceId; document_id: string; assigned_filename: string; source_sha256: string; pages: string[]; text: string }[]
  execution_authorized: false; credit_awarded: false
}
type Draft = { request_id: string; case_sha256: string }
type RunDraft = Draft & { run_id: string }
type CaptureReference = { input_snapshot_id: string; input_snapshot_sha256: string }
type MemoReference = { memo_id: string; memo_sha256: string; file_sha256: string }
export interface GovernanceBodies {
  capture: Draft & { artifact_id: string; consent: 'capture_governance_extraction_and_complete_sources' }
  correction: Draft & CaptureReference & { choice: 'reject_broad_proposal'; source_document_ids: string[]; destination_id: 'private_training_inbox'; audience: 'enrolled_learner_only'; ongoing_automation: 'keep_disabled'; reason: string; consent: 'save_my_corrected_capstone_scope_without_execution' }
  prepare: Draft & CaptureReference & { scope_correction_id: string; scope_correction_sha256: string; source_finding_id: string | null; source_finding_sha256: string | null; consent: 'prepare_original_bounded_capstone_extraction' | 'prepare_repaired_bounded_capstone_extraction' }
  scope: RunDraft & { plan_sha256: string; choice: 'approve' | 'hold'; reason: string; consent: 'save_bounded_governance_execution_decision' }
  execute: { run_id: string; plan_sha256: string; scope_decision_id: string; scope_decision_sha256: string; consent: 'execute_approved_bounded_capstone_extraction' }
  finalize: { run_id: string; plan_sha256: string; authorization_sha256: string; extraction_events_sha256: string; consent: 'finalize_saved_governance_results_without_reexecution' }
  finding: RunDraft & { result_sha256: string; field: 'Funds Obligated to Date'; observed_value: string; source_references: { source_id: GovernanceSourceId; page: number; quote: string }[]; explanation: string; consent: 'save_my_original_source_finding_before_repair' }
  memo: RunDraft & { result_sha256: string; owner_user_id: string; intended_use: string; supported_inputs: string; limitations: string; review_route: string; consent: 'save_checked_capstone_memo_without_release' }
  release: RunDraft & MemoReference & { opened: boolean; choice: 'approve' | 'hold'; reason: string; destination_id: 'private_training_inbox'; audience: 'enrolled_learner_only'; consent: 'save_my_exact_capstone_memo_release_choice' }
  handoff: RunDraft & MemoReference & { release_id: string; release_sha256: string; destination_id: 'private_training_inbox'; action: 'attempt' | 'retry_failed_handoff'; previous_failed_id: string | null; previous_failed_sha256: string | null; consent: 'attempt_approved_private_capstone_handoff' | 'retry_only_failed_private_capstone_handoff' }
  review: RunDraft & { handoff_id: string; handoff_sha256: string; final_supervision: string; previous_submission_id: string | null; consent: 'save_my_capstone_supervision_interpretation' }
}
export type GovernanceAction = keyof GovernanceBodies
export type GovernanceRequest = { [K in GovernanceAction]: { action: K; body: GovernanceBodies[K] } }[GovernanceAction]
type DecisionKind = 'correction' | 'scope' | 'finding' | 'memo' | 'release' | 'handoff' | 'review'
export interface GovernanceRecord<K extends DecisionKind> extends GovernanceIdentity {
  uuid: string; user_id: string; record_kind: string; record_sha256: string; run_id: string; case: GovernanceCase
  submission: GovernanceBodies[K]; submitted_at: string; prompt?: { id: string; phase: string; prompt: string }
  credit_awarded: false; module_completion_eligible?: false
}
export interface GovernanceCorrection extends GovernanceRecord<'correction'> { input_snapshot: GovernanceCapture; flawed_proposal: string; execution_authorized: false; external_effects_authorized: false }
export interface GovernanceFinding extends GovernanceRecord<'finding'> { run: GovernanceRun; checks: GovernanceChecks }
export interface GovernanceScope extends GovernanceRecord<'scope'> { plan_sha256: string; case_sha256: string }
export interface GovernanceChecks {
  run_id: string; phase: 'original' | 'repair'; complete: boolean; source_supported: boolean; observed_semantic_failure: boolean
  fields: { field: string; actual_value: unknown; output_present: boolean; output_comparable: boolean; matches_source: boolean; status: string }[]
}
export interface GovernanceRun extends GovernanceIdentity {
  run_id: string; run_sha256: string; state: 'prepared' | 'executing' | 'completed' | 'failed' | 'uncertain'; phase: 'original' | 'repair'
  plan_sha256: string; case_sha256: string; input_snapshot: GovernanceCapture; input_snapshot_id: string; model_names: string[]; prepared_at: string
  scope_correction: GovernanceCorrection; source_finding: GovernanceFinding | null; changed_fields: string[]; original_run_id: string | null; original_run_sha256: string | null
  scope_decision_id: string | null; scope_decision_sha256: string | null; scope_decision: GovernanceScope | null; authorization_sha256: string | null
  result_sha256: string | null; extraction_events_sha256: string; approval_question: { prompt: string }
  extraction_events: { receipt_sha256: string; receipt: { kind: 'extraction_started' | 'extraction_completed'; extraction_index: number; result?: unknown } }[]
  result: { status: string; checks?: GovernanceChecks; extraction?: unknown; repair_checks?: { repair_requirements_supported: boolean }; reason?: string; completion_mode?: string } | null
  can_save_scope: boolean; can_execute: boolean; can_finalize: boolean; credit_awarded: false; module_completion_eligible: false
}
export interface GovernanceFile { filename: string; content_type: 'application/json'; sha256: string; byte_length: number; memo: { owner_user_id: string; results: Record<string, unknown>; accountability: Record<string, string>; [key: string]: unknown } }
export interface GovernanceMemo extends GovernanceRecord<'memo'> { run: GovernanceRun; file: GovernanceFile; release_authorized: false; delivery_confirmed: false }
export interface GovernanceRelease extends GovernanceRecord<'release'> { memo: GovernanceMemo; delivery_confirmed: false }
export interface GovernanceHandoff extends GovernanceRecord<'handoff'> { release: GovernanceRelease; status: 'failed' | 'delivered'; reason: string
  destination_written: boolean; destination_copy: GovernanceFile | null; previous_failed_receipt: GovernanceHandoff | null; external_delivery: false }
export interface GovernanceReview extends GovernanceRecord<'review'> { handoff: GovernanceHandoff }
export interface GovernanceRecords { capture: GovernanceCapture; run: GovernanceRun; correction: GovernanceCorrection; scope: GovernanceScope; finding: GovernanceFinding; memo: GovernanceMemo; release: GovernanceRelease; handoff: GovernanceHandoff; review: GovernanceReview }
export type GovernanceKind = keyof GovernanceRecords
export type GovernanceView = { [K in GovernanceKind]: { kind: K; value: GovernanceRecords[K] } }[GovernanceKind]
export interface GovernanceList extends GovernanceIdentity {
  case: GovernanceCase; can_submit: boolean; read_only_reason: string | null
  extractions: { artifact_id: string; title: string }[]; older_extractions_available: boolean
  assigned_sources: { document_id: string; title: string; text: string; processing: boolean }[]
  records: { [K in GovernanceKind]: { items: { reference_id: string; kind: K; saved_at: string; run_id: string | null; state: string | null; phase: string | null; artifact_title: string | null; memo_id: string | null; previous_submission_id: string | null }[]; older_available: boolean } }
}
