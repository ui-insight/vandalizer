import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { createReview } from './harness.mjs'

const session = JSON.parse(await readFile(process.env.CERTIFICATION_QA_SESSION, 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293'); assert.equal(session.module_id, 'validation_qa')
assert.match(session.database, /^certification_qa_[a-f0-9]{32}$/)
const authored = JSON.parse(await readFile(new URL('../../../backend/certification-data/drafts/v5.0/validation-qa-case.json', import.meta.url), 'utf8'))
const baseURL = process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294'
assert.ok(['http://127.0.0.1:5292', 'http://127.0.0.1:5294'].includes(baseURL))
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL, resetStorage: false, evidenceMode: 'Real isolated certification HTTP, MongoDB and extraction engine; synthetic workspace fixtures, actor and stub providers/judge; no live model, credit or external delivery' })
const { page, context } = review
const calls = [], runs = [], submissions = [], downloads = [], lost = new Set()
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url())
  const response = await route.fetch({ url: session.api_origin + url.pathname + url.search, timeout: 120000 })
  calls.push({ method: request.method(), path: url.pathname, status: response.status() })
  if (request.method() === 'POST' && response.ok()) {
    if (url.pathname.endsWith('/validation-runs/execute')) runs.push(await response.json())
    if (url.pathname.endsWith('/modules/validation_qa/validation-reviews')) submissions.push(await response.json())
    for (const suffix of ['/validation-captures', '/modules/validation_qa/validation-suites', '/validation-runs/scope', '/validation-runs/execute', '/modules/validation_qa/validation-reviews', '/automatic-reviews']) {
      if (url.pathname.endsWith(suffix) && !lost.has(suffix)) { lost.add(suffix); return route.fulfill({ status: 503, json: { detail: 'QA lost reply after durable save' } }) }
    }
  }
  if (!response.ok()) console.error('CERTIFICATION API', url.pathname, response.status(), await response.text())
  return route.fulfill({ response })
})
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
const panel = page.getByRole('region', { name: 'Representative validation assessment', exact: true })
async function proof() { const response = await context.request.get(session.api_origin + '/qa/state'); assert.equal(response.status(), 200); return response.json() }
async function capture(id, target) {
  if (target) await target.scrollIntoViewIfNeeded()
  const clipped = await panel.evaluate(root => [root, ...root.querySelectorAll('button,p,h4,h5,h6,summary,label,legend')].filter(el => el.clientWidth && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent.slice(0, 90)))
  assert.deepEqual(clipped, [])
  await review.capture(id, 'Production validation UI with real local HTTP, MongoDB, extraction engine and original source PDF downloads. Synthetic actor and stub providers/judge; no earned credit or external delivery.')
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  assert.deepEqual(review.captures.at(-1).smallControls, [])
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  console.log(id)
}
async function matrix(name, target) {
  for (const scale of process.env.REVIEW_BOTH_TEXT_SCALES === '1' ? [1, 2] : [Number(process.env.REVIEW_TEXT_SCALE || 1)]) {
    await page.evaluate(value => { document.documentElement.style.fontSize = `${16 * value}px` }, scale)
    for (const width of [320, 390, 1440]) { await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 }); await capture(`${name}${process.env.REVIEW_BOTH_TEXT_SCALES === '1' ? `-text${scale}` : ''}-${width}`, target) }
  }
  await page.evaluate(value => { document.documentElement.style.fontSize = `${16 * value}px` }, Number(process.env.REVIEW_TEXT_SCALE || 1))
  await page.setViewportSize({ width: 390, height: 844 })
}
async function recover(label) {
  await panel.getByRole('alert').waitFor()
  await capture(`${label}-lost-reply-390`, panel.getByRole('button', { name: 'Check pending validation request', exact: true }))
  await panel.getByRole('button', { name: 'Check pending validation request', exact: true }).click()
}
async function download(button, expected, name) {
  const waiting = page.waitForEvent('download')
  await button.click()
  const file = await waiting
  const path = `${review.out}/${name}-${file.suggestedFilename()}`
  await file.saveAs(path)
  const data = await readFile(path), digest = createHash('sha256').update(data).digest('hex')
  assert.equal(digest, expected)
  downloads.push({ filename: file.suggestedFilename(), artifact: path, sha256: digest, bytes: data.length })
}
async function execute(original) {
  const scope = panel.getByRole('form', { name: 'Approve complete validation suite', exact: true })
  await scope.waitFor()
  await matrix(original ? 'validation-original-scope' : 'validation-retest-scope', scope)
  await scope.getByRole('combobox', { name: 'Scope choice', exact: true }).selectOption('approve')
  await scope.getByRole('textbox', { name: 'Why this scope is appropriate', exact: true }).fill('I checked this exact extraction revision, both complete PDFs, all six source-supported expectations and the resolved model. Only internal execution of the entire suite is approved; no external action or credit.')
  await scope.getByRole('button', { name: 'Save suite scope choice', exact: true }).click()
  if (original) await recover('validation-scope')
  await panel.getByRole('button', { name: 'Run both approved validation cases', exact: true }).click()
  if (original) await recover('validation-execution')
  await panel.getByRole('heading', { name: `${original ? 'Original' : 'Repaired'} revision · Complete suite result saved`, exact: true }).waitFor()
  await matrix(original ? 'validation-observed-failure' : 'validation-complete-retest', panel.getByRole('region', { name: 'Source comparisons', exact: true }).first())
  assert.equal(runs.length, original ? 1 : 2)
  assert.equal(runs.at(-1).result.checks.source_supported, !original)
  for (const source of authored.sources) await download(panel.getByRole('button', { name: `Download original ${source.id.toUpperCase()} PDF`, exact: true }).first(), source.sha256, original ? 'original' : 'retest')
}
try {
  const before = await proof()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByText('Course progress and credential', { exact: true }).waitFor()
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await page.getByRole('button', { name: /^8 / }).click()
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  const captureForm = panel.getByRole('form', { name: 'Capture validation extraction', exact: true })
  await captureForm.waitFor()
  await matrix('validation-assignment', panel.getByRole('heading', { name: 'Representative tests and repair', exact: true }))
  await captureForm.getByRole('combobox', { name: 'Owned extraction', exact: true }).selectOption(session.artifact_id)
  await captureForm.getByRole('button', { name: 'Capture extraction and both sources', exact: true }).click()
  await recover('validation-capture')
  const expectations = panel.getByRole('form', { name: 'Save representative test expectations', exact: true })
  await expectations.waitFor()
  await matrix('validation-empty-expectations', expectations)
  for (const expected of authored.expectations) {
    const group = expectations.getByRole('group', { name: `${expected.source_id.toUpperCase()} · ${expected.field}`, exact: true })
    if (expected.expected_value === null) await group.getByRole('combobox', { name: 'Expectation type', exact: true }).selectOption('explicit_absence')
    else await group.getByRole('textbox', { name: 'Expected value', exact: true }).fill(expected.expected_value)
    await group.getByRole('spinbutton', { name: 'Source page', exact: true }).fill(String(expected.anchors[0].page))
    await group.getByRole('textbox', { name: 'Exact source quote', exact: true }).fill(expected.anchors[0].quote)
    await group.getByRole('textbox', { name: 'Why this source supports the value or absence', exact: true }).fill(expected.meaning)
  }
  await expectations.getByRole('textbox', { name: authored.questions[0].prompt, exact: true }).fill('Both complete proposals cover full-project versus annual budget ambiguity across different project lengths. NSF names a Co-PI; NIH names Co-Investigators without assigning that exact role, requiring explicit absence. I checked all six values against their original source pages. These two proposals cannot prove accuracy on all future grant documents.')
  await matrix('validation-checked-expectations', expectations.getByRole('button', { name: 'Save complete test expectations', exact: true }))
  await expectations.getByRole('button', { name: 'Save complete test expectations', exact: true }).click()
  await recover('validation-suite')
  await panel.getByRole('button', { name: 'Prepare original complete suite', exact: true }).click()
  await execute(true)
  await panel.getByRole('button', { name: 'Use this original failure for repair', exact: true }).click()
  await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Capture validation extraction')
  await matrix('validation-preserved-repair-selection', captureForm)
  assert.equal((await proof()).extraction_calls, 2)
  assert.equal((await context.request.post(session.api_origin + '/qa/repair-extraction')).status(), 200)
  await captureForm.getByRole('button', { name: 'Capture extraction and both sources', exact: true }).click()
  await panel.getByRole('button', { name: 'Prepare complete repaired retest', exact: true }).click()
  await execute(false)
  assert.equal(runs[1].original_run.run_sha256, runs[0].run_sha256)
  assert.equal(runs[1].suite.suite_record_sha256, runs[0].suite.suite_record_sha256)
  await panel.getByRole('button', { name: 'Explain the repair and complete retest', exact: true }).click()
  const interpretation = panel.getByRole('form', { name: 'Save validation repair interpretation', exact: true })
  const answer = 'The original NSF budget was USD 177000 and NIH USD 304000, annual figures rather than their full project totals. I changed the same budget field to request the full multi-year total and retested both complete sources with the unchanged six expectations. The actual corrected outputs are USD 485000 and USD 1250000. Both PIs, the NSF Co-PI and the explicit absent NIH Co-PI remain checked. Model repeatability alone cannot establish source correctness; two documents do not guarantee future accuracy.'
  await interpretation.getByRole('textbox', { name: authored.questions[1].prompt, exact: true }).fill(answer)
  await matrix('validation-repair-interpretation', interpretation.getByRole('button', { name: 'Save repair interpretation', exact: true }))
  await interpretation.getByRole('button', { name: 'Save repair interpretation', exact: true }).click()
  await recover('validation-review')
  await panel.getByRole('heading', { name: 'Saved repair interpretation', exact: true }).waitFor()
  const assessment = panel.getByRole('region', { name: 'Request automatic assessment', exact: true })
  await assessment.getByRole('button', { name: 'Assess saved work automatically', exact: true }).click()
  await assessment.getByRole('alert').waitFor()
  await capture('validation-assessment-lost-reply-390', assessment)
  await assessment.getByRole('button', { name: 'Check saved assessment', exact: true }).click()
  await assessment.getByRole('button', { name: 'Open saved feedback', exact: true }).click()
  await matrix('validation-original-feedback', panel.getByRole('region', { name: 'Saved assessment result', exact: true }))
  await panel.getByRole('button', { name: 'Revise interpretation and preserve original', exact: true }).click()
  await interpretation.getByRole('textbox', { name: authored.questions[1].prompt, exact: true }).fill(answer + ' This revision preserves the original answer and both complete execution receipts.')
  await interpretation.getByRole('button', { name: 'Save repair interpretation', exact: true }).click()
  await assessment.getByRole('button', { name: 'Assess saved work automatically', exact: true }).click()
  await assessment.getByRole('button', { name: 'Open saved feedback', exact: true }).click()
  await matrix('validation-revised-feedback', panel.getByRole('region', { name: 'Saved assessment result', exact: true }))
  assert.equal(submissions[1].submission.previous_submission_id, submissions[0].uuid)
  const after = await proof()
  assert.equal(after.runs, 2); assert.equal(after.captures, 2); assert.equal(after.decisions, 5); assert.equal(after.reviews, 2)
  assert.equal(after.extraction_calls, 4); assert.equal(after.judge_calls, 2); assert.equal(after.total_xp, 0); assert.equal(after.credentials, 0); assert.equal(after.certified, false)
  assert.equal(after.active_enrollment_id, before.active_enrollment_id); assert.equal(after.selection_revision, before.selection_revision); assert.equal(after.in_flight_writes, 0)
  const historyStart = calls.length
  await page.getByRole('button', { name: 'Curriculum', exact: true }).click()
  await page.getByText('Course progress and credential', { exact: true }).click()
  const history = page.getByRole('region', { name: 'Saved course work', exact: true })
  await history.getByRole('button', { name: 'Browse saved course work', exact: true }).click()
  await history.getByRole('combobox', { name: 'Saved course', exact: true }).selectOption(session.enrollment_id)
  await history.getByRole('combobox', { name: 'Saved module', exact: true }).selectOption('validation_qa')
  await panel.getByRole('combobox', { name: 'Saved record type', exact: true }).selectOption('review')
  await panel.getByRole('textbox', { name: 'Saved validation reference', exact: true }).fill(submissions[0].uuid)
  await panel.getByRole('button', { name: 'Open saved validation reference', exact: true }).click()
  await panel.getByRole('heading', { name: 'Saved repair interpretation', exact: true }).waitFor()
  assert.equal(await panel.getByRole('form', { name: 'Capture validation extraction', exact: true }).count(), 0)
  assert.equal(await panel.getByRole('region', { name: 'Request automatic assessment', exact: true }).count(), 0)
  for (const source of authored.sources) await download(panel.getByRole('button', { name: `Download original ${source.id.toUpperCase()} PDF`, exact: true }).first(), source.sha256, 'history')
  await matrix('validation-original-history', panel.getByRole('heading', { name: 'Saved repair interpretation', exact: true }))
  assert.ok(calls.slice(historyStart).every(call => call.method === 'GET')); assert.deepEqual(await proof(), after)
  assert.ok(calls.every(call => call.status === 200), 'Every actual certification API response must succeed; injected lost replies are separate')
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  await writeFile(`${review.out}/persistence-proof.json`, JSON.stringify({ before, after, calls, downloads, run_ids: runs.map(r => r.run_id), review_ids: submissions.map(r => r.uuid), lostRepliesRecoveredWithoutResubmission: true, extractionRepairWasExplicitSyntheticFixtureEdit: true }, null, 2))
  review.observations.push({ realCertificationAPI: true, modelDispatchStubbed: true, runs: 2, savedSuites: 1, interpretations: 2, automaticReviews: 2, verifiedDownloads: downloads.length, originalHistoryPreserved: true, creditAwarded: 0 })
} catch (error) {
  review.observations.push({ failed: true, message: String(error) })
  await writeFile(`${review.out}/failure-dom.txt`, await page.locator('body').ariaSnapshot().catch(() => 'Unavailable'))
  await writeFile(`${review.out}/api-calls.json`, JSON.stringify(calls, null, 2))
  throw error
} finally { await review.flush(); await review.browser.close() }
