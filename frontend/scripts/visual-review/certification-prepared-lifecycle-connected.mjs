import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const session = JSON.parse(await readFile('/private/tmp/certification-prepared-lifecycle-session.json', 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293')
assert.ok(session.database.startsWith('certification_qa_'))
const origin = session.api_origin
const state = () => fetch(origin + '/qa/state').then(response => response.json())
const before = await state()
const targetId = Object.keys(before.lifecycle).find(id => before.lifecycle[id] === 'prepared')
assert.ok(targetId)
const sourceId = before.selection.active_enrollment_id
const review = await createReview({ resetStorage: false, output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5294',
  evidenceMode: 'Real owned course history and selection confirmation HTTP with disposable MongoDB. A synthetic target moves from prepared to awaiting confirmation to active; original work and credential stay unchanged.' })
const { page, context } = review
page.setDefaultTimeout(15000)
const requests = [], writes = []
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url()), method = request.method()
  assert.ok(method === 'GET' || (method === 'POST' && url.pathname === '/api/certification/selection-confirmations'), `Unexpected ${method} ${url.pathname}`)
  if (method === 'POST') writes.push(request.postDataJSON())
  const response = await fetch(origin + url.pathname + url.search, { method,
    ...(method === 'POST' ? { headers: { 'Content-Type': 'application/json' }, body: request.postData() } : {}) })
  const body = await response.text()
  requests.push({ path: url.pathname, method, status: response.status })
  assert.equal(response.status, 200, `${url.pathname}: ${body}`)
  return route.fulfill({ status: response.status, contentType: 'application/json', body })
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function load() {
  await page.setViewportSize({ width: native ? 780 : 320, height: native ? 1700 : 1000 })
  await page.goto(review.baseURL + '/certification')
  if (native) await review.setBrowserZoom(2)
  const panel = page.locator('[data-cert-panel="true"]')
  await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await panel.getByLabel('Your course', { exact: true }).waitFor()
  const curriculum = panel.getByRole('button', { name: 'Curriculum', exact: true })
  if (await curriculum.count()) await curriculum.click()
  const details = panel.locator('details').filter({ has: page.locator('summary').filter({ hasText: /^Course progress and credential$/ }) }).first()
  if (await details.getAttribute('open') === null) await details.locator('summary').first().click()
  await panel.getByRole('button', { name: 'Browse saved course work', exact: true }).click()
  await panel.getByRole('combobox', { name: 'Saved course', exact: true }).waitFor()
  return panel
}
async function inspect(panel, id) {
  await panel.getByRole('combobox', { name: 'Saved course', exact: true }).selectOption(id)
  const region = panel.getByRole('region', { name: 'Original course history', exact: true })
  await region.waitFor()
  return region
}
async function capture(id, region) {
  await region.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  const shot = review.captures.at(-1)
  assert.equal(shot.pageWidth, shot.viewport.width)
  const box = await region.boundingBox()
  assert.ok(box.x >= 0 && box.x + box.width <= shot.viewport.width)
  console.log(id)
}
try {
  let panel = await load()
  let region = await inspect(panel, targetId)
  await region.getByText(/Prepared course — not started/).waitFor()
  await region.getByText(/Preparation does not award credit/).waitFor()
  await capture('prepared-history-mobile', region)
  if (!native) {
    await page.setViewportSize({ width: 1440, height: 1000 })
    await capture('prepared-history-desktop', region)
  }
  assert.equal(writes.length, 0)
  assert.deepEqual(await state(), before)
  const committed = await fetch(origin + '/qa/commit-prepared', { method: 'POST' }).then(response => response.json())
  assert.equal(committed.lifecycle[targetId], 'prepared')
  assert.equal(committed.selection.active_enrollment_id, targetId)
  panel = await load()
  region = await inspect(panel, targetId)
  await region.getByText(/Selection awaiting confirmation/).waitFor()
  await capture('selected-awaiting-confirmation', region)
  await panel.getByRole('button', { name: 'Confirm saved course choice', exact: true }).click()
  await panel.getByRole('status').filter({ hasText: 'Your saved course choice is confirmed' }).waitFor()
  await panel.getByRole('button', { name: 'Reload course history', exact: true }).click()
  region = await inspect(panel, targetId)
  await region.getByText(/· Current course/).waitFor()
  await capture('confirmed-current-course', region)
  region = await inspect(panel, sourceId)
  await region.getByText(/· Retained course/).waitFor()
  await capture('original-retained-course', region)
  const after = await state()
  assert.equal(after.history_sha256, before.history_sha256)
  assert.deepEqual(after.lifecycle, { ...before.lifecycle, [targetId]: 'active' })
  assert.equal(after.credentials, before.credentials)
  assert.equal(after.enrollments, 2)
  assert.equal(after.selection.revision, before.selection.revision + 1)
  assert.equal(after.selection.pending_transition_id, null)
  assert.equal(writes.length, 1)
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  await writeFile(`${review.out}/persistence.json`, JSON.stringify({ before, committed, after, requests, writes }, null, 2))
  review.observations.push({ preparationNotPresentedAsStarted: true, onlyOriginalTargetPromoted: true,
    sourceHistoryAndCredentialPreserved: true, readsDoNotActivate: true })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
