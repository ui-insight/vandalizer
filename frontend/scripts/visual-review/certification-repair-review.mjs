import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { createReview } from './harness.mjs'

const data = new URL('../../../backend/certification-data/', import.meta.url)
const read = async name => JSON.parse(await readFile(new URL(name, data), 'utf8'))
const modules = await read('panel-modules.json'), structure = await read('course-structure.json')
const prompts = (await read('drafts/v5.0/extraction-engine-decisions.json')).map((prompt, index) => ({ ...prompt, prompt_sha256: String(index + 1).repeat(64) }))
const module = modules.find(item => item.id === 'extraction_engine')
module.decisionPrompts = prompts; module.assessment = null
const { expectations: _privateExpectations, ...authoredCase } = await read('drafts/v5.0/extraction-engine-repair.json')
const identity = { enrollment_id: 'qa-nih-repair', course_version: 'qa-nih-repair-draft', manifest_sha256: 'b'.repeat(64), course_title: 'Local NIH repair fixture', modules_total: modules.length, module_ids: modules.map(item => item.id), maximum_xp: 2675 }
const course = { ...identity, ...structure, versioned: true, prerequisites: Object.fromEntries(modules.map(item => [item.id, []])), modules }
const progress = { ...identity, learning_position: null, position_revision: 0, id: 'qa-progress', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, last_activity_date: null }
const runId = 'a'.repeat(32)
const source = execFileSync('/usr/local/bin/pdftotext', ['-layout', fileURLToPath(new URL('drafts/v5.0/documents/nih-r01-neuroscience.pdf', data)), '-'], { encoding: 'utf8' })
const fields = [
  { title: 'Total Budget', searchphrase: 'Full-project total budget in USD, not an annual allocation.', is_optional: false, enum_values: [] },
  { title: 'Postdoctoral Fellow Name', searchphrase: 'Named postdoctoral fellow; leave absent for TBD and never guess.', is_optional: true, enum_values: [] },
  { title: 'Human Subjects', searchphrase: 'Whether human participation is explicitly reported; do not infer No from absence.', is_optional: false, enum_values: ['Yes', 'No'] },
  { title: 'Vertebrate Animals', searchphrase: 'Whether vertebrate animal use is explicitly reported.', is_optional: false, enum_values: ['Yes', 'No'] },
]
const repair = { case: authoredCase, source_document_id: 'assigned-source', repair_case_sha256: 'f'.repeat(64) }
let runState = 'prepared', loseResponse = true, readOnly = false, invalid = false
const receipts = new Map(), writes = []
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5292', resetStorage: false })
const { page, context } = review
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.endsWith('/position')) {
    const body = request.postDataJSON(); progress.position_revision++
    progress.learning_position = { module_id: body.module_id, lesson_id: body.lesson_id, revision: 1, content_sha256: 'c'.repeat(64), saved_at: new Date().toISOString() }
    return route.fulfill({ json: { saved: true, ...identity, position_revision: progress.position_revision, learning_position: progress.learning_position } })
  }
  if (path.endsWith('/practical-runs')) return route.fulfill({ json: { enrollment_id: identity.enrollment_id, module_id: module.id, runs: [{ run_id: runId, state: runState }], older_runs_available: false,
    read_only_reason: readOnly ? 'Your saved course work is read-only; the original example, source and decisions remain available.' : null } })
  if (path.includes('/learner-decisions/')) {
    const record = receipts.get(path.split('/').at(-1))
    return route.fulfill({ status: record ? 200 : 404, json: record || { detail: 'Not found' } })
  }
  if (path.includes('/decisions/')) {
    const promptId = path.split('/decisions/')[1].split('/')[0], prompt = prompts.find(item => item.id === promptId)
    if (path.includes('/runs/')) return route.fulfill({ json: {
      enrollment_id: identity.enrollment_id, module_id: module.id, prompt, run_id: runId, run_state: runState,
      can_submit: !readOnly && runState === (prompt.phase === 'before_execution' ? 'prepared' : 'completed'),
      read_only_reason: readOnly ? 'Your saved course work is read-only; the original example, source and decisions remain available.' : null,
      lab_folder_id: 'Certification training lab', artifact: { title: 'Revised NIH extraction', fields },
      documents: [{ document_id: 'assigned-source', title: 'Assigned NIH proposal', text: source }],
      repair_case: invalid ? { ...repair, source_document_id: 'unrelated' } : repair,
      result: runState === 'completed' ? { entities: [{ 'Total Budget': '1250000', 'Postdoctoral Fellow Name': null, 'Human Subjects': 'No', 'Vertebrate Animals': 'Yes' }] } : null,
      latest_decision: [...receipts.values()].filter(item => item.prompt_id === promptId).at(-1) || null,
    } })
    assert.equal(request.method(), 'POST'); assert.equal(readOnly, false)
    const body = request.postDataJSON(); writes.push(body)
    assert.equal(body.repair_case_sha256, repair.repair_case_sha256)
    if (body.value_checks.some(check => check.source_quote && !source.includes(check.source_quote))) return route.fulfill({ status: 422, json: { detail: 'Each source check must cite the saved assigned document' } })
    const record = { uuid: body.request_id, enrollment_id: identity.enrollment_id, module_id: module.id, run_id: runId,
      prompt_id: promptId, prompt_sha256: prompt.prompt_sha256, submitted_at: new Date().toISOString(), submission: body, credit_awarded: false }
    receipts.set(record.uuid, record)
    if (loseResponse) { loseResponse = false; return route.fulfill({ status: 503, json: { detail: 'Synthetic lost response after save' } }) }
    return route.fulfill({ json: record })
  }
  return route.fallback()
})
const panel = page.getByRole('region', { name: 'Practical review', exact: true })
async function enter() {
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await page.getByRole('button', { name: /^4 Extraction Engine/ }).click()
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  await panel.getByRole('combobox', { name: 'Saved run', exact: true }).selectOption(runId)
  await panel.getByText('Revised NIH extraction', { exact: true }).waitFor()
}
async function capture(name) {
  if (process.env.REVIEW_TEXT_SCALE === '2') {
    const clipping = await panel.evaluate(root => [root, ...root.querySelectorAll('button,p,h4,h5,h6,summary,blockquote')].filter(el => el.clientWidth && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent.slice(0, 90)))
    assert.deepEqual(clipping, [], 'Enlarged repair text clips')
  }
  await review.capture(name, 'Synthetic owned NIH run/decision API responses and actual authored source/case; production frontend; no provider or credit.')
  console.log(name)
}
try {
  await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByText('Course progress and credential', { exact: true }).waitFor()
  await writeFile(resolve(review.out, 'entry-dom.txt'), await page.locator('body').ariaSnapshot())
  if (process.env.REVIEW_INSPECT_ONLY !== '1') {
    await enter()
    await panel.getByText('Inspect the original flawed example', { exact: true }).click()
    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
      await panel.getByRole('region', { name: 'Authored repair example', exact: true }).scrollIntoViewIfNeeded()
      await capture('authored-example-' + width)
      await panel.getByText('Revised NIH extraction', { exact: true }).scrollIntoViewIfNeeded()
      await capture('revised-fields-' + width)
    }
    await page.setViewportSize({ width: 390, height: 844 })
    await panel.getByText('Saved source: Assigned NIH proposal', { exact: true }).click()
    await panel.getByRole('region', { name: 'Saved source text: Assigned NIH proposal', exact: true }).focus()
    await capture('source-keyboard-390')
    await panel.getByLabel('This revised scope is ready to run', { exact: true }).check()
    await panel.getByRole('textbox', { name: 'Explain your decision', exact: true }).fill('I clarified the full-project budget, made the unnamed postdoc optional and constrained the categories before approving this revision.')
    await panel.getByRole('button', { name: 'Save my decision', exact: true }).click()
    await panel.getByRole('alert').waitFor(); await capture('lost-response-390')
    await panel.getByRole('button', { name: 'Check saved decision', exact: true }).click()
    await panel.getByRole('heading', { name: 'Decision saved', exact: true }).waitFor()
    assert.equal(await panel.getByLabel('Saved practical decision', { exact: true }).evaluate(el => el === document.activeElement), true)
    assert.equal(writes.length, 1); await capture('scope-recovered-390')
    runState = 'completed'
    await panel.getByRole('button', { name: 'Reload saved runs', exact: true }).click()
    await panel.getByText(/This run has already left preparation/).waitFor()
    await panel.getByRole('combobox', { name: 'Review stage', exact: true }).selectOption('repair_values')
    await panel.getByRole('region', { name: 'Saved extraction values', exact: true }).focus()
    await capture('revised-output-390')
    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
      await panel.getByRole('group', { name: 'Postdoctoral Fellow Name', exact: true }).scrollIntoViewIfNeeded()
      await capture('absence-check-' + width)
    }
    await panel.getByLabel('I cannot verify the revised result yet', { exact: true }).check()
    await panel.getByRole('textbox', { name: 'Explain your decision', exact: true }).fill('The postdoc is unnamed in the source; the other three values still need source checks.')
    for (const field of prompts[1].required_fields) await panel.getByRole('group', { name: field, exact: true }).getByRole('textbox', { name: 'What did you establish?', exact: true }).fill('I have not completed this check against the assigned source yet.')
    const postdoc = panel.getByRole('group', { name: 'Postdoctoral Fellow Name', exact: true })
    await postdoc.getByRole('combobox', { name: 'Source check', exact: true }).selectOption('supported')
    await postdoc.getByRole('textbox', { name: 'Exact source passage', exact: true }).fill('TBD')
    await postdoc.getByRole('textbox', { name: 'What did you establish?', exact: true }).fill('The personnel row lists TBD for the postdoc, so I did not invent a person.')
    await panel.getByRole('button', { name: 'Save my decision', exact: true }).click()
    await panel.getByRole('heading', { name: 'Decision saved', exact: true }).waitFor()
    await panel.getByText('Saved source checks', { exact: true }).click()
    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
      await panel.getByText('Checked value: Empty value (recorded as supported absence)', { exact: true }).scrollIntoViewIfNeeded()
      await capture('saved-absence-' + width)
    }
    const before = writes.length
    readOnly = true
    await panel.getByRole('button', { name: 'Reload saved runs', exact: true }).click()
    await panel.getByRole('button', { name: 'Save my decision', exact: true }).waitFor()
    await panel.getByRole('region', { name: 'Saved source and learner review', exact: true }).getByRole('status').waitFor()
    assert.equal(await panel.getByRole('button', { name: 'Save my decision', exact: true }).isEnabled(), false)
    await page.setViewportSize({ width: 390, height: 844 }); await capture('read-only-390')
    invalid = true
    await panel.getByRole('button', { name: 'Reload saved runs', exact: true }).click()
    await panel.getByRole('alert').waitFor(); await capture('mismatched-source-390')
    assert.equal(await panel.getByRole('button', { name: 'Save my decision', exact: true }).count(), 0)
    assert.equal(writes.length, before); assert.equal(receipts.size, 2); assert.equal(progress.total_xp, 0)
  }
  for (const item of review.captures) {
    assert.equal(item.pageWidth, item.viewport.width, item.id + ' horizontal overflow')
    assert.deepEqual(JSON.parse(await readFile(resolve(review.out, item.id + '.axe.json'), 'utf8')), [], item.id + ' accessibility')
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ synthetic: true, decisionWrites: writes.length, savedReceipts: receipts.size, modelCalls: 0, creditAwarded: 0 })
} catch (error) {
  console.error(error); review.observations.push({ failed: true, error: String(error) });
  await writeFile(resolve(review.out, 'failure-dom.txt'), await page.locator('body').ariaSnapshot().catch(() => 'DOM unavailable'))
  throw error
} finally { await review.flush(); await review.browser.close() }
