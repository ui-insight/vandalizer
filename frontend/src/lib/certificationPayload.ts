/** Validate tool results before rendering course actions or success summaries.
 * A malformed write response does not prove that the write failed.
 */
import type { CourseDefinition } from '../types/certification'

const tools = new Set(['get_certification_progress', 'get_certification_module', 'get_certification_lesson', 'provision_certification_lab', 'check_certification_module', 'complete_certification_module', 'submit_certification_assessment'])
const object = (v: unknown): v is Record<string, unknown> => v !== null && typeof v === 'object' && !Array.isArray(v)
const text = (v: unknown): v is string => typeof v === 'string' && v.trim().length > 0
const number = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(text)
const stars = (v: unknown) => number(v) && v <= 3
const check = (v: unknown) => object(v) && text(v.name) && typeof v.passed === 'boolean' && typeof v.detail === 'string' && (v.role == null || v.role === 'required' || v.role === 'advisory')
const optionalStrings = (v: Record<string, unknown>, keys: string[]) => keys.every(k => v[k] === undefined || strings(v[k]))
export function isCourseProgressionPolicy(value: unknown): value is NonNullable<CourseDefinition['progression_policy']> {
  return object(value) && text(value.policy_id) && ['design_draft', 'release_candidate'].includes(String(value.state))
    && number(value.required_modules) && value.required_modules > 0
    && number(value.required_outcomes) && value.required_outcomes > 0
    && number(value.base_xp_total) && value.base_xp_total > 0
    && strings(value.rules) && value.rules.length > 0
}
function assessmentMetadata(value: Record<string, unknown>) {
  const outcomes = value.required_outcomes === undefined ? [] : value.required_outcomes
  const mode = value.assessment_mode
  if (mode != null && !['legacy_reflection', 'legacy_practical', 'selected_saved_outcomes'].includes(String(mode))) return false
  if (value.selected_outcome_completion !== undefined && typeof value.selected_outcome_completion !== 'boolean') return false
  if (!Array.isArray(outcomes)) return false
  if (mode !== 'selected_saved_outcomes') return outcomes.length === 0 && !value.selected_outcome_completion
  return outcomes.length > 0 && outcomes.every(outcome => object(outcome) && text(outcome.outcome_id)
    && outcome.outcome_id.startsWith(`${value.module_id}.`) && text(outcome.statement)
    && ['deterministic', 'scenario_choice', 'structured_review'].includes(String(outcome.method)))
    && new Set(outcomes.map(outcome => outcome.outcome_id)).size === outcomes.length
    && Array.isArray(value.assessment_keys) && value.assessment_keys.length === 0
    && Array.isArray(value.assessment_questions) && value.assessment_questions.length === 0
}

export function certificationPayloadIssue(name: string, value: unknown): string | null {
  if (!tools.has(name)) return null
  const invalid = 'The certification response is incomplete or inconsistent. Check your saved course state before continuing; do not repeat a saved action just because its reply is unclear.'
  if (!object(value)) return invalid
  if (value.code === 'certification_response_invalid') return invalid
  if (text(value.error)) return null // Explicit service errors use the existing recovery UI.
  if (value.enrollment_id !== undefined && !['enrollment_id', 'course_version', 'course_title', 'manifest_sha256'].every(k => text(value[k]))) return invalid
  if (value.maximum_stars !== undefined || value.credit_basis !== undefined) {
    if (!number(value.maximum_stars) || value.maximum_stars < 1 || value.maximum_stars > 3
      || !['required_outcomes', 'legacy_rubric'].includes(String(value.credit_basis))
      || (value.credit_basis === 'required_outcomes' && value.maximum_stars !== 1)
      || (number(value.stars) && value.stars > value.maximum_stars)
      || (Array.isArray(value.modules) && value.modules.some(row => object(row) && number(row.stars) && row.stars > (value.maximum_stars as number)))) return invalid
  }
  if (name !== 'get_certification_progress' && !text(value.module_id)) return invalid
  let valid = false
  switch (name) {
    case 'get_certification_progress': {
      const rows = value.modules
      valid = Array.isArray(rows) && rows.length > 0 && rows.every(row => object(row) && text(row.module_id) && text(row.title) && number(row.xp) && typeof row.completed === 'boolean' && stars(row.stars))
      if (!valid || !Array.isArray(rows)) break
      const ids = rows.map(row => row.module_id)
      const completed = rows.filter(row => row.completed).length
      if (value.progression_policy != null && (!isCourseProgressionPolicy(value.progression_policy)
        || !text(value.enrollment_id) || value.credit_basis !== 'required_outcomes'
        || value.progression_policy.required_modules !== rows.length
        || value.progression_policy.base_xp_total !== rows.reduce((total, row) => total + row.xp, 0))) return invalid
      valid = new Set(ids).size === rows.length && value.modules_total === rows.length && value.modules_completed === completed && number(value.total_xp) && text(value.level) && typeof value.certified === 'boolean' && (!value.certified || completed === rows.length) && (value.next_module_id === null || (text(value.next_module_id) && rows.some(row => row.module_id === value.next_module_id && !row.completed)))
      break
    }
    case 'get_certification_module':
      valid = text(value.title) && number(value.xp) && typeof value.completed === 'boolean' && stars(value.stars) && typeof value.overview === 'string' && strings(value.instructions) && optionalStrings(value, ['agent_guidance', 'expected_fields', 'assessment_keys', 'sample_documents', 'provisioned_docs', 'lesson_titles']) && (value.star_criteria === undefined || (object(value.star_criteria) && Object.entries(value.star_criteria).every(([key, v]) => /^[123]$/.test(key) && text(v)))) && assessmentMetadata(value)
      break
    case 'get_certification_lesson': {
      const knowledge = value.knowledge_check
      valid = text(value.title) && text(value.module_title) && text(value.content) && number(value.lesson_number) && value.lesson_number > 0 && number(value.lesson_count) && value.lesson_count >= value.lesson_number && value.is_last === (value.lesson_number === value.lesson_count) && (value.objective === undefined || typeof value.objective === 'string') && (value.diagram == null || typeof value.diagram === 'string')
      if (knowledge != null) valid = valid && object(knowledge) && text(knowledge.question) && Array.isArray(knowledge.options) && knowledge.options.length >= 2 && knowledge.options.every(option => object(option) && text(option.text) && typeof option.correct === 'boolean' && text(option.explanation)) && knowledge.options.filter(option => option.correct).length === 1
      break
    }
    case 'check_certification_module':
      valid = text(value.title) && typeof value.passed === 'boolean' && stars(value.stars) && Array.isArray(value.checks) && value.checks.length > 0 && value.checks.every(check)
      if (valid && Array.isArray(value.checks) && value.checks.some(item => item.role != null)) {
        const required = value.checks.filter(item => item.role === 'required')
        valid = value.checks.every(item => item.role != null) && required.length > 0 && value.passed === required.every(item => item.passed)
      }
      break
    case 'complete_certification_module':
      valid = text(value.title) && number(value.xp_earned) && number(value.total_xp) && value.xp_earned <= value.total_xp && stars(value.stars) && text(value.level) && typeof value.level_up === 'boolean' && typeof value.certified === 'boolean' && (value.modules_total === undefined || (number(value.modules_total) && value.modules_total > 0))
      if (value.credit_origin != null || value.xp_carried != null || value.source_enrollment_id != null) {
        valid = valid && value.credit_origin === 'transferred' && value.xp_earned === 0 && number(value.xp_carried)
          && number(value.total_xp) && value.xp_carried <= value.total_xp && text(value.source_enrollment_id)
      }
      break
    case 'provision_certification_lab':
      valid = strings(value.provisioned_docs) && strings(value.document_names) && text(value.folder) && text(value.message)
      break
    case 'submit_certification_assessment':
      valid = value.stored === true && text(value.message)
      break
  }
  return valid ? null : invalid
}
