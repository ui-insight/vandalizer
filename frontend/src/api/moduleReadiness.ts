import { apiFetch } from './client'
import type { CourseDefinition } from '../types/certification'

export type ReadinessIdentity = Pick<CourseDefinition, 'enrollment_id' | 'course_version' | 'manifest_sha256'>
export type OutcomeState = 'selection_required' | 'assessment_pending' | 'grading_unavailable' | 'revision_required' | 'supported'
export interface AssessmentSelection { review?: string; scenario?: string }
export interface ModuleReadinessResult extends ReadinessIdentity {
  module_id: string
  contract_sha256: string
  rubric_id: string
  assessment_kind: 'module_readiness_draft'
  status: Exclude<OutcomeState, 'supported'> | 'requirements_supported'
  all_required_outcomes_supported: boolean
  outcomes: { outcome_id: string; statement: string; method: 'scenario_choice' | 'structured_review' | 'deterministic'; state: OutcomeState; attempt_id: string | null }[]
  selected_receipts: { kind: 'automatic_review' | 'scenario_recognition'; attempt_id: string; record_sha256: string; result_sha256: string | null }[]
  read_only: true
  credit_awarded: false
  module_completion_eligible: false
  staff_review_required: false
}

export function getModuleReadiness(enrollmentId: string, moduleId: string, selection: AssessmentSelection = {}) {
  const query = new URLSearchParams({ enrollment_id: enrollmentId })
  if (selection.review) query.set('review_attempt_id', selection.review)
  if (selection.scenario) query.set('scenario_attempt_id', selection.scenario)
  return apiFetch<ModuleReadinessResult>(`/api/certification/modules/${encodeURIComponent(moduleId)}/readiness?${query}`)
}

/** Reject stale, incomplete or contradictory read responses before displaying a success. */
export function verifyModuleReadiness(value: ModuleReadinessResult, identity: ReadinessIdentity, moduleId: string,
  selection: AssessmentSelection, original?: ModuleReadinessResult) {
  const digest = /^[a-f0-9]{64}$/
  const states: OutcomeState[] = ['revision_required', 'grading_unavailable', 'assessment_pending', 'selection_required', 'supported']
  if (value.enrollment_id !== identity.enrollment_id || value.course_version !== identity.course_version
    || value.manifest_sha256 !== identity.manifest_sha256 || value.module_id !== moduleId
    || value.assessment_kind !== 'module_readiness_draft' || value.read_only !== true || value.credit_awarded !== false
    || value.module_completion_eligible !== false || value.staff_review_required !== false
    || !digest.test(value.contract_sha256) || !value.rubric_id || !value.outcomes?.length
    || new Set(value.outcomes.map(item => item.outcome_id)).size !== value.outcomes.length) throw new Error('Unavailable requirements')
  for (const item of value.outcomes) {
    const selected = item.method === 'scenario_choice' ? selection.scenario : selection.review
    if (!item.outcome_id || !item.statement?.trim() || !['scenario_choice', 'structured_review', 'deterministic'].includes(item.method)
      || !states.includes(item.state) || item.attempt_id !== (selected || null)
      || (item.method === 'scenario_choice' && !['selection_required', 'supported', 'revision_required'].includes(item.state))
      || (selected ? item.state === 'selection_required' : item.state !== 'selection_required')) throw new Error('Unavailable outcome')
  }
  const receipts = [selection.review && { kind: 'automatic_review', id: selection.review }, selection.scenario && { kind: 'scenario_recognition', id: selection.scenario }].filter(Boolean) as { kind: string; id: string }[]
  if (value.selected_receipts?.length !== receipts.length || receipts.some(expected => {
    const matches = value.selected_receipts.filter(item => item.kind === expected.kind && item.attempt_id === expected.id)
    return matches.length !== 1 || !digest.test(matches[0].record_sha256) || (matches[0].result_sha256 !== null && !digest.test(matches[0].result_sha256))
  })) throw new Error('Unavailable selected evidence')
  if (value.outcomes.some(item => ['supported', 'revision_required'].includes(item.state)
    && !value.selected_receipts.find(receipt => receipt.attempt_id === item.attempt_id)?.result_sha256)) throw new Error('Missing saved result')
  const status = states.find(state => state !== 'supported' && value.outcomes.some(item => item.state === state)) || 'requirements_supported'
  if (value.status !== status || value.all_required_outcomes_supported !== (status === 'requirements_supported')) throw new Error('Contradictory summary')
  if (original && (value.contract_sha256 !== original.contract_sha256 || value.rubric_id !== original.rubric_id
    || value.outcomes.length !== original.outcomes.length || value.outcomes.some(item => !original.outcomes.some(required =>
      required.outcome_id === item.outcome_id && required.method === item.method && required.statement === item.statement)))) throw new Error('Changed requirements')
  return value
}
