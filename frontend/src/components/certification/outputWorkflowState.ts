import type { OutputArtifacts, OutputCapture, OutputCase, OutputHandoff, OutputIdentity, OutputInspection, OutputList, OutputRequest, OutputReview, OutputRun, OutputSaved } from '../../types/outputWorkflow'
import { connectedId as id, connectedDigest as digest } from './connectedWorkflowState'
const text = (value: unknown, min: number, max: number): value is string => typeof value === 'string' && value.trim().length >= min && value.length <= max
const sameCourse = (value: OutputIdentity, listing: OutputList) => value.module_id === 'output_delivery' && value.enrollment_id === listing.enrollment_id
  && value.course_version === listing.course_version && value.manifest_sha256 === listing.manifest_sha256
export const sameOutputCase = (value: OutputCase, expected: OutputCase) => value.module_id === 'output_delivery'
  && value.provenance === 'authored_output_handoff_case_not_generation_or_delivery' && digest(value.case_sha256) && value.case_sha256 === expected.case_sha256
  && value.source_sha256 === expected.source_sha256 && value.questions.length === 3 && new Set(value.questions.map(q => q.id)).size === 3
  && value.questions.every(q => ['artifact_review', 'release_decision', 'delivery_review'].includes(q.id))
  && value.destination.id === 'private_training_inbox' && value.destination.audience === 'enrolled_learner_only' && value.destination.data_scope === 'approved_generated_files_only'
export function sameOutputJson(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return false
  const left = a as Record<string, unknown>, right = b as Record<string, unknown>
  return Object.keys(left).length === Object.keys(right).length && Object.keys(left).every(key => Object.hasOwn(right, key) && sameOutputJson(left[key], right[key]))
}
export function validOutputRequest(request: OutputRequest | null, definition: OutputCase): request is OutputRequest {
  try { return valid(request, definition) } catch { return false }
}
function valid(value: OutputRequest | null, definition: OutputCase): value is OutputRequest {
  if (!value || !value.body || typeof value.body !== 'object') return false
  const body = value.body
  if (!['execute', 'finalize'].includes(value.action) && (!('request_id' in body) || !id(body.request_id))) return false
  if ('case_sha256' in body && body.case_sha256 !== definition.case_sha256) return false
  switch (value.action) {
    case 'capture': return /^[a-f0-9]{24}$/.test(value.body.workflow_id) && value.body.consent === 'capture_output_workflow_inputs'
    case 'prepare': return id(value.body.input_snapshot_id) && digest(value.body.input_snapshot_sha256) && value.body.consent === 'prepare_output_workflow_plan'
    case 'scope': return id(value.body.run_id) && digest(value.body.plan_sha256) && ['approve', 'hold'].includes(value.body.choice) && text(value.body.reason, 10, 4000) && value.body.consent === 'save_output_workflow_scope_decision'
    case 'execute': return id(value.body.run_id) && digest(value.body.plan_sha256) && id(value.body.scope_decision_id) && digest(value.body.scope_decision_sha256) && value.body.consent === 'execute_approved_output_workflow'
    case 'finalize': return id(value.body.run_id) && digest(value.body.plan_sha256) && digest(value.body.authorization_sha256) && digest(value.body.stage_events_sha256) && value.body.consent === 'finalize_saved_output_results_without_reexecution'
    case 'inspection': return id(value.body.run_id) && digest(value.body.result_sha256) && digest(value.body.artifacts_sha256) && digest(value.body.bundle_sha256)
      && typeof value.body.bundle_opened === 'boolean' && ['approve', 'hold'].includes(value.body.choice) && value.body.destination_id === 'private_training_inbox'
      && value.body.audience === 'enrolled_learner_only' && value.body.data_scope === 'approved_generated_files_only'
      && Array.isArray(value.body.file_inspections) && value.body.file_inspections.length > 0 && value.body.file_inspections.length <= 8
      && new Set(value.body.file_inspections.map(file => file.sha256)).size === value.body.file_inspections.length
      && value.body.file_inspections.every(file => digest(file.sha256) && typeof file.opened === 'boolean' && ['usable', 'needs_repair', 'unresolved'].includes(file.judgment) && text(file.observations, 10, 8000))
      && (value.body.choice !== 'approve' || value.body.bundle_opened && value.body.file_inspections.every(file => file.opened && file.judgment === 'usable'))
      && Object.keys(value.body.answers).length === 2 && text(value.body.answers.artifact_review, 10, 8000) && text(value.body.answers.release_decision, 10, 8000)
      && value.body.consent === 'save_exact_output_inspection_and_release_choice'
    case 'handoff': return id(value.body.run_id) && digest(value.body.result_sha256) && id(value.body.review_id) && digest(value.body.review_sha256)
      && digest(value.body.artifacts_sha256) && value.body.destination_id === 'private_training_inbox'
      && (value.body.action === 'attempt' ? value.body.previous_failed_id === null && value.body.previous_failed_sha256 === null && value.body.consent === 'attempt_approved_private_training_handoff'
        : value.body.action === 'retry_failed_handoff' && id(value.body.previous_failed_id) && value.body.previous_failed_id !== value.body.request_id && digest(value.body.previous_failed_sha256) && value.body.consent === 'retry_only_failed_private_training_handoff')
    case 'review': return id(value.body.file_review_id) && digest(value.body.file_review_sha256) && id(value.body.handoff_id) && digest(value.body.handoff_sha256)
      && text(value.body.delivery_review, 10, 8000) && (value.body.previous_submission_id === null || id(value.body.previous_submission_id) && value.body.previous_submission_id !== value.body.request_id)
      && value.body.consent === 'save_output_delivery_interpretation'
    default: return false
  }
}
export function verifyOutputArtifacts(value: OutputArtifacts) {
  if (!digest(value.artifacts_sha256) || value.files.length < 1 || value.files.length > 8 || new Set(value.files.map(file => file.sha256)).size !== value.files.length
    || !digest(value.download.sha256) || !value.download.filename || !Number.isInteger(value.download.size_bytes)
    || value.files.some(file => !digest(file.sha256) || !file.filename || !Number.isInteger(file.size_bytes) || file.size_bytes < 0 || file.inspection.source_correctness_verified !== false || file.inspection.visual_inspection_required !== true)
    || value.learner_inspection_required !== true || value.release_authorized !== false || value.delivery_confirmed !== false || value.credit_awarded !== false
    || value.all_required_files_parseable !== (value.files.length === 2 && new Set(value.files.map(file => file.file_type)).size === 2 && value.files.every(file => ['pdf', 'csv'].includes(file.file_type) && file.inspection.parseable_and_fields_present))) throw new Error('Different saved files')
  return value
}
export function verifyOutputCapture(value: OutputCapture, listing: OutputList) {
  if (!sameCourse(value, listing) || !sameOutputCase(value.case, listing.case) || !id(value.uuid) || !digest(value.input_snapshot_sha256)
    || !digest(value.artifact_sha256) || value.artifact.workflow.id !== value.artifact_id || !Array.isArray(value.artifact.steps)
    || value.documents.length !== 1 || value.documents[0].source_sha256 !== listing.case.source_sha256 || !value.documents[0].text.trim()
    || value.execution_authorized !== false || value.credit_awarded !== false) throw new Error('Different output capture')
  return value
}
export function verifyOutputRun(value: OutputRun, listing: OutputList) {
  verifyOutputCapture(value.input_snapshot, listing)
  if (!sameCourse(value, listing) || !id(value.run_id) || !digest(value.plan_sha256) || value.case_sha256 !== listing.case.case_sha256
    || value.input_snapshot_id !== value.input_snapshot.uuid || value.stage_plans.length !== 4 || !Array.isArray(value.stage_events) || value.stage_events.length > 8
    || !['prepared', 'executing', 'completed', 'failed', 'uncertain'].includes(value.state)
    || value.stage_events.some((event, index) => event.receipt.stage_index !== Math.floor(index / 2) || event.receipt.kind !== (index % 2 === 0 ? 'stage_started' : 'stage_completed') || !digest(event.receipt_sha256))
    || value.state === 'completed' && (value.stage_events.length !== 8 || value.stage_events.some(e => e.receipt.kind === 'stage_completed' && e.receipt.status !== 'completed') || value.result?.status !== 'completed' || !digest(value.result_sha256) || !value.result.generated_artifacts)
    || value.scope_decision && (!sameCourse(value.scope_decision, listing) || value.scope_decision.uuid !== value.scope_decision_id || value.scope_decision.run_id !== value.run_id || value.scope_decision.plan_sha256 !== value.plan_sha256)
    || value.credit_awarded !== false || value.module_completion_eligible !== false) throw new Error('Different output run')
  if (value.result?.generated_artifacts) verifyOutputArtifacts(value.result.generated_artifacts)
  return value
}
export function verifyOutputInspection(value: OutputInspection, listing: OutputList) {
  verifyOutputRun(value.run, listing)
  const files = value.run.result?.generated_artifacts
  if (!sameCourse(value, listing) || !sameOutputCase(value.case, listing.case) || !id(value.uuid) || !digest(value.review_sha256)
    || !validOutputRequest({ action: 'inspection', body: value.submission }, listing.case) || value.submission.request_id !== value.uuid
    || value.run.run_id !== value.submission.run_id || value.run.result_sha256 !== value.submission.result_sha256 || value.run.state !== 'completed'
    || !files || files.artifacts_sha256 !== value.submission.artifacts_sha256 || files.download.sha256 !== value.submission.bundle_sha256
    || value.submission.file_inspections.length !== files.files.length || value.submission.file_inspections.some(file => !files.files.some(actual => actual.sha256 === file.sha256))
    || value.submission.choice === 'approve' && !files.all_required_files_parseable || value.credit_awarded !== false || value.module_completion_eligible !== false) throw new Error('Different output inspection')
  return value
}
export function verifyOutputHandoff(value: OutputHandoff, listing: OutputList) {
  if (!sameCourse(value, listing) || !id(value.uuid) || !digest(value.handoff_sha256) || value.submission.request_id !== value.uuid || value.submission.run_id !== value.run_id
    || !validOutputRequest({ action: 'handoff', body: value.submission }, listing.case) || value.destination.id !== 'private_training_inbox'
    || value.destination.audience !== 'enrolled_learner_only' || value.destination.data_scope !== 'approved_generated_files_only'
    || value.external_delivery !== false || value.credit_awarded !== false) throw new Error('Different private handoff')
  if (value.status === 'failed') {
    if (value.submission.action !== 'attempt' || value.destination_written !== false || value.destination_copy !== null || value.previous_failed_receipt !== null) throw new Error('Different failed handoff')
  } else if (value.status === 'delivered') {
    if (value.destination_written !== true || !value.destination_copy || !value.previous_failed_receipt || value.previous_failed_receipt.status !== 'failed') throw new Error('Missing private copy')
    verifyOutputArtifacts(value.destination_copy); verifyOutputHandoff(value.previous_failed_receipt, listing)
    if (value.destination_copy.artifacts_sha256 !== value.submission.artifacts_sha256 || value.previous_failed_receipt.uuid !== value.submission.previous_failed_id || value.previous_failed_receipt.handoff_sha256 !== value.submission.previous_failed_sha256) throw new Error('Different retry evidence')
  } else throw new Error('Unknown handoff status')
  return value
}
export function verifyOutputReview(value: OutputReview, listing: OutputList) {
  verifyOutputInspection(value.file_review, listing); verifyOutputHandoff(value.handoff, listing)
  if (!sameCourse(value, listing) || !sameOutputCase(value.case, listing.case) || !id(value.uuid) || value.submission.request_id !== value.uuid
    || !validOutputRequest({ action: 'review', body: value.submission }, listing.case)
    || value.file_review.uuid !== value.submission.file_review_id || value.file_review.review_sha256 !== value.submission.file_review_sha256
    || value.handoff.uuid !== value.submission.handoff_id || value.handoff.handoff_sha256 !== value.submission.handoff_sha256
    || value.handoff.submission.review_id !== value.file_review.uuid || value.handoff.submission.review_sha256 !== value.file_review.review_sha256
    || value.credit_awarded !== false || value.module_completion_eligible !== false) throw new Error('Different output review')
  return value
}
export function verifyOutputResponse(saved: OutputSaved, listing: OutputList, request: OutputRequest) {
  if (request.action === 'capture') {
    const value = verifyOutputCapture(saved as OutputCapture, listing)
    if (value.uuid !== request.body.request_id || value.artifact_id !== request.body.workflow_id) throw new Error('Different capture request')
  } else if (request.action === 'inspection' || request.action === 'handoff' || request.action === 'review') {
    const value = request.action === 'inspection' ? verifyOutputInspection(saved as OutputInspection, listing)
      : request.action === 'handoff' ? verifyOutputHandoff(saved as OutputHandoff, listing) : verifyOutputReview(saved as OutputReview, listing)
    if (!sameOutputJson(value.submission, request.body)) throw new Error('Different saved request')
  } else {
    const value = verifyOutputRun(saved as OutputRun, listing)
    if (request.action === 'prepare') {
      if (value.run_id !== request.body.request_id || value.input_snapshot_id !== request.body.input_snapshot_id || value.input_snapshot.input_snapshot_sha256 !== request.body.input_snapshot_sha256) throw new Error('Different plan')
    } else if (value.run_id !== request.body.run_id || value.plan_sha256 !== request.body.plan_sha256) throw new Error('Different run')
    if (request.action === 'execute' && (value.scope_decision_id !== request.body.scope_decision_id || value.scope_decision_sha256 !== request.body.scope_decision_sha256)) throw new Error('Changed scope')
    if (request.action === 'finalize' && (value.authorization_sha256 !== request.body.authorization_sha256 || value.stage_events_sha256 !== request.body.stage_events_sha256)) throw new Error('Changed saved results')
    if (request.action === 'scope' && value.scope_decision_id === request.body.request_id && !sameOutputJson(value.scope_decision?.submission, request.body)) throw new Error('Different scope request')
  }
  return saved
}
