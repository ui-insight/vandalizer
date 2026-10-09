import type { BatchCase, BatchCapture, BatchIdentity, BatchList, BatchRequest, BatchReview, BatchRun, BatchSaved } from '../../types/batchAssessment'
import { connectedId as id, connectedDigest as digest } from './connectedWorkflowState'
import { sameOutputJson as same } from './outputWorkflowState'
const text = (v: unknown, min: number, max: number): v is string => typeof v === 'string' && v.trim().length >= min && v.length <= max
const course = (v: BatchIdentity, l: BatchList) => v.module_id === 'batch_processing' && v.enrollment_id === l.enrollment_id && v.course_version === l.course_version && v.manifest_sha256 === l.manifest_sha256
const pair = (i: string | null, d: string | null) => i === null && d === null || id(i) && digest(d)
export const sameBatchCase = (v: BatchCase, d: BatchCase) => v.module_id === 'batch_processing' && v.provenance === 'authored_batch_assignment_not_pilot_coverage_or_recovery_evidence'
  && digest(v.case_sha256) && v.case_sha256 === d.case_sha256 && same(v.sources, d.sources) && same(v.fields, d.fields) && same(v.questions, d.questions)
  && same(v.pilot_source_ids, d.pilot_source_ids) && v.controlled_failure_source_id === d.controlled_failure_source_id
export function validBatchRequest(v: BatchRequest | null, d: BatchCase): v is BatchRequest {
  try {
    if (!v || !v.body || !['capture', 'prepare', 'scope', 'execute', 'finalize', 'review'].includes(v.action)) return false
    const b = v.body
    if ('request_id' in b && !id(b.request_id)) return false
    if (!['execute', 'finalize'].includes(v.action) && (!('case_sha256' in b) || b.case_sha256 !== d.case_sha256)) return false
    switch (v.action) {
      case 'capture': return id(v.body.artifact_id) && v.body.consent === 'capture_batch_extraction_and_complete_sources'
      case 'prepare': return id(v.body.input_snapshot_id) && digest(v.body.input_snapshot_sha256) && v.body.consent === 'prepare_bounded_batch_action'
        && pair(v.body.parent_run_id, v.body.parent_run_sha256) && pair(v.body.previous_retry_id, v.body.previous_retry_sha256)
        && v.body.request_id !== v.body.parent_run_id && v.body.request_id !== v.body.previous_retry_id
        && (v.body.phase === 'pilot' ? v.body.parent_run_id === null && v.body.failed_source_id === null && v.body.previous_retry_id === null
          : v.body.phase === 'batch' ? id(v.body.parent_run_id) && v.body.failed_source_id === null && v.body.previous_retry_id === null
            : v.body.phase === 'retry' && id(v.body.parent_run_id) && d.sources.some(s => s.id === v.body.failed_source_id))
      case 'scope': return id(v.body.run_id) && digest(v.body.plan_sha256) && ['approve', 'hold'].includes(v.body.choice) && text(v.body.reason, 10, 4000) && v.body.consent === 'save_bounded_batch_scope_decision'
      case 'execute': return id(v.body.run_id) && digest(v.body.plan_sha256) && id(v.body.scope_decision_id) && digest(v.body.scope_decision_sha256) && v.body.consent === 'execute_approved_bounded_batch_action'
      case 'finalize': return id(v.body.run_id) && digest(v.body.plan_sha256) && digest(v.body.authorization_sha256) && digest(v.body.item_events_sha256) && v.body.consent === 'finalize_saved_batch_results_without_reexecution'
      case 'review': return id(v.body.run_id) && digest(v.body.result_sha256) && text(v.body.answers.batch_review, 1, 8000)
        && Object.keys(v.body.answers).length === 1 && v.body.retries.length >= 1 && v.body.retries.length <= 3
        && v.body.retries.every(r => id(r.run_id) && digest(r.result_sha256) && r.run_id !== v.body.run_id) && new Set(v.body.retries.map(r => r.run_id)).size === v.body.retries.length
        && (v.body.previous_submission_id === null || id(v.body.previous_submission_id) && v.body.previous_submission_id !== v.body.request_id) && v.body.consent === 'save_batch_recovery_interpretation'
    }
  } catch { return false }
}
export function verifyBatchCapture(v: BatchCapture, l: BatchList) {
  if (!course(v, l) || !sameBatchCase(v.case, l.case) || !id(v.uuid) || !id(v.artifact_id) || v.artifact.uuid !== v.artifact_id
    || !digest(v.input_snapshot_sha256) || !digest(v.artifact_sha256) || v.documents.length !== 3 || new Set(v.documents.map(s => s.document_id)).size !== 3
    || v.documents.some((s, i) => s.source_id !== l.case.sources[i].id || s.source_sha256 !== l.case.sources[i].sha256 || !id(s.document_id) || !s.pages.length)
    || !same(v.artifact.fields.map(f => f.title), l.case.fields.map(f => f.title)) || v.credit_awarded !== false || v.execution_authorized !== false) throw new Error('Different batch capture')
  return v
}
export function verifyBatchRun(v: BatchRun, l: BatchList, depth = 0): BatchRun {
  if (depth > 8) throw new Error('Recovery ancestry exceeds its limit')
  verifyBatchCapture(v.input_snapshot, l)
  const sources = v.phase === 'pilot' ? l.case.pilot_source_ids : v.phase === 'batch' ? l.case.sources.map(s => s.id) : [v.failed_source_id]
  if (!course(v, l) || !id(v.run_id) || !id(v.batch_id) || !digest(v.run_sha256) || !digest(v.plan_sha256) || v.case_sha256 !== l.case.case_sha256
    || v.input_snapshot_id !== v.input_snapshot.uuid || !['pilot', 'batch', 'retry'].includes(v.phase) || !same(sources, v.source_ids)
    || !['prepared', 'executing', 'completed', 'failed', 'uncertain'].includes(v.state) || !digest(v.item_events_sha256)
    || v.item_events.length > 2 * sources.length || v.item_events.some((e, i) => e.receipt.item_index !== Math.floor(i / 2) || e.receipt.kind !== (i % 2 ? 'item_completed' : 'item_started') || !digest(e.receipt_sha256))
    || v.state === 'completed' && (v.result?.status !== 'completed' || !digest(v.result_sha256) || v.item_events.length !== 2 * sources.length || !v.result.checks
      || !same(v.result.checks.source_ids, v.source_ids) || !same(v.result.item_results?.map(r => r.source_id), v.source_ids)
      || !same(v.result.item_results, v.item_events.filter((_, i) => i % 2).map(e => e.receipt.result)))
    || v.scope_decision && (!course(v.scope_decision, l) || v.scope_decision.uuid !== v.scope_decision_id || v.scope_decision.run_id !== v.run_id || v.scope_decision.plan_sha256 !== v.plan_sha256)
    || v.credit_awarded !== false || v.module_completion_eligible !== false) throw new Error('Different saved batch run')
  if (v.phase === 'pilot') { if (v.parent_run || v.previous_retry || v.failed_source_id || v.batch_id !== v.run_id) throw new Error('Different pilot') }
  else {
    if (!v.parent_run || v.parent_run.state !== 'completed' || v.parent_run.input_snapshot.input_snapshot_sha256 !== v.input_snapshot.input_snapshot_sha256
      || !same(v.parent_run.model_names, v.model_names)) throw new Error('Different original capture or models')
    verifyBatchRun(v.parent_run, l, depth + 1)
    if (v.phase === 'batch') {
      if (v.parent_run.phase !== 'pilot' || !v.parent_run.result?.checks?.all_values_source_supported || v.previous_retry || v.failed_source_id || v.batch_id !== v.run_id) throw new Error('Different checked pilot')
    } else {
      if (v.parent_run.phase !== 'batch' || v.batch_id !== v.parent_run.run_id || !v.parent_run.result?.item_results?.some(r => r.source_id === v.failed_source_id && r.status === 'failed')) throw new Error('Different confirmed failure')
      if (v.previous_retry) {
        verifyBatchRun(v.previous_retry, l, depth + 1)
        if (v.previous_retry.phase !== 'retry' || v.previous_retry.state !== 'completed' || v.previous_retry.batch_id !== v.batch_id || v.previous_retry.failed_source_id !== v.failed_source_id
          || v.previous_retry.result?.item_results?.[0].status !== 'failed') throw new Error('Different previous retry')
      }
    }
  }
  return v
}
export function verifyBatchReview(v: BatchReview, l: BatchList) {
  verifyBatchRun(v.run, l)
  for (const retry of v.retries) verifyBatchRun(retry, l)
  if (!course(v, l) || !sameBatchCase(v.case, l.case) || v.uuid !== v.submission.request_id || v.run.run_id !== v.submission.run_id
    || v.run.phase !== 'batch' || v.run.state !== 'completed' || v.run.result_sha256 !== v.submission.result_sha256
    || !validBatchRequest({ action: 'review', body: v.submission }, l.case) || v.credit_awarded !== false || v.module_completion_eligible !== false
    || !same(v.retries.map(r => ({ run_id: r.run_id, result_sha256: r.result_sha256 })), v.submission.retries)
    || v.retries.some(r => r.state !== 'completed' || r.phase !== 'retry' || r.parent_run?.run_sha256 !== v.run.run_sha256)
    || v.reconciliation.batch_id !== v.run.run_id || new Set(v.retries.map(r => r.failed_source_id)).size !== v.retries.length) throw new Error('Different batch review')
  return v
}
export function verifyBatchResponse(v: BatchSaved, l: BatchList, r: BatchRequest) {
  if (r.action === 'capture') {
    if (!('artifact' in v)) throw new Error('Missing capture')
    verifyBatchCapture(v, l)
    if (v.uuid !== r.body.request_id || v.artifact_id !== r.body.artifact_id) throw new Error('Different capture request')
  } else if (r.action === 'review') {
    if (!('submission' in v)) throw new Error('Missing interpretation')
    verifyBatchReview(v, l)
    if (!same(v.submission, r.body)) throw new Error('Different saved answers')
  } else {
    if (!('state' in v)) throw new Error('Missing run')
    verifyBatchRun(v, l)
    if (v.run_id !== (r.action === 'prepare' ? r.body.request_id : r.body.run_id)) throw new Error('Different run identity')
    if (r.action === 'prepare') {
      if (v.input_snapshot.uuid !== r.body.input_snapshot_id || v.input_snapshot.input_snapshot_sha256 !== r.body.input_snapshot_sha256 || v.phase !== r.body.phase
        || v.failed_source_id !== r.body.failed_source_id || (v.parent_run?.run_id || null) !== r.body.parent_run_id || (v.parent_run?.run_sha256 || null) !== r.body.parent_run_sha256
        || (v.previous_retry?.run_id || null) !== r.body.previous_retry_id || (v.previous_retry?.run_sha256 || null) !== r.body.previous_retry_sha256) throw new Error('Different bounded batch plan')
    } else if (v.plan_sha256 !== r.body.plan_sha256) throw new Error('Different approved plan')
    if (r.action === 'execute' && (v.scope_decision_id !== r.body.scope_decision_id || v.scope_decision_sha256 !== r.body.scope_decision_sha256)) throw new Error('Different execution approval')
    if (r.action === 'finalize' && (v.authorization_sha256 !== r.body.authorization_sha256 || v.item_events_sha256 !== r.body.item_events_sha256)) throw new Error('Different saved item receipts')
  }
  return v
}
