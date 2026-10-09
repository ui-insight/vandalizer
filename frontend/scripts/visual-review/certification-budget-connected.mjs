import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const session = JSON.parse(await readFile(process.env.CERTIFICATION_QA_SESSION, 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293')
assert.equal(session.module_id, 'advanced_nodes')
assert.match(session.database, /^certification_qa_browser_[a-f0-9]{32}$/)
const authored = JSON.parse(await readFile(new URL('../../../backend/certification-data/drafts/v5.0/advanced-nodes-case.json', import.meta.url), 'utf8'))
const baseURL = process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294'
assert.ok(['http://127.0.0.1:5292', 'http://127.0.0.1:5294'].includes(baseURL))
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL, resetStorage: false })
const { page, context } = review
const calls = [], calculations = [], runs = [], submissions = [], lost = new Set()
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url())
  const response = await route.fetch({ url: session.api_origin + url.pathname + url.search, timeout: 120000 })
  calls.push({ method: request.method(), path: url.pathname, status: response.status() })
  if (request.method() === 'POST' && response.ok()) {
    if (url.pathname.endsWith('/budget-calculations')) calculations.push(await response.json())
    if (url.pathname.endsWith('/budget-runs/execute')) runs.push(await response.json())
    if (url.pathname.endsWith('/modules/advanced_nodes/budget-reviews')) submissions.push(await response.json())
    for (const suffix of ['/budget-calculations', '/budget-runs/execute', '/modules/advanced_nodes/budget-reviews', '/automatic-reviews']) {
      if (url.pathname.endsWith(suffix) && !lost.has(suffix)) {
        lost.add(suffix)
        return route.fulfill({ status: 503, json: { detail: 'QA lost response after successful persistence' } })
      }
    }
  }
  if (!response.ok()) console.error('CERTIFICATION API', url.pathname, response.status(), await response.text())
  return route.fulfill({ response })
})
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
const panel = page.getByRole('region', { name: 'Budget workflow assessment', exact: true })
async function proof() { const response = await context.request.get(session.api_origin + '/qa/state'); assert.equal(response.status(), 200); return response.json() }
async function capture(id, target) {
  if (target) await target.scrollIntoViewIfNeeded()
  const clipped = await panel.evaluate(root => [root, ...root.querySelectorAll('button,p,h4,h5,h6,summary,label,legend')].filter(el => el.clientWidth && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent.slice(0, 90)))
  assert.deepEqual(clipped, [])
  await review.capture(id, 'Production learner UI, real local certification HTTP/MongoDB and workflow engine; synthetic actor, source and provider/judge responses. No earned credit or live models.')
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  assert.deepEqual(review.captures.at(-1).smallControls, [])
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  console.log(id)
}
async function matrix(name, target) {
  for (const width of [320, 390, 1440]) { await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 }); await capture(`${name}-${width}`, target) }
  await page.setViewportSize({ width: 390, height: 844 })
}
async function recover(label) {
  await panel.getByRole('alert').waitFor()
  await capture(`${label}-lost-reply-390`, panel.getByRole('button', { name: 'Check pending budget request', exact: true }))
  await panel.getByRole('button', { name: 'Check pending budget request', exact: true }).click()
}
async function execute(original) {
  await panel.getByRole('button', { name: 'Use these saved calculations', exact: true }).click()
  const form = panel.getByRole('form', { name: 'Capture budget workflow', exact: true })
  await form.getByRole('combobox', { name: 'Owned budget workflow', exact: true }).selectOption(session.workflow_id)
  await form.getByRole('textbox', { name: authored.questions[0].prompt, exact: true }).fill('Use the available Prompt for source interpretation and explicit learner arithmetic for exact additions. Code access is unnecessary. The two source reviews share only the assigned budget and saved calculation record; the internal memo waits for both results. No external delivery or policy approval is authorized.')
  if (original) await matrix('budget-method-decision', form)
  await form.getByRole('button', { name: 'Save workflow and method decision', exact: true }).click()
  await panel.getByRole('button', { name: 'Prepare this saved budget workflow', exact: true }).click()
  const scope = panel.getByRole('form', { name: 'Approve budget scope', exact: true })
  await scope.waitFor()
  if (original) await matrix('budget-prepared-scope', scope)
  await scope.getByRole('combobox', { name: 'Budget execution choice', exact: true }).selectOption('approve')
  await scope.getByRole('textbox', { name: 'Explain this scope decision', exact: true }).fill('I inspected the original source, exact saved calculations and task inputs. I approve only this internal memo; no external action or institutional approval is authorized.')
  await scope.getByRole('button', { name: 'Save budget scope decision', exact: true }).click()
  await panel.getByRole('button', { name: 'Run this approved budget workflow', exact: true }).click()
  if (original) await recover('budget-execution')
  await panel.getByRole('heading', { name: 'Run completed', exact: true }).waitFor()
  const evidence = panel.getByRole('region', { name: 'Saved budget run', exact: true })
  const memo = evidence.locator('section').filter({ has: page.getByRole('heading', { name: '2. Internal memo', exact: true }) })
  await memo.getByText('Read actual input for task 1', { exact: true }).click()
  await matrix(original ? 'budget-original-memo-input' : 'budget-revised-memo-input', memo)
  const input = memo.getByRole('region', { name: 'Internal memo task 1 actual input', exact: true })
  assert.ok((await input.innerText()).includes('SOURCE REVIEW'))
  await panel.getByRole('button', { name: 'Review this completed budget run', exact: true }).click()
  const result = panel.getByRole('form', { name: 'Review budget results', exact: true })
  await result.getByRole('textbox', { name: authored.questions[1].prompt, exact: true }).fill(original ? 'My saved Equipment total of 45001 is wrong: the three named source rows add to 45000 USD. The seven direct categories add to 517424; including estimated indirect cost gives 542800. These additions do not reconcile the narrative base, rates or periods, and no institutional policy was supplied.' : 'The linked calculation corrects Equipment to 45000 USD and preserves the original 45001. The seven direct categories total 517424, plus listed indirect cost gives 542800. The narrative base and period assumptions remain unresolved; these sums do not authorize a budget.')
  await result.getByRole('textbox', { name: authored.questions[2].prompt, exact: true }).fill('The two source-reading tasks consume the same assigned source and saved calculations independently. The actual memo context contains both completed source-review results and the calculation record. It cannot rely on a sibling output before that step finishes. Missing evidence would require a stop or clarification, not a claim of a complete memo.')
  if (original) await matrix('budget-result-review', result)
  await result.getByRole('button', { name: 'Save calculation and dependency review', exact: true }).click()
  if (original) await recover('budget-review')
  await panel.getByRole('heading', { name: 'Saved calculation and dependency review', exact: true }).waitFor()
  const assessment = panel.getByRole('region', { name: 'Request automatic assessment', exact: true })
  await assessment.getByRole('button', { name: 'Assess saved work automatically', exact: true }).click()
  if (original) {
    await assessment.getByRole('alert').waitFor()
    await capture('budget-assessment-lost-reply-390', assessment)
    await assessment.getByRole('button', { name: 'Check saved assessment', exact: true }).click()
  }
  await assessment.getByRole('button', { name: 'Open saved feedback', exact: true }).click()
  await matrix(original ? 'budget-original-feedback' : 'budget-revised-feedback', panel.getByRole('region', { name: 'Saved assessment result', exact: true }))
}
try {
  const before = await proof()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByText('Course progress and credential', { exact: true }).waitFor()
  await writeFile(`${review.out}/entry-dom.txt`, await page.locator('body').ariaSnapshot())
  if (process.env.REVIEW_INSPECT_ONLY !== 'entry') {
    await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    await page.getByRole('button', { name: /^6 / }).click()
    await page.getByRole('button', { name: 'Challenge', exact: true }).click()
    await panel.getByRole('button', { name: 'Record new calculations', exact: true }).waitFor()
    await writeFile(`${review.out}/form-dom.txt`, await page.locator('body').ariaSnapshot())
    if (process.env.REVIEW_INSPECT_ONLY !== 'form') {
      if (process.env.REVIEW_READBACK_PROOF) {
        const saved = JSON.parse(await readFile(process.env.REVIEW_READBACK_PROOF, 'utf8'))
        const choices = panel.getByRole('combobox', { name: 'Open saved budget work', exact: true })
        await choices.selectOption('calculation:' + saved.calculation_ids[0])
        await panel.getByRole('button', { name: 'Use these saved calculations', exact: true }).click()
        await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Capture budget workflow')
        await matrix('budget-focus-selected-calculation', panel.getByRole('form', { name: 'Capture budget workflow', exact: true }))
        await panel.getByRole('button', { name: 'Revise these calculations', exact: true }).click()
        await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Calculation entry')
        await matrix('budget-focus-revise-calculation', panel.getByRole('region', { name: 'Calculation entry', exact: true }))
        await choices.selectOption('review:' + saved.review_ids[0])
        await panel.getByRole('button', { name: 'Revise this budget review', exact: true }).click()
        await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Review budget results')
        await matrix('budget-focus-revise-review', panel.getByRole('form', { name: 'Review budget results', exact: true }))
        assert.deepEqual(await proof(), before); assert.ok(calls.every(call => call.method === 'GET'))
        review.observations.push({ focusHandoffsVerified: true, readOnlyEvidenceRecheck: true, writesAdded: 0 })
        await writeFile(`${review.out}/persistence-proof.json`, JSON.stringify({ before, after: await proof(), calls }, null, 2))
      } else {
      await matrix('budget-assignment', panel.getByRole('heading', { name: 'Choose methods, check arithmetic and inspect dependencies', exact: true }))
      await panel.getByRole('button', { name: 'Record new calculations', exact: true }).click()
      const form = panel.getByRole('form', { name: 'Record budget calculations', exact: true })
      await matrix('budget-calculation-entry', form)
      for (const amount of authored.amounts) {
        await form.getByRole('textbox', { name: amount.label + ' amount (USD)', exact: true }).fill(amount.value)
        await form.getByRole('textbox', { name: 'Source quotation for ' + amount.label, exact: true }).fill(amount.anchor.quote)
        await form.getByRole('textbox', { name: 'Explain your check of ' + amount.label, exact: true }).fill('I checked the named source row, its amount and its printed units; no period normalization is inferred.')
      }
      const labels = ['Equipment subtotal', 'Seven listed direct categories', 'Listed summary including estimated indirect cost']
      for (const [index, check] of authored.calculations.entries()) await form.getByRole('textbox', { name: labels[index] + ' result (USD; leave blank if unresolved)', exact: true }).fill(index ? check.expected_value : '45001.00')
      await form.getByRole('textbox', { name: 'Explain what these additions establish and what remains unresolved', exact: true }).fill('These additions check the printed amounts only. The narrative cost base, indirect calculation and period assumptions remain unresolved; no institutional policy or budget approval is established.')
      await matrix('budget-calculation-totals', form.getByRole('button', { name: 'Save source-bound calculations', exact: true }))
      await form.getByRole('button', { name: 'Save source-bound calculations', exact: true }).click()
      await recover('budget-calculation')
      await panel.getByRole('heading', { name: 'Calculation corrections or clarification needed', exact: true }).waitFor()
      await matrix('budget-wrong-calculation', panel.getByRole('region', { name: 'Saved budget calculations', exact: true }))
      await execute(true)
      await panel.getByRole('combobox', { name: 'Open saved budget work', exact: true }).selectOption('calculation:' + calculations[0].uuid)
      await panel.getByRole('button', { name: 'Revise these calculations', exact: true }).click()
      await form.getByRole('textbox', { name: 'Equipment subtotal result (USD; leave blank if unresolved)', exact: true }).fill('45000.00')
      await form.getByRole('button', { name: 'Save source-bound calculations', exact: true }).click()
      await panel.getByRole('heading', { name: 'Source additions supported', exact: true }).waitFor()
      assert.equal(calculations[1].request.previous_snapshot_id, calculations[0].uuid)
      await matrix('budget-corrected-calculation', panel.getByRole('region', { name: 'Saved budget calculations', exact: true }))
      await execute(false)
      const after = await proof()
      assert.equal(after.runs, 2); assert.equal(after.captures, 4); assert.equal(after.decisions, 4); assert.equal(after.reviews, 2)
      assert.equal(after.budget_calls, 6); assert.equal(after.judge_calls, 2); assert.equal(after.total_xp, 0); assert.equal(after.credentials, 0); assert.equal(after.certified, false)
      assert.equal(after.active_enrollment_id, before.active_enrollment_id); assert.equal(after.selection_revision, before.selection_revision); assert.equal(after.in_flight_writes, 0)
      const historyStart = calls.length
      await page.getByRole('button', { name: 'Curriculum', exact: true }).click()
      await page.getByText('Course progress and credential', { exact: true }).click()
      const history = page.getByRole('region', { name: 'Saved course work', exact: true })
      await history.getByRole('button', { name: 'Browse saved course work', exact: true }).click()
      await history.getByRole('combobox', { name: 'Saved course', exact: true }).selectOption(session.enrollment_id)
      await history.getByRole('combobox', { name: 'Saved module', exact: true }).selectOption('advanced_nodes')
      await panel.getByRole('combobox', { name: 'Open saved budget work', exact: true }).selectOption('review:' + submissions[0].uuid)
      await panel.getByRole('heading', { name: 'Saved calculation and dependency review', exact: true }).waitFor()
      assert.equal(await panel.getByRole('button', { name: 'Record new calculations', exact: true }).count(), 0)
      assert.equal(await panel.getByRole('region', { name: 'Request automatic assessment', exact: true }).count(), 0)
      await matrix('budget-original-history', panel.getByRole('heading', { name: 'Saved calculation and dependency review', exact: true }))
      assert.ok(calls.slice(historyStart).every(call => call.method === 'GET')); assert.deepEqual(await proof(), after)
      assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
      await writeFile(`${review.out}/persistence-proof.json`, JSON.stringify({ before, after, calls, calculation_ids: calculations.map(c => c.uuid), run_ids: runs.map(r => r.run_id), review_ids: submissions.map(s => s.uuid), lostRepliesRecoveredWithoutResubmission: true }, null, 2))
      review.observations.push({ realCertificationAPI: true, providersStubbed: true, calculations: 2, runs: 2, reviews: 2, automaticReviews: 2, originalHistoryPreserved: true, creditAwarded: 0 })
      }
    }
  }
} catch (error) {
  review.observations.push({ failed: true, message: String(error) })
  await writeFile(`${review.out}/failure-dom.txt`, await page.locator('body').ariaSnapshot().catch(() => 'Unavailable'))
  await writeFile(`${review.out}/api-calls.json`, JSON.stringify(calls, null, 2))
  throw error
} finally { await review.flush(); await review.browser.close() }
