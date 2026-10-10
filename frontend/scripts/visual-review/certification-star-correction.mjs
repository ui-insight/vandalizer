import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createReview } from './harness.mjs'

const fixture = JSON.parse(await readFile(process.env.REVIEW_FIXTURE, 'utf8'))
const identity = { ...fixture.course, enrollment_id: 'a'.repeat(32) }
const progress = { ...identity, id: 'qa-star-correction', user_id: 'reviewer', modules: {}, learning_position: null,
  position_revision: 0, total_xp: 0, level: 'novice', certified: false, certified_at: null }
const course = { ...identity, versioned: true, progress, prerequisites: Object.fromEntries(identity.modules.map(module => [module.id, []])) }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL,
  evidenceMode: 'Actual frozen module/tool projection, synthetic transport. Lab document list omitted to inspect challenge copy without provisioning. Original criteria preserved; no grading or learner writes.' })
const { page, context, state } = review
const writes = []
await context.route('**/api/certification/**', async route => {
  const request = route.request(), path = new URL(request.url()).pathname
  if (path.endsWith('/journey-events')) return route.fallback()
  if (request.method() !== 'GET') writes.push(path)
  if (path.endsWith('/progress')) return route.fulfill({ json: progress })
  if (path.endsWith('/course')) return route.fulfill({ json: course })
  if (path.endsWith('/credentials')) return route.fulfill({ json: { credentials: [] } })
  if (path.endsWith('/selection-status')) return route.fulfill({ json: { read_only: true, current_enrollment_id: identity.enrollment_id, pending: null } })
  if (path.endsWith('/exercise')) return route.fulfill({ json: { ...fixture.exercise, documents: [] } })
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
const title = fixture.module.editorial_notices[0].title
async function capture(scope, id) {
  const note = scope.getByRole('complementary', { name: title })
  await note.getByText(title, { exact: true }).scrollIntoViewIfNeeded()
  await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1600 : 1000 })
    await page.goto(review.baseURL + '/certification')
    if (native) await review.setBrowserZoom(2)
    const panel = page.locator('[data-cert-panel]')
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    await panel.getByRole('button', { name: /^5 Multi-Step Workflows/ }).click()
    await capture(panel, `learn-${width}`)
    await panel.getByRole('button', { name: 'Challenge', exact: true }).click()
    assert.equal(await panel.getByText(fixture.exercise.star_criteria['3'], { exact: true }).count(), 1)
    await capture(panel, `challenge-${width}`)
    await panel.getByRole('button', { name: 'Return to workspace', exact: true }).click()
    for (const unknown of [false, true]) {
      const cardData = { ...fixture.module, enrollment_id: 'b'.repeat(32) }
      delete cardData.editorial_notices
      if (unknown) for (const key of ['enrollment_id', 'course_version', 'course_title', 'manifest_sha256']) delete cardData[key]
      const id = unknown ? 'unknown' : 'historical'
      state.chatChunks = [{ kind: 'tool_call', tool_name: 'get_certification_module', tool_call_id: id, args: {} },
        { kind: 'tool_result', tool_name: 'get_certification_module', tool_call_id: id, content: cardData }]
      await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Review the original module requirements.')
      await page.getByRole('button', { name: 'Send message', exact: true }).click()
      const card = page.locator('.cert-chat-card').last()
      if (unknown) await card.getByText(/original course version is unavailable/).waitFor()
      await card.getByText(fixture.exercise.star_criteria['3'], { exact: true }).waitFor()
      assert.equal(await card.getByText(fixture.exercise.star_criteria['3'], { exact: true }).count(), 1)
      await capture(card, `${id}-module-${width}`)
    }
  }
  assert.deepEqual(writes, []); assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ courseWrites: writes, originalCriteriaPreserved: true, assessedRulesChanged: false, moduleId: 'multi_step',
    unknownOverviewMatchedWithoutInferringCourse: true })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
