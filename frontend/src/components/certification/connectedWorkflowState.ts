import type { ConnectedCapture, ConnectedCase, ConnectedIdentity, ConnectedList, ConnectedRequest, ConnectedReview, ConnectedRun, ConnectedSaved, ConnectedRecoveryDecision } from '../../types/connectedWorkflow'

export const connectedId = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value)
export const connectedDigest = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value)
export function sameConnectedCase(value: ConnectedCase, expected: ConnectedCase) {
  return value.module_id === 'multi_step' && value.provenance === 'authored_connected_workflow_case_not_execution'
    && connectedDigest(value.case_sha256) && value.case_sha256 === expected.case_sha256
    && value.questions.length === 3 && new Set(value.questions.map(item => item.id)).size === 3
    && value.questions.every(item => ['scope_approval', 'connection_repair', 'source_review'].includes(item.id))
    && (expected.controlled_failure_practice
      ? !!value.controlled_failure_practice && Object.keys(value.controlled_failure_practice).length === Object.keys(expected.controlled_failure_practice).length
        && Object.entries(expected.controlled_failure_practice).every(([key, content]) => value.controlled_failure_practice![key as keyof NonNullable<ConnectedCase['controlled_failure_practice']>] === content)
      : value.controlled_failure_practice === undefined)
}
function sameCourse(value: ConnectedIdentity, listing: ConnectedList) {
  return value.module_id === 'multi_step' && value.enrollment_id === listing.enrollment_id
    && value.course_version === listing.course_version && value.manifest_sha256 === listing.manifest_sha256
}
export function verifyConnectedCapture(value: ConnectedCapture, listing: ConnectedList): ConnectedCapture {
  if (!sameCourse(value, listing) || !connectedId(value.uuid) || !sameConnectedCase(value.case, listing.case)
    || !connectedDigest(value.input_snapshot_sha256) || !connectedDigest(value.artifact_sha256)
    || value.artifact.workflow.id !== value.artifact_id || !Array.isArray(value.artifact.steps)
    || value.documents.length !== 1 || value.documents[0].source_sha256 !== listing.case.source_sha256
    || value.documents[0].assigned_filename !== listing.case.source_filename || !value.documents[0].text.trim()
    || value.execution_authorized !== false || value.credit_awarded !== false) throw new Error('Different captured inputs')
  return value
}
export function verifyConnectedRun(value: ConnectedRun, listing: ConnectedList): ConnectedRun {
  verifyConnectedCapture(value.input_snapshot, listing)
  if (!sameCourse(value, listing) || !connectedId(value.run_id) || value.case_sha256 !== listing.case.case_sha256
    || !connectedDigest(value.plan_sha256) || value.input_snapshot_id !== value.input_snapshot.uuid
    || !['prepared', 'executing', 'completed', 'failed', 'uncertain'].includes(value.state)
    || value.stage_plans.length !== 3 || !Array.isArray(value.stage_events) || value.stage_events.length > 6
    || value.stage_plans.map(item => item.task_type).join() !== 'Extraction,Prompt,Formatter'
    || value.credit_awarded !== false || value.module_completion_eligible !== false
    || (value.execution_purpose !== undefined && !['complete_internal_chain', 'controlled_failure_rehearsal'].includes(value.execution_purpose))
    || (value.execution_purpose === 'controlled_failure_rehearsal' && (!listing.case.controlled_failure_practice || value.state === 'completed' || value.stage_events.length > 4
      || !value.approval_question?.prompt.includes(listing.case.controlled_failure_practice.notice)))
    || (value.state === 'completed' && (value.stage_events.length !== 6 || !connectedDigest(value.result_sha256) || value.result?.status !== 'completed'))
    || (value.scope_decision && (value.scope_decision.uuid !== value.scope_decision_id || value.scope_decision.plan_sha256 !== value.plan_sha256
      || value.scope_decision.run_id !== value.run_id || !sameCourse(value.scope_decision, listing)))) throw new Error('Different saved run')
  return value
}
export function verifyConnectedRecovery(value: ConnectedRecoveryDecision, listing: ConnectedList): ConnectedRecoveryDecision {
  const run = verifyConnectedRun(value.stopped_run, listing), body = value.submission, checks = value.checks
  const expected = [body.failed_stage === 'reason', body.preserve === 'keep_original_run_and_completed_outputs', body.next_action === 'prepare_separate_bounded_run']
  if (!sameCourse(value, listing) || !sameConnectedCase(value.case, listing.case) || !connectedId(value.uuid)
    || !validConnectedRequest({ action: 'recovery', body }, listing.case) || value.uuid !== body.request_id
    || run.run_id !== body.run_id || run.result_sha256 !== body.result_sha256 || run.stage_events_sha256 !== body.stage_events_sha256
    || run.execution_purpose !== 'controlled_failure_rehearsal' || run.state !== 'failed' || run.stage_events.length !== 4
    || run.result?.reason !== 'controlled_training_rejection_before_reasoning_provider' || run.stage_events[1]?.receipt.status !== 'completed'
    || run.stage_events[3]?.receipt.status !== 'failed' || run.stage_events[3]?.receipt.result?.provider_dispatched !== false
    || value.question !== listing.case.controlled_failure_practice?.question
    || checks.checks.length !== 3 || checks.checks.map(c => c.id).join() !== 'first_failed_stage,preserve_successful_work,bounded_recovery_route'
    || checks.checks.some((c, i) => c.supported !== expected[i]) || checks.choices_supported !== expected.every(Boolean)
    || checks.successful_extraction_receipt_sha256 !== run.stage_events[1].receipt_sha256
    || checks.failed_stage_start_sha256 !== run.stage_events[2].receipt_sha256 || checks.controlled_rejection_receipt_sha256 !== run.stage_events[3].receipt_sha256
    || checks.explanation_quality_assessed !== false || checks.execution_authorized !== false || checks.credit_awarded !== false
    || checks.module_completion_eligible !== false || value.credit_awarded !== false || value.module_completion_eligible !== false) throw new Error('Different stopped-run recovery evidence')
  return value
}
export function verifyConnectedReview(value: ConnectedReview, listing: ConnectedList): ConnectedReview {
  verifyConnectedRun(value.original_run, listing); verifyConnectedRun(value.corrected_run, listing)
  if (!sameCourse(value, listing) || !sameConnectedCase(value.case, listing.case) || !connectedId(value.uuid)
    || !validConnectedRequest({ action: 'review', body: value.submission }, listing.case) || value.submission.request_id !== value.uuid
    || value.original_run.run_id !== value.submission.original_run_id || value.corrected_run.run_id !== value.submission.corrected_run_id
    || value.original_run.result_sha256 !== value.submission.original_result_sha256 || value.corrected_run.result_sha256 !== value.submission.corrected_result_sha256
    || value.original_run.state !== 'completed' || value.corrected_run.state !== 'completed'
    || value.credit_awarded !== false || value.module_completion_eligible !== false) throw new Error('Different saved comparison')
  return value
}
export function validConnectedRequest(value: ConnectedRequest | null, definition: ConnectedCase): value is ConnectedRequest {
  if (!value || !value.body || typeof value.body !== 'object') return false
  const body = value.body
  if (!['execute', 'finalize'].includes(value.action) && (!('case_sha256' in body) || body.case_sha256 !== definition.case_sha256 || !('request_id' in body) || !connectedId(body.request_id))) return false
  if (['scope', 'execute', 'finalize'].includes(value.action) && (!('run_id' in body) || !connectedId(body.run_id))) return false
  switch (value.action) {
    case 'capture': return /^[a-f0-9]{24}$/.test(value.body.workflow_id) && value.body.consent === 'capture_connected_workflow_inputs'
    case 'prepare': return connectedId(value.body.input_snapshot_id) && connectedDigest(value.body.input_snapshot_sha256)
      && (value.body.consent === 'prepare_connected_workflow_plan' || value.body.consent === 'prepare_controlled_failure_rehearsal' && !!definition.controlled_failure_practice)
    case 'recovery': return connectedId(value.body.run_id) && connectedDigest(value.body.result_sha256) && connectedDigest(value.body.stage_events_sha256)
      && !!definition.controlled_failure_practice && ['extract', 'reason', 'format', 'unknown'].includes(value.body.failed_stage)
      && ['keep_original_run_and_completed_outputs', 'replace_original_history', 'partial_is_complete'].includes(value.body.preserve)
      && ['prepare_separate_bounded_run', 'resume_in_place', 'restart_all_writes', 'publish_partial'].includes(value.body.next_action)
      && typeof value.body.explanation === 'string' && value.body.explanation.trim().length >= 40 && value.body.explanation.length <= 8000
      && (value.body.previous_submission_id === null || connectedId(value.body.previous_submission_id)) && value.body.consent === 'save_my_actual_stopped_run_recovery_choices'
    case 'scope': return connectedDigest(value.body.plan_sha256) && ['approve', 'hold'].includes(value.body.choice)
      && typeof value.body.reason === 'string' && value.body.reason.trim().length >= 10 && value.body.reason.length <= 4000 && value.body.consent === 'save_connected_workflow_scope_decision'
    case 'execute': return connectedDigest(value.body.plan_sha256) && connectedId(value.body.scope_decision_id) && connectedDigest(value.body.scope_decision_sha256) && value.body.consent === 'execute_approved_connected_workflow'
    case 'finalize': return connectedDigest(value.body.plan_sha256) && connectedDigest(value.body.authorization_sha256) && connectedDigest(value.body.stage_events_sha256) && value.body.consent === 'finalize_saved_connected_results_without_reexecution'
    case 'review': return connectedId(value.body.original_run_id) && connectedId(value.body.corrected_run_id) && value.body.original_run_id !== value.body.corrected_run_id
      && connectedDigest(value.body.original_result_sha256) && connectedDigest(value.body.corrected_result_sha256)
      && (value.body.previous_submission_id === null || connectedId(value.body.previous_submission_id))
      && !!value.body.answers && Object.keys(value.body.answers).length === 2
      && ['connection_repair', 'source_review'].every(key => { const answer = value.body.answers[key as keyof typeof value.body.answers]; return typeof answer === 'string' && !!answer.trim() && answer.length <= 8000 })
      && value.body.consent === 'save_connected_workflow_result_review'
    default: return false
  }
}
export function verifyConnectedResponse(saved: ConnectedSaved, listing: ConnectedList, request: ConnectedRequest) {
  if (request.action === 'capture') {
    const value = verifyConnectedCapture(saved as ConnectedCapture, listing)
    if (value.uuid !== request.body.request_id || value.artifact_id !== request.body.workflow_id) throw new Error('Different capture request')
  } else if (request.action === 'recovery') {
    const value = verifyConnectedRecovery(saved as ConnectedRecoveryDecision, listing)
    if (Object.entries(request.body).some(([key, expected]) => value.submission[key as keyof typeof value.submission] !== expected)) throw new Error('Different recovery choices')
  } else if (request.action === 'review') {
    const value = verifyConnectedReview(saved as ConnectedReview, listing)
    if (Object.entries(request.body).some(([key, expected]) => key === 'answers'
      ? Object.entries(request.body.answers).some(([id, answer]) => value.submission.answers[id as keyof typeof value.submission.answers] !== answer)
      : value.submission[key as keyof typeof value.submission] !== expected)) throw new Error('Different comparison request')
  } else {
    const value = verifyConnectedRun(saved as ConnectedRun, listing)
    if (request.action === 'prepare') {
      if (value.run_id !== request.body.request_id || value.input_snapshot_id !== request.body.input_snapshot_id || value.input_snapshot.input_snapshot_sha256 !== request.body.input_snapshot_sha256) throw new Error('Different plan')
      if ((value.execution_purpose === 'controlled_failure_rehearsal') !== (request.body.consent === 'prepare_controlled_failure_rehearsal')) throw new Error('Different execution purpose')
    } else if (value.run_id !== request.body.run_id || value.plan_sha256 !== request.body.plan_sha256) throw new Error('Different run request')
    if (request.action === 'execute' && (value.scope_decision_id !== request.body.scope_decision_id || value.scope_decision_sha256 !== request.body.scope_decision_sha256)) throw new Error('Scope changed; inspect the original request')
    if (request.action === 'finalize' && (value.authorization_sha256 !== request.body.authorization_sha256 || value.stage_events_sha256 !== request.body.stage_events_sha256)) throw new Error('Stage evidence changed')
  }
  return saved
}
