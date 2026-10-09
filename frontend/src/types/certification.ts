export interface ModuleProgress {
  completed: boolean
  stars: number
  completed_at: string | null
  attempts: number
  xp_earned: number
  xp_carried?: number
  credit_origin?: 'transferred' | 'assessed'
  provisioned_docs?: string[]
  self_assessment?: Record<string, string>
  scenario_attempt_id?: string
  learning_position?: LearningPosition
}

export interface LearningPosition {
  module_id: string
  lesson_id: string
  revision: number
  content_sha256: string
  saved_at: string
}

export interface PositionSaved {
  saved: true
  enrollment_id: string
  course_version: string
  learning_position: LearningPosition
  position_revision: number
}

export interface CertExercise {
  assessment_method?: string
  overview?: string
  documents: string[]
  instructions: string[]
  expected_fields: string[]
  expected_values: Record<string, string[]>
  star_criteria: Record<string, string>
}

export interface CertificationLabStatus extends CourseIdentity {
  module_id: string
  state: 'not_required' | 'not_setup' | 'processing' | 'ready' | 'failed' | 'unavailable'
  folder_id: string | null
  folder_name: string | null
  documents: { name: string; document_id: string | null; state: 'processing' | 'ready' | 'failed' | 'unavailable' }[]
  credit_changed: false
}

export interface CourseIdentity {
  enrollment_id?: string
  course_version?: string
  course_title?: string
  manifest_sha256?: string
  modules_total?: number
  module_ids?: string[]
  maximum_xp?: number
}

export interface CredentialScope {
  contract_id: string
  contract_sha256: string
  promise: string
  agent_assistance: string
  exclusions: string[]
}

export interface CourseDefinition {
  bridge_path?: {
    path_id: string; title: string; description: string; state: 'design_draft' | 'release_candidate'
    course_version: string; manifest_sha256: string; required_outcomes: number
    credit_policy: 'same_course_same_required_outcomes'; duration_minutes: null; rules: string[]
    stages: { id: string; title: string; purpose: string; modules: { module_id: string; title: string; required_outcomes: number }[] }[]
  } | null
  credential_scope?: (CredentialScope & { state: 'design_draft' | 'release_candidate' }) | null
  progression_policy?: { policy_id: string; state: 'design_draft' | 'release_candidate'; required_modules: number; required_outcomes: number; base_xp_total: number; rules: string[] } | null
  selected_outcome_completion?: boolean
  versioned: true
  enrollment_id: string
  course_version: string
  course_title: string
  manifest_sha256: string
  modules_total: number
  maximum_xp: number
  modules: ModuleDefinition[]
  prerequisites: Record<string, string[]>
  levels: { name: string; xp: number }[]
  tiers: TierDefinition[]
}

export interface UpgradeCourseOption {
  course_version: string
  course_title: string
  manifest_sha256: string
  description: string
  required_outcome_count: number
}

export interface UpgradeOptions {
  enrollment_id: string
  policy: 'optional'
  can_activate: false
  courses: UpgradeCourseOption[]
}

export interface SavedWorkPreservationPlan {
  policy: 'retain_with_original_enrollment'
  source_enrollment_id: string
  read_only: true
  can_activate: false
  credit_transferred: false
  reconciliation_required_count: number
  plan_sha256: string
  entries: { kind: string; label: string; record_id: string; module_id: string; module_title: string; state: string;
    proposed_action: 'retain_saved_work' | 'reconcile_operation' | 'retain_unexecuted_work' | 'retain_unassessed_work' | 'retain_original_result';
    reconciliation_required: boolean; explanation: string }[]
}

export interface UpgradePreview {
  preservation_plan?: SavedWorkPreservationPlan
  policy: 'optional'
  can_activate: false
  preview_sha256: string
  source: {
    enrollment_id: string
    course_version: string
    course_title: string
    provenance: string
    total_xp: number
    certified: boolean
    credential_preserved: boolean
    completed_modules: { module_id: string; title: string; completed_at: string | null; xp_earned: number; stars: number }[]
    has_saved_place: boolean
  }
  target: {
    course_version: string
    course_title: string
    manifest_sha256: string
    required_outcome_count: number
    transferred_outcome_count: number
    modules: { module_id: string; title: string; outcomes: { outcome_id: string; statement: string; disposition: 'requires_assessment'; reason: string }[] }[]
  }
  saved_work: { kind: string; label: string; count: number }[]
  work_in_flight: boolean
  unfinished_answers: boolean
  credential_needs_preservation: boolean
}

export interface PendingCompletion {
  attempt_id: string
  module_id: string
  state: 'uncertain' | 'evaluating' | 'graded' | 'review'
  in_flight: boolean
}

export interface CertificationProgress extends CourseIdentity {
  pending_completions?: PendingCompletion[]
  id: string
  user_id: string
  modules: Record<string, ModuleProgress>
  total_xp: number
  level: string
  certified: boolean
  certified_at: string | null
  last_activity_date: string | null
  unlocked?: boolean
  learning_position?: LearningPosition | null
  position_revision?: number
}

export interface ValidationCheck {
  role?: 'required' | 'advisory'
  name: string
  passed: boolean
  detail: string
}

export interface ValidationResult extends CourseIdentity {
  assessment_kind?: 'selected_outcome_validation' | 'transferred_outcome_validation'
  passed: boolean
  stars: number
  checks: ValidationCheck[]
}

export interface CompletionResult extends CourseIdentity {
  credit_origin?: 'transferred'
  xp_carried?: number
  source_enrollment_id?: string
  attempt_id?: string
  module_id: string
  stars: number
  xp_earned: number
  total_xp: number
  level: string
  level_up: boolean
  certified: boolean
  validation: ValidationResult
}

export interface OutcomeCompletionSelection {
  review_attempt_id?: string
  scenario_attempt_id?: string
}

export interface KnowledgeCheckOption {
  text: string
  correct: boolean
  explanation: string
}

export interface KnowledgeCheckData {
  question: string
  options: KnowledgeCheckOption[]
}

export interface LessonSection {
  /** Stable authored identity; never recompute it from position or an edited title. */
  id?: string
  revision?: number
  title: string
  content: string
  variant: 'concept' | 'walkthrough' | 'key-terms' | 'insight'
  objective?: string
  knowledgeCheck?: KnowledgeCheckData
  diagram?: string
}

export interface ModuleDefinition {
  id: string
  number: number
  title: string
  subtitle: string
  description: string
  objectives: string[]
  tips: string[]
  lessons: LessonSection[]
  xp: number
  icon: string
  estimatedMinutes?: number
  assessment?: AssessmentDefinition | null
  scenarioAssessment?: ScenarioDefinition
  decisionPrompts?: PracticalDecisionPrompt[]
  practicalPreparation?: boolean
  repairAssignment?: RepairAssignment
  processAssessment?: ProcessCaseDefinition
  workflowDesignAssessment?: WorkflowDesignCaseDefinition
  connectedWorkflowAssessment?: import('./connectedWorkflow').ConnectedCase
  governanceAssessment?: import('./governanceAssessment').GovernanceCase
  batchAssessment?: import('./batchAssessment').BatchCase
  validationAssessment?: import('./validationSuite').ValidationCase
  outputWorkflowAssessment?: import('./outputWorkflow').OutputCase
  budgetWorkflowAssessment?: import('./budgetWorkflow').BudgetCase
}

export interface PracticalPreparationBody {
  request_id: string
  artifact_id: string
}

export interface PracticalExecutionBody {
  plan_sha256: string
  scope_decision_id: string
  scope_decision_sha256: string
  consent: 'execute_saved_inputs'
}

export interface SavedPracticalExecution {
  enrollment_id: string
  module_id: string
  course_version: string
  manifest_sha256: string
  input_snapshot_id: string
  run_id: string
  state: 'prepared' | 'executing' | 'completed' | 'failed' | 'uncertain'
  plan_sha256: string
  scope_decision_id: string | null
  scope_decision_sha256: string | null
  model_names: string[]
  can_execute: boolean
  blocked_reason: string | null
  started_at: string | null
  finished_at: string | null
  documents_executed: number | null
  result_available: boolean
  credit_awarded: false
  module_completion_eligible: false
}

export interface SavedPracticalPreparation {
  request_id: string
  input_snapshot_id: string
  enrollment_id: string
  module_id: string
  course_version: string
  manifest_sha256: string
  artifact_id: string
  artifact_title: string
  artifact_sha256: string
  captured_at: string
  fields: string[]
  documents: { document_id: string; assigned_filename: string; source_sha256: string }[]
  state: 'inputs_saved' | 'prepared' | 'executing' | 'completed' | 'failed' | 'uncertain'
  run_id: string | null
  plan_sha256: string | null
  model_names: string[]
  scope_prompt_id: string | null
  can_execute: false
  credit_awarded: false
  module_completion_eligible: false
}

export interface AssessmentDefinition {
  title: string
  subtitle: string
  questions: readonly { key: string; question: string; options: readonly string[] }[]
}

export interface TierDefinition {
  name: string
  theme: string
  narrative: string
  moduleIds: string[]
  celebration: string
}

export interface ScenarioDefinition {
  bank_id: string
  revision: number
  bank_sha256: string
  module_id: string
  questions: { id: string; prompt: string; choices: { id: string; text: string }[] }[]
}

export interface ScenarioResult {
  passed: boolean
  assessment_kind: 'scenario_recognition'
  credit_awarded: false
  checks: { id: string; name: string; passed: boolean; detail: string; role: 'required' }[]
}

export interface ScenarioSubmission {
  reused_existing?: boolean
  attempt_id: string
  module_id: string
  bank_sha256: string
  linked_to_progress: boolean
  result: ScenarioResult
}

export interface SavedScenarioSubmission {
  uuid: string
  enrollment_id: string
  module_id: string
  bank_sha256: string
  answers: Record<string, string>
  result: ScenarioResult
  progress_link?: 'selected' | 'unlinked' | 'superseded' | 'unavailable'
  read_only?: true
}

export interface PracticalDecisionPrompt {
  id: string
  revision: number
  module_id: string
  outcome_id: string
  phase: 'before_execution' | 'after_execution'
  question: string
  choices: Record<string, string>
  required_fields: string[]
  prompt_sha256: string
}

export interface PracticalValueCheck {
  field: string
  decision: 'supported' | 'unsupported' | 'unresolved'
  checked_value: string
  source_document_id: string
  source_quote: string
  reason: string
}

export interface PracticalDecisionBody {
  request_id: string
  run_id: string
  prompt_sha256: string
  choice: string
  reason: string
  value_checks: PracticalValueCheck[]
  proposal_selection?: { proposal_sha256: string; source_id: string } | null
  repair_case_sha256?: string | null
}

export interface SavedPracticalDecision {
  uuid: string
  enrollment_id: string
  module_id: string
  run_id: string
  prompt_id: string
  prompt_sha256: string
  submitted_at: string
  submission: PracticalDecisionBody
  credit_awarded: false
}

export interface PracticalHistoryCourseSummary {
  enrollment_id: string
  course_version: string
  course_title: string
  enrollment_state: string
  selection_status?: 'prepared' | 'current' | 'confirmation_pending' | 'retained'
  created_at: string | null
  definition_available: boolean
  provenance?: string
}

export interface PracticalHistoryCourses {
  read_only: true
  courses: PracticalHistoryCourseSummary[]
  older_courses_available: boolean
}

export interface PracticalHistoryCourse {
  enrollment_id: string
  course_version: string
  course_title: string
  manifest_sha256: string
  enrollment_state: string
  selection_status?: 'prepared' | 'current' | 'confirmation_pending' | 'retained'
  provenance?: string
  read_only: true
  modules: { module_id: string; title: string; decision_prompts: PracticalDecisionPrompt[]; scenario_definition?: ScenarioDefinition | null; process_definition?: ProcessCaseDefinition | null; workflow_design_definition?: WorkflowDesignCaseDefinition | null; connected_workflow_definition?: import('./connectedWorkflow').ConnectedCase | null; budget_workflow_definition?: import('./budgetWorkflow').BudgetCase | null; validation_definition?: import('./validationSuite').ValidationCase | null; governance_definition?: import('./governanceAssessment').GovernanceCase | null; batch_definition?: import('./batchAssessment').BatchCase | null; output_workflow_definition?: import('./outputWorkflow').OutputCase | null }[]
}

export interface ScenarioHistoryList {
  enrollment_id: string
  module_id: string
  bank_sha256: string
  read_only: true
  older_attempts_available: boolean
  attempts: { attempt_id: string; submitted_at: string; passed: boolean }[]
}

export interface ScenarioHistoryResult {
  enrollment_id: string
  module_id: string
  attempt_id: string
  bank_sha256: string
  submitted_at: string
  read_only: true
  assessment_kind: 'scenario_recognition'
  credit_awarded: false
  passed: boolean
  questions: { id: string; prompt: string; chosen_answer: string | null; passed: boolean; feedback: string }[]
}

export interface PracticalDecisionContext {
  enrollment_id: string
  module_id: string
  prompt: PracticalDecisionPrompt
  run_id: string
  run_state: string
  can_submit: boolean
  read_only_reason?: string | null
  lab_folder_id: string | null
  artifact: { title: string; fields: { title?: string | null; searchphrase: string; is_optional: boolean; enum_values?: string[] }[] }
  documents: { document_id: string; title: string; text: string }[]
  result: { entities?: Record<string, unknown>[] } | null
  latest_decision: SavedPracticalDecision | null
  scope_proposal?: {
    case: { task: string }
    proposal_sha256: string
    original_source_id: string
    source_options: { id: string; title: string }[]
  } | null
  repair_case?: {
    repair_case_sha256: string
    source_document_id: string
    case: RepairAssignment
  } | null
}

export interface RepairAssignment {
  module_id: 'extraction_engine'
  task: string
  baseline: {
    provenance: 'authored_flawed_example_not_an_execution'
    notice: string
    fields: { title: string; searchphrase: string; is_optional: boolean; enum_values: string[] }[]
    output: Record<string, string | null>
  }
}

export type AutomaticReviewStatus = 'prepared' | 'evaluating' | 'requirements_supported' | 'revision_required' | 'grading_unavailable'
export interface SavedAutomaticReviewSummary {
  attempt_id: string
  enrollment_id: string
  module_id: string
  run_id: string | null
  process_submission_id?: string
  workflow_design_submission_id?: string
  connected_review_submission_id?: string
  validation_review_submission_id?: string
  governance_review_submission_id?: string
  batch_review_submission_id?: string
  output_review_submission_id?: string
  budget_review_submission_id?: string
  prepared_at: string
  finished_at: string | null
  parent_attempt_id: string | null
  status: AutomaticReviewStatus
}
export interface SavedAutomaticReview extends SavedAutomaticReviewSummary {
  course_version: string
  manifest_sha256: string
  assessment_kind: 'practical_review_draft' | 'process_design_review_draft' | 'workflow_design_review_draft' | 'connected_workflow_review_draft' | 'budget_workflow_review_draft' | 'output_workflow_review_draft' | 'validation_suite_review_draft' | 'bounded_batch_review_draft' | 'governance_capstone_review_draft'
  credit_awarded: false
  module_completion_eligible: false
  staff_review_required: false
  can_request_review: false
  can_retry_review: false
  outcomes: {
    outcome_id: string
    statement: string
    method: string
    verdict: 'supported' | 'contradicted' | 'unclear' | 'not_assessed'
    explanation: string
    revision_instruction: string
    citations: { kind: string; quote: string }[]
  }[]
}
export interface SavedAutomaticReviewList {
  enrollment_id: string
  module_id: string
  attempts: SavedAutomaticReviewSummary[]
  older_attempts_available: boolean
}


export interface ProcessCaseDefinition {
  id: string
  revision: number
  module_id: 'process_mapping'
  case_sha256: string
  provenance: 'authored_fictional_design_case_not_execution'
  notice: string
  task: string
  assigned_inputs: { id: string; description: string }[]
  intended_output: string
  repetition: string
  authority: string
  exclusions: string[]
  exception_conditions: string[]
  flawed_proposal: string
  method_comparisons: { id: string; situation: string }[]
  method_options: string[]
  questions: { id: string; outcome_id: string; prompt: string; response_kind: string }[]
}
export interface ProcessSubmissionBody {
  request_id: string
  case_sha256: string
  answers: Record<string, string>
  consent: 'save_reviewed_process_design'
  previous_submission_id: string | null
}
export interface SavedProcessSubmission {
  uuid: string
  enrollment_id: string
  module_id: 'process_mapping'
  course_version: string
  manifest_sha256: string
  case: ProcessCaseDefinition
  submission: ProcessSubmissionBody
  submitted_at: string
  submission_channel: 'authenticated_learner_process_request'
  credit_awarded: false
  module_completion_eligible: false
}
export interface ProcessSubmissionList {
  enrollment_id: string
  module_id: 'process_mapping'
  course_version: string
  manifest_sha256: string
  case: ProcessCaseDefinition
  submissions: { submission_id: string; submitted_at: string; previous_submission_id: string | null }[]
  older_submissions_available: boolean
  can_submit: boolean
  read_only_reason: string | null
}


export interface WorkflowDesignCaseDefinition {
  id: string
  revision: number
  module_id: 'workflow_design'
  provenance: 'authored_workflow_design_case_not_execution'
  case_sha256: string
  notice: string
  task: string
  assigned_inputs: { id: string; description: string }[]
  intended_output: string
  exclusions: string[]
  supplied_map: { id: string; provenance: 'authored_example_not_learner_work'; method_and_rationale: string; ordered_process_map: string; bounded_task_brief: string }
  flawed_proposal: string
  configuration_instructions: string[]
  questions: { id: string; outcome_id: string; prompt: string; response_kind: string }[]
}
export interface WorkflowDesignCaptureBody {
  request_id: string
  workflow_id: string
  case_sha256: string
  handoff: 'owned_saved_process_submission' | 'supplied_example'
  process_submission_id: string | null
  consent: 'capture_saved_workflow_design'
}
export interface SavedWorkflowDesignCapture {
  uuid: string
  enrollment_id: string
  module_id: 'workflow_design'
  course_version: string
  manifest_sha256: string
  input_snapshot_sha256: string
  artifact_id: string
  artifact_sha256: string
  request: WorkflowDesignCaptureBody
  case: WorkflowDesignCaseDefinition
  handoff: { kind: 'owned_saved_process_submission' | 'supplied_example'; original_submission?: SavedProcessSubmission; supplied_map?: WorkflowDesignCaseDefinition['supplied_map'] }
  artifact: {
    workflow: { id: string; name: string; version: number; input_config: Record<string, unknown>; output_config: Record<string, unknown>; resource_config: Record<string, unknown>; config_override: Record<string, unknown> | null }
    steps: { step: { id: string; name: string; is_output: boolean; data: Record<string, unknown> }; tasks: { id: string; name: string; data: Record<string, unknown> }[] }[]
    referenced_extraction_sets: Record<string, unknown>
  }
  credit_awarded: false
  module_completion_eligible: false
  execution_status: 'not_started'
}
export interface WorkflowDesignSubmissionBody {
  request_id: string
  input_snapshot_id: string
  input_snapshot_sha256: string
  case_sha256: string
  answers: Record<string, string>
  consent: 'approve_saved_workflow_design_for_assessment'
  previous_submission_id: string | null
}
export interface SavedWorkflowDesignSubmission {
  uuid: string
  enrollment_id: string
  module_id: 'workflow_design'
  course_version: string
  manifest_sha256: string
  input_snapshot: Omit<SavedWorkflowDesignCapture, 'input_snapshot_sha256'>
  submission: WorkflowDesignSubmissionBody
  submitted_at: string
  submission_channel: 'authenticated_learner_workflow_design_request'
  credit_awarded: false
  module_completion_eligible: false
  execution_authorized: false
}
export interface WorkflowDesignList {
  enrollment_id: string
  module_id: 'workflow_design'
  course_version: string
  manifest_sha256: string
  case: WorkflowDesignCaseDefinition
  submissions: { submission_id: string; submitted_at: string; previous_submission_id: string | null; input_snapshot_id: string; workflow_name: string }[]
  older_submissions_available: boolean
  workflows: { workflow_id: string; name: string; version: number }[]
  older_workflows_available: boolean
  process_choices: ProcessSubmissionList['submissions']
  older_process_choices_available: boolean
  can_submit: boolean
  read_only_reason: string | null
}
