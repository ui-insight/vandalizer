import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL })
const { page } = review
page.setDefaultTimeout(45000)
page.setDefaultNavigationTimeout(60000)
const base = { user_id: 'learner', name: 'Alex Morgan', email: 'learner@example.test', level: 'novice', total_xp: 125, modules_completed: 1, modules_total: 11, certified: false, certified_at: null, last_activity_date: '2026-10-05', unlocked: false, updated_at: null }
const rows = [
  { ...base, progress_id: 'preserved', enrollment_id: 'preserved', course_title: 'Your previous course', course_version: 'continuation-1', enrollment_state: 'completed', is_active: false, can_unlock: false, certified: true, modules_completed: 11 },
  { ...base, progress_id: 'selected', enrollment_id: 'selected', course_title: 'Your selected course', course_version: 'candidate-2', enrollment_state: 'active', is_active: true, can_unlock: true },
  { ...base, user_id: 'needs-review', name: 'Case needing review', progress_id: 'inconsistent', course_title: 'Course needs reconciliation', can_unlock: false, reconciliation_error: 'Multiple enrollments reference this progress record', modules_total: 0, modules_completed: 0 },
]
const recoveryWrites = []
let history = []
let completedRecovery = null
const recoveryReview = { user_id: 'learner', enrollment_id: 'selected', course_version: 'candidate-2', course_title: 'Your selected course', manifest_sha256: 'a'.repeat(64), selection_revision: 0, review_sha256: 'b'.repeat(64), kind: 'attempt', write_id: null, attempt_id: 'c'.repeat(32), module_id: 'foundations', module_title: 'Foundations', attempt_state: 'evaluating', in_flight: false, can_recover: true, explanation: 'Reconcile this interrupted evaluation without grading again. A saved result is retained; an evaluation without a saved grade ends without credit.', operation: null, started_at: null, total_xp: 125, certified: false }
const writes = []
await page.route('**/api/auth/config', route => route.fulfill({ json: { auth_methods: ['password'], oauth_providers: [], trial_system_enabled: false } }))
await page.route('**/api/auth/me', route => route.fulfill({ json: { id: 'reviewer', user_id: 'reviewer', email: 'reviewer@example.test', name: 'Admin reviewer', is_admin: true, is_staff: true, is_demo_user: false, current_team: 'team-1', current_team_uuid: 'team-1' } }))
await page.route('**/api/admin/**', route => {
  const url = new URL(route.request().url()), path = url.pathname
  if (path === '/api/admin/certifications') return route.fulfill({ json: { items: rows, total: rows.length, capped: false } })
  if (path.endsWith('/recovery')) {
    if (route.request().method() === 'GET') return route.fulfill({ json: { review: completedRecovery ? { ...recoveryReview, can_recover: false, kind: 'none', attempt_state: null, explanation: 'No interrupted completion needs recovery.' } : recoveryReview, can_apply: true, history } })
    const body = route.request().postDataJSON()
    recoveryWrites.push(body)
    assert.equal(url.searchParams.get('enrollment_id'), 'selected')
    if (!completedRecovery) {
      completedRecovery = { request_id: body.request_id, enrollment_id: 'selected', status: 'interrupted_before_grade', attempt_id: recoveryReview.attempt_id, actor_user_id: 'reviewer', reason: body.reason }
      history = [{ request_id: body.request_id, actor_user_id: 'reviewer', reason: body.reason, state: 'completed', created_at: '2026-10-05T20:00:00Z', attempt_id: recoveryReview.attempt_id, write_id: null, review_sha256: body.review_sha256, review: recoveryReview, can_resume: false, result: completedRecovery }]
      return route.fulfill({ status: 503, json: { detail: 'Synthetic lost recovery response' } })
    }
    assert.deepEqual(body, recoveryWrites.at(-2))
    return route.fulfill({ json: completedRecovery })
  }
  if (path.endsWith('/unlock')) {
    writes.push({ enrollment: url.searchParams.get('enrollment_id'), body: route.request().postDataJSON() })
    rows[1].unlocked = route.request().postDataJSON().unlocked
    return route.fulfill({ json: { user_id: 'learner', unlocked: rows[1].unlocked, enrollment_id: 'selected' } })
  }
  if (path === '/api/admin/system/version') return route.fulfill({ json: { current: '5.0.0', update_available: false } })
  if (path === '/api/admin/catalog/status') return route.fulfill({ json: { update_available: false } })
  if (path === '/api/admin/telemetry/optin') return route.fulfill({ json: { show_banner: false } })
  return route.fallback()
})
try {
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    history = []; completedRecovery = null
    await page.goto(review.baseURL + '/admin?tab=certifications', { waitUntil: 'domcontentloaded' })
    await page.getByText('Your selected course', { exact: true }).waitFor()
    const previous = page.getByRole('row').filter({ hasText: 'Your previous course' })
    const selected = page.getByRole('row').filter({ hasText: 'Your selected course' })
    const inconsistent = page.getByRole('row').filter({ hasText: 'Course needs reconciliation' })
    assert.equal(await previous.getByRole('button', { name: /^Unlock prerequisites/ }).isDisabled(), true)
    assert.equal(await inconsistent.getByRole('button').isDisabled(), true)
    assert.equal(await selected.getByRole('button', { name: /^Unlock prerequisites/ }).isEnabled(), true)
    await review.capture('course-history-' + width, 'Synthetic administrator rows; no real learner records or administrator writes.')
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    await selected.getByRole('button', { name: /^Unlock prerequisites/ }).click()
    await selected.getByRole('button', { name: /^Re-lock/ }).waitFor()
    assert.equal(writes.at(-1).enrollment, 'selected')
    assert.equal(rows[0].unlocked, false)
    await review.capture('selected-unlock-' + width, 'Only the selected synthetic row changes; history remains read-only.')
    await selected.getByRole('button', { name: 'Review completion recovery for Alex Morgan', exact: true }).click()
    const recovery = page.getByRole('region', { name: 'Completion recovery: Alex Morgan', exact: true })
    await recovery.getByRole('button', { name: 'Apply reviewed recovery', exact: true }).waitFor()
    assert.equal(await recovery.getByRole('button', { name: 'Apply reviewed recovery', exact: true }).isDisabled(), true)
    await recovery.scrollIntoViewIfNeeded()
    await review.capture('recovery-review-' + width, 'Synthetic administrator review only; no live learner access.')
    await recovery.getByLabel('Reason for recovery', { exact: true }).fill('Worker interrupted during assessment; reviewed the original submission.')
    await recovery.getByRole('checkbox').check()
    await recovery.getByRole('button', { name: 'Apply reviewed recovery', exact: true }).click()
    await recovery.getByText('Synthetic lost recovery response', { exact: true }).waitFor()
    await review.capture('recovery-response-uncertain-' + width, 'The original reviewed request is retained after a synthetic lost response.')
    await recovery.getByRole('button', { name: 'Retry this recovery', exact: true }).click()
    await recovery.getByText('Completed recovery', { exact: true }).waitFor()
    assert.equal(rows[1].total_xp, 125)
    assert.equal(history.length, 1)
    await recovery.getByText('Completed recovery', { exact: true }).scrollIntoViewIfNeeded()
    await review.capture('recovery-history-' + width, 'One durable synthetic receipt; same request replayed without new credit.')
    await recovery.getByRole('button', { name: 'Close review', exact: true }).click()
    await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === 'Review completion recovery for Alex Morgan')
    rows[1].unlocked = false
  }
  for (const capture of review.captures) assert.deepEqual(JSON.parse(await readFile(`${review.out}/${capture.id}.axe.json`, 'utf8')), [], `Accessibility violations in ${capture.id}`)
  assert.deepEqual([...review.unmatched], [])
  assert.deepEqual(review.errors, [])
  review.observations.push({ id: 'admin-versioning', writes, recoveryWrites, preservedHistoryChanged: false })
} finally { await review.flush(); await review.browser.close() }
