import type { ValidationCase, ValidationCapture, ValidationIdentity, ValidationList, ValidationRequest, ValidationReview, ValidationRun, ValidationSaved, ValidationSuiteRecord } from '../../types/validationSuite'
import { connectedId as id, connectedDigest as digest } from './connectedWorkflowState'
import { sameOutputJson as same } from './outputWorkflowState'
const text = (value: unknown, min: number, max: number): value is string => typeof value === 'string' && value.trim().length >= min && value.length <= max
const course = (v: ValidationIdentity, l: ValidationList) => v.module_id === 'validation_qa' && v.enrollment_id === l.enrollment_id && v.course_version === l.course_version && v.manifest_sha256 === l.manifest_sha256
export const sameValidationCase = (v: ValidationCase, d: ValidationCase) => v.module_id === 'validation_qa' && v.provenance === 'authored_validation_assignment_not_observed_failure_or_retest'
  && digest(v.case_sha256) && v.case_sha256 === d.case_sha256 && same(v.sources, d.sources) && same(v.fields, d.fields) && same(v.questions, d.questions)
export function validValidationRequest(v: ValidationRequest | null, d: ValidationCase): v is ValidationRequest {
  try {
    if (!v || !v.body || !['capture', 'suite', 'prepare', 'scope', 'execute', 'finalize', 'review'].includes(v.action)) return false
    const b = v.body
    if ('request_id' in b && !id(b.request_id)) return false
    if (!['execute', 'finalize'].includes(v.action) && (!('case_sha256' in b) || b.case_sha256 !== d.case_sha256)) return false
    switch (v.action) {
      case 'capture': return id(v.body.artifact_id) && v.body.consent === 'capture_validation_extraction_and_complete_sources'
      case 'suite': return id(v.body.input_snapshot_id) && digest(v.body.input_snapshot_sha256) && v.body.consent === 'save_checked_representative_expectations_before_execution'
        && text(v.body.suite_design, 40, 8000) && v.body.expectations.length === 6 && new Set(v.body.expectations.map(e => `${e.source_id}:${e.field}`)).size === 6
        && v.body.expectations.every(e => d.sources.some(s => s.id === e.source_id) && d.fields.some(f => f.title === e.field)
          && (e.expected_kind === 'explicit_absence' ? e.expected_value === null : e.expected_kind === 'value' && text(e.expected_value, 1, 1000))
          && text(e.source_reason, 20, 3000) && e.source_references.length >= 1 && e.source_references.length <= 3
          && e.source_references.every(a => Number.isInteger(a.page) && a.page > 0 && text(a.quote, 3, 2000)))
      case 'prepare': return id(v.body.input_snapshot_id) && digest(v.body.input_snapshot_sha256) && id(v.body.suite_id) && digest(v.body.suite_record_sha256)
        && (v.body.original_run_id === null && v.body.original_run_sha256 === null || id(v.body.original_run_id) && digest(v.body.original_run_sha256)) && v.body.consent === 'prepare_complete_validation_suite'
      case 'scope': return id(v.body.run_id) && digest(v.body.plan_sha256) && ['approve', 'hold'].includes(v.body.choice) && text(v.body.reason, 10, 4000) && v.body.consent === 'save_validation_suite_scope_decision'
      case 'execute': return id(v.body.run_id) && digest(v.body.plan_sha256) && id(v.body.scope_decision_id) && digest(v.body.scope_decision_sha256) && v.body.consent === 'execute_approved_complete_validation_suite'
      case 'finalize': return id(v.body.run_id) && digest(v.body.plan_sha256) && digest(v.body.authorization_sha256) && digest(v.body.case_events_sha256) && v.body.consent === 'finalize_saved_validation_results_without_reexecution'
      case 'review': return id(v.body.run_id) && digest(v.body.result_sha256) && text(v.body.answers.repair_review, 1, 8000)
        && Object.keys(v.body.answers).length === 1 && (v.body.previous_submission_id === null || id(v.body.previous_submission_id) && v.body.previous_submission_id !== v.body.request_id) && v.body.consent === 'save_validation_repair_interpretation'
    }
  } catch { return false }
}
export function verifyValidationCapture(v: ValidationCapture, l: ValidationList) {
  if (!course(v, l) || !sameValidationCase(v.case, l.case) || !id(v.uuid) || !id(v.artifact_id) || v.artifact.uuid !== v.artifact_id
    || !digest(v.input_snapshot_sha256) || !digest(v.artifact_sha256) || v.documents.length !== 2
    || v.documents.some((s, i) => s.source_id !== l.case.sources[i].id || s.source_sha256 !== l.case.sources[i].sha256 || !s.pages.length)
    || !same(v.artifact.fields.map(f => f.title), l.case.fields.map(f => f.title)) || v.credit_awarded !== false || v.execution_authorized !== false) throw new Error('Different validation capture')
  return v
}
export function verifyValidationSuite(v: ValidationSuiteRecord, l: ValidationList) {
  verifyValidationCapture(v.input_snapshot, l)
  if (!course(v, l) || !sameValidationCase(v.case, l.case) || v.uuid !== v.submission.request_id || !digest(v.suite_record_sha256) || !digest(v.suite_sha256)
    || !validValidationRequest({ action: 'suite', body: v.submission }, l.case) || v.input_snapshot.uuid !== v.submission.input_snapshot_id
    || v.input_snapshot.input_snapshot_sha256 !== v.submission.input_snapshot_sha256 || v.credit_awarded !== false || v.execution_authorized !== false
    || v.module_completion_eligible !== false || v.source_correctness_verified !== false) throw new Error('Different saved test suite')
  return v
}
export function verifyValidationRun(v: ValidationRun, l: ValidationList, nested = false): ValidationRun {
  verifyValidationCapture(v.input_snapshot, l); verifyValidationSuite(v.suite, l)
  if (!course(v, l) || !id(v.run_id) || !digest(v.run_sha256) || !digest(v.plan_sha256) || v.case_sha256 !== l.case.case_sha256
    || v.input_snapshot_id !== v.input_snapshot.uuid || !['original', 'retest'].includes(v.phase)
    || !['prepared', 'executing', 'completed', 'failed', 'uncertain'].includes(v.state) || !digest(v.case_events_sha256)
    || v.case_events.length > 4 || v.case_events.some((e, i) => e.receipt.case_index !== Math.floor(i / 2) || e.receipt.kind !== (i % 2 ? 'case_completed' : 'case_started') || !digest(e.receipt_sha256))
    || v.state === 'completed' && (v.result?.status !== 'completed' || !digest(v.result_sha256) || v.case_events.length !== 4 || !v.result.checks)
    || v.scope_decision && (!course(v.scope_decision, l) || v.scope_decision.uuid !== v.scope_decision_id || v.scope_decision.run_id !== v.run_id || v.scope_decision.plan_sha256 !== v.plan_sha256)
    || v.credit_awarded !== false || v.module_completion_eligible !== false) throw new Error('Different saved suite run')
  if (v.phase === 'original') { if (v.original_run || v.input_snapshot.uuid !== v.suite.input_snapshot.uuid) throw new Error('Different original revision') }
  else {
    if (nested || !v.original_run || v.original_run.phase !== 'original' || v.original_run.suite.suite_record_sha256 !== v.suite.suite_record_sha256
      || v.original_run.input_snapshot.artifact_id !== v.input_snapshot.artifact_id) throw new Error('Different original failure')
    verifyValidationRun(v.original_run, l, true)
  }
  return v
}
export function verifyValidationReview(v: ValidationReview, l: ValidationList) {
  verifyValidationRun(v.run, l)
  if (!course(v, l) || !sameValidationCase(v.case, l.case) || v.uuid !== v.submission.request_id || v.run.run_id !== v.submission.run_id
    || v.run.phase !== 'retest' || v.run.state !== 'completed' || v.run.result_sha256 !== v.submission.result_sha256
    || !validValidationRequest({ action: 'review', body: v.submission }, l.case) || v.credit_awarded !== false || v.module_completion_eligible !== false) throw new Error('Different repair review')
  return v
}
export function verifyValidationResponse(v: ValidationSaved, l: ValidationList, r: ValidationRequest) {
  if (r.action === 'capture') {
    if (!('artifact' in v)) throw new Error('Missing capture')
    verifyValidationCapture(v, l)
    if (v.uuid !== r.body.request_id || v.artifact_id !== r.body.artifact_id) throw new Error('Different capture request')
  } else if (r.action === 'suite' || r.action === 'review') {
    if (!('submission' in v)) throw new Error('Missing submission')
    if (r.action === 'suite' && 'suite_sha256' in v) verifyValidationSuite(v, l)
    else if (r.action === 'review' && 'run' in v) verifyValidationReview(v, l)
    else throw new Error('Different submission kind')
    if (!same(v.submission, r.body)) throw new Error('Different saved answers')
  } else {
    if (!('state' in v)) throw new Error('Missing run')
    verifyValidationRun(v, l)
    if (v.run_id !== (r.action === 'prepare' ? r.body.request_id : r.body.run_id)) throw new Error('Different run identity')
    if (r.action === 'prepare') {
      if (v.input_snapshot.uuid !== r.body.input_snapshot_id || v.input_snapshot.input_snapshot_sha256 !== r.body.input_snapshot_sha256
        || v.suite.uuid !== r.body.suite_id || v.suite.suite_record_sha256 !== r.body.suite_record_sha256
        || (v.original_run?.run_id || null) !== r.body.original_run_id || (v.original_run?.run_sha256 || null) !== r.body.original_run_sha256) throw new Error('Different suite plan')
    } else if (v.plan_sha256 !== r.body.plan_sha256) throw new Error('Different approved plan')
    if (r.action === 'execute' && (v.scope_decision_id !== r.body.scope_decision_id || v.scope_decision_sha256 !== r.body.scope_decision_sha256)) throw new Error('Different execution approval')
    if (r.action === 'finalize' && (v.authorization_sha256 !== r.body.authorization_sha256 || v.case_events_sha256 !== r.body.case_events_sha256)) throw new Error('Different saved case receipts')
  }
  return v
}
