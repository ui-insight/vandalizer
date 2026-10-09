import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const data = new URL('../../../backend/certification-data/', import.meta.url)
const read = async name => JSON.parse(await readFile(new URL(name, data), 'utf8'))
const modules = await read('panel-modules.json'), structure = await read('course-structure.json')
const module = modules.find(item => item.id === 'foundations')
const prompts = (await read('drafts/v5.0/foundations-decisions.json')).map((prompt, i) => ({ ...prompt, prompt_sha256: String(i + 1).repeat(64) }))
Object.assign(module, { decisionPrompts: prompts, practicalPreparation: true, assessment: null })
const identity = { enrollment_id: 'execution-course', course_version: 'execution-fixture', manifest_sha256: 'a'.repeat(64), course_title: 'Local execution fixture', module_ids: modules.map(item => item.id), modules_total: modules.length, maximum_xp: 2675 }
const course = { ...structure, ...identity, versioned: true, prerequisites: Object.fromEntries(modules.map(item => [item.id, []])), modules }
const progress = { ...identity, user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, learning_position: null }
const runId = 'a'.repeat(32), writes = []
let mode = 'success', state = 'prepared', decision = null
const proposal = { case: await read('drafts/v5.0/foundations-proposal.json'), proposal_sha256: 'e'.repeat(64), original_source_id: 'wrong-source',
  source_options: [{ id: 'wrong-source', title: 'NIH neuroscience proposal' }, { id: 'assigned-source', title: 'Assigned NSF ecology proposal' }] }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5292', resetStorage: false })
const { page, context } = review
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
function receipt() {
  return { ...identity, module_id: module.id, input_snapshot_id: runId, run_id: runId, state, plan_sha256: 'b'.repeat(64),
    scope_decision_id: decision?.uuid || null, scope_decision_sha256: decision ? 'c'.repeat(64) : null,
    model_names: ['configured-extraction-model'], can_execute: state === 'prepared' && !!decision,
    blocked_reason: state === 'prepared' && !decision ? 'Record your scope approval for this saved run before execution' : null,
    started_at: state === 'completed' ? '2026-10-06T11:00:00Z' : null, finished_at: state === 'completed' ? '2026-10-06T11:00:01Z' : null,
    documents_executed: state === 'completed' ? 1 : null, result_available: state === 'completed', credit_awarded: false, module_completion_eligible: false }
}
function approved() { return { uuid: 'd'.repeat(32), enrollment_id: identity.enrollment_id, module_id: module.id, run_id: runId, prompt_id: 'scope_review', prompt_sha256: prompts[0].prompt_sha256,
  submitted_at: '2026-10-06T10:59:00Z', credit_awarded: false, submission: { request_id: 'd'.repeat(32), run_id: runId, prompt_sha256: prompts[0].prompt_sha256,
    choice: 'approve', reason: 'I checked and selected the assigned NSF proposal before execution.', value_checks: [], proposal_selection: { proposal_sha256: proposal.proposal_sha256, source_id: 'assigned-source' } } } }
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  if (request.method() !== 'GET') writes.push({ path, body: request.postDataJSON() })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.endsWith('/practical-runs')) return route.fulfill({ json: { runs: [{ run_id: runId, state }], older_runs_available: false } })
  if (path.endsWith('/execution')) {
    assert.equal(url.searchParams.get('enrollment_id'), identity.enrollment_id)
    if (request.method() === 'GET') {
      if (mode === 'status_error') return route.fulfill({ status: 503, json: { detail: 'Synthetic status outage' } })
      return route.fulfill({ json: mode === 'mismatch' ? { ...receipt(), enrollment_id: 'foreign' } : receipt() })
    }
    assert.deepEqual(request.postDataJSON(), { plan_sha256: 'b'.repeat(64), scope_decision_id: decision.uuid, scope_decision_sha256: 'c'.repeat(64), consent: 'execute_saved_inputs' })
    if (mode === 'stale') return route.fulfill({ status: 409, json: { detail: 'Synthetic changed approval' } })
    assert.equal(state, 'prepared')
    state = 'completed'
    if (mode === 'lost') return route.fulfill({ status: 503, json: { detail: 'Synthetic response loss after execution' } })
    return route.fulfill({ json: receipt() })
  }
  if (path.includes('/decisions/') && path.includes('/runs/')) {
    const prompt = prompts.find(item => path.includes('/decisions/' + item.id + '/'))
    return route.fulfill({ json: { enrollment_id: identity.enrollment_id, module_id: module.id, prompt, run_id: runId, run_state: state,
      can_submit: prompt.phase === 'before_execution' ? state === 'prepared' : state === 'completed', lab_folder_id: 'Training lab',
      artifact: { title: 'Saved NSF proposal extraction', fields: ['PI Name', 'Total Budget', 'Project Period'].map(searchphrase => ({ searchphrase, is_optional: false })) },
      documents: [{ document_id: 'assigned-source', title: 'Assigned NSF ecology proposal', text: 'Synthetic saved source: PI Sarah Chen; total budget USD 485000; project period 2026 to 2029.' }],
      scope_proposal: proposal, result: state === 'completed' ? { entities: [{ 'PI Name': 'Sarah Chen', 'Total Budget': 'USD 485000', 'Project Period': '2026 to 2029' }] } : null,
      latest_decision: prompt.phase === 'before_execution' ? decision : null } })
  }
  if (path.endsWith('/decisions/scope_review') && request.method() === 'POST') {
    const body = request.postDataJSON()
    assert.equal(body.choice, 'approve'); assert.equal(body.proposal_selection.source_id, 'assigned-source')
    decision = { ...approved(), uuid: body.request_id, submission: body }
    return route.fulfill({ json: decision })
  }
  return route.fallback()
})
const panel = page.getByRole('dialog', { name: 'Learning and certification', exact: true })
const execution = page.getByRole('region', { name: 'Execute saved practical run', exact: true })
async function enter({ reset = true } = {}) {
  if (reset && page.url().startsWith(review.baseURL)) await page.evaluate(() => sessionStorage.clear())
  await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await panel.getByRole('button', { name: /1 Foundations/ }).click()
  await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
  await panel.getByRole('combobox', { name: 'Saved run', exact: true }).selectOption(runId)
  await panel.getByRole('heading', { name: 'Saved NSF proposal extraction', exact: true }).waitFor()
  await execution.getByRole('heading', { name: 'Execute your saved run', exact: true }).scrollIntoViewIfNeeded()
}
async function status() {
  await execution.getByRole('button', { name: 'Check execution status', exact: true }).click()
  await execution.getByRole('region', { name: 'Saved execution status', exact: true }).waitFor()
}
async function capture(id) {
  await review.capture(id, 'Synthetic approval and execution receipts. No live model, cost, credit or learner changes.')
  if (process.env.REVIEW_TEXT_SCALE === '2') {
    const overflow = await execution.evaluate(root => [root, ...root.querySelectorAll('button,p,h5,h6,summary')].filter(el => el.clientWidth && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent.slice(0, 80)))
    assert.deepEqual(overflow, [], 'Execution content clips at enlarged text')
  }
  console.log(id)
}
try {
  for (const width of [320, 390, 1440]) {
    mode = 'success'; state = 'prepared'; decision = null
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 }); await enter(); await status()
    await capture('execution-approval-needed-' + width)
    assert.equal(await execution.getByRole('button', { name: 'Run these saved inputs', exact: true }).count(), 0)
    await panel.getByRole('combobox', { name: 'Source I would authorize', exact: true }).selectOption('assigned-source')
    await panel.getByLabel(prompts[0].choices.approve, { exact: true }).check()
    await panel.getByLabel('Explain your decision', { exact: true }).fill('I compared the original NIH proposal and explicitly selected the assigned NSF ecology source.')
    await panel.getByRole('button', { name: 'Save my decision', exact: true }).click()
    await panel.getByRole('heading', { name: 'Decision saved', exact: true }).waitFor()
    const before = writes.length
    await status(); await execution.getByRole('button', { name: 'Run these saved inputs', exact: true }).scrollIntoViewIfNeeded()
    assert.equal(writes.length, before)
    await capture('execution-ready-' + width)
    await execution.getByRole('button', { name: 'Run these saved inputs', exact: true }).click()
    await execution.getByRole('heading', { name: 'Execution result saved', exact: true }).waitFor()
    await capture('execution-completed-' + width)
    await execution.getByText('Execution reference', { exact: true }).click(); await capture('execution-reference-' + width)
    await execution.getByRole('button', { name: 'Review saved values', exact: true }).click()
    const sourceReview = panel.getByRole('region', { name: 'Saved source and learner review', exact: true })
    await sourceReview.getByText('Saved extraction output', { exact: true }).waitFor()
    assert.equal(await panel.getByRole('combobox', { name: 'Review stage', exact: true }).inputValue(), 'value_review')
    await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Saved source and learner review')
    assert.equal(await sourceReview.evaluate(el => el === document.activeElement), true)
    await capture('execution-value-handoff-' + width)
  }
  await page.setViewportSize({ width: 390, height: 844 })
  for (const current of ['executing', 'failed', 'uncertain']) {
    mode = 'success'; state = current; decision = approved(); await enter(); await status(); await capture('execution-' + current + '-390')
    assert.equal(await execution.getByRole('button', { name: 'Run these saved inputs', exact: true }).count(), 0)
  }
  for (const current of ['status_error', 'mismatch']) {
    mode = current; state = 'prepared'; decision = approved(); await enter()
    await execution.getByRole('button', { name: 'Check execution status', exact: true }).click()
    await execution.getByRole('alert').waitFor(); await capture('execution-' + current + '-390')
  }
  for (const current of ['lost', 'stale']) {
    mode = current; state = 'prepared'; decision = approved(); await enter(); await status()
    await execution.getByRole('button', { name: 'Run these saved inputs', exact: true }).click()
    await execution.getByRole('alert').waitFor(); await capture('execution-' + current + '-390')
    const count = writes.length
    mode = 'success'; await enter({ reset: false }); await status(); await capture('execution-' + current + '-recovered-390')
    assert.equal(writes.length, count, 'Status recovery must not dispatch')
  }
  assert.ok(writes.every(item => item.path.endsWith('/execution') || item.path.endsWith('/decisions/scope_review')))
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  for (const item of review.captures) {
    assert.equal(item.pageWidth, item.viewport.width, item.id + ' horizontal overflow')
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/${item.id}.axe.json`, 'utf8')), [], item.id + ' accessibility')
  }
  review.observations.push({ synthetic: true, explicitExecutionRequests: writes.filter(item => item.path.endsWith('/execution')).length,
    scopeDecisionSubmissions: writes.filter(item => item.path.endsWith('/decisions/scope_review')).length, liveModelCalls: 0, creditAwarded: 0 })
} catch (error) {
  console.error('Execution check failed:', error); review.observations.push({ failed: true, message: String(error) }); throw error
} finally { await review.flush(); await review.browser.close() }
