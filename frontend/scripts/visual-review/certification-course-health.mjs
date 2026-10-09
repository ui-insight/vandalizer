import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL,
  evidenceMode: 'Synthetic course-health delivery on an isolated production build. Actual aggregate/privacy/HTTP behavior separately verified with disposable MongoDB. No learner writes or grading.' })
const { page, context } = review
let mode = 'ready', healthReads = 0
const writes = []
const report = {
  read_only: true, scope: 'all_retained_records', started_at: '2026-10-09T20:00:00Z', observed_at: '2026-10-09T20:00:01Z',
  rows: [
    { source: 'automatic_reviews', course_version: 'v5-agentic-course', manifest_sha256: 'a'.repeat(64), state: 'unavailable', provenance: null, count: 2 },
    { source: 'lab_runs', course_version: 'v5-agentic-course', manifest_sha256: 'a'.repeat(64), state: 'uncertain', provenance: null, count: 1 },
    { source: 'enrollments', course_version: 'v5-agentic-course', manifest_sha256: 'b'.repeat(64), state: 'prepared', provenance: 'explicit_upgrade', count: 3 },
    { source: 'enrollments', course_version: null, manifest_sha256: null, state: 'active', provenance: 'legacy_version_unknown', count: 4 },
  ],
  unavailable_metrics: ['start_failures', 'save_refresh_failures', 'grading_disputes', 'abandonment_rate', 'resume_success', 'bridge_uptake'],
}
await context.route('**/api/auth/config', route => route.fulfill({ json: { auth_methods: ['password'], oauth_providers: [], trial_system_enabled: false } }))
await context.route('**/api/auth/me', route => route.fulfill({ json: { id: 'reviewer', user_id: 'reviewer', email: 'reviewer@example.test', name: 'Staff reviewer', is_admin: true, is_staff: true, is_demo_user: false, current_team: 'team-1', current_team_uuid: 'team-1' } }))
await context.route('**/api/admin/**', route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (request.method() !== 'GET') writes.push(path)
  assert.equal(request.method(), 'GET')
  if (path === '/api/admin/certifications') return route.fulfill({ json: { items: [], total: 0, capped: false } })
  if (path === '/api/admin/certifications/health') {
    healthReads++
    if (mode === 'error') return route.fulfill({ status: 503, json: { detail: 'Course health is unavailable. Retry the report.' } })
    return route.fulfill({ json: { ...report, rows: mode === 'empty' ? [] : report.rows } })
  }
  if (path === '/api/admin/system/version') return route.fulfill({ json: { current: '5.0.0', update_available: false } })
  if (path === '/api/admin/catalog/status') return route.fulfill({ json: { update_available: false } })
  if (path === '/api/admin/telemetry/optin') return route.fulfill({ json: { show_banner: false } })
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  const box = await target.boundingBox()
  assert.ok(box.x >= 0 && box.x + box.width <= review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    mode = 'ready'
    const previousReads = healthReads
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    await page.goto(review.baseURL + '/admin?tab=certifications')
    if (native) await review.setBrowserZoom(2)
    const trigger = page.getByText('Course health by version', { exact: true })
    await trigger.waitFor()
    assert.equal(healthReads, previousReads)
    await trigger.focus(); await page.keyboard.press('Enter')
    await page.getByText('Automatic reviews', { exact: true }).waitFor()
    assert.equal(await page.getByRole('region', { name: 'Course health: v5-agentic-course', exact: true }).count(), 2)
    await capture(`health-records-${width}`, page.getByText('Automatic reviews', { exact: true }))
    await capture(`health-unknown-${width}`, page.getByText('Historical or missing course version', { exact: true }))
    const refresh = page.getByRole('button', { name: 'Refresh course health', exact: true })
    mode = 'error'; await refresh.focus(); await page.keyboard.press('Enter')
    await page.getByRole('alert').filter({ hasText: 'Course health is unavailable' }).waitFor()
    assert.equal(await page.getByText('Automatic reviews', { exact: true }).count(), 0)
    await capture(`health-error-${width}`, page.getByRole('alert').filter({ hasText: 'Course health is unavailable' }))
    mode = 'empty'; await refresh.click()
    await page.getByText('No records were found in the four monitored collections.', { exact: true }).waitFor()
    await capture(`health-empty-${width}`, page.getByText('No records were found in the four monitored collections.', { exact: true }))
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  assert.deepEqual(writes, [])
  review.observations.push({ healthReads, writes, loadedOnlyOnRequest: true, packageSeparation: true, unknownHistoryRetained: true, unavailableNotZero: true })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
