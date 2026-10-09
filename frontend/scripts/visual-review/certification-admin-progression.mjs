import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: 'http://127.0.0.1:5294',
  evidenceMode: 'Synthetic admin presentation and CSV export; authenticated policy rejection and non-mutation are separately verified against disposable MongoDB.' })
const { page, context } = review
const base = { user_id: 'learner', name: 'Alex Morgan', email: 'learner@example.test', level: 'novice', total_xp: 0, modules_completed: 0, modules_total: 11, certified: false, certified_at: null, last_activity_date: null, unlocked: false, updated_at: null }
const rows = [
  { ...base, progress_id: 'current', enrollment_id: 'a'.repeat(32), course_title: 'Agentic certification', course_version: 'v5.0-qa', enrollment_state: 'active', is_active: true, can_unlock: false,
    learning_order: 'any_order', progression_policy_id: 'required-outcomes-flexible-order.1', unlock_unavailable_reason: 'Any study order; required outcomes still apply.' },
  { ...base, user_id: 'legacy', name: 'Original learner', progress_id: 'legacy', enrollment_id: 'b'.repeat(32), course_title: 'Preserved original course', course_version: 'legacy-qa', enrollment_state: 'completed', is_active: false, can_unlock: false, total_xp: 1850, modules_completed: 11, certified: true },
]
await context.route('**/api/auth/config', route => route.fulfill({ json: { auth_methods: ['password'], oauth_providers: [], trial_system_enabled: false } }))
await context.route('**/api/auth/me', route => route.fulfill({ json: { id: 'reviewer', user_id: 'reviewer', email: 'reviewer@example.test', name: 'Admin reviewer', is_admin: true, is_staff: true, is_demo_user: false, current_team: 'team-1', current_team_uuid: 'team-1' } }))
const reads = []
await context.route('**/api/admin/**', route => {
  const request = route.request(), path = new URL(request.url()).pathname
  assert.equal(request.method(), 'GET'); reads.push(path)
  if (path === '/api/admin/certifications') return route.fulfill({ json: { items: rows, total: rows.length, capped: false } })
  if (path === '/api/admin/system/version') return route.fulfill({ json: { current: '5.0.0', update_available: false } })
  if (path === '/api/admin/catalog/status') return route.fulfill({ json: { update_available: false } })
  if (path === '/api/admin/telemetry/optin') return route.fulfill({ json: { show_banner: false } })
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function capture(id) {
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    await page.goto(review.baseURL + '/admin?tab=certifications')
    if (native) await review.setBrowserZoom(2)
    const current = page.getByRole('row').filter({ hasText: 'Agentic certification' })
    await current.getByText('Any study order', { exact: true }).waitFor()
    assert.equal(await current.getByRole('button', { name: /Unlock prerequisites/ }).count(), 0)
    await page.getByRole('region', { name: 'Certification progress — scroll for more columns', exact: true }).scrollIntoViewIfNeeded()
    await capture(`course-identity-${native ? 'native' : width}`)
    await current.getByText('Any study order', { exact: true }).scrollIntoViewIfNeeded()
    await capture(`course-policy-${native ? 'native' : width}`)
    const download = page.waitForEvent('download')
    await page.getByRole('button', { name: /Export/ }).click()
    const file = await download
    const saved = `${review.out}/policy-${width}.csv`
    await file.saveAs(saved)
    const text = await readFile(saved, 'utf8')
    assert.ok(text.includes('Study Order') && text.includes('Progression Policy'))
    const row = text.split('\n').find(line => line.includes('Agentic certification'))
    assert.ok(row.includes('not applicable') && row.includes('any_order') && row.includes('required-outcomes-flexible-order.1'))
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push({ noPolicyOverrideControl: true, requiredOutcomesStillApply: true, csvPolicyMatchesRow: true, adminWrites: 0, reads })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
