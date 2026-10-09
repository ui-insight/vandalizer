import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'
const data = new URL('../../../backend/certification-data/', import.meta.url)
const read = async name => JSON.parse(await readFile(new URL(name, data), 'utf8'))
const modules = await read('panel-modules.json'), structure = await read('course-structure.json')
const identity = { enrollment_id: 'qa-validation-enrollment', course_version: 'qa-preserved-course', manifest_sha256: 'b'.repeat(64), course_title: 'Preserved course — QA fixture', modules_total: modules.length, module_ids: modules.map(m => m.id), maximum_xp: 2675 }
const course = { ...identity, ...structure, versioned: true, prerequisites: Object.fromEntries(modules.map(m => [m.id, []])), modules }
const progress = { ...identity, learning_position: null, position_revision: 0, id: 'qa-progress', user_id: 'reviewer', modules: {}, total_xp: 0, level: 'novice', certified: false, certified_at: null, last_activity_date: null }
const result = { passed: false, stars: 0, checks: [
  { name: 'Assigned source', passed: true, role: 'required', detail: 'The assigned source was retained.' },
  { name: 'Value review', passed: false, role: 'required', detail: 'Compare the amount with the original source.' },
] }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL || 'http://127.0.0.1:5307', resetStorage: false })
const { page, context } = review
let mode = 'result', release = null
const writes = []
await context.route('**/api/certification/**', async route => {
  const path = new URL(route.request().url()).pathname
  if (route.request().method() !== 'GET') writes.push(path)
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  if (path.endsWith('/validate')) {
    if (mode === 'pending') await new Promise(resolve => { release = resolve })
    return mode === 'unavailable' ? route.fulfill({ status: 503, json: { detail: 'Synthetic unavailable recheck' } }) : route.fulfill({ json: result })
  }
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function capture(id) {
  await review.capture(id, 'Synthetic preserved-course checks in the actual frozen frontend; no real lab validation or earned credit.')
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    mode = 'result'; writes.length = 0
    await page.setViewportSize({ width, height: native ? 1688 : 1000 })
    await page.goto(review.baseURL + '/certification')
    await page.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    await page.getByRole('button', { name: /^1 Foundations/ }).click()
    const challenge = page.getByRole('button', { name: 'Challenge', exact: true })
    await challenge.focus(); await challenge.press('Enter')
    await page.getByRole('button', { name: 'Check Progress', exact: true }).click()
    await page.getByText('Compare the amount with the original source.', { exact: true }).waitFor()
    mode = 'pending'
    const retry = page.getByRole('button', { name: 'Recheck this module', exact: true })
    await retry.focus(); await retry.press('Enter')
    const pending = page.getByText('Previous check results — rechecking this module…', { exact: true })
    await pending.waitFor(); await pending.scrollIntoViewIfNeeded()
    assert.equal(await retry.isDisabled(), true)
    await capture('retained-check-pending-' + width)
    mode = 'unavailable'; release()
    const unavailable = page.getByText('Recheck unavailable. These are previous check results; your earlier feedback is preserved.', { exact: true })
    await unavailable.waitFor(); await unavailable.scrollIntoViewIfNeeded()
    assert.equal(await page.getByText('The assigned source was retained.', { exact: true }).count(), 1)
    assert.equal(await retry.isDisabled(), false)
    await capture('retained-check-unavailable-' + width)
    mode = 'result'; await retry.focus(); await retry.press('Enter')
    await unavailable.waitFor({ state: 'detached' })
    assert.equal(writes.length, 3); assert.ok(writes.every(path => path.endsWith('/foundations/validate')))
  }
  assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ savedFeedbackPreserved: true, explicitRechecks: true, completions: 0, syntheticAPI: true })
} catch(error) { review.observations.push({ failed: true, message: String(error) }); throw error }
finally { release?.(); await review.flush(); await review.browser.close() }
