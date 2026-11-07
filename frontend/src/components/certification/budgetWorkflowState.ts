import type { BudgetCalculation, BudgetCapture, BudgetCase, BudgetIdentity, BudgetList, BudgetRequest, BudgetReview, BudgetRun, BudgetSaved } from '../../types/budgetWorkflow'
import { connectedId as id, connectedDigest as digest } from './connectedWorkflowState'

export const sameBudgetCase = (value: BudgetCase, expected: BudgetCase) => value.module_id === 'advanced_nodes'
  && value.provenance === 'authored_budget_method_case_not_execution' && digest(value.case_sha256) && value.case_sha256 === expected.case_sha256
  && value.questions.length === 3 && new Set(value.questions.map(q => q.id)).size === 3
  && value.questions.every(q => ['method_choice', 'calculation_review', 'dependency_review'].includes(q.id))
const sameCourse = (value: BudgetIdentity, listing: BudgetList) => value.module_id === 'advanced_nodes'
  && value.enrollment_id === listing.enrollment_id && value.course_version === listing.course_version && value.manifest_sha256 === listing.manifest_sha256
const amount = (value: unknown) => value === null || typeof value === 'string' && /^(0|[1-9][0-9]{0,8})\.[0-9]{2}$/.test(value)
const text = (value: unknown, min: number, max: number): value is string => typeof value === 'string' && value.trim().length >= min && value.length <= max
const calculationIds = ['equipment_subtotal', 'listed_direct_subtotal', 'listed_summary_total']
export function sameBudgetJson(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return false
  const left = a as Record<string, unknown>, right = b as Record<string, unknown>
  return Object.keys(left).length === Object.keys(right).length && Object.keys(left).every(key => Object.hasOwn(right, key) && sameBudgetJson(left[key], right[key]))
}
export function validBudgetRequest(value: BudgetRequest | null, definition: BudgetCase): value is BudgetRequest {
  if (!value || !value.body || typeof value.body !== 'object') return false
  const body = value.body
  if (!['execute', 'finalize'].includes(value.action) && (!('request_id' in body) || !id(body.request_id) || !('case_sha256' in body) || body.case_sha256 !== definition.case_sha256)) return false
  switch (value.action) {
    case 'calculation': return id(value.body.document_id) && (value.body.previous_snapshot_id === null || id(value.body.previous_snapshot_id) && value.body.previous_snapshot_id !== value.body.request_id)
      && value.body.consent === 'save_source_bound_budget_calculations' && Array.isArray(value.body.records) && value.body.records.length === 3
      && new Set(value.body.records.map(record => record.id)).size === 3 && value.body.records.every(record => calculationIds.includes(record.id)
        && record.operation === 'sum' && record.unit === 'USD' && amount(record.result) && text(record.interpretation, 20, 4000)
        && ['recorded_deterministic_arithmetic', 'explicit_learner_arithmetic'].includes(record.method)
        && Array.isArray(record.inputs) && record.inputs.length >= 2 && record.inputs.length <= 10 && new Set(record.inputs.map(input => input.id)).size === record.inputs.length
        && record.inputs.every(input => typeof input.id === 'string' && amount(input.value) && input.unit === 'USD' && Number.isInteger(input.source_page) && input.source_page >= 1
          && text(input.explanation, 10, 2000) && typeof input.source_quote === 'string' && input.source_quote.length <= 2000
          && (input.status === 'unresolved' || input.status === 'supported' && input.value !== null && !!input.source_quote.trim())))
    case 'capture': return /^[a-f0-9]{24}$/.test(value.body.workflow_id) && id(value.body.calculation_snapshot_id) && digest(value.body.calculation_snapshot_sha256)
      && text(value.body.method_choice, 30, 8000) && value.body.consent === 'capture_budget_workflow_and_method'
    case 'prepare': return id(value.body.input_snapshot_id) && digest(value.body.input_snapshot_sha256) && value.body.consent === 'prepare_budget_workflow_plan'
    case 'scope': return id(value.body.run_id) && digest(value.body.plan_sha256) && ['approve', 'hold'].includes(value.body.choice) && text(value.body.reason, 10, 4000) && value.body.consent === 'save_budget_workflow_scope_decision'
    case 'execute': return id(value.body.run_id) && digest(value.body.plan_sha256) && id(value.body.scope_decision_id) && digest(value.body.scope_decision_sha256) && value.body.consent === 'execute_approved_budget_workflow'
    case 'finalize': return id(value.body.run_id) && digest(value.body.plan_sha256) && digest(value.body.authorization_sha256) && digest(value.body.task_events_sha256) && value.body.consent === 'finalize_saved_budget_results_without_reexecution'
    case 'review': return id(value.body.run_id) && digest(value.body.result_sha256) && (value.body.previous_submission_id === null || id(value.body.previous_submission_id))
      && !!value.body.answers && Object.keys(value.body.answers).length === 2 && text(value.body.answers.calculation_review, 1, 8000) && text(value.body.answers.dependency_review, 1, 8000)
      && value.body.consent === 'save_budget_calculation_and_dependency_review'
    default: return false
  }
}
export function verifyBudgetCalculation(value: BudgetCalculation, listing: BudgetList) {
  if (!sameCourse(value, listing) || !sameBudgetCase(value.case, listing.case) || !id(value.uuid) || !digest(value.calculation_snapshot_sha256)
    || !validBudgetRequest({ action: 'calculation', body: value.request }, listing.case) || value.request.request_id !== value.uuid
    || value.document.document_id !== value.request.document_id || value.document.source_sha256 !== listing.case.source_sha256
    || value.document.assigned_filename !== listing.case.source_filename || !value.document.text.trim()
    || value.checks.checks.length !== 3 || new Set(value.checks.checks.map(check => check.id)).size !== 3
    || value.checks.checks.some(check => !calculationIds.includes(check.id) || !['supported', 'revision_required', 'unresolved'].includes(check.state))
    || value.checks.all_arithmetic_supported !== value.checks.checks.every(check => check.state === 'supported')
    || value.credit_awarded !== false || value.module_completion_eligible !== false) throw new Error('Different saved calculation')
  return value
}
export function verifyBudgetCapture(value: BudgetCapture, listing: BudgetList) {
  verifyBudgetCalculation(value.calculation, listing)
  if (!sameCourse(value, listing) || !sameBudgetCase(value.case, listing.case) || !id(value.uuid) || !digest(value.input_snapshot_sha256)
    || !digest(value.artifact_sha256) || value.artifact.workflow.id !== value.artifact_id || !Array.isArray(value.artifact.steps)
    || !text(value.method_choice, 30, 8000) || value.execution_authorized !== false || value.credit_awarded !== false) throw new Error('Different saved workflow')
  return value
}
export function verifyBudgetRun(value: BudgetRun, listing: BudgetList) {
  verifyBudgetCapture(value.input_snapshot, listing)
  const expected = value.stage_plans.reduce((count, stage) => count + stage.tasks.length * 2, 0)
  if (!sameCourse(value, listing) || !id(value.run_id) || !digest(value.plan_sha256) || value.case_sha256 !== listing.case.case_sha256
    || value.input_snapshot_id !== value.input_snapshot.uuid || value.stage_plans.length !== 2 || ![4, 6].includes(expected)
    || !['prepared', 'executing', 'completed', 'failed', 'uncertain'].includes(value.state) || !Array.isArray(value.task_events) || value.task_events.length > expected
    || value.task_events.some((event, index) => event.receipt.sequence !== index || !['task_started', 'task_completed', 'task_failed'].includes(event.receipt.kind))
    || value.state === 'completed' && (value.task_events.length !== expected || value.task_events.some(e => e.receipt.kind === 'task_failed') || value.result?.status !== 'completed' || !digest(value.result_sha256))
    || value.scope_decision && (!sameCourse(value.scope_decision, listing) || value.scope_decision.uuid !== value.scope_decision_id || value.scope_decision.run_id !== value.run_id || value.scope_decision.plan_sha256 !== value.plan_sha256)
    || value.credit_awarded !== false || value.module_completion_eligible !== false) throw new Error('Different saved budget run')
  return value
}
export function verifyBudgetReview(value: BudgetReview, listing: BudgetList) {
  verifyBudgetRun(value.run, listing)
  if (!sameCourse(value, listing) || !sameBudgetCase(value.case, listing.case) || !id(value.uuid) || value.submission.request_id !== value.uuid
    || !validBudgetRequest({ action: 'review', body: value.submission }, listing.case) || value.run.run_id !== value.submission.run_id || value.run.result_sha256 !== value.submission.result_sha256
    || value.run.state !== 'completed' || value.credit_awarded !== false || value.module_completion_eligible !== false) throw new Error('Different saved result review')
  return value
}
export function verifyBudgetResponse(saved: BudgetSaved, listing: BudgetList, request: BudgetRequest) {
  if (request.action === 'calculation') {
    const value = verifyBudgetCalculation(saved as BudgetCalculation, listing)
    if (!sameBudgetJson(value.request, request.body)) throw new Error('Different calculation request')
  } else if (request.action === 'capture') {
    const value = verifyBudgetCapture(saved as BudgetCapture, listing)
    if (value.uuid !== request.body.request_id || value.artifact_id !== request.body.workflow_id || value.method_choice !== request.body.method_choice
      || value.calculation.uuid !== request.body.calculation_snapshot_id || value.calculation.calculation_snapshot_sha256 !== request.body.calculation_snapshot_sha256) throw new Error('Different capture request')
  } else if (request.action === 'review') {
    const value = verifyBudgetReview(saved as BudgetReview, listing)
    if (!sameBudgetJson(value.submission, request.body)) throw new Error('Different result review')
  } else {
    const value = verifyBudgetRun(saved as BudgetRun, listing)
    if (request.action === 'prepare') {
      if (value.run_id !== request.body.request_id || value.input_snapshot_id !== request.body.input_snapshot_id || value.input_snapshot.input_snapshot_sha256 !== request.body.input_snapshot_sha256) throw new Error('Different plan')
    } else if (value.run_id !== request.body.run_id || value.plan_sha256 !== request.body.plan_sha256) throw new Error('Different run')
    if (request.action === 'execute' && (value.scope_decision_id !== request.body.scope_decision_id || value.scope_decision_sha256 !== request.body.scope_decision_sha256)) throw new Error('Changed scope')
    if (request.action === 'finalize' && (value.authorization_sha256 !== request.body.authorization_sha256 || value.task_events_sha256 !== request.body.task_events_sha256)) throw new Error('Changed task evidence')
  }
  return saved
}
