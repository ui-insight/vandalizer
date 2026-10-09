import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const data = new URL('../../../backend/certification-data/', import.meta.url)
const read = async name => JSON.parse(await readFile(new URL(name, data), 'utf8'))
const modules = await read('panel-modules.json'), structure = await read('course-structure.json')
const module = modules.find(item => item.id === 'foundations')
const prompts = (await read('drafts/v5.0/foundations-decisions.json')).map((prompt, i) => ({ ...prompt, prompt_sha256: String(i + 1).repeat(64) }))
Object.assign(module, { decisionPrompts: prompts, practicalPreparation: true, assessment: null })
const identity = { enrollment_id: 'preparation-course', course_version: 'preparation-fixture', manifest_sha256: 'a'.repeat(64), course_title: 'Local preparation fixture', module_ids: modules.map(item => item.id), modules_total: modules.length, maximum_xp: 2675 }
const course = { ...structure, ...identity, versioned: true, prerequisites: Object.fromEntries(modules.map(item => [item.id, []])), modules }
const progress = { ...identity, user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, learning_position: null }
const extraction = { uuid: 'owned-extraction', title: 'NSF proposal fields — PI, budget and project period', set_type: 'extraction', user_id: 'reviewer', item_count: 3 }
const proposal = { case: await read('drafts/v5.0/foundations-proposal.json'), proposal_sha256: 'e'.repeat(64),
  original_source_id: 'course_asset:nih-r01-neuroscience.pdf', source_options: [
    { id: 'course_asset:nih-r01-neuroscience.pdf', title: 'nih-r01-neuroscience.pdf' },
    { id: 'assigned-source', title: 'Assigned NSF proposal' },
  ] }
const receipts = new Map(), writes = []
let mode = 'success'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5307', resetStorage: false })
const { page, context } = review
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
await context.route('**/api/extractions/search-sets*', route => {
  assert.equal(new URL(route.request().url()).searchParams.get('scope'), 'mine')
  if (mode === 'list_error') return route.fulfill({ status: 503, json: { detail: 'Synthetic list outage' } })
  return route.fulfill({ json: mode === 'empty' ? [] : [extraction, { ...extraction, uuid: 'empty-extraction', title: 'Empty extraction — add fields first', item_count: 0 }] })
})
function saved(body) {
  return { ...identity, ...body, input_snapshot_id: body.request_id, module_id: module.id, artifact_title: extraction.title,
    artifact_sha256: 'b'.repeat(64), captured_at: '2026-10-06T10:00:00Z', fields: ['PI Name', 'Total Budget', 'Project Period'],
    documents: [{ document_id: 'assigned-source', assigned_filename: 'nsf-proposal-alpine-ecology.pdf', source_sha256: 'c'.repeat(64) }],
    state: 'prepared', run_id: body.request_id, plan_sha256: 'd'.repeat(64), model_names: ['configured-review-model'],
    scope_prompt_id: 'scope_review', can_execute: false, credit_awarded: false, module_completion_eligible: false }
}
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  if (request.method() !== 'GET') writes.push({ path, body: request.postDataJSON() })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.endsWith('/practical-runs')) {
    assert.equal(url.searchParams.get('enrollment_id'), identity.enrollment_id)
    if (request.method() === 'GET') return route.fulfill({ json: { runs: [...receipts.values()].filter(value => value.run_id).map(value => ({ run_id: value.run_id, state: value.state })), older_runs_available: false } })
    assert.equal(request.method(), 'POST')
    const body = request.postDataJSON()
    assert.equal(body.artifact_id, extraction.uuid)
    assert.match(body.request_id, /^[a-f0-9]{32}$/)
    if (mode === 'reject') return route.fulfill({ status: 422, json: { detail: 'Provision the assigned documents before preparing this run' } })
    const value = saved(body)
    if (mode === 'partial') Object.assign(value, { state: 'inputs_saved', run_id: null, plan_sha256: null, model_names: [], scope_prompt_id: null })
    receipts.set(body.request_id, value)
    if (mode === 'lost' || mode === 'partial') return route.fulfill({ status: 503, json: { detail: 'Synthetic response loss or interrupted planning' } })
    return route.fulfill({ json: mode === 'mismatch' ? { ...value, enrollment_id: 'wrong-enrollment' } : value })
  }
  if (path.includes('/practical-preparations/')) {
    assert.equal(url.searchParams.get('enrollment_id'), identity.enrollment_id)
    if (mode === 'history_error') return route.fulfill({ status: 503, json: { detail: 'Synthetic history outage' } })
    const value = receipts.get(path.split('/').at(-1))
    return route.fulfill({ status: value ? 200 : 404, json: value || { detail: 'Unavailable' } })
  }
  if (path.includes('/decisions/') && path.includes('/runs/')) {
    const value = receipts.get(path.split('/').at(-1)), prompt = prompts.find(item => item.id === 'scope_review')
    assert.ok(value)
    return route.fulfill({ json: { enrollment_id: identity.enrollment_id, module_id: module.id, prompt,
      run_id: value.run_id, run_state: 'prepared', can_submit: true, lab_folder_id: 'Training lab',
      artifact: { title: value.artifact_title, fields: value.fields.map(searchphrase => ({ searchphrase, is_optional: false })) },
      documents: [{ document_id: 'assigned-source', title: 'Assigned NSF proposal', text: 'Synthetic saved source: National Science Foundation proposal, PI Sarah Chen, total budget USD 485000.' }],
      scope_proposal: proposal, result: null, latest_decision: null } })
  }
  return route.fallback()
})
const panel = page.getByRole('dialog', { name: 'Learning and certification', exact: true })
const preparation = page.getByRole('region', { name: 'Prepare a practical run', exact: true })
async function enter({ reset = true } = {}) {
  if (reset && page.url().startsWith(review.baseURL)) await page.evaluate(() => sessionStorage.clear())
  await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await panel.getByRole('button', { name: /1 Foundations/ }).click()
  await panel.getByRole('button', { name: 'Challenge', exact: true }).focus(); await panel.getByRole('button', { name: 'Challenge', exact: true }).press('Enter')
  await preparation.getByRole('heading', { name: 'Prepare a practical run', exact: true }).scrollIntoViewIfNeeded()
}
async function capture(id) {
  await review.capture(id, 'Synthetic owned extraction and preparation receipts. No real model, execution, grade or learner change.')
  if (process.env.REVIEW_TEXT_SCALE === '2' && id !== 'blocked') {
    const overflow = await preparation.evaluate(root => [root, ...root.querySelectorAll('button,p,h4,h5,li,summary')]
      .filter(el => el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1).map(el => ({ tag: el.tagName, text: el.textContent.slice(0, 80) })))
    assert.deepEqual(overflow, [], 'Preparation content clips at enlarged text')
  }
  console.log(id)
}
async function choose() {
  await preparation.getByRole('button', { name: 'Choose my extraction', exact: true }).click()
  await preparation.getByRole('combobox', { name: 'My extraction', exact: true }).selectOption(extraction.uuid)
}
async function submit() { await preparation.getByRole('button', { name: 'Save inputs and prepare for review', exact: true }).click() }
async function ready() { await preparation.getByRole('heading', { name: 'Ready for your scope review', exact: true }).scrollIntoViewIfNeeded() }

const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
let unblock = null, heldHandler = null
async function hold(fragment, method) {
  heldHandler = async route => {
    if (route.request().method() === method && new URL(route.request().url()).pathname.endsWith(fragment)) {
      await new Promise(resolve => { unblock = resolve })
    }
    return route.fallback()
  }
  await context.route('**/api/**', heldHandler)
}
async function release() { await context.unroute('**/api/**', heldHandler); unblock?.(); unblock = null }
async function pendingCapture(region, text, id) {
  const status = region.getByRole('status').filter({ hasText: text })
  await status.waitFor(); await status.scrollIntoViewIfNeeded()
  await capture(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1688 : 1000 })
    receipts.clear(); writes.length = 0
    await enter()
    await hold('/search-sets', 'GET')
    await preparation.getByRole('button', { name: 'Choose my extraction', exact: true }).click()
    await pendingCapture(preparation, 'Loading your extractions', 'preparation-listing-' + width)
    assert.equal(writes.length, 0); await release()
    await preparation.getByRole('combobox', { name: 'My extraction', exact: true }).selectOption(extraction.uuid)
    await hold('/practical-runs', 'POST'); await submit()
    await pendingCapture(preparation, 'Saving inputs and preparing', 'preparation-saving-' + width)
    await release(); await ready()
    const original = [...receipts.keys()][0], count = writes.length
    await enter({ reset: false }); await hold('/practical-preparations/' + original, 'GET')
    await preparation.getByRole('button', { name: 'Check and finish saved preparation', exact: true }).click()
    await pendingCapture(preparation, 'Checking the saved preparation', 'preparation-checking-' + width)
    await release(); await ready(); assert.equal(writes.length, count)
  }
  for (const item of review.captures) {
    assert.equal(item.pageWidth, item.viewport.width, item.id + ' overflow')
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/${item.id}.axe.json`, 'utf8')), [])
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ delayedSyntheticResponses: true, liveModels: 0, actualLearners: 0 })
} catch (error) {
  review.observations.push({ failed: true, message: String(error) }); throw error
} finally { unblock?.(); await review.flush(); await review.browser.close() }
