import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const session = JSON.parse(await readFile('/private/tmp/certification-outcome-selection-session.json', 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293')
assert.ok(session.database.startsWith('certification_qa_'))
const origin = session.api_origin
const before = await fetch(origin + '/qa/state').then(response => response.json())
const course = await fetch(origin + '/api/certification/course?enrollment_id=' + session.enrollment_id).then(response => response.json())
const module = course.modules.find(item => item.id === session.module_id)
assert.ok(module)
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Actual authenticated certification HTTP routes and original saved MongoDB receipts in a disposable database. Synthetic test learner, extraction provider and automatic judge. Read-only UI selection; no real grading or learner data.' })
const { page, context } = review
const requests = []
await context.route('**/api/certification/**', async route => {
  const req = route.request(), url = new URL(req.url())
  assert.equal(req.method(), 'GET', 'Selecting saved outcomes must remain read-only')
  const response = await fetch(origin + url.pathname + url.search)
  const body = await response.text()
  requests.push({ path: url.pathname + url.search, status: response.status })
  assert.equal(response.status, 200, `${url.pathname}: ${body}`)
  await route.fulfill({ status: response.status, contentType: 'application/json', body })
})
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded(); await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 }); await page.goto(review.baseURL + '/certification')
    const panel = page.locator('[data-cert-panel="true"]')
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    await panel.getByRole('button', { name: new RegExp(`^${module.number} ${module.title}`) }).click()
    await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
    const section = panel.getByRole('region', { name: 'Combined module outcomes', exact: true })
    await section.getByRole('button', { name: 'Choose saved assessments', exact: true }).click()
    const practical = section.getByRole('combobox', { name: 'Automatic assessment', exact: true })
    await practical.selectOption(session.review_id)
    const scenario = section.getByRole('combobox', { name: 'Scenario assessment', exact: true })
    assert.equal(await scenario.inputValue(), '')
    const check = section.getByRole('button', { name: 'Check selected assessments', exact: true })
    await check.click(); await section.getByRole('heading', { name: 'Select saved evidence', exact: true }).waitFor()
    const result = section.getByRole('region', { name: 'Module outcome result', exact: true })
    assert.equal(await result.getByText('Supported by selected evidence', { exact: true }).count(), 2)
    await capture(`missing-scenario-${width}`, result)
    await scenario.selectOption(session.failed_scenario_id); await check.click()
    await section.getByRole('heading', { name: 'Revision needed', exact: true }).waitFor()
    await capture(`selected-original-failure-${width}`, result)
    await scenario.selectOption(session.passed_scenario_id); await check.click()
    await section.getByRole('heading', { name: 'All draft outcomes supported', exact: true }).waitFor()
    assert.equal(await result.getByText('Supported by selected evidence', { exact: true }).count(), 3)
    await capture(`explicit-passing-pair-${width}`, result)
  }
  const after = await fetch(origin + '/qa/state').then(response => response.json())
  assert.deepEqual(after, before, 'Reading selected outcomes must preserve every database record and judge call count')
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  await writeFile(`${review.out}/persistence.json`, JSON.stringify({ before, after, requests, unchanged: true }, null, 2))
  review.observations.push({ actualSavedReceiptSelection: true, completeDatabaseUnchanged: true, judgeCallsUnchanged: true, certificationWrites: 0, realModelCalibration: false })
} catch (error) { await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
