import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { createReview } from './harness.mjs'

const fixture = JSON.parse(await readFile(process.env.REVIEW_FIXTURE, 'utf8'))
const { lesson } = fixture
const identity = { ...fixture.course, enrollment_id: 'a'.repeat(32) }
const position = { module_id: lesson.module_id, lesson_id: lesson.lesson_id, revision: lesson.lesson_revision,
  content_sha256: createHash('sha256').update(lesson.content).digest('hex'), saved_at: '2026-10-09T20:00:00Z' }
const progress = { ...identity, id: 'qa-editorial', user_id: 'reviewer', modules: {
  [lesson.module_id]: { completed: false, stars: 0, attempts: 0, xp_earned: 0, learning_position: position },
}, learning_position: position, position_revision: 1, total_xp: 0, level: 'novice', certified: false, certified_at: null }
const course = { ...identity, versioned: true, progress,
  prerequisites: Object.fromEntries(identity.modules.map(module => [module.id, []])) }
const review = await createReview({ output: process.env.REVIEW_OUTPUT, baseURL: process.env.REVIEW_BASE_URL,
  evidenceMode: 'Retained historical package plus actual API/tool correction projection, delivered through synthetic transport. Historical card intentionally omits new notice metadata. No learner or assessment changes.' })
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
  if (path.endsWith('/exercise')) return route.fulfill({ json: { documents: [], instructions: [], expected_fields: [], expected_values: {}, star_criteria: {} } })
  return route.fallback()
})
const native = process.env.REVIEW_NATIVE_PROFILE_ZOOM === '2'
const noticeTitle = lesson.editorial_notices[0].title
async function capture(id, target) {
  await target.scrollIntoViewIfNeeded(); await review.capture(id)
  assert.deepEqual(JSON.parse(await readFile(`${review.out}/${id}.axe.json`, 'utf8')), [])
  assert.equal(review.captures.at(-1).pageWidth, review.captures.at(-1).viewport.width)
  console.log(id)
}
async function inspect(scope, prefix) {
  const notice = scope.getByRole('complementary', { name: noticeTitle })
  await notice.waitFor()
  await capture(prefix + '-correction', notice.getByText(noticeTitle, { exact: true }))
  await capture(prefix + '-preservation', notice.getByText(/Your saved course, assessment requirements and earned credit are preserved/))
  assert.match(await scope.innerText(), /Every result carries a quality score/)
}
try {
  for (const width of native ? [780] : [320, 1440]) {
    await page.setViewportSize({ width, height: native ? 1600 : 1000 })
    await page.goto(review.baseURL)
    if (native) await review.setBrowserZoom(2)
    await page.getByRole('button', { name: 'Open course without chat', exact: true }).click()
    const panel = page.locator('[data-cert-panel]')
    await panel.getByRole('combobox', { name: 'Learning panel position', exact: true }).selectOption('fullscreen')
    await panel.getByRole('heading', { name: lesson.title, exact: true }).waitFor()
    await inspect(panel, `panel-${width}`)
    await panel.getByRole('button', { name: 'Return to workspace', exact: true }).click()
    const historical = { ...lesson, enrollment_id: 'b'.repeat(32) }
    delete historical.editorial_notices
    state.chatChunks = [{ kind: 'tool_call', tool_name: 'get_certification_lesson', tool_call_id: 'historical', args: {} },
      { kind: 'tool_result', tool_name: 'get_certification_lesson', tool_call_id: 'historical', content: historical }]
    await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Review this preserved lesson.')
    await page.getByRole('button', { name: 'Send message', exact: true }).click()
    const card = page.locator('.cert-chat-card').last()
    await inspect(card, `historical-chat-${width}`)
    assert.equal(await card.getByRole('button', { name: 'Save my place', exact: true }).count(), 0)
    const unversioned = { ...historical }
    for (const key of ['enrollment_id', 'course_version', 'course_title', 'manifest_sha256', 'lesson_id', 'lesson_revision', 'maximum_stars', 'credit_basis']) delete unversioned[key]
    state.chatChunks = [{ kind: 'tool_call', tool_name: 'get_certification_lesson', tool_call_id: 'unknown-history', args: {} },
      { kind: 'tool_result', tool_name: 'get_certification_lesson', tool_call_id: 'unknown-history', content: unversioned }]
    await page.getByRole('textbox', { name: 'Message input', exact: true }).fill('Review this older lesson without version metadata.')
    await page.getByRole('button', { name: 'Send message', exact: true }).click()
    const oldCard = page.locator('.cert-chat-card').last()
    await oldCard.getByText(/The original course version is unavailable/).waitFor()
    await inspect(oldCard, `unversioned-chat-${width}`)
    assert.equal(await oldCard.getByRole('button', { name: 'Save my place', exact: true }).count(), 0)
  }
  assert.deepEqual(writes, []); assert.deepEqual(review.errors, []); assert.deepEqual([...review.unmatched], [])
  review.observations.push({ courseWrites: writes, originalBodyPreserved: true, historicalCardHasNoticeMetadata: false,
    exactManifest: identity.manifest_sha256, lessonId: lesson.lesson_id, unversionedTextMatchedWithoutInferringCourse: true, assessedRequirementsChanged: false })
} catch (error) { await review.capture('blocked', String(error)); throw error }
finally { await review.flush(); await review.browser.close() }
