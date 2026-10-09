import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const session = JSON.parse(await readFile('/private/tmp/certification-selected-completion-session.json', 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293')
assert.equal(session.completion_enabled, true)
assert.ok(session.database.startsWith('certification_qa_'))
const origin = session.api_origin
const state = () => fetch(origin + '/qa/state').then(response => response.json())
const before = await state()
assert.equal(before.progress.total_xp, 0)
const course = await fetch(origin + '/api/certification/course?enrollment_id=' + session.enrollment_id).then(response => response.json())
assert.equal(course.selected_outcome_completion, true)
const module = course.modules.find(item => item.id === session.module_id)
assert.equal(course.modules.length, 1)
const review = await createReview({ resetStorage: false, output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Real completion HTTP routes and MongoDB with a synthetic one-module published course and original saved suite/repair/review/scenario receipts. Synthetic judge; no actual learner, production release or live calibration.' })
const { page, context } = review
page.setDefaultTimeout(15000)
const requests = [], completions = []
let mode = 'drop-request'
await context.route('**/api/certification/**', async route => {
  const req = route.request(), url = new URL(req.url()), method = req.method()
  assert.ok(method === 'GET' || (method === 'POST' && url.pathname.endsWith('/complete')), `Unexpected mutation ${method} ${url.pathname}`)
  if (method === 'POST') {
    completions.push({ path: url.pathname + url.search, body: req.postDataJSON(), mode })
    if (mode === 'drop-request') { await route.abort('failed'); return }
  }
  const response = await fetch(origin + url.pathname + url.search, { method, ...(method === 'POST' ? { headers: { 'Content-Type': 'application/json' }, body: req.postData() } : {}) })
  const body = await response.text()
  requests.push({ path: url.pathname + url.search, method, status: response.status })
  assert.equal(response.status, 200, `${url.pathname}: ${body}`)
  if (method === 'POST' && mode === 'drop-response') { await route.abort('failed'); return }
  await route.fulfill({ status: response.status, contentType: 'application/json', body })
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
const width = native ? 780 : 320
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded(); await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  const shot = review.captures.at(-1)
  assert.equal(shot.pageWidth, shot.viewport.width)
  console.log(id)
}
async function load() {
  await page.goto(review.baseURL + '/certification')
  if (native) await review.setBrowserZoom(2)
  const panel = page.locator('[data-cert-panel="true"]')
  await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  return panel
}
try {
  await page.setViewportSize({ width, height: native ? 1700 : 900 })
  let panel = await load()
  await panel.getByRole('button', { name: new RegExp(`^${module.number} ${module.title}`) }).click()
  await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
  const section = panel.getByRole('region', { name: 'Combined module outcomes', exact: true })
  await section.getByRole('button', { name: 'Choose saved assessments', exact: true }).click()
  const practical = section.getByRole('combobox', { name: 'Automatic assessment', exact: true })
  await practical.selectOption(session.review_id)
  const scenario = section.getByRole('combobox', { name: 'Scenario assessment', exact: true })
  await scenario.selectOption(session.failed_scenario_id)
  const check = section.getByRole('button', { name: 'Check selected assessments', exact: true })
  await check.click(); await section.getByRole('heading', { name: 'Revision needed', exact: true }).waitFor()
  const complete = section.getByRole('button', { name: 'Complete module with selected evidence', exact: true })
  assert.equal(await complete.isEnabled(), false)
  await capture('original-failure-cannot-complete', complete)
  await scenario.selectOption(session.passed_scenario_id); await check.click()
  await section.getByRole('heading', { name: 'All required outcomes supported', exact: true }).waitFor()
  assert.equal(await complete.isEnabled(), true)
  await capture('explicit-passing-evidence', complete)
  await complete.focus(); await page.keyboard.press('Enter')
  await section.getByRole('alert').filter({ hasText: 'Completion could not be confirmed' }).waitFor()
  const notice = panel.getByRole('region', { name: 'Pending certification completion', exact: true })
  await capture('request-never-arrived', notice)
  assert.equal((await state()).progress.total_xp, 0)
  mode = 'drop-response'
  panel = await load()
  await capture('reload-retains-original-request', panel.getByRole('region', { name: 'Pending certification completion', exact: true }))
  await panel.getByRole('button', { name: 'Resume original completion', exact: true }).click()
  await page.getByText('Completion could not be confirmed. Resume the original request to finish or retrieve its saved result.', { exact: true }).waitFor()
  const saved = await state()
  assert.equal(saved.progress.certified, true)
  assert.equal(saved.judge_calls, before.judge_calls)
  await capture('response-lost-after-real-credit', panel.getByRole('region', { name: 'Pending certification completion', exact: true }))
  mode = 'deliver'
  panel = await load()
  await capture('saved-credit-and-pending-confirmation', panel.getByRole('region', { name: 'Pending certification completion', exact: true }))
  await panel.getByRole('button', { name: 'Resume original completion', exact: true }).click()
  const celebration = page.getByRole('dialog', { name: 'Course complete', exact: true })
  await celebration.waitFor()
  assert.equal(await celebration.getByRole('img', { name: /stars/ }).count(), 0)
  await capture('replayed-course-completion', celebration.getByRole('button', { name: 'View Certificate', exact: true }))
  await celebration.getByRole('button', { name: 'View Certificate', exact: true }).click()
  await capture('earned-credential', panel.getByRole('button', { name: /Download.*Certificate/i }).first())
  const after = await state()
  assert.equal(after.progress.total_xp, saved.progress.total_xp)
  assert.equal(after.judge_calls, before.judge_calls)
  assert.equal(completions.length, 3)
  for (const request of completions) {
    assert.equal(request.path, completions[0].path)
    assert.deepEqual(request.body, { consent: 'complete_selected_saved_outcomes', review_attempt_id: session.review_id, scenario_attempt_id: session.passed_scenario_id })
  }
  assert.equal(after.counts.certification_attempts, 1)
  assert.equal(after.counts.certification_credentials, 1)
  if (!native) {
    await page.setViewportSize({ width: 1440, height: 1000 })
    await capture('earned-credential-desktop', panel.getByRole('button', { name: /Download.*Certificate/i }).first())
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  await writeFile(`${review.out}/persistence.json`, JSON.stringify({ before, saved, after, requests, completions }, null, 2))
  review.observations.push({ actualSelectedCompletion: true, lostRequestAndLostResponseRecovered: true, identicalOriginalRequest: true, oneCredential: true, oneCreditAward: true, originalJudgeCalls: after.judge_calls, realModelCalibration: false })
} catch (error) { await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
