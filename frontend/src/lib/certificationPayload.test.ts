import { expect, it } from 'vitest'
import { certificationPayloadIssue as issue } from './certificationPayload'

const progress = { modules: [{ module_id: 'foundations', title: 'Foundations', xp: 100, completed: false, stars: 0 }], modules_completed: 0, modules_total: 1, next_module_id: 'foundations', certified: false, total_xp: 0, level: 'novice' }

it('rejects contradictory or malformed policy metadata while retaining old progress cards', () => {
  const policy = { policy_id: 'required-outcomes-flexible-order.1', state: 'design_draft', required_modules: 1, required_outcomes: 3, base_xp_total: 100, rules: ['Same assessed criteria.'] }
  const pinned = { ...progress, enrollment_id: 'e', course_version: 'v', course_title: 'Course', manifest_sha256: 'a'.repeat(64), maximum_stars: 1, credit_basis: 'required_outcomes', progression_policy: policy }
  expect(issue('get_certification_progress', progress)).toBeNull()
  expect(issue('get_certification_progress', pinned)).toBeNull()
  for (const change of [{ required_modules: 2 }, { base_xp_total: 101 }, { rules: [] }, { rules: [' '] }, { state: 'published' }, { required_outcomes: '3' }]) {
    expect(issue('get_certification_progress', { ...pinned, progression_policy: { ...policy, ...change } })).not.toBeNull()
  }
  expect(issue('get_certification_progress', { ...pinned, enrollment_id: undefined })).not.toBeNull()
  expect(issue('get_certification_progress', { ...pinned, credit_basis: 'legacy_rubric' })).not.toBeNull()
})

it.each([
  { maximum_stars: 1 }, { credit_basis: 'required_outcomes' },
  { maximum_stars: true, credit_basis: 'legacy_rubric' },
  { maximum_stars: 3, credit_basis: 'required_outcomes' },
  { maximum_stars: 1, credit_basis: 'legacy_rubric', modules: [{ ...progress.modules[0], stars: 2 }] },
])('rejects contradictory course reward metadata %j', metadata => {
  expect(issue('get_certification_progress', { ...progress, ...metadata })).not.toBeNull()
})
const lesson = { module_id: 'foundations', module_title: 'Foundations', title: 'Inspect the source', content: 'Read the assigned source.', lesson_number: 1, lesson_count: 1, is_last: true }
const completion = { module_id: 'foundations', title: 'Foundations', stars: 1, xp_earned: 125, total_xp: 125, level: 'apprentice', level_up: true, certified: false }
const checks = { module_id: 'foundations', title: 'Foundations', passed: true, stars: 1, checks: [{ name: 'Required run', passed: true, detail: 'Saved output' }, { name: 'Optional enrichment', passed: false, detail: 'Add source context' }] }

it.each(['valid', 'required_failed', 'false_summary', 'unknown_role', 'missing_role', 'only_advice'])('checks explicit role summary: %s', change => {
  const payload = { ...checks, checks: [{ ...checks.checks[0], role: 'required' as string | undefined }, { ...checks.checks[1], role: 'advisory' as string | undefined }] }
  if (change === 'required_failed') payload.checks[0].passed = false
  if (change === 'false_summary') payload.passed = false
  if (change === 'unknown_role') payload.checks[1].role = 'optional_failure'
  if (change === 'missing_role') delete payload.checks[0].role
  if (change === 'only_advice') payload.checks.shift()
  expect(issue('check_certification_module', payload) === null).toBe(change === 'valid')
})
const valid = [
  ['get_certification_progress', progress],
  ['get_certification_module', { module_id: 'foundations', title: 'Foundations', xp: 100, completed: false, stars: 0, overview: 'Inspect a source', instructions: ['Open the source'], star_criteria: { '1': 'Required evidence' } }],
  ['get_certification_lesson', lesson],
  ['check_certification_module', checks],
  ['complete_certification_module', completion],
  ['provision_certification_lab', { module_id: 'foundations', provisioned_docs: [], document_names: [], folder: 'Lab', message: 'No assigned documents' }],
  ['submit_certification_assessment', { module_id: 'foundations', stored: true, message: 'Answers saved' }],
] as const
it.each(valid)('accepts the supported %s response without coercion', (name, payload) => { expect(issue(name, payload)).toBeNull() })
it.each(valid)('rejects missing data for %s rather than inventing successful defaults', (name) => { expect(issue(name, {})).toContain('Check your saved course state') })
it.each([null, '', [], 0, { modules: {} }, { ...progress, certified: 'false' }, { ...progress, modules_total: 2 }, { ...progress, certified: true }, { ...progress, next_module_id: 'foreign' }, { ...progress, total_xp: -1 }, { ...progress, modules: [...progress.modules, ...progress.modules], modules_total: 2 }])('rejects malformed or contradictory progress %j', payload => { expect(issue('get_certification_progress', payload)).not.toBeNull() })
it.each([{ ...lesson, is_last: 'false' }, { ...lesson, lesson_number: 2 }, { ...lesson, content: {} }, { ...lesson, knowledge_check: { question: 'Choose', options: [{ text: 'A', correct: true, explanation: 'A' }, { text: 'B', correct: true, explanation: 'B' }] } }])('rejects unsafe lesson structure %j', payload => { expect(issue('get_certification_lesson', payload)).not.toBeNull() })
it('requires a complete version identity when enrollment is supplied', () => {
  expect(issue('get_certification_progress', { ...progress, enrollment_id: 'e' })).not.toBeNull()
  expect(issue('get_certification_progress', { ...progress, enrollment_id: 'e', course_version: 'v1', course_title: 'Course', manifest_sha256: 'a'.repeat(64) })).toBeNull()
})
it.each([{ ...checks, passed: 'false' }, { ...checks, checks: {} }, { ...checks, checks: [] }, { ...completion, certified: 'false' }, { ...completion, stars: 1000000 }, { ...completion, xp_earned: 500 }, { ...completion, total_xp: Number.NaN }])('rejects unsupported pass/completion data %j', payload => { expect(issue('checks' in payload ? 'check_certification_module' : 'complete_certification_module', payload)).not.toBeNull() })
it('keeps explicit service errors and unrelated tools on their existing paths', () => {
  expect(issue('complete_certification_module', { error: 'Not ready', hint: 'Inspect required evidence' })).toBeNull()
  expect(issue('search_documents', [])).toBeNull()
})

it('accepts all 86 actual backend progress/module/lesson responses from the contract export', async () => {
  const fixture = await import('../components/certification/__fixtures__/chat-tool-contract.json?raw')
  const responses = JSON.parse(fixture.default) as { tool_name: string; content: unknown }[]
  expect(responses).toHaveLength(86)
  for (const response of responses) expect(issue(response.tool_name, response.content), response.tool_name).toBeNull()
})

it('accepts persisted chat assessment, completion, replay and stale-course responses', async () => {
  const fixture = await import('../components/certification/__fixtures__/chat-write-contract.json')
  expect(fixture.default).toHaveLength(5)
  for (const response of fixture.default) expect(issue(response.tool_name, response.content), response.tool_name).toBeNull()
  const completions = fixture.default.filter(response => response.tool_name === 'complete_certification_module' && !response.content.error)
  expect(completions.map(response => response.content.xp_earned)).toEqual([125, 0])
  expect(completions.map(response => response.content.total_xp)).toEqual([125, 125])
})

it('recognizes a backend contract failure as an uncertain response', () => {
  expect(issue('complete_certification_module', { error: 'Response could not be confirmed', code: 'certification_response_invalid' })).toContain('Check your saved course state')
})

const outcome = { outcome_id: 'foundations.inspect', statement: 'Inspect the saved result against its source.', method: 'structured_review' }
const outcomeModule = { ...valid[1][1], assessment_mode: 'selected_saved_outcomes', required_outcomes: [outcome], assessment_keys: [], assessment_questions: [], selected_outcome_completion: false }
it('accepts the pinned required-outcome definition for a draft module', () => {
  expect(issue('get_certification_module', outcomeModule)).toBeNull()
  expect(issue('get_certification_module', { ...outcomeModule, agent_guidance: ['Help the learner inspect their saved work.'] })).toBeNull()
  expect(issue('get_certification_module', { ...outcomeModule, agent_guidance: 'Assistant-only text must be a list' })).not.toBeNull()
})
it.each([
  { required_outcomes: {} }, { required_outcomes: null }, { required_outcomes: [] }, { required_outcomes: [outcome, outcome] },
  { required_outcomes: [{ ...outcome, outcome_id: 'another.inspect' }] },
  { required_outcomes: [{ ...outcome, statement: '' }] },
  { required_outcomes: [{ ...outcome, method: 'participation' }] },
  { assessment_mode: 'legacy_reflection' }, { assessment_keys: ['old_reflection'] },
  { assessment_questions: [{ question: 'An old reflection' }] }, { selected_outcome_completion: 'false' },
])('rejects invalid or contradictory required-outcome instructions %j', change => {
  expect(issue('get_certification_module', { ...outcomeModule, ...change })).not.toBeNull()
})
