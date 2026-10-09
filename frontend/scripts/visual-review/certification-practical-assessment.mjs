import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const data = new URL('../../../backend/certification-data/', import.meta.url)
const read = async name => JSON.parse(await readFile(new URL(name, data), 'utf8'))
const modules = await read('panel-modules.json'), structure = await read('course-structure.json')
const module = modules.find(item => item.id === 'foundations')
const prompts = (await read('drafts/v5.0/foundations-decisions.json')).map((prompt, i) => ({ ...prompt, prompt_sha256: String(i + 1).repeat(64) }))
const valuePrompt = prompts.find(item => item.id === 'value_review')
Object.assign(module, { decisionPrompts: prompts, practicalPreparation: true, assessment: null })
const identity = { enrollment_id: 'assessment-course', course_version: 'assessment-fixture', manifest_sha256: 'a'.repeat(64), course_title: 'Local assessment fixture', module_ids: modules.map(item => item.id), modules_total: modules.length, maximum_xp: 2675 }
const course = { ...structure, ...identity, versioned: true, prerequisites: Object.fromEntries(modules.map(item => [item.id, []])), modules }
const progress = { ...identity, user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, learning_position: null }
const runId = 'a'.repeat(32), writes = [], saved = new Map()
let mode = 'revision', values = null
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5292', resetStorage: false })
const { page, context } = review
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
function receipt(id, parent = null) {
  const status = mode === 'supported' ? 'requirements_supported' : mode === 'unavailable' ? 'grading_unavailable' : ['prepared', 'evaluating'].includes(mode) ? mode : 'revision_required'
  return { ...identity, attempt_id: id, module_id: module.id, run_id: runId, prepared_at: '2026-10-06T12:00:00Z', finished_at: ['prepared', 'evaluating'].includes(status) ? null : '2026-10-06T12:00:01Z', parent_attempt_id: parent,
    status, assessment_kind: 'practical_review_draft', credit_awarded: false, module_completion_eligible: false, staff_review_required: false, can_request_review: false, can_retry_review: false,
    outcomes: [{ outcome_id: 'foundations.executed_extraction', statement: 'Execute the reviewed extraction against the assigned source', method: 'deterministic', verdict: 'supported', explanation: 'The saved execution binds the approved assigned inputs.', revision_instruction: '', citations: [] },
      { outcome_id: 'foundations.verified_values', statement: 'Verify extracted values against the source', method: 'structured_review', verdict: status === 'requirements_supported' ? 'supported' : 'unclear',
        explanation: 'Synthetic feedback: the saved checks do not establish every value.', revision_instruction: status === 'requirements_supported' ? '' : 'Compare each value with an exact passage in the assigned source, then save your revised checks.',
        citations: [{ kind: 'learner_decision', quote: '<script>Untrusted text must stay text</script>' }] }] }
}
function storedValues(body) { return { uuid: body.request_id, enrollment_id: identity.enrollment_id, module_id: module.id, run_id: runId, prompt_id: valuePrompt.id,
  prompt_sha256: valuePrompt.prompt_sha256, submitted_at: '2026-10-06T11:59:00Z', submission: body, credit_awarded: false } }
function seedValues() { values = storedValues({ request_id: 'd'.repeat(32), run_id: runId, prompt_sha256: valuePrompt.prompt_sha256, choice: 'unresolved', reason: 'I cannot establish these synthetic source values yet.',
  value_checks: valuePrompt.required_fields.map(field => ({ field, decision: 'unresolved', checked_value: '', source_document_id: 'assigned-source', source_quote: '', reason: 'No matching source passage has been established for this synthetic sample.' })) }) }
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  if (request.method() !== 'GET') writes.push({ path, body: request.postDataJSON() })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.endsWith('/practical-runs')) return route.fulfill({ json: { runs: [{ run_id: runId, state: 'completed' }], older_runs_available: false } })
  if (path.includes('/decisions/') && path.includes('/runs/')) {
    const prompt = prompts.find(item => path.includes('/decisions/' + item.id + '/'))
    return route.fulfill({ json: { enrollment_id: identity.enrollment_id, module_id: module.id, prompt, run_id: runId, run_state: 'completed', can_submit: prompt.phase === 'after_execution', lab_folder_id: 'Training lab',
      artifact: { title: 'Saved NSF proposal extraction', fields: valuePrompt.required_fields.map(searchphrase => ({ searchphrase, is_optional: false })) },
      documents: [{ document_id: 'assigned-source', title: 'Assigned NSF ecology proposal', text: 'Synthetic assigned-source evidence retained for this run.' }],
      scope_proposal: null, result: { entities: [{ 'PI Name': 'Synthetic value' }] }, latest_decision: prompt.phase === 'after_execution' ? values : null } })
  }
  if (path.endsWith('/decisions/value_review') && request.method() === 'POST') {
    const body = request.postDataJSON()
    assert.equal(body.choice, 'unresolved'); assert.deepEqual(body.value_checks.map(item => item.field), valuePrompt.required_fields)
    assert.ok(body.value_checks.every(item => item.decision === 'unresolved' && item.source_document_id === 'assigned-source' && item.reason.length >= 10))
    values = storedValues(body); return route.fulfill({ json: values })
  }
  if (path.endsWith('/automatic-reviews') && request.method() === 'POST' || path.endsWith('/retry')) {
    assert.equal(url.searchParams.get('enrollment_id'), identity.enrollment_id)
    const body = request.postDataJSON(), parent = path.endsWith('/retry') ? path.split('/').at(-2) : null
    assert.deepEqual(Object.keys(body).sort(), ['consent', 'request_id']); assert.match(body.request_id, /^[a-f0-9]{32}$/)
    assert.equal(body.consent, parent ? 'retry_saved_assessment' : 'assess_saved_work')
    if (parent) assert.equal(saved.get(parent).status, 'grading_unavailable')
    if (!values || mode === 'reject') return route.fulfill({ status: 409, json: { detail: 'Complete the saved value review before requesting assessment' } })
    const result = receipt(body.request_id, parent); saved.set(body.request_id, result)
    if (['lost', 'lost_retry'].includes(mode)) return route.fulfill({ status: 503, json: { detail: 'Synthetic lost response after grading' } })
    return route.fulfill({ json: mode === 'mismatch' ? { ...result, run_id: 'foreign-run' } : result })
  }
  if (path.includes('/automatic-reviews/') && request.method() === 'GET') {
    if (mode === 'history_error') return route.fulfill({ status: 503, json: { detail: 'Synthetic history outage' } })
    const result = saved.get(path.split('/').at(-1))
    return route.fulfill({ status: result ? 200 : 404, json: result || { detail: 'Not found' } })
  }
  if (path.endsWith('/automatic-reviews') && request.method() === 'GET') return route.fulfill({ json: { enrollment_id: identity.enrollment_id, module_id: module.id, attempts: [...saved.values()], older_attempts_available: false } })
  return route.fallback()
})
const panel = page.getByRole('dialog', { name: 'Learning and certification', exact: true })
const assessment = page.getByRole('region', { name: 'Request automatic assessment', exact: true })
const feedback = page.getByRole('region', { name: 'Saved automatic assessments', exact: true })
async function enter({ reset = true } = {}) {
  if (reset && page.url().startsWith(review.baseURL)) await page.evaluate(() => sessionStorage.clear())
  await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await panel.getByRole('button', { name: /1 Foundations/ }).click(); await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
  await panel.getByRole('combobox', { name: 'Saved run', exact: true }).selectOption(runId)
  await panel.getByRole('combobox', { name: 'Review stage', exact: true }).selectOption('value_review')
  await assessment.getByRole('heading', { name: 'Assess your saved work', exact: true }).scrollIntoViewIfNeeded()
}
async function capture(id, region = assessment) {
  await review.capture(id, 'Synthetic saved checks and judge feedback; no real provider, grade, credit or learner update.')
  if (process.env.REVIEW_TEXT_SCALE === '2') {
    const overflow = await region.evaluate(root => [root, ...root.querySelectorAll('button,p,h4,h5,h6,summary,blockquote')].filter(el => el.clientWidth && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent.slice(0, 80)))
    assert.deepEqual(overflow, [], 'Assessment content clips at enlarged text')
  }
  console.log(id)
}
async function requestAssessment() { await assessment.getByRole('button', { name: 'Assess saved work automatically', exact: true }).click() }
async function confirmed() { await assessment.getByRole('region', { name: 'Requested assessment status', exact: true }).waitFor() }
try {
  for (const width of [320, 390, 1440]) {
    mode = 'revision'; values = null
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 }); await enter(); await capture('assessment-entry-' + width)
    await panel.getByRole('radio', { name: valuePrompt.choices.unresolved, exact: true }).check()
    await panel.getByRole('textbox', { name: 'Explain your decision', exact: true }).fill('I cannot establish every value from this synthetic evidence yet.')
    for (const field of valuePrompt.required_fields) await panel.getByRole('group', { name: field, exact: true }).getByRole('textbox', { name: 'What did you establish?', exact: true }).fill('No matching source passage has been established for this synthetic sample.')
    await panel.getByRole('button', { name: 'Save my decision', exact: true }).click(); await panel.getByRole('heading', { name: 'Decision saved', exact: true }).waitFor()
    await requestAssessment(); await confirmed(); await capture('assessment-revision-' + width)
    const count = writes.length
    await assessment.getByRole('button', { name: 'Open saved feedback', exact: true }).click()
    await feedback.getByRole('region', { name: 'Saved assessment result', exact: true }).waitFor()
    await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Saved assessment result')
    await capture('assessment-feedback-' + width, feedback)
    await feedback.getByText('Evidence cited (1)', { exact: true }).click()
    assert.equal(await feedback.locator('script').count(), 0)
    await feedback.getByText('Assessment details', { exact: true }).click(); await capture('assessment-feedback-details-' + width, feedback)
    await feedback.getByRole('button', { name: 'Close assessments', exact: true }).click()
    assert.equal(await feedback.getByRole('button', { name: 'View saved assessments', exact: true }).evaluate(el => el === document.activeElement), true)
    assert.equal(writes.length, count)
  }
  await page.setViewportSize({ width: 390, height: 844 })
  for (const current of ['supported', 'unavailable', 'prepared', 'evaluating', 'lost', 'reject', 'mismatch']) {
    mode = current; seedValues(); await enter(); await requestAssessment()
    if (['lost', 'reject', 'mismatch'].includes(current)) await assessment.getByRole('alert').waitFor(); else await confirmed()
    await capture('assessment-' + current + '-390')
    const count = writes.length, original = writes.at(-1).body.request_id
    if (current === 'unavailable') {
      mode = 'revision'; await assessment.getByRole('button', { name: 'Retry the original assessment', exact: true }).click(); await confirmed()
      assert.equal(saved.get(writes.at(-1).body.request_id).parent_attempt_id, original); await capture('assessment-retried-390')
    } else if (current === 'prepared') {
      mode = 'revision'; await assessment.getByRole('button', { name: 'Finish requested assessment', exact: true }).click(); await confirmed()
      assert.equal(writes.at(-1).body.request_id, original); await capture('assessment-finished-390')
    } else if (current === 'lost') {
      mode = 'history_error'; await enter({ reset: false }); await assessment.getByRole('button', { name: 'Check saved assessment', exact: true }).click()
      await assessment.getByRole('alert').waitFor(); await capture('assessment-history-unavailable-390')
      assert.equal(writes.length, count)
      mode = 'revision'; await assessment.getByRole('button', { name: 'Check saved assessment', exact: true }).click(); await confirmed(); await capture('assessment-lost-recovered-390')
      assert.equal(writes.length, count)
    } else if (current === 'reject') {
      mode = 'revision'; await assessment.getByRole('button', { name: 'Check saved assessment', exact: true }).click()
      await assessment.getByRole('button', { name: 'Finish requested assessment', exact: true }).waitFor(); await capture('assessment-confirmed-missing-390')
      assert.equal(writes.length, count)
      await assessment.getByRole('button', { name: 'Finish requested assessment', exact: true }).click(); await confirmed(); await capture('assessment-rejected-finished-390')
      assert.equal(writes.at(-1).body.request_id, original)
    }
  }
  mode = 'unavailable'; seedValues(); await enter(); await requestAssessment(); await confirmed()
  mode = 'lost_retry'; await assessment.getByRole('button', { name: 'Retry the original assessment', exact: true }).click()
  await assessment.getByRole('alert').waitFor(); await capture('assessment-retry-lost-390')
  const count = writes.length
  mode = 'revision'; await enter({ reset: false }); await assessment.getByRole('button', { name: 'Check saved assessment', exact: true }).click()
  await confirmed(); await capture('assessment-retry-recovered-390'); assert.equal(writes.length, count)
  assert.ok(writes.every(item => item.path.endsWith('/automatic-reviews') || item.path.endsWith('/retry') || item.path.endsWith('/decisions/value_review')))
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  for (const item of review.captures) {
    assert.equal(item.pageWidth, item.viewport.width, item.id + ' horizontal overflow')
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/${item.id}.axe.json`, 'utf8')), [], item.id + ' accessibility')
  }
  review.observations.push({ synthetic: true, explicitWrites: writes.length, liveModelCalls: 0, creditAwarded: 0, staffTasks: 0 })
} catch (error) {
  console.error('Assessment check failed:', error); review.observations.push({ failed: true, message: String(error) }); throw error
} finally { await review.flush(); await review.browser.close() }
