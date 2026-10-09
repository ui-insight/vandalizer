import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const session = JSON.parse(await readFile('/private/tmp/certification-selection-recovery-session.json', 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293')
assert.ok(session.database.startsWith('certification_qa_'))
const origin = session.api_origin
const state = () => fetch(origin + '/qa/state').then(response => response.json())
const before = await state()
const review = await createReview({ resetStorage: false, output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5294',
  evidenceMode: 'Real course selection confirmation HTTP and disposable MongoDB. Synthetic published course, earned source and interrupted internal selections; no actual migration, live model, publication or external delivery.' })
const { page, context } = review
page.setDefaultTimeout(15000)
const requests = [], writes = [], snapshots = []
let mode = 'deliver'
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url()), method = request.method()
  assert.ok(method === 'GET' || (method === 'POST' && url.pathname === '/api/certification/selection-confirmations'), `Unexpected ${method} ${url.pathname}`)
  if (method === 'POST') {
    writes.push({ body: request.postDataJSON(), mode })
    if (mode === 'drop-request') return route.abort('failed')
  }
  const response = await fetch(origin + url.pathname + url.search, { method,
    ...(method === 'POST' ? { headers: { 'Content-Type': 'application/json' }, body: request.postData() } : {}) })
  const body = await response.text()
  requests.push({ path: url.pathname, method, status: response.status })
  assert.equal(response.status, 200, `${url.pathname}: ${body}`)
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
  await panel.getByRole('heading', { name: 'Finish confirming your course choice', exact: true }).waitFor()
  return panel
}
async function capture(id, section) {
  await section.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  const shot = review.captures.at(-1)
  assert.equal(shot.pageWidth, shot.viewport.width)
  const box = await section.boundingBox()
  assert.ok(box.x >= 0 && box.x + box.width <= shot.viewport.width, JSON.stringify(box))
  console.log(id)
}
try {
  let panel = await load()
  let section = panel.getByRole('region', { name: 'Finish confirming your course choice', exact: true })
  await capture('upgrade-pending', section)
  assert.equal(writes.length, 0)
  mode = 'drop-request'
  await section.getByRole('button', { name: 'Confirm saved course choice', exact: true }).focus()
  await page.keyboard.press('Enter')
  await section.getByRole('alert').waitFor()
  await capture('upgrade-request-lost', section)
  assert.deepEqual(await state(), before)
  panel = await load() // Fresh mounted component; original request is server-discovered.
  section = panel.getByRole('region', { name: 'Finish confirming your course choice', exact: true })
  await capture('reload-discovers-original-choice', section)
  mode = 'drop-response'
  await section.getByRole('button', { name: 'Confirm saved course choice', exact: true }).click()
  await section.getByRole('alert').waitFor()
  const committed = await state()
  assert.equal(committed.selection.pending_transition_id, null)
  await capture('upgrade-confirmation-reply-lost', section)
  mode = 'deliver'
  await section.getByRole('button', { name: 'Refresh switch status', exact: true }).click()
  section = panel.getByRole('region', { name: 'Course choice status', exact: true })
  await section.getByRole('status').waitFor()
  await capture('upgrade-recovered-by-read', section)
  assert.equal(writes.length, 2)
  assert.deepEqual(writes[0].body, writes[1].body)
  for (const action of ['return_to_original_course', 'resume_upgraded_course']) {
    const prepared = await fetch(origin + '/qa/next/' + action, { method: 'POST' }).then(response => response.json())
    panel = await load()
    section = panel.getByRole('region', { name: 'Finish confirming your course choice', exact: true })
    await capture(action + '-pending', section)
    if (!native) {
      await page.setViewportSize({ width: 1440, height: 1000 })
      await capture(action + '-desktop', section)
    }
    await section.getByRole('button', { name: 'Confirm saved course choice', exact: true }).click()
    section = panel.getByRole('region', { name: 'Course choice status', exact: true })
    await section.getByRole('status').waitFor()
    await capture(action + '-confirmed', section)
    const confirmed = await state()
    assert.equal(confirmed.selection.revision, prepared.selection.revision)
    assert.equal(confirmed.history_sha256, before.history_sha256)
    assert.equal(confirmed.enrollments, 2)
    assert.equal(confirmed.credentials, 1)
    snapshots.push({ action, prepared, confirmed })
    await section.getByRole('button', { name: 'Refresh my course', exact: true }).click()
  }
  const after = await state()
  assert.equal(after.history_sha256, before.history_sha256)
  assert.equal(after.selection.revision, 3)
  assert.equal(after.selection.pending_transition_id, null)
  assert.equal(writes.length, 4)
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  await writeFile(`${review.out}/persistence.json`, JSON.stringify({ before, after, snapshots, requests, writes }, null, 2))
  review.observations.push({ realConfirmationHttp: true, writesOnlyAfterClick: true, requestAndReplyLoss: true,
    originalChoiceDiscoveredAfterReload: true, originalCreditAndCredentialPreserved: true, staffActions: 0 })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
