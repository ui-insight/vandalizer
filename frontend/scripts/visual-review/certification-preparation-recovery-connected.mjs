import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const session = JSON.parse(await readFile('/private/tmp/certification-preparation-recovery-session.json', 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293')
assert.ok(session.database.startsWith('certification_qa_'))
const origin = session.api_origin
const state = () => fetch(origin + '/qa/state').then(response => response.json())
const before = await state()
const review = await createReview({ resetStorage: false, output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5294',
  evidenceMode: 'Actual learner recovery HTTP/MongoDB against a paused synthetic selection worker. Interrupt recovery after ownership claim; preserve original earned history. No actual accounts, model calls, publication or external delivery.' })
const { page, context } = review
page.setDefaultTimeout(15000)
const requests = [], writes = []
let mode = 'drop-request'
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url()), method = request.method()
  assert.ok(method === 'GET' || (method === 'POST' && url.pathname === '/api/certification/selection-preparation-recoveries'), `Unexpected ${method} ${url.pathname}`)
  if (method === 'POST') {
    writes.push({ body: request.postDataJSON(), mode })
    if (mode === 'drop-request') return route.abort('failed')
  }
  const response = await fetch(origin + url.pathname + url.search, { method,
    ...(method === 'POST' ? { headers: { 'Content-Type': 'application/json' }, body: request.postData() } : {}) })
  const body = await response.text()
  requests.push({ path: url.pathname, method, status: response.status })
  assert.ok(response.status === 200 || (method === 'POST' && response.status === 409), `${url.pathname}: ${body}`)
  if (method === 'POST' && mode === 'drop-response') return route.abort('failed')
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
  await panel.getByRole('heading', { name: 'Keep your current course', exact: true }).waitFor()
  return panel
}
async function capture(id, section) {
  await section.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  const shot = review.captures.at(-1)
  assert.equal(shot.pageWidth, shot.viewport.width)
  const box = await section.boundingBox()
  assert.ok(box.x >= 0 && box.x + box.width <= shot.viewport.width)
  console.log(id)
}
try {
  let panel = await load()
  let section = panel.getByRole('region', { name: 'Keep your current course', exact: true })
  await capture('preparing-current-course-preserved', section)
  assert.equal(writes.length, 0)
  if (!native) {
    await page.setViewportSize({ width: 1440, height: 1000 })
    await capture('preparing-desktop', section)
    await page.setViewportSize({ width: 320, height: 1000 })
  }
  await section.getByRole('button', { name: 'Stop course-change preparation', exact: true }).focus()
  await page.keyboard.press('Enter')
  await section.getByRole('alert').waitFor()
  await capture('stop-request-lost', section)
  assert.deepEqual(await state(), before)
  mode = 'deliver'
  panel = await load()
  section = panel.getByRole('region', { name: 'Keep your current course', exact: true })
  await section.getByRole('button', { name: 'Stop course-change preparation', exact: true }).click()
  await section.getByRole('alert').waitFor()
  await capture('recovery-claim-interrupted', section)
  await section.getByRole('button', { name: 'Refresh switch status', exact: true }).click()
  await section.getByRole('button', { name: 'Finish stopping preparation', exact: true }).waitFor()
  await capture('original-recovery-discovered', section)
  assert.equal(writes.length, 2)
  panel = await load()
  section = panel.getByRole('region', { name: 'Keep your current course', exact: true })
  await section.getByRole('button', { name: 'Finish stopping preparation', exact: true }).waitFor()
  await capture('reload-retains-original-recovery', section)
  mode = 'drop-response'
  await section.getByRole('button', { name: 'Finish stopping preparation', exact: true }).click()
  await section.getByRole('alert').waitFor()
  await capture('stopped-reply-lost', section)
  assert.equal((await state()).in_flight_writes, 0)
  mode = 'deliver'
  await section.getByRole('button', { name: 'Refresh switch status', exact: true }).click()
  section = panel.getByRole('region', { name: 'Course choice status', exact: true })
  await section.getByRole('status').waitFor()
  await capture('read-confirms-no-pending-switch', section)
  await section.getByRole('button', { name: 'Refresh my course', exact: true }).click()
  const after = await fetch(origin + '/qa/resume-old-worker', { method: 'POST' }).then(response => response.json())
  assert.equal(after.history_sha256, before.history_sha256)
  assert.equal(after.active_enrollment_id, before.active_enrollment_id)
  assert.equal(after.revision, before.revision)
  assert.equal(after.recovery_records, 1)
  assert.equal(after.late_worker_rejected, true)
  assert.equal(after.in_flight_writes, 0)
  assert.equal(writes.length, 3)
  assert.ok(writes.every(item => JSON.stringify(item.body) === JSON.stringify(writes[0].body)))
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  await writeFile(`${review.out}/persistence.json`, JSON.stringify({ before, after, requests, writes }, null, 2))
  review.observations.push({ sourceSelectionPreserved: true, originalCreditAndCredentialPreserved: true,
    pausedLateWorkerRejected: true, crossReloadRecovery: true, staffActions: 0 })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
