import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const data = new URL('../../../backend/certification-data/', import.meta.url)
const read = async name => JSON.parse(await readFile(new URL(name, data), 'utf8'))
const modules = await read('panel-modules.json')
const structure = await read('course-structure.json')
const outcomes = await read('drafts/v5.0/outcomes.json')
const identity = { enrollment_id: 'a'.repeat(32), course_version: 'continuation-fixture', manifest_sha256: 'a'.repeat(64), course_title: 'Your existing certification course', modules_total: modules.length, module_ids: modules.map(m => m.id), maximum_xp: 2675 }
const course = { ...structure, ...identity, versioned: true, prerequisites: Object.fromEntries(modules.map(m => [m.id, []])), modules }
const progress = { ...identity, id: 'comparison-progress', user_id: 'reviewer', modules: { foundations: { completed: true, stars: 1, xp_earned: 125, completed_at: '2025-01-01', attempts: 1 } }, total_xp: 125, level: 'novice', certified: false, certified_at: null, last_activity_date: null, learning_position: null }
const target = { course_version: 'v5-comparison-fixture', course_title: 'Vandalizer 5.0 — Supervise document work', description: 'Compare source review, scope, recovery and delivery requirements before deciding on a future optional upgrade.', manifest_sha256: 'b'.repeat(64), required_outcome_count: 33 }
const preview = { policy: 'optional', can_activate: false, preview_sha256: 'c'.repeat(64), source: { ...identity, provenance: 'legacy_version_unknown', total_xp: 125, certified: false, credential_preserved: false, completed_modules: [{ module_id: 'foundations', title: 'Foundations', xp_earned: 125, stars: 1, completed_at: '2025-01-01' }], has_saved_place: true }, target: { ...target, transferred_outcome_count: 0, modules: outcomes.modules.map(module => ({ module_id: module.module_id, title: modules.find(m => m.id === module.module_id).title, outcomes: module.outcomes.map(outcome => ({ outcome_id: outcome.id, statement: outcome.statement, disposition: 'requires_assessment', reason: 'No confirmed outcome equivalence.' })) })) }, saved_work: [{ kind: 'prepared_labs', label: 'Saved lab inputs', count: 1 }, { kind: 'saved_lab_runs', label: 'Saved lab runs', count: 2 }, { kind: 'saved_learner_decisions', label: 'Saved learner decisions', count: 3 }], work_in_flight: false, unfinished_answers: true, credential_needs_preservation: false }

const choiceRequest = { request_id: 'e'.repeat(32), source_enrollment_id: identity.enrollment_id, target_version: target.course_version, preview_sha256: preview.preview_sha256, consent: 'preserve_original_work_and_require_all_new_outcomes' }
const decision = { decision_id: choiceRequest.request_id, source_enrollment_id: identity.enrollment_id, target_version: target.course_version, target_manifest_sha256: target.manifest_sha256, preview_sha256: preview.preview_sha256, decision_sha256: 'f'.repeat(64), accepted_at: '2026-10-09', credit_transferred: false, requires_fresh_activation_check: true,
  activation_request: { request_id: '1'.repeat(32), decision_id: choiceRequest.request_id, consent: 'activate_optional_upgrade_preserving_original_work_without_credit_transfer' } }
const result = { current_enrollment_id: 'b'.repeat(32), confirmation_pending: false, receipt: { request_id: decision.activation_request.request_id, kind: 'optional_upgrade_selection.1', receipt_sha256: 'd'.repeat(64), source_enrollment_id: identity.enrollment_id, target_enrollment_id: 'b'.repeat(32), target_course_version: target.course_version, target_manifest_sha256: target.manifest_sha256, revision: 1, selected_at: '2026-10-09', action: 'activate_optional_upgrade', credit_transferred: false, histories_preserved: true } }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5307', resetStorage: false,
  evidenceMode: 'Frozen production frontend; synthetic held preservation choice and switch responses. No actual course or learner change.' })
const { page, context } = review
const writes = []
await context.route('**/api/certification/**', route => {
  const req = route.request(), path = new URL(req.url()).pathname, post = req.method() === 'POST'
  if (post) writes.push(path)
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/upgrade-options')) return route.fulfill({ json: { enrollment_id: identity.enrollment_id, policy: 'optional', can_activate: false, courses: [target] } })
  if (path.endsWith('/upgrade-preview')) return route.fulfill({ json: preview })
  if (path.endsWith('/upgrade-choice-preview')) return route.fulfill({ json: { comparison: preview, choice: { available: true, reason: null, recorded: false, request: choiceRequest, decision: null } } })
  if (post && path.endsWith('/upgrade-choices')) { assert.deepEqual(req.postDataJSON(), choiceRequest); return route.fulfill({ status: 503, json: { detail: 'Synthetic lost choice reply' } }) }
  if (path.endsWith('/upgrade-choices/' + decision.decision_id)) return route.fulfill({ json: decision })
  if (post && path.endsWith('/upgrade-activations')) { assert.deepEqual(req.postDataJSON(), decision.activation_request); return route.fulfill({ status: 503, json: { detail: 'Synthetic lost switch reply' } }) }
  if (path.endsWith('/upgrade-activations/' + decision.activation_request.request_id)) return route.fulfill({ json: { ...result, request: decision.activation_request, source_enrollment_id: identity.enrollment_id, state: 'applied', read_only: true } })
  return route.fallback()
})
let unblock = null, handler = null
async function hold(fragment, method) {
  handler = async route => {
    if (route.request().method() === method && new URL(route.request().url()).pathname.endsWith(fragment)) await new Promise(resolve => { unblock = resolve })
    return route.fallback()
  }
  await context.route('**/api/**', handler)
}
async function release() { await context.unroute('**/api/**', handler); unblock?.(); unblock = null }
const panel = page.locator('[data-cert-panel]')
async function capture(text, id) {
  const status = panel.getByRole('status').filter({ hasText: text }); await status.waitFor(); await status.scrollIntoViewIfNeeded()
  await review.capture(id, 'Held synthetic response. Preservation save does not switch courses; saved-state checks do not resubmit either action.')
}
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1688 : 1000 }); writes.length = 0
    await page.goto(review.baseURL + '/certification', { waitUntil: 'networkidle' })
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    const details = panel.locator('details').filter({ has: page.locator('summary').filter({ hasText: /^Course progress and credential$/ }) }).first()
    if (await details.getAttribute('open') === null) await details.locator('summary').first().click()
    await panel.getByRole('button', { name: 'Compare course versions', exact: true }).click()
    await panel.getByRole('button', { name: 'Compare ' + target.course_title, exact: true }).click()
    await panel.getByRole('button', { name: 'Review upgrade choice', exact: true }).click()
    const region = panel.getByRole('region', { name: 'Optional upgrade choice', exact: true })
    await region.getByRole('checkbox').check()
    await hold('/upgrade-choices', 'POST'); await region.getByRole('button', { name: 'Save my upgrade choice', exact: true }).click()
    await capture('Saving your optional upgrade choice', 'choice-saving-' + width); assert.equal(writes.length, 0)
    await release(); await region.getByRole('button', { name: 'Check saved choice', exact: true }).waitFor()
    await hold('/upgrade-choices/' + decision.decision_id, 'GET'); await region.getByRole('button', { name: 'Check saved choice', exact: true }).click()
    await capture('Checking the saved optional choice', 'choice-checking-' + width); assert.equal(writes.length, 1)
    await release(); const button = region.getByRole('button', { name: 'Switch to ' + target.course_title, exact: true }); await button.waitFor()
    await hold('/upgrade-activations', 'POST'); await button.focus(); await button.press('Enter')
    await capture('Sending your course switch', 'switch-sending-' + width); assert.equal(writes.length, 1)
    await release(); await region.getByRole('button', { name: 'Check saved switch', exact: true }).waitFor()
    await hold('/upgrade-activations/' + decision.activation_request.request_id, 'GET'); await region.getByRole('button', { name: 'Check saved switch', exact: true }).click()
    await capture('Checking the saved course switch', 'switch-checking-' + width); assert.equal(writes.length, 2)
    await release(); await region.getByText(/course choice has a saved receipt/).waitFor(); assert.equal(writes.length, 2)
  }
  for (const item of review.captures) { assert.equal(item.pageWidth, item.viewport.width); assert.deepEqual(JSON.parse(await readFile(`${review.out}/${item.id}.axe.json`, 'utf8')), []) }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ delayedSyntheticResponses: true, repeatedWritesDuringChecks: 0, actualLearners: 0 })
} catch (error) { review.observations.push({ failed: true, message: String(error) }); throw error }
finally { unblock?.(); await review.flush(); await review.browser.close() }
