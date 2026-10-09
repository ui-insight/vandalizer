import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { createReview } from './harness.mjs'

const session = JSON.parse(await readFile(process.env.CERTIFICATION_QA_SESSION, 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293'); assert.equal(session.module_id, 'governance')
assert.match(session.database, /^certification_qa_[a-f0-9]{32}$/)
const authored = JSON.parse(await readFile(new URL('../../../backend/certification-data/drafts/v5.0/governance-capstone-case.json', import.meta.url), 'utf8'))
const baseURL = process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294'
assert.ok(['http://127.0.0.1:5292', 'http://127.0.0.1:5294'].includes(baseURL))
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL, resetStorage: false,
  evidenceMode: 'Real isolated certification HTTP, MongoDB and ExtractionEngine; synthetic actor, workspace repair endpoint, model dispatch and judge; no live model, earned credit or external delivery' })
const { page, context } = review
const calls = [], runs = [], memos = [], handoffs = [], submissions = [], downloads = [], lost = new Set()
const lostSuffixes = ['/governance-captures', '/governance/corrections', '/modules/governance/governance-runs', '/governance-runs/scope', '/governance-runs/execute', '/governance/findings', '/governance/memos', '/governance/releases', '/governance/handoffs', '/modules/governance/governance-reviews', '/automatic-reviews']
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url())
  const response = await route.fetch({ url: session.api_origin + url.pathname + url.search, timeout: 120000 })
  calls.push({ method: request.method(), path: url.pathname, status: response.status() })
  if (request.method() === 'POST' && response.ok()) {
    if (url.pathname.endsWith('/governance-runs/execute')) runs.push(await response.json())
    if (url.pathname.endsWith('/governance/memos')) memos.push(await response.json())
    if (url.pathname.endsWith('/governance/handoffs')) handoffs.push(await response.json())
    if (url.pathname.endsWith('/modules/governance/governance-reviews')) submissions.push(await response.json())
    for (const suffix of lostSuffixes) if (url.pathname.endsWith(suffix) && !lost.has(suffix)) { lost.add(suffix); return route.fulfill({ status: 503, json: { detail: 'QA lost response after durable save' } }) }
  }
  if (!response.ok()) console.error('CERTIFICATION API', url.pathname, response.status(), await response.text())
  return route.fulfill({ response })
})
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
const panel = page.getByRole('region', { name: 'Governance supervision capstone', exact: true })
const question = id => authored.questions.find(q => q.id === id).prompt
async function proof() { const response = await context.request.get(session.api_origin + '/qa/state'); assert.equal(response.status(), 200); return response.json() }
async function capture(id, target) {
  if (target) await target.scrollIntoViewIfNeeded()
  const clipped = await panel.evaluate(root => [root, ...root.querySelectorAll('button,p,h4,h5,h6,summary,label,legend')].filter(el => el.clientWidth && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent.slice(0, 90)))
  assert.deepEqual(clipped, [])
  await review.capture(id, 'Production capstone learner interface with real isolated HTTP, MongoDB, engine orchestration and exact source/memo downloads. Synthetic actor, model dispatch, judge and editor-repair substitute. No earned credit or external delivery.')
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
  await capture(`${label}-lost-reply-390`, panel.getByRole('button', { name: 'Check pending capstone request', exact: true }))
  await panel.getByRole('button', { name: 'Check pending capstone request', exact: true }).click()
}
async function download(button, expected, name) {
  const waiting = page.waitForEvent('download'); await button.click(); const file = await waiting
  const path = `${review.out}/${name}-${file.suggestedFilename()}`; await file.saveAs(path)
  const bytes = await readFile(path), digest = createHash('sha256').update(bytes).digest('hex'); assert.equal(digest, expected)
  downloads.push({ filename: file.suggestedFilename(), artifact: path, sha256: digest, bytes: bytes.length })
}
async function execute(phase) {
  const form = panel.getByRole('form', { name: 'Approve or hold the exact capstone extraction', exact: true })
  await form.waitFor(); await matrix(`governance-${phase}-approval`, form)
  await form.getByRole('combobox', { name: 'Execution choice', exact: true }).selectOption('approve')
  await form.getByRole('textbox', { name: 'Explain your execution scope choice', exact: true }).fill(phase === 'original'
    ? 'I inspected both complete fictional sources, the six owned instructions, the disclosed funding flaw and configured model. I approve only this original internal diagnostic extraction. My saved scope correction keeps broad sharing, sponsor email and recurring automation disabled; release requires a later separate decision.'
    : 'The saved original finding identifies the actually returned $600000 ceiling as unsupported obligations. I inspected the changed instruction in the same owned funding field and both unchanged complete sources. I approve this complete internal rerun with the original models and settings; no handoff or external action is authorized.')
  await form.getByRole('button', { name: 'Save capstone execution choice', exact: true }).click()
  if (phase === 'original') await recover('governance-execution-choice')
  await panel.getByRole('button', { name: 'Read this extraction’s current approval and run state', exact: true }).click()
  await panel.getByRole('button', { name: phase === 'original' ? 'Run approved original diagnostic extraction' : 'Run approved repaired complete extraction', exact: true }).click()
  if (phase === 'original') await recover('governance-execution')
  await panel.getByRole('heading', { name: `${phase === 'original' ? 'Original diagnostic extraction' : 'Repaired complete extraction'} · Actual result saved`, exact: true }).first().waitFor()
  await matrix(`governance-${phase}-values`, panel.getByRole('region', { name: 'Actual capstone source checks', exact: true }).first())
  assert.equal(runs.length, phase === 'original' ? 1 : 2)
  assert.equal(runs.at(-1).result.checks.source_supported, phase === 'repair')
  for (const source of authored.sources) await download(panel.getByRole('button', { name: `Download original ${source.id} PDF`, exact: true }).first(), source.sha256, phase)
}
try {
  const before = await proof()
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(review.baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByText('Course progress and credential', { exact: true }).waitFor()
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await page.getByRole('button', { name: /^10 Collaboration & Governance/ }).click()
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  const captureForm = panel.getByRole('form', { name: 'Capture your capstone extraction', exact: true })
  await captureForm.waitFor(); await matrix('governance-assignment', panel.getByRole('heading', { name: 'Supervise the capstone and own its handoff', exact: true }))
  await captureForm.getByRole('combobox', { name: 'Owned capstone extraction', exact: true }).selectOption(session.artifact_id)
  await captureForm.getByRole('button', { name: 'Capture extraction and both capstone sources', exact: true }).click(); await recover('governance-capture')
  const correction = panel.getByRole('form', { name: 'Correct the proposed capstone scope', exact: true })
  await correction.getByRole('textbox', { name: question('scope_correction'), exact: true }).fill('The agent cannot approve on my behalf. I reject scanning every document and space, broad sharing, sponsor email and recurring sends. Only these two complete assigned fictional records and my learner-only private training inbox are in scope. Recurring automation remains disabled; I would stop an unintended trigger and inspect its original receipts before deciding any bounded next action.')
  await matrix('governance-scope-correction', correction)
  await correction.getByRole('button', { name: 'Save my corrected capstone scope', exact: true }).click(); await recover('governance-correction')
  await panel.getByRole('button', { name: 'Prepare original diagnostic extraction', exact: true }).click(); await recover('governance-plan')
  await execute('original')
  const finding = panel.getByRole('form', { name: 'Record the original source finding', exact: true })
  await finding.getByRole('textbox', { name: 'Actual unsupported Funds Obligated to Date value', exact: true }).fill('600000')
  await finding.getByRole('textbox', { name: 'Exact award notice page quote', exact: true }).fill(authored.expectations[0].anchors[0].quote)
  await finding.getByRole('textbox', { name: 'Exact issued amendment page quote', exact: true }).fill(authored.expectations[3].anchors[0].quote)
  await finding.getByRole('textbox', { name: 'Explain the actual mismatch and the instruction change you will test', exact: true }).fill('The original run actually returned $600000, the approved project ceiling, as funds obligated to date. The issued amendment adds $70000 to the original $180000, giving revised cumulative obligations of $250000. The later issued amendment controls the changed amount and end date; the ceiling remains distinct. I will change this same funding field to use cumulative obligations from the latest issued amendment, keep all sources and other field identities, and retest both complete records with the same models.')
  await matrix('governance-source-finding', finding.getByRole('button', { name: 'Save my original capstone source finding', exact: true }))
  await finding.getByRole('button', { name: 'Save my original capstone source finding', exact: true }).click(); await recover('governance-finding')
  await panel.getByRole('button', { name: 'Capture my repaired capstone revision', exact: true }).waitFor()
  const repairResponse = await context.request.post(session.api_origin + '/qa/repair'); assert.equal(repairResponse.status(), 200)
  await panel.getByRole('button', { name: 'Capture my repaired capstone revision', exact: true }).click()
  const repairPlan = panel.getByRole('form', { name: 'Prepare the changed capstone revision', exact: true })
  await repairPlan.getByRole('combobox', { name: 'Your saved original source finding', exact: true }).selectOption({ index: 1 })
  await matrix('governance-repair-plan', repairPlan)
  await repairPlan.getByRole('button', { name: 'Prepare this repaired complete extraction', exact: true }).click()
  await execute('repair')
  assert.equal(runs[1].source_finding.run.run_sha256, runs[0].run_sha256)
  const memo = panel.getByRole('form', { name: 'Write the accountable capstone memo', exact: true })
  for (const [name, value] of Object.entries({
    'Intended use': 'Private training rehearsal of an internal award-amendment routing memo as of the simulated January 5, 2027 date; no sponsor submission or real institutional decision.',
    'Supported inputs and source scope': 'Only the complete assigned fictional award notice and issued amendment for RSP-2026-042, interpreted jointly with the issued amendment controlling its changed funding and end date.',
    'Known limitations': 'This checks one fictional award pair and a disclosed instruction flaw. It does not prove reliability across other layouts, scans, later amendments or real award policy, and no real external delivery occurred.',
    'Change and review route · distinguish real-world review roles from certification staff': 'I own this training memo and its checked revision. Changed sources, instructions or intended use need new complete validation and an appropriate research-office review under actual local policy. That hypothetical role is not a certification staff grader or a reason to send or await anything.'
  })) await memo.getByRole('textbox', { name, exact: true }).fill(value)
  await matrix('governance-accountability-memo', memo.getByRole('button', { name: 'Save checked accountable memo', exact: true }))
  await memo.getByRole('button', { name: 'Save checked accountable memo', exact: true }).click(); await recover('governance-memo')
  await panel.getByRole('heading', { name: 'Inspect the accountable memo', exact: true }).waitFor()
  assert.equal(memos.length, 1)
  await download(panel.getByRole('button', { name: 'Download exact accountable memo JSON', exact: true }), memos[0].file.sha256, 'inspected')
  const release = panel.getByRole('form', { name: 'Inspect and decide capstone memo release', exact: true })
  await release.getByRole('checkbox', { name: 'I opened and inspected this exact downloaded memo.', exact: true }).check()
  await release.getByRole('combobox', { name: 'Memo release choice', exact: true }).selectOption('approve')
  await release.getByRole('textbox', { name: question('release_review'), exact: true }).fill('I inspected these exact JSON bytes and the same-extraction repaired result with all six source checks. The memo names me as the responsible training owner, limits use to the two original fictional records, states remaining limitations and gives the review/change route. I approve only my learner-only private inbox. This does not authorize a sponsor send, broad sharing or an enabled recurring action; changed evidence needs another checked revision and release decision.')
  await matrix('governance-exact-release', release)
  await release.getByRole('button', { name: 'Save my exact memo release choice', exact: true }).click(); await recover('governance-release')
  await panel.getByRole('button', { name: 'Attempt approved private memo handoff', exact: true }).click(); await recover('governance-handoff')
  await panel.getByRole('heading', { name: 'Disclosed training rejection · no destination write', exact: true }).waitFor()
  assert.equal(handoffs.length, 1); assert.equal(handoffs[0].destination_written, false); assert.equal(handoffs[0].destination_copy, null)
  await matrix('governance-no-write-failure', panel.getByRole('button', { name: 'Retry only this failed private memo handoff', exact: true }))
  await download(panel.getByRole('button', { name: 'Download exact accountable memo JSON', exact: true }), memos[0].file.sha256, 'failed-approved-memo')
  await panel.getByRole('button', { name: 'Retry only this failed private memo handoff', exact: true }).click()
  await panel.getByRole('heading', { name: 'Same checked memo confirmed in your private inbox', exact: true }).waitFor()
  assert.equal(handoffs.length, 2); assert.deepEqual(handoffs[1].destination_copy, memos[0].file)
  await matrix('governance-confirmed-copy', panel.getByRole('heading', { name: 'Same checked memo confirmed in your private inbox', exact: true }))
  await download(panel.getByRole('button', { name: 'Download exact accountable memo JSON', exact: true }), memos[0].file.sha256, 'confirmed-copy')
  const interpretation = panel.getByRole('form', { name: 'Explain your complete capstone supervision', exact: true })
  const answer = 'I corrected the proposed scope before approval, limiting it to the assigned sources and my private inbox with no recurring or external actions. My original run returned the $600000 ceiling as obligations. I saved the source finding showing the issued amendment raises cumulative obligations to $250000, repaired the same funding field and approved a complete same-model rerun; all six actual values matched the original sources. I inspected the exact accountable memo and its ownership, use, limits and review route before a separate release. The first private handoff was the disclosed rejection with no destination write, not a real outage. I explicitly retried only the same approved bytes, preserving the original failure and avoiding another extraction. The confirming private-copy receipt supports this contained handoff only. I remain the training owner; changed real artifacts require new source checks and appropriate research-office review, not certification staff involvement. This does not establish wider reliability or actual external delivery.'
  await interpretation.getByRole('textbox', { name: question('final_supervision'), exact: true }).fill(answer)
  await matrix('governance-final-supervision', interpretation.getByRole('button', { name: 'Save my capstone supervision interpretation', exact: true }))
  await interpretation.getByRole('button', { name: 'Save my capstone supervision interpretation', exact: true }).click(); await recover('governance-review')
  const assessment = panel.getByRole('region', { name: 'Request automatic assessment', exact: true })
  await assessment.getByRole('button', { name: 'Assess saved work automatically', exact: true }).click(); await assessment.getByRole('alert').waitFor()
  await capture('governance-assessment-lost-reply-390', assessment)
  await assessment.getByRole('button', { name: 'Check saved assessment', exact: true }).click()
  await assessment.getByRole('button', { name: 'Open saved feedback', exact: true }).click()
  await matrix('governance-original-feedback', panel.getByRole('region', { name: 'Saved assessment result', exact: true }))
  await panel.getByRole('button', { name: 'Revise supervision explanation and preserve original', exact: true }).click()
  await interpretation.getByRole('textbox', { name: question('final_supervision'), exact: true }).fill(answer + ' This clarification retains my original interpretation and all earlier immutable receipts.')
  await interpretation.getByRole('button', { name: 'Save revised capstone interpretation', exact: true }).click()
  await assessment.getByRole('button', { name: 'Assess saved work automatically', exact: true }).click()
  await assessment.getByRole('button', { name: 'Open saved feedback', exact: true }).click()
  await matrix('governance-revised-feedback', panel.getByRole('region', { name: 'Saved assessment result', exact: true }))
  assert.equal(submissions.length, 2); assert.equal(submissions[1].submission.previous_submission_id, submissions[0].uuid)
  const after = await proof()
  assert.equal(after.runs, 2); assert.equal(after.captures, 2); assert.equal(after.decisions, 10); assert.equal(after.reviews, 2)
  assert.equal(after.extraction_calls, 2); assert.equal(after.judge_calls, 2); assert.equal(after.total_xp, 0); assert.equal(after.credentials, 0); assert.equal(after.certified, false)
  assert.equal(after.active_enrollment_id, before.active_enrollment_id); assert.equal(after.selection_revision, before.selection_revision); assert.equal(after.in_flight_writes, 0)
  const historyStart = calls.length
  await page.getByRole('button', { name: 'Curriculum', exact: true }).click(); await page.getByText('Course progress and credential', { exact: true }).click()
  const history = page.getByRole('region', { name: 'Saved course work', exact: true })
  await history.getByRole('button', { name: 'Browse saved course work', exact: true }).click()
  await history.getByRole('combobox', { name: 'Saved course', exact: true }).selectOption(session.enrollment_id)
  await history.getByRole('combobox', { name: 'Saved module', exact: true }).selectOption('governance')
  await panel.getByRole('combobox', { name: 'Saved capstone record type', exact: true }).selectOption('review')
  await panel.getByRole('textbox', { name: 'Saved capstone reference', exact: true }).fill(submissions[0].uuid)
  await panel.getByRole('button', { name: 'Open saved capstone reference', exact: true }).click()
  await panel.getByRole('heading', { name: 'Supervision interpretation', exact: true }).waitFor()
  assert.equal(await panel.getByRole('form', { name: 'Capture your capstone extraction', exact: true }).count(), 0)
  assert.equal(await panel.getByRole('region', { name: 'Request automatic assessment', exact: true }).count(), 0)
  await download(panel.getByRole('button', { name: 'Download exact accountable memo JSON', exact: true }), memos[0].file.sha256, 'history')
  await panel.getByText('Inspect preserved source-checked repair', { exact: true }).click()
  for (const source of authored.sources) await download(panel.getByRole('button', { name: `Download original ${source.id} PDF`, exact: true }).first(), source.sha256, 'history')
  await matrix('governance-original-history', panel.getByRole('heading', { name: 'Supervision interpretation', exact: true }))
  assert.ok(calls.slice(historyStart).every(call => call.method === 'GET')); assert.deepEqual(await proof(), after)
  assert.ok(calls.every(call => call.status === 200)); assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  assert.equal(lost.size, lostSuffixes.length)
  await writeFile(`${review.out}/persistence-proof.json`, JSON.stringify({ before, after, calls, downloads, run_ids: runs.map(r => r.run_id), review_ids: submissions.map(r => r.uuid), lostRepliesRecoveredWithoutResubmission: true, controlledNoWriteRejectionDisclosed: true, syntheticEditorRepair: true }, null, 2))
  review.observations.push({ realCertificationAPI: true, modelDispatchStubbed: true, syntheticEditorRepair: true, runs: 2, interpretations: 2, automaticReviews: 2, verifiedDownloads: downloads.length, originalHistoryPreserved: true, creditAwarded: 0 })
} catch (error) {
  review.observations.push({ failed: true, message: String(error) })
  await writeFile(`${review.out}/failure-dom.txt`, await page.locator('body').ariaSnapshot().catch(() => 'Unavailable'))
  await writeFile(`${review.out}/api-calls.json`, JSON.stringify(calls, null, 2))
  throw error
} finally { await review.flush(); await review.browser.close() }
