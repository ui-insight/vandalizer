import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5298',
  evidenceMode: 'Synthetic administrator access changes and saved history. All writes are intercepted; atomic audit, permission and credit preservation are separately tested in isolated MongoDB.' })
const { page, context } = review
page.setDefaultTimeout(30000)
const base = { user_id: 'learner', name: 'Alex Morgan', email: 'learner@example.test', progress_id: 'progress', enrollment_id: 'a'.repeat(32),
  course_title: 'Preserved certification course', course_version: 'legacy-2026-10-02.1', enrollment_state: 'active', is_active: true, can_unlock: true,
  level: 'novice', total_xp: 150, modules_completed: 1, modules_total: 11, certified: false, certified_at: null,
  last_activity_date: null, unlocked: false, updated_at: null }
const summary = { read_only: true, observed_at: '2026-10-08T10:00:00Z', position_status: 'not_recorded', last_saved_lesson: null,
  pending_credential: false, explanation: 'Recorded state only. Refresh for current status; opening this view does not retry, grade or change a course.',
  pending_completions: [], recent_completions: [], older_completions_available: false }
const reason = 'Restore module access for a learner continuing the preserved course after a browser change. Existing assessed work and original course requirements remain in place.'
let mode = 'change', unlocked = false, events = [], loseOnce = true
const requests = []
const row = () => ({ ...base, unlocked, ...(mode === 'historical' ? { enrollment_id: null, course_version: null, course_title: 'Historical course', is_active: null } : {}) })
await context.route('**/api/auth/config', route => route.fulfill({ json: { auth_methods: ['password'], oauth_providers: [] } }))
await context.route('**/api/auth/me', route => route.fulfill({ json: { id: 'reviewer', user_id: 'reviewer', email: 'reviewer@example.test', name: 'Staff reviewer', is_admin: true, is_staff: true, is_demo_user: false, current_team: 'team-1', current_team_uuid: 'team-1' } }))
await context.route('**/api/admin/**', route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  if (path === '/api/admin/certifications/learner/unlock') {
    assert.equal(request.method(), 'PUT')
    assert.equal(url.searchParams.get('enrollment_id'), base.enrollment_id)
    const body = request.postDataJSON()
    assert.deepEqual(Object.keys(body).sort(), ['reason', 'request_id', 'unlocked'])
    assert.equal(body.reason, reason); assert.equal(body.unlocked, true); assert.match(body.request_id, /^[a-f0-9]{32}$/)
    requests.push(body)
    if (!events.length) events.push({ ...body, actor_user_id: 'authorized-administrator-with-a-long-reference', previous_unlocked: false, recorded_at: '2026-10-08T10:00:00Z', credit_effect: 'none' })
    else assert.equal(body.request_id, events[0].request_id)
    unlocked = true
    if (loseOnce) { loseOnce = false; return route.fulfill({ status: 503, json: { detail: 'Synthetic response uncertainty. Inspect saved access or retry the same request.' } }) }
    return route.fulfill({ json: { user_id: base.user_id, unlocked } })
  }
  assert.equal(request.method(), 'GET')
  if (path === '/api/admin/certifications') return route.fulfill({ json: { items: [row()], total: 1, capped: false } })
  if (path === '/api/admin/certifications/learner') {
    assert.equal(url.searchParams.get('enrollment_id'), row().enrollment_id)
    return route.fulfill({ json: { ...row(), modules: {}, support_summary: { ...summary, access_changes: {
      state: mode === 'historical' ? 'not_recorded' : mode === 'unavailable' ? 'unavailable' : 'recorded',
      historical_unlocked: unlocked, older_available: false, changes: mode === 'change' ? events : [],
    } } } })
  }
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
    const suffix = native ? 'native' : width
    mode = 'change'; unlocked = false; events = []; loseOnce = true
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    await page.goto(review.baseURL + '/admin?tab=certifications')
    if (native) await review.setBrowserZoom(2)
    const trigger = page.getByRole('button', { name: /Unlock prerequisites for Alex/ })
    await trigger.click()
    assert.ok((await trigger.boundingBox()).height >= 44)
    const form = page.getByRole('region', { name: 'Change module access: Alex Morgan', exact: true })
    assert.equal(await form.evaluate(node => document.activeElement === node), true)
    await form.scrollIntoViewIfNeeded()
    assert.equal(await form.getByRole('button', { name: 'Save access change', exact: true }).isDisabled(), true)
    await capture(`reason-required-${suffix}`)
    console.log('heading-layout', await form.getByRole('heading').evaluate(node => ({ text: node.textContent, rect: node.getBoundingClientRect().toJSON(), scrollLeft: node.scrollLeft, width: node.scrollWidth, whiteSpace: getComputedStyle(node).whiteSpace, textIndent: getComputedStyle(node).textIndent })))
    await form.getByLabel('Reason for access change').fill(reason)
    await capture(`reason-ready-${suffix}`)
    await form.getByRole('button', { name: 'Save access change', exact: true }).click()
    await form.getByRole('alert').waitFor()
    assert.equal(await form.getByLabel('Reason for access change').isDisabled(), true)
    await capture(`uncertain-${suffix}`)
    const retry = form.getByRole('button', { name: 'Retry same access change' })
    assert.ok((await retry.boundingBox()).height >= 44)
    await retry.click()
    await form.waitFor({ state: 'hidden' })
    try { await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label')?.startsWith('Re-lock prerequisites for')) }
    catch (error) { console.log('focus-diagnostic', await page.evaluate(() => ({ active: document.activeElement?.outerHTML, buttons: [...document.querySelectorAll('button[aria-label*="prerequisites"]')].map(node => node.outerHTML) }))); throw error }
    assert.equal(events.length, 1)
    for (mode of ['change', 'historical', 'unavailable']) {
      await page.goto(review.baseURL + '/admin?tab=certifications')
      const status = page.getByRole('button', { name: /View learning status for/ })
      await status.click()
      const region = page.getByRole('region', { name: 'Learning status: Alex Morgan', exact: true })
      await region.getByRole('heading', { name: 'Administrator access changes' }).waitFor()
      await region.getByRole('heading', { name: 'Administrator access changes' }).scrollIntoViewIfNeeded()
      if (mode === 'change') await region.getByText(reason, { exact: true }).waitFor()
      if (mode === 'historical') await region.getByText(/reason or authorizing administrator/).waitFor()
      if (mode === 'unavailable') await region.getByText(/Access-change history is unavailable/).waitFor()
      await capture(`history-${mode}-${suffix}`)
      await region.getByRole('button', { name: 'Close status' }).click()
      await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label')?.startsWith('View learning status for'))
    }
  }
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push({ simulatedRequests: requests.length, writesIntercepted: true, reasonRequired: true, retryUsesOriginalIdentity: true, separateCreditAndAccess: true, focusReturned: true })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
