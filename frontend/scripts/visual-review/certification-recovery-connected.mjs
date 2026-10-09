import assert from 'node:assert/strict'
import { readFile, writeFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const session = JSON.parse(await readFile(process.env.CERTIFICATION_QA_SESSION, 'utf8'))
assert.equal(session.api_origin, 'http://127.0.0.1:5293'); assert.equal(session.module_id, 'multi_step')
assert.match(session.database, /^certification_qa_[a-f0-9]{32}$/)
const baseURL = process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294'
assert.equal(baseURL, 'http://127.0.0.1:5294')
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL, resetStorage: false,
  evidenceMode: 'Actual isolated HTTP, MongoDB and workflow engine. Synthetic actor and provider outputs; disclosed actual training rejection before reasoning dispatch. No model judge, earned credit or external writes.' })
const { page, context } = review
const nativeZoom = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
const calls = [], savedRuns = [], decisions = [], lost = new Set()
const lostSuffixes = ['/connected-captures', '/modules/multi_step/connected-runs', '/connected-runs/scope', '/connected-runs/execute', '/connected-recovery-decisions']
await context.route('**/api/certification/**', async route => {
  const request = route.request(), url = new URL(request.url())
  const response = await route.fetch({ url: session.api_origin + url.pathname + url.search, timeout: 120000 })
  calls.push({ method: request.method(), path: url.pathname, status: response.status() })
  if (request.method() === 'POST' && response.ok()) {
    if (url.pathname.endsWith('/connected-runs/execute')) savedRuns.push(await response.json())
    if (url.pathname.endsWith('/connected-recovery-decisions')) decisions.push(await response.json())
    for (const suffix of lostSuffixes) if (url.pathname.endsWith(suffix) && !lost.has(suffix)) {
      lost.add(suffix); return route.fulfill({ status: 503, json: { detail: 'QA reply lost after durable save' } })
    }
  }
  if (!response.ok()) console.error('CERTIFICATION API', url.pathname, response.status(), await response.text())
  return route.fulfill({ response })
})
await context.route('**/api/config/theme', route => route.fulfill({ json: { highlight_color: '#581c87', ui_radius: '4px', org_name: 'Vandalizer', app_name: 'Vandalizer', logo_data_url: '', icon_data_url: '' } }))
const panel = page.getByRole('region', { name: 'Connected workflow assessment', exact: true })
async function proof() { const response = await context.request.get(session.api_origin + '/qa/state'); assert.equal(response.status(), 200); return response.json() }
async function capture(id, target) {
  if (target) await target.scrollIntoViewIfNeeded()
  const clipped = await panel.evaluate(root => [root, ...root.querySelectorAll('button,p,h4,h5,h6,summary,label')].filter(el => el.clientWidth && el.scrollWidth > el.clientWidth + 1).map(el => el.textContent.slice(0, 90)))
  assert.deepEqual(clipped, [])
  await review.capture(id, 'Actual isolated HTTP and workflow engine with synthetic actor and model outputs; actual disclosed training rejection, learner choices and separate normal run. No earned credit or external writes.')
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  assert.deepEqual(review.captures.at(-1).smallControls, [])
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  console.log(id)
}
async function matrix(name, target) {
  for (const scale of nativeZoom ? [1] : [1, 2]) {
    await page.evaluate(value => { document.documentElement.style.fontSize = `${16 * value}px` }, scale)
    for (const width of nativeZoom ? [640, 780, 1440] : [320, 390, 1440]) {
      await page.setViewportSize({ width, height: nativeZoom ? 1000 : width < 500 ? 844 : 1000 })
      if (nativeZoom) assert.equal(await review.setBrowserZoom(2), 2)
      await capture(`${name}-${nativeZoom ? 'native200-physical' : `text${scale}`}-${width}`, target)
    }
  }
  await page.evaluate(() => { document.documentElement.style.fontSize = '16px' })
  await page.setViewportSize({ width: nativeZoom ? 780 : 390, height: nativeZoom ? 1688 : 844 })
}
async function recover(label) {
  await panel.getByRole('alert').waitFor()
  await capture(`${label}-lost-reply-390`, panel.getByRole('button', { name: 'Check pending request', exact: true }))
  await panel.getByRole('button', { name: 'Check pending request', exact: true }).click()
}
async function approve(training) {
  const form = panel.getByRole('form', { name: 'Approve or hold connected run', exact: true })
  await form.waitFor()
  if (training) assert.ok((await form.innerText()).includes(session.case.controlled_failure_practice.notice))
  await form.getByRole('combobox', { name: 'Scope choice', exact: true }).selectOption('approve')
  await form.getByRole('textbox', { name: 'Explain your scope choice', exact: true }).fill(training
    ? 'I inspected this saved internal revision and assigned subaward. I approve the disclosed rehearsal: preserve my actual extraction, deliberately stop before reasoning dispatch, and do not start Formatter or any external action.'
    : 'I inspected the separately prepared normal plan and the original stopped run. This recomputes only the internal source review with fresh approval; it neither overwrites the rejection nor replays any external action.')
  await matrix(training ? 'recovery-training-approval' : 'recovery-new-run-approval', form)
  await form.getByRole('button', { name: 'Save scope choice', exact: true }).click()
  if (training) await recover('recovery-scope')
}
try {
  const before = await proof()
  await page.setViewportSize({ width: nativeZoom ? 780 : 390, height: nativeZoom ? 1688 : 844 })
  await page.goto(baseURL + '/certification', { waitUntil: 'domcontentloaded' })
  await page.getByText('Course progress and credential', { exact: true }).waitFor()
  await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await page.getByRole('button', { name: /^5 Multi-Step Workflows/ }).click()
  await page.getByRole('button', { name: 'Challenge', exact: true }).click()
  if (process.env.REVIEW_READBACK_PROOF) {
    const saved = JSON.parse(await readFile(process.env.REVIEW_READBACK_PROOF, 'utf8'))
    assert.equal(saved.after.database, session.database)
    const choices = panel.getByRole('combobox', { name: 'Open saved connected work', exact: true })
    await choices.selectOption('run:' + saved.stopped_run)
    const run = panel.getByRole('region', { name: 'Saved connected run', exact: true })
    await run.getByText('Inspect actual result for stage 2', { exact: true }).click()
    const rejection = run.getByRole('region', { name: 'Actual result for stage 2', exact: true })
    assert.ok((await rejection.innerText()).startsWith('Disclosed training rejection'))
    await matrix('recovery-readable-rejection', rejection)
    const form = panel.getByRole('form', { name: 'Inspect your stopped run and choose recovery', exact: true })
    await form.getByRole('radio', { name: 'Extraction', exact: true }).focus()
    await page.keyboard.press('ArrowDown')
    assert.equal(await form.getByRole('radio', { name: 'Reasoning', exact: true }).isChecked(), true)
    await matrix('recovery-readable-choices', form.getByRole('group', { name: 'First failed stage', exact: true }))
    await form.getByRole('radio', { name: 'Original run, successful output and failed-stage evidence', exact: true }).focus()
    await page.keyboard.press('Space')
    await matrix('recovery-readable-preservation', form.getByRole('group', { name: 'What work should remain intact?', exact: true }))
    await form.getByRole('radio', { name: 'Resume Reasoning in place in this screen', exact: true }).focus()
    await page.keyboard.press('ArrowDown')
    assert.equal(await form.getByRole('radio', { name: 'Prepare and separately approve a new internal run', exact: true }).isChecked(), true)
    await matrix('recovery-readable-route', form.getByRole('group', { name: 'Supported next action', exact: true }))
    await page.keyboard.press('Tab')
    assert.equal(await form.getByRole('textbox', { name: 'Explain the evidence and recovery limits', exact: true }).evaluate(el => el === document.activeElement), true)
    await page.keyboard.insertText('I inspected the saved extraction and rejection. Keep both intact and separately approve a bounded internal run without repeating external writes.')
    await page.keyboard.press('Tab')
    const save = form.getByRole('button', { name: 'Save my recovery choices', exact: true })
    assert.equal(await save.isEnabled(), true)
    assert.equal(await save.evaluate(el => el === document.activeElement), true)
    await matrix('recovery-readable-save', save)
    await choices.selectOption('recovery:' + saved.recovery_choices[1])
    await matrix('recovery-readable-feedback', panel.getByRole('region', { name: 'Saved stopped-run recovery choices', exact: true }))
    assert.ok(calls.every(call => call.method === 'GET')); assert.deepEqual(await proof(), before)
    assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
    await writeFile(`${review.out}/persistence-proof.json`, JSON.stringify({ before, after: await proof(), calls }, null, 2))
    review.observations.push({ readOnlyPresentationRecheck: true, savedRejectionShownDirectly: true, noAdditionalExecutionOrCredit: true })
  } else {
  await panel.getByRole('combobox', { name: 'Saved workflow', exact: true }).selectOption(session.workflow_id)
  await panel.getByRole('button', { name: 'Capture selected workflow and source', exact: true }).click(); await recover('recovery-capture')
  await matrix('recovery-disclosed-rehearsal', panel.getByRole('button', { name: 'Prepare disclosed stopped-run rehearsal', exact: true }))
  await panel.getByRole('button', { name: 'Prepare disclosed stopped-run rehearsal', exact: true }).click(); await recover('recovery-plan')
  await approve(true)
  await panel.getByRole('button', { name: 'Run approved stopped-run rehearsal', exact: true }).click(); await recover('recovery-execution')
  await panel.getByRole('heading', { name: 'Disclosed training stop · original work preserved', exact: true }).waitFor()
  const run = panel.getByRole('region', { name: 'Saved connected run', exact: true })
  await run.getByText('Inspect actual result for stage 1', { exact: true }).click()
  await run.getByText('Inspect actual input for stage 2', { exact: true }).click()
  await run.getByText('Inspect actual result for stage 2', { exact: true }).click()
  assert.equal(savedRuns.length, 1); assert.equal(savedRuns[0].stage_events.length, 4)
  assert.deepEqual((await proof()).provider_calls, [1, 0, 0])
  assert.equal(await panel.getByRole('button', { name: 'Finalize saved results', exact: true }).count(), 0)
  assert.equal(await panel.getByRole('button', { name: 'Use as corrected run', exact: true }).count(), 0)
  await matrix('recovery-preserved-extraction', run.getByRole('region', { name: 'Actual result for stage 1', exact: true }))
  await matrix('recovery-confirmed-rejection', run.getByRole('region', { name: 'Actual result for stage 2', exact: true }))
  const form = panel.getByRole('form', { name: 'Inspect your stopped run and choose recovery', exact: true })
  await form.getByRole('radio', { name: 'Formatter', exact: true }).check()
  await form.getByRole('radio', { name: 'Keep only the successful extraction as the completed deliverable', exact: true }).check()
  await form.getByRole('radio', { name: 'Restart all stages, including any completed external writes', exact: true }).check()
  await form.getByRole('textbox', { name: 'Explain the evidence and recovery limits', exact: true }).fill('These intentionally incorrect fixture choices test feedback and revision preservation. The actual saved extraction and disclosed reasoning rejection are available for inspection.')
  await matrix('recovery-choice-form', form)
  await form.getByRole('button', { name: 'Save my recovery choices', exact: true }).click(); await recover('recovery-choices')
  await panel.getByRole('heading', { name: 'Reconsider the unsupported recovery choices', exact: true }).waitFor()
  await matrix('recovery-unsupported-feedback', panel.getByRole('region', { name: 'Saved stopped-run recovery choices', exact: true }))
  await panel.getByRole('button', { name: 'Revise recovery choices and preserve original', exact: true }).click()
  await form.getByRole('radio', { name: 'Reasoning', exact: true }).check()
  await form.getByRole('radio', { name: 'Original run, successful output and failed-stage evidence', exact: true }).check()
  await form.getByRole('radio', { name: 'Prepare and separately approve a new internal run', exact: true }).check()
  await form.getByRole('textbox', { name: 'Explain the evidence and recovery limits', exact: true }).fill('The actual extraction succeeded and remains intact. Reasoning was deliberately rejected before provider dispatch; Formatter did not start. Keep the original run, successful output and failed-stage input/result. This screen supports a separate prepared and approved internal run only. It does not resume in place, and internal recomputation never authorizes repeating completed external writes. A lost reply or unsaved stage result would first require reading the saved state; cancellation is not rollback.')
  await form.getByRole('button', { name: 'Save revised recovery choices', exact: true }).click()
  await panel.getByRole('heading', { name: 'Recovery choices match this saved run', exact: true }).waitFor()
  await matrix('recovery-supported-feedback', panel.getByRole('region', { name: 'Saved stopped-run recovery choices', exact: true }))
  assert.equal(decisions.length, 2); assert.equal(decisions[1].submission.previous_submission_id, decisions[0].uuid)
  assert.deepEqual((await proof()).provider_calls, [1, 0, 0])
  await panel.getByRole('button', { name: 'Prepare separate internal run for fresh approval', exact: true }).click()
  assert.equal(await panel.getByRole('button', { name: 'Run this approved revision', exact: true }).count(), 0)
  await approve(false)
  await panel.getByRole('button', { name: 'Run this approved revision', exact: true }).click()
  await panel.getByRole('heading', { name: 'Run completed', exact: true }).waitFor()
  await matrix('recovery-separate-completed-run', run)
  const after = await proof()
  assert.equal(after.captures, 1); assert.equal(after.runs, 2); assert.equal(after.decisions, 4); assert.equal(after.reviews, 0)
  assert.deepEqual(after.provider_calls, [2, 1, 1]); assert.equal(after.judge_calls, 0)
  assert.equal(after.total_xp, 0); assert.equal(after.credentials, 0); assert.equal(after.certified, false)
  assert.equal(after.active_enrollment_id, before.active_enrollment_id); assert.equal(after.selection_revision, before.selection_revision); assert.equal(after.in_flight_writes, 0)
  const historyStart = calls.length
  await page.getByRole('button', { name: 'Curriculum', exact: true }).click()
  await page.getByText('Course progress and credential', { exact: true }).click()
  const history = page.getByRole('region', { name: 'Saved course work', exact: true })
  await history.getByRole('button', { name: 'Browse saved course work', exact: true }).click()
  await history.getByRole('combobox', { name: 'Saved course', exact: true }).selectOption(session.enrollment_id)
  await history.getByRole('combobox', { name: 'Saved module', exact: true }).selectOption('multi_step')
  await panel.getByRole('combobox', { name: 'Open saved connected work', exact: true }).selectOption('recovery:' + decisions[0].uuid)
  await panel.getByRole('heading', { name: 'Reconsider the unsupported recovery choices', exact: true }).waitFor()
  assert.equal(await panel.getByRole('button', { name: 'Revise recovery choices and preserve original', exact: true }).count(), 0)
  await panel.getByText('Inspect the original stopped run and successful extraction', { exact: true }).click()
  await matrix('recovery-original-read-only-history', panel.getByRole('heading', { name: 'Disclosed training stop · original work preserved', exact: true }))
  assert.ok(calls.slice(historyStart).every(call => call.method === 'GET')); assert.deepEqual(await proof(), after)
  assert.equal(lost.size, lostSuffixes.length); assert.ok(calls.every(call => call.status === 200))
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  await writeFile(`${review.out}/persistence-proof.json`, JSON.stringify({ before, after, calls, stopped_run: savedRuns[0].run_id, separate_run: savedRuns[1].run_id, recovery_choices: decisions.map(d => d.uuid), lostRepliesRecoveredWithoutResubmission: true }, null, 2))
  review.observations.push({ actualTrainingRejection: true, originalFailurePreserved: true, providerCalls: after.provider_calls, separateApprovalRequired: true, recoveryChoices: 2, judgeCalls: 0, creditAwarded: 0 })
  }
} catch (error) {
  review.observations.push({ failed: true, message: String(error) })
  await writeFile(`${review.out}/failure-dom.txt`, await page.locator('body').ariaSnapshot().catch(() => 'Unavailable'))
  await writeFile(`${review.out}/api-calls.json`, JSON.stringify(calls, null, 2))
  throw error
} finally { await review.flush(); await review.browser.close() }
