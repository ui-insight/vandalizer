import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const session = JSON.parse(await readFile(process.env.CERTIFICATION_QA_SESSION, 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293')
assert.equal(session.module_id, 'process_mapping')
assert.match(session.database, /^certification_qa_browser_[a-f0-9]{32}$/)
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5292', resetStorage: false })
const { page, context } = review
const calls = [], savedDesigns = []
let loseSave = true, loseAssessment = true
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url())
  const response = await route.fetch({ url: session.api_origin + url.pathname + url.search })
  const call = { path: url.pathname, method: request.method(), status: response.status() }
  calls.push(call)
  if (call.method === 'POST' && response.ok() && call.path.endsWith('/process-designs')) savedDesigns.push(await response.json())
  if (call.method === 'POST' && response.ok() && call.path.endsWith('/process-designs') && loseSave) {
    loseSave = false
    return route.fulfill({ status: 503, json: { detail: 'QA lost reply after the original process design was saved' } })
  }
  if (call.method === 'POST' && response.ok() && call.path.endsWith('/automatic-reviews') && loseAssessment) {
    loseAssessment = false
    return route.fulfill({ status: 503, json: { detail: 'QA lost reply after the original process review was saved' } })
  }
  if (!response.ok()) console.error('CERTIFICATION API', call, await response.text())
  return route.fulfill({ response })
})
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
async function proof() {
  const response = await context.request.get(session.api_origin + '/qa/state')
  assert.equal(response.status(), 200)
  return response.json()
}
const panel = page.getByRole('region', { name: 'Process design assessment', exact: true })
async function capture(id) {
  const clipped = await panel.evaluate(root => [root, ...root.querySelectorAll('button,p,h4,h5,h6,summary,blockquote')].filter(el => el.clientWidth && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent.slice(0, 90)))
  assert.deepEqual(clipped, [], 'Process review text clips')
  await review.capture(id, 'Real certification HTTP/MongoDB, production frontend and fictional process case; fixed test actor and stubbed judge; no workflow execution or learner credit.')
  const item = review.captures.at(-1)
  assert.equal(item.pageWidth, item.viewport.width)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  console.log(id)
}
try {
  const before = await proof()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByText('Course progress and credential', { exact: true }).waitFor()
  await writeFile(`${review.out}/entry-dom.txt`, await page.locator('body').ariaSnapshot())
  if (process.env.REVIEW_INSPECT_ONLY !== 'entry') {
    await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    // The current course entry snapshot supplies the module's accessible label.
    await page.getByRole('button', { name: /^2 Thinking in Workflows/ }).click()
    await page.getByRole('button', { name: 'Challenge', exact: true }).click()
    await panel.getByRole('form', { name: 'Your process design', exact: true }).waitFor()
    await writeFile(`${review.out}/form-dom.txt`, await page.locator('body').ariaSnapshot())
    if (process.env.REVIEW_INSPECT_ONLY !== 'form') {
      assert.equal(before.process_designs, 0)
      const brief = panel.getByRole('region', { name: 'Assigned process case', exact: true })
      await brief.getByText('Inspect the flawed proposal', { exact: true }).click()
      for (const width of [320, 390, 1440]) {
        await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
        await brief.getByText('Inspect the flawed proposal', { exact: true }).scrollIntoViewIfNeeded()
        await capture('process-assignment-' + width)
      }
      await page.setViewportSize({ width: 390, height: 844 })
      const answers = {
        method: 'For the one-off question, source-grounded chat is sufficient. Repeated fixed fields fit a reusable extraction. For monthly comparison I choose a bounded workflow because recurring fields and variable narrative evidence need separate stages and a review checkpoint. A project can organize context; no scheduling trigger or autonomous release is authorized.',
        map: '1. Use only report-alpine, report-neural and report-water. 2. Extract recurring fields and preserve source references. 3. Prepare an internal comparison with unresolved items visible. 4. The grants reviewer inspects source and intermediate evidence before any institutional conclusion or separately authorized release. Stop the affected item on missing or conflicting evidence. I removed the proposed source expansion, guessed values, automatic approval and send-before-review. This is a design, not an executed workflow.',
        scope: 'Use the three named fictional reports only. Produce an internal comparison draft with source references and unresolved issues. Do not include other documents, invent missing milestones, approve reports, schedule automation or send externally. Stop and flag an unreadable or unsupported item; preserve its evidence for the grants reviewer.'
      }
      await panel.getByRole('textbox', { name: 'Working method and rationale', exact: true }).fill(answers.method)
      await panel.getByRole('textbox', { name: 'Corrected process map', exact: true }).fill(answers.map)
      await panel.getByRole('textbox', { name: 'Bounded task brief', exact: true }).fill(answers.scope)
      for (const width of [320, 390, 1440]) {
        await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
        await panel.getByRole('textbox', { name: 'Corrected process map', exact: true }).scrollIntoViewIfNeeded()
        await capture('process-draft-' + width)
      }
      await page.setViewportSize({ width: 390, height: 844 })
      await panel.getByRole('button', { name: 'Save my reviewed design', exact: true }).click()
      await panel.getByRole('alert').waitFor()
      await capture('process-save-lost-response-390')
      assert.equal((await proof()).process_designs, 1)
      await panel.getByRole('button', { name: 'Check saved design', exact: true }).click()
      const saved = panel.getByRole('region', { name: 'Saved process design', exact: true })
      await saved.waitFor()
      await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Saved process design')
      assert.equal(await saved.getByRole('region', { name: 'Saved corrected process map', exact: true }).innerText(), answers.map)
      for (const width of [320, 390, 1440]) {
        await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
        const map = saved.getByRole('region', { name: 'Saved corrected process map', exact: true })
        await map.focus(); await page.keyboard.press('PageDown')
        await capture('process-saved-map-' + width)
      }
      await page.setViewportSize({ width: 390, height: 844 })
      const assessment = panel.getByRole('region', { name: 'Request automatic assessment', exact: true })
      await assessment.getByRole('button', { name: 'Assess saved work automatically', exact: true }).click()
      await assessment.getByRole('alert').waitFor()
      await capture('process-assessment-lost-response-390')
      assert.equal((await proof()).judge_calls, 1)
      await assessment.getByRole('button', { name: 'Check saved assessment', exact: true }).click()
      await assessment.getByRole('button', { name: 'Open saved feedback', exact: true }).click()
      const feedback = panel.getByRole('region', { name: 'Saved assessment result', exact: true })
      await feedback.waitFor()
      await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Saved assessment result')
      for (const width of [320, 390, 1440]) {
        await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
        await feedback.scrollIntoViewIfNeeded(); await capture('process-feedback-' + width)
      }
      await page.setViewportSize({ width: 390, height: 844 })
      await panel.getByRole('button', { name: 'Revise this design', exact: true }).click()
      await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Your process design')
      const revision = answers.map + ' Revision: preserve a separate unresolved-item list for the reviewer.'
      await panel.getByRole('textbox', { name: 'Corrected process map', exact: true }).fill(revision)
      await panel.getByRole('button', { name: 'Save my reviewed design', exact: true }).click()
      await saved.waitFor()
      await capture('process-linked-revision-390')
      assert.equal(savedDesigns.length, 2)
      assert.equal(savedDesigns[1].submission.previous_submission_id, savedDesigns[0].uuid)
      assert.equal(savedDesigns[0].submission.answers.human_checkpoint, answers.map)
      const after = await proof()
      assert.equal(after.process_designs, 2); assert.equal(after.reviews, 1); assert.equal(after.judge_calls, 1)
      assert.equal(after.extraction_calls, 0); assert.equal(after.runs, 0); assert.equal(after.decisions, 0)
      assert.equal(after.total_xp, 0); assert.equal(after.certified, false); assert.equal(after.credentials, 0)
      assert.equal(after.active_enrollment_id, before.active_enrollment_id)
      assert.equal(after.selection_revision, before.selection_revision); assert.equal(after.in_flight_writes, 0)
      const historyStart = calls.length
      await page.getByRole('button', { name: 'Curriculum', exact: true }).click()
      await page.getByText('Course progress and credential', { exact: true }).click()
      const history = page.getByRole('region', { name: 'Saved course work', exact: true })
      await history.getByRole('button', { name: 'Browse saved course work', exact: true }).click()
      await history.getByRole('combobox', { name: 'Saved course', exact: true }).selectOption(session.enrollment_id)
      await history.getByRole('combobox', { name: 'Saved module', exact: true }).selectOption('process_mapping')
      await panel.getByRole('combobox', { name: 'Saved process design', exact: true }).selectOption(savedDesigns[0].uuid)
      await saved.waitFor()
      assert.equal(await saved.getByRole('region', { name: 'Saved corrected process map', exact: true }).innerText(), answers.map)
      assert.equal(await panel.getByRole('button', { name: 'Revise this design', exact: true }).count(), 0)
      assert.equal(await panel.getByRole('region', { name: 'Request automatic assessment', exact: true }).count(), 0)
      for (const width of [320, 390, 1440]) {
        await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
        await saved.getByRole('region', { name: 'Saved corrected process map', exact: true }).scrollIntoViewIfNeeded()
        await capture('process-original-history-' + width)
      }
      assert.ok(calls.slice(historyStart).every(call => call.method === 'GET'))
      assert.deepEqual(await proof(), after)
      assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
      await writeFile(`${review.out}/persistence-proof.json`, JSON.stringify({ before, after, calls,
        original_submission_id: savedDesigns[0].uuid, revision_submission_id: savedDesigns[1].uuid,
        original_history_preserved: true, lost_save_recovered_without_resubmission: true, lost_assessment_recovered_without_regrading: true }, null, 2))
      review.observations.push({ realCertificationAPI: true, fixedSyntheticAuthentication: true, providersStubbed: true,
        processDesigns: 2, automaticReviews: 1, workflowExecutions: 0, creditAwarded: 0 })
    }
  }
} catch (error) {
  review.observations.push({ failed: true, message: String(error) })
  await writeFile(`${review.out}/failure-dom.txt`, await page.locator('body').ariaSnapshot().catch(() => 'Unavailable'))
  await writeFile(`${review.out}/api-calls.json`, JSON.stringify(calls, null, 2))
  throw error
} finally { await review.flush(); await review.browser.close() }
