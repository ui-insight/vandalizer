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
const bank = JSON.parse(await readFile(new URL('../../../backend/certification-data/drafts/v5.0/ai-literacy-scenarios.json', import.meta.url), 'utf8'))
const scenarioPosts = []
let originalReceipt = null
await context.route('**/api/certification/modules/ai_literacy/scenarios?**', async route => {
  const request = route.request()
  if (request.method() !== 'POST') return route.fallback()
  const url = new URL(request.url())
  const response = await route.fetch({ url: session.api_origin + url.pathname + url.search })
  calls.push({ path: url.pathname, method: 'POST', status: response.status() })
  scenarioPosts.push(request.postDataJSON())
  assert.equal(response.status(), 200, await response.text())
  const receipt = await response.json()
  if (!originalReceipt) {
    originalReceipt = receipt
    return route.fulfill({ status: 503, json: { detail: 'QA interrupted response after scenario receipt was saved' } })
  }
  assert.deepEqual(receipt, originalReceipt)
  return route.fulfill({ response })
})
try {
  const before = await proof()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await page.getByText('Course progress and credential', { exact: true }).waitFor()
  if (process.env.REVIEW_INSPECT_ONLY === '1') {
    const snapshot = await page.locator('body').ariaSnapshot()
    await writeFile(`${review.out}/entry-dom.txt`, snapshot)
    console.log(snapshot.split('\n').filter(line => line.includes('AI Literacy')).join('\n'))
    await review.flush(); await review.browser.close(); process.exit(0)
  }
  await page.getByRole('button', { name: 'AI Literacy Understanding AI for Research Administration ~10m 50 XP', exact: true }).click()
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  const scenarios = page.getByRole('region', { name: 'Scenario assessment', exact: true })
  for (const question of bank.questions) await scenarios.getByRole('radio', { name: question.choices[0].text, exact: true }).check()
  await scenarios.getByRole('button', { name: 'Submit scenario choices', exact: true }).click()
  await scenarios.getByRole('alert').waitFor(); await capture('connected-scenario-lost-response-390')
  await scenarios.getByRole('button', { name: 'Check saved scenario result', exact: true }).click()
  await scenarios.getByRole('heading', { name: 'Some scenario requirements need another look', exact: true }).waitFor()
  await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Saved scenario result')
  await capture('connected-scenario-recovered-390')
  assert.equal(scenarioPosts.length, 1, 'Checking the saved receipt must not submit again')
  assert.equal(originalReceipt.result.credit_awarded, false)
  const url = session.api_origin + '/api/certification/practical-history/' + session.enrollment_id + '/modules/ai_literacy/scenarios'
  const listing = await (await context.request.get(url)).json()
  assert.equal(listing.attempts.length, 1); assert.equal(listing.attempts[0].attempt_id, originalReceipt.attempt_id)
  const history = page.getByRole('region', { name: 'Saved course work', exact: true })
  for (const width of [320, 390, 1440]) {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
    await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
    await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    const back = page.getByRole('button', { name: 'Curriculum', exact: true })
    if (await back.count()) await back.click()
    await page.getByText('Course progress and credential', { exact: true }).click()
    await history.getByRole('button', { name: 'Browse saved course work', exact: true }).click()
    await history.getByRole('combobox', { name: 'Saved course', exact: true }).selectOption(session.enrollment_id)
    await history.getByRole('combobox', { name: 'Saved module', exact: true }).selectOption('ai_literacy')
    const saved = history.getByRole('region', { name: 'Saved scenario answers', exact: true })
    await saved.getByRole('button', { name: /^Open scenario result 1/ }).click()
    const result = saved.getByRole('region', { name: 'Original scenario result', exact: true })
    await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Original scenario result')
    await result.getByRole('heading', { name: 'More practice needed', exact: true }).scrollIntoViewIfNeeded()
    await capture('connected-scenario-history-' + width)
    for (const question of bank.questions) assert.equal(await result.getByText('Your recorded choice: ' + question.choices[0].text, { exact: true }).count(), 1)
    assert.equal(await saved.getByRole('radio').count(), 0)
  }
  const after = await proof(); assert.deepEqual(after, before)
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  await writeFile(`${review.out}/persistence-proof.json`, JSON.stringify({ before, after, scenarioPosts, originalReceipt, historyCount: listing.attempts.length, calls }, null, 2))
  review.observations.push({ certificationAPI: 'real HTTP handlers and disposable MongoDB', testAuthentication: true, providersStubbed: true,
    scenarioSubmissions: 1, recoveryUsesReadOnlyCheck: true, savedScenarioReceipts: 1, lostResponseRecovered: true, historyOnlyAfterRecovery: true, creditAwarded: 0 })
} catch (error) {
  console.error('Connected scenario failed:', error); review.observations.push({ failed: true, message: String(error) })
  await writeFile(`${review.out}/api-calls.json`, JSON.stringify(calls, null, 2)); throw error
} finally { await review.flush(); await review.browser.close() }
