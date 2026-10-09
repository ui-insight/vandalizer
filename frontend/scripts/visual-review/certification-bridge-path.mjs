import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const root = process.env.REVIEW_PACKAGE
assert.ok(root, 'Use an isolated assembled course package')
const course = { ...JSON.parse(await readFile(`${root}/public-course.json`, 'utf8')), enrollment_id: 'a'.repeat(32) }
assert.equal(course.bridge_path.state, 'design_draft')
assert.equal(course.bridge_path.required_outcomes, 33)
const progress = { ...course, id: 'qa-bridge', user_id: 'reviewer', modules: {}, total_xp: 0,
  level: 'novice', certified: false, learning_position: null, position_revision: 0 }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL,
  evidenceMode: 'Actual pinned unpublished bridge path; synthetic API reads. No assessment submission or credit transfer.' })
const { page, context } = review
const writes = []
await context.route('**/api/certification/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (request.method() !== 'GET') writes.push(path)
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/selection-status')) return route.fulfill({ json: { read_only: true, current_enrollment_id: course.enrollment_id, pending: null } })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  const shot = review.captures.at(-1), box = await target.boundingBox()
  assert.equal(shot.pageWidth, shot.viewport.width)
  assert.ok(box.x >= 0 && box.x + box.width <= shot.viewport.width)
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1688 : 1000 })
    await page.goto(review.baseURL + '/certification')
    if (native) await review.setBrowserZoom(2)
    const panel = page.locator('[data-cert-panel]')
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    const summary = panel.getByText(course.bridge_path.title, { exact: true })
    await summary.focus(); await page.keyboard.press('Enter')
    assert.equal(await panel.getByRole('button', { name: /^Open assessment:/ }).count(), 11)
    for (const stage of course.bridge_path.stages) {
      await capture(`bridge-${stage.id}-${width}`, panel.getByRole('heading', { name: stage.title, exact: true }))
    }
    const rules = panel.getByText('How this path uses your earlier experience', { exact: true })
    await rules.focus(); await page.keyboard.press('Enter')
    await capture(`bridge-rules-${width}`, rules)
    const start = panel.getByRole('button', { name: 'Open assessment: AI Literacy', exact: true })
    await start.focus(); await page.keyboard.press('Enter')
    const scenario = panel.getByRole('region', { name: 'Scenario assessment', exact: true })
    await scenario.waitFor()
    assert.ok(await scenario.getByRole('radio').count() > 0)
    assert.equal(await panel.getByRole('button', { name: 'Challenge', exact: true }).evaluate(element => element === document.activeElement), true)
    await capture(`bridge-assessment-${width}`, scenario.getByRole('heading', { name: 'Practice your judgment', exact: true }))
  }
  assert.deepEqual(writes, [])
  assert.deepEqual(review.errors, [])
  assert.deepEqual([...review.unmatched], [])
  review.observations.push({ stages: 4, modules: 11, requiredOutcomes: 33, keyboardAssessmentEntry: true, writes, creditTransferred: false })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
