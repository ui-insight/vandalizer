import type { GovernanceCase, GovernanceList, GovernanceRequest, GovernanceView, GovernanceCapture, GovernanceRun, GovernanceRecord, GovernanceKind } from '../../types/governanceAssessment'
import { connectedId as id, connectedDigest as digest } from './connectedWorkflowState'
import { sameOutputJson as same } from './outputWorkflowState'
export const governanceId = () => crypto.randomUUID().replaceAll('-', '')
export const governanceKinds: GovernanceKind[] = ['capture', 'correction', 'run', 'scope', 'finding', 'memo', 'release', 'handoff', 'review']
export const governanceLabels: Record<GovernanceKind, string> = { capture: 'Captured extraction', correction: 'Scope correction', run: 'Extraction run', scope: 'Execution approval or hold', finding: 'Original source finding', memo: 'Accountable memo', release: 'Memo release or hold', handoff: 'Private handoff receipt', review: 'Supervision interpretation' }
const kinds = { correction: 'governance_scope_correction', scope: 'bounded_governance_execution', finding: 'governance_original_source_finding', memo: 'governance_accountable_memo', release: 'governance_memo_release_choice', handoff: 'governance_private_training_handoff', review: 'governance_final_supervision_review' }
const text = (v: unknown, min = 1, max = 8000): v is string => typeof v === 'string' && v.trim().length >= min && v.length <= max
export const sameGovernanceCase = (a: GovernanceCase, b: GovernanceCase) => a.module_id === 'governance' && a.provenance === 'authored_supervision_case_not_learner_approval_or_delivery' && digest(a.case_sha256) && same(a, b)
const course = (v: GovernanceView['value'], l: GovernanceList) => v.module_id === 'governance' && v.enrollment_id === l.enrollment_id && v.course_version === l.course_version && v.manifest_sha256 === l.manifest_sha256
const pair = (i: unknown, d: unknown) => i === null && d === null || id(i) && digest(d)
export function validGovernanceRequest(r: GovernanceRequest | null, definition: GovernanceCase): r is GovernanceRequest {
  try {
    if (!r || !r.body) return false
    const b = r.body
    if ('request_id' in b && !id(b.request_id) || 'case_sha256' in b && b.case_sha256 !== definition.case_sha256) return false
    if ('run_id' in b && !id(b.run_id)) return false
    if ('memo_id' in b && (!id(b.memo_id) || !digest(b.memo_sha256) || !digest(b.file_sha256))) return false
    switch (r.action) {
      case 'capture': return id(r.body.artifact_id) && r.body.consent === 'capture_governance_extraction_and_complete_sources'
      case 'correction': return id(r.body.input_snapshot_id) && digest(r.body.input_snapshot_sha256) && r.body.source_document_ids.length === 2
        && new Set(r.body.source_document_ids).size === 2 && r.body.source_document_ids.every(id) && text(r.body.reason, 40)
        && r.body.choice === 'reject_broad_proposal' && r.body.destination_id === 'private_training_inbox' && r.body.audience === 'enrolled_learner_only'
        && r.body.ongoing_automation === 'keep_disabled' && r.body.consent === 'save_my_corrected_capstone_scope_without_execution'
      case 'prepare': return id(r.body.input_snapshot_id) && digest(r.body.input_snapshot_sha256) && id(r.body.scope_correction_id) && digest(r.body.scope_correction_sha256)
        && pair(r.body.source_finding_id, r.body.source_finding_sha256) && (r.body.source_finding_id === null ? r.body.consent === 'prepare_original_bounded_capstone_extraction' : r.body.consent === 'prepare_repaired_bounded_capstone_extraction')
      case 'scope': return digest(r.body.plan_sha256) && ['approve', 'hold'].includes(r.body.choice) && text(r.body.reason, 10, 4000) && r.body.consent === 'save_bounded_governance_execution_decision'
      case 'execute': return digest(r.body.plan_sha256) && id(r.body.scope_decision_id) && digest(r.body.scope_decision_sha256) && r.body.consent === 'execute_approved_bounded_capstone_extraction'
      case 'finalize': return digest(r.body.plan_sha256) && digest(r.body.authorization_sha256) && digest(r.body.extraction_events_sha256) && r.body.consent === 'finalize_saved_governance_results_without_reexecution'
      case 'finding': return digest(r.body.result_sha256) && r.body.field === 'Funds Obligated to Date' && text(r.body.observed_value, 1, 2000) && text(r.body.explanation, 40)
        && r.body.source_references.length >= 2 && r.body.source_references.length <= 6 && new Set(r.body.source_references.map(q => q.source_id)).size === 2
        && r.body.source_references.every(q => ['award', 'amendment'].includes(q.source_id) && Number.isInteger(q.page) && q.page > 0 && q.page <= 100 && text(q.quote, 10, 2000)) && r.body.consent === 'save_my_original_source_finding_before_repair'
      case 'memo': return digest(r.body.result_sha256) && text(r.body.owner_user_id, 1, 300) && [r.body.intended_use, r.body.supported_inputs, r.body.limitations, r.body.review_route].every(t => text(t, 20, 5000)) && r.body.consent === 'save_checked_capstone_memo_without_release'
      case 'release': return typeof r.body.opened === 'boolean' && ['approve', 'hold'].includes(r.body.choice) && (r.body.choice !== 'approve' || r.body.opened)
        && text(r.body.reason, 40) && r.body.destination_id === 'private_training_inbox' && r.body.audience === 'enrolled_learner_only' && r.body.consent === 'save_my_exact_capstone_memo_release_choice'
      case 'handoff': return id(r.body.release_id) && digest(r.body.release_sha256) && r.body.destination_id === 'private_training_inbox'
        && pair(r.body.previous_failed_id, r.body.previous_failed_sha256) && r.body.request_id !== r.body.previous_failed_id
        && (r.body.action === 'attempt' ? r.body.previous_failed_id === null && r.body.consent === 'attempt_approved_private_capstone_handoff'
          : r.body.action === 'retry_failed_handoff' && id(r.body.previous_failed_id) && r.body.consent === 'retry_only_failed_private_capstone_handoff')
      case 'review': return id(r.body.handoff_id) && digest(r.body.handoff_sha256) && text(r.body.final_supervision, 40)
        && (r.body.previous_submission_id === null || id(r.body.previous_submission_id) && r.body.previous_submission_id !== r.body.request_id) && r.body.consent === 'save_my_capstone_supervision_interpretation'
      default: return false
    }
  } catch { return false }
}
function capture(v: GovernanceCapture, l: GovernanceList) {
  if (!course(v, l) || !sameGovernanceCase(v.case, l.case) || !id(v.uuid) || !id(v.artifact_id) || v.artifact.uuid !== v.artifact_id
    || !digest(v.input_snapshot_sha256) || !digest(v.artifact_sha256) || v.documents.length !== 2 || new Set(v.documents.map(s => s.document_id)).size !== 2
    || v.documents.some((s, i) => s.source_id !== l.case.sources[i].id || s.source_sha256 !== l.case.sources[i].sha256 || !id(s.document_id) || !s.pages.length)
    || !same(v.artifact.fields.map(f => f.title), l.case.fields.map(f => f.title)) || v.credit_awarded !== false || v.execution_authorized !== false) throw new Error('Different original capstone capture')
}
function run(v: GovernanceRun, l: GovernanceList, depth: number) {
  capture(v.input_snapshot, l)
  verifyGovernanceView({ kind: 'correction', value: v.scope_correction }, l, depth + 1)
  if (!course(v, l) || !id(v.run_id) || !digest(v.run_sha256) || !digest(v.plan_sha256) || v.case_sha256 !== l.case.case_sha256 || v.input_snapshot_id !== v.input_snapshot.uuid
    || !['original', 'repair'].includes(v.phase) || !['prepared', 'executing', 'completed', 'failed', 'uncertain'].includes(v.state)
    || !digest(v.extraction_events_sha256) || v.extraction_events.length > 2 || v.extraction_events.some((e, i) => e.receipt.extraction_index !== 0 || e.receipt.kind !== (i ? 'extraction_completed' : 'extraction_started') || !digest(e.receipt_sha256))
    || v.state === 'completed' && (v.result?.status !== 'completed' || !digest(v.result_sha256) || v.extraction_events.length !== 2 || !v.result.checks || !same(v.result.extraction, v.extraction_events[1].receipt.result))
    || v.credit_awarded !== false || v.module_completion_eligible !== false) throw new Error('Different capstone run')
  if (v.scope_decision) {
    verifyGovernanceView({ kind: 'scope', value: v.scope_decision }, l, depth + 1, true)
    if (v.scope_decision.uuid !== v.scope_decision_id || v.scope_decision.run_id !== v.run_id || v.scope_decision.plan_sha256 !== v.plan_sha256) throw new Error('Different execution approval')
  }
  if (v.phase === 'original') {
    if (v.source_finding || v.original_run_id || v.original_run_sha256 || v.changed_fields.length || v.scope_correction.input_snapshot.input_snapshot_sha256 !== v.input_snapshot.input_snapshot_sha256) throw new Error('Different original scope')
  } else {
    if (!v.source_finding) throw new Error('Missing original finding')
    verifyGovernanceView({ kind: 'finding', value: v.source_finding }, l, depth + 1)
    const original = v.source_finding.run
    if (original.run_id !== v.original_run_id || original.run_sha256 !== v.original_run_sha256 || original.input_snapshot.artifact_id !== v.input_snapshot.artifact_id
      || original.input_snapshot.artifact_sha256 === v.input_snapshot.artifact_sha256 || !same(original.input_snapshot.documents, v.input_snapshot.documents)
      || !same(original.model_names, v.model_names) || !v.changed_fields.includes('Funds Obligated to Date')) throw new Error('Different repair lineage')
  }
}
export function verifyGovernanceView(view: GovernanceView, l: GovernanceList, depth = 0, embeddedScope = false): GovernanceView {
  if (depth > 16 || !governanceKinds.includes(view.kind) || !course(view.value, l)) throw new Error('Different course or excessive ancestry')
  if (view.kind === 'capture') { capture(view.value, l); return view }
  if (view.kind === 'run') { run(view.value, l, depth); return view }
  const record = view.value
  if (!id(record.uuid) || !id(record.run_id) || (!embeddedScope && !digest(record.record_sha256)) || record.record_kind !== kinds[view.kind]
    || record.uuid !== record.submission.request_id || record.credit_awarded !== false) throw new Error('Different learner record')
  if (view.kind === 'scope') {
    if (view.value.case_sha256 !== l.case.case_sha256 || !validGovernanceRequest({ action: 'scope', body: view.value.submission }, l.case)) throw new Error('Different scope decision')
    return view
  }
  if (!sameGovernanceCase(record.case, l.case) || !validGovernanceRequest({ action: view.kind, body: record.submission } as GovernanceRequest, l.case)) throw new Error('Different learner submission')
  switch (view.kind) {
    case 'correction': capture(view.value.input_snapshot, l); if (view.value.input_snapshot.uuid !== view.value.submission.input_snapshot_id || view.value.input_snapshot.input_snapshot_sha256 !== view.value.submission.input_snapshot_sha256 || !same(view.value.submission.source_document_ids, view.value.input_snapshot.documents.map(d => d.document_id))) throw new Error('Different corrected source scope'); break
    case 'finding': run(view.value.run, l, depth + 1); if (view.value.run.phase !== 'original' || view.value.run.state !== 'completed' || view.value.run.result_sha256 !== view.value.submission.result_sha256 || !view.value.run.result?.checks?.observed_semantic_failure || view.value.run.run_id !== view.value.run_id) throw new Error('Different observed original finding'); break
    case 'memo': run(view.value.run, l, depth + 1); if (view.value.run.phase !== 'repair' || !view.value.run.result?.repair_checks?.repair_requirements_supported || view.value.run.run_id !== view.value.run_id || view.value.run.result_sha256 !== view.value.submission.result_sha256 || !digest(view.value.file.sha256) || view.value.file.memo.owner_user_id !== view.value.user_id) throw new Error('Different accountable memo'); break
    case 'release': verifyGovernanceView({ kind: 'memo', value: view.value.memo }, l, depth + 1); if (view.value.memo.uuid !== view.value.submission.memo_id || view.value.memo.record_sha256 !== view.value.submission.memo_sha256 || view.value.memo.file.sha256 !== view.value.submission.file_sha256 || view.value.memo.run_id !== view.value.run_id) throw new Error('Different memo release'); break
    case 'handoff': {
      const v = view.value
      verifyGovernanceView({ kind: 'release', value: v.release }, l, depth + 1)
      if (v.release.submission.choice !== 'approve' || v.release.uuid !== v.submission.release_id || v.release.record_sha256 !== v.submission.release_sha256
        || v.release.run_id !== v.run_id || v.release.memo.file.sha256 !== v.submission.file_sha256 || v.external_delivery !== false) throw new Error('Different private handoff approval')
      if (v.submission.action === 'attempt') { if (v.status !== 'failed' || v.destination_written || v.destination_copy || v.previous_failed_receipt) throw new Error('Different first no-write failure') }
      else {
        if (!v.previous_failed_receipt || v.previous_failed_receipt.submission.action !== 'attempt') throw new Error('Missing original failure')
        verifyGovernanceView({ kind: 'handoff', value: v.previous_failed_receipt }, l, depth + 1)
        if (v.status !== 'delivered' || !v.destination_written || !same(v.destination_copy, v.release.memo.file) || v.previous_failed_receipt.uuid !== v.submission.previous_failed_id || v.previous_failed_receipt.record_sha256 !== v.submission.previous_failed_sha256 || v.previous_failed_receipt.submission.memo_sha256 !== v.submission.memo_sha256) throw new Error('Different same-bytes recovery')
      }
      break
    }
    case 'review': verifyGovernanceView({ kind: 'handoff', value: view.value.handoff }, l, depth + 1); if (view.value.handoff.status !== 'delivered' || view.value.handoff.uuid !== view.value.submission.handoff_id || view.value.handoff.record_sha256 !== view.value.submission.handoff_sha256 || view.value.handoff.run_id !== view.value.run_id) throw new Error('Different final supervision'); break
  }
  return view
}
export function verifyGovernanceResponse(view: GovernanceView, listing: GovernanceList, request: GovernanceRequest) {
  verifyGovernanceView(view, listing)
  if (request.action === 'capture') {
    if (view.kind !== 'capture' || view.value.uuid !== request.body.request_id || view.value.artifact_id !== request.body.artifact_id) throw new Error('Different capture request')
  } else if (request.action === 'prepare' || request.action === 'execute' || request.action === 'finalize') {
    if (view.kind !== 'run' || view.value.run_id !== ('request_id' in request.body ? request.body.request_id : request.body.run_id)) throw new Error('Different run request')
    if (request.action === 'prepare') {
      if (view.value.input_snapshot.uuid !== request.body.input_snapshot_id || view.value.input_snapshot.input_snapshot_sha256 !== request.body.input_snapshot_sha256
        || view.value.scope_correction.uuid !== request.body.scope_correction_id || view.value.scope_correction.record_sha256 !== request.body.scope_correction_sha256
        || (view.value.source_finding?.uuid || null) !== request.body.source_finding_id || (view.value.source_finding?.record_sha256 || null) !== request.body.source_finding_sha256) throw new Error('Different prepared revision')
    } else if (view.value.plan_sha256 !== request.body.plan_sha256) throw new Error('Different approved plan')
    if (request.action === 'execute' && (view.value.scope_decision_id !== request.body.scope_decision_id || view.value.scope_decision_sha256 !== request.body.scope_decision_sha256)) throw new Error('Different execution consent')
    if (request.action === 'finalize' && (view.value.authorization_sha256 !== request.body.authorization_sha256 || view.value.extraction_events_sha256 !== request.body.extraction_events_sha256)) throw new Error('Different saved extraction')
  } else {
    if (view.kind !== request.action || !('submission' in view.value) || Object.entries(request.body).some(([k, v]) => !same((view.value as GovernanceRecord<typeof request.action>).submission[k as keyof typeof request.body], v))) throw new Error('Different saved learner decision')
  }
  return view
}
