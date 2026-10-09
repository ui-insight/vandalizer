import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const session = JSON.parse(await readFile(process.env.CERTIFICATION_QA_SESSION, 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293')
assert.equal(session.module_id, 'multi_step')
assert.match(session.database, /^certification_qa_browser_[a-f0-9]{32}$/)
const baseURL = process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5292'
assert.ok(['http://127.0.0.1:5292', 'http://127.0.0.1:5294'].includes(baseURL))
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL, resetStorage: false })
const { page, context } = review
const calls = [], savedRuns = [], comparisons = []
const lost = new Set()
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url())
  const response = await route.fetch({ url: session.api_origin + url.pathname + url.search, timeout: 120000 })
  calls.push({ method: request.method(), path: url.pathname, status: response.status() })
  if (request.method() === 'POST' && response.ok()) {
    if (url.pathname.endsWith('/connected-runs/execute')) savedRuns.push(await response.json())
    if (url.pathname.endsWith('/modules/multi_step/connected-reviews')) comparisons.push(await response.json())
    for (const suffix of ['/connected-captures', '/connected-runs/execute', '/modules/multi_step/connected-reviews', '/automatic-reviews']) {
      if (url.pathname.endsWith(suffix) && !lost.has(suffix)) {
        lost.add(suffix)
        return route.fulfill({ status: 503, json: { detail: 'QA lost response after a successful save' } })
      }
    }
  }
  if (!response.ok()) console.error('CERTIFICATION API', url.pathname, response.status(), await response.text())
  return route.fulfill({ response })
})
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
const panel = page.getByRole('region', { name: 'Connected workflow assessment', exact: true })
async function proof() { const response = await context.request.get(session.api_origin + '/qa/state', { timeout: 120000 }); assert.equal(response.status(), 200); return response.json() }
async function capture(id, target) {
  if (target) await target.scrollIntoViewIfNeeded()
  const clipped = await panel.evaluate(root => [root, ...root.querySelectorAll('button,p,h4,h5,h6,summary,label')].filter(el => el.clientWidth && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent.slice(0, 90)))
  assert.deepEqual(clipped, [])
  await review.capture(id, 'Production UI with real local certification HTTP/MongoDB and synthetic learner; actual workflow engine, stubbed providers and judge. No live model, credit or release.')
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  console.log(id)
}
async function matrix(name, target) {
  for (const width of [320, 390, 1440]) { await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 }); await capture(`${name}-${width}`, target) }
  await page.setViewportSize({ width: 390, height: 844 })
}
async function runRevision(original) {
  await panel.getByRole('combobox', { name: 'Saved workflow', exact: true }).selectOption(session.workflow_id)
  await panel.getByRole('button', { name: 'Capture selected workflow and source', exact: true }).click()
  if (original) {
    await panel.getByRole('alert').waitFor()
    await capture('connected-capture-lost-reply-390', panel.getByRole('button', { name: 'Check pending request', exact: true }))
    await panel.getByRole('button', { name: 'Check pending request', exact: true }).click()
  }
  await panel.getByRole('button', { name: 'Prepare this captured revision', exact: true }).click()
  const scope = panel.getByRole('form', { name: 'Approve or hold connected run', exact: true })
  await scope.waitFor()
  if (original) await matrix('connected-prepared', scope)
  await scope.getByRole('combobox', { name: 'Scope choice', exact: true }).selectOption('approve')
  await scope.getByRole('textbox', { name: 'Explain your scope choice', exact: true }).fill('I inspected the saved configuration and assigned source. Run this internal revision only; no external delivery or institutional decision is authorized.')
  await scope.getByRole('button', { name: 'Save scope choice', exact: true }).click()
  await panel.getByRole('button', { name: 'Run this approved revision', exact: true }).click()
  if (original) {
    await panel.getByRole('alert').waitFor()
    await capture('connected-execution-lost-reply-390', panel.getByRole('button', { name: 'Check pending request', exact: true }))
    await panel.getByRole('button', { name: 'Check pending request', exact: true }).click()
  }
  await panel.getByRole('heading', { name: 'Run completed', exact: true }).waitFor()
  const evidence = panel.getByRole('region', { name: 'Saved connected run', exact: true })
  await evidence.getByText('Inspect actual input for stage 3', { exact: true }).click()
  await matrix(original ? 'connected-original-input' : 'connected-corrected-input', evidence.getByRole('region', { name: 'Actual input for stage 3', exact: true }))
  await panel.getByRole('button', { name: original ? 'Use as original run' : 'Use as corrected run', exact: true }).click()
}
async function inspectReadableEvidence(before) {
  const saved = JSON.parse(await readFile(process.env.REVIEW_READBACK_PROOF, 'utf8'))
  assert.equal(saved.after.enrollment_id, session.enrollment_id)
  const choices = panel.getByRole('combobox', { name: 'Open saved connected work', exact: true })
  await choices.selectOption('run:' + saved.original_run_id)
  const evidence = panel.getByRole('region', { name: 'Saved connected run', exact: true })
  await evidence.getByText('Inspect actual input for stage 3', { exact: true }).click()
  const original = evidence.getByRole('region', { name: 'Actual input for stage 3', exact: true })
  assert.ok((await original.innerText()).includes('Subaward Agreement'))
  assert.ok(!(await original.innerText()).includes('"kind": "combined_context"'))
  await matrix('readable-original-formatter-input', original)
  await choices.selectOption('run:' + saved.corrected_run_id)
  await evidence.getByText('Inspect actual input for stage 1', { exact: true }).click()
  await matrix('readable-extraction-input', evidence.getByRole('region', { name: 'Actual input for stage 1', exact: true }))
  await evidence.getByText('Inspect actual input for stage 3', { exact: true }).click()
  await matrix('readable-corrected-formatter-input', evidence.getByRole('region', { name: 'Actual input for stage 3', exact: true }))
  await evidence.getByText('Inspect actual result for stage 3', { exact: true }).click()
  await matrix('readable-corrected-formatter-result', evidence.getByRole('region', { name: 'Actual result for stage 3', exact: true }))
  const after = await proof()
  assert.deepEqual(after, before); assert.ok(calls.every(item => item.method === 'GET'))
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ realCertificationAPI: true, readOnlyEvidenceRecheck: true, providerCallsAdded: 0, improvedTextPresentation: true })
  await writeFile(`${review.out}/persistence-proof.json`, JSON.stringify({ before, after, calls }, null, 2))
}
try {
  const before = await proof()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByText('Course progress and credential', { exact: true }).waitFor()
  await writeFile(`${review.out}/entry-dom.txt`, await page.locator('body').ariaSnapshot())
  if (process.env.REVIEW_INSPECT_ONLY !== 'entry') {
    await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    await page.getByRole('button', { name: /^5 / }).click()
    await page.getByRole('button', { name: 'Challenge', exact: true }).click()
    await panel.getByRole('form', { name: 'Capture connected revision', exact: true }).waitFor()
    await writeFile(`${review.out}/form-dom.txt`, await page.locator('body').ariaSnapshot())
    if (process.env.REVIEW_INSPECT_ONLY !== 'form') {
      if (process.env.REVIEW_READBACK_PROOF) await inspectReadableEvidence(before)
      else {
      await matrix('connected-assignment', panel.getByRole('heading', { name: 'Run, inspect and repair a connected workflow', exact: true }))
      await runRevision(true)
      const correction = await context.request.post(session.api_origin + '/qa/correct-formatter')
      assert.equal(correction.status(), 200)
      await runRevision(false)
      assert.equal(savedRuns.length, 2)
      assert.notEqual(savedRuns[0].result.final_output, savedRuns[1].result.final_output)
      const form = panel.getByRole('form', { name: 'Compare actual connected runs', exact: true })
      const answer = 'I inspected both actual stage contexts and final outputs. The original Formatter reread Workflow Documents; the corrected Formatter receives the reasoning result through Step Input. The original evidence remains saved.'
      await form.getByRole('textbox', { name: /^Compare the connection repair/ }).fill(answer)
      await form.getByRole('textbox', { name: /^Check facts and interpretation/ }).fill('The assigned subaward supports its stated reporting and payment obligations. No institutional policy was supplied, so the draft cannot establish institutional compliance. I retain that uncertainty rather than invent an approval.')
      await matrix('connected-comparison-draft', form)
      await form.getByRole('button', { name: 'Save comparison and source review', exact: true }).click()
      await panel.getByRole('alert').waitFor()
      await capture('connected-comparison-lost-reply-390', panel.getByRole('button', { name: 'Check pending request', exact: true }))
      await panel.getByRole('button', { name: 'Check pending request', exact: true }).click()
      await panel.getByRole('heading', { name: 'Comparison saved', exact: true }).waitFor()
      await matrix('connected-saved-comparison', panel.getByRole('region', { name: 'Saved compare the connection repair', exact: true }))
      const assessment = panel.getByRole('region', { name: 'Request automatic assessment', exact: true })
      await assessment.getByRole('button', { name: 'Assess saved work automatically', exact: true }).click()
      await assessment.getByRole('alert').waitFor()
      await capture('connected-assessment-lost-reply-390', assessment)
      await assessment.getByRole('button', { name: 'Check saved assessment', exact: true }).click()
      await assessment.getByRole('button', { name: 'Open saved feedback', exact: true }).click()
      await matrix('connected-feedback', panel.getByRole('region', { name: 'Saved assessment result', exact: true }))
      await panel.getByRole('button', { name: 'Revise comparison answers', exact: true }).click()
      await form.getByRole('textbox', { name: /^Compare the connection repair/ }).fill(answer + ' Revision: the final summary retains unresolved policy comparison explicitly.')
      await form.getByRole('button', { name: 'Save comparison and source review', exact: true }).click()
      await panel.getByRole('heading', { name: 'Comparison saved', exact: true }).waitFor()
      await capture('connected-linked-revision-390', panel.getByRole('heading', { name: 'Comparison saved', exact: true }))
      assert.equal(comparisons.length, 2); assert.equal(comparisons[1].submission.previous_submission_id, comparisons[0].uuid)
      const after = await proof()
      assert.equal(after.runs, 2); assert.equal(after.captures, 2); assert.equal(after.decisions, 4); assert.equal(after.reviews, 1)
      assert.equal(after.extraction_calls, 2); assert.equal(after.reasoning_calls, 2); assert.equal(after.formatter_calls, 2); assert.equal(after.judge_calls, 1)
      assert.equal(after.total_xp, 0); assert.equal(after.certified, false); assert.equal(after.credentials, 0)
      assert.equal(after.active_enrollment_id, before.active_enrollment_id); assert.equal(after.selection_revision, before.selection_revision); assert.equal(after.in_flight_writes, 0)
      const historyStart = calls.length
      await page.getByRole('button', { name: 'Curriculum', exact: true }).click()
      await page.getByText('Course progress and credential', { exact: true }).click()
      const history = page.getByRole('region', { name: 'Saved course work', exact: true })
      await history.getByRole('button', { name: 'Browse saved course work', exact: true }).click()
      await history.getByRole('combobox', { name: 'Saved course', exact: true }).selectOption(session.enrollment_id)
      await history.getByRole('combobox', { name: 'Saved module', exact: true }).selectOption('multi_step')
      await panel.getByRole('combobox', { name: 'Open saved connected work', exact: true }).selectOption('review:' + comparisons[0].uuid)
      await panel.getByRole('heading', { name: 'Comparison saved', exact: true }).waitFor()
      assert.equal(await panel.getByRole('region', { name: 'Saved compare the connection repair', exact: true }).innerText(), answer)
      assert.equal(await panel.getByRole('button', { name: 'Revise comparison answers', exact: true }).count(), 0)
      assert.equal(await panel.getByRole('region', { name: 'Request automatic assessment', exact: true }).count(), 0)
      await matrix('connected-original-history', panel.getByRole('region', { name: 'Saved compare the connection repair', exact: true }))
      assert.ok(calls.slice(historyStart).every(item => item.method === 'GET')); assert.deepEqual(await proof(), after)
      assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
      await writeFile(`${review.out}/persistence-proof.json`, JSON.stringify({ before, after, calls, original_run_id: savedRuns[0].run_id, corrected_run_id: savedRuns[1].run_id, comparison_ids: comparisons.map(item => item.uuid), lostRepliesRecoveredWithoutResubmission: true }, null, 2))
      review.observations.push({ realCertificationAPI: true, fixedSyntheticAuthentication: true, providersStubbed: true, runs: 2, comparisons: 2, automaticReviews: 1, originalHistoryPreserved: true, creditAwarded: 0 })
      }
    }
  }
} catch (error) {
  review.observations.push({ failed: true, message: String(error) })
  await writeFile(`${review.out}/failure-dom.txt`, await page.locator('body').ariaSnapshot().catch(() => 'Unavailable'))
  await writeFile(`${review.out}/api-calls.json`, JSON.stringify(calls, null, 2))
  throw error
} finally { await review.flush(); await review.browser.close() }
