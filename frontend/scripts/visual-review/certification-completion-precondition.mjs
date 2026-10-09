import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const data = new URL('../../../backend/certification-data/', import.meta.url)
const read = async name => JSON.parse(await readFile(new URL(name, data), 'utf8'))
const modules = await read('panel-modules.json'), structure = await read('course-structure.json')
const identity = { enrollment_id: 'qa-completion-enrollment', course_version: 'qa-completion-course', manifest_sha256: 'b'.repeat(64), course_title: 'Preserved course — QA fixture', modules_total: modules.length, module_ids: modules.map(m => m.id), maximum_xp: 2675 }
const course = { ...identity, ...structure, versioned: true, prerequisites: Object.fromEntries(modules.map(m => [m.id, []])), modules }
const progress = { ...identity, learning_position: null, position_revision: 0, id: 'qa-progress', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, last_activity_date: null, pending_completions: [] }

const moduleId = 'ai_literacy', module = modules.find(item => item.id === moduleId)
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5307', resetStorage: false,
  evidenceMode: 'Two actual browser tabs with synthetic completion counter conflicts; real HTTP/persistence checks use disposable MongoDB separately.' })
const { page, context } = review
const requests = []
let completions = 0, original = null
const conflict = 'Module completion changed in another request. Refresh your course and review its saved result before starting another completion'
await context.route('**/api/certification/**', route => {
  const request = route.request(), url = new URL(request.url()), path = url.pathname
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.endsWith('/complete')) {
    assert.equal(request.method(), 'POST')
    const id = url.searchParams.get('request_id'), expected = url.searchParams.get('expected_attempts')
    requests.push({ id, expected }); assert.equal(expected, '0'); assert.ok(id)
    if (completions) return route.fulfill({ status: 409, json: { detail: { code: 'CERTIFICATION_COMPLETION_CHANGED', message: conflict } } })
    completions++; original = id
    progress.modules[moduleId] = { completed: true, stars: 1, completed_at: '2026-10-09', attempts: 1, xp_earned: 125 }
    progress.total_xp = 125
    return route.fulfill({ json: { module_id: moduleId, attempt_id: id, stars: 1, xp_earned: 125, total_xp: 125, level: 'novice', level_up: false, certified: false, validation: { passed: true, stars: 1, checks: [] } } })
  }
  return route.fallback()
})
async function enter(target) {
  if (target.url().startsWith(review.baseURL)) await target.evaluate(() => sessionStorage.clear())
  await target.goto(review.baseURL + '/certification', { waitUntil: 'networkidle' })
  await target.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
  await target.getByRole('button', { name: new RegExp(`^${module.number} ${module.title}`) }).click()
  await target.getByRole('button', { name: 'Challenge', exact: true }).click()
  return target.getByRole('button', { name: 'Complete Module', exact: true })
}
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1688 : 1000 })
    completions = 0; original = null; requests.length = 0; progress.modules = {}; progress.total_xp = 0
    const first = await context.newPage(); first.on('pageerror', error => review.errors.push(error.message))
    const firstButton = await enter(first), secondButton = await enter(page)
    await firstButton.click()
    await first.waitForFunction(() => document.body.textContent.includes('Module Complete'))
    await secondButton.focus(); await secondButton.press('Enter')
    await page.getByText(conflict, { exact: true }).waitFor()
    const attempts = page.getByText('1 attempt · Completed', { exact: true })
    await attempts.waitFor(); await attempts.scrollIntoViewIfNeeded()
    assert.equal(requests.length, 2); assert.equal(completions, 1); assert.notEqual(requests[1].id, original)
    assert.equal(await page.getByRole('button', { name: 'Complete Module', exact: true }).count(), 0)
    assert.equal(await page.getByRole('region', { name: 'Pending certification completion', exact: true }).count(), 0)
    assert.equal(await page.evaluate(key => sessionStorage.getItem(key), `certification-completion:${identity.enrollment_id}:${moduleId}`), null)
    await review.capture('stale-tab-refreshed-' + width, 'Second tab sends its original counter, receives a definite conflict, refreshes earned state and clears only its stale request; no automatic resubmission.')
    await first.close()
  }
  for (const item of review.captures) { assert.equal(item.pageWidth, item.viewport.width); assert.deepEqual(JSON.parse(await readFile(`${review.out}/${item.id}.axe.json`, 'utf8')), []) }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ twoBrowserTabs: true, newRequestIds: true, originalCounter: 0, completedAttempts: 1, automaticResubmission: false, actualLearners: 0 })
} catch (error) { review.observations.push({ failed: true, message: String(error) }); throw error }
finally { await review.flush(); await review.browser.close() }
