import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const data = new URL('../../../backend/certification-data/', import.meta.url)
const read = async name => JSON.parse(await readFile(new URL(name, data), 'utf8'))
const modules = await read('panel-modules.json')
const structure = await read('course-structure.json')
const module = modules.find(item => item.id === 'foundations')
module.decisionPrompts = (await read('drafts/v5.0/foundations-decisions.json')).map(prompt => ({ ...prompt, prompt_sha256: 'c'.repeat(64) }))
module.assessment = null
const identity = { enrollment_id: 'saved-review-course', course_version: 'saved-review-fixture', manifest_sha256: 'a'.repeat(64), course_title: 'Local saved assessment fixture', modules_total: modules.length, module_ids: modules.map(m => m.id), maximum_xp: 2675 }
const course = { ...structure, ...identity, versioned: true, prerequisites: Object.fromEntries(modules.map(m => [m.id, []])), modules }
const progress = { ...identity, id: 'progress', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, learning_position: null }
const attemptId = 'b'.repeat(32), runId = 'd'.repeat(32)
const summary = { attempt_id: attemptId, enrollment_id: identity.enrollment_id, module_id: 'foundations', run_id: runId, prepared_at: '2026-10-06T07:00:00Z', finished_at: '2026-10-06T07:01:00Z', parent_attempt_id: null, status: 'revision_required' }
const result = { ...summary, course_version: identity.course_version, manifest_sha256: identity.manifest_sha256, assessment_kind: 'practical_review_draft', credit_awarded: false, module_completion_eligible: false, staff_review_required: false, can_request_review: false, can_retry_review: false,
  outcomes: [
    { outcome_id: 'foundations.scoped_proposal', statement: 'Review and correct the proposed scope before execution.', method: 'structured_review', verdict: 'unclear', explanation: 'The saved answer does not establish why this source matches the assigned task.', revision_instruction: 'Compare the saved source agency and document title against the assignment, then explain the scope you would authorize.', citations: [{ kind: 'learner_decision', quote: 'I accepted the suggested source because its filename looked familiar. <script>This quotation is untrusted text.</script>' }] },
    { outcome_id: 'foundations.executed_extraction', statement: 'Execute the approved extraction on the assigned inputs.', method: 'deterministic', verdict: 'supported', explanation: 'The completed run binds the reviewed extraction revision and the exact assigned inputs.', revision_instruction: '', citations: [] },
    { outcome_id: 'foundations.verified_values', statement: 'Verify extracted values against source evidence.', method: 'structured_review', verdict: 'not_assessed', explanation: 'No saved assessment result is available for this outcome.', revision_instruction: '', citations: [] },
  ] }
let mode = 'revision_required'
const writes = []
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5292' })
const { page, context } = review
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  if (request.method() !== 'GET') writes.push(path)
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.endsWith('/practical-runs')) return route.fulfill({ json: { runs: [], older_runs_available: false } })
  if (path.endsWith('/automatic-reviews')) {
    assert.equal(url.searchParams.get('enrollment_id'), identity.enrollment_id)
    return route.fulfill({ json: { enrollment_id: identity.enrollment_id, module_id: module.id, attempts: mode === 'empty' ? [] : [{ ...summary, status: mode === 'error' ? 'revision_required' : mode }], older_attempts_available: mode !== 'empty' } })
  }
  if (path.endsWith('/automatic-reviews/' + attemptId)) {
    assert.equal(url.searchParams.get('enrollment_id'), identity.enrollment_id)
    if (mode === 'error') return route.fulfill({ status: 503, json: { detail: 'Synthetic unavailable response' } })
    return route.fulfill({ json: { ...result, status: mode,
      ...(mode === 'grading_unavailable' ? { parent_attempt_id: 'e'.repeat(32), outcomes: result.outcomes.map(o => o.method === 'deterministic' ? o : { ...o, verdict: 'not_assessed', explanation: 'No saved assessment result is available for this outcome.', revision_instruction: '', citations: [] }) } : {}),
      ...(mode === 'requirements_supported' ? { outcomes: result.outcomes.map(o => ({ ...o, verdict: 'supported', explanation: 'Synthetic supported evidence for local interface testing.', revision_instruction: '' })) } : {}),
      ...(mode === 'evaluating' ? { finished_at: null, outcomes: result.outcomes.map(o => ({ ...o, verdict: 'not_assessed', explanation: 'No saved assessment result is available for this outcome.', revision_instruction: '', citations: [] })) } : {}),
    } })
  }
  return route.fallback()
})
async function capture(id) {
  await review.capture(id, 'Production frontend; synthetic saved assessment fixtures. Read-only; no model, grade or live learner change.')
  if (process.env.REVIEW_TEXT_SCALE === '2' && id !== 'blocked') {
    const overflow = await page.getByRole('region', { name: 'Saved automatic assessments', exact: true }).evaluate(root =>
      [root, ...root.querySelectorAll('button,p,h4,h5,h6,blockquote,input,summary,dd')].filter(el => el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1)
        .map(el => ({ tag: el.tagName, text: el.textContent.slice(0, 100), width: el.clientWidth, content: el.scrollWidth })))
    assert.deepEqual(overflow, [], 'Saved assessment content overflows its container at enlarged text')
  }
  console.log(id)
}
try {
  await page.goto(review.baseURL + '/certification')
  const position = page.getByRole('combobox', { name: 'Learning panel position', exact: true })
  await position.selectOption('floating')
  await review.capture('saved-review-floating-header-1440', 'Floating panel title and position control with the selected text scale.')
  const titleFits = await page.getByText('Certification', { exact: true }).evaluate(element => element.getBoundingClientRect().height <= parseFloat(getComputedStyle(element).lineHeight) + 1)
  assert.equal(titleFits, true, 'The floating panel title must not be squeezed into fragments')
  await position.selectOption('fullscreen')
  const panel = page.getByRole('dialog', { name: 'Learning and certification', exact: true })
  await panel.getByRole('button', { name: /1 Foundations/ }).click()
  await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
  const saved = panel.getByRole('region', { name: 'Saved automatic assessments', exact: true })
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
    await saved.getByRole('heading', { name: 'Saved automatic assessments', exact: true }).scrollIntoViewIfNeeded()
    await capture('saved-review-entry-' + width)
    await saved.getByRole('button', { name: 'View saved assessments', exact: true }).click()
    await saved.getByRole('button', { name: /Assessment 1/ }).scrollIntoViewIfNeeded()
    await capture('saved-review-list-' + width)
    await saved.getByRole('button', { name: /Assessment 1/ }).click()
    await saved.getByRole('heading', { name: 'Revision needed', exact: true }).scrollIntoViewIfNeeded()
    await capture('saved-review-revision-' + width)
    await saved.getByText('Assessment details', { exact: true }).click()
    await saved.getByText('Assessment reference', { exact: true }).scrollIntoViewIfNeeded()
    await capture('saved-review-details-' + width)
    await saved.getByText('Assessment details', { exact: true }).click()
    await saved.getByText('Evidence cited (1)', { exact: true }).click()
    await saved.getByText(result.outcomes[0].citations[0].quote, { exact: true }).scrollIntoViewIfNeeded()
    await capture('saved-review-evidence-' + width)
    await saved.getByRole('button', { name: 'Close assessments', exact: true }).click()
    await page.waitForFunction(() => document.activeElement?.textContent === 'View saved assessments')
  }
  await page.setViewportSize({ width: 390, height: 844 })
  for (const state of ['grading_unavailable', 'requirements_supported', 'evaluating', 'error', 'empty']) {
    mode = state
    await saved.getByRole('button', { name: 'View saved assessments', exact: true }).click()
    if (state !== 'empty') await saved.getByRole('button', { name: /Assessment 1/ }).click()
    if (state === 'error') await saved.getByRole('alert').scrollIntoViewIfNeeded()
    else if (state === 'empty') await saved.getByText('No saved assessments are available for this module yet.', { exact: true }).scrollIntoViewIfNeeded()
    else await saved.getByLabel('Saved assessment result', { exact: true }).scrollIntoViewIfNeeded()
    await capture('saved-review-' + state + '-390')
    await saved.getByRole('button', { name: 'Close assessments', exact: true }).click()
  }
  assert.deepEqual(writes, [])
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  for (const capture of review.captures) {
    assert.equal(capture.pageWidth, capture.viewport.width)
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/${capture.id}.axe.json`, 'utf8')), [])
  }
  review.observations.push({ writes, modelCalls: 0, earnedCredit: 0, synthetic: true })
} catch (error) {
  console.error('Saved assessment check failed:', error)
  try { await capture('blocked') } catch (captureError) { console.error('Failure capture unavailable:', captureError) }
  throw error
} finally { await review.flush(); await review.browser.close() }
