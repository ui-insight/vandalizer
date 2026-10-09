import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const data = new URL('../../../backend/certification-data/', import.meta.url)
const read = async name => JSON.parse(await readFile(new URL(name, data), 'utf8'))
const modules = await read('panel-modules.json')
const structure = await read('course-structure.json')
const outcomes = await read('drafts/v5.0/outcomes.json')
const identity = { enrollment_id: 'comparison-source', course_version: 'continuation-fixture', manifest_sha256: 'a'.repeat(64), course_title: 'Your existing certification course', modules_total: modules.length, module_ids: modules.map(m => m.id), maximum_xp: 2675 }
const course = { ...structure, ...identity, versioned: true, prerequisites: Object.fromEntries(modules.map(m => [m.id, []])), modules }
const progress = { ...identity, id: 'comparison-progress', user_id: 'reviewer', modules: { foundations: { completed: true, stars: 1, xp_earned: 125, completed_at: '2025-01-01', attempts: 1 } }, total_xp: 125, level: 'novice', certified: false, certified_at: null, last_activity_date: null, learning_position: null }
const target = { course_version: 'v5-comparison-fixture', course_title: 'Vandalizer 5.0 — Supervise document work', description: 'Compare source review, scope, recovery and delivery requirements before deciding on a future optional upgrade.', manifest_sha256: 'b'.repeat(64), required_outcome_count: 33 }
const preview = { policy: 'optional', can_activate: false, preview_sha256: 'c'.repeat(64), source: { ...identity, provenance: 'legacy_version_unknown', total_xp: 125, certified: false, credential_preserved: false, completed_modules: [{ module_id: 'foundations', title: 'Foundations', xp_earned: 125, stars: 1, completed_at: '2025-01-01' }], has_saved_place: true }, target: { ...target, transferred_outcome_count: 0, modules: outcomes.modules.map(module => ({ module_id: module.module_id, title: modules.find(m => m.id === module.module_id).title, outcomes: module.outcomes.map(outcome => ({ outcome_id: outcome.id, statement: outcome.statement, disposition: 'requires_assessment', reason: 'No confirmed outcome equivalence.' })) })) }, saved_work: [{ kind: 'prepared_labs', label: 'Saved lab inputs', count: 1 }, { kind: 'saved_lab_runs', label: 'Saved lab runs', count: 2 }, { kind: 'saved_learner_decisions', label: 'Saved learner decisions', count: 3 }], work_in_flight: true, unfinished_answers: true, credential_needs_preservation: false }
preview.work_in_flight = false
preview.preservation_plan = {
  policy: 'retain_with_original_enrollment', source_enrollment_id: identity.enrollment_id,
  read_only: true, can_activate: false, credit_transferred: false, reconciliation_required_count: 2, plan_sha256: 'd'.repeat(64),
  entries: [
    { kind: 'saved_lab_runs', label: 'Lab run', record_id: '1'.repeat(32), module_id: 'foundations', module_title: 'Original Foundations', state: 'uncertain', proposed_action: 'reconcile_operation', reconciliation_required: true, explanation: 'Resolve the original run and any external effects before a switch. Do not rerun it to discover whether it finished.' },
    { kind: 'saved_lab_runs', label: 'Lab run', record_id: '2'.repeat(32), module_id: 'validation_qa', module_title: 'Validation & QA', state: 'prepared', proposed_action: 'retain_unexecuted_work', reconciliation_required: false, explanation: 'Keep the prepared run with its original course. This plan does not approve or execute it.' },
    { kind: 'saved_automatic_reviews', label: 'Automatic assessment', record_id: '3'.repeat(32), module_id: 'validation_qa', module_title: 'Validation & QA', state: 'evaluating', proposed_action: 'reconcile_operation', reconciliation_required: true, explanation: 'Resolve the original automatic assessment before a switch. Keep its original evidence and do not start another assessment.' },
    { kind: 'saved_automatic_reviews', label: 'Automatic assessment', record_id: '4'.repeat(32), module_id: 'governance', module_title: 'Collaboration & Governance', state: 'unavailable', proposed_action: 'retain_original_result', reconciliation_required: false, explanation: 'Keep the original automatic feedback or technical failure with its original course. This does not award or transfer credit.' },
  ],
}
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5294', evidenceMode: 'Synthetic transport tests proposed per-record preservation UI only. No transition, database, assessment, model or real learner operation.' })
const { page, context } = review
page.setDefaultTimeout(15000)
const writes = []
await context.route('**/api/certification/**', async route => {
  const req = route.request(), path = new URL(req.url()).pathname
  if (req.method() !== 'GET') writes.push(path)
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/upgrade-options')) return route.fulfill({ json: { enrollment_id: identity.enrollment_id, policy: 'optional', can_activate: false, courses: [target] } })
  if (path.endsWith('/upgrade-preview')) return route.fulfill({ json: preview })
  return route.fallback()
})
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded(); await review.capture(id)
  const current = review.captures.at(-1)
  assert.equal(current.pageWidth, current.viewport.width)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  console.log(id)
}
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1700 : 950 })
    await page.goto(review.baseURL + '/certification')
    if (native) await review.setBrowserZoom(2)
    const panel = page.locator('[data-cert-panel="true"]')
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    await panel.getByText('Course progress and credential', { exact: true }).click()
    const section = panel.getByRole('region', { name: 'Course versions are your choice', exact: true })
    await section.getByRole('button', { name: 'Compare course versions', exact: true }).click()
    await section.getByRole('button', { name: `Compare ${target.course_title}`, exact: true }).click()
    const summary = section.getByText('Saved work preservation plan', { exact: true })
    await capture('closed-plan-' + width, summary)
    await summary.focus(); await page.keyboard.press('Enter')
    const plan = summary.locator('..')
    assert.equal(await plan.getAttribute('open'), '')
    const unresolved = plan.getByText(/2 saved operations need resolution/)
    await capture('unresolved-work-' + width, unresolved)
    await capture('retained-prepared-and-review-' + width, plan.getByText(/Keep the prepared run with its original course/))
    const reference = plan.getByText('Original work reference', { exact: true }).last()
    await reference.click()
    await capture('original-feedback-reference-' + width, plan.getByText('4'.repeat(32), { exact: true }))
    assert.equal(await section.getByRole('button', { name: /Activate|Switch|Retry run|Start new course/ }).count(), 0)
    assert.equal(await section.getByText(/A course operation is still in progress/).count(), 0)
    await section.getByRole('button', { name: 'Close comparison', exact: true }).click()
    await page.waitForFunction(() => document.activeElement?.textContent === 'Compare course versions')
  }
  assert.deepEqual(writes, []); assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ perRecordProposedPreservation: true, inactiveWriteDoesNotHideUncertainRun: true, keyboardDisclosure: true, originalReference: true, certificationWrites: 0, activation: false })
} catch (error) { await review.capture('blocked', String(error)); throw error } finally { await review.flush(); await review.browser.close() }
