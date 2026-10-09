import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const source = JSON.parse(await readFile(process.env.REVIEW_COURSE_FIXTURE, 'utf8')).before_course
const health = JSON.parse(await readFile(process.env.REVIEW_HEALTH_FIXTURE, 'utf8'))
const course = { ...source, versioned: true, prerequisites: Object.fromEntries(source.modules.map(module => [module.id, []])) }
const lesson = course.modules[0].lessons[1]
const position = { module_id: 'ai_literacy', lesson_id: lesson.id, revision: lesson.revision,
  content_sha256: 'a'.repeat(64), saved_at: '2026-10-09T20:00:00Z' }
course.progress = { ...course.progress, learning_position: position, position_revision: 1,
  modules: { ...course.progress.modules, ai_literacy: { completed: false, stars: 0, attempts: 0, xp_earned: 0, completed_at: null, learning_position: position } } }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL,
  evidenceMode: 'Synthetic learner delivery and failure simulation using retained course content; admin report exported from actual disposable-MongoDB observations. No live learners or assessment writes.' })
const { page, context } = review
const observations = [], allObserved = [], writes = []
let failedTelemetry = false
await context.route('**/api/certification/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (path.endsWith('/journey-events')) {
    const body = request.postDataJSON()
    assert.deepEqual(Object.keys(body).sort(), ['enrollment_id', 'event', 'event_id', 'manifest_sha256'])
    assert.equal(body.enrollment_id, course.enrollment_id)
    assert.equal(body.manifest_sha256, course.manifest_sha256)
    observations.push(body)
    allObserved.push(body)
    if (failedTelemetry) return route.fulfill({ status: 403, json: { detail: 'CSRF validation failed' } })
    return route.fulfill({ json: { recorded: true, assessment_changed: false } })
  }
  if (request.method() !== 'GET') writes.push(path)
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/progress')) return route.fulfill({ json: { ...course, ...course.progress } })
  if (path.endsWith('/position')) return route.fulfill({ status: 409, json: { detail: 'Synthetic saved-place conflict' } })
  if (path.endsWith('/selection-status')) return route.fulfill({ json: { read_only: true, current_enrollment_id: course.enrollment_id, pending: null } })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { overview: 'Synthetic exercise delivery', documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  return route.fallback()
})
await context.route('**/api/auth/config', route => route.fulfill({ json: { auth_methods: ['password'], oauth_providers: [], trial_system_enabled: false } }))
await context.route('**/api/auth/me', route => route.fulfill({ json: { id: 'reviewer', user_id: 'reviewer', email: 'reviewer@example.test', name: 'QA reviewer', is_admin: true, is_staff: true, is_demo_user: false, current_team: 'team-1', current_team_uuid: 'team-1' } }))
await context.route('**/api/admin/**', route => {
  const path = new URL(route.request().url()).pathname
  assert.equal(route.request().method(), 'GET')
  if (path === '/api/admin/certifications') return route.fulfill({ json: { items: [], total: 0, capped: false } })
  if (path === '/api/admin/certifications/health') return route.fulfill({ json: health })
  if (path === '/api/admin/system/version') return route.fulfill({ json: { current: '5.0.0', update_available: false } })
  if (path === '/api/admin/catalog/status') return route.fulfill({ json: { update_available: false } })
  if (path === '/api/admin/telemetry/optin') return route.fulfill({ json: { show_banner: false } })
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded(); await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    observations.length = 0; failedTelemetry = false
    const writesBefore = writes.length
    await page.setViewportSize({ width, height: native ? 1700 : 1000 })
    if (!native && width === 320 && !process.env.REVIEW_REPORT_ONLY) {
    await page.goto(review.baseURL + '/')
    if (native) await review.setBrowserZoom(2)
    await page.getByRole('button', { name: 'Open course without chat', exact: true }).click()
    const panel = page.locator('[data-cert-panel]')
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    await panel.getByRole('heading', { name: lesson.title, exact: true }).waitFor()
    await capture(`restored-lesson-${width}`, panel.getByRole('heading', { name: lesson.title, exact: true }))
    assert.equal(observations.filter(row => row.event === 'saved_lesson_displayed').length, 1)
    failedTelemetry = true
    const navigations = []
    const listener = frame => { if (frame === page.mainFrame()) navigations.push(frame.url()) }
    page.on('framenavigated', listener)
    await panel.getByRole('button', { name: 'Save this place', exact: true }).click()
    await panel.getByText('Your place could not be saved. Reload the saved place before trying again.', { exact: true }).waitFor()
    await capture(`failed-save-telemetry-unavailable-${width}`, panel.getByRole('button', { name: 'Refresh progress', exact: true }))
    assert.ok(observations.some(row => row.event === 'position_save_failed'))
    assert.deepEqual(navigations, [], 'Telemetry CSRF failure cannot reload the learner tab')
    page.off('framenavigated', listener)
    assert.equal(writes.length, writesBefore + 1)
    await panel.getByRole('button', { name: 'Curriculum', exact: true }).click()
    await panel.getByText(course.bridge_path.title, { exact: true }).click()
    await panel.getByRole('button', { name: 'Open assessment: AI Literacy', exact: true }).click()
    await panel.getByRole('button', { name: /Challenge/ }).waitFor()
    await capture(`bridge-entry-${width}`, panel.getByRole('button', { name: /Challenge/ }))
    assert.ok(observations.some(row => row.event === 'bridge_assessment_requested'))
    assert.equal(observations.filter(row => row.event === 'saved_lesson_displayed').length, 1)
    assert.equal(writes.length, writesBefore + 1)
    }
    await page.goto(review.baseURL + '/admin?tab=certifications')
    if (native) await review.setBrowserZoom(2)
    await page.getByText('Course health by version', { exact: true }).click()
    const report = page.getByRole('region', { name: 'Client-reported learning journeys', exact: true })
    await report.waitFor()
    await capture(`journey-report-${width}`, report.getByRole('heading', { name: 'Client-reported learning journeys · last 30 days', exact: true }))
    await capture(`journey-report-counts-${width}`, report.getByText('Reading-place save failed: 1', { exact: true }))
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ received: allObserved, courseWrites: writes, csrfFailureTested: !native && !process.env.REVIEW_REPORT_ONLY, assessmentWrites: 0 })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
