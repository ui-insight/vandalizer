import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const session = JSON.parse(await readFile(process.env.CERTIFICATION_QA_SESSION, 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293')
assert.match(session.database, /^certification_qa_browser_[a-f0-9]{32}$/)
const repair = session.module_id === 'extraction_engine'
const prompts = JSON.parse(await readFile(new URL(`../../../backend/certification-data/drafts/v5.0/${repair ? 'extraction-engine' : 'foundations'}-decisions.json`, import.meta.url), 'utf8'))
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
  const clipped = await panel.evaluate(root => [root, ...root.querySelectorAll('button,p,h4,h5,h6,summary,blockquote')].filter(el => el.clientWidth && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent.slice(0, 90)))
  assert.deepEqual(clipped, [], 'Practical review text clips')
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [], 'Accessibility violations')
  console.log(id)
}
const panel = page.getByRole('region', { name: 'Practical review', exact: true })
const preparation = page.getByRole('region', { name: 'Prepare a practical run', exact: true })
const execution = page.getByRole('region', { name: 'Execute saved practical run', exact: true })
const assessment = page.getByRole('region', { name: 'Request automatic assessment', exact: true })
try {
  const before = await proof()
  assert.equal(before.runs, 0); assert.equal(before.total_xp, 0)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await page.getByRole('button', { name: repair ? /^4 Extraction Engine/ : /^1 Foundations/ }).click()
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  if (repair) {
    await panel.getByRole('region', { name: 'Authored repair example', exact: true }).waitFor()
    assert.equal((await proof()).runs, 0)
    await panel.getByText('Inspect the original flawed example', { exact: true }).click()
    for (const width of [320, 390, 1440]) {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
      await panel.getByRole('region', { name: 'Authored repair example', exact: true }).scrollIntoViewIfNeeded()
      await capture('connected-assignment-' + width)
    }
    await page.setViewportSize({ width: 390, height: 844 })
  }
  await preparation.getByRole('button', { name: 'Choose my extraction', exact: true }).click()
  await preparation.getByRole('combobox', { name: 'My extraction', exact: true }).selectOption(session.artifact_id)
  await preparation.getByRole('button', { name: 'Save inputs and prepare for review', exact: true }).click()
  await preparation.getByRole('heading', { name: 'Ready for your scope review', exact: true }).scrollIntoViewIfNeeded()
  await capture('connected-preparation-390')
  assert.equal((await proof()).extraction_calls, 0)
  await preparation.getByRole('button', { name: 'Review proposed scope', exact: true }).click()
  await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Saved source and learner review')
  if (!repair) {
    assert.equal(await panel.getByRole('combobox', { name: 'Source I would authorize', exact: true }).inputValue(), '')
    await panel.getByRole('combobox', { name: 'Source I would authorize', exact: true }).selectOption(session.document_id)
  }
  await panel.getByLabel(prompts[0].choices.approve, { exact: true }).check()
  await panel.getByLabel('Explain your decision', { exact: true }).fill(repair ? 'I compared the authored errors with the saved NIH definitions, including full-project budget and absent names. I approve this revised scope.' : 'I compared the original proposal with the assigned task and chose the saved NSF source for this run.')
  await panel.getByRole('button', { name: 'Save my decision', exact: true }).click()
  await panel.getByRole('heading', { name: 'Decision saved', exact: true }).waitFor()
  await execution.getByRole('button', { name: 'Check execution status', exact: true }).click()
  await execution.getByRole('button', { name: 'Run these saved inputs', exact: true }).scrollIntoViewIfNeeded()
  await capture('connected-approved-scope-390')
  await execution.getByRole('button', { name: 'Run these saved inputs', exact: true }).click()
  await execution.getByRole('alert').waitFor(); await capture('connected-execution-lost-response-390')
  assert.equal((await proof()).extraction_calls, 1)
  await execution.getByRole('button', { name: 'Check execution status', exact: true }).click()
  await execution.getByRole('heading', { name: 'Execution result saved', exact: true }).waitFor()
  await capture('connected-execution-recovered-390')
  await execution.getByRole('button', { name: 'Review saved values', exact: true }).click()
  await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Saved source and learner review')
  const valuePrompt = prompts.find(item => item.phase === 'after_execution')
  await panel.getByLabel(valuePrompt.choices.unresolved, { exact: true }).check()
  await panel.getByLabel('Explain your decision', { exact: true }).fill('I have not established all required values from their source passages yet. These checks remain unresolved.')
  for (const field of valuePrompt.required_fields) await panel.getByRole('group', { name: field, exact: true }).getByRole('textbox', { name: 'What did you establish?', exact: true }).fill('I still need to compare this value with an exact passage in the saved source.')
  await panel.getByRole('button', { name: 'Save my decision', exact: true }).click()
  await panel.getByRole('heading', { name: 'Decision saved', exact: true }).waitFor()
  await assessment.getByRole('button', { name: 'Assess saved work automatically', exact: true }).click()
  await assessment.getByRole('alert').waitFor(); await capture('connected-assessment-lost-response-390')
  assert.equal((await proof()).judge_calls, 1)
  await assessment.getByRole('button', { name: 'Check saved assessment', exact: true }).click()
  await assessment.getByRole('region', { name: 'Requested assessment status', exact: true }).waitFor()
  await assessment.getByRole('button', { name: 'Open saved feedback', exact: true }).click()
  const feedback = page.getByRole('region', { name: 'Saved assessment result', exact: true })
  await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Saved assessment result')
  await capture('connected-saved-feedback-390')
  if (repair) for (const width of [320, 1440]) {
    await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
    await feedback.scrollIntoViewIfNeeded()
    await capture('connected-saved-feedback-' + width)
  }
  assert.ok((await feedback.innerText()).includes('Synthetic integration feedback'))
  const after = await proof()
  assert.equal(after.extraction_calls, 1); assert.equal(after.judge_calls, 1)
  assert.equal(after.runs, 1); assert.equal(after.reviews, 1); assert.equal(after.decisions, 2)
  assert.equal(after.total_xp, before.total_xp); assert.equal(after.certified, false); assert.equal(after.credentials, 0)
  assert.equal(after.active_enrollment_id, before.active_enrollment_id); assert.equal(after.selection_revision, before.selection_revision)
  assert.equal(after.in_flight_writes, 0)
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  await writeFile(`${review.out}/persistence-proof.json`, JSON.stringify({ before, after, calls }, null, 2))
  review.observations.push({ certificationAPI: 'real HTTP handlers and disposable MongoDB', testAuthentication: true, providersStubbed: true,
    liveModelCalls: 0, lostExecutionRecoveredWithoutRedispatch: true, lostAssessmentRecoveredWithoutRegrading: true, creditAwarded: 0 })
} catch (error) {
  console.error('Connected flow failed:', error)
  await writeFile(`${review.out}/failure-dom.txt`, await page.locator('body').ariaSnapshot().catch(() => 'Browser unavailable'))
  review.observations.push({ failed: true, message: String(error) })
  await writeFile(`${review.out}/api-calls.json`, JSON.stringify(calls, null, 2))
  throw error
} finally { await review.flush(); await review.browser.close() }
