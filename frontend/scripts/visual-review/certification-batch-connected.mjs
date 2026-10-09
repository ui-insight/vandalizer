import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { createReview } from './harness.mjs'

const session = JSON.parse(await readFile(process.env.CERTIFICATION_QA_SESSION, 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293'); assert.equal(session.module_id, 'batch_processing')
assert.match(session.database, /^certification_qa_[a-f0-9]{32}$/)
const authored = JSON.parse(await readFile(new URL('../../../backend/certification-data/drafts/v5.0/batch-processing-case.json', import.meta.url), 'utf8'))
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
    if (url.pathname.endsWith('/batch-runs/execute')) runs.push(await response.json())
    if (url.pathname.endsWith('/modules/batch_processing/batch-reviews')) submissions.push(await response.json())
    for (const suffix of ['/batch-captures', '/modules/batch_processing/batch-runs', '/batch-runs/scope', '/batch-runs/execute', '/modules/batch_processing/batch-reviews', '/automatic-reviews']) {
      if (url.pathname.endsWith(suffix) && !lost.has(suffix)) { lost.add(suffix); return route.fulfill({ status: 503, json: { detail: 'QA lost reply after durable save' } }) }
    }
  }
  if (!response.ok()) console.error('CERTIFICATION API', url.pathname, response.status(), await response.text())
  return route.fulfill({ response })
})
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
const panel = page.getByRole('region', { name: 'Bounded batch assessment', exact: true })
async function proof() { const response = await context.request.get(session.api_origin + '/qa/state'); assert.equal(response.status(), 200); return response.json() }
async function capture(id, target) {
  if (target) await target.scrollIntoViewIfNeeded()
  const clipped = await panel.evaluate(root => [root, ...root.querySelectorAll('button,p,h4,h5,h6,summary,label,legend')].filter(el => el.clientWidth && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent.slice(0, 90)))
  assert.deepEqual(clipped, [])
  await review.capture(id, 'Production batch UI with real local HTTP, MongoDB, extraction engine and original source PDF downloads. Synthetic actor and stub providers/judge; no earned credit or external delivery.')
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
  await capture(`${label}-lost-reply-390`, panel.getByRole('button', { name: 'Check pending batch request', exact: true }))
  await panel.getByRole('button', { name: 'Check pending batch request', exact: true }).click()
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
async function execute(phase) {
  const scope = panel.getByRole('form', { name: 'Approve bounded batch action', exact: true })
  await scope.waitFor()
  await matrix(`batch-${phase}-scope`, scope)
  await scope.getByRole('combobox', { name: 'Scope choice', exact: true }).selectOption('approve')
  const question = { pilot: 'pilot_choice', batch: 'scale_choice', retry: 'recovery_choice' }[phase]
  await scope.getByRole('textbox', { name: authored.questions.find(q => q.id === question).prompt, exact: true }).fill({
    pilot: 'I inspected proposals 1 and 3, all five requested fields and the configured model. Their different PI, budget and research-area values provide a bounded pilot, but the shared NSF template cannot establish quality on other layouts or scans. Only assigned synthetic documents and internal extraction are approved.',
    batch: 'The actual pilot supports all ten values, including full budgets USD 320000 and USD 410000 and the explicit NSF sponsor despite other agency names in proposal 3. I inspected the configured model and measured elapsed time. Token usage and price remain unknown. I approve only the three assigned documents on this unchanged revision; wider reliability remains unproven.',
    retry: 'The saved original batch confirms proposal 2 was deliberately rejected before model dispatch by the disclosed training gate. Proposals 1 and 3 succeeded and their receipts must remain unchanged. I approve only proposal 2 on the same revision and models; this is not a full-batch retry or a real provider outage.'
  }[phase])
  await scope.getByRole('button', { name: 'Save batch scope choice', exact: true }).click()
  if (phase === 'pilot') await recover('batch-scope')
  await panel.getByRole('button', { name: `Run approved ${phase === 'retry' ? 'failed item' : phase}`, exact: true }).click()
  if (phase === 'pilot') await recover('batch-execution')
  const title = { pilot: 'Two-document pilot', batch: 'Three-document batch', retry: 'Targeted item retry' }[phase]
  await panel.getByRole('heading', { name: `${title} · Terminal inventory saved`, exact: true }).first().waitFor()
  const inventory = panel.getByRole('region', { name: 'Batch item inventory', exact: true }).first()
  await matrix(`batch-${phase}-inventory`, inventory)
  assert.equal(runs.length, { pilot: 1, batch: 2, retry: 3 }[phase])
  assert.equal(runs.at(-1).result.checks.all_values_source_supported, phase !== 'batch')
  if (phase === 'batch') {
    assert.equal(await panel.getByRole('button', { name: 'Prepare retry only for proposal 1', exact: true }).count(), 0)
    assert.equal(await panel.getByRole('button', { name: 'Prepare retry only for proposal 3', exact: true }).count(), 0)
    const values = inventory.getByText('Inspect proposal 1 values and identity', { exact: true })
    await values.click(); await matrix('batch-original-values', values); await values.click()
  }
  if (phase === 'pilot' || phase === 'retry') for (const source of authored.sources) await download(panel.getByRole('button', { name: `Download original ${source.id.toUpperCase()} PDF`, exact: true }).first(), source.sha256, phase)
}
try {
  const before = await proof()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByText('Course progress and credential', { exact: true }).waitFor()
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await page.getByRole('button', { name: /^9 / }).click()
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  const captureForm = panel.getByRole('form', { name: 'Capture batch extraction', exact: true })
  await captureForm.waitFor()
  await matrix('batch-assignment', panel.getByRole('heading', { name: 'Checked pilot, complete inventory and targeted recovery', exact: true }))
  await captureForm.getByRole('combobox', { name: 'Owned extraction', exact: true }).selectOption(session.artifact_id)
  await captureForm.getByRole('button', { name: 'Capture extraction and three sources', exact: true }).click()
  await recover('batch-capture')
  await panel.getByRole('button', { name: 'Prepare two-document pilot', exact: true }).click()
  await recover('batch-plan')
  await execute('pilot')
  await panel.getByRole('button', { name: 'Prepare three-document batch from this pilot', exact: true }).click()
  await execute('batch')
  await panel.getByRole('button', { name: 'Prepare retry only for proposal 2', exact: true }).click()
  await execute('retry')
  assert.equal(runs[2].parent_run.run_sha256, runs[1].run_sha256)
  assert.equal(runs[1].parent_run.run_sha256, runs[0].run_sha256)
  await panel.getByRole('button', { name: 'Reconcile inventory and explain recovery', exact: true }).click()
  const interpretation = panel.getByRole('form', { name: 'Save batch recovery interpretation', exact: true })
  const answer = 'All three distinct original input IDs have their own terminal receipts. Proposal 2 was the disclosed training rejection before model dispatch, while proposals 1 and 3 retain their original successful receipt hashes. Only proposal 2 was retried, and its five actual values support the source: Robert Kim, University of Idaho, USD 275000, Computer Science and NSF. The original failure remains preserved. Terminal coverage did not mean successful usable output. The pilot covers different values in one template and sponsor, not all layouts or scans. Measured elapsed time does not establish quality; usage and price remain unknown.'
  await interpretation.getByRole('textbox', { name: authored.questions.find(q => q.id === 'batch_review').prompt, exact: true }).fill(answer)
  await matrix('batch-recovery-interpretation', interpretation.getByRole('button', { name: 'Save batch interpretation', exact: true }))
  await interpretation.getByRole('button', { name: 'Save batch interpretation', exact: true }).click()
  await recover('batch-review')
  await panel.getByRole('heading', { name: 'Saved batch interpretation', exact: true }).waitFor()
  const assessment = panel.getByRole('region', { name: 'Request automatic assessment', exact: true })
  await assessment.getByRole('button', { name: 'Assess saved work automatically', exact: true }).click()
  await assessment.getByRole('alert').waitFor()
  await capture('batch-assessment-lost-reply-390', assessment)
  await assessment.getByRole('button', { name: 'Check saved assessment', exact: true }).click()
  await assessment.getByRole('button', { name: 'Open saved feedback', exact: true }).click()
  await matrix('batch-original-feedback', panel.getByRole('region', { name: 'Saved assessment result', exact: true }))
  await panel.getByRole('button', { name: 'Revise interpretation and preserve original', exact: true }).click()
  await interpretation.getByRole('textbox', { name: authored.questions.find(q => q.id === 'batch_review').prompt, exact: true }).fill(answer + ' This revision preserves the original answer and all original and retry receipts.')
  await interpretation.getByRole('button', { name: 'Save batch interpretation', exact: true }).click()
  await assessment.getByRole('button', { name: 'Assess saved work automatically', exact: true }).click()
  await assessment.getByRole('button', { name: 'Open saved feedback', exact: true }).click()
  await matrix('batch-revised-feedback', panel.getByRole('region', { name: 'Saved assessment result', exact: true }))
  assert.equal(submissions[1].submission.previous_submission_id, submissions[0].uuid)
  const after = await proof()
  assert.equal(after.runs, 3); assert.equal(after.captures, 1); assert.equal(after.decisions, 5); assert.equal(after.reviews, 2)
  assert.equal(after.extraction_calls, 5); assert.equal(after.judge_calls, 2); assert.equal(after.total_xp, 0); assert.equal(after.credentials, 0); assert.equal(after.certified, false)
  assert.equal(after.active_enrollment_id, before.active_enrollment_id); assert.equal(after.selection_revision, before.selection_revision); assert.equal(after.in_flight_writes, 0)
  const historyStart = calls.length
  await page.getByRole('button', { name: 'Curriculum', exact: true }).click()
  await page.getByText('Course progress and credential', { exact: true }).click()
  const history = page.getByRole('region', { name: 'Saved course work', exact: true })
  await history.getByRole('button', { name: 'Browse saved course work', exact: true }).click()
  await history.getByRole('combobox', { name: 'Saved course', exact: true }).selectOption(session.enrollment_id)
  await history.getByRole('combobox', { name: 'Saved module', exact: true }).selectOption('batch_processing')
  await panel.getByRole('combobox', { name: 'Saved record type', exact: true }).selectOption('review')
  await panel.getByRole('textbox', { name: 'Saved batch reference', exact: true }).fill(submissions[0].uuid)
  await panel.getByRole('button', { name: 'Open saved batch reference', exact: true }).click()
  await panel.getByRole('heading', { name: 'Saved batch interpretation', exact: true }).waitFor()
  assert.equal(await panel.getByRole('form', { name: 'Capture batch extraction', exact: true }).count(), 0)
  assert.equal(await panel.getByRole('region', { name: 'Request automatic assessment', exact: true }).count(), 0)
  for (const source of authored.sources) await download(panel.getByRole('button', { name: `Download original ${source.id.toUpperCase()} PDF`, exact: true }).first(), source.sha256, 'history')
  await matrix('batch-original-history', panel.getByRole('heading', { name: 'Saved batch interpretation', exact: true }))
  assert.ok(calls.slice(historyStart).every(call => call.method === 'GET')); assert.deepEqual(await proof(), after)
  assert.ok(calls.every(call => call.status === 200), 'Every actual certification API response must succeed; injected lost replies are separate')
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  await writeFile(`${review.out}/persistence-proof.json`, JSON.stringify({ before, after, calls, downloads, run_ids: runs.map(r => r.run_id), review_ids: submissions.map(r => r.uuid), lostRepliesRecoveredWithoutResubmission: true, controlledFailureDisclosedBeforeDispatch: true }, null, 2))
  review.observations.push({ realCertificationAPI: true, modelDispatchStubbed: true, runs: 3, boundedPilotBatchRetry: true, interpretations: 2, automaticReviews: 2, verifiedDownloads: downloads.length, originalHistoryPreserved: true, creditAwarded: 0 })
} catch (error) {
  review.observations.push({ failed: true, message: String(error) })
  await writeFile(`${review.out}/failure-dom.txt`, await page.locator('body').ariaSnapshot().catch(() => 'Unavailable'))
  await writeFile(`${review.out}/api-calls.json`, JSON.stringify(calls, null, 2))
  throw error
} finally { await review.flush(); await review.browser.close() }
