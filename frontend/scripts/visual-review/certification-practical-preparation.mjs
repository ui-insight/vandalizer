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
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5292', resetStorage: false })
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
  await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
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
try {
  const widths = process.env.REVIEW_WIDTHS === 'none' ? [] : (process.env.REVIEW_WIDTHS || '320,390,1440').split(',').map(Number)
  assert.ok(widths.every(width => [320, 390, 1440].includes(width)), 'Unsupported review width')
  for (const width of widths) {
    mode = 'success'
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 }); await enter()
    await capture('preparation-entry-' + width)
    await choose(); await preparation.getByRole('combobox', { name: 'My extraction', exact: true }).scrollIntoViewIfNeeded()
    await capture('preparation-choice-' + width)
    await submit(); await ready()
    await panel.getByRole('combobox', { name: 'Saved run', exact: true }).waitFor()
    assert.equal(await panel.getByText('No assessed runs are saved for this module yet. Your review will be available here when a run is prepared.', { exact: true }).count(), 0)
    await capture('preparation-ready-' + width)
    await preparation.getByText('Preparation reference', { exact: true }).click()
    await preparation.getByText('Preparation reference', { exact: true }).scrollIntoViewIfNeeded()
    await capture('preparation-reference-' + width)
    await preparation.getByRole('button', { name: 'Review proposed scope', exact: true }).click()
    await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Saved source and learner review')
    assert.equal(await panel.locator('input[type="radio"]:checked').count(), 0)
    assert.equal(await panel.getByRole('combobox', { name: 'Source I would authorize', exact: true }).inputValue(), '')
    await capture('preparation-scope-handoff-' + width)
  }
  await page.setViewportSize({ width: 390, height: 844 })
  for (const state of process.env.REVIEW_PREPARATION_RECOVERY === '0' ? [] : ['empty', 'list_error', 'reject', 'lost', 'partial', 'mismatch']) {
    mode = state; await enter()
    if (['empty', 'list_error'].includes(state)) {
      await preparation.getByRole('button', { name: 'Choose my extraction', exact: true }).click()
      if (state === 'empty') await preparation.getByText('No matching extractions found.', { exact: true }).scrollIntoViewIfNeeded()
      else await preparation.getByRole('alert').scrollIntoViewIfNeeded()
    } else { await choose(); await submit(); await preparation.getByRole('alert').scrollIntoViewIfNeeded() }
    await capture('preparation-' + state + '-390')
    if (state === 'reject') assert.equal(await preparation.getByRole('combobox', { name: 'My extraction', exact: true }).isEnabled(), true)
    if (state === 'lost' || state === 'partial') {
      const original = writes.at(-1).body, count = writes.length
      if (state === 'lost') {
        mode = 'history_error'; await enter({ reset: false })
        await preparation.getByRole('button', { name: 'Check and finish saved preparation', exact: true }).click()
        await preparation.getByRole('alert').scrollIntoViewIfNeeded(); await capture('preparation-history-unavailable-390')
        assert.equal(writes.length, count)
      }
      mode = 'success'
      await preparation.getByRole('button', { name: 'Check and finish saved preparation', exact: true }).click()
      await ready(); await capture('preparation-' + state + '-recovered-390')
      assert.equal(writes.length, count + (state === 'partial' ? 1 : 0))
      if (state === 'partial') assert.deepEqual(writes.at(-1).body, original)
    }
  }
  assert.ok(writes.every(value => value.path.endsWith('/practical-runs')))
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  for (const item of review.captures) {
    assert.equal(item.pageWidth, item.viewport.width, item.id + ' horizontal overflow')
    assert.deepEqual(JSON.parse(await readFile(`${review.out}/${item.id}.axe.json`, 'utf8')), [], item.id + ' accessibility')
  }
  review.observations.push({ synthetic: true, preparationRequests: writes.length, modelCalls: 0, creditAwarded: 0, decisionSubmissions: 0 })
} catch (error) {
  console.error('Preparation check failed:', error)
  review.observations.push({ failed: true, message: String(error) })
  // A stalled renderer cannot reliably capture itself; keep the original
  // failure and completed captures instead of hanging on a second operation.
  throw error
} finally { await review.flush(); await review.browser.close() }
