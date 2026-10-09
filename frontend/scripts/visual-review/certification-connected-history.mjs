import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const session = JSON.parse(await readFile(process.env.CERTIFICATION_QA_SESSION, 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293')
assert.match(session.database, /^certification_qa_browser_[a-f0-9]{32}$/)
const prompts = JSON.parse(await readFile(new URL('../../../backend/certification-data/drafts/v5.0/foundations-decisions.json', import.meta.url), 'utf8'))
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5292', resetStorage: false })
const { page, context } = review
const calls = []
let loseExecution = true, loseAssessment = true
async function realAPI(route) {
  const request = route.request(), url = new URL(request.url())
  const response = await route.fetch({ url: session.api_origin + url.pathname + url.search })
  const call = { path: url.pathname, method: request.method(), status: response.status() }
  calls.push(call)
  if (call.method === 'POST' && response.ok() && call.path.endsWith('/execution') && loseExecution) {
    loseExecution = false
    return route.fulfill({ status: 503, json: { detail: 'QA response interrupted after actual saved execution' } })
  }
  if (call.method === 'POST' && response.ok() && call.path.endsWith('/automatic-reviews') && loseAssessment) {
    loseAssessment = false
    return route.fulfill({ status: 503, json: { detail: 'QA response interrupted after actual saved assessment' } })
  }
  if (!response.ok()) console.error('CERTIFICATION API', call, await response.text())
  return route.fulfill({ response })
}
await context.route('**/api/certification/**', realAPI)
await context.route('**/api/extractions/search-sets?**', realAPI)
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
async function proof() { const response = await context.request.get(session.api_origin + '/qa/state'); assert.equal(response.status(), 200); return response.json() }
async function capture(id) {
  await review.capture(id, 'Production frontend connected to real certification HTTP handlers and disposable MongoDB. Authentication and extraction/judge providers are synthetic; other workspace APIs use UI fixtures.')
  const item = review.captures.at(-1)
  assert.equal(item.pageWidth, item.viewport.width, 'Horizontal overflow')
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [], 'Accessibility violations')
  console.log(id)
}
const panel = page.getByRole('region', { name: 'Practical review', exact: true })
const preparation = page.getByRole('region', { name: 'Prepare a practical run', exact: true })
const execution = page.getByRole('region', { name: 'Execute saved practical run', exact: true })
const assessment = page.getByRole('region', { name: 'Request automatic assessment', exact: true })
try {
  const before = await proof()
  assert.equal(before.runs, 1); assert.equal(before.reviews, 1)
  const runsResponse = await context.request.get(session.api_origin + '/api/certification/modules/foundations/practical-runs?enrollment_id=' + session.enrollment_id)
  assert.equal(runsResponse.status(), 200)
  const listing = await runsResponse.json(); assert.equal(listing.runs.length, 1)
  const runId = listing.runs[0].run_id
  const history = page.getByRole('region', { name: 'Saved course work', exact: true })
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
    await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
    await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    await page.getByText('Course progress and credential', { exact: true }).click()
    await history.getByRole('button', { name: 'Browse saved course work', exact: true }).click()
    await history.getByRole('combobox', { name: 'Saved course', exact: true }).selectOption(session.enrollment_id)
    await history.getByRole('combobox', { name: 'Saved module', exact: true }).selectOption('foundations')
    await panel.getByRole('combobox', { name: 'Saved run', exact: true }).selectOption(runId)
    await panel.getByRole('combobox', { name: 'Review stage', exact: true }).selectOption('value_review')
    await panel.getByRole('region', { name: 'Saved extraction values', exact: true }).focus(); await capture('connected-history-values-' + width)
    assert.equal(await panel.getByRole('button', { name: 'Save my decision', exact: true }).isEnabled(), false)
    assert.equal(await panel.getByRole('heading', { name: 'Decision saved', exact: true }).count(), 1)
    assert.equal(await panel.getByRole('region', { name: 'Execute saved practical run', exact: true }).count(), 0)
    const reviews = panel.getByRole('region', { name: 'Saved automatic assessments', exact: true })
    await reviews.getByRole('button', { name: 'View saved assessments', exact: true }).click()
    await reviews.getByRole('button', { name: /^Assessment 1 · Revision needed/ }).click()
    await reviews.getByRole('region', { name: 'Saved assessment result', exact: true }).waitFor()
    await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Saved assessment result')
    await capture('connected-history-feedback-' + width)
  }
  const after = await proof(); assert.deepEqual(after, before)
  assert.ok(calls.every(call => call.method === 'GET'))
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  await writeFile(`${review.out}/persistence-proof.json`, JSON.stringify({ before, after, calls }, null, 2))
  review.observations.push({ certificationAPI: 'real HTTP handlers and disposable MongoDB', testAuthentication: true, providersStubbed: true, historyOnly: true, noWrites: true })
} catch (error) {
  console.error('Connected history failed:', error); review.observations.push({ failed: true, message: String(error) })
  await writeFile(`${review.out}/api-calls.json`, JSON.stringify(calls, null, 2)); throw error
} finally { await review.flush(); await review.browser.close() }
