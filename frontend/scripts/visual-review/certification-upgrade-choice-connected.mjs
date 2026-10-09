import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const session = JSON.parse(await readFile('/private/tmp/certification-upgrade-choice-session.json', 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293')
assert.ok(session.database.startsWith('certification_qa_'))
const state = () => fetch(session.api_origin + '/qa/state').then(response => response.json())
const before = await state()
assert.equal(before.enrollments, 1)
const review = await createReview({ resetStorage: false, output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5294',
  evidenceMode: 'Actual optional upgrade/return/resume HTTP and MongoDB in agentic-chat panel; synthetic partial credit and verified fixture release flags. No live grading or production migration.' })
const { page, context } = review
page.setDefaultTimeout(15000)
const requests = [], writes = []
let loseChoiceReply = true, loseSwitchRequest = true, loseSwitchReply = true, loseReturnReply = true
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url()), method = request.method()
  const allowed = ['/api/certification/upgrade-choices', '/api/certification/upgrade-activations', '/api/certification/saved-course-selections']
  assert.ok(method === 'GET' || method === 'POST' && allowed.includes(url.pathname), `Unexpected ${method} ${url.pathname}`)
  if (method === 'POST') writes.push({ path: url.pathname, body: request.postDataJSON() })
  if (method === 'POST' && url.pathname.endsWith('/upgrade-activations') && loseSwitchRequest) {
    loseSwitchRequest = false
    return route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail: 'Synthetic undelivered request' }) })
  }
  const response = await fetch(session.api_origin + url.pathname + url.search, { method,
    ...(method === 'POST' ? { headers: { 'Content-Type': 'application/json' }, body: request.postData() } : {}) })
  const body = await response.text()
  requests.push({ path: url.pathname, method, status: response.status })
  assert.ok(response.status === 200 || method === 'GET' && /upgrade-activations\//.test(url.pathname) && response.status === 404, `${url.pathname}: ${body}`)
  if (method === 'POST' && ((url.pathname.endsWith('/upgrade-choices') && loseChoiceReply) || (url.pathname.endsWith('/upgrade-activations') && loseSwitchReply) || (url.pathname.endsWith('/saved-course-selections') && loseReturnReply))) {
    if (url.pathname.endsWith('/upgrade-choices')) loseChoiceReply = false
    if (url.pathname.endsWith('/upgrade-activations')) loseSwitchReply = false
    if (url.pathname.endsWith('/saved-course-selections')) loseReturnReply = false
    return route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ detail: 'Synthetic lost successful reply' }) })
  }
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
  return panel
}
async function comparison(panel) {
  await panel.getByRole('button', { name: 'Compare course versions', exact: true }).click()
  await panel.getByRole('button', { name: /^Compare / }).filter({ hasNotText: 'course versions' }).click()
  await panel.getByRole('button', { name: 'Review upgrade choice', exact: true }).click()
  return panel.getByRole('region', { name: 'Optional upgrade choice', exact: true })
}
async function capture(id, region) {
  await region.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  const shot = review.captures.at(-1), box = await region.boundingBox()
  assert.equal(shot.pageWidth, shot.viewport.width)
  assert.ok(box.x >= 0 && box.x + box.width <= shot.viewport.width)
  console.log(id)
}
try {
  let panel = await load()
  let region = await comparison(panel)
  await region.getByRole('checkbox').waitFor()
  assert.equal(writes.length, 0)
  assert.deepEqual(await state(), before)
  await capture('optional-preservation-mobile', region)
  if (!native) {
    await page.setViewportSize({ width: 1440, height: 1000 })
    await capture('optional-preservation-desktop', region)
  }
  await region.getByRole('checkbox').check()
  await region.getByRole('button', { name: 'Save my upgrade choice', exact: true }).click()
  await region.getByRole('button', { name: 'Check saved choice', exact: true }).waitFor()
  await capture('lost-preservation-reply', region)
  await region.getByRole('button', { name: 'Check saved choice', exact: true }).click()
  await region.getByRole('button', { name: /^Switch to / }).waitFor()
  assert.equal((await state()).selection.active_enrollment_id, before.source_id)
  panel = await load()
  region = await comparison(panel)
  await region.getByRole('button', { name: /^Switch to / }).waitFor()
  assert.equal(writes.length, 1)
  await capture('reloaded-original-choice', region)
  await region.getByRole('button', { name: /^Switch to / }).click()
  await region.getByRole('button', { name: 'Check saved switch', exact: true }).click()
  await region.getByText(/No saved switch was found/).waitFor()
  await capture('undelivered-switch-readback', region)
  await region.getByRole('button', { name: /^Switch to / }).click()
  await region.getByRole('button', { name: 'Check saved switch', exact: true }).click()
  await region.getByText(/course choice has a saved receipt/).waitFor()
  await capture('saved-upgrade-receipt', region)
  const upgraded = await state()
  assert.equal(upgraded.source_sha256, before.source_sha256)
  assert.deepEqual(upgraded.xp, [0, 125])
  assert.equal(upgraded.enrollments, 2)
  assert.equal(upgraded.decisions, 1)
  assert.equal(upgraded.activations, 1)
  assert.equal(upgraded.selection.revision, 1)
  assert.equal(upgraded.selection.pending_transition_id, null)
  assert.deepEqual(writes[1].body, writes[2].body)
  await region.getByRole('button', { name: 'Refresh my course', exact: true }).click()
  for (const action of ['Return to original course', 'Resume upgraded course']) {
    panel = await load()
    await panel.getByRole('button', { name: 'Choose a saved course', exact: true }).click()
    const choices = panel.getByRole('region', { name: 'Continue a saved course', exact: true })
    await choices.getByRole('button', { name: /^Review / }).click()
    region = choices.getByRole('region', { name: 'Saved course preservation review', exact: true })
    await region.getByRole('checkbox').waitFor()
    await region.getByText(`Course version: ${session.target_version}`, { exact: true }).waitFor()
    await capture(action.startsWith('Return') ? 'review-return' : 'review-resume', region)
    await region.getByRole('checkbox').check()
    await region.getByRole('button', { name: action, exact: true }).click()
    if (action.startsWith('Return')) await region.getByRole('button', { name: 'Check saved switch', exact: true }).click()
    await region.getByText(/course choice has a saved receipt/).waitFor()
    await capture(action.startsWith('Return') ? 'returned-original' : 'resumed-upgrade', region)
    const current = await state()
    assert.equal(current.history_sha256, upgraded.history_sha256)
    assert.equal(current.source_sha256, before.source_sha256)
    assert.equal(current.selection.active_enrollment_id, action.startsWith('Return') ? before.source_id : upgraded.selection.active_enrollment_id)
    assert.equal(current.selection.pending_transition_id, null)
  }
  const after = await state()
  assert.equal(after.selection.revision, 3)
  assert.equal(after.saved_selections, 2)
  assert.equal(writes.length, 5)
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  await writeFile(`${review.out}/persistence.json`, JSON.stringify({ before, upgraded, after, requests, writes }, null, 2))
  review.observations.push({ explicitPreservationThenSwitch: true, originalChoiceAcrossReload: true, noAutomaticPostRetry: true,
    exactOriginalRequestAfterReadback: true, sourceAndTargetWorkPreserved: true, returnedAndResumedWithoutDuplicateEnrollment: true })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
