import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { createReview } from './harness.mjs'

const session = JSON.parse(await readFile(process.env.CERTIFICATION_QA_SESSION, 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293'); assert.equal(session.module_id, 'output_delivery')
assert.match(session.database, /^certification_qa_browser_[a-f0-9]{32}$/)
const authored = JSON.parse(await readFile(new URL('../../../backend/certification-data/drafts/v5.0/output-delivery-case.json', import.meta.url), 'utf8'))
const baseURL = process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294'
assert.ok(['http://127.0.0.1:5292', 'http://127.0.0.1:5294'].includes(baseURL))
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL, resetStorage: false, evidenceMode: 'Real isolated certification HTTP, MongoDB and workflow engine; synthetic workspace fixtures, actor and stub providers/judge; no live model, credit or external delivery' })
const { page, context } = review
const calls = [], runs = [], inspections = [], handoffs = [], submissions = [], downloads = [], lost = new Set()
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url())
  const response = await route.fetch({ url: session.api_origin + url.pathname + url.search, timeout: 120000 })
  calls.push({ method: request.method(), path: url.pathname, status: response.status() })
  if (request.method() === 'POST' && response.ok()) {
    if (url.pathname.endsWith('/output-runs/execute')) runs.push(await response.json())
    if (url.pathname.endsWith('/modules/output_delivery/output-file-reviews')) inspections.push(await response.json())
    if (url.pathname.endsWith('/modules/output_delivery/output-handoffs')) handoffs.push(await response.json())
    if (url.pathname.endsWith('/modules/output_delivery/output-reviews')) submissions.push(await response.json())
    for (const suffix of ['/output-captures', '/output-runs/execute', '/output-file-reviews', '/output-handoffs', '/modules/output_delivery/output-reviews', '/automatic-reviews']) {
      if (url.pathname.endsWith(suffix) && !lost.has(suffix)) { lost.add(suffix); return route.fulfill({ status: 503, json: { detail: 'QA lost reply after durable save' } }) }
    }
  }
  if (!response.ok()) console.error('CERTIFICATION API', url.pathname, response.status(), await response.text())
  return route.fulfill({ response })
})
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
const panel = page.getByRole('region', { name: 'Output and delivery assessment', exact: true })
async function proof() { const response = await context.request.get(session.api_origin + '/qa/state'); assert.equal(response.status(), 200); return response.json() }
async function capture(id, target) {
  if (target) await target.scrollIntoViewIfNeeded()
  const clipped = await panel.evaluate(root => [root, ...root.querySelectorAll('button,p,h4,h5,h6,summary,label,legend')].filter(el => el.clientWidth && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent.slice(0, 90)))
  assert.deepEqual(clipped, [])
  await review.capture(id, 'Production output UI with real local HTTP, MongoDB, workflow engine and actual generated file downloads. Synthetic actor and stub providers/judge; no earned credit or external delivery.')
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
  await capture(`${label}-lost-reply-390`, panel.getByRole('button', { name: 'Check pending output request', exact: true }))
  await panel.getByRole('button', { name: 'Check pending output request', exact: true }).click()
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
async function generate(original) {
  const form = panel.getByRole('form', { name: 'Capture output workflow', exact: true })
  await form.getByRole('combobox', { name: 'Owned output workflow', exact: true }).selectOption(session.workflow_id)
  await form.getByRole('button', { name: 'Save output workflow and source', exact: true }).click()
  if (original) await recover('output-capture')
  await panel.getByRole('button', { name: 'Prepare this saved output workflow', exact: true }).click()
  const scope = panel.getByRole('form', { name: 'Approve output generation', exact: true })
  await scope.waitFor()
  if (original) await matrix('output-generation-scope', scope)
  await scope.getByRole('combobox', { name: 'Generation choice', exact: true }).selectOption('approve')
  await scope.getByRole('textbox', { name: 'Explain this generation decision', exact: true }).fill('I inspected the original assigned report, all four stages, models and effective input choices. Only internal generation is approved; release requires a separate inspection of these exact bytes.')
  await scope.getByRole('button', { name: 'Save generation scope decision', exact: true }).click()
  await panel.getByRole('button', { name: 'Generate these approved files', exact: true }).click()
  if (original) await recover('output-generation')
  await panel.getByRole('heading', { name: 'Files generated · handoff is separate', exact: true }).waitFor()
  assert.equal(runs.length, original ? 1 : 2)
  await matrix(original ? 'output-invalid-generated-files' : 'output-repaired-generated-files', panel.getByRole('region', { name: 'Actual generated files', exact: true }))
  await panel.getByRole('button', { name: 'Inspect these files and choose release scope', exact: true }).click()
  await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Output inspection entry')
  const inspection = panel.getByRole('form', { name: 'Inspect files and approve release', exact: true })
  const artifacts = runs.at(-1).result.generated_artifacts
  assert.equal(artifacts.all_required_files_parseable, !original)
  await download(inspection.getByRole('button', { name: 'Download the original assigned PDF', exact: true }), authored.source_sha256, original ? 'original-source' : 'repaired-source')
  for (const file of artifacts.files) {
    await download(inspection.getByRole('button', { name: 'Download ' + file.filename, exact: true }), file.sha256, original ? 'original' : 'repaired')
    await inspection.getByRole('checkbox', { name: `I opened ${file.filename} and inspected its actual contents.`, exact: true }).check()
    await inspection.getByRole('combobox', { name: 'Usability of ' + file.filename, exact: true }).selectOption(file.file_type === 'txt' ? 'needs_repair' : 'usable')
    await inspection.getByRole('textbox', { name: 'What you checked in ' + file.filename, exact: true }).fill(file.file_type === 'txt' ? 'This is a prose-to-text fallback, not the required CSV. Hold release and repair the Formatter; preserve the original generated PDF.' : 'Opened the file and checked required labels, period, Year 2 versus cumulative spending, publication statuses, nine students and source references against the assigned report.')
  }
  await download(inspection.getByRole('button', { name: 'Download the actual deliverables bundle', exact: true }), artifacts.download.sha256, original ? 'original' : 'repaired')
  await inspection.getByRole('checkbox', { name: 'I opened the actual ZIP bundle and checked every member.', exact: true }).check()
  await inspection.getByRole('textbox', { name: authored.questions[0].prompt, exact: true }).fill(original ? 'The PDF contains the labeled reviewed source values, but the second member is unstructured text, not CSV. Generation finished without establishing usable deliverables. Repair that Formatter output before release.' : 'Both actual files preserve the September 1 2026–August 31 2027 reporting period, USD 135500 Year 2 expenditure, USD 287500 cumulative and USD 197500 remaining. Nine students are not eleven. Publications remain distinguished from in-review, in-press and submitted work; future milestones are not completed deliveries.')
  await inspection.getByRole('textbox', { name: authored.questions[1].prompt, exact: true }).fill(original ? 'Hold these exact files because the CSV is missing. No private or external handoff is authorized; repaired bytes require a fresh review and approval.' : 'Approve only these reviewed PDF and CSV bytes and this bundle for my private training inbox. Audience is me alone. Broader sharing is rejected. New bytes or another destination require a fresh explicit review and approval.')
  await matrix(original ? 'output-held-inspection' : 'output-release-inspection', inspection.getByRole('combobox', { name: 'Release choice', exact: true }))
  if (!original) await inspection.getByRole('combobox', { name: 'Release choice', exact: true }).selectOption('approve')
  await inspection.getByRole('button', { name: 'Save inspection and release choice', exact: true }).click()
  if (original) await recover('output-inspection')
  await panel.getByRole('heading', { name: original ? 'Saved file inspection · hold' : 'Saved file inspection · approve', exact: true }).waitFor()
  if (original) assert.equal(await panel.getByRole('button', { name: 'Attempt the approved private handoff', exact: true }).count(), 0)
  await matrix(original ? 'output-saved-hold' : 'output-exact-release-approved', panel.getByRole('region', { name: 'Opened output evidence', exact: true }))
}
try {
  const before = await proof()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByText('Course progress and credential', { exact: true }).waitFor()
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await page.getByRole('button', { name: /^7 / }).click()
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  await panel.getByRole('form', { name: 'Capture output workflow', exact: true }).waitFor()
  await matrix('output-assignment', panel.getByRole('heading', { name: 'Generate, inspect and hand off exact files', exact: true }))
  await generate(true)
  assert.equal((await proof()).output_calls, 2)
  const corrected = await context.request.post(session.api_origin + '/qa/correct-output-format')
  assert.equal(corrected.status(), 200)
  await generate(false)
  assert.equal((await proof()).output_calls, 4)
  await panel.getByRole('button', { name: 'Attempt the approved private handoff', exact: true }).click()
  await recover('output-handoff')
  await panel.getByRole('heading', { name: 'Controlled training handoff failed', exact: true }).waitFor()
  await matrix('output-controlled-failure', panel.getByRole('region', { name: 'Private handoff receipt', exact: true }))
  await panel.getByRole('button', { name: 'Read current approval before retry', exact: true }).click()
  await panel.getByRole('button', { name: 'Retry only this failed private handoff', exact: true }).waitFor()
  await matrix('output-targeted-retry-approval', panel.getByRole('region', { name: 'Current handoff approval', exact: true }))
  await panel.getByRole('button', { name: 'Retry only this failed private handoff', exact: true }).click()
  await panel.getByRole('heading', { name: 'Private training copy confirmed', exact: true }).waitFor()
  await matrix('output-private-copy-confirmed', panel.getByRole('region', { name: 'Private handoff receipt', exact: true }))
  await download(panel.getByRole('button', { name: 'Download the actual deliverables bundle', exact: true }), runs[1].result.generated_artifacts.download.sha256, 'private-copy')
  await panel.getByRole('button', { name: 'Explain this actual delivery outcome', exact: true }).click()
  await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Explain delivery outcome')
  const outcome = panel.getByRole('form', { name: 'Explain delivery outcome', exact: true })
  const answer = 'The first authorized training attempt deliberately rejected before writing. I inspected its failed receipt and current exact approval, then retried only the failed private handoff. The generated files were not regenerated; their digests match the private copy. This confirms a learner-only copy, not email, sponsor submission or another person reading the report. An unknown response requires reading the original request before retry.'
  await outcome.getByRole('textbox', { name: authored.questions[2].prompt, exact: true }).fill(answer)
  await matrix('output-delivery-interpretation', outcome.getByRole('button', { name: 'Save delivery interpretation', exact: true }))
  await outcome.getByRole('button', { name: 'Save delivery interpretation', exact: true }).click()
  await recover('output-outcome-review')
  await panel.getByRole('heading', { name: 'Saved delivery interpretation', exact: true }).waitFor()
  const assessment = panel.getByRole('region', { name: 'Request automatic assessment', exact: true })
  await assessment.getByRole('button', { name: 'Assess saved work automatically', exact: true }).click()
  await assessment.getByRole('alert').waitFor()
  await capture('output-assessment-lost-reply-390', assessment)
  await assessment.getByRole('button', { name: 'Check saved assessment', exact: true }).click()
  await assessment.getByRole('button', { name: 'Open saved feedback', exact: true }).click()
  await matrix('output-original-feedback', panel.getByRole('region', { name: 'Saved assessment result', exact: true }))
  await panel.getByRole('button', { name: 'Revise this delivery interpretation', exact: true }).click()
  await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Explain delivery outcome')
  await outcome.getByRole('textbox', { name: authored.questions[2].prompt, exact: true }).fill(answer + ' My revised interpretation preserves the original failed receipt and does not claim an external recipient.')
  await outcome.getByRole('button', { name: 'Save delivery interpretation', exact: true }).click()
  await panel.getByRole('heading', { name: 'Saved delivery interpretation', exact: true }).waitFor()
  assert.equal(submissions[1].submission.previous_submission_id, submissions[0].uuid)
  await assessment.getByRole('button', { name: 'Assess saved work automatically', exact: true }).click()
  await assessment.getByRole('button', { name: 'Open saved feedback', exact: true }).click()
  await matrix('output-revised-feedback', panel.getByRole('region', { name: 'Saved assessment result', exact: true }))
  const after = await proof()
  assert.equal(after.runs, 2); assert.equal(after.captures, 2); assert.equal(after.decisions, 8); assert.equal(after.reviews, 2)
  assert.equal(after.output_calls, 4); assert.equal(after.judge_calls, 2); assert.equal(after.total_xp, 0); assert.equal(after.credentials, 0); assert.equal(after.certified, false)
  assert.equal(after.active_enrollment_id, before.active_enrollment_id); assert.equal(after.selection_revision, before.selection_revision); assert.equal(after.in_flight_writes, 0)
  const historyStart = calls.length
  await page.getByRole('button', { name: 'Curriculum', exact: true }).click()
  await page.getByText('Course progress and credential', { exact: true }).click()
  const history = page.getByRole('region', { name: 'Saved course work', exact: true })
  await history.getByRole('button', { name: 'Browse saved course work', exact: true }).click()
  await history.getByRole('combobox', { name: 'Saved course', exact: true }).selectOption(session.enrollment_id)
  await history.getByRole('combobox', { name: 'Saved module', exact: true }).selectOption('output_delivery')
  await panel.getByRole('combobox', { name: 'Open saved output work', exact: true }).selectOption('review:' + submissions[0].uuid)
  await panel.getByRole('heading', { name: 'Saved delivery interpretation', exact: true }).waitFor()
  assert.equal(await panel.getByRole('form', { name: 'Capture output workflow', exact: true }).count(), 0)
  assert.equal(await panel.getByRole('region', { name: 'Request automatic assessment', exact: true }).count(), 0)
  await matrix('output-original-history', panel.getByRole('heading', { name: 'Saved delivery interpretation', exact: true }))
  assert.ok(calls.slice(historyStart).every(call => call.method === 'GET')); assert.deepEqual(await proof(), after)
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  await writeFile(`${review.out}/persistence-proof.json`, JSON.stringify({ before, after, calls, downloads, run_ids: runs.map(item => item.run_id), inspection_ids: inspections.map(item => item.uuid), handoff_ids: handoffs.map(item => item.uuid), review_ids: submissions.map(item => item.uuid), lostRepliesRecoveredWithoutResubmission: true, workflowRepairWasExplicitSyntheticFixtureEdit: true }, null, 2))
  review.observations.push({ realCertificationAPI: true, providersStubbed: true, runs: 2, inspections: 2, handoffs: 2, outcomeReviews: 2, automaticReviews: 2, verifiedDownloads: downloads.length, originalHistoryPreserved: true, creditAwarded: 0 })
} catch (error) {
  review.observations.push({ failed: true, message: String(error) })
  await writeFile(`${review.out}/failure-dom.txt`, await page.locator('body').ariaSnapshot().catch(() => 'Unavailable'))
  await writeFile(`${review.out}/api-calls.json`, JSON.stringify(calls, null, 2))
  throw error
} finally { await review.flush(); await review.browser.close() }
