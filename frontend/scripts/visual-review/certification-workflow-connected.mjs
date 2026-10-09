import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const session = JSON.parse(await readFile(process.env.CERTIFICATION_QA_SESSION, 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293')
assert.equal(session.module_id, 'workflow_design')
assert.match(session.database, /^certification_qa_browser_[a-f0-9]{32}$/)
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5292', resetStorage: false })
const { page, context } = review
const calls = [], savedDesigns = []
let loseCapture = true, loseSave = true, loseAssessment = true
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url())
  const response = await route.fetch({ url: session.api_origin + url.pathname + url.search, timeout: 120000 })
  const call = { path: url.pathname, method: request.method(), status: response.status() }
  calls.push(call)
  if (call.method === 'POST' && response.ok() && call.path.endsWith('/modules/workflow_design/designs')) savedDesigns.push(await response.json())
  if (call.method === 'POST' && response.ok() && call.path.endsWith('/design-captures') && loseCapture) {
    loseCapture = false
    return route.fulfill({ status: 503, json: { detail: 'QA lost reply after saved workflow capture' } })
  }
  if (call.method === 'POST' && response.ok() && call.path.endsWith('/modules/workflow_design/designs') && loseSave) {
    loseSave = false
    return route.fulfill({ status: 503, json: { detail: 'QA lost reply after the original workflow approval was saved' } })
  }
  if (call.method === 'POST' && response.ok() && call.path.endsWith('/automatic-reviews') && loseAssessment) {
    loseAssessment = false
    return route.fulfill({ status: 503, json: { detail: 'QA lost reply after the original workflow review was saved' } })
  }
  if (!response.ok()) console.error('CERTIFICATION API', call, await response.text())
  return route.fulfill({ response })
})
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
async function proof() {
  const response = await context.request.get(session.api_origin + '/qa/state', { timeout: 120000 })
  assert.equal(response.status(), 200)
  return response.json()
}
const panel = page.getByRole('region', { name: 'Workflow design assessment', exact: true })
async function capture(id) {
  const clipped = await panel.evaluate(root => [root, ...root.querySelectorAll('button,p,h4,h5,h6,summary,blockquote')].filter(el => el.clientWidth && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent.slice(0, 90)))
  assert.deepEqual(clipped, [], 'Workflow review text clips')
  await review.capture(id, 'Real certification HTTP/MongoDB, production frontend and fictional workflow case; fixed test actor and stubbed judge; no workflow execution or learner credit.')
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
    await page.getByRole('button', { name: /^3 / }).click()
    await page.getByRole('button', { name: 'Challenge', exact: true }).click()
    await panel.getByRole('region', { name: 'Choose workflow revision', exact: true }).waitFor()
    await writeFile(`${review.out}/form-dom.txt`, await page.locator('body').ariaSnapshot())
    if (process.env.REVIEW_INSPECT_ONLY !== 'form') {
      assert.equal(before.workflow_designs, 0)
      const brief = panel.getByRole('region', { name: 'Assigned workflow design case', exact: true })
      await brief.getByText('Inspect the flawed workflow proposal', { exact: true }).click()
      for (const width of [320, 390, 1440]) {
        await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
        await brief.getByText('Inspect the flawed workflow proposal', { exact: true }).scrollIntoViewIfNeeded()
        await capture('workflow-assignment-' + width)
      }
      await page.setViewportSize({ width: 390, height: 844 })
      await panel.getByRole('combobox', { name: 'Saved workflow', exact: true }).selectOption(session.workflow_id)
      if (process.env.REVIEW_OWNED_MAP === '1') {
        const choice = panel.getByRole('combobox', { name: 'Starting process map', exact: true }).getByRole('option', { name: /^My saved map/ })
        assert.equal(await choice.count(), 1)
        await panel.getByRole('combobox', { name: 'Starting process map', exact: true }).selectOption(await choice.getAttribute('value'))
      }
      await panel.getByRole('button', { name: 'Capture selected revision', exact: true }).click()
      await panel.getByRole('alert').waitFor()
      await capture('workflow-capture-lost-response-390')
      assert.equal((await proof()).captures, 1)
      await panel.getByRole('button', { name: 'Check saved capture', exact: true }).click()
      const configuration = panel.getByRole('region', { name: 'Captured workflow configuration', exact: true })
      await configuration.waitFor()
      await writeFile(`${review.out}/capture-dom.txt`, await page.locator('body').ariaSnapshot())
      await configuration.getByText('1. Prepare internal comparison · output', { exact: true }).click()
      for (const width of [320, 390, 1440]) {
        await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
        await configuration.getByRole('region', { name: 'Captured settings for Prepare internal comparison', exact: true }).scrollIntoViewIfNeeded()
        await capture('workflow-configuration-' + width)
      }
      const answers = {
        method: 'The saved Prompt reads workflow_documents and returns an internal comparison through the output step. A separate extraction is unnecessary for this small bounded comparison. I inspected its actual input_sources and prompt. The supplied map is an authored example, not my prior learner work.',
        map: 'I removed the external release from the proposed design. This saved configuration stops at the internal comparison; the approval here is for assessment, not execution or release. Missing or conflicting source evidence remains unresolved for a separate human decision.',
        scope: 'Preserve source references, intermediate comparisons and unresolved items in the internal draft. The fictional reviewer checks evidence before an institutional conclusion. No automatic approval, scheduling or external send is authorized.'
      }
      if (process.env.REVIEW_OWNED_MAP === '1') answers.method = answers.method.replace('The supplied map is an authored example, not my prior learner work.', 'I chose my original saved process map; the capture preserves that original without transferring credit.')
      await panel.getByRole('textbox', { name: 'Trace the saved data flow', exact: true }).fill(answers.method)
      await panel.getByRole('textbox', { name: 'Correction and approval boundary', exact: true }).fill(answers.map)
      await panel.getByRole('textbox', { name: 'Evidence and review path', exact: true }).fill(answers.scope)
      for (const width of [320, 390, 1440]) {
        await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
        await panel.getByRole('textbox', { name: 'Correction and approval boundary', exact: true }).scrollIntoViewIfNeeded()
        await capture('workflow-draft-' + width)
      }
      await page.setViewportSize({ width: 390, height: 844 })
      await panel.getByRole('button', { name: 'Approve this saved revision', exact: true }).click()
      await panel.getByRole('alert').waitFor()
      await capture('workflow-save-lost-response-390')
      assert.equal((await proof()).workflow_designs, 1)
      await panel.getByRole('button', { name: 'Check saved approval', exact: true }).click()
      const saved = panel.getByRole('region', { name: 'Saved workflow approval', exact: true })
      await saved.waitFor()
      await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Saved workflow approval')
      assert.equal(await saved.getByRole('region', { name: 'Saved correction and approval boundary', exact: true }).innerText(), answers.map)
      for (const width of [320, 390, 1440]) {
        await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
        const map = saved.getByRole('region', { name: 'Saved correction and approval boundary', exact: true })
        await map.focus(); await page.keyboard.press('PageDown')
        await capture('workflow-saved-map-' + width)
      }
      await page.setViewportSize({ width: 390, height: 844 })
      const assessment = panel.getByRole('region', { name: 'Request automatic assessment', exact: true })
      await assessment.getByRole('button', { name: 'Assess saved work automatically', exact: true }).click()
      await assessment.getByRole('alert').waitFor()
      await capture('workflow-assessment-lost-response-390')
      assert.equal((await proof()).judge_calls, 1)
      await assessment.getByRole('button', { name: 'Check saved assessment', exact: true }).click()
      await assessment.getByRole('button', { name: 'Open saved feedback', exact: true }).click()
      const feedback = panel.getByRole('region', { name: 'Saved assessment result', exact: true })
      await feedback.waitFor()
      await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Saved assessment result')
      for (const width of [320, 390, 1440]) {
        await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
        await feedback.scrollIntoViewIfNeeded(); await capture('workflow-feedback-' + width)
      }
      await page.setViewportSize({ width: 390, height: 844 })
      await panel.getByRole('button', { name: 'Revise these decisions', exact: true }).click()
      await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Your workflow design decisions')
      const revision = answers.map + ' Revision: preserve a separate unresolved-item list for the reviewer.'
      await panel.getByRole('textbox', { name: 'Correction and approval boundary', exact: true }).fill(revision)
      await panel.getByRole('button', { name: 'Approve this saved revision', exact: true }).click()
      await saved.waitFor()
      await capture('workflow-linked-revision-390')
      assert.equal(savedDesigns.length, 2)
      assert.equal(savedDesigns[0].input_snapshot.handoff.kind, process.env.REVIEW_OWNED_MAP === '1' ? 'owned_saved_process_submission' : 'supplied_example')
      assert.equal(savedDesigns[1].submission.previous_submission_id, savedDesigns[0].uuid)
      assert.equal(savedDesigns[0].submission.answers.approval_boundary, answers.map)
      const after = await proof()
      assert.equal(after.workflow_designs, 2); assert.equal(after.reviews, 1); assert.equal(after.judge_calls, 1)
      assert.equal(after.captures, 1); assert.equal(after.process_designs, 1);
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
      await history.getByRole('combobox', { name: 'Saved module', exact: true }).selectOption('workflow_design')
      await panel.getByRole('combobox', { name: 'Saved workflow approval', exact: true }).selectOption(savedDesigns[0].uuid)
      await saved.waitFor()
      assert.equal(await saved.getByRole('region', { name: 'Saved correction and approval boundary', exact: true }).innerText(), answers.map)
      assert.equal(await panel.getByRole('button', { name: 'Revise these decisions', exact: true }).count(), 0)
      assert.equal(await panel.getByRole('region', { name: 'Request automatic assessment', exact: true }).count(), 0)
      for (const width of [320, 390, 1440]) {
        await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 })
        await saved.getByRole('region', { name: 'Saved correction and approval boundary', exact: true }).scrollIntoViewIfNeeded()
        await capture('workflow-original-history-' + width)
      }
      assert.ok(calls.slice(historyStart).every(call => call.method === 'GET'))
      assert.deepEqual(await proof(), after)
      assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
      await writeFile(`${review.out}/persistence-proof.json`, JSON.stringify({ before, after, calls,
        original_submission_id: savedDesigns[0].uuid, revision_submission_id: savedDesigns[1].uuid,
        original_history_preserved: true, lost_save_recovered_without_resubmission: true, lost_assessment_recovered_without_regrading: true }, null, 2))
      review.observations.push({ realCertificationAPI: true, fixedSyntheticAuthentication: true, providersStubbed: true,
        workflowApprovals: 2, workflowCaptures: 1, automaticReviews: 1, workflowExecutions: 0, creditAwarded: 0 })
    }
  }
} catch (error) {
  review.observations.push({ failed: true, message: String(error) })
  await writeFile(`${review.out}/failure-dom.txt`, await page.locator('body').ariaSnapshot().catch(() => 'Unavailable'))
  await writeFile(`${review.out}/api-calls.json`, JSON.stringify(calls, null, 2))
  throw error
} finally { await review.flush(); await review.browser.close() }
